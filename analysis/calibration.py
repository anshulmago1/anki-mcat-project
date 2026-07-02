"""Memory-model calibration (Speedrun sec. 9 step 1 + grade 20%).

When the model says 0.80, ~80% of held-out reviews at that level should succeed.
Metrics: ECE, Brier score with REL/RES/UNC decomposition, log loss, plus a
reliability diagram. We use a strict TEMPORAL split (train on earlier reviews,
test on later) and must beat a constant-p baseline.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from common import DATA

SIM = DATA / "sim"
OUT = DATA / "eval"


def load_reviews() -> list[dict]:
    with open(SIM / "reviews.csv") as f:
        return list(csv.DictReader(f))


def temporal_split(rows: list[dict], frac: float = 0.7):
    rows = sorted(rows, key=lambda r: int(r["ts"]))
    cut = int(len(rows) * frac)
    return rows[:cut], rows[cut:]


def ece(pred: np.ndarray, obs: np.ndarray, n_bins: int = 10) -> tuple[float, list[dict]]:
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(pred, bins) - 1, 0, n_bins - 1)
    total = len(pred)
    err = 0.0
    diagram = []
    for b in range(n_bins):
        mask = idx == b
        if not mask.any():
            continue
        conf = float(pred[mask].mean())
        acc = float(obs[mask].mean())
        w = int(mask.sum())
        err += (w / total) * abs(acc - conf)
        diagram.append({"bin": b, "lo": round(bins[b], 2), "hi": round(bins[b + 1], 2),
                        "count": w, "confidence": round(conf, 4), "accuracy": round(acc, 4)})
    return err, diagram


def brier_decomposition(pred: np.ndarray, obs: np.ndarray, n_bins: int = 10):
    """BS = REL - RES + UNC (Murphy 1973)."""
    bs = float(np.mean((pred - obs) ** 2))
    base = float(obs.mean())
    unc = base * (1 - base)
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(pred, bins) - 1, 0, n_bins - 1)
    n = len(pred)
    rel = 0.0
    res = 0.0
    for b in range(n_bins):
        mask = idx == b
        nk = int(mask.sum())
        if nk == 0:
            continue
        fk = float(pred[mask].mean())
        ok = float(obs[mask].mean())
        rel += nk * (fk - ok) ** 2
        res += nk * (ok - base) ** 2
    rel /= n
    res /= n
    return {"brier": bs, "reliability": rel, "resolution": res, "uncertainty": unc,
            "identity_check": round(rel - res + unc, 6)}


def log_loss(pred: np.ndarray, obs: np.ndarray) -> float:
    eps = 1e-15
    p = np.clip(pred, eps, 1 - eps)
    return float(-np.mean(obs * np.log(p) + (1 - obs) * np.log(1 - p)))


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_reviews()
    _, test = temporal_split(rows)
    pred = np.array([float(r["model_pred"]) for r in test])
    obs = np.array([int(r["outcome"]) for r in test], dtype=float)

    e, diagram = ece(pred, obs)
    decomp = brier_decomposition(pred, obs)
    ll = log_loss(pred, obs)

    # Baseline: predict the overall recall rate for every review.
    base_p = float(obs.mean())
    base_pred = np.full_like(pred, base_p)
    base = {"brier": float(np.mean((base_pred - obs) ** 2)), "log_loss": log_loss(base_pred, obs)}

    result = {
        "n_test_reviews": len(test),
        "model": {"ece": round(e, 4), **{k: round(v, 4) for k, v in decomp.items()},
                  "log_loss": round(ll, 4)},
        "baseline_constant_p": {"p": round(base_p, 4), "brier": round(base["brier"], 4),
                                 "log_loss": round(base["log_loss"], 4)},
        "beats_baseline": bool(decomp["brier"] < base["brier"] and ll < base["log_loss"]),
        "reliability_diagram": diagram,
    }
    with open(OUT / "calibration.json", "w") as f:
        json.dump(result, f, indent=2)
    _write_reliability_chart(diagram)
    print(f"[calibration] ECE={e:.4f} Brier={decomp['brier']:.4f} "
          f"(REL={decomp['reliability']:.4f} RES={decomp['resolution']:.4f} "
          f"UNC={decomp['uncertainty']:.4f}) logloss={ll:.4f} "
          f"beats_baseline={result['beats_baseline']}")
    return result


def _write_reliability_chart(diagram: list[dict]) -> None:
    """ASCII reliability diagram so the harness needs no plotting deps to pass.
    (matplotlib PNG is emitted by report.py when available.)"""
    lines = ["Reliability diagram (predicted vs actual recall)", "pred | actual | n"]
    for d in diagram:
        bar = "#" * int(round(d["accuracy"] * 40))
        lines.append(f"{d['confidence']:.2f} | {d['accuracy']:.2f} | {d['count']:>4} {bar}")
    (OUT / "reliability_diagram.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    run()
