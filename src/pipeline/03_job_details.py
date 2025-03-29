import asyncio
import os
from pathlib import Path
from sqlalchemy import select
import logfire
from src.db.connection import get_db_session
from src.db.models.models import JobPost, JobDetail
from src.services.job_processor import process_content
from src.utils.config_loader import load_prompt_config
from src.utils.logging import setup_logging
from src.utils.file_utils import write_to_file
from src.services.text_extraction import extract_content

setup_logging(service_name="job-extractor-details")

async def run_details_extractor():
    try:
        config = load_prompt_config("03_job_details")
        target_roles = config.get("target_roles", ["Data Engineer"])
        llm_config = config.get("job_detail_extraction")
        
        # Create output directory for results
        output_dir = Path(os.getenv('PROJECT_ROOT', '.')) / "data" / "job_details"
        os.makedirs(output_dir, exist_ok=True)
        
        async with get_db_session() as session:
            result = await session.execute(
                select(JobPost)
                .where(JobPost.role.in_(target_roles))
            )
            data_items = result.scalars().all()
            
            logfire.info(f"Found {len(data_items)} job posts to process")

            for data_item in data_items:
                source_url = data_item.url
                
                # Generate a filename for this job
                from urllib.parse import urlparse
                domain = urlparse(source_url).netloc.replace(".", "_")
                job_id = data_item.id or "unknown"
                output_file_path = output_dir / f"job_details_{domain}_{job_id}.json"

                content_text = await extract_content(source_url)
                
                json_data = await process_content(source_url, content_text, llm_config)
                
                # Save to database function to be implemented
                # save_to_database(json_data, data_model)
                
                # Write to file using our new utility function
                write_to_file(json_data, str(output_file_path))

    except Exception as e:
        logfire.error(f"Error running details extractor: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(run_details_extractor())  