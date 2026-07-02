# The Rust Engine Change (Speedrun 7a)

## What we changed and why it belongs in Rust

We added the MCAT readiness engine as new methods on Anki's `StatsService`, implemented in the core Rust library (`rslib`), not in the Python/Kotlin UI layers:

- **`TopicMastery`** — per-topic aggregation of FSRS retrievability (the Memory signal), mastered-card count, coverage, and graded-review volume, grouped by MCAT note tags.
- **`ComputeReadiness`** — the three separated scores (Memory / Performance / Readiness) per section, each an evidenced value with a range, the give-up rule, the learning-science multipliers, and the global next-best-action list.
- **`PointsAtStakeOrder`** — orders due cards by `topic_weight × (1 − retrievability)` so the highest-value cards can be studied first.
- **`TopicGraph`** — per-node mastery + prerequisite "ready to learn" flags for the knowledge-graph feature.

**Why Rust, not Python:** these run over the whole collection (target: 50,000 cards) and must hit the dashboard's sub-second/sub-500ms refresh budget, and — critically — they must return **identical numbers on desktop and phone**. Implementing inference once in the compiled shared engine guarantees both, where a Python-side implementation would neither be fast enough nor shared with AnkiDroid. Model *training* (IRT fit, calibration, coefficient fitting) stays offline in Python and feeds in fitted parameters as data.

The implementation reuses Anki's own `fsrs.current_retrievability_seconds(...)` (the same call `stats/graphs/retrievability.rs` uses), so the memory decay is genuine FSRS, not a re-derivation.

## Proof / correctness

- **Rust unit tests:** 8 across `rslib/src/stats/topic_mastery.rs` (5) and `rslib/src/stats/readiness.rs` (3), plus existing stats tests — full stats module runs green (`cargo test -p anki "stats::"`).
- **Python-calling tests (7a requirement):** `pylib/tests/test_topic_mastery.py`, `pylib/tests/test_readiness.py` — call the RPCs through the generated binding and assert grouping, the give-up rule, and next-action ranking.
- **Undo-safe / no corruption:** the queries are read-only over the collection (`search_cards_into_table` + reads); `test_topic_mastery.py` asserts card count and undo state are unchanged after a call. Covered further by the crash test (`analysis/crash_test.py`).

## Upstream files touched + merge difficulty

Base: upstream `ankitects/anki` at `7a9ef3239` (25.09.2+172).

| File | Change | Merge difficulty |
|---|---|---|
| `proto/anki/stats.proto` | +143: new RPCs + messages on `StatsService` | Low — additive; new messages/methods only |
| `rslib/src/stats/mod.rs` | +2: register `topic_mastery`, `readiness` modules | Low — 2 lines |
| `rslib/src/stats/service.rs` | +21: wire the new RPCs to `impl StatsService for Collection` | Low — additive impl methods |
| `rslib/src/stats/topic_mastery.rs` | NEW (307) | None — new file |
| `rslib/src/stats/readiness.rs` | NEW (426) | None — new file |
| `pylib/tests/test_topic_mastery.py`, `test_readiness.py` | NEW (115) | None — new files |
| `qt/aqt/mediasrv.py` | +6: expose new RPCs + `get_config_json` to the desktop webview allowlist | Low |
| `qt/aqt/main.py` | +2: comment (retired the separate dialog) | Low |
| `ts/routes/graphs/+page.svelte` | +3: mount `ReadinessCard` / `KnowledgeGraph` at top of Statistics | Low |
| `ts/routes/graphs/ReadinessCard.svelte` | NEW (224) | None — new file |
| `ts/routes/graphs/KnowledgeGraph.svelte` | NEW | None — new file |

Overall a **future upstream merge is low-risk**: the engine change is almost entirely new files plus additive protobuf entries; only a handful of one-to-few-line edits touch existing files, and none alter upstream scheduler/collection logic. The Android side consumes it automatically by pointing the `anki` submodule at our fork and regenerating Kotlin bindings.
