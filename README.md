# Readygauge — an MCAT readiness engine built on Anki

**Exam: the MCAT** (scored 472–528; four sections B/B, C/P, P/S, CARS each 118–132). A desktop app and an Android companion share **one forked Rust engine** and answer three separate questions honestly — *can you recall this?*, *can you apply it to a new question?*, and *what would you score, and how sure are we?* — refusing to show a number it cannot defend.

This is a fork of [Anki](https://apps.ankiweb.net/) and [AnkiDroid](https://github.com/ankidroid/Anki-Android). License: **AGPL-3.0-or-later**, with credit to Ankitects Pty Ltd and the AnkiDroid project (some upstream parts are BSD-3-Clause; preserved).

---

## The three repos (all forked, all AGPL)

| Fork | Upstream | Role | Our branch |
|---|---|---|---|
| [anshulmago1/anki](https://github.com/anshulmago1/anki) | ankitects/anki | Rust engine (`rslib`) + desktop (Python/Qt) + shared web frontend (`ts/`) | `mcat-readiness` |
| [anshulmago1/Anki-Android-Backend](https://github.com/anshulmago1/Anki-Android-Backend) | ankidroid/Anki-Android-Backend | `rsdroid` JNI bridge; includes `anki` as a submodule, compiles `rslib` to an Android `.aar` | `mcat-readiness` |
| [anshulmago1/Anki-Android](https://github.com/anshulmago1/Anki-Android) | ankidroid/Anki-Android | Kotlin phone app that consumes the `.aar` | `mcat-readiness` |

The **one shared engine change** is written once in Rust (`rslib`) and ships to both platforms because the phone backend includes the desktop engine as a git submodule and regenerates its Kotlin bindings from the same protobuf.

---

## What we built (the readiness model)

Every displayed number is an `EvidencedValue` — value + range + confidence + the reviews/coverage/calibration behind it. Nothing shows without its evidence.

- **Memory (M):** FSRS-6 retrievability, aggregated per AAMC topic from your real reviews (models the forgetting curve).
- **Performance (P):** 3PL IRT — the probability you answer a *new* exam-style question right (transfer, not recall). Computed live in the app (grid-MLE ability θ + Fisher-information SE, a direct port of `analysis/irt_fit.py`), not a `correct/total` proxy. The M−P "paraphrase gap" is a first-class output (real recall→transfer items in `analysis/perf_bridge.py`).
- **Readiness (E):** coverage-gated map to the 118–132 section scale, summed to a 472–528 total with a range and AAMC-style confidence band.
- **Give-up rule:** withholds a score until a section has ≥200 graded reviews, ≥50% coverage, and a tight enough IRT SE.
- **Next-best-action + knowledge graph:** a ranked "do this next" list and an interactive prerequisite graph (nodes colored by mastery) — both proven to beat keyword/vector baselines.
- **Graph-guided AI card generation:** the graph selects your highest-value, prerequisite-ready weak topics; the local LLM generates source-grounded, checker-verified cards for exactly those topics (`make ai-targeted`). The targeting decision beats random/weight/due baselines and never wastes budget on a prerequisite-blocked topic.
- **Learning-science multipliers** (spacing, interleaving, testing) tied to published effect sizes (Cepeda 2008, Bjork/Rohrer, Dunlosky 2013). Honesty: they are **neutral (1.0) in the live score** until session-level study quality is measured — no unearned boost — and are exercised in the interleaving ablation instead.

See [PRD.md](PRD.md) for the full product spec and [docs/models/](docs/models/) for one-page descriptions of each model.

---

## The Rust engine change (graded 20%)

See [docs/RUST_CHANGE.md](docs/RUST_CHANGE.md) for the one-page note and the list of upstream files touched with merge-difficulty. In brief: new RPCs on `StatsService` (`TopicMastery`, `ComputeReadiness`, `PointsAtStakeOrder`, `TopicGraph`) implemented in `anki/rslib/src/stats/`, with ≥11 Rust unit tests + Python-calling tests, undo-safe and read-only over the collection.

---

## Architecture

```mermaid
graph TD
  ENGINE["rslib (Rust): mastery query, readiness inference,<br/>points-at-stake, topic graph"]
  PROTO["proto/anki/stats.proto (one contract)"]
  ENGINE --- PROTO
  PROTO -->|PyO3| DESK["Desktop: pylib + Qt + Svelte Statistics page"]
  PROTO -->|JNI + generated Kotlin| PHONE["AnkiDroid: rsdroid .aar + Statistics webview"]
  DESK <-->|Anki sync protocol| SERVER["self-hosted sync server (from rslib)"]
  PHONE <-->|Anki sync protocol| SERVER
  PY["Python offline: IRT fit, calibration, ablation,<br/>leakage, AI card gen/checker, graph eval"] -.fitted params + apkg.-> ENGINE
```

Full detail: [ARCHITECTURE.md](ARCHITECTURE.md) and [CODEBASE_MAP.md](CODEBASE_MAP.md).

---

## Build & run

### Prerequisites
- Rust (rustup; the pinned toolchain auto-installs), Python 3 with `uv`, Node, Ninja, protoc, a C toolchain.
- Android: JDK 21, Android SDK + NDK `29.0.14206865`, `cargo-ndk`.

### Desktop (from source)
```bash
cd anki
export PATH="$HOME/.cargo/bin:$PATH"
./run                     # build + launch
# or open a specific collection base:
./run -b /path/to/base
```

### Desktop installer (.dmg)
```bash
cd anki && RELEASE=1 ./ninja installer
# -> out/installer/dist/anki-*-mac-apple.dmg
```
Open the `.dmg` and drag **Anki.app** into **/Applications** — the Dock/Launchpad icon
then launches the fork (it replaces the stock Anki; your card data is untouched). The
build is ad-hoc signed, so on a clean Mac use right-click → Open once to pass Gatekeeper.

### Android (emulator or device)
```bash
# 1. build the shared engine into an .aar
cd Anki-Android-Backend && bash build.sh
# 2. build + install the app
cd ../Anki-Android
echo "local_backend=true" >> local.properties
./gradlew assembleFullDebug
adb install -r AnkiDroid/build/outputs/apk/full/debug/AnkiDroid-full-arm64-v8a-debug.apk
```

### Evaluation, AI, benchmark (from `analysis/`)
```bash
cd analysis
make venv          # one-time: numpy venv
make eval          # calibration, IRT, ablation, leakage, real-paraphrase, graph-vs-baselines -> RESULTS.md
make ai            # Ollama RAG card generation + gold-set checker + injection defense (needs `ollama serve`)
make ai-targeted   # graph-guided targeted generation: graph picks weak topics -> grounded+checked cards -> MCAT_Targeted.apkg
make bench         # 50k-card speed benchmark vs section-10 targets (p50/p95/worst)
make crash         # 20x mid-review SIGKILL: zero corruption + AI-off offline score
python sync_test.py  # two-device offline merge + conflict rule (7b)
make demo          # build a real tagged MileDown collection + live dashboard
```

---

## Sync

Both apps share one collection via Anki's own sync protocol (self-hosted server compiled from `rslib`). Conflict rule and the 7b offline-merge evidence: [docs/SYNC.md](docs/SYNC.md).

---

## Honesty

We do not have real student study-history + full-length-score longitudinal data, so we grade the **steps of the bridge** (calibrated memory, held-out performance, documented score mapping) and label the readiness coefficients **not yet field-calibrated**. Results and limitations: [analysis/RESULTS.md](analysis/RESULTS.md).

---

## Repo layout
- `anki/` — engine + desktop fork
- `Anki-Android/`, `Anki-Android-Backend/` — phone forks
- `analysis/` — Python eval/AI/benchmark harness (`make …`)
- `data/` — AAMC outline, knowledge graph, gold set, generated eval artifacts
- `PRD.md`, `MVP.md`, `ARCHITECTURE.md`, `CODEBASE_MAP.md`, `REMAINING_WORK.md` — design docs
- `docs/` — Rust-change note, model one-pagers, sync doc, demo script
