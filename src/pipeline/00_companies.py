import asyncio
import os
import sys
import traceback
import yaml
import logfire
from pathlib import Path
from urllib.parse import urlparse
from src.utils.logging import setup_logging
from src.db.connection import init_db, get_db_session
from src.db.models.models import CompanyUrl

repo_root = os.getenv('PROJECT_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

setup_logging()

def normalize_url(url):
    """Normalize URL by removing trailing slashes and ensuring consistent formatting."""
    if not url:
        return url
    
    # Remove trailing slash if present
    url = url.rstrip('/')
    
    # Ensure consistent protocol format
    if url.startswith('http://'):
        url = url.replace('http://', 'https://')
    elif not url.startswith('https://'):
        url = f'https://{url}'
    
    return url

def load_companies_from_yaml():
    """Load companies from the YAML configuration file."""
    try:
        config_path = Path(repo_root) / "src" / "config" / "00_companies.yaml"
        
        if not config_path.exists():
            logfire.warning(f"Companies config file not found at {config_path}")
            return []
            
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        if not config or 'companies' not in config:
            logfire.warning("No companies found in config file")
            return []
            
        companies = config['companies']
        logfire.info(f"Loaded {len(companies)} companies from config file")
        return companies
    except Exception as e:
        logfire.error(f"Error loading companies from YAML: {str(e)}")
        return []

async def main():
    """Main application entry point."""
    await init_db()
    
    try:
        async with get_db_session() as session:
            # Check for new companies in YAML that aren't in the database
            yaml_companies = load_companies_from_yaml()
            
            companies_added = 0
            for company_data in yaml_companies:
                try:
                    # Normalize URL before comparison
                    normalized_url = normalize_url(company_data["url"])
                    
                    # Check if company exists by normalized URL
                    result = await session.execute(
                        CompanyUrl.__table__.select().where(
                            CompanyUrl.url == normalized_url
                        )
                    )
                    existing_company_by_url = result.scalar_one_or_none()
                    
                    # Also check if company with same name exists
                    result = await session.execute(
                        CompanyUrl.__table__.select().where(
                            CompanyUrl.name == company_data["name"]
                        )
                    )
                    existing_company_by_name = result.scalar_one_or_none()
                    
                    if existing_company_by_url:
                        logfire.debug(f"Company with URL {normalized_url} already exists, skipping")
                        continue
                    elif existing_company_by_name:
                        logfire.warning(f"Company with name {company_data['name']} exists with different URL, updating URL")
                        existing_company_by_name.url = normalized_url
                        await session.commit()
                        continue
                        
                    # If we get here, the company doesn't exist - add it
                    company = CompanyUrl(
                        name=company_data["name"],
                        url=normalized_url,  # Use normalized URL
                    )
                    session.add(company)
                    
                    await session.commit()
                    companies_added += 1
                    
                except Exception as e:
                    logfire.error(f"Error processing company {company_data['name']}", 
                               error_type=type(e).__name__,
                               error=str(e),
                               traceback=traceback.format_exc())
                    await session.rollback()
            
            if companies_added > 0:
                logfire.info(f"Successfully added {companies_added} new companies")
            else:
                logfire.info("No new companies were added")
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
