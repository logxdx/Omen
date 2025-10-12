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


##################
# Code Execution #
##################

from tools.utils.code_execution import execute_python_code


@function_tool
def execute_code(code: str, timeout: int = 120) -> str:
    """
    Executes the given Python code and returns the output or error message in xml format.

    Args:
        code (str): The Python code to execute.
        timeout (int): The maximum time in seconds to wait for the code execution (Default: 120).

    Returns:
        str: The output of the code execution or an error message.
    """
    return execute_python_code(code, timeout=timeout)


MISC_TOOLS = [get_current_datetime, execute_code]
