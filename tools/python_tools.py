from agents import function_tool

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
