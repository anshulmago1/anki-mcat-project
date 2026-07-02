"""Performance-model evaluation on held-out questions (Speedrun sec. 9 step 2,
grade 20%). Must beat two simpler baselines (Speedrun: keyword + vector search).

  - Model:     IRT theta_s (fit on earlier responses) -> P(correct) on held-out Qs.
  - Baseline A (keyword): predict correct iff the topic's mean review
                          retrievability > 0.7 (a memory-only proxy).
  - Baseline B (vector):  predict the topic's historical correct-rate
                          (nearest-neighbour-by-topic similarity proxy).

Metrics: accuracy, AUC-ROC, Brier, wrong-answer rate. Strict temporal split.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from common import DATA
from irt_fit import (estimate_theta, load_questions, load_responses, p_correct,
                     temporal_split)

SIM = DATA / "sim"
OUT = DATA / "eval"


def auc_roc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Mann-Whitney U formulation; no sklearn dependency."""
    order = np.argsort(scores)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    # average ranks for ties
    _, inv, counts = np.unique(scores, return_inverse=True, return_counts=True)
    cum = np.cumsum(counts)
    avg = {}
    start = 0
    for i, c in enumerate(counts):
        avg[i] = (start + 1 + start + c) / 2.0
        start += c
    ranks = np.array([avg[i] for i in inv])
    pos = labels == 1
    n_pos = int(pos.sum())
    n_neg = int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def metrics(pred: np.ndarray, labels: np.ndarray, thresh: float = 0.5) -> dict:
    hard = (pred >= thresh).astype(int)
    acc = float((hard == labels).mean())
    brier = float(np.mean((pred - labels) ** 2))
    auc = auc_roc(pred, labels)
    # wrong-answer rate among items the model predicted correct
    flagged = hard == 1
    wrong = float((labels[flagged] == 0).mean()) if flagged.any() else 0.0
    return {"accuracy": round(acc, 4), "auc": round(auc, 4), "brier": round(brier, 4),
            "wrong_answer_rate": round(wrong, 4)}


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    questions = load_questions()
    responses = load_responses()
    train, test = temporal_split(responses)

    # fit theta per (student, section) on train
    by_ss = defaultdict(list)
    for r in train:
        by_ss[(r["student_id"], r["section"])].append((questions[r["question_id"]], int(r["correct"])))
    theta = {}
    for key, items in by_ss.items():
        if len(items) >= 5:
            theta[key], _ = estimate_theta(items)

    # topic stats from reviews (for keyword baseline) + train correct-rates (vector baseline)
    topic_retr = _topic_mean_retrievability()
    topic_rate = defaultdict(list)
    for r in train:
        topic_rate[r["topic"]].append(int(r["correct"]))
    topic_rate = {t: float(np.mean(v)) for t, v in topic_rate.items()}
    global_rate = float(np.mean([int(r["correct"]) for r in train]))

    model_pred, base_a, base_b, labels = [], [], [], []
    for r in test:
        key = (r["student_id"], r["section"])
        if key not in theta:
            continue
        q = questions[r["question_id"]]
        model_pred.append(p_correct(theta[key], q))
        base_a.append(1.0 if topic_retr.get(r["topic"], 0.0) > 0.7 else 0.0)
        base_b.append(topic_rate.get(r["topic"], global_rate))
        labels.append(int(r["correct"]))

    labels = np.array(labels, dtype=float)
    model_pred = np.array(model_pred)
    result = {
        "n_test": int(len(labels)),
        "model_irt": metrics(model_pred, labels),
        "baseline_a_keyword": metrics(np.array(base_a), labels),
        "baseline_b_vector": metrics(np.array(base_b), labels),
    }
    result["beats_baselines"] = bool(
        result["model_irt"]["auc"] > result["baseline_a_keyword"]["auc"]
        and result["model_irt"]["auc"] > result["baseline_b_vector"]["auc"]
        and result["model_irt"]["brier"] < result["baseline_a_keyword"]["brier"]
        and result["model_irt"]["brier"] < result["baseline_b_vector"]["brier"]
    )
    with open(OUT / "performance.json", "w") as f:
        json.dump(result, f, indent=2)
    m = result["model_irt"]
    print(f"[perf_eval] IRT acc={m['accuracy']} auc={m['auc']} brier={m['brier']} "
          f"| beats_baselines={result['beats_baselines']}")
    return result


def _topic_mean_retrievability() -> dict[str, float]:
    agg = defaultdict(list)
    with open(SIM / "reviews.csv") as f:
        for r in csv.DictReader(f):
            agg[r["topic"]].append(float(r["model_pred"]))
    return {t: float(np.mean(v)) for t, v in agg.items()}


if __name__ == "__main__":
    run()
