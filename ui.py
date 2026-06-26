import datetime
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text
from rich.status import Status
from rich.live import Live

console = Console()

def display_header():
    """Prints the beautiful system startup header."""
    console.print(Panel.fit(
        "[bold cyan]🤖 AI Research Assistant Terminal[/bold cyan]\n"
        "[dim]Powered by LangChain, LangGraph & Gemini 3.5[/dim]\n\n"
        "[bold green]Interactive Commands:[/bold green]\n"
        "  [yellow]/help[/yellow]      - Show guide & active tools\n"
        "  [yellow]/clear[/yellow]     - Clear screen\n"
        "  [yellow]/history[/yellow]   - Print conversation thread\n"
        "  [yellow]/sessions[/yellow]  - List all stored sessions\n"
        "  [yellow]/resume <id>[/yellow]- Resume a specific session\n"
        "  [yellow]/delete <id>[/yellow]- Delete a specific session\n"
        "  [yellow]/multiline[/yellow] - Toggle multi-line input mode\n"
        "  [yellow]/export[/yellow]    - Export current session to Markdown",
        border_style="cyan"
    ))
    console.print("[dim]Type [bold red]'exit'[/bold red] or [bold red]'quit'[/bold red] to close the terminal session.[/dim]\n")


def display_help():
    """Displays a clean table of interactive client-side commands."""
    table = Table(title="💡 Interactive Commands Guide", show_header=True, header_style="bold cyan")
    table.add_column("Command", style="bold green", width=18)
    table.add_column("Description", style="white")

    table.add_row("/help", "Show this interactive commands and tools guide.")
    table.add_row("/clear", "Clear the terminal screen and reprint the header.")
    table.add_row("/history", "Display the entire message exchange of the current session.")
    table.add_row("/sessions", "List all past saved session IDs from SQLite.")
    table.add_row("/resume <id>", "Switch/restore a specific past conversation session.")
    table.add_row("/delete <id>", "Permanently delete a conversation thread from SQLite.")
    table.add_row("/tools", "List all active tools and their descriptions.")
    table.add_row("/multiline", "Toggle multi-line input mode (great for pasting code/blocks).")
    table.add_row("/export", "Export the chat history as a beautifully formatted Markdown file.")
    table.add_row("exit / quit", "Close the terminal session.")

    console.print(table)


def display_tools(tools_list):
    """Lists all available AI Agent tools and their descriptions."""
    table = Table(title="🔧 Active AI Agent Tools", show_header=True, header_style="bold yellow")
    table.add_column("Tool Name", style="bold green", width=30)
    table.add_column("Description", style="white")

    for t in tools_list:
        name = getattr(t, "name", str(t))
        desc = getattr(t, "description", "").strip()
        if "\n" in desc:
            desc = desc.split("\n")[0] + "..."
        elif len(desc) > 100:
            desc = desc[:100] + "..."
        table.add_row(name, desc)

    console.print(table)


def format_msg_content(content) -> str:
    """Robust content extraction from standard message formats."""
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict):
                if "text" in p:
                    parts.append(p["text"])
                elif "content" in p:
                    parts.append(p["content"])
            else:
                parts.append(str(p))
        return "\n".join(parts)
    return str(content)


