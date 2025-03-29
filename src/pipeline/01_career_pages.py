import os
import sys

# Aggiungi la directory principale al sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import logfire
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.models import CompanyUrl, FrontierUrl
from src.db.connection import get_db_session
import re
from src.pipeline.career_validator import CareerPageValidator
from sqlalchemy.exc import SQLAlchemyError, OperationalError, IntegrityError

# Import needed for sitemap exploration
import aiohttp
from urllib.parse import urlparse

from src.utils.logging import setup_logging

setup_logging(service_name="career-crawler")            

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
        """Find career page using multiple strategies in optimal order."""

        base_url = page.url.rstrip('/')
        parsed_url = urlparse(base_url)
        domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # =============== STRATEGY 1: Direct URL Probing ===============
        common_career_paths = [
            "/careers", "/careers/", "/jobs", "/jobs/", "/en/careers", "/en/careers/", 
            "/join-us", "/work-with-us", "/about/careers",
            "/company/careers", "/join", "/opportunities", "/company/jobs", "/team","/lavora-con-noi",
            "/about/jobs", "/about-us/careers", "/about-us/jobs",
            "/it/careers", "/it/jobs", "/it/carriere", "/it/carriere/", "/it/jobs/", "/it/careers/",
            "/lavora-con-noi", "/opportunita", "/carriere"
        ]
        
        for path in common_career_paths:
            try:
                url = f"{domain}{path}"
                response = await page.goto(url, wait_until="domcontentloaded", timeout=5000)
                
                # Check if page exists (status code 200)
                if response and response.status == 200:
                    return url
                
            except Exception as e:
                logfire.debug(f"Error probing URL {path}", error=str(e))
        
         
    async def extract_page_text(self, page: Page) -> str:
        """
        Extract links from the page with their text, context, and potential content description.
        Also includes the full text content of the page.
        """
        # Get the page URL and title
        page_url = page.url
        title = await page.title()
        
        # Start building the structured representation
        structured_content = [
            f"PAGE ANALYSIS: {title}",
            f"URL: {page_url}",
            "\n=== FULL PAGE TEXT ===\n"
        ]
        
        # Extract full page text content
        full_text = await page.evaluate("""() => {
            return document.body.innerText;
        }""")
        
        structured_content.append(full_text)
        structured_content.append("\n=== LINKS ANALYSIS ===\n")
        
        # Extract all links on the page with their context
        all_links = await page.locator("a").all()
        if all_links:
            for link in all_links:
                try:
                    # Get link text and URL
                    link_text = (await link.text_content() or "").strip()
                    href = await link.get_attribute("href") or ""
                    
                    # Skip empty, javascript, and mailto links
                    if not href or href == "#" or href.startswith("javascript:") or href.startswith("mailto:"):
                        continue
                    
                    # Normalize URL
                    if not href.startswith("http"):
                        if href.startswith("/"):
                            parsed_url = urlparse(page_url)
                            href = f"{parsed_url.scheme}://{parsed_url.netloc}{href}"
                        else:
                            href = f"{page_url.rstrip('/')}/{href.lstrip('/')}"
                    
                    # Try to get some context
                    context = ""
                    try:
                        # Get parent element's information for context
                        context = await link.evaluate("""el => {
                            const parent = el.parentElement;
                            if (parent) {
                                // Find which section this link belongs to
                                const section = parent.closest('header, nav, main, section, footer, aside');
                                const sectionName = section ? section.tagName.toLowerCase() : 'unknown';
                                
                                // Check for common patterns indicating job listings
                                const isJobLink = (
                                    el.textContent.toLowerCase().includes('job') || 
                                    el.textContent.toLowerCase().includes('position') || 
                                    el.href.toLowerCase().includes('job') ||
                                    el.href.toLowerCase().includes('career') ||
                                    el.closest('.job-list, .jobs, .positions, .vacancies')
                                );
                                
                                // Get some surrounding text for context
                                let surroundingText = '';
                                const container = el.closest('li, div, article, section') || parent;
                                if (container && container !== el) {
                                    surroundingText = container.textContent.substring(0, 200);
                                }
                                
                                return {
                                    tag: parent.tagName.toLowerCase(),
                                    section: sectionName,
                                    possibleJobListing: isJobLink,
                                    text: surroundingText
                                };
                            }
                            return null;
                        }""")
                    except:
                        pass
                    
                    if context:
                        section_name = context.get("section", "unknown")
                        parent_tag = context.get("tag", "")
                        is_job_link = context.get("possibleJobListing", False)
                        surrounding_text = context.get("text", "").replace(link_text, f"[{link_text}]").strip()
                        
                        structured_content.append(f"• LINK: {link_text} → {href}")
                        structured_content.append(f"  CONTEXT: In {section_name}/{parent_tag}")
                        if is_job_link:
                            structured_content.append(f"  POTENTIAL JOB LISTING: Yes")
                        if surrounding_text:
                            structured_content.append(f"  SURROUNDING TEXT: {surrounding_text[:150]}...")
                    else:
                        structured_content.append(f"• LINK: {link_text} → {href}")
                except Exception as e:
                    logfire.debug(f"Error extracting link context", error=str(e))
        
        return "\n".join(structured_content)
    
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
            
            logfire.info(f"Found career page: {career_url}")
            
            # If no career page found, use the domain URL
            if career_url is None:
                parsed_url = urlparse(company.url)
                domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
                career_url = domain
                logfire.info(f"No specific career page found, using domain: {domain}")
                
                # Check if this domain URL already exists in frontier
                existing_entry = await session.execute(
                    select(FrontierUrl).where(
                        FrontierUrl.company_id == company.id,
                        (FrontierUrl.url == domain) | (FrontierUrl.url_domain == domain)
                    )
                )
                existing_entry = existing_entry.scalars().first()
                
                if not existing_entry:
                    career_frontier = FrontierUrl(
                        company_id=company.id,
                        url_domain=domain,
                        url="", 
                        depth=1,
                        is_target=False,
                        last_visited=datetime.now()
                    )
                    session.add(career_frontier)
                    await session.commit()
                    logfire.info(f"Added new frontier URL: {career_url}")
           
                else:
                    logfire.info(f"Domain URL already exists in frontier: {domain}")
                    # Skip further processing if we're just using the domain
                    return
            
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

            # Save page text and links to file
            safe_filename = re.sub(r'[^\w\-_]', '_', company.name)
            text_file_path = self.output_dir / f"{safe_filename}_page_text.txt"
            with open(text_file_path, "w", encoding="utf-8") as f:
                f.write(f"URL: {career_url}\n\n")
                f.write(page_text)
                
            logfire.info(f"Saved page text and links to file", file_path=str(text_file_path))

            # Use LLM to determine if this page is a target (contains a LIST of job postings)
            is_target, suggested_urls = await self.validator.analyze_career_page(
                page_text=page_text,
                page_url=career_url,
            )

            if existing_career:
                # Update existing record
                existing_career.is_target = is_target
                existing_career.last_visited = datetime.now()
                logfire.info(f"Updated existing frontier URL: {career_url}")
            else:
                # Only create a new record if we haven't already created one for this URL
                # (this prevents duplicates when career_url == domain)
                existing_record = await session.execute(
                    select(FrontierUrl).where(
                        FrontierUrl.company_id == company.id,
                        FrontierUrl.url == career_url
                    )
                )
                existing_record = existing_record.scalars().first()
                
                if not existing_record:
                    career_frontier = FrontierUrl(
                        company_id=company.id,
                        url=career_url,
                        depth=1,
                        is_target=is_target,
                        last_visited=datetime.now()
                    )
                    session.add(career_frontier)
                    logfire.info(f"Added new frontier URL: {career_url}")
                else:
                    logfire.info(f"URL already exists in frontier: {career_url}")
            
            await session.flush()
            
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
                        
                        # Save suggested page text to file
                        safe_company_name = re.sub(r'[^\w\-_]', '_', company.name)
                        safe_url = re.sub(r'[^\w\-_]', '_', suggested_url.split('/')[-1])[:50]
                        suggestion_file_path = self.output_dir / f"{safe_company_name}_suggested_{safe_url}_text.txt"
                        with open(suggestion_file_path, "w", encoding="utf-8") as f:
                            f.write(f"URL: {suggested_url}\n\n")
                            f.write(suggestion_text)
                        
                        logfire.info(f"Saved suggested page text to file", file_path=str(suggestion_file_path))
                      
                        is_suggested_target, _ = await self.validator.analyze_career_page(
                            page_text=suggestion_text,
                            page_url=suggested_url,
                         
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

        finally:
            await context.close()
    
    async def run(self) -> None:
        """Run crawler on all companies in database."""

        browser, context = await self.setup_browser()
        
        try:
            async with get_db_session() as session:
                # First, check for broken target URLs and remove them
                target_urls = await session.execute(
                    select(FrontierUrl).where(FrontierUrl.is_target == True)
                )
                target_urls = target_urls.scalars().all()
                
                # Track companies that had broken targets so we can process them again
                companies_with_broken_targets = set()
                
                for target_url in target_urls:
                    try:
                        # Check if URL is broken
                        response = None
                        try:
                            page = await context.new_page()
                            response = await page.goto(target_url.url, timeout=30000, wait_until="domcontentloaded")
                            await page.close()
                        except Exception as e:
                            logfire.warning(f"Failed to access target URL", url=target_url.url, error=str(e))
                            response = None
                        
                        # If URL is broken (no response or error status)
                        if response is None or response.status >= 400:
                            logfire.info(f"Found broken target URL - deleting", url=target_url.url)
                            companies_with_broken_targets.add(target_url.company_id)
                            await session.delete(target_url)
                            await session.flush()
                    except Exception as e:
                        logfire.error(f"Error checking target URL", url=target_url.url, error=str(e))
                
                # Subquery to find companies that have at least one VALID target URL
                companies_with_targets = select(FrontierUrl.company_id).where(
                    FrontierUrl.is_target == True
                ).distinct().scalar_subquery()
                
                # Main query to find companies without any target URLs
                # or companies that had broken targets
                result = await session.execute(
                    select(CompanyUrl).where(
                        CompanyUrl.id.not_in(companies_with_targets) | 
                        CompanyUrl.id.in_(list(companies_with_broken_targets))
                    )
                )
                companies = result.scalars().all()
                
                logfire.info(f"Found {len(companies)} companies to process (without targets or with broken targets)")

                for company in companies:
                    try:
                        logfire.info(f"Processing company: {company.name}", url=company.url)
                        await self.process_company(company, browser, session)
                    except Exception as e:
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
    try:
        asyncio.run(run_career_crawler())
    finally:
        # Pulizia esplicita delle risorse del loop di eventi
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.stop()
        if not loop.is_closed():
            loop.close()