from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

from models import db, User, Stock, Holding, Event, PriceHistory, Earnings, Transfer, \
                   Title, UserProfile, seed_titles, check_and_unlock_titles, \
                   ShopTitle, ShopPurchase, seed_shop_titles, \
                   ShopBackground, ShopBgPurchase, seed_shop_backgrounds
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

# 서킷 브레이커 상태: {stock_id: unlock_time}
circuit_breakers = {}

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
    seed_titles()
    seed_shop_titles()
    seed_shop_backgrounds()

    # DB 마이그레이션: avg_price 컬럼이 없으면 추가
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    holding_cols = [c['name'] for c in inspector.get_columns('holding')]
    if 'avg_price' not in holding_cols:
        with db.engine.connect() as conn:
            conn.execute(text('ALTER TABLE holding ADD COLUMN avg_price FLOAT DEFAULT 0'))
            conn.commit()
        print("[MIGRATION] avg_price 컬럼 추가 완료")

    # peak_asset 컬럼 마이그레이션
    try:
        profile_cols = [c['name'] for c in inspector.get_columns('user_profile')]
        if 'peak_asset' not in profile_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE user_profile ADD COLUMN peak_asset FLOAT DEFAULT 0'))
                conn.commit()
            print("[MIGRATION] peak_asset 컬럼 추가 완료")
        if 'equipped_shop_title_id' not in profile_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE user_profile ADD COLUMN equipped_shop_title_id INTEGER DEFAULT NULL'))
                conn.commit()
            print("[MIGRATION] equipped_shop_title_id 컬럼 추가 완료")
        # custom_bg 슬롯 컬럼 마이그레이션
        for col in ['custom_bg_1', 'custom_bg_2', 'custom_bg_3']:
            if col not in profile_cols:
                with db.engine.connect() as conn:
                    conn.execute(text(f'ALTER TABLE user_profile ADD COLUMN {col} VARCHAR(500)'))
                    conn.commit()
                print(f"[MIGRATION] {col} 컬럼 추가 완료")
        if 'custom_bg_slot_count' not in profile_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE user_profile ADD COLUMN custom_bg_slot_count INTEGER DEFAULT 0'))
                conn.commit()
            print("[MIGRATION] custom_bg_slot_count 컬럼 추가 완료")
    except Exception as e:
        print(f"[MIGRATION] user_profile 테이블 없음, 건너뜀: {e}")

    # password 컬럼 마이그레이션
    user_cols = [c['name'] for c in inspector.get_columns('user')]
    if 'password' not in user_cols:
        with db.engine.connect() as conn:
            conn.execute(text("""ALTER TABLE "user" ADD COLUMN password VARCHAR(100) DEFAULT '' """))
            conn.commit()
        print("[MIGRATION] password 컬럼 추가 완료")

    # username 컬럼 길이 마이그레이션 (VARCHAR(20) → VARCHAR(50))
    try:
        with db.engine.connect() as conn:
            conn.execute(text('ALTER TABLE "user" ALTER COLUMN username TYPE VARCHAR(50)'))
            conn.commit()
        print("[MIGRATION] username VARCHAR(50) 변경 완료")
    except Exception as e:
        print(f"[MIGRATION] username 컬럼 변경 건너뜀: {e}")

    # color 컬럼 길이 마이그레이션
    try:
        with db.engine.connect() as conn:
            conn.execute(text('ALTER TABLE shop_title ALTER COLUMN color TYPE VARCHAR(100)'))
            conn.execute(text('ALTER TABLE title ALTER COLUMN color TYPE VARCHAR(100)'))
            conn.commit()
        print("[MIGRATION] color 컬럼 VARCHAR(100) 변경 완료")
    except Exception as e:
        print(f"[MIGRATION] color 컬럼 변경 건너뜀: {e}")

    # 종목 목록 - 새 종목은 여기에 추가하면 자동으로 DB에 반영됨
    STOCK_LIST = [
        dict(name="오성전자",           ticker="005930", price=1000, description="대한민국 대표 반도체·가전 기업"),
        dict(name="테슬라",             ticker="TSLA",   price=2000, description="전기차 및 에너지 혁신 기업"),
        dict(name="애플",               ticker="AAPL",   price=1500, description="아이폰·맥 등 프리미엄 IT 기기 기업"),
        dict(name="카카오",             ticker="035720", price=800,  description="국내 최대 모바일 플랫폼 기업"),
        dict(name="네이버",             ticker="035420", price=1200, description="검색·커머스·핀테크 종합 플랫폼"),
        dict(name="가천대",             ticker="GCU",    price=1200, description="주식도둑의 본거지"),
        dict(name="윤상현레버리지연구소",       ticker="YSH",    price=3000, description="마침내! 사업의 방향성을 굳힌 기업입니다."),
        dict(name="개잡주전문주식회사",       ticker="GJJ",    price=30000, description="다양한 주식을 취급하는 윤상현연구소 소속 회사"),
        dict(name="김경주모아이석상발굴사업",       ticker="GMI",    price=25000, description="대체 어째서 모아이 석상을 발굴하는거죠??"),
        dict(name="연우신무역회사",       ticker="YSM",    price=3300, description="떡상 가능성조차 불분명한 의문의 기업"),
        dict(name="승리트릭컬주식회사", ticker="STK",    price=1000, description="수상할 정도로 대뾴니가 많은 기업"),
        dict(name="고한민성장촉진주식회사", ticker="KSJ",    price=5000, description="모두의 평균을 높이는 유망주 기업"),
        dict(name="이상어 아쿠아리움", ticker="LSA",    price=3500, description="개발자가 인정하는 아쿠아리움 ㅇㅇ"),
        dict(name="엔비디아", ticker="NVA",    price=500000, description="그래픽카드의 성지"), 
        dict(name="X", ticker="GHM",    price=1000000, description="화성갈끄니까~"),               
    ]

    existing = {s.ticker: s for s in db.session.execute(db.select(Stock)).scalars().all()}

    for s_data in STOCK_LIST:
        if s_data["ticker"] in existing:
            # 기존 종목 - 이름/설명 갱신
            existing[s_data["ticker"]].name = s_data["name"]
            existing[s_data["ticker"]].description = s_data["description"]
        else:
        # 새 종목 추가
            new_stock = Stock(**s_data)
            db.session.add(new_stock)
            db.session.flush()
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


