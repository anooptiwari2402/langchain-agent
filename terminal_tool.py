import subprocess
from langchain_core.tools import tool
from config import WORKSPACE_DIR
from security import is_safe_command

@tool
def execute_terminal_command(command: str) -> str:
    """
    Executes a terminal/shell command on the local machine and returns stdout and stderr.
    Use this to run test suites, execute python files, run compilers, check git status, or check packages.
    Only run safe, non-interactive commands. Do not run blocking or interactive commands (e.g. do not run 'nano', 'top', or 'ping' without bounds).
    """
    # 1. Security scan
    is_safe, error_message = is_safe_command(command)
    if not is_safe:
        return error_message

    try:
        # 2. Run with timeout to prevent hanging on interactive inputs or infinite loops
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
            timeout=30,  # 30-second hard limit
            cwd=str(WORKSPACE_DIR)  # Restrict execution folder context
        )

        output = []
        if result.stdout:
            output.append(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            output.append(f"STDERR:\n{result.stderr}")

        if not output:
            return f"Command '{command}' completed successfully with no terminal output."

        return "\n\n".join(output)

    except subprocess.TimeoutExpired:
        return f"Timeout Error: Command '{command}' was terminated after exceeding the 30-second limit."
    except Exception as e:
        return f"Execution Error: {str(e)}"
