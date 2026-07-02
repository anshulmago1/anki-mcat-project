"""Longitudinal persona simulation against the REAL engine, with genuine
forgetting/decay.

A virtual student studies the MCAT deck over N weeks. We evolve each card's FSRS
state (stability/difficulty) day by day using an FSRS-consistent update, and -
crucially - the forgetting curve itself is the ENGINE's: at each weekly snapshot
we write each card's memory_state + a backdated last_review_time into a real Anki
collection, then call the in-engine `compute_readiness` RPC. So the retrievability
decay, the three scores, and the give-up rule all come from the engine.

Usage:
  python simulate_persona.py --persona consistent --weeks 12 [--out file.csv]

Personas: consistent | crammer | cars_neglecter
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import time
from pathlib import Path

from common import DATA, add_anki_to_path, load_outline, section_topic_weights, all_topics

DECAY = 0.2
FACTOR = 0.9 ** (-1.0 / DECAY) - 1.0
SECTIONS = ["BB", "CP", "PS", "CARS"]

PERSONAS = {
    # studies steadily, reviews due cards (spacing), interleaves, all sections
    "consistent": dict(days_per_week=5, new_per_session=8, reviews_per_session=40,
                       sections=SECTIONS, spacing=True, interleave=True,
                       skill=0.0, start_week=0),
    # crams everything into the last 3 weeks, massed, little spacing
    "crammer": dict(days_per_week=6, new_per_session=30, reviews_per_session=30,
                    sections=SECTIONS, spacing=False, interleave=False,
                    skill=-0.1, start_week=9),
    # studies science well, never touches CARS -> CARS coverage stays 0
    "cars_neglecter": dict(days_per_week=5, new_per_session=8, reviews_per_session=40,
                           sections=["BB", "CP", "PS"], spacing=True, interleave=True,
                           skill=0.05, start_week=0),
}


def retr(elapsed_days: float, stability: float) -> float:
    return (1.0 + FACTOR * elapsed_days / max(stability, 1e-6)) ** (-DECAY)


class CardState:
    __slots__ = ("topic", "section", "stability", "difficulty", "last_day", "reps")

    def __init__(self, topic, section, day):
        self.topic = topic
        self.section = section
        self.stability = 2.5          # initial "Good" stability (days)
        self.difficulty = 5.0
        self.last_day = day
        self.reps = 1

    def review(self, day, skill, g):
        elapsed = day - self.last_day
        r_true = retr(elapsed, self.stability)
        recalled = g.random() < min(0.99, max(0.02, r_true + skill))
        if recalled:
            self.stability *= 1.0 + 0.9 * (1.0 - r_true) * (11.0 - self.difficulty) / 6.0
            self.difficulty = max(1.0, self.difficulty - 0.15)
        else:
            self.stability = max(1.0, self.stability * 0.5)
            self.difficulty = min(10.0, self.difficulty + 0.5)
        self.last_day = day
        self.reps += 1


def topic_pool(outline, sections):
    return [t for t in all_topics(outline) if t["section"] in sections]


def simulate(persona_name: str, weeks: int, g: random.Random):
    outline = load_outline()
    p = PERSONAS[persona_name]
    pool = topic_pool(outline, p["sections"])
    cards: list[CardState] = []
    pool_idx = 0
    snapshots = []  # per-week card snapshots: list of (stability, difficulty, days_since_last, topic, section, reps)

    for week in range(1, weeks + 1):
        for dow in range(7):
            day = (week - 1) * 7 + dow
            studying = (dow < p["days_per_week"]) and (week - 1 >= p["start_week"])
            if not studying:
                continue
            # review due cards (spacing): elapsed >= stability
            due = [c for c in cards if (day - c.last_day) >= (c.stability if p["spacing"] else 0.5)]
            if not p["interleave"]:
                due.sort(key=lambda c: c.section)  # blocked
            else:
                g.shuffle(due)
            for c in due[: p["reviews_per_session"]]:
                c.review(day, p["skill"], g)
            # introduce new cards (expand coverage)
            for _ in range(p["new_per_session"]):
                if pool_idx >= len(pool):
                    break
                t = pool[pool_idx]; pool_idx += 1
                cards.append(CardState(t["id"], t["section"], day))
        # weekly snapshot
        now_day = week * 7
        snap = [(c.topic, c.section, c.stability, c.difficulty, now_day - c.last_day, c.reps) for c in cards]
        snapshots.append(snap)
    return outline, snapshots


def build_collection_for_snapshot(col_path: Path, snap, weights):
    """Write the snapshot into a real Anki collection (memory_state + backdated
    last_review_time) and return the engine's compute_readiness response."""
    add_anki_to_path()
    from anki.collection import Collection
    from anki.cards import FSRSMemoryState
    from anki import stats_pb2

    if col_path.exists():
        col_path.unlink()
    col = Collection(str(col_path))
    col.set_config("fsrs", True)
    now = int(time.time())
    DAY = 86400

    # add a card per studied item with its decayed memory state
    section_reviews = {s: 0 for s in SECTIONS}
    section_perf_reviews = {s: 0 for s in SECTIONS}
    for topic, section, stability, difficulty, days_since, reps in snap:
        note = col.newNote()
        note["Front"] = f"{topic} probe"
        note["Back"] = "answer"
        note.tags = [topic]
        col.addNote(note)
        card = note.cards()[0]
        card.memory_state = FSRSMemoryState(stability=float(stability), difficulty=float(difficulty))
        card.decay = DECAY
        card.last_review_time = now - int(days_since * DAY)
        card.reps = int(reps)
        col.update_card(card)
        section_reviews[section] += int(reps)

    # performance model: P_s grows with cumulative reviews per section (learning curve)
    sections_in = []
    for sec in SECTIONS:
        reviews = section_reviews[sec]
        p_s = 0.35 + 0.5 * (1.0 - math.exp(-reviews / 120.0))  # ceiling ~0.85
        theta_se = max(0.2, 1.5 / math.sqrt(reviews + 1))
        sections_in.append(stats_pb2.ReadinessSectionInput(
            section=sec, topic_prefix=f"mcat::{sec.lower()}",
            topic_weights=weights[sec], performance=p_s, theta_se=theta_se,
            alpha_space=1.0, alpha_inter=1.0, alpha_test=1.0,
        ))
    params = stats_pb2.ReadinessParams(
        b0=-1.0, b_m=1.3, b_p=2.2, b_c=0.5,
        min_graded_reviews=200, min_coverage=0.5, max_irt_se=0.5,
    )
    resp = col._backend.compute_readiness(
        search="", mastered_threshold=0.7, sections=sections_in, params=params)
    col.close()
    return resp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", choices=list(PERSONAS), default="consistent")
    ap.add_argument("--weeks", type=int, default=12)
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    g = random.Random(args.seed)
    outline, snapshots = simulate(args.persona, args.weeks, g)
    weights = section_topic_weights(outline)
    col_path = DATA / "sim_persona" / f"{args.persona}.anki2"
    col_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    print(f"\n=== PERSONA: {args.persona}  ({args.weeks} weeks) ===")
    print(f"{'wk':>2} | {'B/B':^16} | {'C/P':^16} | {'P/S':^16} | {'CARS':^16} | total")
    for wk, snap in enumerate(snapshots, 1):
        resp = build_collection_for_snapshot(col_path, snap, weights)
        sec_by = {s.section: s for s in resp.sections}
        cells = []
        row = {"week": wk}
        for sec in SECTIONS:
            s = sec_by[sec]
            mem = s.memory.value
            rd = "WTHLD" if s.readiness.abstained else f"{s.readiness.value:.0f}"
            cov = s.memory.coverage_pct
            cells.append(f"M{mem:.2f} C{cov:.0f}% {rd:>5}")
            row[f"{sec}_memory"] = round(mem, 3)
            row[f"{sec}_coverage"] = round(cov, 1)
            row[f"{sec}_reviews"] = s.memory.graded_reviews
            row[f"{sec}_readiness"] = None if s.readiness.abstained else round(s.readiness.value, 1)
        tot = resp.total
        total_disp = "WITHHELD" if tot.abstained else f"{tot.value:.0f} [{tot.range_lo:.0f}-{tot.range_hi:.0f}]"
        row["total"] = None if tot.abstained else round(tot.value, 0)
        rows.append(row)
        print(f"{wk:>2} | " + " | ".join(cells) + f" | {total_disp}")

    out = Path(args.out) if args.out else DATA / "sim_persona" / f"{args.persona}_timeline.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n[persona] timeline -> {out}")
    _behavior_summary(args.persona, rows)


def _behavior_summary(persona, rows):
    print("\n--- model behavior checks ---")
    # forgetting: did any section's memory drop week-over-week somewhere?
    drops = any(rows[i][f"{s}_memory"] < rows[i - 1][f"{s}_memory"] - 0.02
                for i in range(1, len(rows)) for s in SECTIONS
                if rows[i].get(f"{s}_memory") and rows[i - 1].get(f"{s}_memory"))
    print(f"  forgetting/decay observed (memory dipped between weeks): {drops}")
    first_score = next((r["week"] for r in rows if r["total"] is not None), None)
    print(f"  first week a TOTAL readiness was shown (give-up lifted): {first_score}")
    cars_ever = any(r["CARS_readiness"] is not None for r in rows)
    print(f"  CARS ever scored: {cars_ever}")
    last = rows[-1]
    print(f"  final week: total={last['total']} | "
          + " ".join(f"{s}:cov{last[f'{s}_coverage']:.0f}%/rev{last[f'{s}_reviews']}" for s in SECTIONS))


if __name__ == "__main__":
    main()
