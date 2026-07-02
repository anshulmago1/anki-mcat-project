# Readiness Model (E) + Give-Up Rule

**Question answered:** what would the student score today, and how sure are we?

## Method
Per section, a logit-linear map to the 118–132 scale, combining memory (with learning-science multipliers), performance, and coverage:

```
E_s = 118 + 14 · σ( b0 + bM · M_s · α_space · α_inter · α_test + bP · P_s + bC · C_s )
E_total = Σ_s E_s          (472–528, summed like the real MCAT)
```

- Coefficients `{b0, bM, bP, bC}` are fit offline (`analysis/score_map.py`); the section→scaled residuals give a ±3–4 point band.
- The total is shown with a propagated range and an AAMC-style confidence band (±1 section / ±2 total), widening when data is sparse.

## Learning-science multipliers (each cited, each gated)
| Multiplier | Range | Trigger | Evidence |
|---|---|---|---|
| α_space | 1.0–1.4 | review timing vs FSRS-optimal | Cepeda 2008 (spacing, up to +150% vs massed) |
| α_inter | 1.0–1.3 | session mixes ≥2 topics AND all R_i>0.4 (Bjork prior-knowledge gate) | Bjork lab 20%→63%; Taylor & Rohrer 2010 |
| α_test | 1.0–1.5 | active retrieval; disabled if median response <2s | Dunlosky 2013 high-utility, d≈0.55 |

## Give-up rule (Speedrun sec. 4) — coded constants
A section's readiness is **withheld** unless all hold:
- `MIN_GRADED_REVIEWS = 200` per section
- `MIN_COVERAGE = 0.50` of the section's AAMC topics
- `MAX_IRT_SE = 0.50`

If any section abstains, the **total abstains** and lists what's missing plus the next-best action. This is why a strong-in-3-sections / blind-to-CARS student is never told they're ready — the core failure mode of competitor tools.

## Evidence + honesty
Every readiness value carries its reviews, coverage %, confidence, and drivers. The score mapping is documented and, per Speedrun sec. 9, **explicitly labeled not-yet-field-calibrated** (we lack real study-history + full-length-score data). Saying "we calibrated memory and validated performance on held-out questions, but can't yet prove the projected score" scores higher than a fabricated number.
