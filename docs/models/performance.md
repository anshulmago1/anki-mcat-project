# Performance Model (P)

**Question answered:** can the student answer a *new*, exam-style question that uses the fact — transfer, not recall?

## Method
3-parameter logistic Item Response Theory. For section ability `θ_s` and question `j` with discrimination `a`, difficulty `b`, guessing `c` (≈0.25 for a 4-choice MCQ):

```
P(correct | θ_s, a, b, c) = c + (1 − c) / (1 + e^(−a(θ_s − b)))
```

- `θ_s` is estimated by MLE from the student's answered questions (in-app question checks); item parameters are fit offline (`analysis/irt_fit.py`) and exported.
- `P_s` = mean predicted correctness over the section's items. CARS uses a `θ` independent of the science sections (reading comprehension, not fact recall).

## Why P ≠ M (the point of the bridge)
Recalling a flashcard is not the same as applying the concept to a passage (transfer-appropriate processing; Pan & Rickard 2018: retrieval-practice transfer d = 0.40, dropping to 0.28 when the question is reworded). The **paraphrase gap M − P** is reported as a first-class output (Speedrun 7d).

## Evidence + evaluation (Speedrun step 2)
Held-out questions answered, IRT standard error `SE(θ_s)`, and the paraphrase gap. On a temporal split (`analysis/perf_eval.py`): **accuracy 0.70, AUC 0.74, Brier 0.19** — beats both a keyword baseline (predict correct iff topic R>0.7) and a vector-similarity baseline. Paraphrase test: recall 0.83 vs transfer 0.57 → gap 0.27 (positive, so P measures transfer).

## Give-up interaction
If `SE(θ_s)` exceeds the threshold (too few questions answered), the section abstains and the next-best-action recommends a question check.
