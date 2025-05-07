import asyncio
import os
from pathlib import Path
from sqlalchemy import select
import logfire
from src.db.connection import get_db_session
from src.db.models.models import JobPost, JobDetail, CompanyUrl
from src.services.job_processor import process_content
from src.utils.config_loader import load_prompt_config
from src.utils.logging import setup_logging
from src.services.text_extraction import extract_content

setup_logging(service_name="job-extractor-details")


async def run_details_extractor():
    try:
        config = load_prompt_config("03_job_details")
        target_roles = config.get("target_roles", ["Data Engineer"])
        llm_config = config.get("job_detail_extraction")

        # Update to use the new folder structure
        output_dir = Path(os.getenv("PROJECT_ROOT", ".")) / "data" / "03_job_details"
        os.makedirs(output_dir, exist_ok=True)

        logfire.info(f"Processing job details for roles: {', '.join(target_roles)}")

        async with get_db_session() as session:
            result = await session.execute(
                select(JobPost).where(JobPost.role.in_(target_roles))
            )
            data_items = result.scalars().all()

            logfire.info(f"Found {len(data_items)} job posts to process")

            for data_item in data_items:
                source_url = data_item.url

                # Get company information for better identification
                company = (
                    await session.get(CompanyUrl, data_item.company_id)
                    if data_item.company_id
                    else None
                )
                company_name = company.name if company else "unknown_company"

                # Create a source identifier that includes company and job info
                from urllib.parse import urlparse

                domain = urlparse(source_url).netloc
                source_identifier = f"{company_name}:job-{data_item.id}:{domain}"

                logfire.info(
                    f"Processing job: {data_item.title} for company: {company_name}"
                )

                # Extract the content
                content_text = await extract_content(source_url)

                if not content_text:
                    logfire.error(f"Failed to extract content from URL", url=source_url)
                    continue

                try:
                    # Process the content
                    json_data = await process_content(
                        source_url, content_text, llm_config
                    )

                    # Add additional metadata to JSON
                    json_data["job_id"] = data_item.id
                    json_data["job_title"] = data_item.title
                    json_data["company_name"] = company_name
                    json_data["company_id"] = data_item.company_id

                    json_data["role"] = data_item.role

                    logfire.info(
                        f"Successfully processed and saved job details",
                        job_id=data_item.id,
                        job_title=data_item.title,
                        company=company_name,
                    )

                    # TODO: Store job details in database if needed
                    # This would replace the commented out save_to_database function

                except Exception as e:
                    logfire.error(
                        f"Error processing job details",
                        job_id=data_item.id,
                        url=source_url,
                        error=str(e),
                        exc_info=True,
                    )

    except Exception as e:
        logfire.error(f"Error running details extractor: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(run_details_extractor())
