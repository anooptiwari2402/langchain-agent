import asyncio
import datetime
import os
import sys
import warnings
from pathlib import Path

# Suppress annoying third-party library warnings to keep terminal outputs pristine
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*schema.*")

from config import WORKSPACE_DIR
from agent_factory import AgentManager
import ui

def extract_chunk_text(chunk) -> str:
    """Helper to safely extract textual token from chat model stream chunks."""
    if not chunk:
        return ""
    content = getattr(chunk, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict):
                if "text" in p:
                    parts.append(p["text"])
            else:
                parts.append(str(p))
        return "".join(parts)
    return ""


async def run_agent_stream(agent, human_question, config):
    """
    Executes the agent in streaming mode using astream_events,
    displaying thoughts, tools, and token stream in real-time.
    """
    handler = ui.TerminalStreamHandler()
    inputs = {"messages": [{"role": "user", "content": human_question}]}
    
    # We use high-quality astream_events version 2
    handler.start_spinner("Thinking and researching...")
    try:
        async for event in agent.astream_events(inputs, version="v2", config=config):
            event_type = event["event"]
            name = event["name"]

            # Token streaming
            if event_type == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk:
                    text = extract_chunk_text(chunk)
                    if text:
                        handler.on_token(text)

            # Tool Execution Start
            elif event_type == "on_tool_start":
                tool_inputs = event["data"].get("input", {})
                handler.on_tool_start(name, tool_inputs)

            # Tool Execution End
            elif event_type == "on_tool_end":
                tool_output = event["data"].get("output")
                handler.on_tool_end(name, tool_output)

    except Exception as e:
        handler.stop_spinner()
        ui.console.print(f"\n[bold red]Streaming error occurred:[/bold red] {e}")
    finally:
        handler.finalize()


async def get_session_messages(agent_obj, run_config):
    """Fetches messages for a specific session/thread from the agent graph state."""
    try:
        state = await agent_obj.aget_state(run_config)
        return state.values.get("messages", [])
    except Exception as e:
        ui.console.print(f"[bold red]Could not retrieve history for the session:[/bold red] {e}")
        return []


async def handle_export(agent_obj, run_config):
    """Exports conversation log to a Markdown file in the workspace directory."""
    messages = await get_session_messages(agent_obj, run_config)
    if not messages:
        ui.console.print("[yellow]No chat history to export.[/yellow]")
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
            md_content.append(ui.format_msg_content(msg.content))
            md_content.append("\n---")
        elif msg_type == "AIMessage":
            content_text = ui.format_msg_content(msg.content)
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
            content_str = ui.format_msg_content(msg.content)
            md_content.append(f"\n<details>")
            md_content.append(f"<summary>🔧 Tool Output: {msg.name}</summary>\n")
            md_content.append("```")
            md_content.append(content_str)
            md_content.append("```")
            md_content.append("</details>\n")
            md_content.append("---")

    filename = f"research_export_{file_timestamp}.md"
    filepath = WORKSPACE_DIR / filename

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(md_content))
        ui.print_panel(
            "Export Success",
            f"[bold green]✓ Conversation Exported Successfully![/bold green]\n"
            f"[dim]Markdown file saved to:[/dim] [cyan]{filepath}[/cyan]",
            border_style="green"
        )
    except Exception as e:
        ui.console.print(f"[bold red]Failed to export conversation file:[/bold red] {e}")


def handle_list_sessions(agent_manager):
    """Retrieves and lists all saved chat sessions in a beautiful table."""
    sessions = agent_manager.get_stored_sessions()
    if not sessions:
        ui.console.print("[yellow]No saved conversation sessions found.[/yellow]")
        return

    table = ui.Table(title="💾 Saved Chat Sessions", show_header=True, header_style="bold cyan")
    table.add_column("Session / Thread ID", style="bold green", width=35)
    table.add_column("Last Node State", style="yellow")
    table.add_column("Last Updated", style="white")

    for s in sessions:
        table.add_row(s["thread_id"], s["node"], str(s["timestamp"]))

    ui.console.print(table)


