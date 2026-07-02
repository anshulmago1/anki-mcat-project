"""Shared helpers for the local-AI layer: a stdlib Ollama client, a tiny TF-IDF
retriever for RAG, source/gold loaders, and a disk cache so `make ai` is
reproducible without re-calling the model.

No third-party deps beyond numpy (already used by the harness). The LLM runs
locally via Ollama (privacy-preserving, offline-capable per Speedrun sec. 6/7f).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
AI = DATA / "ai"
EVAL = DATA / "eval"
CACHE = AI / "cache.json"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_TAGS = "http://localhost:11434/api/tags"
MODEL = "llama3"

_TOKEN = re.compile(r"[a-z0-9+']+")
_STOP = {"the", "a", "an", "of", "to", "in", "on", "and", "or", "is", "are", "does",
         "do", "what", "which", "for", "with", "at", "by", "its", "it", "this", "that",
         "how", "why", "as", "be", "you", "your", "from", "than", "into", "when", "where"}


def toks(s: str) -> list[str]:
    return [t for t in _TOKEN.findall(s.lower()) if t not in _STOP]


def load_sources() -> dict:
    return json.loads((AI / "sources.json").read_text())


def load_gold() -> list[dict]:
    return json.loads((AI / "gold_set.json").read_text())["items"]


def ollama_available(timeout: float = 4.0) -> bool:
    try:
        req = urllib.request.Request(OLLAMA_TAGS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _cache_load() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text())
        except Exception:
            return {}
    return {}


def _cache_save(c: dict) -> None:
    AI.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(c, indent=2))


def ollama_generate(prompt: str, temperature: float = 0.0, seed: int = 7,
                    use_cache: bool = True) -> str:
    """Call the local model. Cached by prompt hash for reproducibility."""
    key = hashlib.sha256(f"{MODEL}|{temperature}|{seed}|{prompt}".encode()).hexdigest()
    cache = _cache_load()
    if use_cache and key in cache:
        return cache[key]
    body = json.dumps({
        "model": MODEL, "prompt": prompt, "stream": False,
        "options": {"temperature": temperature, "seed": seed},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.loads(r.read().decode())["response"]
    cache[key] = out
    _cache_save(cache)
    return out


class TfidfRetriever:
    """Tiny TF-IDF cosine retriever over the source passages (numpy only)."""

    def __init__(self, passages: list[dict]):
        self.passages = passages
        self.docs = [toks(p["text"]) for p in passages]
        vocab = sorted(set().union(*self.docs)) if self.docs else []
        self.idx = {w: i for i, w in enumerate(vocab)}
        n = len(passages)
        df = np.zeros(len(vocab))
        for d in self.docs:
            for w in set(d):
                df[self.idx[w]] += 1
        self.idf = np.log((1 + n) / (1 + df)) + 1
        self.mat = np.array([self._vec(d) for d in self.docs]) if passages else np.zeros((0, 0))

    def _vec(self, tokens: list[str]) -> np.ndarray:
        v = np.zeros(len(self.idx))
        for w in tokens:
            if w in self.idx:
                v[self.idx[w]] += 1
        if tokens:
            v *= self.idf
            nrm = np.linalg.norm(v)
            if nrm:
                v /= nrm
        return v

    def top_k(self, query: str, k: int = 3) -> list[dict]:
        if len(self.passages) == 0:
            return []
        q = self._vec(toks(query))
        sims = self.mat @ q
        order = np.argsort(-sims)[:k]
        return [self.passages[i] for i in order]


def extract_json(text: str) -> dict | None:
    """Pull the first {...} object out of an LLM response (tolerates ```json fences)."""
    if "```" in text:
        # strip code fences; keep inner content
        parts = text.split("```")
        for seg in parts:
            seg = seg.strip()
            if seg.startswith("json"):
                seg = seg[4:].strip()
            if seg.startswith("{"):
                text = seg
                break
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    return None
    return None


def die_if_no_ollama() -> None:
    if not ollama_available():
        print("[ai] Ollama not reachable at localhost:11434. Start it with "
              "`ollama serve` and `ollama pull llama3`, then re-run.",
              file=sys.stderr)
        sys.exit(2)
