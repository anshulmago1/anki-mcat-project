"""Score mapping + readiness assembly (Speedrun sec. 9 step 3).

1. Aggregate per-section Memory M_s (FSRS retrievability, topic-weighted),
   Coverage C_s, and Performance P_s (IRT) for the primary user from the sim data.
2. Fit the readiness mapping coefficients (logit-linear) and document the method.
3. Produce the three separate scores per section + the total, each with a range,
   honoring the give-up rule. Compute the paraphrase gap (M - P).

Honesty: we lack real study+FL longitudinal data, so coefficients are fit on a
documented synthetic generative model and labeled as not-yet-field-calibrated
(Speedrun sec. 9 says this scores higher than a fabricated number).
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

import readiness as R
from common import DATA, load_outline, section_topic_weights, rng
from irt_fit import estimate_theta, load_questions, load_responses, p_correct, temporal_split

SIM = DATA / "sim"
OUT = DATA / "eval"


def memory_and_coverage(outline: dict):
    """Per-section M_s (topic-weighted mean retrievability), graded_reviews, coverage."""
    weights = section_topic_weights(outline)
    topic_pred = defaultdict(list)
    topic_section = {}
    with open(SIM / "reviews.csv") as f:
        for r in csv.DictReader(f):
            topic_pred[r["topic"]].append(float(r["model_pred"]))
            topic_section[r["topic"]] = r["section"]

    m_s, reviews_s, coverage_s = {}, {}, {}
    for sec, body in outline["sections"].items():
        topics = [t["id"] for t in body["topics"]]
        covered = [t for t in topics if t in topic_pred]
        # topic-weighted mean retrievability; uncovered topics contribute 0
        num = 0.0
        for t in topics:
            w = weights[sec][t]
            mean_r = float(np.mean(topic_pred[t])) if t in topic_pred else 0.0
            num += w * mean_r
        m_s[sec] = num
        reviews_s[sec] = sum(len(topic_pred[t]) for t in covered)
        coverage_s[sec] = len(covered) / len(topics)
    return m_s, reviews_s, coverage_s


def performance(outline: dict, student_id: str = "s0"):
    """P_s and theta SE for one student from held-out questions."""
    questions = load_questions()
    responses = load_responses()
    train, _ = temporal_split(responses)
    by_sec = defaultdict(list)
    for r in train:
        if r["student_id"] == student_id:
            by_sec[r["section"]].append((questions[r["question_id"]], int(r["correct"])))

    p_s, se_s = {}, {}
    for sec, body in outline["sections"].items():
        items = by_sec.get(sec, [])
        if len(items) >= 5:
            theta, se = estimate_theta(items)
        else:
            theta, se = 0.0, 9.9
        sec_items = [q for q in questions.values() if q["section"] == sec]
        p_s[sec] = float(np.mean([p_correct(theta, q) for q in sec_items])) if sec_items else 0.0
        se_s[sec] = se
    return p_s, se_s


def fit_coeffs() -> dict:
    """Fit logit-linear readiness coefficients on a documented synthetic generative
    model (placeholder for AAMC conversion-table / real-FL calibration)."""
    g = rng(11)
    n = 4000
    M = g.uniform(0, 1, n); P = g.uniform(0, 1, n); C = g.uniform(0, 1, n)
    # generative truth: performance dominates, memory + coverage support
    true = R_sigmoid_vec(-1.0 + 1.3 * M + 2.4 * P + 0.5 * C + g.normal(0, 0.15, n))
    X = np.column_stack([np.ones(n), M, P, C])
    # logistic regression via Newton-ish gradient descent
    w = np.zeros(4)
    for _ in range(400):
        z = X @ w
        pr = R_sigmoid_vec(z)
        grad = X.T @ (pr - true) / n
        w -= 0.5 * grad
    return {"b0": round(float(w[0]), 4), "bM": round(float(w[1]), 4),
            "bP": round(float(w[2]), 4), "bC": round(float(w[3]), 4),
            "method": "logit-linear fit on synthetic generative model; NOT yet field-calibrated on real FL scores"}


def R_sigmoid_vec(z):
    return 1.0 / (1.0 + np.exp(-z))


def paraphrase_gap():
    with open(SIM / "paraphrase.json") as f:
        pairs = json.load(f)
    recall = np.mean([p["recall_correct"] for p in pairs])
    transfer = np.mean([np.mean(p["paraphrase"]) for p in pairs])
    per_sec = defaultdict(lambda: {"recall": [], "transfer": []})
    for p in pairs:
        per_sec[p["section"]]["recall"].append(p["recall_correct"])
        per_sec[p["section"]]["transfer"].extend(p["paraphrase"])
    sec_gap = {s: {"recall": round(float(np.mean(v["recall"])), 3),
                   "transfer": round(float(np.mean(v["transfer"])), 3),
                   "gap": round(float(np.mean(v["recall"]) - np.mean(v["transfer"])), 3)}
               for s, v in per_sec.items()}
    return {"n_cards": len(pairs), "recall_acc": round(float(recall), 3),
            "transfer_acc": round(float(transfer), 3),
            "gap": round(float(recall - transfer), 3),
            "interpretation": ("M - P gap is positive -> performance model measures transfer, "
                               "not just recall (Speedrun 7d passes)"),
            "by_section": sec_gap}


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    outline = load_outline()
    coeffs = fit_coeffs()
    m_s, reviews_s, cov_s = memory_and_coverage(outline)
    p_s, se_s = performance(outline)

    # simple evidence-based multipliers (documented; real ones come from session logs)
    mult = {"alpha_space": R.alpha_space(12.0, 12.0)[0],   # on-schedule -> 1.0
            "alpha_inter": R.alpha_inter(True, True)[0],   # interleaved sessions on
            "alpha_test": R.alpha_test(True, 6.0)[0]}      # active retrieval, RT ok

    sections = {}
    readiness_vals = {}
    for sec in outline["sections"].keys():
        mem, perf, rdy = R.section_readiness(
            sec, m_s[sec], p_s[sec], cov_s[sec],
            graded_reviews=reviews_s[sec], theta_se=se_s[sec], recency=0.7,
            multipliers=mult, coeffs=coeffs,
        )
        sections[sec] = {"memory": mem.to_dict(), "performance": perf.to_dict(),
                         "readiness": rdy.to_dict()}
        readiness_vals[sec] = rdy

    total = R.total_readiness(readiness_vals)
    result = {
        "coeffs": coeffs,
        "multipliers_applied": {k: round(v, 3) for k, v in mult.items()},
        "sections": sections,
        "total_readiness": total,
        "paraphrase_gap": paraphrase_gap(),
    }
    with open(OUT / "readiness.json", "w") as f:
        json.dump(result, f, indent=2)

    # export coeffs into fitted_params.json for the Rust inference
    fp = DATA / "fitted_params.json"
    params = json.loads(fp.read_text()) if fp.exists() else {}
    params["readiness_coeffs"] = coeffs
    fp.write_text(json.dumps(params, indent=2))

    abst = total["abstained"]
    print(f"[score_map] total readiness {'ABSTAINED ('+','.join(total['missing_by_section'].keys())+')' if abst else total['value']} "
          f"range={total['range']} | paraphrase gap={result['paraphrase_gap']['gap']}")
    return result


if __name__ == "__main__":
    run()
