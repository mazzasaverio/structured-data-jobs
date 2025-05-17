import asyncio
import logfire
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.models import CompanyUrl, FrontierUrl


class CareerCrawler:
    """Crawler for finding career pages on company websites."""

    def __init__(self, output_dir: str = "data/output"):
        """Initialize crawler with output directory."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def setup_browser(self) -> Tuple[Browser, BrowserContext]:
        """Set up Playwright browser and context."""
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        )
        return browser, context

    async def find_career_link(self, url: str) -> Optional[str]:
        """Find career page using multiple strategies in optimal order."""

        parsed_url = urlparse(url.rstrip("/"))
        domain = f"{parsed_url.scheme}://{parsed_url.netloc}"

        # =============== STRATEGY 1: Direct URL Probing ===============
        common_career_paths = [
            "/careers",
            "/careers/",
            "/jobs",
            "/jobs/",
            "/en/careers",
            "/en/careers/",
            "/join-us",
            "/work-with-us",
            "/about/careers",
            "/company/careers",
            "/join",
            "/opportunities",
            "/company/jobs",
            "/team",
            "/lavora-con-noi",
            "/about/jobs",
            "/about-us/careers",
            "/about-us/jobs",
            "/it/careers",
            "/it/jobs",
            "/it/carriere",
            "/it/carriere/",
            "/it/jobs/",
            "/it/careers/",
            "/lavora-con-noi",
            "/opportunita",
            "/carriere",
            "/en/company/careers",
            "/en/company/jobs",
            "/en/about/careers",
        ]

        # Create a new page for URL checking
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        )
        page = await context.new_page()

        try:
            # Try Strategy 1: Direct URL Probing
            for path in common_career_paths:
                try:
                    check_url = f"{domain}{path}"
                    logfire.debug(f"Probing URL: {check_url}")
                    response = await page.goto(
                        check_url, wait_until="domcontentloaded", timeout=5000
                    )

                    # Check if page exists (status code 200)
                    if response and response.status == 200:
                        logfire.info(f"Direct probing found working URL: {check_url}")
                        return check_url

                except Exception as e:
                    logfire.debug(f"Error probing URL {path}", error=str(e))

            # =============== STRATEGY 2: Link Text Analysis ===============
            logfire.info("Strategy 1 failed, trying Strategy 2: Link Analysis")

            # Keywords that might indicate career pages (in English and Italian)
            career_keywords = [
                "career",
                "careers",
                "jobs",
                "join us",
                "work with us",
                "join our team",
                "opportunities",
                "employment",
                "vacancies",
                "job openings",
                "open positions",
                "lavora con noi",
                "opportunità",
                "carriere",
                "posizioni aperte",
                "lavoro",
                "unisciti a noi",
                "join",
                "team",
                "hiring",
                "work for us",
            ]

            # Career-related paths in URLs
            career_paths = [
                "career",
                "careers",
                "jobs",
                "join",
                "lavora",
                "carriere",
                "company/careers",
                "about/careers",
                "en/company/careers",
                "en/careers",
            ]

            # Navigate to the main company page with a longer timeout
            try:
                logfire.info(f"Navigating to main page: {url}")
                await page.goto(url, wait_until="networkidle", timeout=15000)

                # Wait for dynamic content to load
                await page.wait_for_timeout(2000)

                # Extract all links from the page
                links = await page.query_selector_all("a")
                logfire.info(f"Found {len(links)} links on the page")

                # Check for career links by href
                for link in links:
                    try:
                        href = await link.get_attribute("href")
                        if not href:
                            continue

                        href_lower = href.lower()

                        # Check if URL path contains career indicators
                        if any(path in href_lower for path in career_paths):
                            text = (await link.text_content() or "").strip()
                            logfire.info(
                                f"Found potential career link by URL: '{text}' → {href}"
                            )

                            # Normalize URL
                            if not href.startswith("http"):
                                if href.startswith("/"):
                                    href = f"{domain}{href}"
                                else:
                                    href = f"{domain}/{href}"

                            # Verify the link works
                            try:
                                response = await page.goto(
                                    href, wait_until="domcontentloaded", timeout=5000
                                )
                                if response and response.status == 200:
                                    return href
                            except Exception as e:
                                logfire.debug(
                                    f"Error validating URL", url=href, error=str(e)
                                )
                    except Exception as e:
                        logfire.debug(f"Error processing link", error=str(e))

                # Second pass: check by link text
                for link in links:
                    try:
                        href = await link.get_attribute("href")
                        if (
                            not href
                            or href == "#"
                            or href.startswith("javascript:")
                            or href.startswith("mailto:")
                        ):
                            continue

                        text = (await link.text_content() or "").strip()
                        if not text:
                            continue

                        # Check for exact or partial keyword matches
                        if any(
                            keyword.lower() == text.lower()
                            for keyword in career_keywords
                        ):
                            logfire.info(
                                f"Found exact keyword match: '{text}' → {href}"
                            )

                            # Normalize URL
                            if not href.startswith("http"):
                                if href.startswith("/"):
                                    href = f"{domain}{href}"
                                else:
                                    href = f"{domain}/{href}"

                            # Verify the link works
                            try:
                                response = await page.goto(
                                    href, wait_until="domcontentloaded", timeout=5000
                                )
                                if response and response.status == 200:
                                    return href
                            except Exception as e:
                                logfire.debug(
                                    f"Error validating URL", url=href, error=str(e)
                                )

                        # Partial match
                        elif any(
                            keyword.lower() in text.lower()
                            for keyword in career_keywords
                        ):
                            logfire.info(
                                f"Found partial keyword match: '{text}' → {href}"
                            )

                            # Normalize URL
                            if not href.startswith("http"):
                                if href.startswith("/"):
                                    href = f"{domain}{href}"
                                else:
                                    href = f"{domain}/{href}"

                            # Verify the link works
                            try:
                                response = await page.goto(
                                    href, wait_until="domcontentloaded", timeout=5000
                                )
                                if response and response.status == 200:
                                    return href
                            except Exception as e:
                                logfire.debug(
                                    f"Error validating URL", url=href, error=str(e)
                                )

                    except Exception as e:
                        logfire.debug(f"Error analyzing link text", error=str(e))

                logfire.info("No career links found on main page")
                return None

            except Exception as e:
                logfire.error(f"Error during link analysis", error=str(e))
                return None

        finally:
            await context.close()
            await browser.close()
            await playwright.stop()

    async def process_company(self, company: CompanyUrl, session: AsyncSession) -> None:
        """Process a single company to find its career page."""
        logfire.info(f"Processing company: {company.name} - {company.url}")

        try:
            # Find career page URL
            career_url = await self.find_career_link(company.url)

            if not career_url:
                logfire.info(f"No career page found for {company.url}")
                return

            logfire.info(f"Found career page: {career_url}")

            # Check if career URL already exists in frontier
            existing_career = await session.execute(
                select(FrontierUrl).where(
                    FrontierUrl.company_id == company.id, FrontierUrl.url == career_url
                )
            )
            existing_career = existing_career.scalars().first()

            # If it doesn't exist, create a new frontier URL entry
            if not existing_career:
                parsed_url = urlparse(company.url)
                domain = f"{parsed_url.scheme}://{parsed_url.netloc}"

                # Create new frontier URL entry
                frontier_url = FrontierUrl(
                    url=career_url,
                    url_domain=domain,
                    company_id=company.id,
                    depth=1,
                    is_target=True,  # Mark as a target URL for job listings
                    last_visited=None,
                )

                session.add(frontier_url)
                await session.flush()

                logfire.info(f"Added new frontier URL: {career_url}")
            else:
                # Update existing entry
                existing_career.is_target = True
                await session.flush()

                logfire.info(f"Updated existing frontier URL: {career_url}")

        except Exception as e:
            import traceback

            logfire.error(
                "Error processing company",
                company=company.name,
                url=company.url,
                error=str(e),
                traceback=traceback.format_exc(),
            )
