import asyncio
import json
import os
import yaml
import copy
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple
import logfire
import time
from openai import AzureOpenAI
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from src.db.models.models import CompanyUrl, FrontierUrl, JobPost
from src.db.connection import get_db_session
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.utils.logging import setup_logging

# Get the project root directory
repo_root = os.getenv('PROJECT_ROOT', os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Configure logfire when this module is run directly
if __name__ == "__main__":
    setup_logging(service_name="job-extractor")
    logfire.info("Job extractor logging initialized")

class LLMProcessor:
    """Handles LLM requests to Azure OpenAI with configurable prompts."""
    
    def __init__(self, client, config_prompt):
        self.client = client
        self.config_prompt = config_prompt
        self.last_api_call_time = 0  # Timestamp of the last API call
        self.total_api_calls = 0
        self.total_api_time = 0

        if 'messages' not in self.config_prompt:
            raise ValueError("Config must contain 'messages' key")
        if 'model' not in self.config_prompt:
            raise ValueError("Config must contain 'model' key")
        
        logfire.info(f"Initialized LLMProcessor with model: {self.config_prompt['model']}")

    async def make_request(self, text, url=None):
        try:
            logfire.info(f"Preparing LLM request for URL: {url}", text_length=len(text) if text else 0)
            messages = self._prepare_messages(text, url)
            if not messages:
                raise ValueError("Failed to prepare messages")
            
            response_format = self.config_prompt.get('response_format', {"type": "json_object"})
            
            # Simple rate limiting
            current_time = asyncio.get_event_loop().time()
            time_since_last_call = current_time - self.last_api_call_time
            
            if time_since_last_call < 10:  # 10 seconds between calls
                wait_time = 10 - time_since_last_call
                logfire.info(f"Rate limiting: waiting {wait_time:.2f} seconds before next API call")
                await asyncio.sleep(wait_time)
            
            # Update timestamp before call
            api_start_time = time.time()
            self.last_api_call_time = asyncio.get_event_loop().time()
            self.total_api_calls += 1
            
            logfire.info(f"Sending API request to Azure OpenAI", 
                        model=self.config_prompt['model'],
                        message_count=len(messages),
                        api_call_number=self.total_api_calls)
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                response_format=response_format,
                temperature=0
            )
            
            api_duration = time.time() - api_start_time
            self.total_api_time += api_duration
            
            logfire.info(f"Received API response", 
                       duration_seconds=api_duration,
                       total_api_calls=self.total_api_calls,
                       average_duration=self.total_api_time/self.total_api_calls if self.total_api_calls > 0 else 0)
            
            return response.choices[0].message.content
            
        except Exception as e:
            logfire.error(f"Error in make_request: {str(e)}", 
                        url=url, 
                        text_length=len(text) if text else 0,
                        exc_info=True)
            raise

    def _prepare_messages(self, text, url=None):
        try:
            if not text:
                return None
                
            messages = copy.deepcopy(self.config_prompt['messages'])
            
            for message in messages:
                if message['role'] == 'user':
                    content = message['content']
                    content = content.replace('{text}', text)
                    if url:
                        content = content.replace('{url}', url)
                    message['content'] = content
                    
            return messages
            
        except Exception as e:
            logfire.error(f"Error in _prepare_messages: {str(e)}", exc_info=True)
            raise


