from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import BigInteger

db = SQLAlchemy()

# 클래스들 정리
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False, default='')
    cash = db.Column(db.Float, default=10000)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    ticker = db.Column(db.String(10), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200))

class Holding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'), nullable=False)
    quantity = db.Column(BigInteger, default=0)   # Integer → BigInteger (overflow 방지)
    avg_price = db.Column(db.Float, default=0)    # 평균 매수가

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'), nullable=False)
    title = db.Column(db.String(100))
    description = db.Column(db.String(200))
    impact = db.Column(db.Float)
    duration = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PriceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Transfer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)   # 받는 금액
    fee = db.Column(db.Float, nullable=False)       # 수수료
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Earnings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'), nullable=False)
    quarter = db.Column(db.String(20))       # "2025 3Q"
    revenue = db.Column(BigInteger)           # 매출 (억원) — BigInteger (overflow 방지)
    operating = db.Column(BigInteger)         # 영업이익
    net = db.Column(BigInteger)               # 순이익
    rev_chg = db.Column(db.Float)            # 전분기 대비 매출 증감률
    op_chg = db.Column(db.Float)             # 영업이익 증감률
    net_chg = db.Column(db.Float)            # 순이익 증감률
    beat = db.Column(db.String(20))          # "▲ 예상치 상회" or "▼ 예상치 하회"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TradeLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, nullable=False)
    stock_id = db.Column(db.Integer, nullable=False)

    action = db.Column(db.String(10))  # 'buy' or 'sell'
    quantity = db.Column(BigInteger)   # BigInteger
    price = db.Column(db.Float)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    market_impact = db.Column(db.Float, default=0.0)   # 시장 영향 누적
    halt_until = db.Column(db.DateTime, nullable=True) # 거래 정지 시간


# ── 칭호 / 배경 시스템 ──────────────────────────────────────────────

# 칭호 정의 테이블 (앱 초기화 시 seed_titles()로 DB에 삽입)
# condition_type: 'asset' (총 자산 기준)
# condition_value: 해당 타입의 임계값 (원 단위)
class Title(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(30), nullable=False)   # "억만장자"
    emoji          = db.Column(db.String(10), nullable=False)   # "💰"
    description    = db.Column(db.String(100))                  # "총 자산 1억 원 돌파"
    condition_type = db.Column(db.String(20), nullable=False)   # "asset"
    condition_value= db.Column(db.Float, nullable=False)        # 100_000_000
    color          = db.Column(db.String(20), nullable=False)   # CSS 색상값 (예: "#f59e0b")
    sort_order     = db.Column(db.Integer, default=0)           # 표시 순서 (낮을수록 먼저)


# 유저 프로필 테이블 (1유저 1행)
# unlocked_title_ids: 쉼표로 구분된 Title.id 문자열 (예: "1,2,3")
#   → JSON 컬럼 대신 String을 사용해 SQLite 호환성 유지
# equipped_title_id : 현재 장착 중인 Title.id (없으면 NULL)
# equipped_bg       : 현재 장착 중인 배경 키 (예: "default", "purple", "gold")
class UserProfile(db.Model):
    id                      = db.Column(db.Integer, primary_key=True)
    user_id                 = db.Column(db.Integer, db.ForeignKey('user.id'),
                                        nullable=False, unique=True)
    unlocked_title_ids      = db.Column(db.String(200), default='1')  # 새싹(id=1)은 기본 지급
    equipped_title_id       = db.Column(db.Integer, db.ForeignKey('title.id'), nullable=True)
    equipped_shop_title_id  = db.Column(db.Integer, db.ForeignKey('shop_title.id'), nullable=True)
    equipped_bg             = db.Column(db.String(30), default='default')
    peak_asset              = db.Column(db.Float, default=0)          # 최대 보유 자산
    updated_at              = db.Column(db.DateTime, default=datetime.utcnow,
                                        onupdate=datetime.utcnow)


# ── 칭호 초기 데이터 (app.py의 create_tables() 안에서 호출) ─────────
TITLE_SEEDS = [
    {
        'id': 1,
        'name': '새싹 투자자',
        'emoji': '🌱',
        'description': '주식고수에 첫 발을 내딛었습니다',
        'condition_type': 'asset',
        'condition_value': 0,          # 가입 즉시 지급
        'color': '#8888aa',
        'sort_order': 1,
    },
    {
        'id': 2,
        'name': '억만장자',
        'emoji': '💰',
        'description': '총 자산 1억 원 돌파',
        'condition_type': 'asset',
        'condition_value': 100_000_000,
        'color': '#f59e0b',
        'sort_order': 2,
    },
    {
        'id': 3,
        'name': '다이아 투자자',
        'emoji': '💎',
        'description': '총 자산 10억 원 돌파',
        'condition_type': 'asset',
        'condition_value': 1_000_000_000,
        'color': '#06b6d4',
        'sort_order': 3,
    },
    {
        'id': 4,
        'name': '전설의 고수',
        'emoji': '👑',
        'description': '총 자산 1조 원 돌파',
        'condition_type': 'asset',
        'condition_value': 1_000_000_000_000,
        'color': '#a855f7',
        'sort_order': 4,
    },
]

