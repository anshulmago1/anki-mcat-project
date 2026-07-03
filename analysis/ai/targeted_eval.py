"""Does graph-guided TARGETING of AI card generation beat structure-blind
targeting? (Speedrun sec. 8 "beat a baseline", applied to the AI x graph feature.)

The generator quality is held constant; the only thing that varies is WHICH topics
we spend a fixed generation budget on. We compare, over many simulated learner
mastery snapshots, four strategies for picking B topics to generate cards for:

  * GRAPH  (ours): learning_ready (prerequisites mastered) AND not mastered, top
    points-at-stake = weight x (1 - mastery). Exactly the TopicGraph selection.
  * RANDOM : B random unmastered topics.
  * WEIGHT : highest AAMC weight, ignoring mastery/readiness (a keyword-style rule).
  * DUE    : most-forgotten (highest 1 - mastery), what plain Anki surfaces.

Metric: at-risk-ready exam weight addressed = sum over chosen topics of
`weight x (1 - mastery)`, counted ONLY when the topic is learning_ready (studying
a topic whose prerequisites are shaky yields ~no durable gain - the same
scaffolding premise as graph_eval). Also tracked: how many chosen topics were
prerequisite-BLOCKED (wasted generation budget).

Pre-registered hypothesis: GRAPH addresses more at-risk-ready exam weight per
budget than all three baselines AND never targets a blocked topic. Reported with
95% CIs. LLM-free and deterministic; reproduce with `python ai/targeted_eval.py`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # analysis/ for graph_eval + common

from graph_eval import MASTERED, ci95, load_graph, prereq_readiness  # noqa: E402
from common import DATA  # noqa: E402

OUT = DATA / "eval"
N_PROFILES = 400
BUDGET = 5  # topics we can afford to generate cards for


def strat_graph(nodes, prereqs, mastery, B):
    ready = [n for n in nodes
             if mastery[n] < MASTERED and prereq_readiness(n, prereqs, mastery) >= 1.0]
    ready.sort(key=lambda n: nodes[n]["weight"] * (1 - mastery[n]), reverse=True)
    return ready[:B]


def strat_random(nodes, prereqs, mastery, B, rng):
    cand = [n for n in nodes if mastery[n] < MASTERED]
    rng.shuffle(cand)
    return cand[:B]


def strat_weight(nodes, prereqs, mastery, B):
    return sorted(nodes, key=lambda n: nodes[n]["weight"], reverse=True)[:B]


def strat_due(nodes, prereqs, mastery, B):
    cand = [n for n in nodes if mastery[n] < MASTERED]
    cand.sort(key=lambda n: 1 - mastery[n], reverse=True)
    return cand[:B]


def value(chosen, nodes, prereqs, mastery):
    """at-risk-ready exam weight addressed; blocked picks score 0 (wasted budget)."""
    v, blocked = 0.0, 0
    for n in chosen:
        if prereq_readiness(n, prereqs, mastery) >= 1.0:
            v += nodes[n]["weight"] * (1 - mastery[n])
        else:
            blocked += 1
    return v, blocked


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    nodes, prereqs, _related = load_graph()
    node_ids = list(nodes.keys())

    scores = {k: [] for k in ("graph", "random", "weight", "due")}
    blocked = {k: [] for k in scores}
    for i in range(N_PROFILES):
        rng = np.random.default_rng(2000 + i)
        mastery = {n: float(rng.uniform(0.0, 1.0)) for n in node_ids}
        picks = {
            "graph": strat_graph(nodes, prereqs, mastery, BUDGET),
            "random": strat_random(nodes, prereqs, mastery, BUDGET, rng),
            "weight": strat_weight(nodes, prereqs, mastery, BUDGET),
            "due": strat_due(nodes, prereqs, mastery, BUDGET),
        }
        for k, chosen in picks.items():
            v, b = value(chosen, nodes, prereqs, mastery)
            scores[k].append(v)
            blocked[k].append(b)

    summary = {}
    for k in scores:
        m, ci = ci95(scores[k])
        summary[k] = {"value_mean": round(m, 3), "value_ci95": ci,
                      "blocked_mean": round(float(np.mean(blocked[k])), 3)}

    g = np.array(scores["graph"])
    beats = {}
    for base in ("random", "weight", "due"):
        diff = g - np.array(scores[base])
        m, ci = ci95(diff)
        beats[base] = {"delta": round(m, 3), "delta_ci95": ci, "significant": bool(ci[0] > 0)}

    result = {
        "preregistered_hypothesis": ("graph-guided targeting > random/weight/due on at-risk-ready "
                                     "exam weight addressed per budget AND never targets a blocked topic"),
        "n_profiles": N_PROFILES, "budget_topics": BUDGET,
        "metric": "sum over chosen topics of weight*(1-mastery), counted only when learning_ready",
        "by_strategy": summary,
        "graph_minus_baselines": beats,
        "beats_baselines": bool(all(beats[b]["significant"] for b in beats)
                                and summary["graph"]["blocked_mean"] == 0.0),
    }
    (OUT / "targeted_eval.json").write_text(json.dumps(result, indent=2))

    print(f"[targeted_eval] value: graph={summary['graph']['value_mean']} "
          f"random={summary['random']['value_mean']} weight={summary['weight']['value_mean']} "
          f"due={summary['due']['value_mean']} | blocked graph={summary['graph']['blocked_mean']} "
          f"weight={summary['weight']['blocked_mean']} due={summary['due']['blocked_mean']} "
          f"| beats_baselines={result['beats_baselines']}")
    return result


if __name__ == "__main__":
    run()
