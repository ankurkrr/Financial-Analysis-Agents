"""
OllamaLLM - Local LLM connector for LangChain
Connects to Ollama running on localhost:11434
"""

import requests
import json
from typing import Optional, List
from langchain.llms.base import LLM


class OllamaLLM(LLM):
    model: str = "llama3.1:8b"

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """Send prompt to local Ollama model and return response"""
        try:
            url = "http://localhost:11434/api/generate"
            payload = {"model": self.model, "prompt": prompt, "stream": False}

            response = requests.post(url, json=payload, timeout=300)
            response.raise_for_status()

            data = response.json()
            return data.get("response", "").strip()
        except requests.exceptions.ConnectionError:
            return "Ollama server not running. Start it with `ollama serve`."
        except Exception as e:
            return f"Ollama error: {e}"

    @property
    def _identifying_params(self):
        return {"model": self.model}

    @property
    def _llm_type(self):
        return "ollama"
