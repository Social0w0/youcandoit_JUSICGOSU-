from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from models import db, User, Stock, Holding, Event, PriceHistory
import random
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

#커밋확인용
app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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

    if Stock.query.count() == 0:
        stocks = [
            Stock(name="오성전자", ticker="005930", price=1000, description="대한민국 대표 반도체·가전 기업"),
            Stock(name="테슬라", ticker="TSLA", price=2000, description="전기차 및 에너지 혁신 기업"),
            Stock(name="애플", ticker="AAPL", price=1500, description="아이폰·맥 등 프리미엄 IT 기기 기업"),
            Stock(name="카카오", ticker="035720", price=800, description="국내 최대 모바일 플랫폼 기업"),
            Stock(name="네이버", ticker="035420", price=1200, description="검색·커머스·핀테크 종합 플랫폼"),
            Stock(name="가천대", ticker="035420", price=1200, description="주식도둑의 본거지"),
        ]
        db.session.add_all(stocks)
        db.session.commit()

        # 초기 가격 히스토리 저장
        for s in stocks:
            h = PriceHistory(stock_id=s.id, price=s.price)
            db.session.add(h)
        db.session.commit()

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
    if not username:
        return jsonify({"error": "유저명을 입력해주세요"}), 400
    if len(username) > 20:
        return jsonify({"error": "유저명은 20자 이내로 입력해주세요"}), 400

    existing = db.session.execute(
        db.select(User).where(User.username == username)
    ).scalar_one_or_none()

    if existing:
        return jsonify({"error": "이미 존재하는 유저명입니다", "user_id": existing.id}), 409

    user = User(username=username)
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "유저 생성 완료", "user_id": user.id, "username": user.username})

# -------------------------
# 유저 로그인 (username으로 찾기)
# -------------------------
@app.route("/login", methods=["POST"])
def login():
    username = request.json.get("username", "").strip()
    user = db.session.execute(
        db.select(User).where(User.username == username)
    ).scalar_one_or_none()

    if not user:
        return jsonify({"error": "존재하지 않는 유저입니다"}), 404

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
        .order_by(PriceHistory.timestamp.asc())
        .limit(60)
    ).scalars().all()

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
    ranking_list = []

    for u in users:
        holdings = db.session.execute(
            db.select(Holding).where(Holding.user_id == u.id)
        ).scalars().all()
        total = u.cash

        for h in holdings:
            stock = db.session.get(Stock, h.stock_id)
            total += stock.price * h.quantity

        ranking_list.append({
            "username": u.username,
            "total": round(total, 2),
            "cash": round(u.cash, 2)
        })

    ranking_list.sort(key=lambda x: x["total"], reverse=True)
    return jsonify(ranking_list)

# -------------------------
# 최근 이벤트
# -------------------------
@app.route("/events/recent")
def get_recent_events():
    global recent_events
    events = recent_events[-10:]
    return jsonify(events)

# -------------------------
# 게임 틱 함수들
# -------------------------
def update_stock_prices():
    stocks = db.session.execute(db.select(Stock)).scalars().all()

    for s in stocks:
        # 기본 랜덤 변동 (-3% ~ +3%)
        change = random.uniform(-0.03, 0.03)

        # 이벤트 효과 적용
        events = db.session.execute(
            db.select(Event).where(Event.stock_id == s.id, Event.duration > 0)
        ).scalars().all()

        for e in events:
            change += e.impact * 0.5  # 이벤트 영향 누적
            e.duration -= 1
            if e.duration <= 0:
                db.session.delete(e)

        s.price = max(10, s.price * (1 + change))  # 최소가격 10원

        # 히스토리 저장
        history = PriceHistory(stock_id=s.id, price=s.price)
        db.session.add(history)

    db.session.commit()


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


def game_tick():
    with app.app_context():
        update_stock_prices()
        trigger_event()


# 스케줄러 시작 (5초마다 틱)
scheduler.add_job(func=game_tick, trigger="interval", seconds=5)
scheduler.start()

# -------------------------
# 실행
# -------------------------
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
