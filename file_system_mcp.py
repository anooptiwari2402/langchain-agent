from langchain_mcp_adapters.client import MultiServerMCPClient


def file_system_mcp_tool():
    return MultiServerMCPClient(
        {
            "filesystem": {
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-filesystem",
                    "/Users/anooptiwari/Downloads"      # <-- workspace path
                ],
                "transport": "stdio",
            }
        }
    )
