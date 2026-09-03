"""CLI for the Multi-Agent Research Assistant.

Usage:
    python -m app.cli research "Compare DataSphere 1 and QuantumSoft 2 pricing"
    python -m app.cli approvals list
    python -m app.cli approvals show <approval_id>
    python -m app.cli approvals approve <approval_id> --reviewer "Jane Doe"
    python -m app.cli approvals reject <approval_id> --reviewer "Jane Doe" --comment "needs more data"
"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from app.runner import run_research_stream
from app.tools.approval_store import decide, get_approval, list_pending

app = typer.Typer(help="Multi-Agent Research Assistant CLI")
approvals_app = typer.Typer(help="Manage report approvals")
app.add_typer(approvals_app, name="approvals")

console = Console()


@app.command()
def research(task: str, session_id: str = typer.Option(None, help="Reuse an existing session id")):
    """Run the Supervisor -> Researcher -> Writer -> Human Approval workflow."""
    console.print(f"[bold cyan]Starting research:[/bold cyan] {task}")
    last_route = None
    for state in run_research_stream(task, session_id=session_id):
        route = state.get("route")
        if route and route.value != last_route:
            console.print(f"[yellow]-> routed to {route.value}[/yellow]  ({state.get('route_reason', '')})")
            last_route = route.value

    draft = state.get("draft")
    approval = state.get("approval")
    if draft:
        console.print(Markdown(f"# {draft.title}\n\n{draft.executive_summary}"))
        console.print(f"[green]Full report saved to:[/green] {state.get('report_path')}")
    if approval:
        console.print(
            f"[bold magenta]Filed for human approval[/bold magenta] - approval_id: {approval.approval_id}"
        )
        console.print("Review with: python -m app.cli approvals show " + approval.approval_id)


@approvals_app.command("list")
def approvals_list():
    pending = list_pending()
    if not pending:
        console.print("No pending approvals.")
        return
    table = Table(title="Pending Approvals")
    table.add_column("approval_id")
    table.add_column("session_id")
    table.add_column("title")
    table.add_column("created_at")
    for a in pending:
        table.add_row(a.approval_id, a.session_id, a.report_title, str(a.created_at))
    console.print(table)


@approvals_app.command("show")
def approvals_show(approval_id: str):
    approval = get_approval(approval_id)
    if not approval:
        console.print(f"[red]No approval found with id {approval_id}[/red]")
        raise typer.Exit(code=1)
    console.print(Markdown(approval.report_markdown))
    console.print(f"Status: [bold]{approval.status.value}[/bold]")


@approvals_app.command("approve")
def approvals_approve(approval_id: str, reviewer: str = typer.Option(...), comment: str = typer.Option(None)):
    approval = decide(approval_id, approved=True, reviewer=reviewer, comment=comment)
    console.print(f"[green]Approved[/green] {approval.approval_id} by {reviewer}")


@approvals_app.command("reject")
def approvals_reject(approval_id: str, reviewer: str = typer.Option(...), comment: str = typer.Option(None)):
    approval = decide(approval_id, approved=False, reviewer=reviewer, comment=comment)
    console.print(f"[red]Rejected[/red] {approval.approval_id} by {reviewer}")


if __name__ == "__main__":
    app()
