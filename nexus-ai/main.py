"""
NEXUS AI — Main Entry Point
Run this to start the system.

Usage:
  python main.py              → Start API server
  python main.py task "..."   → Run a task directly
  python main.py status       → Show system status
"""

import asyncio
import sys
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

app = typer.Typer()
console = Console()


def print_banner():
    console.print(Panel.fit(
        "[bold cyan]NEXUS AI SYSTEM[/bold cyan]\n"
        "[dim]Autonomous Multi-Agent Creative AI[/dim]\n"
        "[dim]Phase 1 — Core Engine[/dim]",
        border_style="cyan"
    ))


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000):
    """Start the NEXUS API server."""
    print_banner()
    console.print(f"[green]Starting NEXUS API on http://{host}:{port}[/green]")
    console.print("[dim]Dashboard can connect at /status[/dim]")
    import uvicorn
    uvicorn.run("core.api:app", host=host, port=port, reload=True)


@app.command()
def task(prompt: str, auto: bool = False):
    """Run a task through ARIA."""
    print_banner()
    console.print(f"\n[cyan]Task:[/cyan] {prompt}\n")

    async def _run():
        from core.orchestrator import aria
        plan = await aria.process(prompt, auto_execute=auto)
        console.print_json(data=plan)
        return plan

    asyncio.run(_run())


@app.command()
def status():
    """Show system status."""
    print_banner()

    async def _status():
        from core.router import tracker
        from core.memory import memory
        from config.models import MODELS

        console.print("\n[bold]Usage Stats:[/bold]")
        console.print(f"Daily cost: ${tracker.get_daily_cost():.4f}")
        console.print(f"Monthly cost: ${tracker.get_monthly_cost():.4f}")

        console.print("\n[bold]Memory:[/bold]")
        stats = memory.get_stats()
        for k, v in stats.items():
            console.print(f"  {k}: {v} entries")

        console.print("\n[bold]Models Available:[/bold]")
        table = Table()
        table.add_column("Model", style="cyan")
        table.add_column("Provider")
        table.add_column("Cost/1k")
        table.add_column("Status")

        for k, m in MODELS.items():
            status_str = "[green]Available[/green]" if m.available else "[red]Phase 2[/red]"
            cost_str = "FREE" if m.cost_per_1k_tokens == 0 else f"${m.cost_per_1k_tokens}"
            table.add_row(m.name, m.provider.value, cost_str, status_str)

        console.print(table)

    asyncio.run(_status())


@app.command()
def test():
    """Test the system with a sample task."""
    print_banner()

    async def _test():
        from core.orchestrator import aria
        console.print("[yellow]Running test task...[/yellow]")
        plan = await aria.process(
            "Create a minimal logo concept for a fintech startup called 'Vaultly'",
            context="Target audience: millennials, clean and trustworthy"
        )
        console.print("\n[green]Pipeline Plan:[/green]")
        for step in plan.get("pipeline", []):
            console.print(f"  Step {step['step']}: [{step['agent']}] {step['action']}")
        console.print(f"\nEstimated cost: ${plan.get('estimated_cost_usd', 0)}")
        console.print(f"Requires approval: {plan.get('requires_human_approval', True)}")

    asyncio.run(_test())


if __name__ == "__main__":
    if len(sys.argv) == 1:
        serve()
    else:
        app()
