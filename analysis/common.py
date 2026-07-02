"""Shared helpers for the MCAT readiness analysis harness.

Everything here is deliberately dependency-light (numpy only) so `make eval`
runs anywhere. Anki is imported lazily and only when a real collection is needed.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ANKI = ROOT / "anki"


def load_outline() -> dict:
    with open(DATA / "aamc_outline.json") as f:
        return json.load(f)


def section_topic_weights(outline: dict) -> dict[str, dict[str, float]]:
    """section -> {topic_id -> within-section weight}."""
    out = {}
    for sec, body in outline["sections"].items():
        out[sec] = {t["id"]: t["weight"] for t in body["topics"]}
    return out


def all_topics(outline: dict) -> list[dict]:
    rows = []
    for sec, body in outline["sections"].items():
        for t in body["topics"]:
            rows.append({**t, "section": sec})
    return rows


def add_anki_to_path() -> None:
    """Put the built pylib on sys.path so `import anki` works."""
    for p in (ANKI / "out" / "pylib", ANKI / "pylib"):
        if p.exists() and str(p) not in sys.path:
            sys.path.insert(0, str(p))


def rng(seed: int = 7):
    import numpy as np  # lazy: only the numpy-based eval scripts need this
    return np.random.default_rng(seed)
