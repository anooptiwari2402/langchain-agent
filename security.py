import re
from pathlib import Path
from config import WORKSPACE_DIR, FORBIDDEN_TOKENS, SENSITIVE_PATTERNS

def validate_and_sanitize_path(path_str: str) -> tuple[bool, str]:
    """
    Validates that a path is safe, does not escape WORKSPACE_DIR,
    and does not access sensitive files or directories.
    """
    try:
        # Resolve path relative to workspace directory
        raw_path = Path(path_str)
        if raw_path.is_absolute():
            resolved_path = raw_path.resolve()
        else:
            resolved_path = (WORKSPACE_DIR / raw_path).resolve()

        # Check path traversal: resolved path must be within WORKSPACE_DIR
        # (or be the workspace directory itself)
        if not (resolved_path == WORKSPACE_DIR or WORKSPACE_DIR in resolved_path.parents):
            return False, f"Path Traversal Error: Target path '{path_str}' is outside of the workspace directory."

        # Check for sensitive patterns in the absolute path string
        resolved_str = str(resolved_path)
        for pattern in SENSITIVE_PATTERNS:
            if re.search(pattern, resolved_str, re.IGNORECASE):
                return False, f"Security Error: Access to sensitive system/config path '{pattern}' is prohibited."

        return True, ""
    except Exception as e:
        return False, f"Path Validation Error: Invalid path format. Details: {e}"


def is_safe_command(command: str) -> tuple[bool, str]:
    """
    Analyzes a shell command to ensure it's safe to run.
    Checks forbidden keywords, shell pipes, and absolute/relative path access.
    """
    command_lower = command.strip().lower()

    # 1. Broad blacklist of forbidden command elements
    for token in FORBIDDEN_TOKENS:
        # Match whole word to avoid blocking words like "sudo" inside other commands if any,
        # but splits or space checks are safe
        words = command_lower.split()
        if token in words or any(w.startswith(f"{token}=") or w.startswith(f"--{token}") for w in words):
            return False, f"Security Error: Token '{token}' is restricted for safety."

    # 2. Prevent recursive removal commands using Regex (e.g., rm -rf, rm -r, rm -fR)
    rm_recursive_pattern = r"\brm\s+-[rRfF]*[rR]+[rRfF]*\b|\brm\s+--recursive\b"
    if re.search(rm_recursive_pattern, command_lower):
        return False, "Security Error: Recursive removal commands (like 'rm -r') are prohibited."

    # 3. Prevent arbitrary downloading and piping directly to bash/sh
    pipe_to_shell_pattern = r"\b(curl|wget)\b.*\b(bash|sh)\b"
    if re.search(pipe_to_shell_pattern, command_lower):
        return False, "Security Error: Downloading and piping directly to shell is blocked for safety."

    # 4. Prevent accessing environment secrets directly via echoing, env print, etc.
    env_leak_pattern = r"\b(env|printenv|set|export)\b"
    if re.search(env_leak_pattern, command_lower):
        # We can allow 'env' or 'export' in highly specific safe circumstances,
        # but generally blocking is safer to prevent leaking GOOGLE_API_KEY.
        return False, "Security Error: Inspection or modification of environment variables is restricted."

    # 5. Extract all candidate file/directory paths from the command
    # Paths usually contain alphanumeric characters, slashes, dots, and hyphens
    path_candidates = re.findall(r"(?:[a-zA-Z]:)?[/\\a-zA-Z0-9_\.\-]+[/\\a-zA-Z0-9_\.\-]+", command)
    for candidate in path_candidates:
        # Ignore purely numeric or simple words, only check actual path-like strings
        if "/" in candidate or "\\" in candidate or "." in candidate:
            # Skip if it is just a flag, float value or version number (e.g. -v, --version, 3.10)
            if candidate.startswith("-") or re.match(r"^\d+\.\d+$", candidate):
                continue
            is_valid, err_msg = validate_and_sanitize_path(candidate)
            if not is_valid:
                return False, err_msg

    # 6. Check system-wide paths in raw string
    system_paths = ["/etc", "/var", "/bin", "/sbin", "/usr", "/private", "/System", "/Library"]
    for path in system_paths:
        if path in command_lower:
            # Exception: Allow if it references the current .venv inside WORKSPACE_DIR
            resolved_workspace_str = str(WORKSPACE_DIR.resolve())
            if path in resolved_workspace_str:
                continue
            return False, f"Security Error: Direct reference to sensitive system path '{path}' is prohibited."

    return True, ""
