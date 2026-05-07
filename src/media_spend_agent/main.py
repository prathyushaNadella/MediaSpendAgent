from __future__ import annotations

import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from media_spend_agent.agent import MediaSpendAgent
from media_spend_agent.amc.client import AMCClient
from media_spend_agent.config import load_settings

console = Console()


def main() -> None:
    console.print(
        Panel(
            "[bold]Media Spend Agent[/bold]\n"
            "Incremental ROAS analysis for Amazon Marketing Cloud\n\n"
            "Ask me about your campaign performance, iROAS, or budget recommendations.\n"
            "Type [bold]quit[/bold] or [bold]exit[/bold] to end the session.",
            title="Welcome",
            border_style="blue",
        )
    )

    settings = load_settings()

    if not settings.anthropic_api_key:
        console.print("[red]Error: ANTHROPIC_API_KEY not set. Add it to your .env file.[/red]")
        sys.exit(1)

    amc_client = None
    if settings.amc_client_id and settings.amc_client_secret and settings.amc_refresh_token:
        amc_client = AMCClient(settings)
        console.print("[green]AMC credentials found — live data mode.[/green]\n")
    else:
        console.print(
            "[yellow]AMC credentials not configured. "
            "The agent will respond but cannot fetch live data.\n"
            "Set AMC_CLIENT_ID, AMC_CLIENT_SECRET, and AMC_REFRESH_TOKEN in .env[/yellow]\n"
        )

    agent = MediaSpendAgent(settings, amc_client=amc_client)

    while True:
        try:
            user_input = console.input("[bold cyan]You:[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            console.print("[dim]Goodbye![/dim]")
            break

        try:
            with console.status("[bold green]Thinking...[/bold green]"):
                response = agent.chat(user_input)
            console.print()
            console.print(Markdown(response))
            console.print()
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]\n")

    if amc_client is not None:
        amc_client.close()


def __name_main() -> None:
    main()


if __name__ == "__main__":
    main()
