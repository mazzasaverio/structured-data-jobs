import asyncio
import sys
import time
import traceback
import os
import logfire
import gc
import warnings
import atexit
import signal
import yaml
from pathlib import Path
from src.utils.logging import setup_logging, log_span, enable_debug_logging, log_separator
from src.db.connection import init_db, test_connection, get_db_session, verify_database_url
from src.db.models.models import CompanyUrl, FrontierUrl
from src.crawler.career_crawler import run_career_crawler       
import aiohttp
from urllib.parse import urlparse
from sqlalchemy.exc import SQLAlchemyError

_subprocess_resources = []

# Get the project root directory
repo_root = os.getenv('PROJECT_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def track_resource(resource, name):
    """Track a resource for debugging purposes"""
    _subprocess_resources.append((resource, name))
    logfire.info(f"Resource tracked: {name}", resource_type=type(resource).__name__)

# Check if debug mode is requested
if os.environ.get("DEBUG", "").lower() in ("1", "true", "yes"):
    enable_debug_logging()
    logfire.info("Debug logging enabled")
else:
    setup_logging()

warnings.filterwarnings("ignore", 
                       message="Event loop is closed", 
                       category=RuntimeWarning)

def load_companies_from_yaml():
    """Load companies from the YAML configuration file."""
    try:
        config_path = Path(repo_root) / "src" / "config" / "companies.yaml"
        
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
    setup_logging()
    
    with log_span("database_initialization"):
        await init_db()
        logfire.info("Database initialized successfully")
    
    log_separator("DATABASE OPERATIONS")
    try:
        async with get_db_session() as session:
            log_separator("DATABASE QUERY")
            result = await session.execute(CompanyUrl.__table__.select())
            companies = result.scalars().all()
            
            if not companies:
                logfire.info("No companies found in database. Loading from config file...")
                companies_to_add = load_companies_from_yaml()
                for company_data in companies_to_add:
                    company = CompanyUrl(
                        name=company_data["name"],
                        url=company_data["url"],
                    )
                    session.add(company)

                await session.commit()
                logfire.info(f"Added {len(companies_to_add)} companies to database")
            else:
                # Check for new companies in YAML that aren't in the database
                yaml_companies = load_companies_from_yaml()
                
                companies_added = 0
                for company_data in yaml_companies:
                    try:
                        # First check if this company exists by URL (most reliable identifier)
                        result = await session.execute(
                            CompanyUrl.__table__.select().where(
                                CompanyUrl.url == company_data["url"]
                            )
                        )
                        existing_company = result.scalar_one_or_none()
                        
                        if existing_company:
                            logfire.debug(f"Company with URL {company_data['url']} already exists, skipping")
                            continue
                            
                        # If we get here, the company doesn't exist - add it
                        company = CompanyUrl(
                            name=company_data["name"],
                            url=company_data["url"],
                        )
                        session.add(company)
                        
                        await session.commit()
                        companies_added += 1
                        
                    except Exception as e:
                        import traceback
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
   
    log_separator("RUNNING CRAWLER")

    try:
        with logfire.span("career_crawler_execution") as span:
            await run_career_crawler()
            logfire.info("Career crawler completed successfully")
    except Exception as e:
        import traceback
        log_separator("CRAWLER ERROR")
        logfire.error("Career crawler failed", 
                    error_type=type(e).__name__,
                    error_message=str(e),
                    traceback=traceback.format_exc())
        print(f"\nERROR: {type(e).__name__}: {str(e)}")
        print("Traceback:")
        print('\n'.join('  ' + line for line in traceback.format_exc().splitlines()[-10:]))
        return 1
    
    log_separator("APPLICATION COMPLETED")
    
    try:
        for task in asyncio.all_tasks(asyncio.get_event_loop()):
            if task != asyncio.current_task() and not task.done():
                task.cancel()
    except Exception as e:
        logfire.warning("Error during cleanup", error=str(e))
    
    return 0

def force_cleanup():
    gc.collect()

atexit.register(force_cleanup)

def signal_handler(sig, frame):
    """Handle exit signals properly"""
    print("Received signal, shutting down gracefully...")
    sys.exit(0)

# Register signal handlers at the beginning of your program
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
  
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        exit_code = loop.run_until_complete(main())

        # Now check for pending tasks with explicit loop reference
        pending = asyncio.all_tasks(loop)
        logfire.info("Pending tasks before cleanup", 
                   count=len(pending),
                   task_names=[t.get_name() if hasattr(t, 'get_name') else "Unknown" for t in pending])
        
        # Cancel remaining tasks
        for task in pending:
            if task.done() or task == asyncio.current_task(loop):
                continue
            logfire.info("Cancelling task", task_name=task.get_name() if hasattr(task, 'get_name') else "Unknown")
            task.cancel()
        
        if pending:
            logfire.info("Waiting for task cancellation")
            loop.run_until_complete(asyncio.wait(pending, timeout=5))
    finally:
        gc.collect()
    
        # Explicitly terminate any remaining browser processes
        try:
            import psutil
            
            current_process = psutil.Process()
            for child in current_process.children(recursive=True):
                try:
                    os.kill(child.pid, signal.SIGTERM)
                except:
                    pass
        except ImportError:
            pass
    
    try:
        import psutil
        process = psutil.Process()
        print(f"Process resources at exit: {len(process.open_files())} open files, {process.num_threads()} threads")
    except ImportError:
        print("psutil not installed - skipping process resource check")
    
    sys.exit(exit_code)
