"""
REMNANT CLI

Commands:
  remnant ingest   --source arxiv --domain "distributed systems" --years 20
  remnant decay    --domain "distributed systems" --top 20
  remnant detect   --query "we keep having cascade failures"
  remnant translate --concept <id> --from-field physics --to-field "organizational behavior"
  remnant stats
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from remnant.config import DB_PATH
from remnant.graph.knowledge_graph import KnowledgeGraph

app = typer.Typer(name="remnant", help="Civilizational memory infrastructure.")
console = Console()


def _graph() -> KnowledgeGraph:
    return KnowledgeGraph(DB_PATH)


@app.command()
def ingest(
    source: str = typer.Option("arxiv", help="Source: arxiv | pubmed"),
    domain: str = typer.Option(..., help="Domain/topic to query"),
    max_results: int = typer.Option(100, help="Max documents to fetch"),
    years: int = typer.Option(20, help="How many years back to fetch"),
):
    """Ingest documents from a source into the knowledge graph."""
    from datetime import datetime, timezone
    from remnant.ingestion.arxiv import ArxivIngester
    from remnant.ingestion.pubmed import PubMedIngester
    from remnant.extraction.concept import extract_concept
    from remnant.extraction.fingerprint import embed
    from remnant.models import DocumentNode
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering

    graph = _graph()
    since_year = datetime.now(timezone.utc).year - years

    ingesters = {"arxiv": ArxivIngester, "pubmed": PubMedIngester}
    if source not in ingesters:
        console.print(f"[red]Unknown source: {source}[/]")
        raise typer.Exit(1)

    ingester = ingesters[source]()

    async def run() -> None:
        docs = []
        console.print(f"[cyan]Fetching {max_results} docs from {source} for '{domain}'...[/]")
        async for doc in ingester.fetch(domain, max_results=max_results, since_year=since_year):
            docs.append(doc)
            graph.upsert_document(DocumentNode(
                id=doc.id, source=doc.source, title=doc.title,
                url=doc.url, published_at=doc.published_at,
            ))

        console.print(f"[green]Fetched {len(docs)} documents. Embedding...[/]")
        if not docs:
            return

        texts = [d.title + " " + d.abstract[:300] for d in docs]
        embeddings = embed(texts)

        # Cluster into concept groups
        n_clusters = max(2, min(len(docs) // 5, 20))
        if len(docs) >= 2:
            clustering = AgglomerativeClustering(
                n_clusters=n_clusters, metric="cosine", linkage="average"
            )
            labels = clustering.fit_predict(embeddings)
        else:
            labels = [0] * len(docs)

        console.print(f"[cyan]Extracting concepts from {n_clusters} clusters...[/]")
        for cluster_id in range(n_clusters):
            cluster_docs = [d for d, l in zip(docs, labels) if l == cluster_id]
            if not cluster_docs:
                continue
            concept = extract_concept(cluster_docs)
            graph.upsert_concept(concept)
            for doc in cluster_docs:
                graph.add_edge(doc.id, concept.id, "EXPRESSES",
                               meta={"year": doc.published_at.year})
            console.print(f"  [green]✓[/] {concept.label} ({len(cluster_docs)} docs)")

        console.print(f"[bold green]Done. Graph: {graph.concept_count()} concepts, "
                      f"{graph.document_count()} documents.[/]")

    asyncio.run(run())


@app.command()
def decay(
    domain: Optional[str] = typer.Option(None, help="Filter by domain"),
    top: int = typer.Option(20, help="Show top N by decay score"),
):
    """Show decay scores for concepts in the graph."""
    from remnant.decay.scorer import run_all
    from remnant.alerts.notifier import print_decay_report

    graph = _graph()
    reports = run_all(graph)
    if domain:
        reports = [r for r in reports if any(domain.lower() in d.lower() for d in r.concept.domains)]

    print_decay_report(reports, top_n=top)
    alerts = [r for r in reports if r.alert]
    console.print(f"\n[bold]Total: {len(reports)} concepts | {len(alerts)} alerts[/]")


@app.command()
def detect(
    query: str = typer.Option(..., help="Text to check for collisions"),
    top: int = typer.Option(5, help="Top N candidates"),
):
    """Detect if a query is approaching an existing concept."""
    from remnant.collision.detector import detect as _detect
    from remnant.alerts.notifier import print_collision_report

    graph = _graph()
    report = _detect(query, graph, top_k=top)
    print_collision_report(report)


@app.command()
def translate(
    concept: str = typer.Option(..., help="Concept ID (from decay or detect output)"),
    from_field: str = typer.Option("", help="Source field (optional, inferred if blank)"),
    to_field: str = typer.Option(..., help="Target field to translate into"),
):
    """Translate a concept into another field's vocabulary."""
    from remnant.translation.broker import translate as _translate
    from remnant.models import TranslationRequest
    from rich.panel import Panel
    from rich.markdown import Markdown

    graph = _graph()
    req = TranslationRequest(concept_id=concept, from_field=from_field, to_field=to_field)
    result = _translate(req, graph)

    console.print(Panel(
        Markdown(result.translation),
        title=f"[bold]{result.concept.label}[/] → {to_field}",
        border_style="cyan",
    ))
    if result.key_analogies:
        console.print("\n[bold]Key analogies:[/]")
        for a in result.key_analogies:
            console.print(f"  • {a}")
    if result.suggested_papers:
        console.print("\n[bold]Suggested reading:[/]")
        for p in result.suggested_papers:
            console.print(f"  • {p}")


@app.command()
def stats():
    """Show graph statistics."""
    graph = _graph()
    console.print(f"[bold cyan]REMNANT Graph Stats[/]")
    console.print(f"  Concepts : {graph.concept_count()}")
    console.print(f"  Documents: {graph.document_count()}")
    console.print(f"  Edges    : {graph.G.number_of_edges()}")


if __name__ == "__main__":
    app()
