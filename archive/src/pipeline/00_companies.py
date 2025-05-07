import asyncio
import os
import sys
import traceback
import logfire
from src.utils.logging import setup_logging
from src.db.connection import init_db, get_db_session
from src.db.models.models import CompanyUrl
from src.utils.url_utils import normalize_url
from src.utils.config_loader import load_prompt_config

repo_root = os.getenv(
    "PROJECT_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

setup_logging()


async def main():
    """Main application entry point."""
    await init_db()

    try:
        async with get_db_session() as session:
            # Check for new companies in YAML that aren't in the database
            config = load_prompt_config("00_companies")
            logfire.info(f"Loaded configuration: {config}")

            # Check if 'companies' key exists in config, use empty list as default if not
            companies = config.get("companies", [])
            logfire.info(f"Found {len(companies)} companies in configuration")

            if not companies:
                logfire.warning(
                    "No companies found in configuration. Please check 00_companies.yaml file exists and contains company data."
                )

            for company_data in companies:
                try:
                    logfire.info(f"Processing company data: {company_data}")
                    normalized_url = normalize_url(company_data["url"])
                    logfire.info(
                        f"Normalized URL: {normalized_url} (original: {company_data['url']})"
                    )

                    # Check if company exists by normalized URL
                    logfire.debug(
                        f"Checking if company with URL {normalized_url} exists in database"
                    )
                    result = await session.execute(
                        CompanyUrl.__table__.select().where(
                            CompanyUrl.url == normalized_url
                        )
                    )
                    existing_company_by_url = result.scalar_one_or_none()

                    if existing_company_by_url:
                        logfire.debug(
                            f"Company with URL {normalized_url} already exists, skipping"
                        )
                        continue

                    # If we get here, the company doesn't exist - add it
                    logfire.info(
                        f"Adding new company: {company_data['name']} with URL {normalized_url}"
                    )
                    company = CompanyUrl(
                        name=company_data["name"],
                        url=normalized_url,
                    )
                    session.add(company)

                    logfire.debug("Committing changes to database")
                    await session.commit()
                    logfire.info(f"Successfully added company {company_data['name']}")

                except KeyError as ke:
                    logfire.error(
                        f"Key error processing company data: {company_data}",
                        missing_key=str(ke),
                        error_type="KeyError",
                        traceback=traceback.format_exc(),
                    )
                    await session.rollback()
                except Exception as e:
                    logfire.error(
                        f"Error processing company {company_data.get('name', 'UNKNOWN')}",
                        error_type=type(e).__name__,
                        error=str(e),
                        traceback=traceback.format_exc(),
                    )
                    await session.rollback()

    except Exception as e:
        logfire.error(
            "Error in database operations",
            error=str(e),
            traceback=traceback.format_exc(),
        )
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
