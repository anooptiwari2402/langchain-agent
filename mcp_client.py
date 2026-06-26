import sys
import shutil
from langchain_mcp_adapters.client import MultiServerMCPClient
from config import WORKSPACE_DIR
from fallback_tools import get_fallback_tools

async def initialize_filesystem_tools(console_reporter=None) -> tuple[list, bool]:
    """
    Initializes the Model Context Protocol (MCP) filesystem server tools.
    If the server cannot be initialized (e.g. npx not found, node errors, etc.),
    it automatically falls back to native Python filesystem tools and reports the status.

    Returns:
        A tuple of (tools_list, using_mcp_boolean)
    """
    # 1. Check if 'npx' is available on the system path
    npx_path = shutil.which("npx")
    if not npx_path:
        if console_reporter:
            console_reporter("[yellow]⚠️ 'npx' command not found. Falling back to native Python filesystem tools.[/yellow]")
        return get_fallback_tools(), False

    try:
        # 2. Setup MCP filesystem adapter
        client = MultiServerMCPClient(
            {
                "filesystem": {
                    "command": "npx",
                    "args": [
                        "-y",
                        "@modelcontextprotocol/server-filesystem",
                        str(WORKSPACE_DIR)
                    ],
                    "transport": "stdio",
                }
            }
        )

        file_system_tools = await client.get_tools()

        # Clean up '$schema' from MCP tool schemas to prevent provider warnings
        for t in file_system_tools:
            if hasattr(t, "args_schema") and isinstance(t.args_schema, dict) and "$schema" in t.args_schema:
                del t.args_schema["$schema"]

        if console_reporter:
            console_reporter("[green]✓ MCP Filesystem Server initialized successfully.[/green]")
        return file_system_tools, True

    except Exception as e:
        if console_reporter:
            console_reporter(f"[yellow]⚠️ Failed to load MCP filesystem tools ({e}). Falling back to native Python tools.[/yellow]")
        return get_fallback_tools(), False
