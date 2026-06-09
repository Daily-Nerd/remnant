"""Global configuration loaded from environment / .env file."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = Path(os.getenv("REMNANT_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "remnant.db"

# ── LLM ───────────────────────────────────────────────────────────────────
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://litellm.litellm.svc.cluster.local:4000")
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# ── Embeddings ────────────────────────────────────────────────────────────
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")

# ── Decay scoring ─────────────────────────────────────────────────────────
DECAY_ALERT_THRESHOLD = float(os.getenv("DECAY_ALERT_THRESHOLD", "0.65"))
COLLISION_SIMILARITY_THRESHOLD = float(os.getenv("COLLISION_SIMILARITY_THRESHOLD", "0.72"))

# ── External APIs ─────────────────────────────────────────────────────────
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
