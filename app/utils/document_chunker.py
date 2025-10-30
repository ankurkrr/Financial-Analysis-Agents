"""Utility for chunking large documents to stay within token limits"""
from typing import List, Dict, Any
import tiktoken
import math

def count_tokens(text: str) -> int:
    """Count tokens in a text string using tiktoken"""
    try:
        enc = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
        return len(enc.encode(text))
    except Exception:
        # Fallback: rough estimate based on words/chars
        return len(text.split()) * 1.3  # Conservative estimate

def chunk_documents(documents: Dict[str, List[Dict[str, Any]]], 
                   max_chunk_tokens: int = 4000) -> List[Dict[str, List[Dict[str, Any]]]]:
    """Split documents into chunks that fit within token limits
    
    Args:
        documents: Dict with 'reports' and 'transcripts' lists
        max_chunk_tokens: Max tokens per chunk (default 8k leaves room for prompt)
        
    Returns:
        List of document chunks, each with the same structure as input
    """
    chunks = []
    current_chunk = {"reports": [], "transcripts": []}
    current_tokens = 0
    
    # Helper to estimate doc tokens
    def doc_tokens(doc: Dict) -> int:
        text = ""
        if "content" in doc:
            text += doc["content"]
        if "text" in doc:
            text += doc["text"]
        return count_tokens(text)
    
    # Process reports first
    for report in documents.get("reports", []):
        tokens = doc_tokens(report)
        if current_tokens + tokens > max_chunk_tokens and current_chunk["reports"]:
            chunks.append(current_chunk)
            current_chunk = {"reports": [], "transcripts": []}
            current_tokens = 0
        current_chunk["reports"].append(report)
        current_tokens += tokens
        
    # Process transcripts
    for transcript in documents.get("transcripts", []):
        tokens = doc_tokens(transcript)
        if current_tokens + tokens > max_chunk_tokens and (current_chunk["reports"] or current_chunk["transcripts"]):
            chunks.append(current_chunk)
            current_chunk = {"reports": [], "transcripts": []}
            current_tokens = 0
        current_chunk["transcripts"].append(transcript)
        current_tokens += tokens
    
    # Add final chunk if not empty
    if current_chunk["reports"] or current_chunk["transcripts"]:
        chunks.append(current_chunk)
        
    return chunks