# app/llm/gemini_llm.py
"""
LangChain-compatible wrapper for Google Gemini models.
Loads model and API key from environment variables.
Includes retry logic for rate limit handling.
"""

import os
import time
import google.generativeai as genai
from dotenv import load_dotenv
from langchain.llms.base import LLM
from typing import List, Optional, Any

load_dotenv()


class GeminiLLM(LLM):
    """LangChain-compatible Gemini wrapper with retry & rate-limit protection."""

    model_name: str = ""
    api_key: Optional[str] = None
    model: Any = None  # Pydantic-safe dynamic field

    def __init__(self, model_name: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        model_from_env = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        key_from_env = os.getenv("GEMINI_API_KEY")

        object.__setattr__(self, "model_name", model_name or model_from_env)
        object.__setattr__(self, "api_key", key_from_env)

        if not self.api_key:
            raise ValueError("❌ Missing GEMINI_API_KEY in environment variables.")

        genai.configure(api_key=self.api_key)
        model_instance = genai.GenerativeModel(model_name=self.model_name)
        object.__setattr__(self, "model", model_instance)

    @property
    def _llm_type(self) -> str:
        """Required LangChain property."""
        return "gemini"

    @property
    def _identifying_params(self):
        return {"model_name": self.model_name}

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """Generate text from Gemini with auto-retry for rate limits."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt)
                if response and hasattr(response, "text"):
                    return response.text.strip()
                else:
                    return "Gemini returned empty response."
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "Rate" in error_str:
                    wait_time = 5 * (attempt + 1)
                    print(f"⚠️ Gemini rate limit hit. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                return f"Gemini Error: {error_str}"

        return "Gemini Error: Max retries exceeded."
