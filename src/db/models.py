"""
数据库模型定义
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import enum

Base = declarative_base()


class SourceType(enum.Enum):
    WALLET = "wallet"
    CEX = "cex"


class AssetType(enum.Enum):
    TOKEN = "token"          # 普通代币
    DEFI = "defi"            # DeFi 仓位
    NFT = "nft"              # NFT
    SPOT = "spot"            # 交易所现货
    FUTURES = "futures"      # 合约
    EARN = "earn"            # 理财/质押


class Wallet(Base):
    """钱包地址表"""
    __tablename__ = "wallets"
    
    id = Column(Integer, primary_key=True)
    address = Column(String(64), unique=True, nullable=False)
    label = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    snapshots = relationship("Snapshot", back_populates="wallet")


class CexAccount(Base):
    """交易所账号表"""
    __tablename__ = "cex_accounts"
    
    id = Column(Integer, primary_key=True)
    exchange = Column(String(20), nullable=False)  # binance/bybit/okx/bitget
    account_label = Column(String(100))
    api_key_ref = Column(String(100))  # 配置文件中的引用标识
    created_at = Column(DateTime, default=datetime.utcnow)
    
    snapshots = relationship("Snapshot", back_populates="cex_account")


class Snapshot(Base):
    """资产快照表 - 每次采集的汇总"""
    __tablename__ = "snapshots"
    
    id = Column(Integer, primary_key=True)
    source_type = Column(String(10), nullable=False)  # wallet/cex
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True)
    cex_account_id = Column(Integer, ForeignKey("cex_accounts.id"), nullable=True)
    total_usd = Column(Float, default=0.0)
    snapshot_time = Column(DateTime, default=datetime.utcnow)
    
    wallet = relationship("Wallet", back_populates="snapshots")
    cex_account = relationship("CexAccount", back_populates="snapshots")
    details = relationship("AssetDetail", back_populates="snapshot", cascade="all, delete-orphan")


class AssetDetail(Base):
    """资产明细表 - 具体持仓"""
    __tablename__ = "asset_details"
    
    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("snapshots.id"), nullable=False)
    asset_type = Column(String(20), nullable=False)  # token/defi/nft/spot/futures/earn
    symbol = Column(String(20), nullable=False)
    chain = Column(String(20), nullable=True)  # eth/bsc/arb/... CEX 为空
    protocol = Column(String(50), nullable=True)  # DeFi 协议名
    amount = Column(Float, default=0.0)
    price_usd = Column(Float, default=0.0)
    value_usd = Column(Float, default=0.0)
    
    snapshot = relationship("Snapshot", back_populates="details")


def init_db(db_path: str = "portfolio.db"):
    """初始化数据库"""
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return engine


def get_session(engine):
    """获取数据库会话"""
    Session = sessionmaker(bind=engine)
    return Session()


if __name__ == "__main__":
    # 测试初始化
    engine = init_db()
    print("数据库初始化完成")
