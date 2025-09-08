from agents import function_tool

##################
# Date-Time Tool #
##################
import datetime


@function_tool
def get_current_datetime() -> str:
    """
    Get the current date and time in IST.

    Returns:
        Current date and time in YYYY-MM-DD HH:MM:SS format (IST)
    """
    ist_offset = datetime.timedelta(hours=5, minutes=30)
    current_utc = datetime.datetime.now(datetime.timezone.utc)
    ist_time = current_utc + ist_offset
    return ist_time.strftime("%Y-%m-%d %H:%M:%S")
