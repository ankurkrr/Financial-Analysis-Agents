# Project Architecture & Design

## Project Overview

This TCS Financial Forecasting Agent is built with a modular, event-driven architecture that combines several specialized components:

### 1. Architectural Approach

```
[FastAPI Server] → [Agent Coordinator] → [Tool Chain] → [LLM (Ollama)] → [MySQL]
```

- **FastAPI Layer**: Handles HTTP requests, input validation, and response formatting
- **Agent Coordinator**: Orchestrates the analysis workflow and tool selection
- **Tool Chain**: Specialized tools for different analysis aspects
- **LLM Layer**: Local Ollama instance running llama2-3b
- **Storage Layer**: MySQL for persistent storage and audit trails

### 2. Design Choices

1. **Local LLM Processing**:
   - Using Ollama with llama2-3b for complete data privacy
   - Local processing eliminates API costs and latency
   - Suitable for sensitive financial analysis

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

## Agent & Tool Design

### 1. Master Agent Prompt

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

### 2. Tool Specifications

#### FinancialDataExtractorTool
- **Purpose**: Extract key financial metrics from PDF reports
- **Capabilities**:
  - Parse structured financial tables
  - Extract specific metrics (revenue, profit, margins)
  - Handle different PDF formats
- **Implementation**:
  ```python
  class FinancialDataExtractorTool(BaseTool):
      name = "financial_data_extractor"
      description = "Extract financial metrics from quarterly reports"
      
      def process_document(self, pdf_path):
          # Multi-stage extraction:
          # 1. Try table extraction
          # 2. Fall back to text parsing
          # 3. Use pattern matching for specific metrics
  ```

#### QualitativeAnalysisTool
- **Purpose**: Analyze textual content from earnings calls
- **Capabilities**:
  - Semantic search across transcripts
  - Sentiment analysis of management comments
  - Theme extraction and categorization
- **Implementation**:
  ```python
  class QualitativeAnalysisTool(BaseTool):
      name = "qualitative_analyzer"
      description = "Analyze earnings call transcripts for insights"
      
      def analyze_transcript(self, text):
          # Processing steps:
          # 1. Text chunking
          # 2. Semantic embedding
          # 3. Theme clustering
          # 4. Sentiment scoring
  ```

### 3. Agent Chain Flow

1. **Input Processing**:
   ```mermaid
   graph TD
   A[User Request] --> B[Validate Parameters]
   B --> C[Initialize Agent]
   C --> D[Load Tools]
   ```

2. **Document Gathering**:
   ```mermaid
   graph TD
   A[Agent] --> B[Fetch Reports]
   B --> C[Fetch Transcripts]
   C --> D[Validate Documents]
   ```

3. **Analysis Chain**:
   ```mermaid
   graph TD
   A[Financial Extraction] --> B[Metric Analysis]
   B --> C[Qualitative Analysis]
   C --> D[Synthesis]
   D --> E[JSON Formation]
   ```

### 4. Error Handling & Retries

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

### 5. Data Flow

1. **Input Stage**:
   ```json
   {
     "quarters": 3,
     "sources": ["screener", "company-ir"]
   }
   ```

2. **Processing Stage**:
   - Document retrieval & validation
   - Metric extraction & verification
   - Qualitative analysis & synthesis

3. **Output Stage**:
   ```json
   {
     "forecast": {
       "metrics": {
         "revenue_growth": "12.3%",
         "operating_margin": "25.1%"
       },
       "analysis": {
         "confidence": 0.85,
         "supporting_evidence": [...]
       }
     }
   }
   ```

## Evaluation & Validation

### 1. Metric Validation
- Cross-reference extracted metrics with published reports
- Confidence scoring for extraction accuracy
- Automatic anomaly detection

### 2. Qualitative Validation
- Source attribution for insights
- Sentiment consistency checking
- Theme clustering validation

### 3. Forecast Validation
- Historical accuracy tracking
- Comparison with analyst consensus
- Confidence interval calculation