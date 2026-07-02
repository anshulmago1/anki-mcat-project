"""Readiness composite - Python reference implementation.

This mirrors the Rust inference that runs live in the app (rslib/src/stats/readiness.rs).
It produces the three SEPARATE scores (Memory, Performance, Readiness), each as an
EvidencedValue with a range, and enforces the give-up rule. No number is returned
without its evidence; if the gate fails, `abstained=True` and the caller shows what's
missing instead of a score.

Every learning-science multiplier carries its citation (Speedrun + Brainlift).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

# --- Give-up rule: coded named constants (Speedrun sec. 4 / formulaic_approach 3.2) ---
MIN_GRADED_REVIEWS = 200      # per section; IRT theta needs ~100-200 items
MIN_COVERAGE = 0.50           # >=50% of AAMC categories per section
MAX_IRT_SE = 0.50             # above this the 90% CI spans >14 scaled points
MIN_RECENCY = 0.50            # >=50% of due reviews done within 2x interval

SECTION_SPAN = 14.0           # 118..132
SECTION_MIN = 118.0

# Multiplier effect-size citations (rendered alongside any applied multiplier).
CITATIONS = {
    "alpha_space": "Cepeda et al. 2008: optimal spacing up to +150% recall vs massed (Dunlosky high-utility)",
    "alpha_inter": "Bjork lab: blocked 20% -> interleaved 63% transfer @1wk; Taylor & Rohrer 2010 ~2x math accuracy",
    "alpha_test": "Dunlosky et al. 2013: practice testing high-utility, d~0.55-0.60 over restudy",
    "memory": "FSRS-6 power-law retrievability (benchmark log loss ~0.345, AUC ~0.705)",
    "performance": "3PL IRT ability estimate on held-out exam-style questions",
    "score_map": "Linear/logistic map; community regression AAMC FL1+FL2 vs real MCAT r~0.86",
}


@dataclass
class EvidencedValue:
    value: float
    range: tuple[float, float]
    confidence: str            # low|moderate|high
    graded_reviews: int
    coverage_pct: float
    method: str
    drivers: list[str] = field(default_factory=list)
    calibration: dict | None = None
    abstained: bool = False
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["range"] = [round(self.range[0], 2), round(self.range[1], 2)]
        d["value"] = round(self.value, 2) if not self.abstained else None
        return d


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def alpha_space(actual_gap: float, optimal_gap: float) -> tuple[float, str]:
    if optimal_gap <= 0:
        return 1.0, CITATIONS["alpha_space"]
    ratio = actual_gap / optimal_gap - 1.0
    return 1.0 + 0.4 * max(-0.5, min(0.5, ratio)), CITATIONS["alpha_space"]


def alpha_inter(mixes_two_topics: bool, all_topics_known: bool) -> tuple[float, str]:
    # Bjork gate: desirable only with sufficient prior knowledge (all R_i > 0.4)
    on = mixes_two_topics and all_topics_known
    return (1.3 if on else 1.0), CITATIONS["alpha_inter"]


def alpha_test(active_retrieval: bool, median_rt_secs: float) -> tuple[float, str]:
    # anti-"tap Good without reading": disable below 2s median response
    on = active_retrieval and median_rt_secs >= 2.0
    return (1.5 if on else 1.0), CITATIONS["alpha_test"]


# Readiness coefficients (evidence-based defaults; refined by score_map.fit()).
DEFAULT_COEFFS = {"b0": -1.2, "bM": 1.4, "bP": 2.2, "bC": 0.6}


def section_readiness(
    section: str,
    m_s: float, p_s: float, c_s: float,
    graded_reviews: int, theta_se: float, recency: float,
    multipliers: dict[str, float] | None = None,
    coeffs: dict[str, float] | None = None,
) -> tuple[EvidencedValue, EvidencedValue, EvidencedValue]:
    """Return (memory, performance, readiness) EvidencedValues for one section."""
    coeffs = coeffs or DEFAULT_COEFFS
    mult = multipliers or {"alpha_space": 1.0, "alpha_inter": 1.0, "alpha_test": 1.0}
    mfac = mult["alpha_space"] * mult["alpha_inter"] * mult["alpha_test"]

    # confidence from evidence volume + coverage + IRT SE
    conf = _confidence(graded_reviews, c_s, theta_se)

    memory = EvidencedValue(
        value=m_s, range=_band(m_s, 0.05, conf), confidence=conf,
        graded_reviews=graded_reviews, coverage_pct=round(c_s * 100, 1),
        method=CITATIONS["memory"],
        drivers=[f"{section} mean retrievability {m_s:.2f} over {graded_reviews} reviews"],
    )
    performance = EvidencedValue(
        value=p_s, range=_band(p_s, max(0.03, theta_se * 0.1), conf), confidence=conf,
        graded_reviews=graded_reviews, coverage_pct=round(c_s * 100, 1),
        method=CITATIONS["performance"],
        drivers=[f"{section} IRT theta SE {theta_se:.2f}", f"paraphrase-aware P_s {p_s:.2f}"],
    )

    # --- give-up rule ---
    missing = []
    if graded_reviews < MIN_GRADED_REVIEWS:
        missing.append(f"{graded_reviews}/{MIN_GRADED_REVIEWS} graded reviews")
    if c_s < MIN_COVERAGE:
        missing.append(f"coverage {c_s*100:.0f}% < {int(MIN_COVERAGE*100)}%")
    if theta_se > MAX_IRT_SE:
        missing.append(f"IRT SE {theta_se:.2f} > {MAX_IRT_SE}")
    if recency < MIN_RECENCY:
        missing.append(f"recency {recency*100:.0f}% < {int(MIN_RECENCY*100)}%")

    lin = coeffs["b0"] + coeffs["bM"] * m_s * mfac + coeffs["bP"] * p_s + coeffs["bC"] * c_s
    e_s = SECTION_MIN + SECTION_SPAN * sigmoid(lin)
    # half-width grows with IRT SE and missing coverage
    hw = 1.0 + 6.0 * min(0.5, theta_se) + 4.0 * max(0.0, MIN_COVERAGE - c_s)
    drivers = [f"M={m_s:.2f}", f"P={p_s:.2f}", f"coverage={c_s*100:.0f}%"]
    for k, v in mult.items():
        if abs(v - 1.0) > 1e-9:
            drivers.append(f"{k}={v:.2f} ({CITATIONS[k].split(':')[0]})")

    lo = max(SECTION_MIN, e_s - hw)
    hi = min(SECTION_MIN + SECTION_SPAN, e_s + hw)
    readiness = EvidencedValue(
        value=e_s, range=(lo, hi), confidence=conf,
        graded_reviews=graded_reviews, coverage_pct=round(c_s * 100, 1),
        method=CITATIONS["score_map"], drivers=drivers,
        abstained=bool(missing), missing=missing,
    )
    return memory, performance, readiness


def _confidence(reviews: int, coverage: float, se: float) -> str:
    if reviews >= MIN_GRADED_REVIEWS and coverage >= 0.6 and se <= 0.4:
        return "high"
    if reviews >= MIN_GRADED_REVIEWS // 2 and coverage >= MIN_COVERAGE:
        return "moderate"
    return "low"


def _band(p: float, base_hw: float, conf: str) -> tuple[float, float]:
    mult = {"high": 1.0, "moderate": 1.6, "low": 2.4}[conf]
    hw = base_hw * mult
    return (max(0.0, p - hw), min(1.0, p + hw))


def total_readiness(section_vals: dict[str, EvidencedValue]) -> dict:
    """Sum the four section readiness estimates -> total on 472..528, with a
    propagated range. If any section abstains, the total abstains (Speedrun honesty rule)."""
    any_abstain = any(v.abstained for v in section_vals.values())
    total = sum(v.value for v in section_vals.values())
    # propagate variance: half-width = sqrt(sum hw_i^2) (z~1.0 per-section bands)
    hw = math.sqrt(sum(((v.range[1] - v.range[0]) / 2.0) ** 2 for v in section_vals.values()))
    missing = {s: v.missing for s, v in section_vals.items() if v.abstained}
    return {
        "abstained": any_abstain,
        "value": None if any_abstain else round(total, 0),
        "range": [max(472.0, round(total - hw, 0)), min(528.0, round(total + hw, 0))],
        "missing_by_section": missing,
        "note": ("Readiness withheld: insufficient evidence in "
                 + ", ".join(missing.keys()) if any_abstain else
                 "All gates passed; estimate shown with AAMC-style confidence band."),
    }