def seed_titles():
    """앱 시작 시 Title 테이블에 초기 데이터가 없으면 삽입."""
    if Title.query.count() == 0:
        for data in TITLE_SEEDS:
            db.session.add(Title(**data))
        db.session.commit()


# ── 상점 칭호 시스템 ──────────────────────────────────────────────

# 상점에서 현금으로 구매하는 칭호 정의 테이블
class ShopTitle(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(30), nullable=False)    # "황금 손"
    emoji       = db.Column(db.String(10), nullable=False)    # "🤑"
    description = db.Column(db.String(100))                   # "상점에서 구매한 칭호"
    price       = db.Column(db.Float, nullable=False)         # 구매 가격 (원)
    color       = db.Column(db.String(20), nullable=False)    # CSS 색상값
    sort_order  = db.Column(db.Integer, default=0)


# 유저의 상점 칭호 구매 기록
class ShopPurchase(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    shop_title_id  = db.Column(db.Integer, db.ForeignKey('shop_title.id'), nullable=False)
    purchased_at   = db.Column(db.DateTime, default=datetime.utcnow)


# ── 상점 칭호 초기 데이터 ────────────────────────────────────────
SHOP_TITLE_SEEDS = [
    {
        'id': 1,
        'name': '황금의 손',
        'emoji': '🤑',
        'description': '오르는 주식을 알아보는 눈을 지니셨군요?',
        'price': 1000_0000,
        'color': '#f59e0b',
        'sort_order': 1,
    },
    {
        'id': 2,
        'name': '열혈 트레이더',
        'emoji': '🔥',
        'description': '시장을 불태우는 자',
        'price': 1500_0000,
        'color': '#ef4444',
        'sort_order': 2,
    },
    {
        'id': 3,
        'name': '다크호스',
        'emoji': '🐴',
        'description': '아무도 예측 못할 다크호스',
        'price': 1_5000_0000,
        'color': "#38226d83",
        'sort_order': 3,
    },
    {
        'id': 4,
        'name': '월스트리트의 해커',
        'emoji': '💻',
        'description': '너도 할 수 있다! 주가조작!',
        'price': 3_0000_0000,
        'color': '#06b6d4',
        'sort_order': 4,
    },
    {
        'id': 5,
        'name': '시장의 설계자',
        'emoji': '📐',
        'description': '수학으로 부를 설계하는 자',
        'price': 5_0000_0000,
        'color': '#22c55e',
        'sort_order': 5,
    },
    {
        'id': 6,
        'name': '개미들의 우상',
        'emoji': '🐜',
        'description': '오오.. 개미들의 왕이시여!',
        'price': 100_0000_0000,
        'color': "#a05757",
        'sort_order': 5,
    },
    {
        'id': 7,
        'name': '하락장의 생존자',
        'emoji': '😮‍💨',
        'description': '그날은.. 정말 끔찍했어요!',
        'price': 10_0000_0000,
        'color': "#2e76a2",
        'sort_order': 5,
    },
    {
        'id': 8,
        'name': '쫒겨난 CEO',
        'emoji': '🧿',
        'description': '하지만 주식은 올랐죠?',
        'price': 10_0000_0000,
        'color': "#97fff1",
        'sort_order': 5,
    },
    {
        'id': 9,
        'name': '투자 고수',
        'emoji': '🥽',
        'description': '이 정도 경지라면, 두려울 게 없겠네요!',
        'price': 1000_0000_0000,
        'color': "#ffe990",
        'sort_order': 5,
    },
    {
        'id': 10,
        'name': '주식의 신',
        'emoji': '🎖️',
        'description': '정점',
        'price': 1_0000_0000_0000_0000,
        'color': "#0000ff",
        'sort_order': 6,
    },
]


def seed_shop_titles():
    existing_ids = {
        t.id for t in ShopTitle.query.all()
    }

    for data in SHOP_TITLE_SEEDS:
        if data['id'] not in existing_ids:
            db.session.add(ShopTitle(**data))

    db.session.commit()


# ── 칭호 자동 지급 헬퍼 (app.py의 매수/매도/포트폴리오 API에서 호출) ─
def check_and_unlock_titles(user_id: int, total_asset: float):
    """
    total_asset 기준으로 조건을 충족하는 칭호를 자동 지급한다.
    새로 지급된 칭호 목록(Title 객체 리스트)을 반환한다.
    """
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        # 프로필이 아직 없으면 생성 (새싹은 기본 포함)
        profile = UserProfile(user_id=user_id, unlocked_title_ids='1')
        db.session.add(profile)
        db.session.flush()

    unlocked = set(
        int(x) for x in profile.unlocked_title_ids.split(',') if x.strip()
    )

    eligible = Title.query.filter(
        Title.condition_type == 'asset',
        Title.condition_value <= total_asset
    ).all()

    newly_unlocked = []
    for title in eligible:
        if title.id not in unlocked:
            unlocked.add(title.id)
            newly_unlocked.append(title)

    if newly_unlocked:
        profile.unlocked_title_ids = ','.join(str(i) for i in sorted(unlocked))
        db.session.commit()

    return newly_unlocked