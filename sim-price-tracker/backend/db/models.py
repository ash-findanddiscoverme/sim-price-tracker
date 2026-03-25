"""Database models for SIM price tracker."""

from datetime import datetime
from typing import Optional, List
import json

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, Index
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from .database import Base


class Provider(Base):
    """Provider / network / affiliate site."""
    __tablename__ = "providers"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(20), nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    plans: Mapped[List["Plan"]] = relationship("Plan", back_populates="provider")


class Plan(Base):
    """SIM-only plan."""
    __tablename__ = "plans"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Core fields (priority)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    data_gb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    data_unlimited: Mapped[bool] = mapped_column(Boolean, default=False)
    contract_months: Mapped[int] = mapped_column(Integer, default=1)
    
    # Attribution
    network_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Confidence tracking
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_reasons: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extraction_strategy: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    needs_verification: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Metadata
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    provider: Mapped["Provider"] = relationship("Provider", back_populates="plans")
    price_snapshots: Mapped[List["PriceSnapshot"]] = relationship("PriceSnapshot", back_populates="plan")
    
    __table_args__ = (
        Index("ix_plans_provider_external", "provider_id", "external_id", unique=True),
    )
    
    @property
    def current_price(self) -> Optional[float]:
        """Get most recent price."""
        if self.price_snapshots:
            return max(self.price_snapshots, key=lambda s: s.scraped_at).price
        return None
    
    @property
    def confidence_reasons_list(self) -> List[str]:
        """Get confidence reasons as list."""
        if self.confidence_reasons:
            try:
                return json.loads(self.confidence_reasons)
            except json.JSONDecodeError:
                return []
        return []


class PriceSnapshot(Base):
    """Historical price record."""
    __tablename__ = "price_snapshots"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    plan: Mapped["Plan"] = relationship("Plan", back_populates="price_snapshots")
    
    __table_args__ = (
        Index("ix_snapshots_plan_date", "plan_id", "scraped_at"),
    )


class ScrapeRun(Base):
    """Record of a scrape execution."""
    __tablename__ = "scrape_runs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    total_providers: Mapped[int] = mapped_column(Integer, default=0)
    successful_providers: Mapped[int] = mapped_column(Integer, default=0)
    total_plans_found: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
