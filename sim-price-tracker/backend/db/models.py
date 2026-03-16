from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class Provider(Base):
    """Network provider or affiliate site"""
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(50), unique=True, nullable=False)
    provider_type = Column(String(20), nullable=False)  # network, mvno, affiliate
    logo_url = Column(String(500), nullable=True)
    website_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    plans = relationship("Plan", back_populates="provider", lazy="selectin")


class Plan(Base):
    """A SIM-only plan offering"""
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    name = Column(String(200), nullable=False)
    url = Column(String(1000), nullable=False)
    data_gb = Column(Integer, nullable=True)  # None means unlimited
    data_unlimited = Column(Boolean, default=False)
    contract_months = Column(Integer, default=1)  # 1 = rolling monthly
    is_5g = Column(Boolean, default=False)
    minutes = Column(String(50), nullable=True)  # "unlimited" or number
    texts = Column(String(50), nullable=True)  # "unlimited" or number
    extras = Column(Text, nullable=True)  # JSON string of extras
    external_id = Column(String(200), nullable=True)  # For deduplication
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    provider = relationship("Provider", back_populates="plans")
    price_snapshots = relationship("PriceSnapshot", back_populates="plan", lazy="selectin", order_by="PriceSnapshot.scraped_at.desc()")

    @property
    def current_price(self):
        """Get the most recent price"""
        if self.price_snapshots:
            return self.price_snapshots[0].price
        return None


class PriceSnapshot(Base):
    """Historical price record for a plan"""
    __tablename__ = "price_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False, index=True)
    price = Column(Float, nullable=False)  # Monthly price in GBP
    scraped_at = Column(DateTime, default=datetime.utcnow, index=True)

    plan = relationship("Plan", back_populates="price_snapshots")
