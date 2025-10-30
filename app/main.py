from fastapi import FastAPI
from app.api.endpoints import router as api_router
from dotenv import load_dotenv
import os
import nest_asyncio


load_dotenv()  # load .env file at runtime
nest_asyncio.apply()

# NOTE: Do not abort server startup if OPENROUTER_API_KEY is missing. The
# ForecastAgent / LLM wrapper will raise a clear error at call time if the
# API key is required. This allows the app to start in dev/test environments
# where a fake or mocked LLM may be used.

app = FastAPI(title="TCS Financial Forecasting Agent")

app.include_router(api_router, prefix="/api")

@app.get("/health")
async def health():
    return {"status": "ok"}