@app.route("/admin/delete_user", methods=["POST"])
def delete_user():
    username = request.json.get("username", "").strip()
    if not username:
        return jsonify({"error": "username 필요"}), 400

    user = db.session.execute(
        db.select(User).where(User.username == username)
    ).scalar_one_or_none()

    if not user:
        return jsonify({"error": f"{username} 유저 없음"}), 404

    # 연관 데이터 전부 삭제
    db.session.execute(db.delete(Holding).where(Holding.user_id == user.id))
    db.session.execute(db.delete(Transfer).where(
        (Transfer.from_id == user.id) | (Transfer.to_id == user.id)
    ))
    db.session.delete(user)
    db.session.commit()

    return jsonify({"message": f"{username} 삭제 완료"})

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

    # 서킷 브레이커 체크
    remaining = check_circuit_breaker(stock_id)
    if remaining:
        stock = db.session.get(Stock, stock_id)
        stock_name = stock.name if stock else "해당 종목"
        return jsonify({
            "error": f"🚫 {stock_name} 거래 정지 중 (급격한 가격 변동)",
            "halt_remaining": remaining
        }), 423  # 423 Locked

    user = db.session.get(User, user_id)
    stock = db.session.get(Stock, stock_id)

    if not user:
        return jsonify({"error": "유저를 찾을 수 없습니다"}), 404
    if not stock:
        return jsonify({"error": "주식을 찾을 수 없습니다"}), 404

    cost = stock.price * qty

    # ── 총 자산 계산 (매수 전 기준) ──
    holdings_before = db.session.execute(
        db.select(Holding).where(Holding.user_id == user_id)
    ).scalars().all()
    total_asset_before = user.cash + sum(
        db.session.get(Stock, h.stock_id).price * h.quantity
        for h in holdings_before
    )

    # ── 계단식 매수 한도 제한 ──
    GYEONG = 1_000_000_000_000_0000  # 1경 = 10^16
    JO    = 1_000_000_000_000        # 1조 = 10^12

    if total_asset_before >= GYEONG:
        # 1경 이상: 총재산의 30%가 최대 매수 금액
        max_cost = total_asset_before * 0.30
        if cost > max_cost:
            return jsonify({
                "error": f"💰 자산 규모 제한: 1경 이상 보유자는 1회 매수 금액이 총재산의 30% 이하여야 합니다 "
                         f"(최대 {max_cost:,.0f}원, 요청 {cost:,.0f}원)"
            }), 400
    elif total_asset_before >= JO:
        # 1조 이상 ~ 1경 미만: 총재산의 50%가 최대 매수 금액
        max_cost = total_asset_before * 0.50
        if cost > max_cost:
            return jsonify({
                "error": f"💰 자산 규모 제한: 1조 이상 보유자는 1회 매수 금액이 총재산의 50% 이하여야 합니다 "
                         f"(최대 {max_cost:,.0f}원, 요청 {cost:,.0f}원)"
            }), 400

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

    # ── 칭호 자동 지급 체크 ──
    holdings_all = db.session.execute(
        db.select(Holding).where(Holding.user_id == user_id)
    ).scalars().all()
    total_asset = user.cash + sum(
        db.session.get(Stock, h.stock_id).price * h.quantity
        for h in holdings_all
    )

    # peak_asset 갱신
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if profile and total_asset > (profile.peak_asset or 0):
        profile.peak_asset = total_asset
        db.session.commit()


    newly = check_and_unlock_titles(user_id, total_asset)

    return jsonify({
        "message": f"{stock.name} {qty}주 매수 완료",
        "cash": round(user.cash, 2),
        "total_cost": round(cost, 2),
        "new_titles": [{"name": t.name, "emoji": t.emoji, "color": t.color} for t in newly]
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

    # 서킷 브레이커 체크
    remaining = check_circuit_breaker(stock_id)
    if remaining:
        stock = db.session.get(Stock, stock_id)
        stock_name = stock.name if stock else "해당 종목"
        return jsonify({
            "error": f"🚫 {stock_name} 거래 정지 중 (급격한 가격 변동)",
            "halt_remaining": remaining
        }), 423


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

    # ── 칭호 자동 지급 체크 ──
    holdings_all = db.session.execute(
        db.select(Holding).where(Holding.user_id == user_id)
    ).scalars().all()
    total_asset = user.cash + sum(
        db.session.get(Stock, h.stock_id).price * h.quantity
        for h in holdings_all
    )
    # peak_asset 갱신
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if profile and total_asset > (profile.peak_asset or 0):
        profile.peak_asset = total_asset
        db.session.commit()

    newly = check_and_unlock_titles(user_id, total_asset)

    return jsonify({
        "message": f"{stock.name} {qty}주 매도 완료",
        "cash": round(user.cash, 2),
        "revenue": round(revenue, 2),
        "new_titles": [{"name": t.name, "emoji": t.emoji, "color": t.color} for t in newly]
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

    def get_equipped_title(user_id):
        profile = UserProfile.query.filter_by(user_id=user_id).first()
        if not profile:
            return None
        # 상점 칭호 우선, 없으면 업적 칭호
        shop_title_id = getattr(profile, 'equipped_shop_title_id', None)
        if shop_title_id:
            t = db.session.get(ShopTitle, shop_title_id)
            return {"name": t.name, "emoji": t.emoji, "color": t.color} if t else None
        if profile.equipped_title_id:
            t = db.session.get(Title, profile.equipped_title_id)
            return {"name": t.name, "emoji": t.emoji, "color": t.color} if t else None
        return None

    ranking_list = [{
        "username": u.username,
        "total": round(u.cash + stock_values.get(u.id, 0), 2),
        "cash": round(u.cash, 2),
        "title": get_equipped_title(u.id),
        "bg": (UserProfile.query.filter_by(user_id=u.id).first() or UserProfile()).equipped_bg or "default"
    } for u in users]

    ranking_list.sort(key=lambda x: x["total"], reverse=True)
    return jsonify(ranking_list)


# -------------------------
# 프로필 조회
# -------------------------
@app.route("/profile/<int:user_id>")
def get_profile(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "유저 없음"}), 404

    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        # 프로필 없으면 새싹 기본 지급하며 생성
        profile = UserProfile(user_id=user_id, unlocked_title_ids='1')
        db.session.add(profile)
        db.session.commit()

    unlocked_ids = set(
        int(x) for x in profile.unlocked_title_ids.split(',') if x.strip()
    )
    all_titles = Title.query.order_by(Title.sort_order).all()

    # 현재 총 자산 계산
    holdings = db.session.execute(
        db.select(Holding).where(Holding.user_id == user_id)
    ).scalars().all()
    total_asset = user.cash
    for h in holdings:
        stock = db.session.get(Stock, h.stock_id)
        if stock:
            total_asset += stock.price * h.quantity

    # 상점 칭호 구매 목록
    purchased_rows = db.session.execute(
        db.select(ShopPurchase.shop_title_id).where(ShopPurchase.user_id == user_id)
    ).scalars().all()
    purchased_shop_ids = set(purchased_rows)
    all_shop_titles = ShopTitle.query.order_by(ShopTitle.sort_order).all()

    return jsonify({
        "username": user.username,
        "equipped_title_id": profile.equipped_title_id,
        "equipped_shop_title_id": getattr(profile, 'equipped_shop_title_id', None),
        "equipped_bg": profile.equipped_bg or "default",
        "total_asset": round(total_asset, 2),
        "peak_asset": round(profile.peak_asset or 0, 2),
        "custom_bg_slot_count": profile.custom_bg_slot_count or 0,
        "custom_bg_1": profile.custom_bg_1,
        "custom_bg_2": profile.custom_bg_2,
        "custom_bg_3": profile.custom_bg_3,
        "titles": [{
            "id": t.id,
            "name": t.name,
            "emoji": t.emoji,
            "description": t.description,
            "color": t.color,
            "condition_value": t.condition_value,
            "unlocked": t.id in unlocked_ids
        } for t in all_titles],
        "shop_titles": [{
            "id": t.id,
            "name": t.name,
            "emoji": t.emoji,
            "description": t.description,
            "price": t.price,
            "color": t.color,
            "purchased": t.id in purchased_shop_ids,
        } for t in all_shop_titles],
    })

# -------------------------
# 유저명으로 프로필 조회 (랭킹 클릭용)
# -------------------------
@app.route("/profile/by_username/<string:uname>")
def get_profile_by_username(uname):
    user = db.session.execute(
        db.select(User).where(User.username == uname)
    ).scalar_one_or_none()
    if not user:
        return jsonify({"error": "유저 없음"}), 404
    return get_profile(user.id)

# -------------------------
# 칭호/배경 장착
# -------------------------
@app.route("/profile/<int:user_id>/equip", methods=["POST"])
def equip_profile(user_id):
    data = request.json or {}
    title_id = data.get("title_id")   # None이면 칭호 해제
    bg = data.get("bg")               # None이면 배경 변경 안 함

    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id, unlocked_title_ids='1')
        db.session.add(profile)
        db.session.flush()

    # 칭호 장착 변경
    if "title_id" in data:
        if title_id is None:
            profile.equipped_title_id = None
        else:
            unlocked_ids = set(
                int(x) for x in profile.unlocked_title_ids.split(',') if x.strip()
            )
            if title_id not in unlocked_ids:
                return jsonify({"error": "보유하지 않은 칭호입니다"}), 403
            profile.equipped_title_id = title_id

    # 배경 변경
    if bg is not None:
        FREE_BGS = {"default", "purple", "gold", "green", "red"}
        SHOP_BGS = {"black","violet","forest","yellow","crimson","blue","sky","pink",
                    "white","orange","lime","lavender","rose","lightblue","silver"}
        CUSTOM_BGS = {"custom_bg_1", "custom_bg_2", "custom_bg_3"}
        ALL_BGS = FREE_BGS | SHOP_BGS | CUSTOM_BGS

        if bg not in ALL_BGS:
            return jsonify({"error": "유효하지 않은 배경입니다"}), 400

        # 상점 배경은 구매 여부 확인
        if bg in SHOP_BGS:
            purchased = db.session.execute(
                db.select(ShopBgPurchase).where(
                    ShopBgPurchase.user_id == user_id,
                    ShopBgPurchase.bg_key == bg
                )
            ).scalar_one_or_none()
            if not purchased:
                return jsonify({"error": "구매하지 않은 배경입니다"}), 403

        # 커스텀 배경은 슬롯 구매 여부 + URL 존재 여부 확인
        if bg in CUSTOM_BGS:
            slot_num = int(bg.split("_")[2])
            if (profile.custom_bg_slot_count or 0) < slot_num:
                return jsonify({"error": f"커스텀 배경 슬롯 {slot_num}을 구매하지 않았습니다"}), 403
            url = getattr(profile, f"custom_bg_{slot_num}", None)
            if not url:
                return jsonify({"error": "해당 슬롯에 이미지가 등록되지 않았습니다. 먼저 이미지를 업로드해주세요."}), 400

        profile.equipped_bg = bg

    db.session.commit()
    return jsonify({"message": "프로필 업데이트 완료",
                    "equipped_title_id": profile.equipped_title_id,
                    "equipped_bg": profile.equipped_bg})

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
    # since: 클라이언트가 마지막으로 받은 이벤트의 ISO timestamp (없으면 최근 20개 반환)
    since_str = request.args.get("since")

    query = (
        db.select(Event, Stock)
        .join(Stock, Stock.id == Event.stock_id)
        .order_by(Event.created_at.desc())
    )

    if since_str:
        try:
            since_dt = datetime.fromisoformat(since_str)
            # since 이후에 생성된 이벤트만 반환 (최대 10개)
            query = query.where(Event.created_at > since_dt).limit(10)
        except ValueError:
            query = query.limit(20)
    else:
        # 첫 접속: 최근 3개만 반환 (과거 이벤트 폭탄 방지)
        query = query.limit(3)

    rows = db.session.execute(query).all()
    rows = list(reversed(rows))  # 시간 오름차순으로 정렬

    return jsonify([{
        "stock_name": stock.name,
        "ticker": stock.ticker,
        "title": e.title,
        "description": e.description,
        "impact": e.impact,
        "type": "positive" if e.impact > 0 else "negative",
        "time": e.created_at.strftime("%H:%M:%S"),
        "created_at": e.created_at.isoformat()  # 클라이언트가 since로 사용할 값
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
# 관리자 - 유저 생성
# -------------------------
@app.route("/admin/create_test_user", methods=["POST"])
def create_test_user():
    data = request.json
    username = data.get("username", "testplayer")
    password = data.get("password", "1234")
    cash = data.get("cash", 9999999)

    existing = User.query.filter_by(username=username).first()
    if existing:
        existing.cash = cash
        db.session.commit()
        return jsonify({"message": f"{username} cash 수정 완료", "cash": cash})

    user = User(username=username, password=password, cash=cash)
    db.session.add(user)
    db.session.flush()
    db.session.add(UserProfile(user_id=user.id))
    db.session.commit()
    return jsonify({"message": f"{username} 생성 완료", "id": user.id, "cash": cash})

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

    profile = UserProfile.query.filter_by(user_id=from_id).first()  # user_id → from_id
    if profile and total_assets > (profile.peak_asset or 0):
        profile.peak_asset = total_assets
        db.session.commit()

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

    receiver_holdings = db.session.execute(
        db.select(Holding).where(Holding.user_id == receiver.id)
    ).scalars().all()
    receiver_total = receiver.cash + sum(
        db.session.get(Stock, h.stock_id).price * h.quantity
        for h in receiver_holdings
    )
    receiver_profile = UserProfile.query.filter_by(user_id=receiver.id).first()
    if receiver_profile and receiver_total > (receiver_profile.peak_asset or 0):
        receiver_profile.peak_asset = receiver_total

    db.session.commit()

    return jsonify({
        "message": f"{receiver.username}에게 {int(amount):,}원 송금 완료",
        "sent": round(total_cost, 2),
        "received": round(amount, 2),
        "fee": round(amount * 0.05, 2),
        "cash": round(sender.cash, 2)
    })

# -------------------------
# 상점 시스템
# -------------------------
@app.route("/shop/titles")
def get_shop_titles():
    """상점 칭호 목록 + 유저의 구매 여부 반환"""
    user_id = request.args.get("user_id", type=int)

    purchased_ids = set()
    if user_id:
        rows = db.session.execute(
            db.select(ShopPurchase.shop_title_id).where(ShopPurchase.user_id == user_id)
        ).scalars().all()
        purchased_ids = set(rows)

    titles = db.session.execute(
        db.select(ShopTitle).order_by(ShopTitle.sort_order)
    ).scalars().all()

    return jsonify([{
        "id": t.id,
        "name": t.name,
        "emoji": t.emoji,
        "description": t.description,
        "price": t.price,
        "color": t.color,
        "purchased": t.id in purchased_ids,
    } for t in titles])


@app.route("/shop/buy", methods=["POST"])
def shop_buy():
    """상점 칭호 구매"""
    data = request.json or {}
    user_id = data.get("user_id")
    shop_title_id = data.get("shop_title_id")

    if not user_id or not shop_title_id:
        return jsonify({"error": "잘못된 요청입니다"}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "유저를 찾을 수 없습니다"}), 404

    shop_title = db.session.get(ShopTitle, shop_title_id)
    if not shop_title:
        return jsonify({"error": "칭호를 찾을 수 없습니다"}), 404

    # 이미 구매했는지 확인
    already = db.session.execute(
        db.select(ShopPurchase).where(
            ShopPurchase.user_id == user_id,
            ShopPurchase.shop_title_id == shop_title_id
        )
    ).scalar_one_or_none()
    if already:
        return jsonify({"error": "이미 보유한 칭호입니다"}), 400

    if user.cash < shop_title.price:
        return jsonify({"error": f"현금이 부족합니다 (필요: {int(shop_title.price):,}원)"}), 400

    # 구매 처리
    user.cash -= shop_title.price
    purchase = ShopPurchase(user_id=user_id, shop_title_id=shop_title_id)
    db.session.add(purchase)

    # UserProfile의 unlocked_title_ids에 상점칭호를 별도 관리하지 않고
    # 상점칭호는 ShopPurchase에서만 조회. equipped는 profile의 equipped_shop_title_id 사용.
    # → equipped_shop_title_id 컬럼은 마이그레이션으로 추가
    db.session.commit()

    return jsonify({
        "message": f"'{shop_title.emoji} {shop_title.name}' 칭호 구매 완료!",
        "cash": round(user.cash, 2),
        "shop_title": {
            "id": shop_title.id,
            "name": shop_title.name,
            "emoji": shop_title.emoji,
            "color": shop_title.color,
        }
    })


@app.route("/shop/equip", methods=["POST"])
def shop_equip():
    """상점 칭호 장착/해제. 상점 칭호와 업적 칭호는 별도 슬롯."""
    data = request.json or {}
    user_id = data.get("user_id")
    shop_title_id = data.get("shop_title_id")   # None이면 해제

    if not user_id:
        return jsonify({"error": "잘못된 요청입니다"}), 400

    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        return jsonify({"error": "프로필을 찾을 수 없습니다"}), 404

    if shop_title_id:
        # 보유 여부 확인
        purchase = db.session.execute(
            db.select(ShopPurchase).where(
                ShopPurchase.user_id == user_id,
                ShopPurchase.shop_title_id == shop_title_id
            )
        ).scalar_one_or_none()
        if not purchase:
            return jsonify({"error": "구매하지 않은 칭호입니다"}), 400

    profile.equipped_shop_title_id = shop_title_id
    db.session.commit()

    return jsonify({
        "message": "상점 칭호 장착 완료" if shop_title_id else "상점 칭호 해제 완료",
        "equipped_shop_title_id": profile.equipped_shop_title_id,
    })


# ── 상점 배경 목록 조회 ──
@app.route("/shop/backgrounds")
def get_shop_backgrounds():
    user_id = request.args.get("user_id", type=int)

    purchased_keys = set()
    custom_slot_count = 0
    custom_urls = {}

    if user_id:
        rows = db.session.execute(
            db.select(ShopBgPurchase.bg_key).where(ShopBgPurchase.user_id == user_id)
        ).scalars().all()
        purchased_keys = set(rows)

        profile = UserProfile.query.filter_by(user_id=user_id).first()
        if profile:
            custom_slot_count = profile.custom_bg_slot_count or 0
            for i in range(1, 4):
                url = getattr(profile, f"custom_bg_{i}", None)
                if url:
                    custom_urls[f"custom_{i}"] = url

    bgs = db.session.execute(
        db.select(ShopBackground).order_by(ShopBackground.sort_order)
    ).scalars().all()

    CUSTOM_PRICES = [10_000_000_000, 100_000_000_000, 1_000_000_000_000]

    return jsonify({
        "color_bgs": [{
            "key": b.key,
            "label": b.label,
            "price": b.price,
            "purchased": b.key in purchased_keys,
        } for b in bgs],
        "custom_slots": [{
            "slot": i + 1,
            "price": CUSTOM_PRICES[i],
            "purchased": custom_slot_count >= i + 1,
            "image_url": custom_urls.get(f"custom_{i+1}"),
        } for i in range(3)],
    })


# ── 상점 배경 색상 구매 ──
@app.route("/shop/buy_bg", methods=["POST"])
def buy_shop_bg():
    data = request.json or {}
    user_id = data.get("user_id")
    bg_key  = data.get("bg_key")

    if not user_id or not bg_key:
        return jsonify({"error": "잘못된 요청입니다"}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "유저를 찾을 수 없습니다"}), 404

    shop_bg = ShopBackground.query.filter_by(key=bg_key).first()
    if not shop_bg:
        return jsonify({"error": "존재하지 않는 배경입니다"}), 404

    already = db.session.execute(
        db.select(ShopBgPurchase).where(
            ShopBgPurchase.user_id == user_id,
            ShopBgPurchase.bg_key == bg_key
        )
    ).scalar_one_or_none()
    if already:
        return jsonify({"error": "이미 보유한 배경입니다"}), 400

    if user.cash < shop_bg.price:
        return jsonify({"error": f"현금이 부족합니다 (필요: {int(shop_bg.price):,}원)"}), 400

    user.cash -= shop_bg.price
    purchase = ShopBgPurchase(user_id=user_id, bg_key=bg_key)
    db.session.add(purchase)
    db.session.commit()

    return jsonify({
        "message": f"'{shop_bg.label}' 배경 구매 완료!",
        "cash": round(user.cash, 2),
        "bg_key": bg_key,
    })


# ── 커스텀 배경 슬롯 구매 ──
@app.route("/shop/buy_custom_bg_slot", methods=["POST"])
def buy_custom_bg_slot():
    data = request.json or {}
    user_id = data.get("user_id")

    if not user_id:
        return jsonify({"error": "잘못된 요청입니다"}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "유저를 찾을 수 없습니다"}), 404

    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id, unlocked_title_ids='1')
        db.session.add(profile)
        db.session.flush()

    current_slots = profile.custom_bg_slot_count or 0

    if current_slots >= 3:
        return jsonify({"error": "커스텀 배경 슬롯은 최대 3개입니다"}), 400

    CUSTOM_PRICES = [10_000_000_000, 100_000_000_000, 1_000_000_000_000]
    price = CUSTOM_PRICES[current_slots]

    if user.cash < price:
        return jsonify({"error": f"현금이 부족합니다 (필요: {int(price):,}원)"}), 400

    user.cash -= price
    profile.custom_bg_slot_count = current_slots + 1
    db.session.commit()

    return jsonify({
        "message": f"커스텀 배경 슬롯 {current_slots + 1}번 구매 완료!",
        "cash": round(user.cash, 2),
        "custom_bg_slot_count": profile.custom_bg_slot_count,
    })


# ── 커스텀 배경 이미지 URL 등록/수정 ──
@app.route("/shop/set_custom_bg", methods=["POST"])
def set_custom_bg():
    data = request.json or {}
    user_id   = data.get("user_id")
    slot      = data.get("slot")
    image_url = (data.get("image_url") or "").strip()

    if not user_id or not slot or slot not in [1, 2, 3]:
        return jsonify({"error": "잘못된 요청입니다"}), 400

    if not image_url:
        return jsonify({"error": "이미지 URL을 입력해주세요"}), 400

    if not (image_url.startswith("http://") or image_url.startswith("https://")):
        return jsonify({"error": "올바른 이미지 URL을 입력해주세요 (http:// 또는 https://)"}), 400

    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile or (profile.custom_bg_slot_count or 0) < slot:
        return jsonify({"error": f"커스텀 배경 슬롯 {slot}번을 구매하지 않았습니다"}), 403

    setattr(profile, f"custom_bg_{slot}", image_url)
    db.session.commit()

    return jsonify({
        "message": f"커스텀 배경 {slot}번 이미지가 등록되었습니다!",
        "slot": slot,
        "image_url": image_url,
    })


# -------------------------
# 닉네임 변경 (총 자산의 15% 소모)
# -------------------------
@app.route("/shop/rename", methods=["POST"])
def shop_rename():
    """닉네임 변경권 구매 & 즉시 적용. 100만원 + 총 자산의 15%를 현금에서 차감."""
    data = request.json or {}
    user_id = data.get("user_id")
    new_username = (data.get("new_username") or "").strip()

    if not user_id:
        return jsonify({"error": "잘못된 요청입니다"}), 400
    if not new_username:
        return jsonify({"error": "새 닉네임을 입력해주세요"}), 400
    if len(new_username) > 20:
        return jsonify({"error": "닉네임은 20자 이내로 입력해주세요"}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "유저를 찾을 수 없습니다"}), 404

    # 동일 닉네임 변경 시도
    if user.username == new_username:
        return jsonify({"error": "현재 닉네임과 동일합니다"}), 400

    # 중복 닉네임 확인
    existing = db.session.execute(
        db.select(User).where(User.username == new_username)
    ).scalar_one_or_none()
    if existing:
        return jsonify({"error": "이미 사용 중인 닉네임입니다"}), 409

    # 총 자산 계산
    holdings = db.session.execute(
        db.select(Holding).where(Holding.user_id == user_id)
    ).scalars().all()
    total_asset = user.cash
    for h in holdings:
        stock = db.session.get(Stock, h.stock_id)
        if stock:
            total_asset += stock.price * h.quantity

    fee = total_asset * 0.01  # 총 자산의 15%

    if user.cash < fee:
        return jsonify({
            "error": f"현금이 부족합니다 (필요: {int(fee):,}원, 보유 현금: {int(user.cash):,}원)",
            "fee": round(fee, 2),
            "cash": round(user.cash, 2),
        }), 400

    old_username = user.username
    user.cash -= fee
    user.username = new_username
    db.session.commit()

    return jsonify({
        "message": f"닉네임이 '{old_username}' → '{new_username}'(으)로 변경되었습니다!",
        "old_username": old_username,
        "new_username": new_username,
        "fee": round(fee, 2),
        "cash": round(user.cash, 2),
        "total_asset": round(total_asset, 2),
    })