class JobExtractor:
    """Extracts job postings from target URLs and saves them to the database."""
    
    def __init__(self):
        logfire.info("Initializing JobExtractor")
        self.client = self._setup_azure_client()
        self.prompt_config = self._load_prompt_config()
        self.llm_processor = LLMProcessor(self.client, self.prompt_config)
        
        # Create results directory if it doesn't exist
        self.results_dir = Path(repo_root) / "data" / "results" / "job_extractions"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Add counters for monitoring
        self.processed_urls = 0
        self.successful_extractions = 0
        self.failed_extractions = 0
        self.extracted_jobs = 0
        self.start_time = time.time()
        
        logfire.info("JobExtractor initialized successfully", 
                   results_dir=str(self.results_dir))
        
    def _setup_azure_client(self) -> AzureOpenAI:
        """Set up Azure OpenAI client."""
        try:
            logfire.info("Setting up Azure OpenAI client")
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            
            if not endpoint or not api_key:
                logfire.error("Azure OpenAI credentials not found in environment variables",
                           endpoint_exists=bool(endpoint),
                           api_key_exists=bool(api_key))
                raise ValueError("Missing Azure OpenAI credentials")
            
            client = AzureOpenAI(
                azure_endpoint=endpoint, 
                api_key=api_key,  
                api_version="2024-12-01-preview"
            )
            logfire.info("Azure OpenAI client set up successfully")
            return client
        except Exception as e:
            logfire.error(f"Error setting up Azure OpenAI client: {str(e)}", exc_info=True)
            raise
    
    def _load_prompt_config(self) -> Dict[str, Any]:
        """Load prompt configuration from YAML file."""
        config_path = Path(repo_root) / "src" / "config" / "job_extraction.yaml"
        
        try:
            logfire.info(f"Loading prompt config from {config_path}")
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            if 'job_extraction' in config:
                config = config['job_extraction']
                
            logfire.info("Prompt config loaded successfully", 
                       model=config.get('model', 'not specified'),
                       message_count=len(config.get('messages', [])))
            return config
        except Exception as e:
            logfire.error(f"Error loading config from {config_path}: {str(e)}", exc_info=True)
            # Return a minimal default config if file cannot be loaded
            default_config = {
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": "You are an expert in analyzing job listings."},
                    {"role": "user", "content": "Extract job listings from this page: {text}"}
                ],
                "response_format": {"type": "json_object"}
            }
            logfire.info("Using default prompt config due to config loading failure")
            return default_config
    
    async def setup_browser(self) -> Tuple[Browser, BrowserContext]:
        """Set up Playwright browser and context."""
        logfire.info("Setting up Playwright browser")
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        logfire.info("Playwright browser setup complete")
        return playwright, browser, context
    
    async def extract_page_text(self, page: Page) -> str:
        """Extract all text content from the page with URLs in their original context."""
        try:
            page_url = page.url
            logfire.info(f"Extracting text from page: {page_url}")
            
            # Wait for the page to load
            await page.wait_for_load_state("networkidle", timeout=30000)
            logfire.info("Page reached 'networkidle' state", url=page_url)
            
            # Try to expand any "Show more" or "Load more" buttons that might reveal more content
            expand_selectors = [
                "button:text-matches('(show|load|view) more', 'i')",
                "a:text-matches('(show|load|view) more', 'i')",
                "button:text-matches('expand', 'i')",
                "a:text-matches('expand', 'i')",
                "button:text-matches('see all', 'i')",
                "a:text-matches('see all', 'i')"
            ]
            
            for selector in expand_selectors:
                try:
                    element_count = await page.locator(selector).count()
                    if element_count > 0:
                        logfire.info(f"Found {element_count} expandable elements with selector: {selector}")
                        elements = await page.locator(selector).all()
                        for i, element in enumerate(elements):
                            try:
                                await element.click()
                                logfire.info(f"Clicked expandable element {i+1}/{element_count}", selector=selector)
                                await asyncio.sleep(2)
                            except Exception as click_error:
                                logfire.warning(f"Failed to click expandable element", 
                                             index=i,
                                             selector=selector,
                                             error=str(click_error))
                except Exception as selector_error:
                    logfire.warning(f"Error processing selector {selector}: {str(selector_error)}")
            
            # Extract page title
            title = await page.title()
            logfire.info(f"Page title: {title}", url=page_url)
            
            # Extract all text and links preserving their original positions
            start_evaluate = time.time()
            logfire.info("Starting JavaScript content extraction")
            full_content = await page.evaluate("""() => {
                function getTextAndLinksRecursive(node, result = []) {
                    if (node.nodeType === Node.TEXT_NODE) {
                        const text = node.textContent.trim();
                        if (text) {
                            result.push({ type: 'text', content: text });
                        }
                    } else if (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'A' && node.href) {
                        // For links, capture both text and URL
                        const text = node.innerText.trim();
                        if (text) {
                            result.push({ 
                                type: 'link', 
                                content: text,
                                url: node.href
                            });
                        }
                    } else if (node.nodeType === Node.ELEMENT_NODE) {
                        // Only apply getComputedStyle to element nodes
                        try {
                            // Skip hidden elements
                            const style = window.getComputedStyle(node);
                            const isVisible = style && style.display !== 'none' && style.visibility !== 'hidden';
                            
                            if (isVisible) {
                                // Process children
                                for (const child of node.childNodes) {
                                    getTextAndLinksRecursive(child, result);
                                }
                                
                                // Add line breaks after block elements
                                if (/^(div|p|h[1-6]|ul|ol|li|table|tr|section|article|header|footer|form)$/i.test(node.tagName)) {
                                    result.push({ type: 'linebreak' });
                                }
                            }
                        } catch (error) {
                            // If getComputedStyle fails, still try to process children
                            for (const child of node.childNodes) {
                                getTextAndLinksRecursive(child, result);
                            }
                        }
                    }
                    return result;
                }
                
                // Start from body
                const bodyContent = getTextAndLinksRecursive(document.body);
                
                // Format the result into a single string with URLs preserved
                let formattedContent = '';
                let lastWasLinebreak = false;
                
                for (const item of bodyContent) {
                    if (item.type === 'text') {
                        formattedContent += item.content + ' ';
                        lastWasLinebreak = false;
                    } else if (item.type === 'link') {
                        formattedContent += item.content + ' [' + item.url + '] ';
                        lastWasLinebreak = false;
                    } else if (item.type === 'linebreak' && !lastWasLinebreak) {
                        formattedContent += '\\n';
                        lastWasLinebreak = true;
                    }
                }
                
                return formattedContent.trim().replace(/\\n{3,}/g, '\\n\\n');
            }""")
            
            extraction_time = time.time() - start_evaluate
            content_length = len(full_content) if full_content else 0
            
            logfire.info("Completed page content extraction", 
                       duration_seconds=extraction_time,
                       content_length=content_length,
                       url=page_url)
            
            # Format extracted information
            structured_content = [
                f"PAGE ANALYSIS: {title}",
                f"URL: {page.url}",
                "\n=== FULL PAGE CONTENT WITH URLS ===\n",
                full_content
            ]
            
            result = "\n".join(structured_content)
            logfire.info("Text extraction completed successfully", 
                       result_length=len(result),
                       url=page_url)
            return result
            
        except Exception as e:
            logfire.error(f"Error extracting page text: {str(e)}", 
                        url=page.url if page else "unknown",
                        exc_info=True)
            # Return a minimal version if extraction fails
            try:
                minimal_content = f"URL: {page.url}\nTitle: {await page.title()}\n\n{await page.content()}"
                logfire.warning("Using fallback minimal content extraction")
                return minimal_content
            except Exception as fallback_error:
                logfire.error(f"Fallback extraction also failed: {str(fallback_error)}")
                return f"URL: {page.url if page else 'unknown'}\nExtraction failed"
    
    async def extract_job_listings(self, page_text: str, page_url: str) -> List[dict]:
        """Extract job listings from the page text using LLM."""
        try:
            logfire.info(f"Extracting job listings from {page_url}", text_length=len(page_text))
            start_time = time.time()
            
            # Process with LLM
            response_content = await self.llm_processor.make_request(page_text, page_url)
            
            try:
                result = json.loads(response_content)
                logfire.info("Successfully parsed LLM response as JSON")
            except json.JSONDecodeError as json_error:
                logfire.error("Failed to parse LLM response as JSON", 
                           error=str(json_error),
                           response_content=response_content[:500])
                return []
            
            # Save result to JSON file for analysis
            self._save_result_to_json(page_url, result)
            
            # Check if extraction was successful
            extraction_success = result.get("extraction_success", False)
            job_listings = result.get("job_listings", [])
            reasoning = result.get("reasoning", "No reason provided")
            
            duration = time.time() - start_time
            
            if not extraction_success:
                logfire.warning(f"Extraction not successful for {page_url}", reasoning=reasoning)
                self.failed_extractions += 1
                return []
            
            self.successful_extractions += 1
            self.extracted_jobs += len(job_listings)
            
            logfire.info(f"Successfully extracted {len(job_listings)} job listings", 
                       url=page_url, 
                       duration_seconds=duration,
                       reasoning=reasoning)
            
            return job_listings
            
        except Exception as e:
            logfire.error(f"Error extracting job listings: {str(e)}", 
                        url=page_url,
                        exc_info=True)
            self.failed_extractions += 1
            return []
    
    def _save_result_to_json(self, page_url: str, result: Dict[str, Any]) -> None:
        """Save extraction result to a JSON file."""
        try:
            # Create a filename based on timestamp and URL
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Extract domain from URL for the filename
            domain = urlparse(page_url).netloc.replace(".", "_")
            
            filename = f"{timestamp}_{domain}.json"
            filepath = self.results_dir / filename
            
            # Prepare data to save
            data_to_save = {
                "page_url": page_url,
                "extraction_timestamp": timestamp,
                "result": result
            }
            
            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2)
                
            logfire.info(f"Saved extraction result to {filepath}")
        except Exception as e:
            logfire.error(f"Error saving result to JSON: {str(e)}", 
                        url=page_url,
                        exc_info=True)
    
    async def process_target_url(self, frontier_url: FrontierUrl) -> None:
        """Process a target URL and extract job listings."""
        playwright = None
        browser = None
        context = None
        
        try:
            url = frontier_url.url
            logfire.info(f"Processing target URL: {url}", url_id=frontier_url.id)
            start_time = time.time()
            self.processed_urls += 1
            
            # Setup browser
            logfire.info(f"Setting up browser for {url}")
            playwright, browser, context = await self.setup_browser()
            page = await context.new_page()
            
            # Navigate to page
            logfire.info(f"Navigating to {url}")
            navigation_start = time.time()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            navigation_time = time.time() - navigation_start
            logfire.info(f"Navigation completed in {navigation_time:.2f} seconds", url=url)
            
            # Extract page text
            extraction_start = time.time()
            page_text = await self.extract_page_text(page)
            extraction_time = time.time() - extraction_start
            logfire.info(f"Text extraction completed in {extraction_time:.2f} seconds", 
                       url=url, 
                       text_length=len(page_text))
            
            # Extract job listings
            analysis_start = time.time()
            job_listings = await self.extract_job_listings(page_text, url)
            analysis_time = time.time() - analysis_start
            
            # Save job listings to database
            if job_listings:
                logfire.info(f"Found {len(job_listings)} job listings at {url}")
                save_start = time.time()
                await self.save_job_listings(job_listings, frontier_url)
                save_time = time.time() - save_start
                logfire.info(f"Job listings saved to database in {save_time:.2f} seconds", url=url)
            else:
                logfire.warning(f"No job listings found at {url}")
            
            # Update last_visited timestamp in frontier_url
            logfire.info(f"Updating last_visited timestamp for {url}")
            update_start = time.time()
            async with get_db_session() as session:
                await session.execute(
                    update(FrontierUrl)
                    .where(FrontierUrl.id == frontier_url.id)
                    .values(last_visited=datetime.now())
                )
                await session.commit()
            update_time = time.time() - update_start
            
            total_time = time.time() - start_time
            logfire.info(f"Completed processing {url}", 
                       total_duration=total_time,
                       navigation_time=navigation_time,
                       extraction_time=extraction_time,
                       analysis_time=analysis_time,
                       update_time=update_time,
                       job_count=len(job_listings))
                
        except Exception as e:
            logfire.error(f"Error processing target URL {frontier_url.url}: {str(e)}", 
                        url_id=frontier_url.id,
                        exc_info=True)
        finally:
            # Clean up resources
            cleanup_start = time.time()
            try:
                if context:
                    await context.close()
                if browser:
                    await browser.close()
                if playwright:
                    await playwright.stop()
                cleanup_time = time.time() - cleanup_start
                logfire.info(f"Browser resources cleaned up in {cleanup_time:.2f} seconds")
            except Exception as cleanup_error:
                logfire.error(f"Error during browser cleanup: {str(cleanup_error)}", exc_info=True)
    
    async def save_job_listings(self, job_listings: List[dict], frontier_url: FrontierUrl) -> None:
        """Save job listings to the database."""
        try:
            saved_count = 0
            already_exists_count = 0
            invalid_url_count = 0
            
            logfire.info(f"Saving {len(job_listings)} job listings to database", url=frontier_url.url)
            
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
                            domain_parts = frontier_url.url.split('/')
                            if len(domain_parts) >= 3:
                                base_domain = f"{domain_parts[0]}//{domain_parts[2]}"
                                job_url = f"{base_domain}{job_url}" if job_url.startswith('/') else f"{frontier_url.url.rstrip('/')}/{job_url.lstrip('/')}"
                            logfire.info(f"Normalized URL: {old_url} -> {job_url}")
                        except Exception as url_error:
                            logfire.error(f"Failed to normalize URL: {old_url}", error=str(url_error))
                            invalid_url_count += 1
                            continue
                    
                    # Check if job already exists
                    existing_job = await session.execute(
                        select(JobPost).where(JobPost.url == job_url)
                    )
                    if existing_job.scalar_one_or_none():
                        logfire.debug(f"Job post already exists: {job_url}", title=job_title)
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
                        role=job_role
                    )
                    
                    session.add(new_job)
                    saved_count += 1
                
                # Commit all changes
                await session.commit()
                logfire.info(f"Saved {saved_count} new job listings to database", 
                           already_exists=already_exists_count,
                           invalid_urls=invalid_url_count,
                           company=company.name)
                
        except Exception as e:
            logfire.error(f"Error saving job listings: {str(e)}", 
                        company_id=frontier_url.company_id,
                        url=frontier_url.url,
                        exc_info=True)