def display_history(messages):
    """Displays a list of chat history messages beautifully."""
    if not messages:
        console.print("[yellow]No chat history found in this session.[/yellow]")
        return

    console.print("\n" + "=" * console.width)
    console.print("[bold cyan]📜 Session Chat History[/bold cyan]")
    console.print("=" * console.width + "\n")

    for msg in messages:
        msg_type = msg.__class__.__name__
        if msg_type == "HumanMessage":
            console.print(f"\n[bold magenta]👤 User[/bold magenta]:")
            console.print(format_msg_content(msg.content))
            console.print("-" * console.width)
        elif msg_type == "AIMessage":
            content_text = format_msg_content(msg.content)
            if content_text.strip():
                console.print(f"\n[bold green]🤖 Assistant[/bold green]:")
                console.print(Markdown(content_text))
                console.print("-" * console.width)

            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    console.print(f"[dim]⚡ Called Tool: [bold yellow]{tc['name']}[/bold yellow] with args: {tc['args']}[/dim]")
                console.print("-" * console.width)
        elif msg_type == "ToolMessage":
            result_str = format_msg_content(msg.content)
            if len(result_str) > 150:
                result_str = result_str[:150] + "... (truncated)"
            console.print(f"[dim]↩️ Tool [yellow]{msg.name}[/yellow] returned: {result_str}[/dim]")
            console.print("-" * console.width)


def get_multiline_input():
    """Interactive reader for multi-line inputs."""
    console.print("\n[bold magenta]User (Multi-line mode - type 'SEND' or press Enter twice on a new line to finish):[/bold magenta]")
    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == "SEND":
                break
            if line == "" and lines and lines[-1] == "":
                lines.pop()
                break
            lines.append(line)
        except EOFError:
            break
        except KeyboardInterrupt:
            console.print("\n[yellow]Multi-line input cancelled.[/yellow]")
            return ""
    return "\n".join(lines).strip()


def render_markdown(text: str):
    """Prints markdown text formatted nicely."""
    console.print(Markdown(text))


def print_status(message: str, spinner: str = "dots") -> Status:
    """Returns a Rich status/spinner object with a standard format."""
    return console.status(f"[bold blue]{message}[/bold blue]", spinner=spinner)


def print_panel(title: str, content: str, border_style: str = "green"):
    """Displays a stylized Rich panel with borders."""
    console.print(Panel(content, title=title, border_style=border_style))


class TerminalStreamHandler:
    """
    Handles streaming output in real-time, displaying thoughts, tool calls, and LLM tokens beautifully.
    """
    def __init__(self):
        self.active_spinner = None
        self.streaming_started = False
        self.tool_count = 0

    def start_spinner(self, text: str):
        self.stop_spinner()
        self.active_spinner = console.status(f"[bold blue]{text}[/bold blue]", spinner="bouncingBar")
        self.active_spinner.start()

    def stop_spinner(self):
        if self.active_spinner:
            self.active_spinner.stop()
            self.active_spinner = None

    def on_tool_start(self, tool_name: str, inputs: dict):
        self.stop_spinner()
        self.tool_count += 1
        console.print(f"\n[bold yellow]⚡ [Step {self.tool_count}] Executing Tool: {tool_name}[/bold yellow]")
        # Beautifully print tool arguments
        args_str = ", ".join(f"{k}={repr(v)}" for k, v in inputs.items())
        console.print(f"[dim]   Arguments: ({args_str})[/dim]")
        self.start_spinner(f"Running {tool_name}...")

    def on_tool_end(self, tool_name: str, output):
        self.stop_spinner()
        # Clean and truncate output
        output_str = format_msg_content(output)
        if len(output_str) > 250:
            output_str = output_str[:250] + "... (truncated)"
        console.print(f"[dim]   ↩️ Tool [yellow]{tool_name}[/yellow] completed with output:[/dim]")
        console.print(f"   [italic dim]{output_str}[/italic dim]")
        self.start_spinner("Analyzing results...")

    def on_token(self, token_text: str):
        self.stop_spinner()
        if not self.streaming_started:
            console.print("\n[bold green]🤖 Assistant[/bold green]: ", end="")
            self.streaming_started = True
        console.print(token_text, end="")
        # Force flush to ensure smooth real-time output
        import sys
        sys.stdout.flush()

    def finalize(self):
        self.stop_spinner()
        if self.streaming_started:
            console.print()  # Add a trailing newline
            console.print("-" * console.width)
        else:
            console.print("[dim]No textual output generated.[/dim]")
        self.streaming_started = False
        self.tool_count = 0
