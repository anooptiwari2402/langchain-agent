import os
from langchain_mcp_adapters.client import MultiServerMCPClient


def file_system_mcp_tool():
    workspace_dir = os.getenv("WORKSPACE_DIR", "/Users/anooptiwari/Downloads")
    return MultiServerMCPClient(
        {
            "filesystem": {
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-filesystem",
                    workspace_dir
                ],
                "transport": "stdio",
            }
        }
    )
