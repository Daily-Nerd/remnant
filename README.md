# REMNANT
### *Civilizational Memory Infrastructure*

> Because the worst thing a civilization can do is solve a problem twice.

REMNANT is an epistemic decay monitoring system. It tracks the attention half-life of human knowledge across fields, detects when practitioners are about to re-derive something already solved, and brokers cross-domain concept translations before the wheel gets reinvented.

---

## The Problem

You have Google. You have arXiv. You have every paper ever written.

But **knowing something is stored somewhere** and **knowing it exists when you need it** are completely different things.

- Bacteriophage therapy was standard Soviet medicine in the 1940s. "Discovered" again in 2020 as antibiotic resistance peaked — decades of patient deaths in the gap.
- Eventual consistency, vector clocks, gossip protocols — all in Bell Labs papers from the 70s. Every few years a startup "invents" them.
- The Tacoma Narrows Bridge (1940): the failure mode was documented in earlier bridge collapses. The knowledge existed. It wasn't salient.

This isn't ignorance. This is a structural failure in how knowledge stays alive.

---

## What REMNANT Does

**Five layers:**

| Layer | What it does |
|-------|-------------|
| **Ingestion** | Continuous indexing of arXiv, PubMed, ACM, patents, SO, HN, GitHub |
| **Concept Extraction** | Maps the *underlying idea* independent of vocabulary — same concept, three fields, one node |
| **Decay Modeling** | Tracks attention half-life per concept-node; flags when important ideas go dark |
| **Collision Detection** | Detects ambient signal that someone is re-deriving something — alerts *before* the question is formed |
| **Translation Brokering** | Surfaces concepts from Field A to practitioners in Field B, in their vocabulary |

---

## Architecture

```
remnant/
├── ingestion/      # Source adapters (arxiv, pubmed, web, github)
├── extraction/     # Concept extraction + semantic fingerprinting
├── decay/          # Temporal salience modeling + decay scoring
├── collision/      # Problem-pattern detection + alert generation
├── translation/    # Cross-domain concept translation engine
├── graph/          # Knowledge graph (NetworkX + persistent store)
└── alerts/         # Notification delivery (email, webhook, CLI)
```

---

## Quickstart

```bash
git clone https://github.com/Daily-Nerd/remnant
cd remnant
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # add your API keys

# Seed the corpus with a domain
remnant ingest --source arxiv --domain "distributed systems" --years 20

# Check decay scores for a domain
remnant decay --domain "distributed systems" --top 20

# Run collision detection against a query
remnant detect --query "we keep having cascade failures in our microservices"

# Get a cross-domain translation
remnant translate --concept "phase transitions" --from-field physics --to-field "organizational behavior"
```

---

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md).

---

## License

MIT — Daily-Nerd
