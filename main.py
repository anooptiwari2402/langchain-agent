import asyncio
import os
import sys
import warnings
import datetime
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_community.tools import DuckDuckGoSearchRun
from terminal_tool import execute_terminal_command, WORKSPACE_DIR

from file_system_mcp import file_system_mcp_tool
from prompt import SYSTEM_PROMPT

# Import rich elements for a beautiful interactive interface
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.status import Status
from rich.table import Table
from rich.text import Text
from langgraph.checkpoint.memory import MemorySaver

# Suppress annoying third-party library warnings to keep terminal outputs pristine
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*schema.*")

console = Console()


def display_help(con):
    """Displays a clean table of interactive client-side commands."""
    table = Table(title="💡 Interactive Commands Guide", show_header=True, header_style="bold cyan")
    table.add_column("Command", style="bold green", width=15)
    table.add_column("Description", style="white")

    table.add_row("/help", "Show this interactive commands and tools guide.")
    table.add_row("/clear", "Clear the terminal screen and reprint the header.")
    table.add_row("/history", "Display the entire message exchange of the current session.")
    table.add_row("/tools", "List all active tools and their descriptions.")
    table.add_row("/multiline", "Toggle multi-line input mode (great for pasting code/blocks).")
    table.add_row("/export", "Export the chat history as a beautifully formatted Markdown file.")
    table.add_row("exit / quit", "Close the terminal session.")

    con.print(table)


def display_tools(con, tools_list):
    """Lists all available AI Agent tools and their descriptions."""
    table = Table(title="🔧 Active AI Agent Tools", show_header=True, header_style="bold yellow")
    table.add_column("Tool Name", style="bold green", width=25)
    table.add_column("Description", style="white")

    for t in tools_list:
        name = getattr(t, "name", str(t))
        desc = getattr(t, "description", "").strip()
        # Clean up description to show first line or up to 100 characters
        if "\n" in desc:
            desc = desc.split("\n")[0] + "..."
        elif len(desc) > 100:
            desc = desc[:100] + "..."
        table.add_row(name, desc)

    con.print(table)


async def display_history(con, agent_obj, run_config):
    """Fetches chat history from the agent's LangGraph state and displays it beautifully."""
    try:
        state = await agent_obj.aget_state(run_config)
        messages = state.values.get("messages", [])
    except Exception as e:
        con.print(f"[bold red]Could not retrieve history:[/bold red] {e}")
        return

    if not messages:
        con.print("[yellow]No chat history found in this session.[/yellow]")
        return

    con.print("\n" + "=" * con.width)
    con.print("[bold cyan]📜 Session Chat History[/bold cyan]")
    con.print("=" * con.width + "\n")

    for msg in messages:
        msg_type = msg.__class__.__name__
        if msg_type == "HumanMessage":
            con.print(f"\n[bold magenta]User[/bold magenta]:")
            con.print(str(msg.content))
            con.print("-" * con.width)
        elif msg_type == "AIMessage":
            # Extract content safely
            content_text = ""
            if isinstance(msg.content, list):
                parts = []
                for p in msg.content:
                    if isinstance(p, dict):
                        if "text" in p:
                            parts.append(p["text"])
                        elif "content" in p:
                            parts.append(p["content"])
                    else:
                        parts.append(str(p))
                content_text = "\n".join(parts)
            else:
                content_text = str(msg.content)

            if content_text.strip():
                con.print(f"\n[bold green]Assistant[/bold green]:")
                con.print(Markdown(content_text))
                con.print("-" * con.width)

            # Highlight tool calls
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    con.print(f"[dim]⚡ Called Tool: [bold yellow]{tc['name']}[/bold yellow] with args: {tc['args']}[/dim]")
                con.print("-" * con.width)
        elif msg_type == "ToolMessage":
            result_str = str(msg.content)
            if len(result_str) > 120:
                result_str = result_str[:120] + "... (truncated)"
            con.print(f"[dim]↩️ Tool [yellow]{msg.name}[/yellow] returned: {result_str}[/dim]")
            con.print("-" * con.width)


