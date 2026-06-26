import sqlite3
from contextlib import contextmanager
from langchain.agents import create_agent
from langchain_community.tools import DuckDuckGoSearchRun
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from config import DB_PATH, MODEL_NAME
from prompt import SYSTEM_PROMPT
from terminal_tool import execute_terminal_command
from mcp_client import initialize_filesystem_tools
from fallback_tools import get_fallback_tools
import aiosqlite

class AgentManager:
    """
    Manages the lifecycle, database connection, and compilation of the LangChain Agent.
    """
    def __init__(self):
        self.db_conn = None
        self.checkpointer = None
        self.agent = None
        self.tools = []
        self.using_mcp = False

    async def setup_database(self):
        """Initializes sqlite3 connection and sets up LangGraph SqliteSaver."""
        try:
            # Connect to local SQLite DB file for persistent threads
            self.db_conn = await aiosqlite.connect(str(DB_PATH))
            self.checkpointer = AsyncSqliteSaver(self.db_conn)
            # Sets up checkpoints tables if they don't exist
            await self.checkpointer.setup()
        except Exception as e:
            print(f"Error setting up SQLite persistent database: {e}")
            raise e

    async def compile_agent(self, console_reporter=None):
        """Compiles the LangGraph agent with persistent memory and all tools."""
        # 1. Initialize persistent DB
        await self.setup_database()

        # 2. Register tools
        search = DuckDuckGoSearchRun()

        # Try initializing filesystem tools via MCP or fallback to native Python tools
        fs_tools, self.using_mcp = await initialize_filesystem_tools(console_reporter)

        self.tools = [search, execute_terminal_command] + fs_tools

        # 3. Create agent graph
        self.agent = create_agent(
            model=MODEL_NAME,
            tools=self.tools,
            system_prompt=SYSTEM_PROMPT,
            checkpointer=self.checkpointer
        )

    def get_stored_sessions(self) -> list[dict]:
        """
        Retrieves all past unique conversation threads and their metadata.
        Returns a sorted list of dictionaries with session_id, modified_at, etc.
        """
        if not self.checkpointer:
            return []

        sessions = {}
        try:
            # Retrieve checkpoint tuples
            for checkpoint_tuple in self.checkpointer.list(None):
                thread_id = checkpoint_tuple.config.get("configurable", {}).get("thread_id")
                if not thread_id:
                    continue

                # Fetch modification time from metadata if available
                metadata = checkpoint_tuple.metadata or {}
                timestamp = metadata.get("ts", "")
                if not timestamp:
                    # Fallback to current date or standard key
                    timestamp = "Unknown Date"

                # Keep track of latest checkpoint for this thread_id
                if thread_id not in sessions:
                    sessions[thread_id] = {
                        "thread_id": thread_id,
                        "timestamp": timestamp,
                        "node": checkpoint_tuple.metadata.get("source", "model")
                    }
        except Exception as e:
            print(f"Error listing database sessions: {e}")

        # Return sessions sorted by thread ID or timestamp
        return sorted(sessions.values(), key=lambda x: x["thread_id"], reverse=True)

    def delete_session(self, thread_id: str) -> bool:
        """Permanently deletes a thread from the persistent database."""
        if not self.db_conn:
            return False
        try:
            # We can delete all records corresponding to this thread_id
            cursor = self.db_conn.cursor()
            # In LangGraph checkpoints tables, records are associated with thread_id
            # Let's inspect checkpoint tables and delete
            # The standard table names for SqliteSaver: 'checkpoints', 'writes', 'checkpoint_blobs', 'checkpoint_writes'
            tables = ["checkpoints", "writes", "checkpoint_blobs", "checkpoint_writes"]
            for table in tables:
                try:
                    cursor.execute(f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,))
                except sqlite3.OperationalError:
                    # Some tables might not exist depending on the specific schema version
                    continue
            self.db_conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting session '{thread_id}': {e}")
            return False

    async def close(self):
        """Clean closure of resources and DB connection."""
        if self.db_conn:
            try:
                await self.db_conn.close()
            except Exception:
                pass
            self.db_conn = None
