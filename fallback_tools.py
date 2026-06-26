import os
from pathlib import Path
from langchain_core.tools import tool
from config import WORKSPACE_DIR
from security import validate_and_sanitize_path

@tool
def fallback_list_directory(sub_dir: str = ".") -> str:
    """
    List contents of the specified subdirectory within the workspace.
    Returns a formatted string listing all files and directories.
    """
    is_safe, error_msg = validate_and_sanitize_path(sub_dir)
    if not is_safe:
        return error_msg

    target_dir = (WORKSPACE_DIR / sub_dir).resolve()
    if not target_dir.exists():
        return f"Error: Directory '{sub_dir}' does not exist."
    if not target_dir.is_dir():
        return f"Error: Path '{sub_dir}' is a file, not a directory."

    try:
        entries = os.listdir(target_dir)
        output = []
        for entry in sorted(entries):
            # Skip hidden files like .git or .DS_Store
            if entry.startswith(".") and entry != "..":
                continue
            entry_path = target_dir / entry
            entry_type = "[DIR]" if entry_path.is_dir() else "[FILE]"
            size_str = f"({entry_path.stat().st_size} bytes)" if entry_path.is_file() else ""
            output.append(f"{entry_type} {entry} {size_str}")

        if not output:
            return f"Directory '{sub_dir}' is empty."
        return "\n".join(output)
    except Exception as e:
        return f"Error listing directory: {e}"


@tool
def fallback_read_file(file_path: str) -> str:
    """
    Read the contents of a text file from the workspace.
    Returns the file contents as a text string.
    """
    is_safe, error_msg = validate_and_sanitize_path(file_path)
    if not is_safe:
        return error_msg

    target_file = (WORKSPACE_DIR / file_path).resolve()
    if not target_file.exists():
        return f"Error: File '{file_path}' does not exist."
    if not target_file.is_file():
        return f"Error: Path '{file_path}' is not a file."

    try:
        # Check size to prevent loading massive binary files
        file_size = target_file.stat().st_size
        if file_size > 5 * 1024 * 1024:  # 5MB limit
            return f"Error: File '{file_path}' is too large to read in terminal ({file_size} bytes)."

        with open(target_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return content
    except Exception as e:
        return f"Error reading file: {e}"


@tool
def fallback_write_file(file_path: str, content: str, mode: str = "w") -> str:
    """
    Write or append content to a file in the workspace.
    `mode` should be 'w' to overwrite or 'a' to append.
    """
    if mode not in ("w", "a"):
        return "Error: Mode must be either 'w' (write) or 'a' (append)."

    is_safe, error_msg = validate_and_sanitize_path(file_path)
    if not is_safe:
        return error_msg

    target_file = (WORKSPACE_DIR / file_path).resolve()
    try:
        # Ensure parent directory exists
        target_file.parent.mkdir(parents=True, exist_ok=True)

        with open(target_file, mode, encoding="utf-8") as f:
            f.write(content)

        action = "written" if mode == "w" else "appended"
        return f"Successfully {action} to '{file_path}'."
    except Exception as e:
        return f"Error writing file: {e}"


@tool
def fallback_search_grep(pattern: str, file_pattern: str = "*") -> str:
    """
    Recursively search text files under the workspace directory for the specified search pattern (grep-like).
    `file_pattern` is a glob pattern of files to search (e.g. '*.py', '*.txt').
    """
    try:
        results = []
        # Walk and search
        for path in WORKSPACE_DIR.rglob(file_pattern):
            if path.is_file():
                # Skip hidden folders
                if any(part.startswith(".") for part in path.relative_to(WORKSPACE_DIR).parts):
                    continue

                is_safe, _ = validate_and_sanitize_path(str(path.relative_to(WORKSPACE_DIR)))
                if not is_safe:
                    continue

                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if pattern in line:
                                rel_path = path.relative_to(WORKSPACE_DIR)
                                results.append(f"{rel_path}:{line_num}: {line.strip()}")
                except Exception:
                    # Ignore unreadable files (e.g. binary)
                    continue

        if not results:
            return f"No matches found for '{pattern}' in files matching '{file_pattern}'."
        return "\n".join(results[:100])  # Cap at 100 results
    except Exception as e:
        return f"Error performing grep search: {e}"


def get_fallback_tools():
    """Returns a list of native Python filesystem fallback tools."""
    return [
        fallback_list_directory,
        fallback_read_file,
        fallback_write_file,
        fallback_search_grep
    ]
