# Verification bundle

One place to verify the project. Every row links to a captured log in
[docs/verification/](verification/) and gives the exact command to reproduce it.
Full model results are in [analysis/RESULTS.md](../analysis/RESULTS.md); deployment
artifacts (installer hash, APK, `.aar`) are in
[docs/verification/deployment.md](verification/deployment.md).

Captured 2026-07-03 on a mid-range Apple-Silicon Mac.

## Test output

| What | Result | Log | Reproduce |
|---|---|---|---|
| Rust engine unit tests (MCAT stats modules) | **15 passed / 0 failed** | [rust_tests.txt](verification/rust_tests.txt) | `cargo test -p anki --lib stats::` |
| Python integration tests (RPCs from Python) | **5 passed** | [python_tests.txt](verification/python_tests.txt) | `out/pyenv/bin/python -m pytest pylib/tests/test_topic_graph.py pylib/tests/test_readiness.py pylib/tests/test_topic_mastery.py` |
| TypeScript/Svelte typecheck | **0 errors / 0 warnings** | [svelte_check.txt](verification/svelte_check.txt) | `cd anki/ts && svelte-check` |
| Evaluation harness (`make eval`) | green (calibration ECE 0.008; IRT AUC 0.74 beats baselines; interleaving ablation +9.2pp; graph +14.3/+18.5; real paraphrase gap 0.13; targeted-gen graph 0.62 vs 0.23/0.33/0.32) | [make_eval.txt](verification/make_eval.txt) | `make -C analysis eval` |
| Local-AI generation (7f) | **correct-rate 0.75 vs 0.0** keyword/vector; **injection defense 6/6**; 30 cards exported | [make_ai.txt](verification/make_ai.txt) | `make -C analysis ai` |
| Graph-guided targeted generation | 3/3 grounded cards passed the checker; targeting beats random/weight/due | [make_ai_targeted.txt](verification/make_ai_targeted.txt) | `make -C analysis ai-targeted` |
| Study planner: graph vs keyword vs vector search | **graph beats both at all K** (exam gain@10 +1.83 vs keyword / +1.81 vs vector, 95% CIs exclude 0; real `nomic-embed-text` embeddings); text↔prereq AUC 0.86–0.90 but direction acc = 0.5 (symmetric) | [study_plan.txt](verification/study_plan.txt) | `make -C analysis plan` |
| Two-device sync (7b) | **20/20 reviews merged, no double-count, conflict = last-write-wins** | [sync_test.txt](verification/sync_test.txt) | `python analysis/sync_test.py` |
| Live phone↔desktop sync (real apps) | **bidirectional, verified**: desktop→server→phone (phone collection == desktop: scm/mod/cards identical), and a "Good" review on the phone → server → desktop (revlog 16→17, exact review present) | [live_sync.txt](verification/live_sync.txt) · [live_sync_phone.png](verification/live_sync_phone.png) | see log (self-hosted `syncserver` + AnkiDroid fork on emulator) |
| Crash + offline (7g) | **0/20 corrupted**; AI fails-closed offline; score still computes | [crash_test.txt](verification/crash_test.txt) | `make -C analysis crash` |
| Benchmark, 50k-card deck (7h + sec.10) | see note below | [make_bench.txt](verification/make_bench.txt) | `make -C analysis bench` |

## Benchmark note (honest)

On the 50,000-card deck, all actions clear their **p50** targets, and the
user-visible **dashboard first load** (`compute_readiness`) clears its p95 budget
(≈488 ms vs 1000 ms). The two full-collection scans (`topic_mastery`,
`topic_graph`) land at **p95 ≈ 530–555 ms against the strict 500 ms *refresh*
target** on this machine (p50 ≈ 470 ms) - a marginal miss under load. The
single-pass `compute_readiness` optimization already cut that path ~4x; a tag/
retrievability index would close the remaining gap and is noted as future work.
`next_card_after_grading` is ≈2.6 ms p95 (target 100 ms). Numbers are reported as
measured, not gamed.

## Deployment evidence

See [deployment.md](verification/deployment.md): macOS `.dmg` (SHA-256 pinned) that
is verified to contain the fork's features (not stock Anki), the signed Android
APK, and the shared-engine `.aar`. The installer *screen recording* is the single
artifact that must be captured by a human - a 1-minute runbook is included there.

## Everything at once

```bash
cd analysis
make eval && make ai && make ai-targeted && make bench && make crash
python sync_test.py
cd ../anki && cargo test -p anki --lib stats:: && (cd ts && svelte-check)
```
