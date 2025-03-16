import os
import json
import yaml
import copy
from pathlib import Path
from typing import Dict, List, Tuple, Any
from dotenv import load_dotenv
import logfire
from openai import AzureOpenAI
import time
import asyncio
import datetime

load_dotenv()

repo_root = os.getenv('PROJECT_ROOT')

class LLMProcessor:
    """Handles LLM requests to Azure OpenAI with configurable prompts."""
    
    def __init__(self, client, config_prompt):
        self.client = client
        self.config_prompt = config_prompt
        self.last_api_call_time = 0  # Timestamp dell'ultima chiamata API

        if 'messages' not in self.config_prompt:
            raise ValueError("Config must contain 'messages' key")
        if 'model' not in self.config_prompt:
            raise ValueError("Config must contain 'model' key")
        
        logfire.info(f"Initialized LLMProcessor with model: {self.config_prompt['model']}")

    async def make_request(self, text, fields_to_extract=None):
        try:
            messages = self._prepare_messages(text)
            if not messages:
                raise ValueError("Failed to prepare messages")
            
            response_format = self._prepare_response_format(fields_to_extract)
            
            # Controllo semplice per il rate limiting
            current_time = time.time()
            time_since_last_call = current_time - self.last_api_call_time
            
            if time_since_last_call < 10:  # 10 secondi tra le chiamate
                wait_time = 10 - time_since_last_call
                logfire.info(f"Waiting {wait_time:.2f} seconds before next API call")
                await asyncio.sleep(wait_time)
            
            # Aggiorna il timestamp prima della chiamata
            self.last_api_call_time = time.time()
            

            response = self.client.chat.completions.create(
                model= "gpt-4o",
                messages=messages,
                response_format=response_format,
                temperature=0
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logfire.error(f"Error in make_request: {str(e)}", exc_info=True)
            raise

    def _prepare_messages(self, text):
        try:
            if not text:
                return None
                
            messages = copy.deepcopy(self.config_prompt['messages'])
            
            for message in messages:
                if message['role'] == 'user':
                    message['content'] = message['content'].replace('{text}', text)
                    
            return messages
            
        except Exception as e:
            logfire.error(f"Error in _prepare_messages: {str(e)}", exc_info=True)
            raise
    
    def _prepare_response_format(self, fields_to_extract=None):
        if not fields_to_extract:
            return self.config_prompt.get('response_format', {"type": "json_object"})
            
        response_format = copy.deepcopy(self.config_prompt['response_format'])
        schema = response_format['json_schema']['schema']
        
        schema['properties'] = {
            field: schema['properties'][field] 
            for field in fields_to_extract 
            if field in schema['properties']
        }
        schema['required'] = [
            field for field in schema['required'] 
            if field in fields_to_extract
        ]
        
        return response_format

class CareerPageValidator:
    """Uses Azure OpenAI to validate career pages and suggest alternative URLs."""
    
    def __init__(self):
        self.client = self._setup_azure_client()
        self.prompt_config = self._load_prompt_config()
        self.llm_processor = LLMProcessor(self.client, self.prompt_config)
        
        # Create results directory if it doesn't exist
        self.results_dir = Path(repo_root) / "data" / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
    def _setup_azure_client(self) -> AzureOpenAI:
        try:
            client = AzureOpenAI(
                azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"), 
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),  
                api_version="2024-12-01-preview"
                )
            return client


        except Exception as e:
            logfire.error(f"Error setting up Azure OpenAI client: {str(e)}")
            raise
    
    def _load_prompt_config(self) -> Dict[str, Any]:
        """Load prompt configuration from YAML file."""
        config_path = Path(repo_root) / "src" / "config" / "career_validation.yaml"
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                if 'career_validation' in config:
                    return config['career_validation']
                return config
        except Exception as e:
            logfire.error(f"Error loading config from {config_path}: {str(e)}")
            # Return a minimal default config if file cannot be loaded
            return {
                "model": "gpt-4",
                "messages": [
                    {"role": "system", "content": "You are an expert in analyzing career pages."},
                    {"role": "user", "content": "Analyze this web page: {text}"}
                ],
                "response_format": {"type": "json_object"}
            }
    
    async def analyze_career_page(self, page_text: str, page_url: str, page_links: List[dict]) -> Tuple[bool, List[dict]]:
        """
        Analyze a career page to determine if it's a target page containing a list of job postings.
        """
        try:
            prompt_text = self._prepare_prompt(page_text, page_url, page_links)
            response_content = await self.llm_processor.make_request(prompt_text)
            result = json.loads(response_content)
            
            is_target = result.get("is_target", False)
            suggested_urls = result.get("suggested_urls", [])
            
            # Save result to JSON file
            self._save_result_to_json(page_url, result)
            
            return is_target, suggested_urls
        except Exception as e:
            logfire.error(f"Error analyzing career page: {str(e)}")
            # Use fallback validation if LLM fails
            is_target = self._fallback_validation(page_text, page_url)
            
            # Save fallback result to JSON
            fallback_result = {
                "is_target": is_target,
                "confidence": 30,  # Low confidence for fallback
                "reasoning": "Determined using fallback method due to LLM failure",
                "suggested_urls": []
            }
            self._save_result_to_json(page_url, fallback_result)
            
            return is_target, []
    
    def _save_result_to_json(self, page_url: str, result: Dict[str, Any]) -> None:
        """Save analysis result to a JSON file."""
        try:
            # Create a filename based on timestamp and URL
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Extract domain from URL for the filename
            from urllib.parse import urlparse
            domain = urlparse(page_url).netloc.replace(".", "_")
            
            filename = f"{timestamp}_{domain}.json"
            filepath = self.results_dir / filename
            
            # Prepare data to save
            data_to_save = {
                "page_url": page_url,
                "analysis_timestamp": timestamp,
                "result": result
            }
            
            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2)
                
            logfire.info(f"Saved analysis result to {filepath}")
        except Exception as e:
            logfire.error(f"Error saving result to JSON: {str(e)}")
    
    def _fallback_validation(self, page_text: str, page_url: str) -> bool:
        """Simple fallback validation if LLM fails"""
        job_keywords = ['job', 'career', 'position', 'opening', 'vacancy', 'apply', 'join our team', 'work with us']
        page_text_lower = page_text.lower()
        keyword_matches = sum(1 for keyword in job_keywords if keyword in page_text_lower)
        logfire.info("Using fallback validation", keyword_matches=keyword_matches)
        return keyword_matches >= 2  # If at least 2 keywords match, it's probably a job page
    
    def _prepare_prompt(self, page_text: str, page_url: str, page_links: List[dict]) -> str:
        """Prepare the prompt for the LLM."""
        # Limit page text to avoid token limits (around 6K characters)
        max_text_length = 6000
        truncated_text = page_text[:max_text_length] + ("..." if len(page_text) > max_text_length else "")
        
        # Format the most important links (limit to 15 to save tokens)
        formatted_links = []
        for link in page_links[:15]:
            formatted_links.append(f"- \"{link.get('text', '').strip()}\": {link.get('url', '')}")
        
        links_text = "\n".join(formatted_links)
        
        # Create the prompt
        prompt = f"""Analyze this web page from {page_url} to determine if it's a valid career/jobs page with actual job listings.

PAGE TEXT EXCERPT:
{truncated_text}

IMPORTANT LINKS ON THE PAGE:
{links_text}

Respond with a detailed analysis determining if this is a valid career page with job listings. If it's not, suggest alternative URLs from the links that might contain job listings.
"""
        return prompt 
    












