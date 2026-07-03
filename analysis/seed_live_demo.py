"""Seed a LIVE Anki collection with a realistic mid-progress MCAT state so the
in-app readiness card + knowledge graph show real data (not an empty profile).

It ADDS to the given collection (does not wipe it):
  * MCAT-tagged cards with uneven coverage (BB/CP well covered, PS partial,
    CARS sparse) so the give-up rule visibly trips on the weak sections,
  * enough reviews (3 passes) that BB/CP clear the 200-graded-review gate while
    PS/CARS stay below it,
  * a `mcat_perf` config (per-section answered exam-style items, each with 3PL
    item params a/b/c and the 0/1 outcome) so the desktop caller can estimate a
    genuine 3PL-IRT ability (θ) + Fisher SE and compute P_s for the well-covered
    sections.

Result in the app: BB & CP show projected section scores; PS & CARS are withheld;
the total is withheld (honesty rule) because not every section qualifies; the
knowledge graph is colored by real mastery.

Usage: ANKI_PY seed_live_demo.py "/path/to/collection.anki2"   (app must be closed)
"""
from __future__ import annotations

import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

from common import add_anki_to_path, all_topics, load_outline

# per-section mastery gradient (FSRS stability days) -> drives Memory score colors
SECTION_STABILITY = {"BB": 30, "CP": 20, "PS": 12, "CARS": 6}
# days since last review (older -> lower retrievability -> more believable, sub-cap)
SECTION_ELAPSED = {"BB": (8, 30), "CP": (14, 45), "PS": (20, 60), "CARS": (25, 70)}

SECTION_CARDS_PER_TOPIC = {"BB": 12, "CP": 11, "PS": 5, "CARS": 4}
SECTION_REVIEW_FRAC = {"BB": 0.95, "CP": 0.9, "PS": 0.6, "CARS": 0.4}
SECTION_TOPIC_COVERAGE = {"BB": 1.0, "CP": 1.0, "PS": 0.625, "CARS": 0.34}

# Performance from answered exam-style questions. The desktop caller runs a real
# 3PL-IRT ability estimate (grid MLE θ + Fisher SE) over these items, so we must
# seed genuine per-item 3PL params + Bernoulli outcomes rather than correct/total.
# BB is strongest, then CP, then PS (weaker); CARS has none -> abstains. Enough
# items per covered section that the Fisher SE lands < 0.5 (won't abstain on SE).
PERF_SEED = 5
PERF_TRUE_THETA = {"BB": 1.2, "CP": 0.7, "PS": -0.3}
PERF_N_ITEMS = {"BB": 40, "CP": 40, "PS": 18}
PERF_GUESS_C = 0.25  # 4-choice MCQ


def _p3pl(theta: float, a: float, b: float, c: float) -> float:
    return c + (1 - c) / (1 + math.exp(-a * (theta - b)))


def build_mcat_perf() -> dict:
    """Per-section answered exam-style items with 3PL params + Bernoulli outcomes.

    a ~ N(1.1, 0.35) (clipped to [0.3, 2.5], matching analysis/simulate.py),
    b ~ N(0, 1), c = 0.25, correct ~ Bernoulli(p3pl(true_theta, item)). Uses the
    stdlib RNG (dedicated seed) so this stays runnable under the numpy-free Anki
    interpreter that launches this script.
    """
    g = random.Random(PERF_SEED)
    perf: dict[str, dict] = {}
    for sec, n in PERF_N_ITEMS.items():
        theta = PERF_TRUE_THETA[sec]
        items = []
        for _ in range(n):
            a = round(min(max(g.gauss(1.1, 0.35), 0.3), 2.5), 3)
            b = round(g.gauss(0.0, 1.0), 3)
            p = _p3pl(theta, a, b, PERF_GUESS_C)
            items.append({
                "a": a,
                "b": b,
                "c": PERF_GUESS_C,
                "correct": int(g.random() < p),
            })
        perf[sec] = {"items": items}
    return perf


