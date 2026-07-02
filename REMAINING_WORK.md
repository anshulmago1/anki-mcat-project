# Status vs. the Speedrun Assignment

Audit against the Speedrun spec. Almost everything is now implemented, tested, and
reproducible. The only remaining items are ones **you** must do by hand (record the
demo video, install on truly clean machines, optional release-signing).

Legend: ✅ done · 🟡 partial / your action · ❌ not started

---

## Spec requirements — status

| Spec item | Status | Evidence |
|---|---|---|
| Real change inside Anki's Rust code (7a) | ✅ | `rslib`: mastery query, readiness inference, points-at-stake, **TopicGraph**; 15 Rust unit tests + 4 Python tests; single-pass `compute_readiness` |
| Three separate scores, each a range (sec. 3-4) | ✅ | Memory / Performance / Readiness, every value an `EvidencedScore` with range + drivers, computed in-engine |
| Give-up rule / refuse score without data | ✅ | coded thresholds, abstains, shown on desktop + phone |
| Coverage map (7c) | ✅ | coverage % + abstain; AAMC outline is the single source of truth, maps generated into Svelte + Kotlin via `gen_outline_maps.py` (no drift) |
| Paraphrase test (7d) | ✅ | 30 **real** hand-authored recall→transfer pairs (`data/questions/paraphrase_real.json`); gap 0.13, TF-IDF cosine max 0.38 (genuine paraphrases), gap↔difficulty corr 0.61 |
| Leakage check (7e) | ✅ | TF-IDF detector, self-tested, in `make eval` |
| Memory calibration (sec. 9 step 1) | ✅ | ECE 0.008 / Brier / log loss, beats baseline |
| Performance on held-out (step 2) | ✅ | 3PL IRT, AUC 0.74, beats keyword + vector |
| Score mapping with a range (step 3) | ✅ | documented, honest "not field-calibrated" label |
| Study feature, 3 builds (sec. 8) | ✅ | interleaving ablation V1/V2/V3, pre-registered |
| **AI: source-grounded, checked, beats a baseline (7f)** | ✅ | local llama3 RAG; gold set (50); checker with pre-registered cutoffs; **0.75 vs 0.0** correct-rate vs keyword/vector; injection defense **6/6**; passing cards exported to `.apkg` |
| **Two-way sync + conflict rule (7b)** | ✅ | `sync_test.py` through a real local sync server: 20 offline reviews merge with no loss/double-count; same-card conflict → last-write-wins; `docs/SYNC.md` |
| **Crash + offline (7g)** | ✅ | `crash_test.py`: 20× mid-review SIGKILL → 0 corruption; AI fails-closed offline, score still computes |
| **One-command benchmark + sec.10 targets (7h)** | ✅ | `make bench` on 50,000 cards; all actions within p95 targets (dashboard load 475ms<1s, refresh 470ms<500ms, next card 2.3ms<100ms) |
| Two apps share one engine | ✅ | desktop + AnkiDroid run the forked `rslib`; in-app readiness screen on both |
| Fair, re-runnable tests | ✅ | `make eval` / `make ai` / `make bench` / `make crash`, temporal splits |
| Deliverables (README, 3 model one-pagers, Rust note, files-touched) | ✅ | `README.md`, `docs/models/*.md`, `docs/RUST_CHANGE.md` |
| **Knowledge graph beats keyword+vector (bonus, sec.13)** | ✅ | interactive `KnowledgeGraph.svelte` + `TopicGraph` RPC; `graph_eval.py`: +14.3 / +18.5 projected-MCAT points, 0 prereq-violating steps |
| Next-best-action engine | ✅ | global ranked actions with learning-science reasons |

Full numbers: `analysis/RESULTS.md` (10 sections). Reproduce: `make eval && make ai && make bench && make crash` + `python analysis/sync_test.py`.

---

## Remaining — your manual actions

### R1. Installers on genuinely clean devices  🟡
- Desktop `.dmg` is built (`anki/out/installer/...`); install it on a clean machine / fresh
  user and confirm it launches and the readiness + graph screens work.
- Phone: the debug APK runs on the emulator (satisfies "runs on a device"). Optional: produce
  a **release-signed** APK for polish.

### R2. Demo video (3-5 min)  ❌ (recording)
Show: a review session, the Rust change in action, a card synced phone→desktop, the three
scores with ranges, the knowledge graph, the AI features, and the test results.

### R3. Optional bonus
- Section 9 step 4: validate against real students with study history + practice-test scores.
- Field-calibrate the readiness coefficients once real outcome data exists.
- Push the AI-generated `.apkg` into the shipped deck; wire `PointsAtStakeOrder` into a live
  "study highest-value cards now" queue button.

---

## One-command recap

```
cd analysis
make eval     # calibration, IRT, leakage, score map, paraphrase(real), ablation, graph_eval -> RESULTS.md
make ai       # local-LLM RAG generation, gold-set check, beats baselines, injection defense, export apkg
make bench    # 50,000-card speed benchmark vs section-10 targets
make crash    # 20x mid-review kill: zero corruption + AI-off offline score
python sync_test.py   # two-device offline merge + conflict rule (7b)
```
