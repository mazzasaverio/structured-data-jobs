import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import logfire
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import CompanyUrl, FrontierUrl
from src.db.connection import get_db_session
from src.utils.logging import log_span
import re
from src.crawler.career_validator import CareerPageValidator


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
        try:
            self.validator = CareerPageValidator()
        except Exception as e:
            logfire.error("Failed to initialize CareerPageValidator", error=str(e))
            raise  # Re-raise to prevent crawler from starting with invalid config
    
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
    
    async def extract_page_links(self, page: Page) -> List[dict]:
        """Extract all links from a page."""
        links = await page.query_selector_all('a')
        result = []
        
        for link in links:
            try:
                href = await link.get_attribute('href') or ''
                if not href or href == '#' or href.startswith('javascript:') or href.startswith('mailto:'):
                    continue
                    
                text = (await link.text_content() or '').strip()
                
                # Normalize relative URLs
                if not href.startswith('http'):
                    base_url = page.url
                    if href.startswith('/'):
                        domain_parts = base_url.split('/')
                        if len(domain_parts) >= 3:
                            href = f"{domain_parts[0]}//{domain_parts[2]}{href}"
                    else:
                        href = f"{base_url.rstrip('/')}/{href.lstrip('/')}"
                
                result.append({"url": href, "text": text})
            except Exception as e:
                logfire.warning(f"Error extracting link", error=str(e))
        
        return result
    
    async def process_company(self, company: CompanyUrl, browser: Browser, session: AsyncSession) -> None:
        """Process a single company to find its career page."""
        logfire.info(f"Processing company: {company.name}", url=company.url)
        
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Visit company homepage (level 0)
            await page.goto(company.url, timeout=60000, wait_until="domcontentloaded")
         
            career_url = await self.find_career_link(page)
            
            if not career_url:
                logfire.warning(f"No career link found", company=company.name)
                return
                
            logfire.info(f"Found career page: {career_url}")
            
            # Visit career page and extract text
            await page.goto(career_url, timeout=60000, wait_until="domcontentloaded")
            
                        # Check if career URL already exists in frontier
            existing_career = await session.execute(
                select(FrontierUrl).where(
                    FrontierUrl.company_id == company.id,
                    FrontierUrl.url == career_url
                )
            )
            existing_career = existing_career.scalars().first()

         
            # Extract text and links
            page_text = await self.extract_page_text(page)
            page_links = await self.extract_page_links(page)
            logfire.info(f"Found {len(page_links)} links on career page")
            
            # Use LLM to determine if this page is a target (contains a LIST of job postings)
            is_target, suggested_urls = await self.validator.analyze_career_page(
                page_text=page_text,
                page_url=career_url,
                page_links=page_links
            )

            career_frontier = FrontierUrl(
                company_id=company.id,
                url=career_url,
                depth=1,
                is_target=is_target,  # The LLM determines if this is a target
                last_visited=datetime.now()
            )
            session.add(career_frontier)
            await session.flush()
            
            # Save text to file for reference
            filename = f"{company.name.replace(' ', '_').lower()}_career_page.txt"
            file_path = self.output_dir / filename
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(page_text)
                f.write("\n\n--- LINKS FOUND ON THIS PAGE ---\n\n")
                for link in page_links:
                    f.write(f"{link['text']} -> {link['url']}\n")
            
            logfire.info(f"Saved career page text with {len(page_links)} links", file=str(file_path))
            
            # If not a target but has suggested URLs, add them to frontier
            if not is_target and suggested_urls:
                logfire.info(f"LLM suggests exploring these URLs:", urls=suggested_urls)
                
                
                # Visit each suggested URL to check if it's a target
                for suggestion in suggested_urls:
                    suggested_url = suggestion.get('url')
                    if not suggested_url:
                        continue
                        
                    try:
                        logfire.info(f"Checking suggested URL: {suggested_url}")
                        await page.goto(suggested_url, timeout=60000, wait_until="domcontentloaded")
                        
                        # Extract and analyze
                        suggestion_text = await self.extract_page_text(page)
                        suggestion_links = await self.extract_page_links(page)
                        
                        is_suggested_target, _ = await self.validator.analyze_career_page(
                            page_text=suggestion_text,
                            page_url=suggested_url,
                            page_links=suggestion_links
                        )
                        
                        # Update frontier entry
                        frontier_entry = await session.execute(
                            select(FrontierUrl).where(
                                FrontierUrl.company_id == company.id,
                                FrontierUrl.url == suggested_url
                            )
                        )
                        frontier_entry = frontier_entry.scalars().first()
                        
                        if frontier_entry:
                            frontier_entry.is_target = is_suggested_target
                            frontier_entry.last_visited = datetime.now()
                            await session.flush()
                        else:
                            logfire.warning(f"Suggested URL not found in frontier", url=suggested_url)
                            # Add to frontier with is_target=False (we'll check it later)
                            new_frontier = FrontierUrl(
                                company_id=company.id,
                                url=suggested_url,
                                depth=1,  
                                is_target=is_suggested_target,  
                                last_visited=None  
                            )
                            session.add(new_frontier)
                            logfire.info(f"Added suggested URL to frontier", url=suggested_url)

                        await session.flush()
                            
                            
                    except Exception as e:
                        logfire.error(f"Error checking suggested URL", 
                                     url=suggested_url,
                                     error=str(e))
            
            if is_target:
                logfire.info("Career page is a target (contains a list of job postings)", url=career_url)
            else:
                logfire.info("Career page is not a target", url=career_url)
            
        except Exception as e:
            import traceback
            logfire.error("Error processing company", 
                         company=company.name, 
                         url=company.url,
                         error=str(e),
                         traceback=traceback.format_exc())
            # Don't raise - let the caller handle the session
        
        finally:
            await context.close()
    
    async def run(self) -> None:
        """Run crawler on all companies in database."""
        logfire.info("Starting career crawler")
        
        browser, context = await self.setup_browser()
        
        try:
            # Use a single session for the whole run
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
                    try:
                        # Process company with the shared session
                        await self.process_company(company, browser, session)
                        # Commit after each company to save progress
                        await session.commit()
                    except Exception as e:
                        # If there's an error with one company, rollback and continue with the next
                        await session.rollback()
                        import traceback
                        logfire.error(f"Error processing company", 
                                     company=company.name,
                                     error=str(e),
                                     traceback=traceback.format_exc())
        
        except Exception as e:
            import traceback
            logfire.error(f"Crawler error", 
                        error=str(e),
                        traceback=traceback.format_exc())
        
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
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch()
        context = await browser.new_context()
        page = await context.new_page()
        
        crawler = CareerCrawler()
        await crawler.run()
        
    finally:
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
