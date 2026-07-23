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
    color          = db.Column(db.String(100), nullable=False)   # CSS 색상값 (예: "#f59e0b")
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
    equipped_gacha_title_id = db.Column(db.Integer, db.ForeignKey('gacha_title.id'), nullable=True)
    equipped_bg             = db.Column(db.String(30), default='default')
    peak_asset              = db.Column(db.Float, default=0)          # 최대 보유 자산
    updated_at              = db.Column(db.DateTime, default=datetime.utcnow,
                                        onupdate=datetime.utcnow)
    # 커스텀 이미지 배경 슬롯
    custom_bg_1             = db.Column(db.String(500), nullable=True)
    custom_bg_2             = db.Column(db.String(500), nullable=True)
    custom_bg_3             = db.Column(db.String(500), nullable=True)
    custom_bg_slot_count    = db.Column(db.Integer, default=0)  # 구매한 슬롯 수 (0~3)
    # 관리자 지급 커스텀 칭호
    equipped_custom_title_id = db.Column(db.Integer, db.ForeignKey('custom_title.id'), nullable=True)


# ── 관리자 지급 커스텀 칭호 ──────────────────────────────────────────

class CustomTitle(db.Model):
    """관리자가 직접 생성·지급하는 커스텀 칭호 정의 테이블"""
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(30), nullable=False)    # "베타테스터"
    emoji       = db.Column(db.String(10), nullable=False)    # "🧪"
    description = db.Column(db.String(100))
    color       = db.Column(db.String(100), nullable=False)   # 기존 color 규칙 동일
    sort_order  = db.Column(db.Integer, default=0)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)


class CustomTitleOwned(db.Model):
    """유저-커스텀칭호 소유 기록 (M:N)"""
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    custom_title_id = db.Column(db.Integer, db.ForeignKey('custom_title.id'), nullable=False)
    granted_at      = db.Column(db.DateTime, default=datetime.utcnow)
    note            = db.Column(db.String(100))  # 지급 사유 메모 (선택)


# ── 칭호 초기 데이터 (app.py의 create_tables() 안에서 호출) ─────────
TITLE_SEEDS = [
    {
        'id': 1,
        'name': '새싹 투자자',
        'emoji': '🌱',
        'description': '주식고수에 첫 발을 내딛었습니다',
        'condition_type': 'asset',
        'condition_value': 0,
        'color': '#8888aa',          # 기본 단색 유지
        'sort_order': 1,
    },
    {
        'id': 2,
        'name': '억만장자',
        'emoji': '💰',
        'description': '총 자산 1억 원 돌파',
        'condition_type': 'asset',
        'condition_value': 100_000_000,
        'color': 'anim:gold',        # ✨ 황금 shimmer
        'sort_order': 2,
    },
    {
        'id': 3,
        'name': '다이아 투자자',
        'emoji': '💎',
        'description': '총 자산 10억 원 돌파',
        'condition_type': 'asset',
        'condition_value': 1_000_000_000,
        'color': 'anim:ice',         # ❄️ 청백 shimmer
        'sort_order': 3,
    },
    {
        'id': 4,
        'name': '전설의 고수',
        'emoji': '👑',
        'description': '총 자산 1조 원 돌파',
        'condition_type': 'asset',
        'condition_value': 1_000_000_000_000,
        'color': "#9E28FF",      # 🌌 galaxy 그라데이션
        'sort_order': 4,
    },
]

def seed_titles():
    """앱 시작 시 Title 테이블을 TITLE_SEEDS와 동기화.
    - 없는 항목은 새로 삽입
    - 이미 있는 항목은 color / name / emoji / description 을 항상 최신값으로 업데이트
    """
    existing = {t.id: t for t in Title.query.all()}
    for data in TITLE_SEEDS:
        if data['id'] not in existing:
            db.session.add(Title(**data))
        else:
            t = existing[data['id']]
            t.color       = data['color']
            t.name        = data['name']
            t.emoji       = data['emoji']
            t.description = data['description']
            t.sort_order  = data['sort_order']
    db.session.commit()


