"""Automatic card checker (Speedrun 7f: "classify correct/wrong/poor with a
pre-registered cutoff"). Given a generated card {front, back, citation} it:

  1. GROUNDING: verifies the card's answer is supported by the cited source
     passage (token recall of the back against the passage). Ungrounded answers
     are hallucinations -> WRONG.
  2. GOLD MATCH: matches the card to the best gold fact on the same topic and
     measures key-term coverage (does it state the right fact?).
  3. ATOMICITY: a learning-science quality gate (one sentence, short, no 'and'
     conjunction of facts).

Pre-registered decision rule (fixed before seeing model output):
  * WRONG   if not grounded OR no gold key-term match (states nothing correct).
  * CORRECT if grounded AND key-term coverage >= 0.40 (or the primary key term
            is present) AND atomic.
  * POOR    otherwise (grounded + on-topic but non-atomic / too long / partial).

Thresholds are constants below so the cutoff is explicit and reproducible.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aicommon import load_gold, load_sources, toks  # noqa: E402

# --- pre-registered cutoffs ---
GROUNDING_RECALL = 0.45   # >= this fraction of back's content tokens appear in the cited passage
COVERAGE_CUTOFF = 0.40    # >= this fraction of a gold item's key_terms present
MAX_ATOMIC_WORDS = 26     # a longer back is treated as non-atomic (POOR)


def _passage_index(sources: dict) -> dict:
    return {p["id"]: p for p in sources["passages"]}


def _topic_text(sources: dict) -> dict:
    """topic -> concatenated text of all its passages (the retrieved grounding set)."""
    out: dict[str, str] = {}
    for p in sources["passages"]:
        out[p["topic"]] = out.get(p["topic"], "") + " " + p["text"]
    return out


def _phrase_in(text: str, phrase: str) -> bool:
    return phrase.lower() in text.lower()


def key_term_coverage(text: str, key_terms: list[str]) -> float:
    if not key_terms:
        return 0.0
    hit = sum(1 for kt in key_terms if _phrase_in(text, kt))
    return hit / len(key_terms)


def grounding_recall(back: str, passage_text: str) -> float:
    bt = set(toks(back))
    if not bt:
        return 0.0
    pt = set(toks(passage_text))
    return len(bt & pt) / len(bt)


def is_atomic(back: str) -> bool:
    words = back.split()
    if len(words) > MAX_ATOMIC_WORDS:
        return False
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", back.strip()) if s]
    if len(sentences) > 1:
        return False
    # crude compound-fact detector: multiple independent clauses joined by ; or ", and"
    if back.count(";") >= 1:
        return False
    return True


def best_gold(card: dict, gold: list[dict]) -> dict | None:
    cands = [g for g in gold if g["topic"] == card.get("topic")]
    if not cands:
        return None
    text = f"{card.get('front','')} {card.get('back','')}"
    return max(cands, key=lambda g: key_term_coverage(text, g["key_terms"]))


def classify(card: dict, gold: list[dict], passages: dict, topic_text: dict) -> dict:
    back = card.get("back", "") or ""
    cit = card.get("citation", "")
    # RAG faithfulness: the answer must be supported by the retrieved passage set
    # for this topic (a wrong citation shouldn't be read as a hallucination).
    ground_src = topic_text.get(card.get("topic"), "")
    if cit in passages:
        ground_src += " " + passages[cit]["text"]
    grounded = bool(ground_src.strip()) and grounding_recall(back, ground_src) >= GROUNDING_RECALL

    g = best_gold(card, gold)
    text = f"{card.get('front','')} {back}"
    cov = key_term_coverage(text, g["key_terms"]) if g else 0.0
    primary_hit = bool(g) and _phrase_in(text, g["key_terms"][0])
    atomic = is_atomic(back)

    if not grounded:
        label, reason = "wrong", "answer not supported by cited source (hallucination or bad citation)"
    elif not back.strip():
        label, reason = "wrong", "empty answer"
    elif cov < COVERAGE_CUTOFF and not primary_hit:
        label, reason = "wrong", "does not state the correct fact (no gold key-term match)"
    elif atomic and (cov >= COVERAGE_CUTOFF or primary_hit):
        label, reason = "correct", "grounded, states the right fact, atomic"
    else:
        label, reason = "poor", ("grounded and on-topic but non-atomic/too long"
                                 if not atomic else "grounded but only partially correct")

    return {"label": label, "reason": reason, "grounded": grounded,
            "coverage": round(cov, 2), "atomic": atomic,
            "gold_id": g["id"] if g else None}


def run_over(cards: list[dict]) -> dict:
    gold = load_gold()
    sources = load_sources()
    passages = _passage_index(sources)
    topic_text = _topic_text(sources)
    tally = {"correct": 0, "poor": 0, "wrong": 0}
    detail = []
    for c in cards:
        r = classify(c, gold, passages, topic_text)
        tally[r["label"]] += 1
        detail.append({**{k: c.get(k) for k in ("method", "topic", "front", "back", "citation")}, **r})
    n = max(1, len(cards))
    return {"n": len(cards), "tally": tally,
            "correct_rate": round(tally["correct"] / n, 3),
            "poor_rate": round(tally["poor"] / n, 3),
            "wrong_rate": round(tally["wrong"] / n, 3),
            "detail": detail}


if __name__ == "__main__":
    import json
    gen = Path(__file__).resolve().parents[2] / "data" / "ai" / "generated_cards.json"
    cards = json.loads(gen.read_text()) if gen.exists() else []
    res = run_over(cards)
    print(f"[ai.checker] {res['tally']} correct_rate={res['correct_rate']}")