async def run_job_extractor():
    """Main function to run the job extractor."""
    logfire.info("Starting job extractor")
    start_time = time.time()
    
    try:
        # No need to check internal attributes, setup_logging() is safe to call multiple times
        try:
            from src.utils.logging import setup_logging
            setup_logging(service_name="job-extractor")
            logfire.info("Ensured Logfire is configured")
        except Exception as logging_error:
            logfire.warning(f"Error configuring Logfire: {str(logging_error)}")
        
        job_extractor = JobExtractor()
        
        # Get all target URLs that haven't been visited in the last 24 hours
        async with get_db_session() as session:
            # Get target URLs
            logfire.info("Querying database for target URLs")
            result = await session.execute(
                select(FrontierUrl)
                .where(FrontierUrl.is_target == True)
            )
            target_urls = result.scalars().all()
            
            logfire.info(f"Found {len(target_urls)} target URLs to process")
            
            # Process each target URL
            for i, frontier_url in enumerate(target_urls):
                logfire.info(f"Processing URL {i+1}/{len(target_urls)}: {frontier_url.url}", 
                           url_id=frontier_url.id)
                await job_extractor.process_target_url(frontier_url)
                # Add a small delay between processing URLs to avoid overloading
                logfire.info(f"Waiting 5 seconds before processing next URL")
                await asyncio.sleep(5)
            
        # Log summary statistics
        total_time = time.time() - start_time
        logfire.info("Job extractor completed successfully", 
                   total_duration_seconds=total_time,
                   processed_urls=job_extractor.processed_urls,
                   successful_extractions=job_extractor.successful_extractions,
                   failed_extractions=job_extractor.failed_extractions,
                   extracted_jobs=job_extractor.extracted_jobs,
                   average_time_per_url=total_time/job_extractor.processed_urls if job_extractor.processed_urls > 0 else 0)
        
    except Exception as e:
        logfire.error(f"Error running job extractor: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(run_job_extractor()) 