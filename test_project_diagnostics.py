"""
Diagnostic Test Script for Financial Forecasting Agent
------------------------------------------------------
Run this file with:  python test_project_diagnostics.py

It checks:
1. Environment variables and API key
2. OpenRouter LLM connectivity
3. FinancialDataExtractorTool
4. QualitativeAnalysisTool
5. ForecastAgent integration
"""

import os
import asyncio
import logging
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# ---- 1️⃣ Check ENVIRONMENT ----
def check_env():
    print("\n[1️⃣] Checking environment variables...")
    key = os.getenv("GEMINI_API_KEY")
    base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/")

    if not key:
        print("❌  GEMINI_API_KEY missing — add it to .env or system environment.")
    else:
        print("✅  GEMINI_API_KEY detected.")

    print(f"BASE URL: {base_url}")
    return bool(key)


# ---- 2️⃣ Check LLM ----
def test_llm():
    print("\n[2️⃣] Testing GeminiLLM connectivity...")
    try:
        from app.llm.gemini_llm import GeminiLLM
        llm = GeminiLLM()
        resp = llm._call("Say hello in one short sentence.")
        print(f"✅ LLM OK. Response: {resp[:100]}...")
    except Exception:
        print("❌ LLM test failed.")
        traceback.print_exc()


# ---- 3️⃣ Check FinancialDataExtractorTool ----
def test_financial_tool():
    print("\n[3️⃣] Testing FinancialDataExtractorTool...")
    try:
        from app.tools.financial_extractor_tool import FinancialDataExtractorTool
        tool = FinancialDataExtractorTool()
        result = tool.run(action="extract_all")
        print("✅ FinancialDataExtractorTool OK.")
        print(result)
    except Exception:
        print("❌ FinancialDataExtractorTool test failed.")
        traceback.print_exc()


# ---- 4️⃣ Check QualitativeAnalysisTool ----
def test_qualitative_tool():
    print("\n[4️⃣] Testing QualitativeAnalysisTool...")
    try:
        from app.tools.qualitative_analysis_tool import QualitativeAnalysisTool
        qa = QualitativeAnalysisTool()

        # Sample minimal transcript in /data/documents
        transcripts = [
            {"name": "Q1-Earnings-Transcript.txt", "local_path": "data/documents/Q1-Earnings-Transcript.txt"}
        ]
        result = qa.analyze(transcripts)
        print("✅ QualitativeAnalysisTool OK.")
        print(result)
    except Exception:
        print("❌ QualitativeAnalysisTool test failed.")
        traceback.print_exc()


# ---- 5️⃣ Check ForecastAgent ----
async def test_forecast_agent():
    print("\n[5️⃣] Testing ForecastAgent orchestration...")
    try:
        from app.agents.forecast_agent import ForecastAgent
        agent = ForecastAgent()
        result = await agent.run("TCS")
        print("✅ ForecastAgent completed successfully.")
        print(result)
    except Exception:
        print("❌ ForecastAgent test failed.")
        traceback.print_exc()


# ---- ENTRY POINT ----
if __name__ == "__main__":
    print("🚀 Running full diagnostic on TCS Forecasting Agent...")

    env_ok = check_env()
    test_llm()
    test_financial_tool()
    test_qualitative_tool()

    try:
        asyncio.run(test_forecast_agent())
    except RuntimeError:
        # Handle 'event loop already running'
        loop = asyncio.get_event_loop()
        loop.run_until_complete(test_forecast_agent())

    print("\n✅ Diagnostic complete.")
