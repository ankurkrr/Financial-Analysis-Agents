"""
app/tools/financial_extractor_tool.py - Refactored as a proper class-based tool
"""
import os
import re
import json
from typing import List, Dict, Any, Optional
from app.utils.number_parsing import parse_inr_number
import warnings
from langchain.tools import tool
import math
from app.llm.gemini_llm import GeminiLLM

llm = GeminiLLM()

# Defer heavy optional imports (pdfplumber, pdf2image, pytesseract) to runtime
# inside the methods that need them. This avoids import-time failures in
# environments that don't have system-level deps (poppler, tesseract).
_HAS_PDFPLUMBER = False
_HAS_PDF2IMAGE = False
_HAS_PYTESSERACT = False
try:
    warnings.filterwarnings("ignore", category=UserWarning, module="camelot")
except Exception:
    pass


# Camelot import with fallback
try:
    import camelot
    _HAS_CAMELOT = True
except Exception:
    _HAS_CAMELOT = False


class FinancialDataExtractorTool:
    """
    Robust financial data extraction tool using multiple methods:
    1. Camelot table extraction (best for structured PDFs)
    2. pdfplumber text extraction (fallback)
    3. OCR with pytesseract (last resort)
    """
    
    def __init__(self):
        self.extraction_methods = ["camelot", "pdfplumber", "ocr"]
        
    def extract(self, reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Main extraction method called by LangChain agent
        
        Args:
            reports: List of report dicts with 'local_path', 'name', 'source_url'
            
        Returns:
            Structured dict with extracted metrics and metadata
        """
        results = []
        
        for report in reports:
            path = report.get("local_path")
            if not path or not os.path.exists(path):
                results.append({
                    "doc_meta": report,
                    "error": "file_not_found",
                    "metrics": {}
                })
                continue
            
            # Extract from this report
            extraction_result = self._extract_from_single_report(path, report)
            results.append(extraction_result)
        
        return {
            "tool": "FinancialDataExtractorTool",
            "status": "completed",
            "reports_processed": len(results),
            "results": results
        }
    
    def _extract_from_single_report(self, pdf_path: str, metadata: Dict) -> Dict[str, Any]:
        """Extract metrics from a single PDF report"""
        
        metrics = {}
        extraction_log = {
            "camelot": {"attempted": False, "metrics_found": 0, "hits": []},
            "pdfplumber": {"attempted": False, "metrics_found": 0, "snippets": []},
            "ocr": {"attempted": False, "metrics_found": 0, "text_length": 0}
        }
        
        # Method 1: Camelot table extraction
        if _HAS_CAMELOT:
            extraction_log["camelot"]["attempted"] = True
            camelot_metrics = self._extract_with_camelot(pdf_path)
            for metric in camelot_metrics:
                key = self._normalize_metric_key(metric["label"])
                if key and key not in metrics:
                    metrics[key] = {
                        "value": metric["value"],
                        "unit": metric.get("unit", "INR_Cr"),
                        "confidence": metric.get("confidence", 0.85),
                        "source": {"method": "camelot", "page": metric.get("page")},
                        "label": metric["label"]
                    }
                    extraction_log["camelot"]["metrics_found"] += 1
            extraction_log["camelot"]["hits"] = camelot_metrics
        
        # Method 2: pdfplumber text extraction (if key metrics still missing)
        required_metrics = ["total_revenue", "net_profit", "operating_profit", "ebitda"]
        missing_metrics = [m for m in required_metrics if m not in metrics]
        
        if missing_metrics:
            extraction_log["pdfplumber"]["attempted"] = True
            text = self._extract_text_with_pdfplumber(pdf_path)
            if text:
                pdfplumber_metrics = self._parse_metrics_from_text(text)
                for metric in pdfplumber_metrics:
                    key = self._normalize_metric_key(metric["label"])
                    if key and key in missing_metrics and key not in metrics:
                        metrics[key] = {
                            "value": metric["value"],
                            "unit": metric.get("unit", "INR_Cr"),
                            "confidence": 0.65,
                            "source": {"method": "pdfplumber"},
                            "label": metric["label"]
                        }
                        extraction_log["pdfplumber"]["metrics_found"] += 1
                
                extraction_log["pdfplumber"]["snippets"] = pdfplumber_metrics[:5]
        
        # Method 3: OCR (last resort if still missing critical metrics)
        critical_missing = any(m not in metrics for m in ["total_revenue", "net_profit"])
        if critical_missing:
            extraction_log["ocr"]["attempted"] = True
            ocr_text = self._extract_with_ocr(pdf_path, max_pages=5)
            if ocr_text:
                extraction_log["ocr"]["text_length"] = len(ocr_text)
                ocr_metrics = self._parse_metrics_from_text(ocr_text)
                for metric in ocr_metrics:
                    key = self._normalize_metric_key(metric["label"])
                    if key and key not in metrics:
                        metrics[key] = {
                            "value": metric["value"],
                            "unit": metric.get("unit", "INR_Cr"),
                            "confidence": 0.45,
                            "source": {"method": "ocr"},
                            "label": metric["label"]
                        }
                        extraction_log["ocr"]["metrics_found"] += 1
        
        return {
            "doc_meta": metadata,
            "metrics": metrics,
            "extraction_log": extraction_log,
            "metrics_count": len(metrics)
        }
    
    def _extract_with_camelot(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Use Camelot to extract table data"""
        results = []
        
        try:
            # Try both lattice and stream flavors
            tables = []
            for flavor in ['lattice', 'stream']:
                try:
                    tables.extend(camelot.read_pdf(pdf_path, pages='all', flavor=flavor))
                except Exception:
                    pass
            
            for table in tables:
                df = table.df
                page = table.page
                
                # Scan for financial metric labels
                for r_idx in range(df.shape[0]):
                    for c_idx in range(df.shape[1]):
                        cell = str(df.iat[r_idx, c_idx])
                        
                        # Check if this cell contains a financial label
                        if self._is_financial_label(cell):
                            # Look for numeric value in same row (to the right)
                            numeric_val = None
                            for k in range(c_idx + 1, min(df.shape[1], c_idx + 5)):
                                candidate = str(df.iat[r_idx, k])
                                val = parse_inr_number(candidate)
                                if val is not None:
                                    numeric_val = val
                                    break
                            
                            # Also check same column (below)
                            if numeric_val is None:
                                for k in range(r_idx + 1, min(df.shape[0], r_idx + 3)):
                                    candidate = str(df.iat[k, c_idx])
                                    val = parse_inr_number(candidate)
                                    if val is not None:
                                        numeric_val = val
                                        break
                            
                            if numeric_val is not None:
                                results.append({
                                    "label": cell.strip(),
                                    "value": numeric_val,
                                    "unit": "INR_Cr",
                                    "page": page,
                                    "confidence": 0.85
                                })
        except Exception:
            pass
        
        return results
    
    def _extract_text_with_pdfplumber(self, pdf_path: str) -> str:
        """Extract text using pdfplumber"""
        text = ""
        try:
            # Lazy import pdfplumber
            try:
                import pdfplumber
            except Exception:
                return text

            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages[:10]:  # Limit to first 10 pages
                    page_text = page.extract_text()
                    if page_text:
                        text += "\n\n" + page_text
        except Exception:
            pass
        return text
    
    def _extract_with_ocr(self, pdf_path: str, dpi: int = 200, max_pages: int = 5) -> str:
        """Extract text using OCR (slowest method)"""
        text = ""
        try:
            # Lazy imports
            try:
                from pdf2image import convert_from_path
            except Exception:
                return text

            try:
                import pytesseract
            except Exception:
                return text

            pages = convert_from_path(pdf_path, dpi=dpi)
            for page in pages[:max_pages]:
                try:
                    page_text = pytesseract.image_to_string(page)
                    text += "\n\n" + page_text
                except Exception:
                    continue
        except Exception:
            pass
        return text
    
    def _parse_metrics_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Parse financial metrics from plain text"""
        metrics = []
        
        # Common financial labels to search for
        labels = [
            "Total Revenue", "Revenue", "Net Revenue",
            "Net Profit", "Profit After Tax", "PAT",
            "Operating Profit", "EBIT", "Operating Income",
            "EBITDA",
            "EPS", "Earnings Per Share"
        ]
        
        for label in labels:
            # Find label in text (case insensitive)
            pattern = re.escape(label)
            match = re.search(pattern, text, re.IGNORECASE)
            
            if match:
                # Extract surrounding context (next 300 chars)
                start = match.start()
                context = text[start:start + 300]
                
                # Try to find a number in this context
                value = parse_inr_number(context)
                if value is not None:
                    metrics.append({
                        "label": label,
                        "value": value,
                        "unit": "INR_Cr",
                        "context": context[:150]
                    })
        
        return metrics

    def extract_metrics_from_text(self, text: str) -> Dict[str, Any]:
        """Robust regex-based extractor for key financial metrics from free text.

        Returns a dict mapping normalized metric keys to values and metadata.
        """
        patterns = {
            "total_revenue": r"(?i)(?:revenue from operations|total income|total revenue|revenue).*?([\d,\.]+)\s*(crore|million|inr|₹)?",
            "net_profit": r"(?i)(?:net profit|profit after tax|pat).*?([\d,\.]+)\s*(crore|million|inr|₹)?",
            "operating_margin": r"(?i)(?:operating margin|ebit margin).*?([\d\.]+)\s*%",
            "net_profit_margin": r"(?i)(?:net profit margin|profit margin).*?([\d\.]+)\s*%",
            "eps": r"(?i)\b(?:eps|earnings per share)\b.*?([\d\.]+)",
            "ebitda": r"(?i)(?:ebitda|earnings before interest).*?([\d,\.]+)\s*(crore|inr|₹)?",
            "roe": r"(?i)(?:return on equity|roe).*?([\d\.]+)\s*%",
            "free_cash_flow": r"(?i)(?:free cash flow|fcf).*?([\d,\.]+)\s*(crore|inr|₹)?",
            "debt_to_equity": r"(?i)(?:debt[-\s]*to[-\s]*equity|d/?e).*?([\d\.]+)"
        }

        found = {}
        for key, pattern in patterns.items():
            m = re.search(pattern, text)
            if m:
                raw = m.group(1)
                unit_raw = None
                try:
                    unit_raw = m.group(2)
                except Exception:
                    unit_raw = None

                # Try parse using existing helper
                val = parse_inr_number(raw)
                if val is None:
                    # fallback: remove commas and try float
                    try:
                        val = float(raw.replace(",", ""))
                    except Exception:
                        val = None

                if val is not None and isinstance(val, (int, float)) and (not math.isnan(val)):
                    # Normalize units: convert million -> crore (1 crore = 10 million)
                    unit_marker = (unit_raw or "").lower() if unit_raw else ""
                    if "million" in unit_marker and key not in ["operating_margin", "net_profit_margin", "roe", "debt_to_equity"]:
                        try:
                            val = float(val) / 10.0
                        except Exception:
                            pass

                    # Default unit mapping
                    if key in ["operating_margin", "net_profit_margin", "roe"]:
                        unit = "%"
                    elif key == "debt_to_equity":
                        unit = "ratio"
                    else:
                        unit = "INR_Cr"

                    found[key] = {"value": val, "unit": unit, "confidence": 0.6}

        return {"metrics": found, "count": len(found)}

    def validate_and_enrich_metrics(self, metrics: Dict[str, Any], text: str) -> Dict[str, Any]:
        """Use the configured LLM to validate and enrich extracted metrics.

        This method will attempt to call the LLM obtained from get_llm(). If the
        LLM call fails, it will attempt lightweight deterministic enrichments
        (e.g., compute margins where possible).
        """
        # Normalize input metrics
        metrics = metrics or {}

        # Build prompt for the LLM
        prompt = f"""
You are a financial data assistant. Given extracted metrics: {json.dumps(metrics)}
and the report text (first 4000 chars):\n
{text[:4000]}

Please:
1) Return a JSON object with cleaned numeric values (numbers only) for keys: total_revenue, net_profit, operating_profit, ebitda, eps, roe, free_cash_flow, debt_to_equity, operating_margin, net_profit_margin.
2) If a margin is missing and you can compute it (e.g., operating_margin = operating_profit / total_revenue * 100), compute and include it.
3) Standardize units to crore (INR_Cr) or percentages where appropriate.
4) Provide a "notes" field indicating any assumptions.

