import os
import json
import logfire
from typing import Dict, Any
from dotenv import load_dotenv
from openai import AzureOpenAI

from src.services.llm_processor import LLMProcessor

load_dotenv()


async def process_content(
    source_url: str, content_text: str, llm_config: Dict[str, Any]
) -> Dict[str, Any]:
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
                "processing_status": "failed",
            }

        # Initialize Azure OpenAI client
        client = AzureOpenAI(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version="2024-12-01-preview",
        )

        llm_processor = LLMProcessor(client, llm_config)

        response_content = await llm_processor.make_request(content_text)

        job_details = json.loads(response_content)

        job_details["source_url"] = source_url
        job_details["processed_timestamp"] = llm_processor.last_api_call_time

        logfire.info(f"Successfully processed job content from {source_url}")
        return job_details

    except Exception as e:
        logfire.error(
            f"Error processing job content from {source_url}: {str(e)}", exc_info=True
        )
        # Return a minimal result with error information
        return {
            "source_url": source_url,
            "error": str(e),
            "processing_status": "failed",
        }
