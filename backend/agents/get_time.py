from datetime import datetime
import pytz
import json

def get_time():
    """
    Get the current date and time in IST (Asia/Kolkata).
    Returns:
        JSON string with formatted datetime (e.g., "2025-04-13 23:30:00+05:30").
    """
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist).strftime('%Y-%m-%d %H:%M:%S%z')
    return json.dumps({"datetime": current_time})