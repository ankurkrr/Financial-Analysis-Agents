# TCS Financial Forecasting Agent

An AI-powered financial analysis agent that generates business outlook forecasts for Tata Consultancy Services (TCS) using a hosted Gemini model, LangChain, FastAPI, and advanced document processing techniques. The agent uses Google's Generative Language API (Gemini) for LLM inference. Follow the configuration steps below to obtain an API key and wire it into the application.

## 📋 Table of Contents

- [Project Overview](#project-overview)
- [Agent &amp; Tool Design](#agent--tool-design)
- [Prerequisites](#prerequisites)
- [Detailed Setup Guide](#detailed-setup-guide)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Project Structure](#project-structure)
- [API Usage](#api-usage)

# Project Overview

## Architectural Approach

```
[FastAPI Server] → [Agent Coordinator] → [Tool Chain] → [LLM (Gemini hosted)] → [MySQL]
```

- **FastAPI Layer**: Handles HTTP requests, input validation, and response formatting
- **Agent Coordinator**: Orchestrates the analysis workflow and tool selection
- **Tool Chain**: Specialized tools for different analysis aspects
- **LLM Layer**: Primary integration with Google's Gemini (Generative Language API). The project also includes an optional local LLM adapter using Ollama for on-prem or offline usage (see `app/llm/gemini_llm.py` and `app/llm/ollama_llm.py`).
- **Storage Layer**: MySQL for persistent storage and audit trails

## Design Choices

1. **Hosted LLM Processing (Gemini)**:

   - Using Gemini via Google's Generative Language API for high-quality LLM responses
   - Requires an API key (create at https://aistudio.google.com/api-keys) and configuration in `.env`
   - Easier to scale and keep up-to-date with model improvements
2. **Modular Tool Design**:

   - Each tool is self-contained with clear responsibilities
   - Easy to extend or modify individual components
   - Tools can be tested and debugged independently
3. **Async Processing**:

   - FastAPI's async support for handling multiple requests
   - Non-blocking database operations
   - Efficient document processing pipeline
4. **Data Persistence**:

   - MySQL for structured data storage
   - Audit trail of all analyses
   - Easy retrieval of historical forecasts

# Agent & Tool Design

## 1. Master Agent Prompt

The agent uses this core prompt template:

```text
You are a financial analysis expert tasked with creating a forecast for TCS.
Your goal is to provide a well-reasoned forecast based on available data.

You have access to these tools:
1. FinancialDataExtractorTool: Extract metrics from financial reports
2. QualitativeAnalysisTool: Analyze earnings calls and management commentary

Process:
1. Gather financial metrics for past quarters
2. Identify trends and patterns
3. Analyze management commentary for forward-looking statements
4. Synthesize findings into a structured forecast

Constraints:
- Always cite sources for claims
- Provide confidence scores (0-1) for predictions
- Format output as specified JSON
- Handle missing data gracefully
```

## 2. Tool Specifications

### FinancialDataExtractorTool

- **Purpose**: Extract key financial metrics from PDF reports
- **Capabilities**:
  - Parse structured financial tables
  - Extract specific metrics (revenue, profit, margins)
  - Handle different PDF formats

### QualitativeAnalysisTool

- **Purpose**: Analyze textual content from earnings calls
- **Capabilities**:
  - Semantic search across transcripts
  - Sentiment analysis of management comments
  - Theme extraction and categorization

## 3. Agent Chain Flow

1. **Input Processing**:

   - Validate user parameters
   - Initialize agent with tools
   - Set up execution context
2. **Document Gathering**:

   - Fetch financial reports
   - Fetch earnings transcripts
   - Validate document integrity
3. **Analysis Chain**:

   - Extract financial metrics
   - Analyze trends
   - Process qualitative insights
   - Synthesize forecast

## 4. Error Handling & Retries

- **Document Fetching**:

  - Retry failed downloads (max 3 attempts)
  - Fall back to cached copies if available
- **Metric Extraction**:

  - Multiple parsing strategies
  - Confidence scoring for extracted values
- **LLM Interactions**:

  - Temperature adjustment for more focused output
  - Output validation with JSON schema
  - Automatic retry with adjusted prompts

## Prerequisites

* Windows 10/11 or later
* Python 3.10 or higher
* MySQL 8.0
* Ollama
* Virtual environment recommended

## Detailed Setup Guide

### 1. Installing MySQL

1. Download MySQL Installer:

   - Go to [MySQL Downloads](https://dev.mysql.com/downloads/installer/)
   - Download "Windows (x86, 32-bit), MSI Installer"
2. Install MySQL:

   - Run the downloaded installer
   - Choose "Custom" installation
   - Select:
     - MySQL Server 8.0.x
     - MySQL Workbench
   - Click "Next" and "Execute"
   - Choose "Standalone MySQL Server"
   - Set root password:  (or your choice)
   - Keep other default settings
3. Verify MySQL Installation:

   - Open Command Prompt
   - Run: `mysql --version`
   - Should show MySQL 8.0.x
4. Create Database:

   - Open MySQL Workbench
   - Connect to localhost (user: root, password: your_password)
   - Run this SQL:
     ```sql
     CREATE DATABASE tcs_forecast;
     ```

### 2. Configuring Gemini (Google Generative API)

1. Create an API Key:

   - Go to https://aistudio.google.com/api-keys and create an API key for the Generative Language API.
2. Add the API key to your `.env` file:

   - Open the project's `.env` file and add the following entry (replace with your key):

     GEMINI_API_KEY=YOUR_GEMINI_API_KEY
   - Also ensure the `BASE_URL` and `GEMINI_MODEL` variables are present. Example:

     BASE_URL=https://generativelanguage.googleapis.com/v1beta/
     GEMINI_MODEL=models/gemma-3-27b-it
   - The app expects `GEMINI_API_KEY` to contain the API key used to authenticate requests to the Generative Language API. If you want to run a local model instead, you can configure the Ollama adapter (see `app/llm/ollama_llm.py`).
3. Notes on usage:

   - This project provides an integration module at `app/llm/gemini_llm.py` which uses the configured `BASE_URL`, `GEMINI_MODEL`, and `GEMINI_API` to call Gemini.
   - Keep your API key secret. Do not commit real keys to public repositories.

### 3. Python Setup

1. Install Python:

   - Download Python 3.10+ from [python.org](https://www.python.org/downloads/)
   - Check "Add Python to PATH" during installation
2. Verify Python:

   - Open new Command Prompt
   - Run: `python --version`
   - Should show Python 3.10.x or higher

## Installation

1. Clone the repository:

   ```cmd
   git clone https://github.com/ankurkrr/Financial-Analysis-Agents.git
   ```
2. Create virtual environment:

   ```cmd
   python -m venv venv
   venv\Scripts\activate
   ```
3. Install dependencies:

   ```cmd
   pip install -r requirements.txt
   ```

## Configuration

1. Setup environment variables:

   - Create or edit `.env` file:
     ```
     MYSQL_HOST=localhost
     MYSQL_PORT=3306
     MYSQL_USER=root
     MYSQL_PASSWORD=
     MYSQL_DB=tcs_forecast
     MYSQL_URL=mysql+pymysql://root:password@localhost:3306/forecast_db
     API_HOST=0.0.0.0
     API_PORT=8082

     GEMINI_API_KEY=

     BASE_URL=https://generativelanguage.googleapis.com/v1beta/
     GEMINI_MODEL=models/gemma-3-27b-it

     EMBEDDING_MODEL=all-MiniLM-L6-v2

     TESSERACT_CMD=/usr/bin/tesseract
     ```

   GEMINI_API_KEY=
   BASE_URL=https://generativelanguage.googleapis.com/v1beta/
   GEMINI_MODEL=models/gemma-3-27b-it

   # Embeddings

   EMBEDDING_MODEL=all-MiniLM-L6-v2

   # Tesseract (if using OCR)

   TESSERACT_CMD=/usr/bin/tesseract
   API_HOST=0.0.0.0
   API_PORT=8082


   ```

   ```

## Running the Application

### 1. Ensure Services are Running

1. Check MySQL is running:

   - Open Services (Win + R, type 'services.msc')
   - Find "MySQL80"
   - Status should be "Running"
   - If not, right-click → Start
2. Start the Application (no local Ollama required):
3. Open new Command Prompt
4. Navigate to project directory
5. Activate virtual environment:

   ```cmd
   venv\Scripts\activate
   ```
6. Start FastAPI server:

   ```cmd
   uvicorn app.main:app --host 0.0.0.0 --port 8082 --reload
   ```

### 2. Start the Application

1. Open new Command Prompt
2. Navigate to project directory
3. Activate virtual environment:
   ```cmd
   venv\Scripts\activate
   ```
4. Start FastAPI server:
   ```cmd
   uvicorn app.main:app --host 0.0.0.0 --port 8082 --reload
   ```

### 3. Verify Setup

1. Open browser: http://localhost:8082/docs
2. Check health endpoint: http://localhost:8082/health
3. Test forecast endpoint with sample request:
   POST http://localhost:8082/health
   ```json
   header key:content-type, value:application/json

   raw-json
   {
       "quarters": 3,
       "sources": ["screener", "company-ir"]
   }
   ```

### Troubleshooting

1. MySQL Connection Issues:

   - Verify MySQL is running
   - Check password in `.env`
   - Try connecting with MySQL Workbench
2. Gemini / API Issues:

   - Ensure `GEMINI_API` is set in `.env` and is valid
   - Verify `BASE_URL` and `GEMINI_MODEL` are set correctly in `.env`
   - Check that your network permits outbound calls to the Generative Language API endpoint
   - Look for API errors in the server logs (invalid key, rate limits, or permission issues)
3. API Issues:

   - Check all environment variables
   - Look for errors in terminal
   - Verify port 8082 is free

## Project Structure

```
app/
├── api/
│   └── endpoints.py        # FastAPI routes
├── agents/
│   └── forecast_agent.py   # Main agent logic
├── tools/
│   ├── financial_extractor_tool.py
│   └── qualitative_analysis_tool.py
├── llm/
│   ├── gemini_llm.py       # Gemini (Google Generative Language API) integration
├── db/
│   └── mysql_client.py     # Database operations
├── utils/
│   ├── document_chunker.py
│   └── number_parsing.py
└── main.py                # Application entry point
```

## API Usage

### GET /health

Health check endpoint to verify service status

### POST /api/forecast

Generate a forecast based on recent financial documents

Request body:

```json
{
    "quarters": 3,
    "sources": ["screener", "company-ir"]
}
```

Response:

```json
{
    "forecast": {
        "metrics": {
            "revenue_growth": "12.3%",
            "operating_margin": "25.1%",
            "net_profit": "10500 Cr"
        },
        "qualitative_analysis": {
            "outlook": "positive",
            "key_themes": [
                "Digital transformation",
                "Cloud adoption",
                "Cost optimization"
            ]
        },
        "confidence_scores": {
            "metrics": 0.85,
            "analysis": 0.78
        }
    },
    "metadata": {
        "source_documents": ["Q2_2023.pdf", "Q1_2023.pdf"],
        "processing_time": "2.3s"
    }
}
```
