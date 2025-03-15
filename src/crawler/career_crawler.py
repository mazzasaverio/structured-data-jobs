import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import logfire
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import CompanyUrl, FrontierUrl, JobPostingUrl
from src.db.connection import get_db_session
from src.utils.logging import  log_span
import re


# Career-related terms in English and Italian
CAREER_TERMS = [
    "career", "careers", "jobs", "job", "work with us", "join us", "join our team",
    "lavora con noi", "carriere", "opportunità", "opportunita", "lavoro", "posizioni aperte"
]

class CareerCrawler:
    """Crawler for finding career pages on company websites."""
    
    def __init__(self, output_dir: str = "output/career_pages"):
        """Initialize crawler with output directory."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def setup_browser(self) -> Tuple[Browser, BrowserContext]:
        """Set up Playwright browser and context."""
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        return browser, context
    
    async def find_career_link(self, page: Page) -> Optional[str]:
        """Find career/jobs link on a company homepage."""
        links = await page.query_selector_all('a')
        
        for link in links:
            href = await link.get_attribute('href') or ''
            if not href or href == '#' or href.startswith('javascript:') or href.startswith('mailto:'):
                continue
            
            text = (await link.text_content() or '').lower().strip()
            aria_label = (await link.get_attribute('aria-label') or '').lower().strip()
            title = (await link.get_attribute('title') or '').lower().strip()
            
            for term in CAREER_TERMS:
                if (term in text or term in aria_label or term in title):
                    if href.startswith('http'):
                        return href
                    else:
                        base_url = page.url
                        if href.startswith('/'):
                            domain_parts = base_url.split('/')
                            if len(domain_parts) >= 3:
                                return f"{domain_parts[0]}//{domain_parts[2]}{href}"
                        else:
                            return f"{base_url.rstrip('/')}/{href.lstrip('/')}"
                        
                        
        
        logfire.info("No career link found")
        return None
    
    async def extract_page_text(self, page: Page) -> str:
        """Extract all text content from a page."""
        return await page.evaluate("() => document.body.innerText")
    
    async def validate_career_page(self, text: str) -> bool:
        """Simple validation if page contains job listings."""
        job_terms = [
            "apply now", "job description", "responsibilities", "requirements",
            "qualifications", "full-time", "part-time", "candidate", "position",
            "candidati ora", "descrizione del lavoro", "responsabilità", "requisiti", 
            "qualifiche", "tempo pieno", "tempo parziale"
        ]
        
        for term in job_terms:
            if term in text.lower():
                return True
        
        return False
    
    async def process_company(self, company: CompanyUrl, session: AsyncSession, browser: Browser) -> None:
        """Process a single company to find its career page."""
        logfire.info(f"Processing company: {company.name}", url=company.url)
        
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Visit company homepage (level 0)
            await page.goto(company.url, timeout=60000, wait_until="domcontentloaded")
            
            # Record URL as visited
            frontier_url = FrontierUrl(
                company_id=company.id,
                url=company.url,
                last_crawled_at=datetime.now()
            )
            session.add(frontier_url)
            
            # Find career link
            career_url = await self.find_career_link(page)
            
            if career_url:
                logfire.info(f"Found career page", company=company.name, url=career_url)
                
                # Level 1: Visit career page and extract text
                await page.goto(career_url, timeout=60000, wait_until="domcontentloaded")
                
                # Extract text
                page_text = await self.extract_page_text(page)
                
                # Save text to file
                filename = f"{company.name.replace(' ', '_').lower()}_career_page.txt"
                file_path = self.output_dir / filename
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(page_text)
                
                logfire.info(f"Saved career page text", file=str(file_path))
                
                # Simple validation
                is_valid = await self.validate_career_page(page_text)
                
                # Check if URL exists in database
                existing_target = await session.execute(
                    select(FrontierUrl).where(
                        FrontierUrl.company_id == company.id,
                        FrontierUrl.url == career_url
                    )
                )
                existing_target = existing_target.scalars().first()
                
                if is_valid:
                    if not existing_target:
                        # Store career URL in database
                        frontier_url = FrontierUrl(
                            company_id=company.id,
                            url=career_url,
                            depth=1,
                            contains_job_listings=True,
                            last_visited=datetime.now()
                        )
                        session.add(frontier_url)
                    else:
                        # Update last crawled timestamp
                        existing_target.contains_job_listings = True
                        existing_target.last_visited = datetime.now()
                else:
                    logfire.info("Page doesn't appear to contain job listings", url=career_url)
                
                # Add to frontier
                frontier_url = FrontierUrl(
                    company_id=company.id,
                    url=career_url,
                    last_crawled_at=datetime.now()
                )
                session.add(frontier_url)
                await session.commit()
            
            else:
                logfire.warning(f"No career page found", company=company.name)
                await session.commit()
        
        except Exception as e:
            logfire.error(f"Error processing company", company=company.name, error=str(e))
        
        finally:
            await context.close()
    
    async def run(self) -> None:
        """Run crawler on all companies in database."""
        logfire.info("Starting career crawler")
        
        browser, context = await self.setup_browser()
        
        try:
            async with get_db_session() as session:
                # Get all companies
                result = await session.execute(select(CompanyUrl))
                companies = result.scalars().all()
                
                if not companies:
                    logfire.warning("No companies found in database")
                    return
                
                logfire.info(f"Found {len(companies)} companies to process")
                
                # Process each company
                for company in companies:
                    await self.process_company(company, session, browser)
        
        except Exception as e:
            logfire.error(f"Crawler error", error=str(e))
        
        finally:
            await context.close()
            await browser.close()
            logfire.info("Career crawler completed")

async def run_career_crawler():
    """Run the career crawler."""
    playwright = None
    browser = None
    context = None
    page = None
    
    try:
        # Start playwright and launch browser
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch()
        context = await browser.new_context()
        page = await context.new_page()
        
        crawler = CareerCrawler()
        await crawler.run()
        
    finally:
        # Close everything in reverse order with explicit error handling
        if page:
            try:
                await page.close()
            except:
                pass
                
        if context:
            try:
                await context.close()
            except:
                pass
                
        if browser:
            try:
                await browser.close()
            except:
                pass
                
        if playwright:
            try:
                await playwright.stop()
            except:
                pass

if __name__ == "__main__":
    asyncio.run(run_career_crawler())
