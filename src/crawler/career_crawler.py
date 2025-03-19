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
from sqlalchemy.exc import SQLAlchemyError, OperationalError, IntegrityError
import traceback

# Import needed for sitemap exploration
import aiohttp
from urllib.parse import urlparse

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
        """Find career page using multiple strategies in optimal order."""
        # Get domain information
        base_url = page.url.rstrip('/')
        parsed_url = urlparse(base_url)
        domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # =============== STRATEGY 1: Direct URL Probing ===============
        logfire.info("Trying direct URL probing for career pages")
        common_career_paths = [
            "/careers", "/careers/", "/jobs", "/jobs/", "/en/careers", "/en/careers/", 
            "/join-us", "/work-with-us", "/about/careers",
            "/company/careers", "/join", "/opportunities", "/company/jobs", "/team","/lavora-con-noi",
            "/about/jobs", "/about-us/careers", "/about-us/jobs",
            "/it/careers", "/it/jobs",
            "/lavora-con-noi", "/opportunita", "/carriere"
        ]
        
        for path in common_career_paths:
            try:
                url = f"{domain}{path}"
                logfire.debug(f"Trying URL: {url}")
                
                # Navigate to the potential career page with a short timeout
                response = await page.goto(url, wait_until="domcontentloaded", timeout=5000)
                
                # Check if page exists (status code 200)
                if response and response.status == 200:
                    # Verify it's actually a career page by looking for job-related terms
                    content = await page.content()
                    job_terms = ["job", "position", "opening", "career", "opportunity", 
                               "team", "hiring", "recruit", "join"]
                    
                    if any(term in content.lower() for term in job_terms):
                        logfire.info(f"Found career page by direct URL: {url}")
                        return url
            except Exception as e:
                logfire.debug(f"Error probing URL {path}", error=str(e))
        
        # Return to home page for next strategies
        await page.goto(base_url, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        
        # =============== STRATEGY 2: Simple Text Matching ===============
        logfire.info("Trying simple text matching for career links")
        career_link_texts = [
            "careers", "jobs", "work with us", "join us", "join our team", 
            "open positions", "we're hiring", "lavora con noi", "opportunità",
            "join", "recruiting", "carriere", "career", "job"
        ]
        
        for text in career_link_texts:
            try:
                link_selector = f"a:text-matches('{text}', 'i')"
                if await page.locator(link_selector).count() > 0:
                    link = page.locator(link_selector).first
                    href = await link.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"{domain}{href}"
                        logfire.info(f"Found career link via text match: {full_url}")
                        return full_url
            except Exception as e:
                logfire.debug(f"Error in text matching for '{text}'", error=str(e))
        
        # =============== STRATEGY 3: Sitemap Exploration ===============
        logfire.info("Checking sitemap for career pages")
        try:
            sitemap_url = f"{domain}/sitemap.xml"
            async with aiohttp.ClientSession() as client_session:
                async with client_session.get(sitemap_url, timeout=5) as response:
                    if response.status == 200:
                        sitemap_text = await response.text()
                        career_patterns = ["career", "job", "join", "opportunit", "work-with"]
                        
                        import re
                        for pattern in career_patterns:
                            # Look for URLs containing career-related terms
                            matches = re.findall(rf'<loc>(https?://[^<]+{pattern}[^<]*)</loc>', sitemap_text, re.IGNORECASE)
                            for match in matches:
                                try:
                                    await page.goto(match, wait_until="domcontentloaded", timeout=5000)
                                    logfire.info(f"Found potential career page via sitemap: {match}")
                                    return match
                                except Exception:
                                    continue
        except Exception as e:
            logfire.debug(f"Error exploring sitemap", error=str(e))
        
        # Return to home page for next strategies
        await page.goto(base_url, wait_until="domcontentloaded")
        
        # =============== STRATEGY 4: Primary Navigation ===============
        logfire.info("Exploring primary navigation")
        nav_selectors = [
            "nav", "header", ".header", ".navigation", ".main-menu", 
            ".navbar", ".nav-menu", "#main-menu"
        ]
        
        for selector in nav_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    nav_element = page.locator(selector).first
                    
                    # Search for career-related links in the navigation
                    for text in career_link_texts:
                        try:
                            link = nav_element.locator(f"a:text-matches('{text}', 'i')").first
                            if await link.count() > 0:
                                href = await link.get_attribute("href")
                                if href:
                                    full_url = href if href.startswith("http") else f"{domain}{href}"
                                    logfire.info(f"Found career link in primary navigation: {full_url}")
                                    return full_url
                        except Exception:
                            continue
            except Exception as e:
                logfire.debug(f"Error exploring navigation {selector}", error=str(e))
        
        # =============== STRATEGY 5: Footer and Secondary Areas ===============
        logfire.info("Checking footer and secondary areas")
        secondary_selectors = [
            "footer", ".footer", "#footer", ".bottom", ".secondary-menu",
            ".links", ".site-links", ".meta-links"
        ]
        
        for selector in secondary_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    element = page.locator(selector).first
                    
                    # Check for career links
                    for text in career_link_texts:
                        try:
                            link = element.locator(f"a:text-matches('{text}', 'i')").first
                            if await link.count() > 0:
                                href = await link.get_attribute("href")
                                if href:
                                    full_url = href if href.startswith("http") else f"{domain}{href}"
                                    logfire.info(f"Found career link in secondary area: {full_url}")
                                    return full_url
                        except Exception:
                            continue
            except Exception as e:
                logfire.debug(f"Error exploring secondary area {selector}", error=str(e))
        
        # =============== STRATEGY 6: Interactive Navigation ===============
        logfire.info("Trying interactive navigation elements")
        interactive_selectors = [
            "a:has-text('Company')", "a:has-text('About')", "a:has-text('About us')",
            "button:has-text('Menu')", "[aria-label='menu']", ".menu-toggle",
            ".dropdown", "nav .has-submenu", ".header-menu"
        ]
        
        for selector in interactive_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    logfire.info(f"Clicking interactive element: {selector}")
                    await page.locator(selector).first.click()
                    await page.wait_for_timeout(1000)  # Wait for animation
                    
                    # Now look for career links in the expanded menu
                    for text in career_link_texts:
                        try:
                            link = page.locator(f"a:text-matches('{text}', 'i')").first
                            if await link.count() > 0:
                                href = await link.get_attribute("href")
                                if href:
                                    full_url = href if href.startswith("http") else f"{domain}{href}"
                                    logfire.info(f"Found career link after interaction: {full_url}")
                                    return full_url
                        except Exception:
                            continue
            except Exception as e:
                logfire.debug(f"Error with interactive element {selector}", error=str(e))
        
        # =============== STRATEGY 7: Search Function ===============
        logfire.info("Trying site search if available")
        search_selectors = [
            "input[type='search']", ".search-input", "input[placeholder*='search' i]",
            "[aria-label='Search']", ".search-form input", "#search"
        ]
        
        for selector in search_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    search_input = page.locator(selector).first
                    await search_input.fill("careers")
                    await search_input.press("Enter")
                    await page.wait_for_load_state("networkidle")
                    
                    # Look for career-related links in the search results
                    for text in career_link_texts:
                        try:
                            link = page.locator(f"a:text-matches('{text}', 'i')").first
                            if await link.count() > 0:
                                href = await link.get_attribute("href")
                                if href:
                                    full_url = href if href.startswith("http") else f"{domain}{href}"
                                    logfire.info(f"Found career link via search: {full_url}")
                                    return full_url
                        except Exception:
                            continue
            except Exception as e:
                logfire.debug(f"Error using search function", error=str(e))
        
        # If we get here, no career page was found after all attempts
        logfire.warning("No career link found after all attempts")
        return None
    
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
                # Create new record
                career_frontier = FrontierUrl(
                    company_id=company.id,
                    url=career_url,
                    depth=1,
                    is_target=is_target,
                    last_visited=datetime.now()
                )
                session.add(career_frontier)
                logfire.info(f"Added new frontier URL: {career_url}")
            
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
                # Subquery to find companies that have at least one target URL
                companies_with_targets = select(FrontierUrl.company_id).where(
                    FrontierUrl.is_target == True
                ).distinct().scalar_subquery()
                
                # Main query to find companies without any target URLs
                result = await session.execute(
                    select(CompanyUrl).where(
                        CompanyUrl.id.not_in(companies_with_targets)
                    )
                )
                companies = result.scalars().all()
                
                logfire.info(f"Found {len(companies)} companies without target job pages to process")

                for company in companies:
                    try:
                        logfire.info(f"Processing company: {company.name}", url=company.url)
                        await self.process_company(company, browser, session)
                        await session.commit()
                    except Exception as e:
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
