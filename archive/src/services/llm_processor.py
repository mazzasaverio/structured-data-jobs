import json
import logfire
from typing import Dict, List, Any, Optional
from openai import AzureOpenAI
import copy
import time
import asyncio


class LLMProcessor:
    """Handles LLM requests to Azure OpenAI with configurable prompts."""

    def __init__(self, client, config_prompt):
        self.client = client
        self.config_prompt = config_prompt
        self.last_api_call_time = 0  # Timestamp dell'ultima chiamata API

        if "messages" not in self.config_prompt:
            raise ValueError("Config must contain 'messages' key")
        if "model" not in self.config_prompt:
            raise ValueError("Config must contain 'model' key")

        logfire.info(
            f"Initialized LLMProcessor with model: {self.config_prompt['model']}"
        )

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
                model="gpt-4o",
                messages=messages,
                response_format=response_format,
                temperature=0,
            )

            return response.choices[0].message.content

        except Exception as e:
            logfire.error(f"Error in make_request: {str(e)}", exc_info=True)
            raise

    def _prepare_messages(self, text):
        try:
            if not text:
                return None

            messages = copy.deepcopy(self.config_prompt["messages"])

            for message in messages:
                if message["role"] == "user":
                    message["content"] = message["content"].replace("{text}", text)

            return messages

        except Exception as e:
            logfire.error(f"Error in _prepare_messages: {str(e)}", exc_info=True)
            raise

    def _prepare_response_format(self, fields_to_extract=None):
        if not fields_to_extract:
            return self.config_prompt.get("response_format", {"type": "json_object"})

        response_format = copy.deepcopy(self.config_prompt["response_format"])
        schema = response_format["json_schema"]["schema"]

        schema["properties"] = {
            field: schema["properties"][field]
            for field in fields_to_extract
            if field in schema["properties"]
        }
        schema["required"] = [
            field for field in schema["required"] if field in fields_to_extract
        ]

        return response_format
