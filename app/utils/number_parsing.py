"""
app/utils/number_parsing.py - Fixed to handle Indian number format
"""
import re


def parse_inr_number(text: str):
    """
    Parse Indian Rupee numbers from text.
    Handles formats like:
    - ₹ 12,345.67 Cr
    - 1,23,456 (Indian format)
    - 123,456 (Western format)
    - 9876.54
    """
    if not text:
        return None
    
    # Pattern 1: ₹ symbol with number
    m = re.search(r'₹\s*([0-9,\.]+)\s*(Cr|Crore|CR|cr|Million|Mn)?', text)
    if m:
        num_str = m.group(1)
        try:
            # Remove all commas and parse
            return float(num_str.replace(',', ''))
        except:
            return None
    
    # Pattern 2: Indian number format (1,23,456 or 12,34,567)
    # Indian format has commas every 2 digits after the first 3
    m2 = re.search(r'\b([0-9]{1,3}(?:,[0-9]{2})+(?:,[0-9]{3})?)\b', text)
    if m2:
        num_str = m2.group(1)
        try:
            return float(num_str.replace(',', ''))
        except:
            return None
    
    # Pattern 3: Western number format with commas (123,456 or 1,234,567)
    m3 = re.search(r'\b([0-9]{1,3}(?:,[0-9]{3})+)\b', text)
    if m3:
        num_str = m3.group(1)
        try:
            return float(num_str.replace(',', ''))
        except:
            return None
    
    # Pattern 4: Plain number (no commas)
    m4 = re.search(r'\b([0-9]+(?:\.[0-9]+)?)\b', text)
    if m4:
        try:
            return float(m4.group(1))
        except:
            return None
    
    return None