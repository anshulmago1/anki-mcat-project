"""Does the knowledge-graph recommender beat structure-blind baselines? (Speedrun
sec. 8 "prove your feature beats a baseline", applied to the cue-diagnostics graph.)

Premise (learning science): learning is scaffolded - studying a concept whose
prerequisites are shaky yields little durable gain (knowledge-space / ALEKS-style
prerequisite structure; transfer requires prior schema). We encode that in a
*pre-registered generative model* and then compare three "what to study next"
recommenders on identical simulated learners:

  * GRAPH  (ours): only recommends topics whose prerequisites are mastered
    (learning_ready gate), choosing the highest points-at-stake among them -
    exactly the TopicGraph RPC's recommended-path rule.
  * KEYWORD (baseline A): recommends the highest points-at-stake topic overall,
    ignoring prerequisite structure (a weight/forgetting heuristic).
  * VECTOR  (baseline B): recommends the topic most similar (same section +
    related-edge adjacency, a stand-in for embedding similarity) to what the
    learner has already touched - also structure-blind.

Metric: projected MCAT total (472-528) from weighted topic mastery after a fixed
study budget, plus "wasted steps" (studying a topic with unmet prerequisites).
Hypothesis (pre-registered): GRAPH > both baselines on exam score AND has fewer
wasted steps. Reported with 95% CIs over many simulated learners.

Honesty: this is a simulation of a mechanism we can defend from the literature,
not a live learner study; it shows the *recommender* exploits prerequisite
structure the baselines cannot. Reproduce with `python graph_eval.py`.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from common import DATA, load_outline

GRAPH = DATA / "knowledge_graph.json"
OUT = DATA / "eval"

MASTERED = 0.7          # a topic counts as "mastered" at this mastery level
BASE_GAIN = 0.45        # learning rate per focused study step
UNPREPARED_FLOOR = 0.2  # efficiency when prerequisites are entirely unmet
N_LEARNERS = 300
STEPS = 45              # study budget (< #topics * a couple of passes)


def load_graph():
    g = json.loads(GRAPH.read_text())
    nodes = {n["id"]: n for n in g["nodes"]}
    prereqs = defaultdict(list)
    for e in g["edges"]:
        if e["type"] == "prereq":
            prereqs[e["to"]].append(e["from"])
    related = defaultdict(set)
    for e in g["edges"]:
        if e["type"] == "related":
            related[e["from"]].add(e["to"])
            related[e["to"]].add(e["from"])
    return nodes, prereqs, related


def section_weights(outline):
    return {s: b["section_weight"] for s, b in outline["sections"].items()}


def prereq_readiness(topic, prereqs, mastery):
    reqs = prereqs.get(topic, [])
    if not reqs:
        return 1.0
    return float(np.mean([1.0 if mastery[r] >= MASTERED else 0.0 for r in reqs]))


def exam_score(nodes, outline, sec_w, mastery):
    """Weighted mastery -> 472..528, matching the readiness scale."""
    per_sec = defaultdict(lambda: [0.0, 0.0])  # section -> [sum w*mastery, sum w]
    for nid, n in nodes.items():
        per_sec[n["section"]][0] += n["weight"] * mastery[nid]
        per_sec[n["section"]][1] += n["weight"]
    total = 0.0
    for s, (num, den) in per_sec.items():
        sec_mastery = num / den if den else 0.0
        total += sec_w.get(s, 0.0) * sec_mastery
    # sec_w sums to ~1 across the 4 sections; map [0,1] -> [472,528]
    return 472.0 + 56.0 * total


# --- recommenders: each returns the next topic id, or None if all mastered ---
def rec_graph(nodes, prereqs, related, mastery, touched):
    ready = [nid for nid in nodes
             if mastery[nid] < MASTERED and prereq_readiness(nid, prereqs, mastery) >= 1.0]
    if not ready:
        ready = [nid for nid in nodes if mastery[nid] < MASTERED]
    if not ready:
        return None
    # highest points-at-stake = weight * (1 - mastery)
    return max(ready, key=lambda nid: nodes[nid]["weight"] * (1 - mastery[nid]))


def rec_keyword(nodes, prereqs, related, mastery, touched):
    cand = [nid for nid in nodes if mastery[nid] < MASTERED]
    if not cand:
        return None
    # structure-blind: pure points-at-stake, ignores prerequisites
    return max(cand, key=lambda nid: nodes[nid]["weight"] * (1 - mastery[nid]))


def rec_vector(nodes, prereqs, related, mastery, touched):
    cand = [nid for nid in nodes if mastery[nid] < MASTERED]
    if not cand:
        return None
    if not touched:
        # cold start: most-connected / highest-weight, still structure-blind
        return max(cand, key=lambda nid: nodes[nid]["weight"])

    def sim(nid):
        # similarity to already-touched topics: related-edge overlap + same section
        s = 0.0
        for t in touched:
            if t == nid:
                continue
            if nid in related.get(t, set()):
                s += 1.0
            if nodes[nid]["section"] == nodes[t]["section"]:
                s += 0.25
        return s

    return max(cand, key=lambda nid: (sim(nid), nodes[nid]["weight"]))


def simulate(recommender, nodes, prereqs, related, outline, sec_w, seed):
    rng = np.random.default_rng(seed)
    mastery = {nid: 0.0 for nid in nodes}
    # small heterogeneous starting knowledge so learners differ
    for nid in nodes:
        mastery[nid] = float(rng.uniform(0.0, 0.15))
    touched: list[str] = []
    wasted = 0
    for _ in range(STEPS):
        pick = recommender(nodes, prereqs, related, mastery, touched)
        if pick is None:
            break
        ready = prereq_readiness(pick, prereqs, mastery)
        if prereqs.get(pick) and ready < 1.0:
            wasted += 1
        eff = UNPREPARED_FLOOR + (1 - UNPREPARED_FLOOR) * ready
        gain = BASE_GAIN * eff * (1 - mastery[pick])  # diminishing returns
        mastery[pick] = min(1.0, mastery[pick] + gain)
        if pick not in touched:
            touched.append(pick)
    return exam_score(nodes, outline, sec_w, mastery), wasted


def ci95(x):
    x = np.asarray(x, dtype=float)
    m = float(x.mean())
    half = float(1.96 * x.std(ddof=1) / np.sqrt(len(x)))
    return m, [round(m - half, 2), round(m + half, 2)]


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    outline = load_outline()
    sec_w = section_weights(outline)
    nodes, prereqs, related = load_graph()

    recs = {"graph": rec_graph, "keyword": rec_keyword, "vector": rec_vector}
    scores = {k: [] for k in recs}
    wasted = {k: [] for k in recs}
    for i in range(N_LEARNERS):
        for k, fn in recs.items():
            sc, w = simulate(fn, nodes, prereqs, related, outline, sec_w, seed=1000 + i)
            scores[k].append(sc)
            wasted[k].append(w)

    summary = {}
    for k in recs:
        m, ci = ci95(scores[k])
        summary[k] = {"exam_mean": round(m, 2), "exam_ci95": ci,
                      "wasted_mean": round(float(np.mean(wasted[k])), 2)}

    g = np.array(scores["graph"])
    beats = {}
    for base in ("keyword", "vector"):
        diff = g - np.array(scores[base])
        m, ci = ci95(diff)
        beats[base] = {"delta_points": round(m, 2), "delta_ci95": ci,
                       "significant": bool(ci[0] > 0)}

    result = {
        "preregistered_hypothesis": ("graph recommender > keyword & vector on projected MCAT "
                                     "AND fewer wasted (prereq-violating) steps"),
        "n_learners": N_LEARNERS, "study_steps": STEPS,
        "generative_model": {"mastered_at": MASTERED, "base_gain": BASE_GAIN,
                             "unprepared_efficiency_floor": UNPREPARED_FLOOR,
                             "note": "gain scales with fraction of prerequisites mastered"},
        "by_recommender": summary,
        "graph_minus_baselines": beats,
        "beats_baselines": bool(beats["keyword"]["significant"] and beats["vector"]["significant"]
                                and summary["graph"]["wasted_mean"] < summary["keyword"]["wasted_mean"]
                                and summary["graph"]["wasted_mean"] < summary["vector"]["wasted_mean"]),
    }
    with open(OUT / "graph_eval.json", "w") as f:
        json.dump(result, f, indent=2)

    print(f"[graph_eval] exam: graph={summary['graph']['exam_mean']} "
          f"keyword={summary['keyword']['exam_mean']} vector={summary['vector']['exam_mean']} "
          f"| graph-keyword={beats['keyword']['delta_points']} {beats['keyword']['delta_ci95']} "
          f"graph-vector={beats['vector']['delta_points']} {beats['vector']['delta_ci95']} "
          f"| wasted g={summary['graph']['wasted_mean']} k={summary['keyword']['wasted_mean']} "
          f"v={summary['vector']['wasted_mean']} | beats_baselines={result['beats_baselines']}")
    return result


if __name__ == "__main__":
    run()