async def export_chat_history(con, agent_obj, run_config):
    """Exports conversation log to a Markdown file in the workspace directory."""
    try:
        state = await agent_obj.aget_state(run_config)
        messages = state.values.get("messages", [])
    except Exception as e:
        con.print(f"[bold red]Could not retrieve history for export:[/bold red] {e}")
        return

    if not messages:
        con.print("[yellow]No chat history to export.[/yellow]")
        return

    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    file_timestamp = now.strftime("%Y%m%d_%H%M%S")

    md_content = [
        f"# AI Research Assistant Chat Export",
        f"**Session Date:** {timestamp}",
        f"**Thread ID:** {run_config['configurable']['thread_id']}\n",
        "---"
    ]

    for msg in messages:
        msg_type = msg.__class__.__name__
        if msg_type == "HumanMessage":
            md_content.append(f"\n### 👤 User")
            md_content.append(str(msg.content))
            md_content.append("\n---")
        elif msg_type == "AIMessage":
            content_text = ""
            if isinstance(msg.content, list):
                parts = []
                for p in msg.content:
                    if isinstance(p, dict):
                        if "text" in p:
                            parts.append(p["text"])
                        elif "content" in p:
                            parts.append(p["content"])
                    else:
                        parts.append(str(p))
                content_text = "\n".join(parts)
            else:
                content_text = str(msg.content)

            if content_text.strip():
                md_content.append(f"\n### 🤖 Assistant")
                md_content.append(content_text)
                md_content.append("\n---")

            if hasattr(msg, "tool_calls") and msg.tool_calls:
                md_content.append("\n**⚡ Tool Calls:**")
                for tc in msg.tool_calls:
                    md_content.append(f"- **{tc['name']}** with arguments: `{tc['args']}`")
                md_content.append("\n---")
        elif msg_type == "ToolMessage":
            content_str = str(msg.content)
            md_content.append(f"\n<details>")
            md_content.append(f"<summary>🔧 Tool Output: {msg.name}</summary>\n")
            md_content.append("```")
            md_content.append(content_str)
            md_content.append("```")
            md_content.append("</details>\n")
            md_content.append("---")

    filename = f"research_export_{file_timestamp}.md"
    filepath = os.path.join(WORKSPACE_DIR, filename)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(md_content))
        con.print(Panel(
            f"[bold green]✓ Conversation Exported Successfully![/bold green]\n"
            f"[dim]Markdown file saved to:[/dim] [cyan]{filepath}[/cyan]",
            title="Export Success",
            border_style="green"
        ))
    except Exception as e:
        con.print(f"[bold red]Failed to export conversation file:[/bold red] {e}")


def get_multiline_input(con):
    """Interactive reader for multi-line inputs."""
    con.print("\n[bold magenta]User (Multi-line mode - type 'SEND' or press Enter twice on a new line to finish):[/bold magenta]")
    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == "SEND":
                break
            if line == "" and lines and lines[-1] == "":
                lines.pop()  # Remove trailing empty line
                break
            lines.append(line)
        except EOFError:
            break
        except KeyboardInterrupt:
            con.print("\n[yellow]Multi-line input cancelled.[/yellow]")
            return ""
    return "\n".join(lines).strip()


