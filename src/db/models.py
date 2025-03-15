from datetime import datetime
from typing import List, Optional
from sqlalchemy import ForeignKey, String, Text, DateTime, Boolean, func, Column, Integer, UniqueConstraint
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
    
    frontier_urls: Mapped[List["FrontierUrl"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    job_posting_urls: Mapped[List["JobPostingUrl"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class FrontierUrl(Base):
    """URLs that have been explored, tracking whether they contain job listings"""
    __tablename__ = "frontier_urls"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("company_urls.id"), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, default=0)  # Level where URL was found
    contains_job_listings: Mapped[bool] = mapped_column(Boolean, default=False)  # Indicates if page contains job listings
    last_visited: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.now(), 
        onupdate=func.now()
    )
    
    __table_args__ = (
        UniqueConstraint('url', 'company_id', name='uix_frontier_url_company'),
    )
     
    company: Mapped["CompanyUrl"] = relationship(back_populates="frontier_urls")
    job_posting_urls: Mapped[List["JobPostingUrl"]] = relationship(back_populates="frontier_url", cascade="all, delete-orphan")


class JobPostingUrl(Base):
    """Individual job description pages"""
    __tablename__ = "job_posting_urls"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    frontier_id: Mapped[int] = mapped_column(ForeignKey("frontier_urls.id"))  
    company_id: Mapped[int] = mapped_column(ForeignKey("company_urls.id"))  
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    job_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    job_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    extracted_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.now(), 
        onupdate=func.now()
    )
     
    frontier_url: Mapped["FrontierUrl"] = relationship(back_populates="job_posting_urls")  # Changed from target_url
    company: Mapped["CompanyUrl"] = relationship(back_populates="job_posting_urls")  # Added company relationship
    
    __table_args__ = (
        UniqueConstraint('url', 'company_id', name='uix_job_url_company'),
    )
