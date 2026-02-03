from datetime import datetime
import uuid

def generate_case_id():
    return f"NS-{uuid.uuid4().hex[:8].upper()}"

def format_date_readable(value):
    """
    Converts date or YYYY-MM-DD string to:
    03 Feb 2026 (Tuesday)
    """

    try:
        if isinstance(value, date):
            dt = datetime.combine(value, datetime.min.time())
        elif isinstance(value, str):
            dt = datetime.strptime(value, "%Y-%m-%d")
        else:
            return "N/A"

        return dt.strftime("%d %b %Y (%A)")

    except Exception:
        return "N/A"

