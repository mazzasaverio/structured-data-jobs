import asyncio
import sys
import time
from src.utils.logging import setup_logging, get_logger, log_span
from src.db.connection import init_db, test_connection, get_db_session, verify_database_url
from src.db.models import CompanyUrl, Frontier, TargetUrl, JobPostingUrl

setup_logging()
logger = get_logger()

async def main():
    """Main application entry point."""
    with log_span("application_startup"):
        logger.info("Starting lean-jobs-crawler application")
        
        logger.info("Testing database connection...")
        verify_result = verify_database_url()
        if not verify_result:
            logger.error("Invalid database URL configuration")
            return 1
        
        connection_ok = await test_connection()
        
        if not connection_ok:
            logger.error("Failed to connect to the database")
            return 1
        
        logger.info("Successfully connected to the database!")
        
        with log_span("database_initialization"):
            logger.info("Initializing database...")
            await init_db()
            logger.info("Database initialized successfully")
        
        logger.info("Application started successfully")
    
    try:
        async with get_db_session() as session:
            result = await session.execute(CompanyUrl.__table__.select())
            companies = result.scalars().all()
            
            if not companies:
                logger.info("No companies found. Creating a test company...")
                company = CompanyUrl(
                    name="Igenius",
                    url="https://www.igenius.ai",
                )
                session.add(company)
                await session.commit()
                logger.info(f"Test company created with ID: {company.id}")
            else:
                logger.info(f"Found {len(companies)} companies in database:")
                for company in companies:
                    logger.info(f"- {company.name} (ID: {company.id})")
    
    except Exception as e:
        logger.error(f"Database test error: {str(e)}")
        return 1
    
    logger.info("Database connection test completed successfully!")
    return 0


if __name__ == "__main__":
    start_time = time.time()
    exit_code = asyncio.run(main())
    duration = time.time() - start_time
    
    logger.info("Application run completed", 
               duration_seconds=duration,
               exit_code=exit_code)
    
    sys.exit(exit_code)