# ── 상점 칭호 시스템 ──────────────────────────────────────────────

# 상점에서 현금으로 구매하는 칭호 정의 테이블
class ShopTitle(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(30), nullable=False)    # "황금 손"
    emoji       = db.Column(db.String(10), nullable=False)    # "🤑"
    description = db.Column(db.String(100))                   # "상점에서 구매한 칭호"
    price       = db.Column(db.Float, nullable=False)         # 구매 가격 (원)
    color       = db.Column(db.String(100), nullable=False)    # CSS 색상값
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
        'color': 'anim:gold',        # ✨ 황금 shimmer
        'sort_order': 1,
    },
    {
        'id': 2,
        'name': '열혈 트레이더',
        'emoji': '🔥',
        'description': '시장을 불태우는 자',
        'price': 1500_0000,
        'color': 'anim:fire',        # 🔥 불꽃 그라데이션
        'sort_order': 2,
    },
    {
        'id': 12,
        'name': '존버의 화석',
        'emoji': '🗿',
        'description': '우리는, 결국 승리한다.',
        'price': 3000_0000,
        'color': "#746060",          # 단색 유지 (화석 느낌)
        'sort_order': 2,
    },
    {
        'id': 13,
        'name': '상폐 컬렉터',
        'emoji': '💀',
        'description': '우리는, 결국 승리한다.',
        'price': 4000_0000,
        'color': 'anim:glitch',      # ⚡ 글리치 (해골 느낌)
        'sort_order': 2,
    },
    {
        'id': 14,
        'name': '광대',
        'emoji': '🤡',
        'description': '아저씨는 왜 집이 없어요??',
        'price': 5000_0000,
        'color': 'anim:rainbow',     # 🌈 무지개 (광대 느낌)
        'sort_order': 3,
    },
    {
        'id': 3,
        'name': '다크호스',
        'emoji': '🐴',
        'description': '아무도 예측 못할 다크호스',
        'price': 1_5000_0000,
        'color': 'linear-gradient(90deg, #38226d, #7b5ea7)',  # 정적 다크 퍼플
        'sort_order': 3,
    },
    {
        'id': 4,
        'name': '월스트리트의 해커',
        'emoji': '💻',
        'description': '너도 할 수 있다! 주가조작!',
        'price': 3_0000_0000,
        'color': 'anim:neon',        # 💡 neon pulse (해커 느낌)
        'sort_order': 4,
    },
    {
        'id': 5,
        'name': '시장의 설계자',
        'emoji': '📐',
        'description': '수학으로 부를 설계하는 자',
        'price': 5_0000_0000,
        'color': '#22c55e',          # 단색 유지
        'sort_order': 5,
    },
    {
        'id': 6,
        'name': '개미들의 우상',
        'emoji': '🐜',
        'description': '오오.. 개미들의 왕이시여!',
        'price': 100_0000_0000,
        'color': "#a05757",          # 단색 유지
        'sort_order': 5,
    },
    {
        'id': 7,
        'name': '하락장의 생존자',
        'emoji': '😮‍💨',
        'description': '그날은.. 정말 끔찍했어요!',
        'price': 10_0000_0000,
        'color': 'linear-gradient(90deg, #2e76a2, #06b6d4)',  # 정적 블루 그라데이션
        'sort_order': 5,
    },
    {
        'id': 8,
        'name': '쫒겨난 CEO',
        'emoji': '🧿',
        'description': '하지만 주식은 올랐죠?',
        'price': 10_0000_0000,
        'color': 'anim:ice',         # ❄️ ice shimmer
        'sort_order': 5,
    },
    {
        'id': 9,
        'name': '투자 고수',
        'emoji': '🥽',
        'description': '이 정도 경지라면, 두려울 게 없겠네요!',
        'price': 1000_0000_0000,
        'color': 'anim:shimmer',     # shimmer (ffe990 베이스는 CSS에서 커스텀 가능)
        'sort_order': 7,
    },
    {
        'id': 11,
        'name': '물린 자의 품격',
        'emoji': '😎',
        'description': '나 지금... 떨고 있니?',
        'price': 70_0000_0000,
        'color': "#9fff31",          # 단색 유지
        'sort_order': 6,
    },
    {
        'id': 15,
        'name': '보이지 않는 손',
        'emoji': '✋',
        'description': '주가를 주무르는 거대한 권력!',
        'price': 1_0000_0000_0000,
        'color': 'anim:shimmer',     # shimmer
        'sort_order': 7,
    },
    {
        'id': 16,
        'name': '불사조',
        'emoji': '🐦‍🔥',
        'description': '뭣 4조가 불에 탄다고??!',
        'price': 4_0000_0000_0000,
        'color': 'anim:fire',        # 🔥 불꽃
        'sort_order': 7,
    },
    {
        'id': 17,
        'name': '초신성',
        'emoji': '🌠',
        'description': '어느새 여기까지.',
        'price': 100_0000_0000_0000,
        'color': 'anim:galaxy',      # 🌌 galaxy
        'sort_order': 7,
    },
    {
        'id': 18,
        'name': '글로볼',
        'emoji': '🌏',
        'description': '주식을 세계로 !!',
        'price': 1000_0000_0000_0000,
        'color': 'anim:rainbow',     # 🌈 rainbow
        'sort_order': 7,
    },
    {
        'id': 10,
        'name': '주식의 신',
        'emoji': '🎖️',
        'description': '정점',
        'price': 1_0000_0000_0000_0000,
        'color': 'anim:galaxy',      # 🌌 최고 등급 - galaxy
        'sort_order': 8,
    },
]


