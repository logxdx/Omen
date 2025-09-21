# python_executor.py
# -*- coding: utf-8 -*-
"""Standalone Python execution helper.
Provides:
 - execute_python_code_sync(code, timeout) -> str (XML string)
 - execute_python_code_async(code, timeout) -> str (XML string)

XML format returned:
<result>
  <returncode>...</returncode>
  <timed_out>True|False</timed_out>
  <output>...escaped output...</output>
  <error>...escaped stderr...</error>
</result>
"""

import asyncio
import sys
import tempfile
import os
from typing import Optional
import uuid
import subprocess
from xml.sax.saxutils import escape as xml_escape


def _wrap_xml(
    returncode: Optional[int],
    stdout: Optional[str],
    stderr: Optional[str],
    timed_out: Optional[bool],
) -> str:
    """Wrap the results into an XML string, escaping text content."""
    output = ""

    if returncode is not None:
        output += f"<returncode>{str(returncode)}</returncode>\n"
    if timed_out is not None:
        output += f"<timed_out>{str(timed_out)}</timed_out>\n"
    if stdout is not None:
        output += f"<output>\n{xml_escape(stdout)}\n</output>\n"
    if stderr is not None:
        output += f"<error>\n{xml_escape(stderr)}\n</error>\n"

    return f"<result>\n{output}</result>"


async def execute_python_code_async(code: str, timeout: float = 300.0) -> str:
    """
    Execute python code asynchronously in a temporary file.
    Returns: XML-formatted string containing returncode, output, error, timed_out.
    """
    # Create a temporary directory so the file is automatically removed when closed
    with tempfile.TemporaryDirectory() as tmpdir:
        filename = os.path.join(tmpdir, f"tmp_{uuid.uuid4().hex}.py")
        # Write code to temp file
        with open(filename, "w", encoding="utf-8") as f:
            f.write(code)

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            filename,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        timed_out = False
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
            stdout_bytes, stderr_bytes = await proc.communicate()
            returncode = proc.returncode
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            timed_out = True
            # Try to terminate the process cleanly
            try:
                proc.terminate()
            except Exception:
                pass
            # Wait a short moment for termination then read whatever we can
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
            stdout_bytes, stderr_bytes = await proc.communicate()
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            # Annotate stderr with timeout message if not present
            tm_msg = f"\nTimeoutError: execution exceeded timeout of {timeout} seconds."
            if tm_msg.strip() not in stderr:
                stderr = stderr + tm_msg
            returncode = -1

        return _wrap_xml(returncode, stdout, stderr, timed_out)


def execute_python_code(code: str, timeout: float = 300.0) -> str:
    """
    Execute python code synchronously in a temporary file.
    Returns: XML-formatted string containing returncode, output, error, timed_out.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        filename = os.path.join(tmpdir, f"tmp_{uuid.uuid4().hex}.py")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(code)

        timed_out = False
        try:
            completed = subprocess.run(
                [sys.executable, "-u", filename],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
                text=True,
            )
            returncode = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            # subprocess.TimeoutExpired may have partial output depending on platform
            stdout = (
                exc.stdout.decode("utf-8", errors="replace")
                if isinstance(exc.stdout, (bytes, bytearray))
                else ""
            )
            stderr = (
                exc.stderr.decode("utf-8", errors="replace")
                if isinstance(exc.stderr, (bytes, bytearray))
                else ""
            )
            tm_msg = f"\nTimeoutError: execution exceeded timeout of {timeout} seconds."
            if tm_msg.strip() not in stderr:
                stderr = stderr + tm_msg
            returncode = -1

        return _wrap_xml(returncode, stdout, stderr, timed_out)


# Convenience wrapper to call async from sync contexts easily
def execute_python_code_sync(
    code: str, timeout: float = 300.0, *, prefer_async: bool = False
) -> str:
    """
    Unified entry point.
      - prefer_async=False (default): runs synchronously (blocking)
      - prefer_async=True: runs using asyncio (will create/run an event loop)
    Returns XML string.
    """
    if prefer_async:
        # If there's already an active loop, caller should call execute_python_code_async directly.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Can't call asyncio.run inside a running loop; caller should call the async function.
            raise RuntimeError(
                "An active asyncio event loop is running. Call execute_python_code_async() "
                "directly from async code instead of execute_python_code(..., prefer_async=True)."
            )
        return asyncio.run(execute_python_code_async(code, timeout=timeout))
    else:
        return execute_python_code_sync(code, timeout=timeout)


# Example usage when run as a script
if __name__ == "__main__":
    sample_code = 'print("Hello from sandboxed runner")\nimport sys\nprint("stderr example", file=sys.stderr)\n'
    print("Synchronous run result:")
    print(execute_python_code(sample_code, timeout=5.0))

    print("\nAsynchronous run result:")
    print(asyncio.run(execute_python_code_async(sample_code, timeout=5.0)))
