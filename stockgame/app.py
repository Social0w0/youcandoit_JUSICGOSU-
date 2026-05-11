from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from models import db, User, Stock, Holding, Event, PriceHistory, Earnings, Transfer
import random
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

import os

app = Flask(__name__)
CORS(app)

db_url = os.getenv("DATABASE_URL", "sqlite:///db.sqlite3")

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,   # 쿼리 전에 연결 살아있는지 확인
    'pool_recycle': 300,     # 5분마다 연결 재활용
}
db.init_app(app)

scheduler = BackgroundScheduler()

# -------------------------
# 이벤트 데이터
# -------------------------
EVENTS = {
    "positive": [
        ("신제품 출시 성공!", "혁신적인 신제품이 시장에서 폭발적인 반응을 얻고 있습니다."),
        ("대규모 계약 체결", "글로벌 기업과의 대규모 파트너십이 발표되었습니다."),
        ("실적 서프라이즈", "예상을 훌쩍 뛰어넘는 분기 실적이 발표되었습니다."),
        ("정부 지원 확정", "대규모 정부 지원금 수혜 기업으로 선정되었습니다."),
        ("해외 시장 진출 성공", "새로운 해외 시장에서 폭발적인 성장을 기록하고 있습니다."),
        ("AI 기술 특허 획득", "핵심 AI 기술 특허를 획득하며 기술력을 인정받았습니다."),
    ],
    "negative": [
        ("대규모 리콜 발생", "주요 제품에서 결함이 발견되어 대규모 리콜이 진행 중입니다."),
        ("CEO 돌연 사임", "갑작스러운 CEO 사임 소식으로 시장이 충격에 빠졌습니다."),
        ("해킹 사고 발생", "대규모 개인정보 유출 사고가 발생하여 신뢰도가 급락했습니다."),
        ("공정위 조사 착수", "불공정 거래 혐의로 공정거래위원회 조사를 받게 되었습니다."),
        ("핵심 인재 대거 이탈", "주요 연구진이 경쟁사로 이직하며 기술 유출 우려가 커졌습니다."),
        ("분기 실적 쇼크", "예상보다 훨씬 낮은 실적이 발표되어 투자자들이 실망했습니다."),
    ]
}

# 최근 이벤트 버퍼 (SSE용)
recent_events = []

# -------------------------
# 초기 세팅
# -------------------------
with app.app_context():
    db.create_all()

    # DB 마이그레이션: avg_price 컬럼이 없으면 추가
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    holding_cols = [c['name'] for c in inspector.get_columns('holding')]
    if 'avg_price' not in holding_cols:
        with db.engine.connect() as conn:
            conn.execute(text('ALTER TABLE holding ADD COLUMN avg_price FLOAT DEFAULT 0'))
            conn.commit()
        print("[MIGRATION] avg_price 컬럼 추가 완료")

    # password 컬럼 마이그레이션
    user_cols = [c['name'] for c in inspector.get_columns('user')]
    if 'password' not in user_cols:
        with db.engine.connect() as conn:
            conn.execute(text("""ALTER TABLE "user" ADD COLUMN password VARCHAR(100) DEFAULT '' """))
            conn.commit()
        print("[MIGRATION] password 컬럼 추가 완료")

    # 종목 목록 - 새 종목은 여기에 추가하면 자동으로 DB에 반영됨
    STOCK_LIST = [
        dict(name="오성전자",           ticker="005930", price=1000, description="대한민국 대표 반도체·가전 기업"),
        dict(name="테슬라",             ticker="TSLA",   price=2000, description="전기차 및 에너지 혁신 기업"),
        dict(name="애플",               ticker="AAPL",   price=1500, description="아이폰·맥 등 프리미엄 IT 기기 기업"),
        dict(name="카카오",             ticker="035720", price=800,  description="국내 최대 모바일 플랫폼 기업"),
        dict(name="네이버",             ticker="035420", price=1200, description="검색·커머스·핀테크 종합 플랫폼"),
        dict(name="가천대",             ticker="GCU",    price=1200, description="주식도둑의 본거지"),
        dict(name="윤상현컴퍼니",       ticker="YSH",    price=3000, description="가천대주식도둑 소유 회사"),
        dict(name="연우신무역회사",       ticker="YSM",    price=3300, description="떡상 가능성조차 불분명한 의문의 기업"),
        dict(name="승리트릭컬주식회사", ticker="STK",    price=1000, description="수상할 정도로 대뾴니가 많은 기업"),
        dict(name="고한민성장촉진주식회사", ticker="KSJ",    price=5000, description="모두의 평균을 높이는 유망주 기업"),
        dict(name="이상어 아쿠아리움", ticker="LSA",    price=3500, description="개발자가 인정하는 아쿠아리움 ㅇㅇ"),
        dict(name="엔비디아", ticker="NVA",    price=500000, description="그래픽카드의 성지"), 
        dict(name="X", ticker="GHM",    price=1000000, description="화성갈끄니까~"),               
    ]

    existing_names = {s.name for s in db.session.execute(db.select(Stock)).scalars().all()}

    for s_data in STOCK_LIST:
        if s_data["name"] not in existing_names:
            new_stock = Stock(**s_data)
            db.session.add(new_stock)
            db.session.flush()  # id 확보
            h = PriceHistory(stock_id=new_stock.id, price=new_stock.price)
            db.session.add(h)
            print(f"[INIT] 새 종목 추가: {s_data['name']}")

    db.session.commit()

