from datetime import datetime
from typing import List, Optional
from sqlalchemy import ForeignKey, String, Text, DateTime, Boolean, func, Column, Integer, UniqueConstraint, event
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
    job_posts: Mapped[List["JobPost"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class FrontierUrl(Base):
    """URLs that have been explored, tracking whether they are targets (job posting URLs)"""
    __tablename__ = "frontier_urls"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    url_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("company_urls.id"), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, default=0)  # Level where URL was found
    is_target: Mapped[bool] = mapped_column(Boolean, default=False)  # Indicates if URL is a target (job posting)
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


class JobPost(Base):
    """Job posts extracted from target URLs"""
    __tablename__ = "job_posts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    url_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    url_target: Mapped[str] = mapped_column(String(1024), nullable=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("company_urls.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.now(), 
        onupdate=func.now()
    )
    
    company: Mapped["CompanyUrl"] = relationship(back_populates="job_posts")


# SQLAlchemy event listener to populate url_domain with the company's url
@event.listens_for(FrontierUrl, 'before_insert')
def populate_url_domain(mapper, connection, frontier_url):
    """Populate url_domain with the URL from the associated CompanyUrl before insert"""
    if frontier_url.company_id and not frontier_url.url_domain:
        # Get the company's URL from the session
        from sqlalchemy.orm import Session
        session = Session(connection)
        company = session.get(CompanyUrl, frontier_url.company_id)
        if company:
            frontier_url.url_domain = company.url


# Event listener for relationship changes - updates url_domain if company_id changes
@event.listens_for(FrontierUrl, 'before_update')
def update_url_domain(mapper, connection, frontier_url):
    """Update url_domain if company_id changes"""
    if hasattr(frontier_url, '_sa_instance_state') and frontier_url._sa_instance_state.attrs.get('company_id').history.has_changes():
        from sqlalchemy.orm import Session
        session = Session(connection)
        company = session.get(CompanyUrl, frontier_url.company_id)
        if company:
            frontier_url.url_domain = company.url
