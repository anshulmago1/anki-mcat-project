# Memory Model (M)

**Question answered:** can the student recall a trained fact right now?

## Method
Per card, we use Anki's FSRS-6 retrievability — a power-law forgetting curve evaluated at the current elapsed time since last review:

```
R = (1 + factor · t / S) ^ (−decay)
```

- `t` = seconds since last review, `S` = FSRS stability, `decay` = FSRS-6 decay (≈0.2). `factor` is set so `R(S, S) = 0.90`.
- Computed in the engine via `fsrs.current_retrievability_seconds(state, elapsed, decay)` — the same call Anki's own retrievability graph uses, so decay is genuine, not re-derived.

The section score is the AAMC-topic-weighted mean over covered topics:

```
M_s = Σ_i  w_i · mean_R_i
```

where `w_i` is the topic's AAMC weight and `mean_R_i` is the card-weighted mean retrievability for topic `i` (from the `TopicMastery` RPC).

## Evidence attached (never a bare number)
Graded reviews behind the score, coverage %, last-review recency, and the method tag `FSRS-6 retrievability`. Displayed with a confidence-scaled range.

## Calibration (Speedrun step 1)
When the model says 0.80, ~80% of held-out reviews at that level should succeed. On a temporal held-out split (`analysis/calibration.py`): **ECE 0.008**, **Brier 0.078** (REL 0.0005 − RES 0.0015 + UNC 0.0795), **log loss 0.286** — beats the constant-p baseline. Anchored to the FSRS-6 benchmark (log loss ≈0.345, AUC ≈0.705).

## Give-up interaction
M contributes to readiness only when its section clears the gate (≥200 graded reviews, ≥50% coverage). A section with high M but thin evidence still abstains.
