# Demo Video Script (3–5 min)

Everything below is already working; this is a shot list so the recording hits every graded item.

## Setup (before recording)
- Sync server running: `cd anki && SYNC_USER1=mcat:mcat123 SYNC_BASE=/tmp/mcat_syncserver SYNC_PORT=8090 out/pyenv/bin/python -m anki.syncserver`
- Desktop on the MileDown base: `./run -b /Users/anshul/Desktop/AlphaAI/anki-mcat-project/mcat_base`
- Emulator windowed: `emulator -avd mcat_test -gpu swiftshader_indirect &`

## Shot list

1. **The two apps, one engine (0:00–0:30).** Desktop Anki + the Android emulator side by side, both showing the MileDown MCAT deck. State the exam (MCAT) and that both run the same forked Rust engine.

2. **A review session (0:30–1:00).** Review a few real MileDown cards on desktop; answer with Good/Again. Mention FSRS scheduling.

3. **The three scores + give-up rule (1:00–2:00).** Tools → Statistics. Show the readiness card at the top:
   - Memory / Performance / Readiness per section, each with a range and evidence.
   - CARS **withheld** with the reason (coverage) — call out the give-up rule / coverage blindspot.
   - The **"Do this next"** ranked next-best-action list with learning-science reasons.
   - Scroll to the **knowledge graph** — nodes colored by mastery, prerequisite edges, recommended path.

4. **The Rust change in action (2:00–2:30).** Briefly show `anki/rslib/src/stats/readiness.rs` + `topic_mastery.rs`, and `cargo test -p anki "stats::"` passing. Note it ships to both platforms.

5. **Phone→desktop sync (2:30–3:15).** On the phone, review a card; tap sync. On desktop, sync and show the review appear (and the readiness numbers update). Mention the conflict rule (`docs/SYNC.md`).

6. **AI features (3:15–4:00).** `cd analysis && make ai`: show source-grounded card generation (each card carries its named source), the gold-set checker classifying correct/wrong/poor, the pre-registered cutoff blocking failures, and the eval beating keyword/vector baselines. Note it's local (Ollama) and the app scores fully with AI off.

7. **Test results (4:00–4:45).** `make eval` + open `analysis/RESULTS.md`: calibration (ECE/Brier), performance AUC vs baselines, interleaving ablation V1/V2/V3, leakage check, paraphrase gap. `make bench` p50/p95/worst. Mention crash test = zero corruption.

8. **Close (4:45–5:00).** Restate the thesis: three honest, evidence-backed numbers; refuses to guess; tells you the single best next thing to study.

## One-liners to have ready
- "Every number carries its evidence; if it can't, the app abstains."
- "Memory is FSRS forgetting; Performance is IRT transfer; Readiness is the coverage-gated map — three different questions, three different numbers."
- "The engine change is one Rust implementation that ships to desktop and phone."
