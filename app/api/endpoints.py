from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from uuid import uuid4
from typing import Optional, List
import logging
import asyncio
import json

from app.agents.forecast_agent import ForecastAgent
from app.db.mysql_client import MySQLClient

router = APIRouter()

# Lazy-initialized global instances
agent: Optional[ForecastAgent] = None
db: Optional[MySQLClient] = None


def ensure_services():
    """Initialize ForecastAgent and MySQLClient once (lazy init)."""
    global agent, db
    if agent is None:
        try:
            agent = ForecastAgent()
            logging.info("✅ ForecastAgent initialized.")
        except Exception as e:
            logging.exception("❌ Failed to initialize ForecastAgent")
            raise HTTPException(status_code=500, detail=f"ForecastAgent init failed: {e}")

    if db is None:
        try:
            db = MySQLClient()
            logging.info("✅ MySQLClient initialized and connected.")
        except Exception as e:
            logging.exception("❌ Failed to initialize MySQLClient")
            raise HTTPException(status_code=500, detail=f"MySQLClient init failed: {e}")


class ForecastRequest(BaseModel):
    ticker: str = "TCS"
    quarters: int = 3
    sources: List[str] = ["screener", "company-ir"]
    include_market: bool = False


@router.post("/forecast/tcs")
async def forecast_tcs(request: Request, req: ForecastRequest):
    """
    Main endpoint for running the TCS ForecastAgent.
    - Logs request to MySQL
    - Runs the forecasting pipeline
    - Logs result to MySQL
    """
    ensure_services()

    # Generate unique request ID
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    payload = req.dict()
    ticker = payload.get("ticker", "TCS")

    # Log the incoming request
    try:
        db.log_request(request_id, payload)
        logging.info(f"🟢 Logged request {request_id} for ticker={ticker}")
    except Exception as e:
        logging.warning(f"⚠️ Failed to log request {request_id}: {e}")

    # Run ForecastAgent safely
    try:
        logging.info(f"🚀 Running ForecastAgent for {ticker} ({request_id})")
        result = agent.run(
            ticker=ticker,
            request_id=request_id,
            quarters=req.quarters,
            sources=req.sources,
            include_market=req.include_market
        )

        # Log result to DB
        try:
            db.log_result(request_id, result)
            logging.info(f"💾 Logged result for {request_id}")
        except Exception as e:
            logging.warning(f"⚠️ Failed to log result for {request_id}: {e}")

        return result

    except asyncio.TimeoutError:
        db.log_event(request_id, "timeout", {"error": f"ForecastAgent exceeded timeout for {ticker}"})
        raise HTTPException(status_code=504, detail=f"ForecastAgent timed out for {ticker}")
    except Exception as e:
        db.log_event(request_id, "agent_error", {"error": str(e)})
        logging.exception("❌ ForecastAgent error")
        raise HTTPException(status_code=500, detail=f"ForecastAgent error: {e}")


@router.get("/status/{request_id}")
async def get_status(request_id: str):
    """Retrieve the last stored forecast result for a given request_id."""
    ensure_services()
    try:
        result = db.get_result(request_id)
        if result:
            return result
        raise HTTPException(status_code=404, detail="Request ID not found in database.")
    except Exception:
        logging.exception("❌ Failed to fetch result from MySQL.")
        raise HTTPException(status_code=500, detail="Failed to fetch result from DB.")


@router.get("/health/capabilities")
async def health_check():
    """Returns runtime capability diagnostics for debugging."""
    import importlib.util
    import os

    def _has_pkg(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except Exception:
            return False

    return {
        "llm": {
            "gemini_api_key_set": bool(os.getenv("GEMINI_API_KEY")),
        },
        "db": {
            "mysql_host": os.getenv("MYSQL_HOST", "localhost"),
            "connected": db is not None,
        },
        "pdf_tools": {
            "camelot": _has_pkg("camelot"),
            "pdfplumber": _has_pkg("pdfplumber"),
            "pytesseract": _has_pkg("pytesseract"),
        }
    }