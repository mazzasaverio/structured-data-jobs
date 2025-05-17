from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import (
    Column,
    ForeignKey,
    String,
    Text,
    DateTime,
    Boolean,
    func,
    Integer,
    UniqueConstraint,
    event,
    JSON,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class CompanyUrl(Base):
    """Company root URLs"""

    __tablename__ = "company_urls"

    id = Column(Integer, primary_key=True)
    url = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    frontier_urls = relationship(
        "FrontierUrl", back_populates="company", cascade="all, delete-orphan"
    )
    job_posts = relationship(
        "JobPost", back_populates="company", cascade="all, delete-orphan"
    )


class FrontierUrl(Base):
    """URLs that have been explored, tracking whether they are targets (job posting URLs)"""

    __tablename__ = "frontier_urls"

    id = Column(Integer, primary_key=True)
    url_domain = Column(String(255), nullable=False)
    url = Column(String(1024), nullable=False)
    company_id = Column(Integer, ForeignKey("company_urls.id"), nullable=False)
    depth = Column(Integer, default=0)  # Level where URL was found
    is_target = Column(
        Boolean, default=False
    )  # Indicates if URL is a target (job posting)
    last_visited = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("url", "company_id", name="uix_frontier_url_company"),
    )

    company = relationship("CompanyUrl", back_populates="frontier_urls")


class JobPost(Base):
    """Job posts extracted from target URLs"""

    __tablename__ = "job_posts"

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    role = Column(String(255), nullable=False)
    url = Column(String(1024), nullable=False, unique=True)
    url_domain = Column(String(255), nullable=False)
    url_target = Column(String(1024), nullable=False)
    company_id = Column(Integer, ForeignKey("company_urls.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    company = relationship("CompanyUrl", back_populates="job_posts")


# Event listeners
@event.listens_for(FrontierUrl, "before_insert")
def populate_url_domain(mapper, connection, frontier_url):
    """Populate url_domain with the URL from the associated CompanyUrl before insert"""
    if frontier_url.company_id and not frontier_url.url_domain:
        from sqlalchemy.orm import Session

        session = Session(connection)
        company = session.get(CompanyUrl, frontier_url.company_id)
        if company:
            frontier_url.url_domain = company.url


@event.listens_for(FrontierUrl, "before_update")
def update_url_domain(mapper, connection, frontier_url):
    """Update url_domain if company_id changes"""
    if (
        hasattr(frontier_url, "_sa_instance_state")
        and frontier_url._sa_instance_state.attrs.get(
            "company_id"
        ).history.has_changes()
    ):
        from sqlalchemy.orm import Session

        session = Session(connection)
        company = session.get(CompanyUrl, frontier_url.company_id)
        if company:
            frontier_url.url_domain = company.url