@app.route("/admin/reset")
def reset():
    # 1. 보유 주식 삭제
    db.session.query(Holding).delete()

    # 2. 이벤트 삭제
    db.session.query(Event).delete()

    # 3. 가격 히스토리 삭제
    db.session.query(PriceHistory).delete()

    # 4. 유저 돈 초기화
    for u in User.query.all():
        u.cash = 10000

    # 5. 주식 가격 초기화 (중요!)
    base_prices = {
        "삼성": 1000,
        "애플": 1500,
        "테슬라": 2000,
        "오성전자": 1200
    }

    for s in Stock.query.all():
        if s.name in base_prices:
            s.price = base_prices[s.name]

    db.session.commit()

    return "게임 상태 초기화 완료"

# -------------------------
# 프론트엔드 서빙
# -------------------------
@app.route("/")
def index():
    return render_template("index.html")

# -------------------------
# 유저 생성
# -------------------------
@app.route("/create_user", methods=["POST"])
def create_user():
    username = request.json.get("username", "").strip()
    password = request.json.get("password", "").strip()
    if not username:
        return jsonify({"error": "유저명을 입력해주세요"}), 400
    if len(username) > 20:
        return jsonify({"error": "유저명은 20자 이내로 입력해주세요"}), 400
    if not password:
        return jsonify({"error": "비밀번호를 입력해주세요"}), 400
    if len(password) > 50:
        return jsonify({"error": "비밀번호는 50자 이내로 입력해주세요"}), 400

    existing = db.session.execute(
        db.select(User).where(User.username == username)
    ).scalar_one_or_none()

    if existing:
        return jsonify({"error": "이미 존재하는 유저명입니다", "user_id": existing.id}), 409

    user = User(username=username, password=password)
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "유저 생성 완료", "user_id": user.id, "username": user.username})

# -------------------------
# 유저 로그인 (username으로 찾기)
# -------------------------
@app.route("/login", methods=["POST"])
def login():
    username = request.json.get("username", "").strip()
    password = request.json.get("password", "").strip()
    user = db.session.execute(
        db.select(User).where(User.username == username)
    ).scalar_one_or_none()

    if not user:
        return jsonify({"error": "존재하지 않는 유저입니다"}), 404

    if not user.password:
        # 비밀번호 없는 기존 유저 → 처음 입력한 비밀번호로 등록
        if not password:
            return jsonify({"error": "비밀번호를 입력하세요 (첫 로그인 시 비밀번호가 설정됩니다)"}), 400
        user.password = password
        db.session.commit()
    elif user.password != password:
        return jsonify({"error": "비밀번호가 틀렸습니다"}), 401

    return jsonify({"user_id": user.id, "username": user.username, "cash": user.cash})

# -------------------------
# 주식 목록
# -------------------------
@app.route("/stocks")
def get_stocks():
    stocks = db.session.execute(db.select(Stock)).scalars().all()
    result = []
    for s in stocks:
        # 직전 가격 (변동률 계산)
        histories = db.session.execute(
            db.select(PriceHistory)
            .where(PriceHistory.stock_id == s.id)
            .order_by(PriceHistory.timestamp.desc())
            .limit(2)
        ).scalars().all()

        prev_price = histories[1].price if len(histories) >= 2 else s.price
        change_pct = ((s.price - prev_price) / prev_price * 100) if prev_price else 0

        # 활성 이벤트
        active_events = db.session.execute(
            db.select(Event).where(Event.stock_id == s.id, Event.duration > 0)
        ).scalars().all()

        result.append({
            "id": s.id,
            "name": s.name,
            "ticker": s.ticker,
            "price": round(s.price, 2),
            "description": s.description,
            "change_pct": round(change_pct, 2),
            "has_event": len(active_events) > 0,
            "event_direction": "positive" if active_events and active_events[0].impact > 0 else ("negative" if active_events else None)
        })

    return jsonify(result)

