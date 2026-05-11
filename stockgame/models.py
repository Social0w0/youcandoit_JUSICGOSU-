from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

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
    quantity = db.Column(db.Integer, default=0)
    avg_price = db.Column(db.Float, default=0)  # 평균 매수가

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
    revenue = db.Column(db.Integer)           # 매출 (억원)
    operating = db.Column(db.Integer)         # 영업이익
    net = db.Column(db.Integer)               # 순이익
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
    quantity = db.Column(db.Integer)
    price = db.Column(db.Float)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    market_impact = db.Column(db.Float, default=0.0)   # 시장 영향 누적
    halt_until = db.Column(db.DateTime, nullable=True) # 거래 정지 시간