def seed_shop_titles():
    """앱 시작 시 ShopTitle 테이블을 SHOP_TITLE_SEEDS와 동기화.
    - 없는 항목은 새로 삽입
    - 이미 있는 항목은 color / name / emoji / description / price 를 항상 최신값으로 업데이트
    """
    existing = {t.id: t for t in ShopTitle.query.all()}
    seen_ids = set()
    for data in SHOP_TITLE_SEEDS:
        if data['id'] in seen_ids:
            # SHOP_TITLE_SEEDS 안에 같은 id가 중복 정의된 경우 (복붙 실수 등)
            # 여기서 걸러서 같은 PK를 두 번 insert하는 사고를 막는다.
            print(f"[SEED WARNING] shop_title id={data['id']} 가 SHOP_TITLE_SEEDS에 중복 정의되어 있습니다. 뒤에 나온 항목은 무시합니다.")
            continue
        seen_ids.add(data['id'])
        if data['id'] not in existing:
            db.session.add(ShopTitle(**data))
        else:
            t = existing[data['id']]
            t.color       = data['color']
            t.name        = data['name']
            t.emoji       = data['emoji']
            t.description = data['description']
            t.sort_order  = data['sort_order']
            # price는 이미 구매한 유저가 있을 수 있어 기본 유지. 바꾸려면 아래 주석 해제:
            # t.price = data['price']
    db.session.commit()


# ── 상점 배경 시스템 ──────────────────────────────────────────────

class ShopBackground(db.Model):
    __tablename__ = 'shop_background'
    id         = db.Column(db.Integer, primary_key=True)
    key        = db.Column(db.String(50), unique=True, nullable=False)
    label      = db.Column(db.String(50), nullable=False)
    price      = db.Column(db.Float, default=50000)
    sort_order = db.Column(db.Integer, default=0)


class ShopBgPurchase(db.Model):
    __tablename__ = 'shop_bg_purchase'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bg_key     = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


