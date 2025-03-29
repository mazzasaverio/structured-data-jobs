"""Utility module for setting up Azure OpenAI client."""
import os
import logfire
from openai import AzureOpenAI

def setup_azure_client() -> AzureOpenAI:
    """Set up Azure OpenAI client.
    
    Returns:
        AzureOpenAI: Configured Azure OpenAI client
        
    Raises:
        ValueError: If required environment variables are missing
    """
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