# -------------------------
# 닉네임 변경 비용 미리보기
# -------------------------
@app.route("/shop/rename/preview/<int:user_id>")
def shop_rename_preview(user_id):
    """닉네임 변경 시 차감될 비용(총 자산 15%) 미리보기"""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "유저를 찾을 수 없습니다"}), 404

    holdings = db.session.execute(
        db.select(Holding).where(Holding.user_id == user_id)
    ).scalars().all()
    total_asset = user.cash
    for h in holdings:
        stock = db.session.get(Stock, h.stock_id)
        if stock:
            total_asset += stock.price * h.quantity

    fee = total_asset * 0.15
    return jsonify({
        "total_asset": round(total_asset, 2),
        "fee": round(fee, 2),
        "cash": round(user.cash, 2),
        "affordable": user.cash >= fee,
    })


# -------------------------
# 게임 틱 함수들
# -------------------------
_tick_counter = 0

def update_stock_prices():
    global _tick_counter
    _tick_counter += 1

    stocks = db.session.execute(db.select(Stock)).scalars().all()

    all_events = db.session.execute(
        db.select(Event).where(Event.duration > 0)
    ).scalars().all()
    events_by_stock = {}
    for e in all_events:
        events_by_stock.setdefault(e.stock_id, []).append(e)

    new_histories = []
    for s in stocks:
        prev_price = s.price  # 변동률 계산용
        
        change = random.uniform(-0.018, 0.018)

        for i, e in enumerate(events_by_stock.get(s.id, [])):
            decay = 0.5 ** i
            change += e.impact * 0.5 * decay
            e.duration -= 1
            if e.duration <= 0:
                e.duration = 0

        s.price = max(10, s.price * (1 + change))
        new_histories.append(PriceHistory(stock_id=s.id, price=s.price))
        
        # 서킷 브레이커 체크
        change_pct = ((s.price - prev_price) / prev_price * 100) if prev_price else 0
        halt = trigger_circuit_breaker(s.id, change_pct)
        if halt:
            print(f"[CIRCUIT BREAKER] {s.name}: {change_pct:+.2f}% 변동 → {halt}초 거래 정지")

    db.session.bulk_save_objects(new_histories)

    # ✅ 여기에 추가 - 모든 유저 peak_asset 갱신
    all_users = db.session.execute(db.select(User)).scalars().all()
    stocks_price_map = {s.id: s.price for s in stocks}  # 이미 위에서 가격 갱신된 stocks 재활용
    all_holdings = db.session.execute(db.select(Holding)).scalars().all()

    # 유저별 보유주식 총액 집계
    holdings_by_user = {}
    for h in all_holdings:
        holdings_by_user.setdefault(h.user_id, []).append(h)

    for u in all_users:
        stock_value = sum(
            stocks_price_map.get(h.stock_id, 0) * h.quantity
            for h in holdings_by_user.get(u.id, [])
        )
        total_asset = u.cash + stock_value

        profile = UserProfile.query.filter_by(user_id=u.id).first()
        if profile and total_asset > (profile.peak_asset or 0):
            profile.peak_asset = total_asset
            
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
        if _tick_counter % 60 == 0:
        # 오래된 이벤트 정리 (24시간 이상 된 것만)
            from datetime import timedelta
            cutoff = datetime.utcnow() - timedelta(hours=24)
            db.session.execute(
                db.delete(Event).where(Event.created_at < cutoff)
            )

    db.session.commit()

