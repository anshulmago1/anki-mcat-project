"""End-to-end readiness dashboard over a REAL Anki collection.

This is a THIN CLIENT: all inference (the three scores, multipliers, give-up rule)
runs inside the engine via the `compute_readiness` RPC we added to rslib. Python
only bundles the AAMC outline + offline-trained params and renders the result.

Usage: python dashboard.py [collection.anki2]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from common import DATA, add_anki_to_path, load_outline, section_topic_weights

MASTERED_THRESHOLD = 0.7
# Give-up thresholds (override to experiment, e.g. MIN_REVIEWS=10 MIN_COVERAGE=0.4).
MIN_REVIEWS = int(os.environ.get("MIN_REVIEWS", "200"))
MIN_COVERAGE = float(os.environ.get("MIN_COVERAGE", "0.5"))
# learning-science multipliers (each cited in the engine); on for the demo
ALPHA = {"space": 1.0, "inter": 1.3, "test": 1.5}


def performance_by_section() -> dict:
    """P_s + theta SE per section from the offline IRT model (data/eval/readiness.json)."""
    p = DATA / "eval" / "readiness.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    out = {}
    for sec, body in data["sections"].items():
        perf = body["performance"]
        out[sec] = {"p_s": perf["value"] if perf["value"] is not None else 0.0, "se": 0.35}
    return out


def coeffs() -> dict:
    fp = DATA / "fitted_params.json"
    if fp.exists():
        c = json.loads(fp.read_text()).get("readiness_coeffs")
        if c:
            return c
    return {"b0": -1.0, "bM": 1.3, "bP": 2.2, "bC": 0.5}


def build(col_path: Path) -> dict:
    add_anki_to_path()
    from anki.collection import Collection
    from anki import stats_pb2

    outline = load_outline()
    weights = section_topic_weights(outline)
    perf = performance_by_section()
    c = coeffs()

    sections_in = []
    for sec in outline["sections"].keys():
        p = perf.get(sec, {"p_s": 0.0, "se": 9.9})
        sections_in.append(stats_pb2.ReadinessSectionInput(
            section=sec,
            topic_prefix=f"mcat::{sec.lower()}",
            topic_weights=weights[sec],
            performance=p["p_s"],
            theta_se=p["se"],
            alpha_space=ALPHA["space"], alpha_inter=ALPHA["inter"], alpha_test=ALPHA["test"],
        ))
    params = stats_pb2.ReadinessParams(
        b0=c["b0"], b_m=c["bM"], b_p=c["bP"], b_c=c["bC"],
        min_graded_reviews=MIN_REVIEWS, min_coverage=MIN_COVERAGE, max_irt_se=0.5,
    )

    col = Collection(str(col_path))
    try:
        resp = col._backend.compute_readiness(
            search="", mastered_threshold=MASTERED_THRESHOLD,
            sections=sections_in, params=params,
        )
    finally:
        col.close()
    return resp


def render(resp) -> str:
    def ev(e):
        if e.abstained:
            return f"WITHHELD -> need {', '.join(e.missing)}"
        return f"{e.value:.2f} range [{e.range_lo:.2f}, {e.range_hi:.2f}]"

    L = ["", "=" * 66, "  MCAT READINESS DASHBOARD (computed inside the Anki engine)", "=" * 66]
    t = resp.total
    if t.abstained:
        L.append("  Projected MCAT: -- WITHHELD --")
        L.append(f"  Insufficient evidence in: {', '.join(t.missing)}")
    else:
        L.append(f"  Projected MCAT: {t.value:.0f}  (likely range {t.range_lo:.0f}-{t.range_hi:.0f})")
    L.append("-" * 66)
    for s in resp.sections:
        m, p, r = s.memory, s.performance, s.readiness
        L.append(f"\n  [{s.section}]  coverage {m.coverage_pct:.0f}%  ({m.graded_reviews} graded reviews)")
        L.append(f"    Memory      : {m.value:.2f} range [{m.range_lo:.2f}, {m.range_hi:.2f}]")
        L.append(f"    Performance : {p.value:.2f} range [{p.range_lo:.2f}, {p.range_hi:.2f}]")
        L.append(f"    Readiness   : {ev(r)}  (conf={r.confidence})")
        L.append(f"    Next best   : {s.next_best_topic}  (stake {s.next_best_points_at_stake:.3f})")
    L.append("\n" + "=" * 66)
    return "\n".join(L)


def main() -> None:
    col_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "demo" / "mcat_demo.anki2"
    if not col_path.exists():
        print(f"collection not found: {col_path}\nRun build_mcat_apkg.py or make_demo_collection.py first.")
        sys.exit(1)
    resp = build(col_path)
    print(render(resp))


if __name__ == "__main__":
    main()