async def main():
    # 1. Initialize AgentManager
    agent_manager = AgentManager()

    ui.console.print("[bold yellow]Initializing filesystem tools, search engines & persistent memory...[/bold yellow]")
    
    # Live status during compile
    with ui.print_status("Preparing Agent graph..."):
        await agent_manager.compile_agent(console_reporter=ui.console.print)

    # 2. Display start header
    ui.console.clear()
    ui.display_header()

    if agent_manager.using_mcp:
        ui.console.print("[dim green]🧬 Standard Model Context Protocol (MCP) Filesystem is active.[/dim green]\n")
    else:
        ui.console.print("[dim yellow]🛡️ Running sandboxed local Python fallback filesystem tools.[/dim yellow]\n")

    # 3. Generate initial session ID based on current timestamp
    session_id = f"research_session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    config = {"configurable": {"thread_id": session_id}}

    ui.console.print(f"🔄 Active Conversation Session: [bold cyan]{session_id}[/bold cyan]\n")

    multiline_mode = False

    while True:
        try:
            if multiline_mode:
                human_question = ui.get_multiline_input()
            else:
                human_question = ui.Prompt.ask("\n[bold magenta]User[/bold magenta]")

            if not human_question.strip():
                continue

            cmd_parts = human_question.strip().split()
            cmd_lower = cmd_parts[0].lower()

            # Handle interactive commands
            if cmd_lower in ["exit", "quit"]:
                ui.console.print("[yellow]Saving session state. Goodbye![/yellow]")
                break

            if cmd_lower == "/help":
                ui.display_help()
                continue

            if cmd_lower == "/clear":
                ui.console.clear()
                ui.display_header()
                ui.console.print(f"🔄 Active Conversation Session: [bold cyan]{session_id}[/bold cyan]\n")
                continue

            if cmd_lower == "/tools":
                ui.display_tools(agent_manager.tools)
                continue

            if cmd_lower == "/history":
                messages = await get_session_messages(agent_manager.agent, config)
                ui.display_history(messages)
                continue

            if cmd_lower == "/export":
                await handle_export(agent_manager.agent, config)
                continue

            if cmd_lower == "/sessions":
                handle_list_sessions(agent_manager)
                continue

            if cmd_lower == "/resume":
                if len(cmd_parts) < 2:
                    ui.console.print("[bold red]Usage:[/bold red] /resume <session_id>")
                    continue
                target_id = cmd_parts[1].strip()
                # Verify if this session exists
                sessions = agent_manager.get_stored_sessions()
                existing_ids = [s["thread_id"] for s in sessions]
                if target_id not in existing_ids:
                    ui.console.print(f"[bold red]Error:[/bold red] Session '{target_id}' not found in SQLite.")
                    continue
                session_id = target_id
                config = {"configurable": {"thread_id": session_id}}
                ui.console.print(f"[bold green]✓ Session Switched![/bold green] Currently resuming: [bold cyan]{session_id}[/bold cyan]")
                messages = await get_session_messages(agent_manager.agent, config)
                ui.display_history(messages)
                continue

            if cmd_lower == "/delete":
                if len(cmd_parts) < 2:
                    ui.console.print("[bold red]Usage:[/bold red] /delete <session_id>")
                    continue
                target_id = cmd_parts[1].strip()
                success = agent_manager.delete_session(target_id)
                if success:
                    ui.console.print(f"[bold green]✓ Session '{target_id}' permanently deleted from database.[/bold green]")
                    # If current session deleted, generate a new one
                    if target_id == session_id:
                        session_id = f"research_session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        config = {"configurable": {"thread_id": session_id}}
                        ui.console.print(f"🔄 Started new conversation session: [bold cyan]{session_id}[/bold cyan]")
                else:
                    ui.console.print(f"[bold red]Failed to delete session '{target_id}'.[/bold red]")
                continue

            if cmd_lower == "/multiline":
                multiline_mode = not multiline_mode
                ui.console.print(f"[bold yellow]🔄 Multi-line input mode {'ENABLED' if multiline_mode else 'DISABLED'}.[/bold yellow]")
                if multiline_mode:
                    ui.console.print("[dim]Type your message. To finish, press Enter twice on empty lines or type 'SEND' on a new line.[/dim]")
                continue

            # Run the agent with real-time streaming
            await run_agent_stream(agent_manager.agent, human_question, config)

        except KeyboardInterrupt:
            ui.console.print("\n[yellow]Session interrupted. Exiting...[/yellow]")
            break
        except Exception as e:
            ui.console.print(f"\n[bold red]An unexpected error occurred:[/bold red] {e}")

    # Cleanup resources on exit
    agent_manager.close()


def cli_entry():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli_entry()