from datetime import timedelta

def check_circuit_breaker(stock_id):
    """서킷 브레이커 상태 확인. 거래 불가 시 남은 시간(초) 반환, 거래 가능 시 None"""
    if stock_id not in circuit_breakers:
        return None
    
    unlock_time = circuit_breakers[stock_id]
    now = datetime.utcnow()
    
    if now >= unlock_time:
        del circuit_breakers[stock_id]
        return None
    
    return int((unlock_time - now).total_seconds())


def trigger_circuit_breaker(stock_id, change_pct):
    """변동률에 따라 서킷 브레이커 발동. 발동 시 정지 시간(초) 반환"""
    abs_change = abs(change_pct)
    
    if abs_change < 5:
        return None
    
    # 변동률에 비례한 정지 시간 계산
    # 5% → 60초, 10% → 120초, 15% → 180초, 최대 300초(5분)
    halt_seconds = min(int(abs_change * 12), 300)
    
    unlock_time = datetime.utcnow() + timedelta(seconds=halt_seconds)
    circuit_breakers[stock_id] = unlock_time
    
    return halt_seconds


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
        multiplier = random.uniform(1.05, 1.20)
        beat = "▲ 예상치 상회"
    else:
        multiplier = random.uniform(0.75, 0.92)
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
            impact = random.choice([0.03, 0.05, 0.10, 0.15])
        else:
            impact = random.choice([-0.03, -0.05, -0.10, -0.20])

        duration = random.randint(3, 10)

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
        if random.random() < 0.2:
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