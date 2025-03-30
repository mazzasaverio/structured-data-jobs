import asyncio
import os
import sys
import traceback
import logfire
from pathlib import Path
from urllib.parse import urlparse
from src.utils.logging import setup_logging
from src.db.connection import init_db, get_db_session
from src.db.models.models import CompanyUrl
from src.utils.url_utils import normalize_url
from src.utils.config_loader import load_prompt_config

repo_root = os.getenv('PROJECT_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

setup_logging()



async def main():
    """Main application entry point."""
    await init_db()
    
    try:
        async with get_db_session() as session:
            # Check for new companies in YAML that aren't in the database
            config = load_prompt_config("00_companies")
        
            
            companies = config['companies']
         
            for company_data in companies:
                try:
                    
                    normalized_url = normalize_url(company_data["url"])
                    
                    # Check if company exists by normalized URL
                    result = await session.execute(
                        CompanyUrl.__table__.select().where(
                            CompanyUrl.url == normalized_url
                        )
                    )
                    existing_company_by_url = result.scalar_one_or_none()
                    
                   
                    
                    if existing_company_by_url:
                        logfire.debug(f"Company with URL {normalized_url} already exists, skipping")
                        continue
             
                        
                    # If we get here, the company doesn't exist - add it
                    company = CompanyUrl(
                        name=company_data["name"],
                        url=normalized_url, 
                    )
                    session.add(company)
                    
                    await session.commit()
                 
                except Exception as e:
                    logfire.error(f"Error processing company {company_data['name']}", 
                               error_type=type(e).__name__,
                               error=str(e),
                               traceback=traceback.format_exc())
                    await session.rollback()
            
          
    except Exception as e:
        logfire.error("Error in database operations", error=str(e), traceback=traceback.format_exc())
        raise
    
    return 0

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        exit_code = loop.run_until_complete(main())
    finally:
        loop.close()
    
    sys.exit(exit_code)