async def main():
    load_dotenv()

    console.print(Panel.fit(
        "[bold cyan]AI Research Assistant Terminal[/bold cyan]\n"
        "[dim]Powered by LangChain, LangGraph & Gemini 3.5[/dim]\n\n"
        "[bold green]Interactive Commands:[/bold green]\n"
        "  [yellow]/help[/yellow]      - Show guide & active tools\n"
        "  [yellow]/clear[/yellow]     - Clear screen\n"
        "  [yellow]/history[/yellow]   - Print conversation thread\n"
        "  [yellow]/multiline[/yellow] - Toggle multi-line input\n"
        "  [yellow]/export[/yellow]    - Export logs to Markdown\n",
        border_style="cyan"
    ))

    # Loading indicator for tool initialization
    with Status("[bold yellow]Initializing filesystem tools & search engines...", spinner="dots") as status:
        search = DuckDuckGoSearchRun()
        try:
            file_system_tool = await file_system_mcp_tool().get_tools()
            # Clean up '$schema' from MCP tool schemas to prevent providers warnings
            for t in file_system_tool:
                if hasattr(t, "args_schema") and isinstance(t.args_schema, dict) and "$schema" in t.args_schema:
                    del t.args_schema["$schema"]
        except Exception as e:
            console.print(f"[bold red]Error initializing filesystem tool:[/bold red] {e}")
            file_system_tool = []

        # Create memory saver checkpointer for seamless turn-by-turn conversational memory
        memory = MemorySaver()

        # Compile agent with checkpointer
        agent = create_agent(
            model="google_genai:gemini-3.5-flash",
            tools=[search, execute_terminal_command, *file_system_tool],
            system_prompt=SYSTEM_PROMPT,
            checkpointer=memory
        )
        status.update("[bold green]Assistant Ready![/bold green]")

    console.print(
        "[dim]Type [bold red]'exit'[/bold red] or [bold red]'quit'[/bold red] to close the terminal session.[/dim]\n")

    # Generate a unique thread session ID based on current timestamp
    session_id = f"research_session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    config = {"configurable": {"thread_id": session_id}}

    multiline_mode = False

    while True:
        try:
            # Check input mode and prompt accordingly
            if multiline_mode:
                human_question = get_multiline_input(console)
            else:
                human_question = Prompt.ask("\n[bold magenta]User[/bold magenta]")

            if not human_question.strip():
                continue

            cmd_lower = human_question.strip().lower()

            # Handle interactive commands
            if cmd_lower in ["exit", "quit"]:
                console.print("[yellow]Exiting session. Goodbye![/yellow]")
                break

            if cmd_lower == "/help":
                display_help(console)
                continue

            if cmd_lower == "/clear":
                console.clear()
                console.print(Panel.fit(
                    "[bold cyan]AI Research Assistant Terminal[/bold cyan]\n"
                    "[dim]Powered by LangChain, LangGraph & Gemini 3.5[/dim]",
                    border_style="cyan"
                ))
                continue

            if cmd_lower == "/tools":
                display_tools(console, [search, execute_terminal_command] + file_system_tool)
                continue

            if cmd_lower == "/history":
                await display_history(console, agent, config)
                continue

            if cmd_lower == "/export":
                await export_chat_history(console, agent, config)
                continue

            if cmd_lower == "/multiline":
                multiline_mode = not multiline_mode
                console.print(f"[bold yellow]🔄 Multi-line input mode {'ENABLED' if multiline_mode else 'DISABLED'}.[/bold yellow]")
                if multiline_mode:
                    console.print("[dim]Type your message. To finish, press Enter twice on empty lines or type 'SEND' on a new line.[/dim]")
                continue

            # Spinner while LLM processes
            with Status("[bold blue]Thinking and researching...", spinner="bouncingBar") as status:
                response = await agent.ainvoke(
                    {"messages": [{"role": "user", "content": human_question}]},
                    config=config
                )

            # Extract content text safely
            message_content = response["messages"][-1].content

            # Robust list-based content extraction
            output_text = ""
            if isinstance(message_content, list):
                parts = []
                for part in message_content:
                    if isinstance(part, dict):
                        if "text" in part:
                            parts.append(part["text"])
                        elif "content" in part:
                            parts.append(part["content"])
                    else:
                        parts.append(str(part))
                output_text = "\n".join(parts)
            else:
                output_text = str(message_content)

            # Print beautifully rendered markdown response
            console.print("\n[bold green]Assistant[/bold green]:")
            console.print(Markdown(output_text))
            console.print("-" * console.width)

        except KeyboardInterrupt:
            console.print("\n[yellow]Session interrupted. Exiting...[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[bold red]An error occurred:[/bold red] {e}")


def cli_entry():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli_entry()