def section_of(tags):
    for t in tags:
        p = t.split("::")
        if len(p) >= 2 and p[0] == "mcat":
            return p[1].upper()
    return "?"


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: seed_live_demo.py <collection.anki2>")
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"collection not found: {path}")
        sys.exit(1)

    add_anki_to_path()
    from anki.collection import Collection

    col = Collection(str(path))
    g = random.Random(5)
    try:
        col.set_config("fsrs", True)
    except Exception:
        pass

    outline = load_outline()
    covered = set()
    for sec, body in outline["sections"].items():
        topics = [t["id"] for t in body["topics"]]
        k = max(1, round(len(topics) * SECTION_TOPIC_COVERAGE[sec]))
        covered.update(topics[:k])

    deck_id = col.decks.id("MCAT::Readygauge")
    # avoid double-seeding if run twice
    already = len(col.find_cards("tag:mcat::*"))
    total = 0
    if already < 50:
        for topic in all_topics(outline):
            if topic["id"] not in covered:
                continue
            n = SECTION_CARDS_PER_TOPIC[topic["section"]]
            for i in range(n):
                note = col.newNote()
                note["Front"] = f"{topic['label']} - probe {i}"
                note["Back"] = f"Answer for {topic['id']} #{i}"
                note.tags = [topic["id"]]
                col.add_note(note, deck_id)
                total += 1

    # Assign FSRS memory states + review counts directly to a fraction of the
    # covered cards. graded_reviews (the give-up gate) reads card.reps, and
    # retrievability reads memory_state, so this reliably produces a mid-progress
    # state that clears the gate for well-studied sections. (The scheduler won't
    # let you rack up 200+ reviews in one session because cards graduate.)
    from anki.cards import FSRSMemoryState
    from anki.consts import CARD_TYPE_REV
    col.decks.set_current(deck_id)
    now = int(time.time())
    batch = []
    per_sec_reps: dict[str, int] = defaultdict(int)
    reviewed = 0
    for cid in col.find_cards("tag:mcat::*"):
        card = col.get_card(cid)
        sec = section_of(card.note().tags)
        if g.random() > SECTION_REVIEW_FRAC.get(sec, 0.5):
            continue  # leave as a "new" (unstudied) card
        base = SECTION_STABILITY.get(sec, 50)
        stab = g.uniform(base * 0.5, base * 1.5)
        lo, hi = SECTION_ELAPSED.get(sec, (10, 40))
        card.memory_state = FSRSMemoryState(stability=stab, difficulty=g.uniform(4, 7))
        card.reps = g.randint(4, 12)
        card.type = CARD_TYPE_REV
        card.last_review_time = now - g.randint(lo, hi) * 86400
        per_sec_reps[sec] += card.reps
        reviewed += 1
        batch.append(card)
        if len(batch) >= 500:
            col.update_cards(batch); batch = []
    if batch:
        col.update_cards(batch)

    # seed performance from answered exam-style questions (3PL items)
    mcat_perf = build_mcat_perf()
    col.set_config("mcat_perf", mcat_perf)

    n_state = sum(1 for cid in col.find_cards("tag:mcat::*")
                  if getattr(col.get_card(cid), "memory_state", None) is not None)
    col.close()
    perf_counts = {s: f"{sum(i['correct'] for i in v['items'])}/{len(v['items'])}"
                   for s, v in mcat_perf.items()}
    print(f"[seed] collection: {path}")
    print(f"[seed] added_cards={total} studied_cards={reviewed} cards_with_memory_state={n_state}")
    print(f"[seed] graded_reviews per section: {dict(per_sec_reps)}")
    print(f"[seed] mcat_perf 3PL items seeded (correct/total shown): {perf_counts} (CARS omitted -> abstains)")
    print("[seed] done. Relaunch Anki and open Stats.")


if __name__ == "__main__":
    main()