Return ONLY valid JSON.
"""

        llm = None
        try:
            llm = get_llm()
            raw = llm._call(prompt)
            try:
                parsed = json.loads(raw)
                return {"status": "ok", "metrics": parsed}
            except Exception:
                # LLM returned non-JSON; fallthrough to fallback behavior
                pass
        except Exception as e:
            # LLM not available or failed; continue to deterministic enrichment
            pass

        # Fallback deterministic enrichments
        enriched = dict(metrics)  # shallow copy

        # Try compute operating_margin if missing and we have operating_profit and total_revenue
        try:
            if "operating_margin" not in enriched and "operating_profit" in enriched and "total_revenue" in enriched:
                op = float(enriched["operating_profit"]["value"]) if isinstance(enriched["operating_profit"], dict) else float(enriched["operating_profit"])
                rev = float(enriched["total_revenue"]["value"]) if isinstance(enriched["total_revenue"], dict) else float(enriched["total_revenue"])
                if rev != 0:
                    enriched["operating_margin"] = {"value": (op / rev) * 100, "unit": "%", "confidence": 0.5}
        except Exception:
            pass

        # Compute simple rate-of-change (QoQ) if previous period values are supplied
        try:
            for base_key in ["total_revenue", "net_profit", "ebitda"]:
                prev_key = f"{base_key}_prev"
                if base_key in enriched and prev_key in enriched:
                    cur_val = enriched[base_key]["value"] if isinstance(enriched[base_key], dict) else enriched[base_key]
                    prev_val = enriched[prev_key]["value"] if isinstance(enriched[prev_key], dict) else enriched[prev_key]
                    try:
                        cur = float(cur_val)
                        prev = float(prev_val)
                        if prev != 0:
                            pct = ((cur - prev) / abs(prev)) * 100.0
                            enriched[f"{base_key}_qoq_pct"] = {"value": pct, "unit": "%", "confidence": 0.5}
                    except Exception:
                        continue
        except Exception:
            pass

        # Normalize nested structures to simple dict format
        cleaned = {}
        for k, v in enriched.items():
            if isinstance(v, dict) and "value" in v:
                cleaned[k] = {"value": v["value"], "unit": v.get("unit", "INR_Cr"), "confidence": v.get("confidence", 0.5)}
            else:
                # best-effort
                try:
                    cleaned[k] = {"value": float(v), "unit": "INR_Cr", "confidence": 0.4}
                except Exception:
                    continue

        return {"status": "fallback", "metrics": cleaned, "notes": "LLM unavailable or returned non-JSON; used deterministic enrichment"}

    
    def _is_financial_label(self, text: str) -> bool:
        """Check if text looks like a financial metric label"""
        if not text or len(text) < 3:
            return False
        
        text_lower = text.lower()
        keywords = [
            "revenue", "profit", "income", "ebitda", "ebit",
            "margin", "earnings", "eps", "pat", "sales"
        ]
        
        return any(keyword in text_lower for keyword in keywords)
    
    def _normalize_metric_key(self, label: str) -> Optional[str]:
        """Normalize various label formats to standard metric keys"""
        if not label:
            return None
        
        label_lower = label.lower()
        
        # Revenue
        if "revenue" in label_lower or "sales" in label_lower:
            return "total_revenue"
        
        # Net Profit
        if ("net" in label_lower and "profit" in label_lower) or "pat" in label_lower or "profit after tax" in label_lower:
            return "net_profit"
        
        # Operating Profit
        if ("operating" in label_lower and ("profit" in label_lower or "income" in label_lower)) or label_lower == "ebit":
            return "operating_profit"
        
        # EBITDA
        if "ebitda" in label_lower:
            return "ebitda"
        
        # EPS
        if "eps" in label_lower or "earnings per share" in label_lower:
            return "eps"
        
        # Operating Margin
        if "operating" in label_lower and "margin" in label_lower:
            return "operating_margin"
        
        return None


# Legacy function wrapper for backward compatibility
def extract_financial_data(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Legacy function - delegates to the class-based tool"""
    tool = FinancialDataExtractorTool()
    return tool.extract(reports)


@tool("extract_financial_metrics", return_direct=True)
def extract_financial_metrics(text: str) -> dict:
    """LangChain tool wrapper: extract financial metrics from free text.

    Returns a dict: {"metrics": {...}, "count": N}
    """
    extractor = FinancialDataExtractorTool()
    try:
        return extractor.extract_metrics_from_text(text)
    except Exception as e:
        return {"error": str(e)}


@tool("validate_and_enrich_metrics", return_direct=True)
def validate_and_enrich_metrics_tool(metrics_input: str, text: str) -> dict:
    """LangChain tool wrapper: validate/enrich metrics using configured LLM.

    metrics_input can be a JSON string or a dict.
    """
    extractor = FinancialDataExtractorTool()
    try:
        if isinstance(metrics_input, str):
            try:
                metrics = json.loads(metrics_input)
            except Exception:
                # fallback: treat as empty
                metrics = {}
        else:
            metrics = metrics_input

        return extractor.validate_and_enrich_metrics(metrics, text)
    except Exception as e:
        return {"error": str(e)}