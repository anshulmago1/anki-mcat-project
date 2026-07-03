# Performance Model (P)

**Question answered:** can the student answer a *new*, exam-style question that uses the fact — transfer, not recall?

## Method
3-parameter logistic Item Response Theory. For section ability `θ_s` and question `j` with discrimination `a`, difficulty `b`, guessing `c` (≈0.25 for a 4-choice MCQ):

```
P(correct | θ_s, a, b, c) = c + (1 − c) / (1 + e^(−a(θ_s − b)))
```

- `θ_s` is estimated by MLE from the student's answered questions (in-app question checks); item parameters are fit offline (`analysis/irt_fit.py`) and exported.
- `P_s` = mean predicted correctness over the section's items. CARS uses a `θ` independent of the science sections (reading comprehension, not fact recall).

### Live path (desktop / AnkiDroid)
The dashboard's Performance number is genuinely IRT, not a `correct/total` proxy. The answered exam-style items for each section are persisted in the collection config `mcat_perf` as per-section 3PL items:

```json
{ "BB": { "items": [ { "a": 1.1, "b": 0.3, "c": 0.25, "correct": 1 }, ... ] }, ... }
```

The desktop caller (`anki/ts/routes/graphs/ReadinessCard.svelte`) then reproduces `analysis/irt_fit.py` exactly in TypeScript before calling the `ComputeReadiness` RPC:

- `θ_s` is estimated by grid-search MLE over `θ ∈ [-4, 4]` (161 points) maximizing `Σ [y·log p + (1−y)·log(1−p)]` (probabilities clipped to `[1e-6, 1−1e-6]`; first grid point wins on ties, matching `np.argmax`).
- `SE(θ_s) = 1/√I` where `I = Σ a² · (p−c)²/(1−c)² · (1−p)/p` is the summed 3PL Fisher information at `θ_s` (identical formula to `irt_fit.estimate_theta`).
- `P_s` = mean of `p3pl(θ_s, item)` over the section's answered items.
- A section with no answered items abstains on SE (`θ_se = 9.9`), tripping the give-up rule.

`P_s` and `SE(θ_s)` are passed into `ComputeReadiness`; the Rust `PERF_METHOD` label ("3PL IRT ability on held-out exam-style questions") is therefore accurate for the live path.

## Why P ≠ M (the point of the bridge)
Recalling a flashcard is not the same as applying the concept to a passage (transfer-appropriate processing; Pan & Rickard 2018: retrieval-practice transfer d = 0.40, dropping to 0.28 when the question is reworded). The **paraphrase gap M − P** is reported as a first-class output (Speedrun 7d).

## Evidence + evaluation (Speedrun step 2)
Held-out questions answered, IRT standard error `SE(θ_s)`, and the paraphrase gap. On a temporal split (`analysis/perf_eval.py`): **accuracy 0.70, AUC 0.74, Brier 0.19** — beats both a keyword baseline (predict correct iff topic R>0.7) and a vector-similarity baseline. Paraphrase test: recall 0.83 vs transfer 0.57 → gap 0.27 (positive, so P measures transfer).

## Give-up interaction
If `SE(θ_s)` exceeds the threshold (too few questions answered), the section abstains and the next-best-action recommends a question check.
