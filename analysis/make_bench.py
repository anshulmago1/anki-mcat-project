"""One-command benchmark on the shared 50,000-card deck (Speedrun 7h + sec. 10).

Builds (once, then caches) a 50k-card MCAT collection tagged per the AAMC outline
with FSRS memory states, then times each dashboard/review action the readiness
features add, reporting p50 / p95 / worst against the section-10 targets:

  * Dashboard first load  (compute_readiness)      p95 < 1000 ms
  * Dashboard refresh     (topic_mastery)          p95 <  500 ms
  * Knowledge graph       (topic_graph)            p95 <  500 ms
  * Points-at-stake queue (points_at_stake_order)  p95 <  500 ms
  * Next card after grading (getCard + answerCard) p95 <  100 ms

Run: `make bench`  (or  ../anki/out/pyenv/bin/python make_bench.py [n_cards])
Outputs data/eval/bench.json. Deterministic; re-runs reuse the cached deck.
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

from common import DATA, add_anki_to_path, load_outline

BENCH = DATA / "bench"
OUT = DATA / "eval"
N_CARDS = int(sys.argv[1]) if len(sys.argv) > 1 else 50_000
FRAC_WITH_STATE = 0.7   # fraction of cards given an FSRS memory state
MEASURE_RUNS = 25

# section-10 p95 targets (ms)
TARGETS = {
    "dashboard_first_load_compute_readiness": 1000,
    "dashboard_refresh_topic_mastery": 500,
    "knowledge_graph_topic_graph": 500,
    "points_at_stake_order": 500,
    "next_card_after_grading": 100,
}


def build_or_load(n_cards: int):
    add_anki_to_path()
    from anki.collection import Collection

    BENCH.mkdir(parents=True, exist_ok=True)
    path = BENCH / f"bench_{n_cards}.anki2"
    marker = BENCH / f"bench_{n_cards}.ready"
    if path.exists() and marker.exists():
        print(f"[bench] reusing cached deck {path}")
        return Collection(str(path))

    if path.exists():
        path.unlink()
    print(f"[bench] building {n_cards}-card deck (one-time)...")
    col = Collection(str(path))
    col.set_config("fsrs", True)
    outline = load_outline()
    topics = [t["id"] for s in outline["sections"].values() for t in s["topics"]]
    g = random.Random(7)
    deck_id = col.decks.id("MCAT::Bench")

    t0 = time.perf_counter()
    for i in range(n_cards):
        note = col.newNote()
        note["Front"] = f"Bench question {i} about {topics[i % len(topics)].split('::')[-1]}"
        note["Back"] = f"Answer {i}"
        note.tags = [topics[i % len(topics)]]
        col.add_note(note, deck_id)
        if (i + 1) % 10000 == 0:
            print(f"[bench]   added {i + 1}/{n_cards} ({time.perf_counter()-t0:.0f}s)")
    print(f"[bench] notes added in {time.perf_counter()-t0:.1f}s; assigning memory states...")

    # give a fraction of cards an FSRS memory state (batched updates for speed)
    from anki.cards import FSRSMemoryState
    from anki.consts import CARD_TYPE_REV
    t1 = time.perf_counter()
    cids = col.find_cards("deck:MCAT::Bench")
    now = int(time.time())
    batch = []
    for cid in cids:
        if g.random() > FRAC_WITH_STATE:
            continue
        card = col.get_card(cid)
        card.memory_state = FSRSMemoryState(stability=g.uniform(5, 400), difficulty=g.uniform(3, 8))
        card.reps = g.randint(1, 12)
        card.type = CARD_TYPE_REV
        card.last_review_time = now - g.randint(1, 60) * 86400
        batch.append(card)
        if len(batch) >= 2000:
            col.update_cards(batch)
            batch = []
    if batch:
        col.update_cards(batch)
    print(f"[bench] memory states set in {time.perf_counter()-t1:.1f}s")
    marker.write_text("ok")
    return col


def sections_input(outline: dict):
    from anki import stats_pb2
    secs = []
    for sec, body in outline["sections"].items():
        secs.append(stats_pb2.ReadinessSectionInput(
            section=sec, topic_prefix=f"mcat::{sec.lower()}",
            topic_weights={t["id"]: t["weight"] for t in body["topics"]},
            performance=0.6, theta_se=0.3, alpha_space=1.0, alpha_inter=1.3, alpha_test=1.5,
        ))
    return secs


def graph_input():
    from anki import stats_pb2
    g = json.loads((DATA / "knowledge_graph.json").read_text())
    nodes = [stats_pb2.TopicGraphNode(id=n["id"], section=n["section"],
                                      label=n["label"], weight=n["weight"]) for n in g["nodes"]]
    edges = [stats_pb2.TopicGraphEdge(**{"from": e["from"], "to": e["to"]})
             for e in g["edges"] if e["type"] == "prereq"]
    return nodes, edges


def pct(sorted_ms, q):
    if not sorted_ms:
        return 0.0
    i = min(len(sorted_ms) - 1, int(q * (len(sorted_ms) - 1) + 0.5))
    return round(sorted_ms[i], 1)


def time_action(fn, runs=MEASURE_RUNS):
    fn()  # warm up
    samples = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t) * 1000.0)
    samples.sort()
    return {"p50": pct(samples, 0.5), "p95": pct(samples, 0.95),
            "worst": round(samples[-1], 1), "runs": runs}


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    col = build_or_load(N_CARDS)
    from anki import stats_pb2  # noqa: F401
    outline = load_outline()
    secs = sections_input(outline)
    params = stats_pb2.ReadinessParams(b0=-1.0, b_m=1.3, b_p=2.2, b_c=0.5,
                                       min_graded_reviews=200, min_coverage=0.5, max_irt_se=0.5)
    nodes, edges = graph_input()
    weights = {t["id"]: t["weight"] for s in outline["sections"].values() for t in s["topics"]}

    n_total = len(col.find_cards("deck:MCAT::Bench"))
    results = {}

    results["dashboard_first_load_compute_readiness"] = time_action(
        lambda: col._backend.compute_readiness(search="", mastered_threshold=0.7,
                                                sections=secs, params=params))
    results["dashboard_refresh_topic_mastery"] = time_action(
        lambda: col._backend.topic_mastery(search="", topic_prefix="mcat", mastered_threshold=0.7))
    results["knowledge_graph_topic_graph"] = time_action(
        lambda: col._backend.topic_graph(search="", topic_prefix="mcat", mastered_threshold=0.7,
                                          mastery_threshold=0.7, nodes=nodes, prereq_edges=edges))
    results["points_at_stake_order"] = time_action(
        lambda: col._backend.points_at_stake_order(search="", topic_weights=weights,
                                                    mastered_threshold=0.7))

    # review-loop step: getCard + answerCard. Put a clean batch of cards back in
    # the new queue and lift today's limit so the queue is genuinely served.
    bench_did = col.decks.id("MCAT::Bench")
    col.decks.set_current(bench_did)
    conf = col.decks.config_dict_for_deck_id(bench_did)
    conf["new"]["perDay"] = 99999
    conf["rev"]["perDay"] = 99999
    col.decks.update_config(conf)
    review_ids = list(col.find_cards("deck:MCAT::Bench"))[:400]
    col.sched.schedule_cards_as_new(review_ids, reset_counts=True)
    col.sched.extend_limits(1000, 1000)
    served = col.sched.counts()
    print(f"[bench] review queue counts before timing: {served}")

    def review_step():
        c = col.sched.getCard()
        if c is not None:
            col.sched.answerCard(c, 3)
        return c
    # sanity: make sure cards are actually being served, else the metric is a no-op
    if col.sched.getCard() is None:
        print("[bench] WARNING: no cards served for review-step; metric skipped")
        results["next_card_after_grading"] = {"p50": None, "p95": None, "worst": None,
                                              "runs": 0, "note": "no due cards"}
    else:
        results["next_card_after_grading"] = time_action(review_step, runs=200)

    report = {"n_cards": n_total, "frac_with_memory_state": FRAC_WITH_STATE,
              "targets_p95_ms": TARGETS, "actions": {}}
    all_pass = True
    for name, r in results.items():
        target = TARGETS[name]
        ok = None if r.get("p95") is None else (r["p95"] <= target)
        if ok is False:
            all_pass = False
        report["actions"][name] = {**r, "target_p95_ms": target, "pass": ok}

    report["all_within_targets"] = all_pass
    (OUT / "bench.json").write_text(json.dumps(report, indent=2))
    col.close()

    print(f"\n[bench] {n_total} cards")
    print(f"{'action':42} {'p50':>8} {'p95':>8} {'worst':>8} {'target':>8}  pass")
    for name, r in report["actions"].items():
        print(f"{name:42} {str(r['p50']):>8} {str(r['p95']):>8} {str(r['worst']):>8} "
              f"{r['target_p95_ms']:>8}  {r['pass']}")
    print(f"[bench] all within section-10 targets: {all_pass}")
    return report


if __name__ == "__main__":
    run()
