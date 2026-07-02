# Readygauge — MVP Definition

*The smallest version of [PRD.md](PRD.md) that delivers real value to Maya and clears every hard grading gate in the brief. If a feature isn't on this page, it is post-MVP.*

---

## 1. MVP in one sentence

**Maya reviews her MCAT deck on desktop and Android (one shared Rust engine, syncing), and sees three separate, evidence-backed numbers — Memory, Performance, Readiness — where Readiness refuses to appear until it has the data to defend it.**

That sentence is the entire MVP. Everything below either makes it true or is explicitly cut.

---

## 2. Who it's for (unchanged from the PRD)

**Maya, 21, senior pre-med, MCAT in ~4 months, 12,000-card Anki deck.** She can't tell *feeling ready* from *being ready*, and no tool tells her the single best next thing to study with evidence behind it. The MVP exists to give her one honest readiness picture and one honest next step.

---

## 3. The one golden path (the MVP demo)

This is the single flow that must work end to end. The 3–5 minute demo video is this path.

```
Maya opens desktop Readygauge
  -> reviews ~20 cards on her MCAT deck (FSRS scheduling)
  -> opens the Dashboard
       -> Memory: 0.78 (range, evidence: 412 reviews)
       -> Performance: shown with paraphrase gap
       -> Readiness: ABSTAINS -> "No CARS score: 38% coverage, 43/200 reviews.
                                   Next best: 20 CARS passages on [topic]."
  -> picks up her phone (AnkiDroid build, same deck)
  -> reviews 10 cards offline on the train
  -> reconnects -> reviews sync to desktop, none lost or doubled
  -> desktop dashboard updates with the new evidence
```

If that path runs on clean devices with AI switched off, the MVP exists.

---

## 4. MVP user stories (must-have)

- *As Maya, I review the same deck on my laptop and my phone and my progress is the same in both* — shared engine + sync.
- *As Maya, I see my Memory score with the number of reviews behind it, not just a percentage* — evidenced memory.
- *As Maya, when the app doesn't have enough data, it tells me so and tells me what to study next* — give-up rule + next-best action.
- *As Maya, I can see that remembering a card is not the same as answering a reworded question* — the paraphrase gap.
- *As Maya, I trust the Memory number because the app can show it was right ~80% of the time when it said 80%* — calibration.

Each maps to a PRD section: shared engine §11, evidenced memory §3/§6.1, give-up §7, paraphrase §7d, calibration §13.1.

---

## 5. What's IN the MVP

Scoped to clear the brief's hard caps (real Rust change, phone+sync, held-out tests, no fabricated numbers, clean-device install) and deliver the golden path.

### 5.1 Engine (the non-negotiable core)
- Anki **forked and building from source** (desktop).
- **Rust mastery query** in `rslib` returning per-topic `mastered_count`, `mean_retrievability`, `coverage_fraction`, `graded_reviews` (PRD §8.1).
- ≥ 3 Rust unit tests + 1 Python-calling test; undo works; no corruption.
- AAMC topic → card tagging so the query has topics to aggregate.

### 5.2 Two apps + sync
- **AnkiDroid build** running the shared Rust backend (the §8 change ships to it).
- Both apps load and review the MCAT deck on the shared engine.
- **Two-way sync** with offline review → reconnect, no loss/duplication, and **one documented conflict rule** (latest-review-timestamp wins, tie-break by device id).

### 5.3 The three scores (each an `EvidencedValue`, never bare)
- **Memory (M_s):** FSRS-6 retrievability, weighted by AAMC topic weight, shown with range + review count.
- **Performance (P_s):** IRT-based transfer estimate on held-out exam-style questions, with the **paraphrase gap (M−P)** displayed.
- **Readiness (E_s, E_total):** coverage-gated section→total map with a range; **abstains** under the give-up thresholds (PRD §7).
- **Coverage map** + **next-best action** (points-at-stake: `w_i·(1−R_i)`).

### 5.4 Honesty / evaluation (required to avoid auto-fail and 60% caps)
- **Give-up rule** as coded constants (200 reviews/section, 50% coverage, SE(θ)≤0.5, recency) — PRD §7.
- **Memory calibration**: reliability diagram + Brier/log loss on held-out reviews, beating constant-p.
- **Leakage check** script, run and logged clean (PRD §13.3).
- **One re-runnable command** that reproduces the eval numbers.

### 5.5 Packaging
- Desktop installer that runs on a clean machine.
- Signed Android APK that runs on a clean device.
- **Both run with AI off** and still produce all three scores.

---

## 6. What's explicitly OUT of the MVP (deferred)

These are real PRD features intentionally cut from the first viable slice. Cutting them does not breach any hard gate.

| Deferred | Why it can wait |
|---|---|
| **AI card generation + RAG + checker** | AI is additive; the brief allows (and requires) the app to score with AI off. Lands Friday, not in the core MVP. |
| **Full learning-science multipliers** (α_space/α_inter/α_test live in readiness) | MVP can ship readiness with multipliers = 1.0 and add them as the ablation work; the formula already supports it. |
| **Interleaving three-build ablation** | Depends on the study feature being toggleable; it's the Sunday "prove it" work, not the core loop. |
| **iOS** | Out of scope entirely this cycle. |
| **Performance/readiness regression coefficients fit on real student data** | MVP uses the documented AAMC-conversion-table mapping with honest "not yet longitudinally validated" labeling (PRD §13.5). |
| **Real-time sync, E2E encryption, 100k cards, notarized multi-OS installers** | PRD §16 "later ideas." |
| **Full AAMC outline ingestion (all ~600 categories)** | MVP ships a representative tagged subset sufficient to demonstrate coverage + abstention; full ingestion is a fast-follow. |

---

## 7. The single biggest risk (do this first)

Per the brief's "Get Anki Building First": the MVP's hard part is **not** the scores — it's getting Anki to compile from source, making one tiny Rust change appear in the desktop app, and getting the **same engine running on Android with sync**. If the shared-engine + sync spine isn't proven by mid-week, nothing else matters.

**De-risking order:** (1) Anki builds + trivial Rust change visible in desktop → (2) AnkiDroid builds with the shared backend → (3) sync a single card phone↔desktop → *then* (4) the mastery query → (5) the three scores → (6) calibration/leakage. Score UI work does not start until the engine spine is green.

---

## 8. Definition of Done (MVP acceptance)

The MVP is done when all of these are demonstrably true on clean devices:

1. Desktop and AnkiDroid review the **same deck on the shared Rust engine**; the mastery query runs on both.
2. The dashboard shows **three separate scores**, each with a range and its evidence — **no bare numbers anywhere**.
3. Readiness **abstains** when below threshold and names what's missing + the next-best action.
4. The **paraphrase gap** is visible (performance ≠ memory).
5. 10 offline reviews per device sync to 20 with none lost/duplicated; a same-card conflict resolves by the documented rule.
6. Memory is **calibrated** (reliability diagram + Brier/log loss beating constant-p on held-out reviews).
7. The **leakage check** runs clean and is logged.
8. **AI is off** and the app still produces all three scores.
9. Desktop installer + signed APK **install and run on clean devices**.
10. The Rust change has **≥3 Rust tests + 1 Python test**, undo works, and no collection corruption.

Items 1, 5, 9, 10 are the hard-gate items — they are not negotiable for an MVP that grades above the caps.

---

*MVP = the golden path (§3) running on the engine spine (§5.1–5.2), surfacing three honest numbers (§5.3) with the give-up rule and calibration (§5.4), AI off. Everything else is the post-MVP roadmap in the PRD.*
