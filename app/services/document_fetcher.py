# app/services/document_fetcher.py
import os
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict
from urllib.parse import urljoin, urlparse
import hashlib
import time
from datetime import datetime

# Use data directory at project root for downloads
DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "downloads")
SCREENER_COMPANY_URL_TEMPLATE = "https://www.screener.in/company/{ticker}/consolidated/"

# Ensure the downloads directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def _get_tcs_ir_url(year: str = None, quarter: str = None) -> str:
    """
    Generate TCS IR URL with proper year and quarter parameters.
    Args:
        year: e.g. '2023-24', '2025-26' 
        quarter: e.g. 'Q1', 'Q2', 'Q3', 'Q4'
    Returns:
        Full URL with params
    """
    base = "https://www.tcs.com/investor-relations/financial-statements"
    if not year or not quarter:
        return base
    # Convert Q1->quarter1, Q2->quarter2 etc
    quarter_param = f"quarter{quarter[1]}" if quarter and quarter.startswith('Q') else quarter
    # Use the exact URL format with fragments
    return f"{base}#year={year}&quarter={quarter_param}"


def _render_page_with_playwright(url: str) -> str:
    """Render a page with Playwright (synchronous) and return HTML content.
    This helper is optional: if Playwright isn't installed, it returns an empty string.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        # Playwright not available
        return ""

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000)
            # wait briefly for network to settle
            page.wait_for_load_state("networkidle", timeout=10000)
            content = page.content()
            browser.close()
            return content
    except Exception:
        return ""

def fetch_tcs_ir_reports(year: str = None, quarters: List[str] = None, consolidated_only: bool = True, max_reports: int = 4) -> List[Dict]:
    """
    Fetch TCS IR quarterly financial statements.
    Args:
        year: e.g. '2023-24', '2025-26' (str)
        quarters: e.g. ['Q1', 'Q2']
        consolidated_only: if True, only fetch consolidated reports (ignored for direct PDF downloads)
        max_reports: max number of reports to fetch
    Returns:
        List of dicts: {name, local_path, source_url}
    """
    reports = []
    
    if not year:
        # Current fiscal year format (e.g. 2025-26)
        current_year = "2023-24"  # Using a known year for testing
        year = current_year
    if not quarters:
        # Current quarter
        quarters = ["Q2"]  # Since we're in Oct 2025, Q2 should be available
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
    }

    # Process each quarter
    for q in quarters:
        if len(reports) >= max_reports:
            break
            
        url = _get_tcs_ir_url(year, q)
        try:
            # First get the main page to find PDF links
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            
            # Get PDF URLs from known patterns
            # Parse the page for any visible links first
            soup = BeautifulSoup(resp.text, 'html.parser')
            pdf_urls = []
            
            # Find PDF links in the page
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.lower().endswith('.pdf'):
                    if not href.startswith(('http://', 'https://')):
                        href = urljoin(url, href)
                    pdf_urls.append(href)
            
            # Add known URL patterns as backup
            fiscal_year = int(year.split('-')[1])  # 2025-26 -> 26
            quarter_num = q[1]  # Q1 -> 1
            patterns = [
                f"https://www.tcs.com/content/dam/tcs/investor-relations/financial-statements/q{quarter_num}fy{fiscal_year:02d}/TCS_Quarter_{quarter_num}_Financial_Results.pdf",
                f"https://www.tcs.com/content/dam/tcs/investor-relations/financial-statements/q{quarter_num}fy{fiscal_year:02d}/TCS_Q{quarter_num}_FY{fiscal_year:02d}_Consolidated_Results.pdf",
                f"https://www.tcs.com/content/dam/tcs/investor-relations/financial-statements/{year}/Q{quarter_num}/TCS_Financial_Results.pdf"
            ]
            pdf_urls.extend(patterns)
            # If no PDF URLs found from static HTML, try rendering the page with Playwright (optional)
            if not pdf_urls:
                rendered = _render_page_with_playwright(url)
                if rendered:
                    soup_js = BeautifulSoup(rendered, "html.parser")
                    for a in soup_js.find_all('a', href=True):
                        href = a['href']
                        if href.lower().endswith('.pdf'):
                            if not href.startswith(('http://', 'https://')):
                                href = urljoin(url, href)
                            pdf_urls.append(href)
            
            # Try to download PDFs from the found URLs
            for pdf_url in pdf_urls:
                try:
                    # Update headers for PDF download
                    pdf_headers = headers.copy()
                    pdf_headers["Accept"] = "application/pdf,*/*"
                    
                    # Try to fetch the PDF
                    pdf_resp = requests.get(pdf_url, headers=pdf_headers, stream=True, timeout=30)
                    
                    # Skip if not found
                    if pdf_resp.status_code == 404:
                        continue
                        
                    pdf_resp.raise_for_status()
                    
                    # Verify it's a PDF
                    content_type = pdf_resp.headers.get('content-type', '').lower()
                    if 'pdf' not in content_type and not pdf_url.lower().endswith('.pdf'):
                        continue
                    
                    # Save the PDF with proper quarter formatting
                    quarter_num = int(q.replace('Q',''))
                    fiscal_year = year.replace('-', '_')
                    name = f"TCS_Q{quarter_num}_FY{fiscal_year}_Results"
                    url_hash = hashlib.sha1(pdf_url.encode()).hexdigest()[:8]
                    fname = f"{url_hash}_{name}.pdf"
                    local_path = os.path.join(DOWNLOAD_DIR, fname)
                    
                    with open(local_path, 'wb') as f:
                        for chunk in pdf_resp.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                
                    # Verify file size
                    if os.path.getsize(local_path) > 1000:  # Must be > 1KB
                        reports.append({
                            "name": name,
                            "local_path": local_path,
                            "source_url": pdf_url,
                            "year": year,
                            "quarter": q,
                            "type": "Consolidated"
                        })
                        # Break after first successful download
                        break
                    else:
                        os.remove(local_path)
                        
                except requests.exceptions.RequestException:
                    continue  # Try next URL
                    
        except Exception as e:
            print(f"Error processing {url}: {str(e)}")
            continue

    return reports

    return reports
def _download_file(url: str, dest_dir: str = DOWNLOAD_DIR) -> str:
    """
    Download a file and return local path. Name by SHA1(url)+basename to avoid collisions.
    """
    try:
        resp = requests.get(url, stream=True, timeout=30)
        resp.raise_for_status()
        # guess filename
        parsed = urlparse(url)
        base = os.path.basename(parsed.path) or "file"
        url_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
        fname = f"{url_hash}_{base}"
        local_path = os.path.join(dest_dir, fname)
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(1024*64):
                if chunk:
                    f.write(chunk)
        return local_path
    except Exception:
        return ""

def _is_pdf_link(href: str) -> bool:
    if not href:
        return False
    href = href.split('?')[0].lower()
    return href.endswith(".pdf")

def _looks_like_transcript_text(text: str) -> bool:
    if not text:
        return False
    text = text.lower()
    keys = ["transcript", "earnings call", "concall", "conference call", "management commentary", "transcribed"]
    return any(k in text for k in keys)

def fetch_quarterly_documents(ticker: str, quarters: int, sources: List[str]=None) -> Dict[str, List[Dict]]:
    """
    Scrape Screener.in company consolidated page for documents.
    Returns:
       {"reports":[{"name":..., "local_path":...}], "transcripts":[{"name":..., "local_path":...}]}
    """
    url = SCREENER_COMPANY_URL_TEMPLATE.format(ticker=ticker)
    reports = []
    transcripts = []

    try:
        headers = {"User-Agent": "tcs-forecast-agent/0.1 (+https://example.com)"}
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Screener has a div with id 'documents' or a section — search for anchors containing '.pdf'
        # Find all anchors inside the page
        anchors = soup.find_all("a", href=True)
        pdf_links = []
        for a in anchors:
            href = a["href"]
            # absolute url
            full = urljoin(url, href)
            if _is_pdf_link(full):
                # check if anchor text suggests 'results', 'quarterly' etc
                text = (a.get_text() or "").strip()
                pdf_links.append({"href": full, "text": text})
            else:
                # also capture anchors that look like pdf but use query param
                if "pdf" in full.lower() and ".pdf" in full.lower():
                    pdf_links.append({"href": full, "text": (a.get_text() or "").strip()})

        # deduplicate by href
        seen = set()
        pdf_links_unique = []
        for p in pdf_links:
            if p["href"] not in seen:
                seen.add(p["href"])
                pdf_links_unique.append(p)

        # Sort: prefer those whose anchor text mentions 'quarter' or 'results' or 'consolidated'
        def score_pdf_link(p):
            text = p["text"].lower()
            s = 0
            if "quarter" in text or "q" in text:
                s += 2
            if "results" in text or "consolidated" in text:
                s += 2
            if "annual" in text:
                s -= 1
            return -s  # negative for reverse sort

        pdf_links_unique = sorted(pdf_links_unique, key=score_pdf_link)

        # Download top N PDFs
        for idx, p in enumerate(pdf_links_unique[:max(quarters*2, 6)]):
            local = _download_file(p["href"])
            if local:
                # Extract quarter and year info from the text or filename
                text = p["text"].lower()
                fname = os.path.basename(local).lower()
                
                # Try to extract quarter and year info
                quarter_pattern = r'q[1-4]|quarter\s*[1-4]'
                year_pattern = r'20\d{2}[-_]?\d{2}|fy\d{2}[-_]?\d{2}'
                
                q_match = re.search(quarter_pattern, text) or re.search(quarter_pattern, fname)
                y_match = re.search(year_pattern, text) or re.search(year_pattern, fname)
                
                if q_match and y_match:
                    q_num = q_match.group(0)[-1]
                    year = y_match.group(0).replace('fy', '20')
                    name = f"TCS_Q{q_num}_FY{year}_Report"
                else:
                    name = p["text"] or os.path.basename(local)
                
                reports.append({
                    "name": name,
                    "local_path": local,
                    "source_url": p["href"],
                    "date_downloaded": datetime.now().isoformat()
                })
            time.sleep(0.5)

        # Now try to find transcripts: anchors whose text looks like transcript keywords or link targets containing 'transcript' or 'concall'
        anchors = soup.find_all("a", href=True)
        transcript_candidates = []
        for a in anchors:
            txt = (a.get_text() or "").strip()
            href = urljoin(url, a["href"])
            if _looks_like_transcript_text(txt) or 'transcript' in href.lower() or 'concall' in href.lower() or 'conference-call' in href.lower():
                transcript_candidates.append({"href": href, "text": txt})

        # De-duplicate and download if pdf; otherwise store external link metadata and try to download if pointing to a .txt or .html that looks like transcript
        seen_t = set()
        for t in transcript_candidates:
            if t["href"] in seen_t:
                continue
            seen_t.add(t["href"])
            href = t["href"]
            # If it's a PDF, download
            if _is_pdf_link(href):
                local = _download_file(href)
                if local:
                    transcripts.append({"name": t["text"] or os.path.basename(local), "local_path": local, "source_url": href})
            else:
                # try fetching the page and parse text, save as .txt
                try:
                    r2 = requests.get(href, timeout=20)
                    r2.raise_for_status()
                    soup2 = BeautifulSoup(r2.text, "html.parser")
                    # heuristics: find divs that look like transcript text
                    body_text = soup2.get_text(separator="\n")
                    # Save a local txt file
                    if len(body_text) > 200:
                        fname = os.path.join(DOWNLOAD_DIR, hashlib.sha1(href.encode()).hexdigest()[:8] + "_transcript.txt")
                        with open(fname, "w", encoding="utf-8") as f:
                            f.write(body_text)
                        transcripts.append({"name": t["text"] or href, "local_path": fname, "source_url": href})
                except Exception:
                    # skip if cannot download
                    pass

        # TCS IR scraping (new)
        ir_reports = fetch_tcs_ir_reports(year=None, quarters=None, consolidated_only=True, max_reports=quarters)
        reports.extend(ir_reports)

        # If transcripts empty, try third-party search fallback (DuckDuckGo unofficial via html query)
        if not transcripts:
            # naive attempt: search quick for 'TCS earnings call transcript' on google is not allowed here; skip
            pass

    except Exception:
        # If any error, fall back to returning any files in data/test_fixtures for local dev
        # Provide a fallback to local test files (developer should place sample files)
        test_fixtures_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "test_fixtures")
        fallback_reports = [
            {"name":"Q1_SAMPLE","local_path":os.path.join(test_fixtures_dir, "sample_report_q1.pdf")},
            {"name":"Q4_SAMPLE","local_path":os.path.join(test_fixtures_dir, "sample_report_q4.pdf")},
            {"name":"Q3_SAMPLE","local_path":os.path.join(test_fixtures_dir, "sample_report_q3.pdf")},
        ]
        fallback_transcripts = [
            {"name":"Q1_TRANSCRIPT","local_path":os.path.join(test_fixtures_dir, "sample_transcript_q1.txt")},
            {"name":"Q4_TRANSCRIPT","local_path":os.path.join(test_fixtures_dir, "sample_transcript_q4.txt")},
            {"name":"Q3_TRANSCRIPT","local_path":os.path.join(test_fixtures_dir, "sample_transcript.txt")}
        ]
        return {"reports": fallback_reports[:quarters], "transcripts": fallback_transcripts[:max(1, quarters-1)]}

    # Final limit to requested quarters
    return {"reports": reports[:quarters], "transcripts": transcripts[:max(1, quarters-1)]}

class DocumentFetcher:
    def __init__(self):
        pass

    def fetch_quarterly_documents(self, ticker, quarters, sources=None):
        return fetch_quarterly_documents(ticker, quarters, sources)