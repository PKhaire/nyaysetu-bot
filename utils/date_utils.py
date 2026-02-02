from datetime import datetime
import uuid

def generate_case_id():
    return f"NS-{uuid.uuid4().hex[:8].upper()}"

def format_date_readable(date_str):
    """
    Converts YYYY-MM-DD -> 16 Dec 2025 (Tuesday)
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%d %b %Y (%A)")
    except Exception:
        return date_str  # safe fallback
