import os
import asyncio
from datetime import datetime, timedelta
import pendulum
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

import logfire
from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

# Constants
POSTGRES_CONN_ID = "postgres_neon"
DEFAULT_OUTPUT_DIR = "/usr/local/airflow/include/data/output"

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "start_date": pendulum.datetime(2023, 1, 1, tz="UTC"),
}


class CareerPageFinder:
    """Finds career pages on company websites and identifies job listings pages."""

    def __init__(self, output_dir: str = DEFAULT_OUTPUT_DIR):
        """Initialize with output directory."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pg_hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)

    async def setup_browser(self) -> Tuple[Browser, BrowserContext]:
        """Set up Playwright browser and context."""
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        )
        return playwright, browser, context

    async def find_career_page(self, url: str) -> Optional[str]:
        """Find the career page for a company website."""
        parsed_url = urlparse(url.rstrip("/"))
        domain = f"{parsed_url.scheme}://{parsed_url.netloc}"

        # Common career page paths to check directly
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

        # Setup browser for checking
        playwright, browser, context = await self.setup_browser()
        page = await context.new_page()

        try:
            # STRATEGY 1: Direct URL check with common paths
            for path in common_career_paths:
                try:
                    check_url = f"{domain}{path}"
                    logfire.debug(f"Checking common path: {check_url}")

                    response = await page.goto(
                        check_url, wait_until="domcontentloaded", timeout=5000
                    )

                    if response and response.status == 200:
                        logfire.info(f"Found career page at: {check_url}")

                        # Additional check to see if this appears to be a jobs page
                        if await self.is_job_listings_page(page):
                            logfire.info(f"Confirmed as job listings page: {check_url}")
                            return check_url
                        else:
                            logfire.debug(
                                f"Page exists but doesn't appear to be a job listings page: {check_url}"
                            )

                except Exception as e:
                    logfire.debug(f"Error checking path {path}", error=str(e))

            # STRATEGY 2: Analyze links on main page
            logfire.info(f"Checking main page for career links: {url}")

            # Keywords that likely indicate career/jobs pages
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

            # Career-related paths to look for in URLs
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

            try:
                # Navigate to main page
                await page.goto(url, wait_until="networkidle", timeout=15000)
                await page.wait_for_timeout(2000)  # Wait for dynamic content

                # Get all links
                links = await page.query_selector_all("a")
                link_data = []

                # First pass: Check URL patterns
                for link in links:
                    try:
                        href = await link.get_attribute("href")
                        if not href:
                            continue

                        href_lower = href.lower()
                        text = (await link.text_content() or "").strip()

                        # Collect link data for further analysis
                        link_data.append(
                            {"href": href, "text": text, "href_lower": href_lower}
                        )

                        # Quick check for career-related patterns in URL
                        if any(path in href_lower for path in career_paths):
                            # Normalize URL
                            if not href.startswith("http"):
                                if href.startswith("/"):
                                    href = f"{domain}{href}"
                                else:
                                    href = f"{domain}/{href}"

                            logfire.info(f"Found potential career link in URL: {href}")

                            # Verify the link
                            try:
                                response = await page.goto(
                                    href, wait_until="domcontentloaded", timeout=5000
                                )
                                if response and response.status == 200:
                                    if await self.is_job_listings_page(page):
                                        return href
                            except Exception as e:
                                logfire.debug(
                                    f"Error validating URL {href}", error=str(e)
                                )

                    except Exception as e:
                        continue

                # Second pass: Check link text for career-related keywords
                for data in link_data:
                    href, text = data["href"], data["text"]

                    if (
                        not href
                        or href == "#"
                        or href.startswith("javascript:")
                        or href.startswith("mailto:")
                        or not text
                    ):
                        continue

                    # Check for exact or partial keyword matches in link text
                    exact_match = any(
                        keyword.lower() == text.lower() for keyword in career_keywords
                    )
                    partial_match = any(
                        keyword.lower() in text.lower() for keyword in career_keywords
                    )

                    if exact_match or partial_match:
                        match_type = "exact" if exact_match else "partial"
                        logfire.info(
                            f"Found {match_type} keyword match in link text: '{text}' → {href}"
                        )

                        # Normalize URL
                        if not href.startswith("http"):
                            if href.startswith("/"):
                                href = f"{domain}{href}"
                            else:
                                href = f"{domain}/{href}"

                        # Verify the link
                        try:
                            response = await page.goto(
                                href, wait_until="domcontentloaded", timeout=5000
                            )
                            if response and response.status == 200:
                                if await self.is_job_listings_page(page):
                                    return href
                        except Exception as e:
                            logfire.debug(f"Error validating URL {href}", error=str(e))

                logfire.info(f"No job listings page found for {url}")
                return None

            except Exception as e:
                logfire.error(f"Error analyzing main page {url}", error=str(e))
                return None

        finally:
            await page.close()
            await context.close()
            await browser.close()
            await playwright.stop()

    async def is_job_listings_page(self, page: Page) -> bool:
        """
        Determine if the current page is a job listings page by analyzing content.
        """
        # Check page title
        title = await page.title()
        title_lower = title.lower()

        job_title_indicators = [
            "careers",
            "jobs",
            "open positions",
            "job openings",
            "join our team",
            "work with us",
            "carriere",
            "lavora con noi",
            "posizioni aperte",
        ]

        if any(indicator in title_lower for indicator in job_title_indicators):
            return True

        # Check for job listing patterns
        try:
            # Check for elements that typically contain job listings
            job_listing_selectors = [
                "div.job-listing",
                "div.careers-list",
                "ul.jobs-list",
                "div.positions",
                "div.open-positions",
                ".job-card",
                "[data-job-id]",
                "[data-position-id]",
                ".career-item",
                ".job-item",
                ".vacancy",
                ".role-listing",
            ]

            for selector in job_listing_selectors:
                elements = await page.query_selector_all(selector)
                if len(elements) > 1:  # More than one listing found
                    return True

            # Look for multiple links with job titles
            links = await page.query_selector_all("a")
            job_title_words = [
                "engineer",
                "developer",
                "manager",
                "director",
                "specialist",
                "analyst",
                "designer",
                "assistant",
                "coordinator",
                "head of",
                "lead",
                "senior",
                "junior",
            ]

            job_title_count = 0
            for link in links:
                text = (await link.text_content() or "").strip().lower()
                if any(word in text for word in job_title_words):
                    job_title_count += 1
                    if job_title_count >= 3:  # At least 3 job title links
                        return True

            # Check for job-related text content
            content = await page.content()
            content_lower = content.lower()

            job_content_indicators = [
                "job description",
                "qualifications",
                "responsibilities",
                "requirements",
                "apply now",
                "submit your application",
                "apply for this position",
                "what we offer",
                "we're looking for",
                "join our team",
                "posizione",
                "requisiti",
                "candidati",
                "candidati ora",
                "apply for this job",
            ]

            indicator_count = sum(
                1 for indicator in job_content_indicators if indicator in content_lower
            )
            if indicator_count >= 3:  # Multiple job content indicators
                return True

            return False

        except Exception as e:
            logfire.debug(f"Error analyzing page for job listings", error=str(e))
            return False

    def fetch_companies_without_career_pages(self) -> List[Dict[str, Any]]:
        """Fetch companies that don't have a mapped career page yet."""
        conn = self.pg_hook.get_conn()
        cursor = conn.cursor()

        try:
            # Query to find companies without frontier_urls entries marked as targets
            query = """
                SELECT cu.id, cu.name, cu.url 
                FROM company_urls cu
                LEFT JOIN (
                    SELECT DISTINCT company_id 
                    FROM frontier_urls 
                    WHERE is_target = TRUE
                ) fu ON cu.id = fu.company_id
                WHERE fu.company_id IS NULL
                ORDER BY cu.id;
            """

            cursor.execute(query)
            companies = [
                {"id": row[0], "name": row[1], "url": row[2]}
                for row in cursor.fetchall()
            ]

            logfire.info(f"Found {len(companies)} companies without career pages")
            return companies

        finally:
            cursor.close()
            conn.close()

    def save_career_page(self, company_id: int, url: str, domain: str) -> None:
        """Save career page to database."""
        conn = self.pg_hook.get_conn()
        cursor = conn.cursor()

        try:
            # Check if this frontier URL already exists
            check_query = """
                SELECT id FROM frontier_urls 
                WHERE company_id = %s AND url = %s
            """
            cursor.execute(check_query, (company_id, url))
            existing = cursor.fetchone()

            if existing:
                # Update existing entry
                update_query = """
                    UPDATE frontier_urls 
                    SET is_target = TRUE, 
                        last_visited = %s
                    WHERE id = %s
                """
                cursor.execute(update_query, (datetime.now(), existing[0]))
                logfire.info(f"Updated existing frontier URL: {url}")
            else:
                # Insert new entry
                insert_query = """
                    INSERT INTO frontier_urls 
                    (company_id, url, url_domain, depth, is_target, last_visited, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(
                    insert_query,
                    (
                        company_id,
                        url,
                        domain,
                        1,  # depth
                        True,  # is_target
                        datetime.now(),  # last_visited
                        datetime.now(),  # created_at
                        datetime.now(),  # updated_at
                    ),
                )
                logfire.info(f"Added new frontier URL: {url}")

            conn.commit()

        except Exception as e:
            conn.rollback()
            logfire.error(f"Error saving career page", error=str(e))
            raise

        finally:
            cursor.close()
            conn.close()

    async def process_company(self, company: Dict[str, Any]) -> None:
        """Process a single company to find its career page."""
        company_id = company["id"]
        company_name = company["name"]
        company_url = company["url"]

        logfire.info(f"Processing company: {company_name}", url=company_url)

        try:
            # Find career page
            career_url = await self.find_career_page(company_url)

            if not career_url:
                logfire.info(f"No career page found for {company_name}")
                return

            logfire.info(f"Found career page for {company_name}: {career_url}")

            # Extract domain for storage
            parsed_url = urlparse(company_url)
            domain = f"{parsed_url.scheme}://{parsed_url.netloc}"

            # Save to database
            self.save_career_page(company_id, career_url, domain)

        except Exception as e:
            logfire.error(f"Error processing company {company_name}", error=str(e))


@dag(
    dag_id="career_pages_crawler",
    default_args=default_args,
    schedule="@weekly",  # Run weekly
    catchup=False,
    tags=["web", "crawler", "career-pages"],
    doc_md="""
    # Career Pages Crawler
    
    This DAG:
    1. Fetches companies from the database that don't have career pages mapped yet
    2. Crawls company websites to find career pages with job listings
    3. Saves discovered career pages to the database
    
    The crawler uses multiple strategies to find job listing pages:
    - Checking common career page paths
    - Analyzing link text for career-related keywords
    - Analyzing page content to confirm it contains job listings
    """,
)
def career_pages_crawler():

    @task
    def fetch_companies():
        """Fetch companies without career pages from database."""
        finder = CareerPageFinder()
        return finder.fetch_companies_without_career_pages()

    @task
    def process_companies(companies: List[Dict[str, Any]]):
        """Process companies to find career pages."""
        # Create and set the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        finder = CareerPageFinder()

        try:
            # Process companies in batches to avoid memory issues
            batch_size = 10
            total = len(companies)

            for i in range(0, total, batch_size):
                batch = companies[i : i + batch_size]
                logfire.info(
                    f"Processing batch {i//batch_size + 1}/{(total+batch_size-1)//batch_size}"
                )

                # Create tasks for each company in batch
                tasks = [finder.process_company(company) for company in batch]

                # Run batch concurrently
                loop.run_until_complete(asyncio.gather(*tasks))

        except Exception as e:
            logfire.error(f"Error processing companies", error=str(e))

        finally:
            # Clean up resources
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()

            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))

            loop.close()
            asyncio.set_event_loop(None)

    companies = fetch_companies()
    process_companies(companies)


career_pages_crawler_dag = career_pages_crawler()

if __name__ == "__main__":
    career_pages_crawler_dag.test()
