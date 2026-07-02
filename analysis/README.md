# MCAT Readiness - Learning-Science Analysis Harness

Evidence-backed implementation of the three-layer readiness model and its
evaluation. Every number traces to a source; nothing is shown without evidence.

## Run it

```bash
make venv     # one-time: create .venv with numpy
make eval     # reproduce all metrics -> data/eval/*.json + RESULTS.md
make demo     # build a real tagged Anki collection + run the live dashboard
```

`make eval` uses a plain numpy venv. `make demo`/`make dashboard` use Anki's built
Python (`../anki/out/pyenv`) because they call the live Rust engine.

## What each piece does (mapped to the Speedrun spec)

| File | Purpose | Spec |
|---|---|---|
| `../data/aamc_outline.json` | AAMC content categories, section + topic weights, tag scheme | sec.5, 7c |
| `simulate.py` | seeded synthetic reviews / IRT question bank / paraphrase pairs | sec.9 |
| `calibration.py` | ECE, Brier (REL/RES/UNC), log loss, reliability diagram; beats constant-p | step 1, 20% |
| `irt_fit.py` | 3PL IRT theta MLE; exports item params + theta | step 2 |
| `perf_eval.py` | held-out accuracy / AUC / Brier; beats keyword + vector baselines | step 2, 20% |
| `readiness.py` | M/P/E composite, multipliers (each cited), give-up rule, EvidencedValue | sec.3-4, 4 |
| `score_map.py` | section->scaled mapping, coefficient fit, total + range, paraphrase gap | step 3, 7d |
| `ablation.py` | pre-registered interleaving 3-build ablation (V1/V2/V3) | sec.8, 15% |
| `leakage_check.py` | TF-IDF n-gram cosine leak detector (self-tested) | 7e |
| `make_demo_collection.py` | real MCAT-tagged Anki collection with reviews | 7c |
| `dashboard.py` | end-to-end: memory from the live Rust mastery query -> 3 scores + give-up | sec.3-4 |
| `report.py` | assembles `RESULTS.md` (honest, incl. limitations + nulls) | sec.9 |

## The Rust change (lives in the engine, ships to both apps)

The Memory layer's per-topic aggregation is a real `rslib` change:
`anki/proto/anki/stats.proto` (TopicMastery RPC), `anki/rslib/src/stats/topic_mastery.rs`
(4 unit tests), wired in `mod.rs` + `service.rs`, with a Python-calling test in
`anki/pylib/tests/test_topic_mastery.py` (grouping + undo/read-only safety).

## Honesty

We lack real student study+full-length-score longitudinal data, so we grade the
steps of the bridge on honest synthetic data and label the readiness coefficients
as not-yet-field-calibrated. See the limitations section of `RESULTS.md`.
