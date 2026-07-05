# Demo Video — script, runbook, and two-way-sync steps

Everything below is already working. This file has three parts:
1. **Which recording is due when** (Friday proof vs. Sunday 3–5 min hand-in)
2. **Pre-flight runbook** — exact commands to launch desktop + phone + sync server with the deck preloaded
3. **The narration script** (timed shot list) + a **what-to-include checklist**

Exam: **MCAT** (472–528; four sections 118–132). Both apps run the same forked Rust engine.

---

## 1. Which recording is due when

| Deadline | What the recording must prove (from the Speedrun spec) |
|---|---|
| **Friday** | (a) AI **eval numbers + baseline comparison** (AI beats keyword/vector), and (b) **a card reviewed on the phone showing up on the desktop after sync**. |
| **Sunday (final, sec.12)** | One **3–5 min** video showing: a review session · the Rust change in action · a card synced phone→desktop · the three scores with ranges · the AI features · the test results. |

The full script below covers the Sunday hand-in; the **Friday-critical shots are tagged `[FRIDAY]`**, so you can cut a shorter Friday clip from the same run.

---

## 2. Pre-flight runbook (do this before you hit record)

> Current machine state (as left by the live-sync verification): sync server is UP on `:27703`, the emulator is running, `mcat_base` holds the 2,888-card MileDown deck, and the fork is installed at `/Applications/Anki.app`. If you rebooted, run the steps below from scratch.

**Terminal A — self-hosted sync server** (holds the shared collection; user `mcat`/`mcat`):
```bash
cd /Users/anshul/Desktop/AlphaAI/anki-mcat-project
SYNC_USER1="mcat:mcat" SYNC_BASE="/tmp/mcat_livesync" SYNC_HOST="0.0.0.0" SYNC_PORT="27703" \
MAX_SYNC_PAYLOAD_MEGS="1000" \
PYTHONPATH="$PWD/anki/out/pylib:$PWD/anki/pylib" \
anki/out/pyenv/bin/python -c "from anki.syncserver import run_sync_server; run_sync_server()"
# leave running; you should see: listening addr=0.0.0.0:27703
```

**Terminal B — desktop app on the seeded, synced collection** (`mcat_base` has the deck + readiness data):
```bash
cd /Users/anshul/Desktop/AlphaAI/anki-mcat-project/anki
export PATH="$HOME/.cargo/bin:$PATH"
./run -b /Users/anshul/Desktop/AlphaAI/anki-mcat-project/mcat_base
```
One-time desktop sync config (needed so the Sync button hits the local server, not AnkiWeb):
- **Preferences → Syncing → self-hosted sync server URL** = `http://127.0.0.1:27703/`
- Click **Sync** (↻), log in as **mcat / mcat**. First sync should be **No changes** (already converged). Leave it logged in.