# -------------------------
# 매수
# -------------------------
@app.route("/buy", methods=["POST"])
def buy():
    user_id = request.json.get("user_id")
    stock_id = request.json.get("stock_id")
    qty = request.json.get("quantity", 1)

    if qty <= 0:
        return jsonify({"error": "수량은 1 이상이어야 합니다"}), 400

    user = db.session.get(User, user_id)
    stock = db.session.get(Stock, stock_id)

    if not user:
        return jsonify({"error": "유저를 찾을 수 없습니다"}), 404
    if not stock:
        return jsonify({"error": "주식을 찾을 수 없습니다"}), 404

    cost = stock.price * qty

    if user.cash < cost:
        return jsonify({"error": f"잔액 부족 (필요: {cost:.0f}원, 보유: {user.cash:.0f}원)"}), 400

    user.cash -= cost

    holding = db.session.execute(
        db.select(Holding).where(Holding.user_id == user_id, Holding.stock_id == stock_id)
    ).scalar_one_or_none()

    if holding:
        # 평균매수가 재계산: (기존총액 + 새구매액) / 새총수량
        total_cost_prev = holding.avg_price * holding.quantity
        holding.avg_price = (total_cost_prev + cost) / (holding.quantity + qty)
        holding.quantity += qty
    else:
        holding = Holding(user_id=user_id, stock_id=stock_id, quantity=qty, avg_price=stock.price)
        db.session.add(holding)

    db.session.commit()
    return jsonify({
        "message": f"{stock.name} {qty}주 매수 완료",
        "cash": round(user.cash, 2),
        "total_cost": round(cost, 2)
    })

# -------------------------
# 매도
# -------------------------
@app.route("/sell", methods=["POST"])
def sell():
    user_id = request.json.get("user_id")
    stock_id = request.json.get("stock_id")
    qty = request.json.get("quantity", 1)

    if qty <= 0:
        return jsonify({"error": "수량은 1 이상이어야 합니다"}), 400

    user = db.session.get(User, user_id)
    stock = db.session.get(Stock, stock_id)

    if not user:
        return jsonify({"error": "유저를 찾을 수 없습니다"}), 404
    if not stock:
        return jsonify({"error": "주식을 찾을 수 없습니다"}), 404

    holding = db.session.execute(
        db.select(Holding).where(Holding.user_id == user_id, Holding.stock_id == stock_id)
    ).scalar_one_or_none()

    if not holding or holding.quantity < qty:
        current_qty = holding.quantity if holding else 0
        return jsonify({"error": f"보유 주식 부족 (보유: {current_qty}주)"}), 400

    revenue = stock.price * qty
    holding.quantity -= qty
    user.cash += revenue

    if holding.quantity == 0:
        db.session.delete(holding)

    db.session.commit()
    return jsonify({
        "message": f"{stock.name} {qty}주 매도 완료",
        "cash": round(user.cash, 2),
        "revenue": round(revenue, 2)
    })

# -------------------------
# 포트폴리오
# -------------------------
@app.route("/portfolio/<int:user_id>")
def portfolio(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "유저를 찾을 수 없습니다"}), 404

    holdings = db.session.execute(
        db.select(Holding).where(Holding.user_id == user_id)
    ).scalars().all()

    total = user.cash
    result = []

    for h in holdings:
        stock = db.session.get(Stock, h.stock_id)
        value = stock.price * h.quantity
        total += value
        avg_price = h.avg_price if h.avg_price else stock.price
        profit = (stock.price - avg_price) * h.quantity
        profit_pct = ((stock.price - avg_price) / avg_price * 100) if avg_price else 0
        result.append({
            "stock_id": stock.id,
            "stock": stock.name,
            "ticker": stock.ticker,
            "quantity": h.quantity,
            "price": round(stock.price, 2),
            "avg_price": round(avg_price, 2),
            "value": round(value, 2),
            "profit": round(profit, 2),
            "profit_pct": round(profit_pct, 2)
        })

    return jsonify({
        "username": user.username,
        "cash": round(user.cash, 2),
        "stocks": result,
        "total": round(total, 2)
    })

