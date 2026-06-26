import subprocess
import os
import re
from langchain_core.tools import tool

# Dynamically set Workspace directory boundary from environment variable
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "/Users/anooptiwari/Downloads")


@tool
def execute_terminal_command(command: str) -> str:
    """
    Executes a terminal/shell command on the local machine and returns stdout and stderr.
    Use this to run test suites, execute python files, run compilers, check git status, or check packages.
    Only run safe, non-interactive commands. Do not run blocking or interactive commands (e.g. do not run 'nano', 'top', or 'ping' without bounds).
    """
    command_lower = command.lower()

    # 1. Broad blacklist of forbidden command elements
    forbidden_tokens = ["sudo", "shutdown", "reboot", "mkfs", "dd", "format", "chown", "chmod"]
    for token in forbidden_tokens:
        if token in command_lower.split() or f" {token} " in f" {command_lower} ":
            return f"Security Error: Command execution aborted. Token '{token}' is restricted for safety."

    # 2. Prevent recursive removal commands using Regex (e.g., rm -rf, rm -r, rm -fR)
    rm_recursive_pattern = r"\brm\s+-[rRfF]*[rR]+[rRfF]*\b|\brm\s+--recursive\b"
    if re.search(rm_recursive_pattern, command_lower):
        return "Security Error: Recursive removal commands (like 'rm -r') are prohibited."

    # 3. Prevent arbitrary downloading and piping directly to bash/sh
    pipe_to_shell_pattern = r"\b(curl|wget)\b.*\b(bash|sh)\b"
    if re.search(pipe_to_shell_pattern, command_lower):
        return "Security Error: Downloading and piping directly to shell is blocked for safety."

    # 4. Limit actions targeting sensitive system-wide paths
    system_paths = ["/etc", "/var", "/bin", "/sbin", "/usr", "/private", "/System", "/Library"]
    for path in system_paths:
        # Check if they are trying to view or access files in system folders, except within the workspace path
        if path in command_lower and not WORKSPACE_DIR.startswith(path):
            return f"Security Error: Access to sensitive system path '{path}' is prohibited."

    try:
        # 5. Run with timeout to prevent hanging on interactive inputs or infinite loops
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
            timeout=30,  # 30-second hard limit
            cwd=WORKSPACE_DIR  # Restrict execution folder context
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
