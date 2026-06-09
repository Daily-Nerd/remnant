#!/usr/bin/env python
"""
Seed the REMNANT corpus with foundational domains.

Usage:
    python scripts/seed_corpus.py
    python scripts/seed_corpus.py --domains "distributed systems" biology
    python scripts/seed_corpus.py --source pubmed --max 200
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from remnant.cli import app
import typer

SEED_DOMAINS = [
    "distributed systems consensus fault tolerance",
    "antibiotic resistance bacteriophage therapy",
    "network resilience cascade failure",
    "urban planning community displacement",
    "phase transitions complex systems",
    "immune memory adaptive response",
]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--domains", nargs="+", default=SEED_DOMAINS)
    parser.add_argument("--source", default="arxiv")
    parser.add_argument("--max", type=int, default=50)
    parser.add_argument("--years", type=int, default=30)
    args = parser.parse_args()

    for domain in args.domains:
        print(f"\n>>> Seeding: {domain}")
        from typer.testing import CliRunner
        runner = typer.testing.CliRunner()
        result = runner.invoke(app, [
            "ingest",
            "--source", args.source,
            "--domain", domain,
            "--max-results", str(args.max),
            "--years", str(args.years),
        ])
        print(result.output)
        if result.exit_code != 0 and result.exception:
            print(f"Error: {result.exception}")
