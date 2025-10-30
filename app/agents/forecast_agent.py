"""
app/agents/forecast_agent.py - LangChain-based TCS Forecasting Agent (resilient version)
"""
import os
import re
import json
import asyncio
import logging
import warnings
from datetime import datetime, timezone
from typing import Dict, Any, List
from jsonschema import validate, ValidationError
from dotenv import load_dotenv
from langchain.agents import Tool, AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate
from langchain.schema import AgentAction
from app.tools.financial_extractor_tool import FinancialDataExtractorTool
from app.tools.qualitative_analysis_tool import QualitativeAnalysisTool
from app.llm.ollama_llm import OllamaLLM

llm = OllamaLLM(model="llama3.1:8b")

import nest_asyncio
nest_asyncio.apply()

from langchain.agents import initialize_agent, AgentType
from langchain.tools import Tool
from langchain.memory import ConversationBufferMemory

from app.tools.financial_extractor_tool import (
    extract_financial_metrics,
    validate_and_enrich_metrics_tool,
    FinancialDataExtractorTool,
)
from app.tools.qualitative_analysis_tool import QualitativeAnalysisTool

# ---------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------
warnings.filterwarnings("ignore", category=UserWarning, module="camelot")
load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------
# JSON Schema for final forecast
# ---------------------------------------------------------------------
FORECAST_SCHEMA = {
    "type": "object",
    "required": ["metadata", "numeric_trends", "qualitative_summary", "forecast", "risks_and_opportunities", "sources"],
    "properties": {
        "metadata": {
            "type": "object",
            "required": ["ticker", "request_id", "analysis_date", "quarters_analyzed"],
            "properties": {
                "ticker": {"type": "string"},
                "request_id": {"type": "string"},
                "analysis_date": {"type": "string", "format": "date-time"},
                "quarters_analyzed": {"type": "array", "items": {"type": "string"}}
            }
        },
        "numeric_trends": {"type": "object"},
        "qualitative_summary": {"type": "object"},
        "forecast": {"type": "object"},
        "risks_and_opportunities": {"type": "object"},
        "sources": {"type": "array"}
    }
}

# ---------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------
REACT_PROMPT = """You are an Expert Expert financial analyst generating TCS forecasts using two tools.

REQUIRED TOOLS (in order):
1. FinancialDataExtractorTool - Extract numeric data
2. QualitativeAnalysisTool - Analyze management insights

RULES:
- In each step, output ONLY ONE of:
  (a) A Tool call with: Thought, Action, and Action Input
  (b) A Final Answer (only after using all tools)
- Never include both Action and Final Answer in the same output.
- Always produce valid JSON at the end that matches the forecast schema.

Ticker: {ticker}
Request ID: {request_id}

{agent_scratchpad}
"""

# ---------------------------------------------------------------------
# Main Agent
# ---------------------------------------------------------------------
"""
forecast_agent.py — event-loop safe LangChain agent orchestration for TCS Forecasting
"""




logger = logging.getLogger(__name__)


class ForecastAgent:
    """
    ForecastAgent orchestrates multiple tools:
    - FinancialDataExtractorTool
    - QualitativeAnalysisTool
    - OpenRouterLLM for reasoning and forecasting
    """

    def __init__(self):
        self.llm = llm

        # Initialize Tools
        self.financial_extractor = FinancialDataExtractorTool()
        self.qualitative_tool = QualitativeAnalysisTool()

        # Wrap tools as LangChain Tool objects
        self.tools = [
            Tool(
                name="FinancialDataExtractorTool",
                func=lambda x: self.financial_extractor.extract(x),
                description="Extracts financial metrics like revenue, profit, EBITDA from financial PDFs."
            ),
            Tool(
                name="extract_financial_metrics",
                func=extract_financial_metrics,
                description="Extracts structured metrics from text input."
            ),
            Tool(
                name="validate_and_enrich_metrics",
                func=validate_and_enrich_metrics_tool,
                description="Validates and enriches metrics using LLM or deterministic logic."
            ),
            Tool(
                name="QualitativeAnalysisTool",
                func=lambda x: self.qualitative_tool.analyze(x),
                description="Analyzes management commentary, forward guidance, and risks qualitatively."
            ),
        ]

        # Conversation memory
        self.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

        # Initialize LangChain Agent
        self.agent = initialize_agent(
            tools=self.tools,
            llm=self.llm,
            agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
            memory=self.memory,
        )

    # --- Core business logic ---

    async def _async_run_pipeline(
        self,
        ticker: str,
        request_id: str,
        quarters: int = 3,
        sources: List[str] = None,
        include_market: bool = False
    ) -> Dict[str, Any]:
        """
        Main async forecast workflow — robust against LLM parsing errors.
        """
        try:
            dummy_text = f"Generate a qualitative and quantitative business forecast for {ticker}."
            logger.info(f"🚀 Running ForecastAgent for {ticker} ({request_id})")

            try:
                # Run the LangChain agent (offloaded to thread to avoid blocking event loop)
                forecast = await asyncio.to_thread(self.agent.run, dummy_text)
            except Exception as e:
                # Handle LangChain ReAct parsing errors gracefully
                if "Parsing LLM output produced both" in str(e) or "OutputParserException" in str(e):
                    logger.warning("⚠️ Recovered from mixed action+final output. Extracting Final Answer manually.")
                    import re
                    match = re.search(r"Final Answer:\s*(.*)", str(e), re.DOTALL)
                    if match:
                        forecast = match.group(1).strip()
                    else:
                        forecast = "ForecastAgent encountered mixed ReAct output; recovered partial result."
                else:
                    raise

            return {
                "status": "ok",
                "ticker": ticker,
                "request_id": request_id,
                "forecast": forecast,
            }

        except Exception as e:
            logger.exception("ForecastAgent async pipeline failed")
            return {
                "status": "error",
                "ticker": ticker,
                "request_id": request_id,
                "error": str(e),
            }


    # --- Public safe entry point ---

    def run(
        self,
        ticker: str,
        request_id: str,
        quarters: int = 3,
        sources: List[str] = None,
        include_market: bool = False
    ) -> Dict[str, Any]:
        """
        Safe synchronous entrypoint for both FastAPI and test environments.
        Handles asyncio.run() safely inside running loops.
        """

        async def _run_with_timeout():
            return await asyncio.wait_for(
                self._async_run_pipeline(ticker, request_id, quarters, sources, include_market),
                timeout=300
            )

        try:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # In FastAPI or pytest context
                    task = loop.create_task(_run_with_timeout())
                    return loop.run_until_complete(task)
                else:
                    return asyncio.run(_run_with_timeout())
            except RuntimeError:
                # No active loop
                return asyncio.run(_run_with_timeout())

        except asyncio.TimeoutError:
            logger.error(f"⚠️ ForecastAgent timed out for {ticker} ({request_id})")
            return {
                "error": "timeout",
                "message": f"ForecastAgent exceeded 90s for {ticker}",
                "ticker": ticker,
                "request_id": request_id,
            }
        except Exception as e:
            logger.exception("ForecastAgent run() failed")
            return {
                "error": "agent_execution_failed",
                "message": str(e),
                "ticker": ticker,
                "request_id": request_id,
            }
