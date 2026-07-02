"""Generate reproducible synthetic data for the readiness evaluation harness.

We do NOT have real student study + full-length-score longitudinal data (Speedrun
sec. 9 calls this out as a bonus). So we grade the *steps of the bridge* on
honestly-simulated data with known ground truth:

  - reviews.csv      : FSRS-style review outcomes with a known forgetting process,
                       so memory-model calibration (ECE/Brier/log loss) is measurable.
  - questions.json   : a per-topic question bank with 3PL IRT item params.
  - responses.csv    : simulated student answers to those questions (for theta/P_s).
  - paraphrase.json  : 30 cards x 2 reworded questions, where transfer is harder
                       than recall -> a measurable M - P gap (Speedrun 7d).

Everything is seeded. Temporal fields are emitted so downstream code can do
strict temporal train/test splits (no leakage).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from common import DATA, all_topics, load_outline, rng

SIM = DATA / "sim"
FSRS_DECAY = 0.2  # FSRS-6 w20 default; R(t) = (1 + f * t/S) ** -decay


def retrievability(t_days: np.ndarray, stability: np.ndarray, decay: float = FSRS_DECAY) -> np.ndarray:
    """FSRS-6 power-law forgetting curve. R(S, S) == 0.9 by construction."""
    factor = 0.9 ** (-1.0 / decay) - 1.0
    return (1.0 + factor * (t_days / stability)) ** (-decay)


def simulate_reviews(outline: dict, g: np.random.Generator) -> list[dict]:
    """Each topic gets a number of cards; each card gets several spaced reviews.

    The TRUE recall prob follows the FSRS curve at the card's stability. The
    memory model's *prediction* is the same curve evaluated at an estimated
    stability that carries mild noise -> realistic, measurable (mis)calibration.
    Coverage deliberately varies by section so the give-up rule has something to trip on.
    """
    rows: list[dict] = []
    # cards-per-topic multiplier per section -> CARS & PS intentionally sparse
    section_density = {"BB": 60, "CP": 55, "PS": 22, "CARS": 12}
    cid = 0
    t0 = 1_700_000_000  # fixed epoch for reproducible timestamps
    for topic in all_topics(outline):
        sec = topic["section"]
        n_cards = section_density[sec]
        for _ in range(n_cards):
            cid += 1
            stability = float(np.clip(g.lognormal(mean=2.3, sigma=0.7), 1.0, 400.0))
            est_stability = stability * float(np.exp(g.normal(0, 0.18)))  # model's noisy estimate
            n_reviews = int(g.integers(1, 9))
            elapsed = 0.0
            for r in range(n_reviews):
                gap = float(np.clip(g.lognormal(mean=1.4, sigma=0.6), 0.2, 120.0))
                elapsed += gap
                p_true = float(retrievability(np.array([elapsed]), np.array([stability]))[0])
                p_pred = float(retrievability(np.array([elapsed]), np.array([est_stability]))[0])
                outcome = int(g.random() < p_true)
                rows.append({
                    "card_id": cid,
                    "topic": topic["id"],
                    "section": sec,
                    "review_index": r,
                    "t_days": round(elapsed, 3),
                    "stability": round(stability, 3),
                    "model_pred": round(p_pred, 5),
                    "outcome": outcome,
                    "ts": t0 + int(elapsed * 86400) + cid,  # for temporal split
                })
                # successful review grows stability (desirable-difficulty flavor)
                if outcome:
                    stability *= 1.0 + 0.9 * (1.0 - p_true)
                    est_stability *= 1.0 + 0.9 * (1.0 - p_pred)
                else:
                    stability = max(1.0, stability * 0.6)
                    est_stability = max(1.0, est_stability * 0.6)
                elapsed = 0.0
    return rows


def simulate_question_bank(outline: dict, g: np.random.Generator):
    """3PL IRT bank + simulated responses from students with per-section ability.

    Returns (questions, responses, students). Transfer (passage) questions are
    deliberately harder than the raw fact, so recall > performance.
    """
    questions = []
    qid = 0
    for topic in all_topics(outline):
        for _ in range(g.integers(10, 22)):
            qid += 1
            questions.append({
                "id": f"q{qid}",
                "topic": topic["id"],
                "section": topic["section"],
                "a": round(float(np.clip(g.normal(1.1, 0.35), 0.3, 2.5)), 3),   # discrimination
                "b": round(float(g.normal(0.0, 1.0)), 3),                        # difficulty
                "c": 0.25,                                                        # 4-choice guess
                "stem": f"Passage-style item on {topic['label']} (#{qid}).",
            })

    n_students = 40
    students = []
    for s in range(n_students):
        # one ability per section; CARS independent of the science sections
        theta = {sec: round(float(g.normal(0.0, 1.0)), 3) for sec in outline["sections"].keys()}
        students.append({"id": f"s{s}", "theta": theta})

    def p_correct(theta, q):
        return q["c"] + (1 - q["c"]) / (1 + np.exp(-q["a"] * (theta - q["b"])))

    responses = []
    t0 = 1_700_500_000
    for st in students:
        for q in questions:
            th = st["theta"][q["section"]]
            p = float(p_correct(th, q))
            responses.append({
                "student_id": st["id"],
                "question_id": q["id"],
                "section": q["section"],
                "topic": q["topic"],
                "p_true": round(p, 5),
                "correct": int(g.random() < p),
                "ts": t0 + g.integers(0, 90 * 86400),
            })
    return questions, responses, students


def simulate_paraphrase(outline: dict, g: np.random.Generator):
    """30 cards, each with: recall outcome (card front->back) and 2 reworded
    exam-style questions. Transfer success < recall success (transfer-appropriate
    processing; Pan & Rickard 2018 d 0.40 -> 0.28 when reworded)."""
    topics = all_topics(outline)
    pairs = []
    for i in range(30):
        topic = topics[int(g.integers(0, len(topics)))]
        recall_p = float(np.clip(g.normal(0.85, 0.1), 0.4, 0.99))
        transfer_p = float(np.clip(recall_p - abs(g.normal(0.22, 0.08)), 0.05, recall_p))
        pairs.append({
            "card_id": f"pc{i}",
            "topic": topic["id"],
            "section": topic["section"],
            "recall_correct": int(g.random() < recall_p),
            "paraphrase": [int(g.random() < transfer_p), int(g.random() < transfer_p)],
            "recall_p": round(recall_p, 3),
            "transfer_p": round(transfer_p, 3),
        })
    return pairs


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    SIM.mkdir(parents=True, exist_ok=True)
    outline = load_outline()
    g = rng(7)

    reviews = simulate_reviews(outline, g)
    write_csv(SIM / "reviews.csv", reviews)

    questions, responses, students = simulate_question_bank(outline, g)
    with open(SIM / "questions.json", "w") as f:
        json.dump(questions, f, indent=2)
    write_csv(SIM / "responses.csv", responses)
    with open(SIM / "students.json", "w") as f:
        json.dump(students, f, indent=2)

    pairs = simulate_paraphrase(outline, g)
    with open(SIM / "paraphrase.json", "w") as f:
        json.dump(pairs, f, indent=2)

    print(f"reviews:   {len(reviews)} rows -> {SIM/'reviews.csv'}")
    print(f"questions: {len(questions)} items -> {SIM/'questions.json'}")
    print(f"responses: {len(responses)} rows -> {SIM/'responses.csv'}")
    print(f"paraphrase:{len(pairs)} cards -> {SIM/'paraphrase.json'}")


if __name__ == "__main__":
    main()
