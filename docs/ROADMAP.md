# REMNANT — Roadmap

## Phase 0: Foundation (Current)
- [x] Repo scaffolding
- [x] Architecture spec
- [ ] Core data models (pydantic)
- [ ] SQLite persistence layer
- [ ] Knowledge graph (NetworkX)
- [ ] arXiv ingestion adapter
- [ ] Basic concept extraction (embeddings only, no LLM labeling yet)
- [ ] CLI skeleton (`remnant ingest`, `remnant decay`, `remnant detect`)

## Phase 1: MVP — Single Domain (Weeks 2–4)
- [ ] PubMed ingestion adapter
- [ ] LLM concept labeling (OpenAI / local via LiteLLM)
- [ ] Decay scoring v1 (citation velocity only)
- [ ] Collision detection v1 (embedding similarity)
- [ ] CLI: `remnant translate`
- [ ] `.env.example` + config docs
- [ ] Tests for decay model + collision detector
- [ ] Seed corpus: "distributed systems" (1990–2026)
- [ ] Demo: 10 forgotten concepts with decay scores

## Phase 2: Cross-Domain (Weeks 5–8)
- [ ] Multi-domain ingestion (CS + Biology + Physics + Economics)
- [ ] Cross-domain edge detection in knowledge graph
- [ ] Translation broker v1 (LLM-powered)
- [ ] Decay scoring v2 (cross-domain penetration added)
- [ ] Practitioner profile builder (from GitHub + arXiv author pages)
- [ ] Alert webhook delivery

## Phase 3: Production Hardening (Weeks 9–12)
- [ ] Async ingestion pipeline (APScheduler)
- [ ] Incremental updates (only re-process changed/new docs)
- [ ] API server (FastAPI) for external integrations
- [ ] Email digest delivery
- [ ] Dashboard (simple HTML, no framework)
- [ ] First real user: a research org or pharma team

## Phase 4: Scale (Month 4+)
- [ ] GitHub Issues / HN / Reddit ingestion
- [ ] Patent database ingestion
- [ ] Real-time collision detection API
- [ ] Slack / Discord bot integration
- [ ] Multi-tenant practitioner profiles
- [ ] Enterprise pilot (pharma or infrastructure)

## North Star Metric
**Collision detections that changed what someone did.** Not alerting volume. Actual prevented re-inventions, with before/after attribution.
