from datetime import datetime
from typing import List, Optional
from sqlalchemy import ForeignKey, String, Text, DateTime, Boolean, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


class CompanyUrl(Base):
    """Company root URLs"""
    __tablename__ = "company_urls"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.now(), 
        onupdate=func.now()
    )
    
    # Relationships
    frontier_urls: Mapped[List["Frontier"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    target_urls: Mapped[List["TargetUrl"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class Frontier(Base):
    """URLs that have already been explored and shouldn't be crawled again"""
    __tablename__ = "frontier"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company_urls.id"))
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    last_crawled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Relationships
    company: Mapped["CompanyUrl"] = relationship(back_populates="frontier_urls")


class TargetUrl(Base):
    """Pages containing job posting listings"""
    __tablename__ = "target_urls"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company_urls.id"))
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.now(), 
        onupdate=func.now()
    )
    
    # Relationships
    company: Mapped["CompanyUrl"] = relationship(back_populates="target_urls")
    job_posting_urls: Mapped[List["JobPostingUrl"]] = relationship(back_populates="target_url", cascade="all, delete-orphan")


class JobPostingUrl(Base):
    """Individual job description pages"""
    __tablename__ = "job_posting_urls"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    target_url_id: Mapped[int] = mapped_column(ForeignKey("target_urls.id"))
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.now(), 
        onupdate=func.now()
    )
    
    # Relationships
    target_url: Mapped["TargetUrl"] = relationship(back_populates="job_posting_urls")
