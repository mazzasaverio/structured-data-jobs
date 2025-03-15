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
from src.utils.logging import setup_logging, log_span, enable_debug_logging, log_separator
from src.db.connection import init_db, test_connection, get_db_session, verify_database_url
from src.db.models import CompanyUrl, FrontierUrl, TargetUrl, JobPostingUrl
from src.crawler.career_crawler import run_career_crawler       

# Track subprocess resources for debugging
_subprocess_resources = []

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

async def main():
    """Main application entry point."""
    setup_logging()
    log_separator("STARTING APPLICATION")
    
    logfire.info("Testing database connection...")
    verify_result = verify_database_url()
    if not verify_result:
        logfire.error("Invalid database URL configuration")
        return 1
    
    connection_ok = await test_connection()
    
    if not connection_ok:
        logfire.error("Failed to connect to the database")
        return 1
    
    logfire.info("Successfully connected to the database!")
    
    with log_span("database_initialization"):
        logfire.info("Initializing database...")
        await init_db()
        logfire.info("Database initialized successfully")
    
    logfire.info("Application started successfully")
    
    log_separator("DATABASE OPERATIONS")
    try:
        async with get_db_session() as session:
            log_separator("DATABASE QUERY")
            result = await session.execute(CompanyUrl.__table__.select())
            companies = result.scalars().all()
            
            if not companies:
                logfire.info("No companies found. Creating test company")
                company = CompanyUrl(
                    name="Igenius",
                    url="https://www.igenius.ai",
                )
                session.add(company)
                await session.commit()
                logfire.info("Test company created", id=company.id)
            else:
                logfire.info("Found companies in database", count=len(companies))
                
                for i, company in enumerate(companies):
                    try:
                        if isinstance(company, int):
                            company_obj = await session.get(CompanyUrl, company)
                            if company_obj:
                                logfire.info("Company details", 
                                           company_id=company_obj.id,
                                           company_name=company_obj.name,
                                           url=getattr(company_obj, 'url', None))
                            else:
                                logfire.warning(f"Company with ID {company} not found")
                        elif hasattr(company, 'name') and hasattr(company, 'id'):
                            logfire.info("Company details", 
                                       company_id=company.id,
                                       company_name=company.name,
                                       url=getattr(company, 'url', None))
                        else:
                            logfire.warning(f"Invalid company object #{i}", 
                                          type=str(type(company)))
                    except Exception as e:
                        logfire.error(f"Error processing company #{i}", error=str(e))
    except Exception as e:
        import traceback
        logfire.error("Database session error", 
                    error_type=type(e).__name__,
                    error=str(e),
                    traceback=traceback.format_exc())
        return 1
    
    log_separator("RUNNING CRAWLER")
    logfire.info("Starting career page crawler...")
    try:
        with logfire.span("career_crawler_execution") as span:
            logfire.info("Starting career crawler")
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
    start_time = time.time()
    
    # First create the event loop and set it
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Now you can log, but pass the loop explicitly to all_tasks
    logfire.info("Starting application", active_tasks="N/A")  # Initialize without tasks count
    
    try:
        logfire.info("Running main function")
        exit_code = loop.run_until_complete(main())
        logfire.info("Main function completed")
        
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
        # Force garbage collection before exit
        gc.collect()
        
        # Add a small delay to let OS processes terminate
        time.sleep(0.5)
        
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
    
    duration = time.time() - start_time
    print(f"Application completed in {duration:.2f} seconds with exit code {exit_code}")
    
    # Final check of process resources - make sure psutil is installed
    try:
        import psutil
        process = psutil.Process()
        print(f"Process resources at exit: {len(process.open_files())} open files, {process.num_threads()} threads")
    except ImportError:
        print("psutil not installed - skipping process resource check")
    
    sys.exit(exit_code)
