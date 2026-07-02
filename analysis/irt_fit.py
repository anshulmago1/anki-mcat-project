"""IRT performance model (Speedrun sec. 9 step 2).

3PL: P(correct | theta, a, b, c) = c + (1 - c) / (1 + e^-a(theta - b)).

We estimate each student's per-section ability theta by MLE from their answered
questions, then predict correctness on held-out questions. Item params (a, b, c)
and fitted thetas are exported to data/fitted_params.json for the Rust readiness
inference to consume. CARS uses a theta independent of the science sections.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from common import DATA

SIM = DATA / "sim"
OUT = DATA


def load_questions() -> dict[str, dict]:
    with open(SIM / "questions.json") as f:
        return {q["id"]: q for q in json.load(f)}


def load_responses() -> list[dict]:
    with open(SIM / "responses.csv") as f:
        return list(csv.DictReader(f))


def p_correct(theta: float, q: dict) -> float:
    return q["c"] + (1 - q["c"]) / (1 + np.exp(-q["a"] * (theta - q["b"])))


def estimate_theta(items: list[tuple[dict, int]]) -> tuple[float, float]:
    """MLE theta over a grid + Fisher-information SE. items: [(question, correct)]."""
    grid = np.linspace(-4, 4, 161)
    loglik = np.zeros_like(grid)
    for q, y in items:
        p = np.clip(p_correct_vec(grid, q), 1e-6, 1 - 1e-6)
        loglik += y * np.log(p) + (1 - y) * np.log(1 - p)
    theta = float(grid[int(np.argmax(loglik))])
    info = 0.0
    for q, _ in items:
        p = float(np.clip(p_correct(theta, q), 1e-6, 1 - 1e-6))
        # 3PL Fisher information for one item
        info += (q["a"] ** 2) * ((p - q["c"]) ** 2 / (1 - q["c"]) ** 2) * ((1 - p) / p)
    se = float(1.0 / np.sqrt(info)) if info > 0 else float("inf")
    return theta, se


def p_correct_vec(theta: np.ndarray, q: dict) -> np.ndarray:
    return q["c"] + (1 - q["c"]) / (1 + np.exp(-q["a"] * (theta - q["b"])))


def temporal_split(rows: list[dict], frac: float = 0.6):
    rows = sorted(rows, key=lambda r: int(r["ts"]))
    cut = int(len(rows) * frac)
    return rows[:cut], rows[cut:]


def fit() -> dict:
    questions = load_questions()
    responses = load_responses()
    train, _ = temporal_split(responses)

    # group training responses by (student, section)
    by_ss: dict[tuple[str, str], list[tuple[dict, int]]] = defaultdict(list)
    for r in train:
        q = questions[r["question_id"]]
        by_ss[(r["student_id"], r["section"])].append((q, int(r["correct"])))

    thetas: dict[str, dict[str, dict]] = defaultdict(dict)
    for (student, section), items in by_ss.items():
        if len(items) < 5:
            continue
        theta, se = estimate_theta(items)
        thetas[student][section] = {"theta": round(theta, 4), "se": round(se, 4), "n": len(items)}

    params = {
        "items": {qid: {"a": q["a"], "b": q["b"], "c": q["c"], "section": q["section"],
                        "topic": q["topic"]} for qid, q in questions.items()},
        "student_theta": thetas,
        # readiness mapping coefficients filled in by score_map.py
        "readiness_coeffs": None,
    }
    with open(OUT / "fitted_params.json", "w") as f:
        json.dump(params, f, indent=2)
    print(f"[irt_fit] fitted theta for {len(thetas)} students x sections "
          f"from {len(train)} training responses -> data/fitted_params.json")
    return params


if __name__ == "__main__":
    fit()
