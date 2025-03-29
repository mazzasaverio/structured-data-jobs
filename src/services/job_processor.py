import os
import json
import logfire
from typing import Dict, Any
from dotenv import load_dotenv
from openai import AzureOpenAI

from src.services.llm_processor import LLMProcessor

load_dotenv()

async def process_content(source_url: str, content_text: str, llm_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process job posting content using LLM to extract structured information.
    
    Args:
        source_url (str): The URL of the job posting
        content_text (str): The extracted text content from the job posting
        llm_config (Dict[str, Any]): Configuration for the LLM processing
        
    Returns:
        Dict[str, Any]: Structured job details in JSON format
    """
    try:
        logfire.info(f"Processing job content from URL: {source_url}")
        
        # Verifica se il contenuto è vuoto
        if not content_text:
            logfire.warning(f"Empty content received for {source_url}")
            return {
                "source_url": source_url,
                "error": "No content available for processing",
                "processing_status": "failed"
            }
        
        # Initialize Azure OpenAI client
        client = AzureOpenAI(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version="2024-12-01-preview"
        )
        
        # Initialize LLM processor with the provided config
        llm_processor = LLMProcessor(client, llm_config)
        
        # Prepare prompt with source URL and content
        prompt_text = _prepare_job_prompt(source_url, content_text)
        
        # Make request to LLM
        response_content = await llm_processor.make_request(prompt_text)
        
        # Parse response as JSON
        job_details = json.loads(response_content)
        
        # Add metadata
        job_details["source_url"] = source_url
        job_details["processed_timestamp"] = llm_processor.last_api_call_time
        
        logfire.info(f"Successfully processed job content from {source_url}")
        return job_details
        
    except Exception as e:
        logfire.error(f"Error processing job content from {source_url}: {str(e)}", exc_info=True)
        # Return a minimal result with error information
        return {
            "source_url": source_url,
            "error": str(e),
            "processing_status": "failed"
        }

def _prepare_job_prompt(source_url: str, content_text: str) -> str:
    """
    Prepare the prompt for job content processing.
    
    Args:
        source_url (str): The URL of the job posting
        content_text (str): The extracted text content from the job posting
        
    Returns:
        str: The prepared prompt for the LLM
    """
    prompt = f"""Extract detailed information from this job posting.

SOURCE URL: {source_url}

JOB POSTING CONTENT:
{content_text}

Please extract all relevant information about this job posting, including but not limited to:
- Job title
- Company name
- Location (remote, on-site, hybrid)
- Employment type (full-time, part-time, contract)
- Experience level required
- Education requirements
- Skills required and preferred
- Responsibilities
- Benefits and perks
- Salary information (if available)
"""
    return prompt 