**Terminal C — Android emulator** (windowed, so it's on camera):
```bash
export ANDROID_HOME="/opt/homebrew/share/android-commandlinetools"
"$ANDROID_HOME/emulator/emulator" -avd mcat_test -netdelay none -netspeed full -no-snapshot-save &
# then open AnkiDroid:
"$ANDROID_HOME/platform-tools/adb" shell am start -n com.ichi2.anki.debug/com.ichi2.anki.IntentHandler
```
The phone is **already configured** to sync to `http://10.0.2.2:27703/` (custom URL + auto-sync + logged in as `mcat`). Open it once and let it auto-sync so both sides are converged before recording.

**Converge both before rolling:** sync desktop, then open/sync the phone, until both say "No changes." (This keeps the on-camera sync a clean *incremental* merge and avoids the one-time full-sync dialog.)

---

## 3. Two-way sync — the exact on-camera sequence  `[FRIDAY]`

**Phone → desktop (the required shot):**
1. On the **phone**, open a deck (e.g., *Behavioral*), tap a card → **Show answer** → **Good**. Say the card's prompt out loud so it's identifiable.
2. Tap the **sync icon** on the phone (top-right) — wait for it to finish.
3. On the **desktop**, click **Sync (↻)**.
4. Show the result: the **"Studied today"** count / that deck's due counts change, and (Tools → Statistics) the **readiness numbers update**. Say: "The phone review just landed on the desktop."

**Desktop → phone (reverse, optional but strong):**
1. On the **desktop**, review one card → **Good** → click **Sync**.
2. On the **phone**, tap **Sync** → open the same deck and show the review reflected.

Mention the conflict rule while syncing: *"Reviews union-merge and never double-count; same-card offline edits resolve last-write-wins — documented in `docs/SYNC.md`, and verified live in `docs/verification/live_sync.txt`."*

---

## 4. Narration script (timed, ~4:30)

**0:00–0:30 — Two apps, one engine.**  `[FRIDAY-context]`
Desktop Anki and the Android emulator side by side, both showing the MileDown MCAT deck.
> "This is an MCAT readiness tool built on a fork of Anki. The desktop app and this Android phone run the **same forked Rust engine** — same cards, same progress, and they sync. The MCAT is scored 472–528 across four sections."

**0:30–1:00 — A review session.**
Review a few real MileDown cards on desktop; answer Good/Again.
> "Normal Anki review, scheduled by FSRS — that's the memory layer. But memory isn't readiness, so we built two more."

**1:00–2:00 — The three scores + give-up rule + next action.**
Tools → Statistics → the readiness card at the top.
> "Three separate numbers, each with a range and its evidence. **Memory** is FSRS retrievability. **Performance** is a 3PL IRT estimate — the chance you get a *new* exam-style question right, computed live in the engine. **Readiness** maps to the 118–132 scale with a confidence band."
- Point at a **section that's withheld** (coverage/insufficient data): *"When there isn't enough evidence, it refuses to show a score and says exactly what's missing — that's the give-up rule."*  `[honesty]`
- Point at **"Do this next"**: *"It always names the single highest-value next topic, with the learning-science reason."*
- Expand the **knowledge graph**: *"Nodes colored by mastery, prerequisite edges, and a recommended path that never sends you to a topic whose foundations are shaky."*

**2:00–2:30 — The Rust change in action.**
Show `anki/rslib/src/stats/` (readiness.rs / topic_mastery.rs / topic_graph.rs) and a passing test run:
```bash
cd anki && cargo test -p anki --lib stats::
```
> "The readiness, mastery, and graph logic live in Anki's Rust core as new protobuf RPCs — 15 unit tests plus a Python-calling test — so the exact same engine ships to desktop and phone."

**2:30–3:15 — Phone → desktop sync.**  `[FRIDAY]`
Run the two-way sync sequence from section 3 on camera.

**3:15–4:00 — AI features.**  `[FRIDAY]`
```bash
cd analysis && make ai
```
> "Local, source-grounded card generation with Ollama. Every card carries its named source; a checker classifies correct / wrong / poor against a 50-item gold set; a pre-registered cutoff blocks failures; and it beats keyword and vector baselines — 0.75 vs 0.0. Prompt-injection defense passes 6 of 6. Turn AI off and the app still scores."

**4:00–4:30 — Test results.**  `[FRIDAY-numbers]`
Open `analysis/RESULTS.md` (or `docs/VERIFICATION.md`).
> "Calibration ECE 0.008; performance AUC 0.74 beating keyword and vector; interleaving ablation V1/V2/V3; leakage check clean; paraphrase gap measured. And the knowledge-graph study planner beats real TF-IDF and neural-embedding search by ~1.8 MCAT points, 95% CI excluding zero. Benchmarks p50/p95 on a 50k-card deck; crash test zero corruption."

**4:30 — Close.**
> "Three honest, evidence-backed numbers, a tool that refuses to guess, and it always tells you the single best next thing to study."

---

## 5. What-to-include checklist (map to the spec)

- [ ] Exam stated (MCAT) + two apps, one engine  `[sec.12]`
- [ ] A review session  `[sec.12]`
- [ ] Rust change in action + tests passing  `[sec.12]`
- [ ] Card synced **phone → desktop**  `[sec.12, FRIDAY]`
- [ ] Three scores (Memory / Performance / Readiness) **each with a range**  `[sec.12]`
- [ ] Give-up rule / abstention shown on a low-data section  `[honesty]`
- [ ] AI features: named source, checker, cutoff, **beats keyword/vector**  `[sec.12, FRIDAY]`
- [ ] Test results: calibration, performance, ablation, leakage, benchmark  `[sec.12, FRIDAY]`
- [ ] (bonus) knowledge-graph study planner beats keyword+vector
- [ ] (bonus) AI-off still gives a score / installer runs on clean machine

---

## One-liners to have ready
- "Every number carries its evidence; if it can't, the app abstains."
- "Memory is FSRS forgetting; Performance is IRT transfer; Readiness is the coverage-gated map — three questions, three numbers."
- "The engine change is one Rust implementation that ships to desktop and phone."
- "Reviews union-merge on sync and never double-count; conflicts are last-write-wins."
