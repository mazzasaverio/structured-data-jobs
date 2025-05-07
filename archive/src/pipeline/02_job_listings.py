import asyncio
import os
from pathlib import Path
from typing import List, Dict
import logfire
from urllib.parse import urlparse

from src.db.models.models import CompanyUrl, FrontierUrl, JobPost
from src.db.connection import get_db_session
from sqlalchemy import select
from src.services.html_to_markdown import convert_webpage_to_markdown
from src.services.job_processor import process_content

from src.utils.config_loader import load_prompt_config
from src.utils.logging import setup_logging

setup_logging()

# Get the project root directory
repo_root = os.getenv(
    "PROJECT_ROOT",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)


async def save_job_listings(
    job_listings: List[dict], frontier_url: FrontierUrl
) -> None:
    """Save job listings to the database."""
    try:
        saved_count = 0
        already_exists_count = 0
        invalid_url_count = 0

        logfire.info(
            f"Saving {len(job_listings)} job listings to database", url=frontier_url.url
        )

        async with get_db_session() as session:
            # Get company URL
            company = await session.get(CompanyUrl, frontier_url.company_id)
            if not company:
                logfire.error(f"Company not found for ID: {frontier_url.company_id}")
                return

            logfire.info(f"Processing job listings for company: {company.name}")

            for job in job_listings:
                # Check if job URL is valid
                job_url = job.get("url", "")
                job_title = job.get("title", "Unknown Position")

                if not job_url:
                    logfire.warning(f"Skipping job with missing URL", title=job_title)
                    invalid_url_count += 1
                    continue

                # Normalize URL if needed
                if not job_url.startswith("http"):
                    old_url = job_url
                    try:
                        domain_parts = frontier_url.url.split("/")
                        if len(domain_parts) >= 3:
                            base_domain = f"{domain_parts[0]}//{domain_parts[2]}"
                            job_url = (
                                f"{base_domain}{job_url}"
                                if job_url.startswith("/")
                                else f"{frontier_url.url.rstrip('/')}/{job_url.lstrip('/')}"
                            )
                        logfire.info(f"Normalized URL: {old_url} -> {job_url}")
                    except Exception as url_error:
                        logfire.error(
                            f"Failed to normalize URL: {old_url}", error=str(url_error)
                        )
                        invalid_url_count += 1
                        continue

                # Check if job already exists
                existing_job = await session.execute(
                    select(JobPost).where(JobPost.url == job_url)
                )
                if existing_job.scalar_one_or_none():
                    logfire.debug(
                        f"Job post already exists: {job_url}", title=job_title
                    )
                    already_exists_count += 1
                    continue

                # Get the role from the job data (with fallback to "Other")
                job_role = job.get("role", "Other")

                # Create new job post
                new_job = JobPost(
                    title=job_title,
                    url=job_url,
                    url_domain=frontier_url.url_domain,
                    url_target=frontier_url.url,
                    company_id=frontier_url.company_id,
                    role=job_role,
                )

                session.add(new_job)
                saved_count += 1

            # Commit all changes
            await session.commit()
            logfire.info(
                f"Saved {saved_count} new job listings to database",
                already_exists=already_exists_count,
                invalid_urls=invalid_url_count,
                company=company.name,
            )

    except Exception as e:
        logfire.error(
            f"Error saving job listings: {str(e)}",
            company_id=frontier_url.company_id,
            url=frontier_url.url,
            exc_info=True,
        )


async def run_job_extractor():
    """Main function to run the job extractor."""
    config = load_prompt_config("02_job_listings")

    # Rename to match the key in your config file (job_extraction instead of job_listing_extraction)
    llm_config = config.get("job_extraction")

    if not llm_config:
        logfire.error(
            "Failed to load LLM configuration. Check if the 'job_extraction' key exists in config file."
        )
        return

    logfire.info("Loaded LLM configuration", model=llm_config.get("model", "unknown"))

    # Update to use the new folder structure
    output_dir = Path(os.getenv("PROJECT_ROOT", ".")) / "data" / "02_job_listings"
    os.makedirs(output_dir, exist_ok=True)

    async with get_db_session() as session:
        result = await session.execute(
            select(FrontierUrl).where(FrontierUrl.is_target == True)
        )
        target_urls = result.scalars().all()

        logfire.info(f"Found {len(target_urls)} target URLs to process")

        for frontier_url in target_urls:
            source_url = frontier_url.url

            # Get company information for better source identification
            company = await session.get(CompanyUrl, frontier_url.company_id)
            company_name = company.name if company else "unknown_company"

            # Create a source identifier that includes company and URL info
            domain = urlparse(source_url).netloc
            source_identifier = f"{company_name}:{domain}:{frontier_url.id}"

            logfire.info(
                f"Processing target URL: {source_url} for company: {company_name}"
            )

            # Extract content with the new method
            content_text = await convert_webpage_to_markdown(source_url)

            if not content_text:
                logfire.error(f"Failed to extract content from URL", url=source_url)
                json_data = {
                    "source_url": source_url,
                    "company_name": company_name,
                    "company_id": frontier_url.company_id,
                    "error": "No content available for processing",
                    "processing_status": "failed",
                    "job_listings": [],
                }
            else:

                logfire.info(
                    f"Successfully extracted content from URL",
                    url=source_url,
                    content_length=len(content_text),
                )

                try:
                    json_data = await process_content(
                        source_url, content_text, llm_config
                    )

                    # Add additional metadata to JSON
                    json_data["company_name"] = company_name
                    json_data["company_id"] = frontier_url.company_id
                    json_data["frontier_url_id"] = frontier_url.id
                    json_data["version_info"] = version_info

                except Exception as e:
                    logfire.error(
                        f"Error processing content from URL",
                        url=source_url,
                        error=str(e),
                        error_type=type(e).__name__,
                        exc_info=True,
                    )
                    json_data = {
                        "source_url": source_url,
                        "company_name": company_name,
                        "company_id": frontier_url.company_id,
                        "frontier_url_id": frontier_url.id,
                        "error": str(e),
                        "processing_status": "failed",
                        "job_listings": [],
                    }

            logfire.info(
                f"Saved job listings data with new storage system",
                company=company_name,
                url=source_url,
            )

            job_listings = json_data.get("job_listings", [])

            if job_listings:
                await save_job_listings(job_listings, frontier_url)


if __name__ == "__main__":
    asyncio.run(run_job_extractor())