SHOP_BG_LIST = [
    {"key": "black",     "label": "검정",      "price": 50000, "sort_order": 10},
    {"key": "violet",    "label": "보라",       "price": 50000, "sort_order": 11},
    {"key": "forest",    "label": "초록",       "price": 50000, "sort_order": 12},
    {"key": "yellow",    "label": "노랑",       "price": 50000, "sort_order": 13},
    {"key": "crimson",   "label": "빨강",       "price": 50000, "sort_order": 14},
    {"key": "blue",      "label": "파란색",     "price": 50000, "sort_order": 15},
    {"key": "sky",       "label": "하늘색",     "price": 50000, "sort_order": 16},
    {"key": "pink",      "label": "핑크",       "price": 50000, "sort_order": 17},
    {"key": "white",     "label": "하양",       "price": 50000, "sort_order": 18},
    {"key": "orange",    "label": "주황",       "price": 50000, "sort_order": 19},
    {"key": "lime",      "label": "연두",       "price": 50000, "sort_order": 20},
    {"key": "lavender",  "label": "연보라",     "price": 50000, "sort_order": 21},
    {"key": "rose",      "label": "연한 빨강",  "price": 50000, "sort_order": 22},
    {"key": "lightblue", "label": "연한 파랑",  "price": 50000, "sort_order": 23},
    {"key": "silver",    "label": "은색",       "price": 50000, "sort_order": 24},
]


def seed_shop_backgrounds():
    for b in SHOP_BG_LIST:
        existing = ShopBackground.query.filter_by(key=b["key"]).first()
        if not existing:
            db.session.add(ShopBackground(**b))
    db.session.commit()


# ── 칭호 자동 지급 헬퍼 (app.py의 매수/매도/포트폴리오 API에서 호출) ─
# ── 뽑기(가챠) 시스템 ──────────────────────────────────────────────

# 뽑기 전용 칭호 정의
# is_point_purchasable: False 이면 포인트로 구매 불가 (확률의 신 등)
# rarity: 'common'(1pt) | 'rare'(2~3pt) | 'epic' | 'legendary'
class GachaTitle(db.Model):
    __tablename__ = 'gacha_title'
    id                  = db.Column(db.Integer, primary_key=True)
    name                = db.Column(db.String(30), nullable=False)
    emoji               = db.Column(db.String(10), nullable=False)
    description         = db.Column(db.String(100))
    color               = db.Column(db.String(100), nullable=False)
    rarity              = db.Column(db.String(20), nullable=False, default='common')  # common/rare/epic/legendary
    weight              = db.Column(db.Integer, nullable=False, default=100)          # 뽑기 가중치 (높을수록 잘 나옴)
    point_value         = db.Column(db.Integer, nullable=False, default=1)            # 뽑혔을 때 지급 포인트 (꽝 역할)
    is_point_purchasable= db.Column(db.Boolean, nullable=False, default=True)         # 포인트 상점에서 구매 가능 여부
    point_price         = db.Column(db.Integer, nullable=True)                        # 포인트 상점 구매 가격 (None=구매불가)
    sort_order          = db.Column(db.Integer, default=0)


# 유저의 뽑기 칭호 보유 기록
class GachaTitleOwned(db.Model):
    __tablename__ = 'gacha_title_owned'
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    gacha_title_id  = db.Column(db.Integer, db.ForeignKey('gacha_title.id'), nullable=False)
    obtained_at     = db.Column(db.DateTime, default=datetime.utcnow)


# 유저 뽑기 포인트 (현금과 분리)
class GachaPoint(db.Model):
    __tablename__ = 'gacha_point'
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    points      = db.Column(db.Integer, nullable=False, default=0)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# 유저가 장착 중인 뽑기 칭호 (UserProfile에 컬럼 추가 대신 별도 관리)
# → UserProfile에 equipped_gacha_title_id 컬럼을 마이그레이션으로 추가


