"""Alert delivery — CLI (rich), JSON webhook, future: email/Slack."""
from __future__ import annotations

import json
from typing import Callable

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from remnant.models import CollisionReport, DecayReport

console = Console()


def print_decay_report(reports: list[DecayReport], top_n: int = 20) -> None:
    table = Table(title="Epistemic Decay Report", box=box.ROUNDED, show_lines=True)
    table.add_column("Concept", style="bold cyan", max_width=35)
    table.add_column("Domains", style="dim", max_width=30)
    table.add_column("Decay", justify="right")
    table.add_column("Citation Vel.", justify="right")
    table.add_column("Alert", justify="center")

    for r in reports[:top_n]:
        decay_str = f"[red]{r.decay_score:.2f}[/]" if r.alert else f"{r.decay_score:.2f}"
        alert_str = "🔴 YES" if r.alert else "—"
        table.add_row(
            r.concept.label,
            ", ".join(r.concept.domains[:2]),
            decay_str,
            f"{r.citation_velocity:.2f}",
            alert_str,
        )
    console.print(table)


def print_collision_report(report: CollisionReport) -> None:
    if not report.candidates:
        console.print("[green]No collision candidates found.[/]")
        return

    if report.top_alert:
        console.print(Panel(
            f"[bold red]⚠️  COLLISION ALERT[/bold red]\n\n"
            f"[bold]{report.top_alert.concept.label}[/bold]\n"
            f"Similarity: {report.top_alert.similarity:.0%} | "
            f"Decay: {report.top_alert.concept.decay_score:.2f}\n\n"
            f"{report.top_alert.concept.description[:300]}",
            title="You may be re-deriving existing knowledge",
            border_style="red",
        ))

    table = Table(title="Collision Candidates", box=box.ROUNDED)
    table.add_column("Concept", style="bold", max_width=35)
    table.add_column("Similarity", justify="right")
    table.add_column("Relevance", justify="right")
    table.add_column("Alert")

    for c in report.candidates:
        table.add_row(
            c.concept.label,
            f"{c.similarity:.0%}",
            f"{c.relevance_score:.3f}",
            "🔴" if c.alert else "—",
        )
    console.print(table)


async def send_webhook(url: str, payload: dict) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json=payload)