# -------------------------
# 가격 히스토리
# -------------------------
@app.route("/history/<int:stock_id>")
def history(stock_id):
    data = db.session.execute(
        db.select(PriceHistory)
        .where(PriceHistory.stock_id == stock_id)
        .order_by(PriceHistory.timestamp.desc())
        .limit(300)
    ).scalars().all()

    data = list(reversed(data))  # 최신 300개를 시간순으로

    return jsonify([
        {
            "price": round(d.price, 2),
            "time": d.timestamp.strftime("%H:%M:%S")
        }
        for d in data
    ])

# -------------------------
# 랭킹
# -------------------------
@app.route("/ranking")
def ranking():
    users = db.session.execute(db.select(User)).scalars().all()
    stocks_map = {s.id: s.price for s in db.session.execute(db.select(Stock)).scalars().all()}
    holdings_all = db.session.execute(db.select(Holding)).scalars().all()

    stock_values = {}
    for h in holdings_all:
        price = stocks_map.get(h.stock_id, 0)
        stock_values[h.user_id] = stock_values.get(h.user_id, 0) + price * h.quantity

    ranking_list = [{
        "username": u.username,
        "total": round(u.cash + stock_values.get(u.id, 0), 2),
        "cash": round(u.cash, 2)
    } for u in users]

    ranking_list.sort(key=lambda x: x["total"], reverse=True)
    return jsonify(ranking_list)

# -------------------------
# 실적 발표 조회
# -------------------------
@app.route("/earnings/<int:stock_id>")
def get_earnings(stock_id):
    rows = db.session.execute(
        db.select(Earnings)
        .where(Earnings.stock_id == stock_id)
        .order_by(Earnings.created_at.desc())
        .limit(4)
    ).scalars().all()

    return jsonify([{
        "quarter": e.quarter,
        "revenue": e.revenue,
        "operating": e.operating,
        "net": e.net,
        "rev_chg": e.rev_chg,
        "op_chg": e.op_chg,
        "net_chg": e.net_chg,
        "beat": e.beat,
        "time": e.created_at.strftime("%H:%M:%S")
    } for e in rows])

# -------------------------
# 최근 이벤트
# -------------------------
@app.route("/events/recent")
def get_recent_events():
    rows = db.session.execute(
        db.select(Event, Stock)
        .join(Stock, Stock.id == Event.stock_id)
        .order_by(Event.created_at.desc())
        .limit(20)
    ).all()

    return jsonify([{
        "stock_name": stock.name,
        "ticker": stock.ticker,
        "title": e.title,
        "description": e.description,
        "impact": e.impact,
        "type": "positive" if e.impact > 0 else "negative",
        "time": e.created_at.strftime("%H:%M:%S")
    } for e, stock in rows])

# -------------------------
# 관리자 - 이벤트 강제 발생
# -------------------------
@app.route("/admin/trigger_event", methods=["POST"])
def admin_trigger_event():
    data = request.json or {}
    stock_id = data.get("stock_id")        # 없으면 랜덤
    event_type = data.get("type", "random") # "positive" | "negative" | "random"
    impact_val = data.get("impact")         # 없으면 랜덤

    stocks = db.session.execute(db.select(Stock)).scalars().all()
    if stock_id:
        s = db.session.get(Stock, stock_id)
        if not s:
            return jsonify({"error": "종목 없음"}), 404
    else:
        s = random.choice(stocks)

    if event_type == "positive":
        is_positive = True
    elif event_type == "negative":
        is_positive = False
    else:
        is_positive = random.random() < 0.5

    event_pool = EVENTS["positive"] if is_positive else EVENTS["negative"]
    title, desc = random.choice(event_pool)

    if impact_val is not None:
        impact = float(impact_val)
    else:
        impact = random.choice([0.08,0.12,0.15,0.20]) if is_positive else random.choice([-0.08,-0.12,-0.15,-0.20])

    duration = data.get("duration", random.randint(3, 8))

    event = Event(stock_id=s.id, title=title, description=desc, impact=impact, duration=duration)
    db.session.add(event)
    db.session.commit()

    print(f"[ADMIN EVENT] {s.name}: {title} (impact: {impact:+.0%})")
    return jsonify({"message": f"{s.name}에 이벤트 발생!", "stock": s.name, "title": title, "impact": impact})