# ── 뽑기 칭호 시드 데이터 ────────────────────────────────────────
GACHA_TITLE_SEEDS = [
    # ── common (weight 120~200, 1pt) ──
    {
        'id': 1,  'name': '행운아', 'emoji': '🎲',
        'description': '운이 좋은 사람, 그게 나야',
        'color': '#a3e635', 'rarity': 'common', 'weight': 100,
        'point_value': 1, 'is_point_purchasable': True, 'point_price': 30, 'sort_order': 1,
    },
    {
        'id': 2,  'name': '복권 수집가', 'emoji': '🎫',
        'description': '긁다 보면 언젠간 터진다',
        'color': '#facc15', 'rarity': 'common', 'weight': 80,
        'point_value': 1, 'is_point_purchasable': True, 'point_price': 35, 'sort_order': 2,
    },
    {
        'id': 3,  'name': '슬롯머신 마스터', 'emoji': '🎰',
        'description': '딩딩딩~ 7이 세 개!',
        'color': '#fb923c', 'rarity': 'common', 'weight': 80,
        'point_value': 1, 'is_point_purchasable': True, 'point_price': 80, 'sort_order': 3,
    },
    {
        'id': 4,  'name': '뽑기왕', 'emoji': '🎯',
        'description': '뽑기라면 자신 있어',
        'color': '#38bdf8', 'rarity': 'common', 'weight': 60,
        'point_value': 1, 'is_point_purchasable': True, 'point_price': 80, 'sort_order': 4,
    },
    {
        'id': 5,  'name': '캡슐토이 중독자', 'emoji': '🪆',
        'description': '또 돌렸어... 또 꽝이야...',
        'color': '#c084fc', 'rarity': 'common', 'weight': 70,
        'point_value': 1, 'is_point_purchasable': True, 'point_price': 90, 'sort_order': 5,
    },
    {
        'id': 6,  'name': '기대치 계산기', 'emoji': '🧮',
        'description': '기댓값? 나는 항상 마이너스지',
        'color': '#94a3b8', 'rarity': 'common', 'weight': 65,
        'point_value': 1, 'is_point_purchasable': True, 'point_price': 100, 'sort_order': 6,
    },
    {
        'id': 7,  'name': '운빨 이론가', 'emoji': '🔮',
        'description': '오늘은 분명히 나올 차례야',
        'color': '#818cf8', 'rarity': 'common', 'weight': 60,
        'point_value': 1, 'is_point_purchasable': True, 'point_price': 100, 'sort_order': 7,
    },
    # ── rare (weight 40~80, 2~3pt) ──
    {
        'id': 8,  'name': '황금 손가락', 'emoji': '☝️',
        'description': '내가 고르면 반드시 나온다',
        'color': 'anim:gold', 'rarity': 'rare', 'weight': 40,
        'point_value': 2, 'is_point_purchasable': True, 'point_price': 300, 'sort_order': 10,
    },
    {
        'id': 9,  'name': '네잎클로버', 'emoji': '🍀',
        'description': '행운이 따르는 자',
        'color': '#4ade80', 'rarity': 'rare', 'weight': 35,
        'point_value': 2, 'is_point_purchasable': True, 'point_price': 300, 'sort_order': 11,
    },
    {
        'id': 10, 'name': '럭키 세븐', 'emoji': '7️⃣',
        'description': '777! 잭팟!',
        'color': 'anim:rainbow', 'rarity': 'rare', 'weight': 30,
        'point_value': 2, 'is_point_purchasable': True, 'point_price': 300, 'sort_order': 12,
    },
    {
        'id': 11, 'name': '도박사의 오류', 'emoji': '🎭',
        'description': '이번엔 진짜 나올 것 같은데...',
        'color': '#f472b6', 'rarity': 'rare', 'weight': 22,
        'point_value': 2, 'is_point_purchasable': True, 'point_price': 450, 'sort_order': 13,
    },
    {
        'id': 12, 'name': '뽑기 중독 치료 중', 'emoji': '🏥',
        'description': '다음이 마지막이야... 진짜로',
        'color': '#67e8f9', 'rarity': 'rare', 'weight': 20,
        'point_value': 3, 'is_point_purchasable': True, 'point_price': 450, 'sort_order': 14,
    },
    {
        'id': 13, 'name': '별의 별', 'emoji': '⭐',
        'description': '별을 따다 담은 자',
        'color': 'anim:shimmer', 'rarity': 'rare', 'weight': 20,
        'point_value': 3, 'is_point_purchasable': True, 'point_price': 500, 'sort_order': 15,
    },
    # ── epic (weight 8~20, 3pt) ──
    {
        'id': 14, 'name': '확률 파괴자', 'emoji': '💥',
        'description': '0.1%를 뚫은 자',
        'color': 'anim:fire', 'rarity': 'epic', 'weight': 10,
        'point_value': 3, 'is_point_purchasable': True, 'point_price': 1000, 'sort_order': 20,
    },
    {
        'id': 15, 'name': '운명의 선택자', 'emoji': '⚡',
        'description': '운명은 내 손 안에',
        'color': 'anim:neon', 'rarity': 'epic', 'weight': 7, 
        'point_value': 3, 'is_point_purchasable': True, 'point_price': 1000, 'sort_order': 21,
    },
    {
        'id': 16, 'name': '카지노 디스트로이어', 'emoji': '🃏',
        'description': '카지노를 무너뜨린 전설',
        'color': 'anim:glitch', 'rarity': 'epic', 'weight': 5,
        'point_value': 3, 'is_point_purchasable': True, 'point_price': 1400, 'sort_order': 22,
    },
    {
        'id': 17, 'name': '은하수 뽑기꾼', 'emoji': '🌌',
        'description': '우주에서도 꽝은 꽝이야',
        'color': 'anim:galaxy', 'rarity': 'epic', 'weight': 4,
        'point_value': 3, 'is_point_purchasable': True, 'point_price': 1600, 'sort_order': 23,
    },
    # ── legendary (weight 1~3, 3pt) — 포인트 구매 가능 ──
    {
        'id': 18, 'name': '신의 한 수', 'emoji': '🪁',
        'description': '전설의 경지에 도달한 뽑기꾼',
        'color': 'anim:godsky', 'rarity': 'legendary', 'weight': 3,
        'point_value': 10, 'is_point_purchasable': True, 'point_price': 4000, 'sort_order': 30,
    },
    {
        'id': 19, 'name': '무한 루프', 'emoji': '♾️',
        'description': '뽑고 또 뽑고 뽑고 또 뽑고',
        'color': 'anim:ice', 'rarity': 'legendary', 'weight': 2,
        'point_value': 10, 'is_point_purchasable': True, 'point_price': 5000, 'sort_order': 31,
    },
    # ── legendary (포인트 구매 불가 — 확률의 신) ──
    {
        'id': 20, 'name': '확률의 신', 'emoji': '🍀',
        'description': '오직 뽑기로만 얻을 수 있는 전설',
        'color': 'anim:luck', 'rarity': 'legendary', 'weight': 1,
        'point_value': 3, 'is_point_purchasable': False, 'point_price': None, 'sort_order': 99,
    },
]


def seed_gacha_titles():
    """앱 시작 시 GachaTitle 테이블을 동기화."""
    existing = {t.id: t for t in GachaTitle.query.all()}
    for data in GACHA_TITLE_SEEDS:
        if data['id'] not in existing:
            db.session.add(GachaTitle(**data))
        else:
            t = existing[data['id']]
            db.session.expire(t)        # ← 추가: 캐시 초기화
            for k, v in data.items():
                if k != 'id':
                    setattr(t, k, v)
    db.session.commit()


def get_or_create_gacha_point(user_id: int) -> 'GachaPoint':
    gp = GachaPoint.query.filter_by(user_id=user_id).first()
    if not gp:
        gp = GachaPoint(user_id=user_id, points=0)
        db.session.add(gp)
        db.session.flush()
    return gp


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