# -------------------------
# 송금 시스템
# -------------------------
@app.route("/transfer", methods=["POST"])
def transfer():
    from_id = request.json.get("from_id")
    to_username = request.json.get("to_username", "").strip()
    amount = float(request.json.get("amount", 0))

    if amount <= 0:
        return jsonify({"error": "송금액은 0보다 커야 합니다"}), 400

    sender = db.session.get(User, from_id)
    if not sender:
        return jsonify({"error": "유저를 찾을 수 없습니다"}), 404

    receiver = db.session.execute(
        db.select(User).where(User.username == to_username)
    ).scalar_one_or_none()
    if not receiver:
        return jsonify({"error": "받는 유저를 찾을 수 없습니다"}), 404
    if receiver.id == from_id:
        return jsonify({"error": "자기 자신에게는 송금할 수 없습니다"}), 400

    # 총 자산 계산
    holdings = db.session.execute(
        db.select(Holding).where(Holding.user_id == from_id)
    ).scalars().all()
    total_assets = sender.cash
    for h in holdings:
        stock = db.session.get(Stock, h.stock_id)
        total_assets += stock.price * h.quantity

    # 10% 제한
    max_amount = total_assets * 0.1
    if amount > max_amount:
        return jsonify({"error": f"한 번에 총 자산의 10% ({int(max_amount):,}원) 이하만 송금 가능합니다"}), 400

    # 5% 수수료
    total_cost = amount * 1.05
    if sender.cash < total_cost:
        return jsonify({"error": f"잔액 부족 (수수료 포함 {int(total_cost):,}원 필요)"}), 400

    # 쿨타임 체크 (최근 송금 기록)
    last_transfer = db.session.execute(
        db.select(Transfer)
        .where(Transfer.from_id == from_id)
        .order_by(Transfer.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if last_transfer:
        from datetime import timezone, timedelta
        now = datetime.utcnow()
        elapsed = (now - last_transfer.created_at).total_seconds()
        # 쿨타임: 기본 60초 + 금액 1000원당 10초 추가 (최대 10분)
        cooldown = min(60 + (last_transfer.amount / 1000) * 5, 600)
        if elapsed < cooldown:
            remain = int(cooldown - elapsed)
            return jsonify({"error": f"쿨타임 중입니다. {remain}초 후 다시 시도하세요"}), 429

    # 송금 실행
    sender.cash -= total_cost
    receiver.cash += amount

    log = Transfer(from_id=from_id, to_id=receiver.id, amount=amount, fee=amount * 0.05)
    db.session.add(log)
    db.session.commit()

    return jsonify({
        "message": f"{receiver.username}에게 {int(amount):,}원 송금 완료",
        "sent": round(total_cost, 2),
        "received": round(amount, 2),
        "fee": round(amount * 0.05, 2),
        "cash": round(sender.cash, 2)
    })

# -------------------------
# 게임 틱 함수들
# -------------------------
_tick_counter = 0

def update_stock_prices():
    global _tick_counter
    _tick_counter += 1

    stocks = db.session.execute(db.select(Stock)).scalars().all()

    # 이벤트 한 번에 전체 조회
    all_events = db.session.execute(
        db.select(Event).where(Event.duration > 0)
    ).scalars().all()
    events_by_stock = {}
    for e in all_events:
        events_by_stock.setdefault(e.stock_id, []).append(e)

    new_histories = []
    for s in stocks:
        change = random.uniform(-0.03, 0.03)

        for e in events_by_stock.get(s.id, []):
            change += e.impact * 0.5
            e.duration -= 1
            if e.duration <= 0:
                db.session.delete(e)

        s.price = max(10, s.price * (1 + change))
        new_histories.append(PriceHistory(stock_id=s.id, price=s.price))

    db.session.bulk_save_objects(new_histories)

    # 60틱마다 오래된 PriceHistory 정리 (종목당 최근 360개만 유지)
    if _tick_counter % 60 == 0:
        from sqlalchemy import text
        for s in stocks:
            subq = (
                db.select(PriceHistory.id)
                .where(PriceHistory.stock_id == s.id)
                .order_by(PriceHistory.timestamp.desc())
                .limit(360)
                .subquery()
            )
            db.session.execute(
                db.delete(PriceHistory)
                .where(PriceHistory.stock_id == s.id)
                .where(PriceHistory.id.notin_(db.select(subq.c.id)))
            )

    db.session.commit()


# -------------------------
# 실적 발표 로직
# -------------------------
# 종목별 기준 실적 (매출/영업이익/순이익 단위: 억원)
STOCK_FINANCIALS = {
    "오성전자": {"revenue": 3000, "operating": 450, "net": 320},
    "테슬라":   {"revenue": 1800, "operating": 210, "net": 150},
    "애플":     {"revenue": 2500, "operating": 600, "net": 480},
    "카카오":   {"revenue": 900,  "operating": 120, "net": 85},
    "네이버":   {"revenue": 1100, "operating": 200, "net": 160},
    "가천대":   {"revenue": 500,  "operating": 60,  "net": 40},
}

def generate_earnings(stock, is_positive):
    base = STOCK_FINANCIALS.get(stock.name, {"revenue": 1000, "operating": 150, "net": 100})
    if is_positive:
        multiplier = random.uniform(1.05, 1.30)
        beat = "▲ 예상치 상회"
    else:
        multiplier = random.uniform(0.65, 0.92)
        beat = "▼ 예상치 하회"

    revenue = round(base["revenue"] * multiplier * random.uniform(0.95, 1.05))
    operating = round(base["operating"] * multiplier * random.uniform(0.90, 1.10))
    net = round(base["net"] * multiplier * random.uniform(0.85, 1.15))

    # 전분기 대비 증감률 - DB에서 직전 실적 조회
    prev = db.session.execute(
        db.select(Earnings)
        .where(Earnings.stock_id == stock.id)
        .order_by(Earnings.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    rev_chg = round((revenue / prev.revenue - 1) * 100, 1) if prev else 0
    op_chg  = round((operating / prev.operating - 1) * 100, 1) if prev else 0
    net_chg = round((net / prev.net - 1) * 100, 1) if prev else 0

    quarter = ["1Q", "2Q", "3Q", "4Q"][random.randint(0,3)]

    # DB에 저장
    earnings = Earnings(
        stock_id=stock.id,
        quarter=f"2025 {quarter}",
        revenue=revenue,
        operating=operating,
        net=net,
        rev_chg=rev_chg,
        op_chg=op_chg,
        net_chg=net_chg,
        beat=beat,
    )
    db.session.add(earnings)
    db.session.commit()

    return earnings


def trigger_event():
    global recent_events
    stocks = db.session.execute(db.select(Stock)).scalars().all()
    s = random.choice(stocks)

    # 20% 확률로 이벤트 발생
    if random.random() < 0.2:
        is_positive = random.random() < 0.5
        event_pool = EVENTS["positive"] if is_positive else EVENTS["negative"]
        title, desc = random.choice(event_pool)

        if is_positive:
            impact = random.choice([0.08, 0.12, 0.15, 0.20])
        else:
            impact = random.choice([-0.08, -0.12, -0.15, -0.20])

        duration = random.randint(3, 8)

        event = Event(
            stock_id=s.id,
            title=title,
            description=desc,
            impact=impact,
            duration=duration
        )
        db.session.add(event)
        db.session.commit()

        event_data = {
            "stock_name": s.name,
            "ticker": s.ticker,
            "title": title,
            "description": desc,
            "impact": impact,
            "type": "positive" if is_positive else "negative",
            "time": datetime.utcnow().strftime("%H:%M:%S")
        }
        recent_events.append(event_data)
        if len(recent_events) > 50:
            recent_events = recent_events[-50:]

        print(f"[EVENT] {s.name}: {title} (impact: {impact:+.0%})")

        # 30% 확률로 실적 발표도 함께 생성
        if random.random() < 0.3:
            earnings = generate_earnings(s, is_positive)
            print(f"[EARNINGS] {s.name} {earnings.quarter}: 매출 {earnings.revenue}억, 영업이익 {earnings.operating}억")


def game_tick():
    with app.app_context():
        update_stock_prices()
        trigger_event()


# 스케줄러 시작 (10초마다 틱, 중복실행 방지)
scheduler.add_job(
    func=game_tick,
    trigger="interval",
    seconds=10,
    max_instances=1,
    misfire_grace_time=5
)
scheduler.start()

# 커밋용
# -------------------------
# 실행
# -------------------------
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)