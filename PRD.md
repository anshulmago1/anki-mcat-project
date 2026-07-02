# Readygauge — Product Requirements Document

**An MCAT readiness engine built on a fork of Anki.** A desktop app and an Android companion that share one Rust engine, measure memory, performance, and readiness as three separate evidence-backed numbers, and refuse to show a score they cannot defend.

> **Exam (stated up front, per the brief): the MCAT.** Scored 472–528, four sections each scored 118–132 (B/B, C/P, P/S, CARS). The whole app is built for one persona preparing for this one exam on its real scoring scale.

> **Mobile target:** Android via **AnkiDroid** (open source, AGPL-3.0), running the shared Anki Rust backend. iOS is out of scope for this build.

---

## 1. Summary

Readygauge forks Anki and turns it from a memory tool into a **readiness instrument** for the MCAT. Anki's FSRS already answers one question well — *can the student recall this fact right now?* Readygauge adds the two harder bridges the brief demands: from **memory** to **performance** (can the student answer a *new* passage-style question that uses the fact?) and from performance to **readiness** (what would the student score today, and how sure are we?).

The product is built on a single non-negotiable principle, taken directly from the Brainlift and the honesty rule in the brief:

> **No number is ever displayed without the evidence that produced it.** Every score, range, and recommendation carries its source: the reviews behind it, the coverage it assumes, how calibrated past guesses turned out, and the rule under which it gives up and shows nothing. A confident number with none of that behind it is a guess in a nice font, and this app does not ship guesses.

This is the **Spiky POV** from the Brainlift made into a product spec: current MCAT tools (Princeton Review, Kaplan, Blueprint, UWorld, Magoosh) all reduce readiness to *percent correct mapped to a score*, with no decay model, no coverage gate, no transfer measurement, and no uncertainty band. Readygauge treats learning as a **calibrated decision problem under uncertainty** and only makes a claim when the evidence justifies it.

What ships:

1. **A real Rust engine change** — a per-topic **mastery query** in `rslib`, fast enough to power the dashboard on 50,000 cards, exposed to Python and shipped to the AnkiDroid build because the engine is shared.
2. **Two apps, one engine** — forked desktop Anki + AnkiDroid companion that review the same deck and sync two-way.
3. **Three separate scores** — Memory (M), Performance (P), Readiness (E) — each with a range, each with its evidence, never blended into one number.
4. **An AI layer that is strictly additive** — source-grounded card generation and checking, evaluated on held-out data, beating a simpler baseline, and fully switchable off. The app gives a score with AI off.

---

## 2. Persona & the real problem

**Maya, 21** — a senior pre-med taking the MCAT in four months. She already lives in Anki (a 12,000-card MCAT deck) and grinds UWorld and AAMC FLs. She studies at a desk on weekends and on her phone between classes. Her problem is not *access to material* — it is **knowing if she is actually ready.**

Her dashboards lie to her in four specific ways the Brainlift documents:

- **Temporal blindness.** She crushed Biochem in month one; every tool still shows "Biochem: strong" today even though FSRS-style decay says her retrievability has dropped. (Ebbinghaus forgetting curve; Bjork & Bjork, 2011, storage vs. retrieval strength.)
- **Illusion of competence.** Her UWorld percentage climbs because she recognizes recycled questions, not because she can transfer the concept to a novel passage. (Karpicke & Roediger, 2008 — re-readers predicted ~80%, recalled ~40%.)
- **Coverage blindspot.** She has barely touched CARS and Psych/Social, but her overall estimate looks reassuring because tools score only what she's answered. (Derivita's coverage-adjusted readiness is the rare counter-example.)
- **False precision.** A "509" Blueprint FL is really 509 ± ~7, but it's shown as a single confident number with no band — while the AAMC's own reports use confidence bands (±1 section, ±2 total).

**The real problem Readygauge solves:** Maya cannot tell the difference between *feeling ready* and *being ready*, and no tool tells her **the single best next thing to study** based on learning science rather than raw percent correct. Readygauge separates memory from transfer, gates on coverage, attaches uncertainty to every claim, and surfaces the next-best action — and abstains, loudly, when it doesn't have the evidence.

This persona justifies every required feature: a huge fact base (FSRS memory), passage-style transfer (performance model), broad blueprint to cover (coverage gate), mobile review between classes (AnkiDroid + sync), and honest day-before-test confidence (calibrated readiness with a give-up rule).

---

## 3. The thesis: evidence behind every number (the core constraint)

This section is the contract for the whole app. It is the user's explicit requirement — *not a single number exists without evidence backing it up* — turned into an enforceable rule.

**Every displayed quantity is an `EvidencedValue`, never a bare float.** A score that cannot populate its evidence fields is not rendered; the give-up state is shown instead.

```ts
interface EvidencedValue {
  value: number;                 // the point estimate
  range: [number, number];       // likely range (never shown without this)
  confidence: 'low' | 'moderate' | 'high';
  evidence: {
    gradedReviews: number;       // reviews/questions that produced it
    coveragePct: number;         // % of AAMC outline topics covered
    calibration: { metric: 'Brier' | 'logloss'; value: number; asOf: string };
    drivers: string[];           // top human-readable reasons ("CARS coverage 31%")
    lastUpdated: string;         // ISO timestamp
    method: string;              // named formula/source, e.g. "FSRS-6 retrievability"
    source?: string;             // for AI outputs: the named source citation
  };
  abstained: boolean;            // true => show give-up message, not the value
}
```

**Provenance rules, enforced in code:**

- A **readiness** number renders only if all four abstention thresholds pass (§7). Otherwise `abstained = true` and the UI shows what's missing.
- An **AI-generated card or answer** renders only if `evidence.source` is a named, retrievable citation that passed the card check (§9). No source ⇒ the AI section scores zero per the brief.
- A **section score** is never invented; it is a sum/transform of measured per-topic signals with a stated method (§5–6).
- **Learning-science multipliers** (spacing, interleaving, testing) are applied only with their effect-size citation attached (§6.4), and only when their gating preconditions hold (e.g. interleaving requires prior knowledge — Bjork's "desirable difficulties are only desirable with sufficient background").

---

## 4. Scope

### In scope
- Fork of Anki building from source (desktop) + AnkiDroid build (Android), sharing the Rust backend.
- **Rust mastery query** in `rslib` returning per-topic mastered count, mean retrievability, and coverage fraction (§8), with ≥3 Rust unit tests + 1 Python-calling test, undo-safe and corruption-free.
- **Three-layer model** — Memory (FSRS retrievability), Performance (IRT transfer), Readiness (coverage-gated section→total mapping) — each an `EvidencedValue` with a range (§6).
- **Coverage map** against the AAMC content outline, displayed and used as a hard abstention gate (§7c).
- **Give-up rule** with named, coded thresholds (§7).
- **Two-way sync** desktop ↔ AnkiDroid with offline review and a documented conflict rule (§11–12).
- **AI layer:** source-grounded card generation + card checker + held-out eval + baseline comparison; fully toggleable off (§9).
- **One study-feature ablation** (interleaving) across three builds, pre-registered (§10).
- **Evaluation harness:** calibration (ECE, reliability diagram, Brier decomposition, log loss), performance accuracy/AUC vs. baselines, leakage check (§13).
- Desktop installer + signed Android APK that both run with AI off.

### Out of scope
- iOS build (Android only this cycle).
- Other exams (LSAT/GMAT/USMLE) — MCAT only.
- Bonus longitudinal validation against real students with both study history and FL scores (graded as bonus only; we honestly report we lack this data).
- Real-time (<1s) sync, E2E-encrypted sync, 100k-card stretch — listed as later ideas (§16).

### Brief-compliance gate map

| Brief requirement | How Readygauge meets it |
|---|---|
| Real change inside Anki's Rust code | Mastery query in `rslib` + new protobuf message + Python call (§8) |
| Two apps, one shared engine, syncing | Forked desktop Anki + AnkiDroid on the shared Rust backend (§11) |
| Three separate scores, each a range | M / P / E as `EvidencedValue` with ranges (§6) |
| Held-out, re-runnable evaluation | Temporal splits + one-command harness + leakage check (§13) |
| One study feature tested off/on | Interleaving three-build ablation, pre-registered (§10) |
| Every AI output sourced, checked, beats baseline | RAG with named sources + card checker + baseline comparison (§9) |
| Refuses to score without enough data | Coded abstention thresholds (§7) |
| Desktop installer + phone build, AI-off capable | Installer + signed APK; AI is additive and toggleable (§14–15) |
| License AGPL-3.0-or-later, credit Anki | Public AGPL fork, BSD-3 parts preserved, Anki credited (§14) |

---

## 5. The MCAT scoring model (the output space)

| Section | Scaled range | Midpoint | Questions | Time |
|---|---|---|---|---|
| Biological & Biochemical (B/B) | 118–132 | 125 | 59 | 95 min |
| Chemical & Physical (C/P) | 118–132 | 125 | 59 | 95 min |
| Psych/Social/Bio (P/S) | 118–132 | 125 | 59 | 95 min |
| Critical Analysis & Reasoning (CARS) | 118–132 | 125 | 53 | 90 min |
| **Total** | **472–528** | **500** | 230 | 375 min |

Raw counts are equated to 118–132 per section; the four sections sum to the total with no nonlinear total-level transform. The model therefore works **section-by-section, then sums** — matching how the MCAT is built — and CARS uses a separate ability estimate from the science sections (it is reading comprehension, not fact recall).

The AAMC reports official scores with **confidence bands (±1 section, ±2 total)**. Readygauge mirrors this: every section and total is shown as a band, widening when data is sparse and narrowing as evidence accumulates.

---

## 6. The three-layer model (formulas, each evidence-tagged)

The brief forbids blending memory, performance, and readiness into one number. Each layer is measured independently and displayed separately.

### 6.1 Memory — M (per topic, aggregated per section)

FSRS-6 power-law retrievability for topic *i*:

\[ R_i(t, S_i) = \left(1 + \text{factor}\cdot\frac{t}{S_i}\right)^{-w_{20}}, \quad \text{factor} = 0.9^{-1/w_{20}} - 1 \]

Section memory is the AAMC-topic-weighted mean of retrievability:

\[ M_s = \sum_{i \in s} w_i \cdot R_i(t, S_i) \]

- **Evidence attached:** number of graded reviews per topic, FSRS stability/difficulty, last-review recency. Method tag: `FSRS-6 retrievability`.
- **Calibration is required before display:** when M says 80%, ~80% of held-out reviews at that retrievability must succeed (§13.1). FSRS-6 benchmark anchors: log loss ≈ 0.344–0.345, RMSE(bins) ≈ 0.063–0.065, AUC ≈ 0.705–0.708 (~350M reviews).

### 6.2 Performance — P (per section, transfer not recall)

3-parameter logistic IRT for the probability the student answers a novel question *j* correctly given section ability θ_s:

\[ P(\text{correct}\mid\theta_s,a_j,b_j,c_j) = c_j + \frac{1-c_j}{1+e^{-a_j(\theta_s-b_j)}} \]

with guessing c_j ≈ 0.25 for 4-choice MCQs. Section performance:

\[ P_s = \frac{1}{n_s}\sum_{j=1}^{n_s} P(\text{correct}\mid\theta_s,a_j,b_j,c_j) \]

- **Why M ≠ P (transfer-appropriate processing, Morris/Bransford/Franks 1977):** card recall and novel-passage accuracy are measurably different. Pan & Rickard (2018) meta-analysis: retrieval-practice transfer d = 0.40, dropping to d = 0.28 when the final question is reworded. The **paraphrase gap (M_s − P_s)** is a first-class, displayed output (§7d), not hidden in an average.
- **Evidence attached:** held-out questions answered per section, IRT standard error SE(θ_s), the paraphrase gap. Method tag: `2PL/3PL IRT ability`.

### 6.3 Readiness — E (coverage-gated section → total)

Coverage for section *s* = fraction of AAMC content categories with ≥1 high-quality card **and** ≥1 exam-style question:

\[ C_s = \frac{|\{i\in s:\text{deck covers }i\}|}{|\{i\in s:i\in\text{AAMC outline}\}|} \]

Section readiness (logistic map to the 118–132 scale, coefficients fit on held-out practice data):

\[ \hat{E}_s = 118 + 14\cdot\sigma\!\big(\beta_0 + \beta_M\cdot M_s\cdot\alpha_{space}\,\alpha_{inter}\,\alpha_{test} + \beta_P\cdot P_s + \beta_C\cdot C_s\big) \]

Total = sum of four section estimates:

\[ \hat{E}_{total} = \sum_{s=1}^{4}\hat{E}_s \]

90% prediction interval by propagating per-layer variance (IRT standard error + coverage Dirichlet-multinomial + bootstrap of the regression coefficients):

\[ \hat{E}_{total} \pm z_{0.95}\sqrt{\sum_s \text{Var}(\hat{E}_s)} \]

- **Score-mapping evidence:** community regression (n≈98) shows AAMC FL1+FL2 average correlates with real MCAT at r ≈ 0.86; a 2020 peer-reviewed study found practice-exam performance predicts real MCAT at β = 0.74 (p < 0.001), with median practice score the single best predictor. The linear map \(\hat{\text{scaled}}_s = \beta_0 + \beta_1\bar{P}_s\) is fit on AAMC conversion tables; residuals give the ±3–4 scaled-point interval.

### 6.4 Learning-science multipliers (each with its effect size, each gated)

Applied to the **memory signal feeding readiness**, never as free parameters. Each renders its citation in the evidence panel.

| Multiplier | Range | Trigger | Evidence |
|---|---|---|---|
| α_space (spacing) | 1.0–1.4 | review timing vs. FSRS-optimal gap | Cepeda 2008: optimal gap up to +150% recall vs. massed; Dunlosky high-utility |
| α_inter (interleaving) | 1.0–1.3 | session mixes ≥2 topic categories **and** R_i > 0.4 for all (Bjork gate) | Bjork lab: blocked 20% → interleaved 63% transfer at 1 week; Taylor & Rohrer 2010 ~doubled math accuracy |
| α_test (testing effect) | 1.0–1.5 | active retrieval (no preview); **disabled** if median response < 2s | Dunlosky 2013 high-utility, d ≈ 0.55–0.60 over restudy |

\[ \alpha_{space,i} = 1 + 0.4\cdot\text{clamp}\!\big(\tfrac{t_{actual}}{t_{optimal}}-1,\,-0.5,\,0.5\big) \]
\[ \alpha_{inter} = 1 + 0.3\cdot\mathbb{1}[\text{mixes}\ge2\text{ topics, all }R_i>0.4] \]
\[ \alpha_{test} = 1 + 0.5\cdot\mathbb{1}[\text{active retrieval, median RT}\ge2s] \]

**Anti-gaming (the "taps Good without reading" attacker):** sessions with median response < 2s/card are flagged; α_test reverts to 1.0; a large M_s−P_s gap with high review counts triggers a "verify your reviews" warning. FSRS sees memory behavior, not intent — so the app cross-checks behavior against transfer.

---

## 7. The give-up rule (abstention, coded as named constants)

Abstention is a formal selective-prediction decision, not UX polish: a falsely confident 510 when the student is really at 495 is more harmful than "insufficient data." **Readiness renders only if all four hold per section; otherwise the give-up state shows what's missing.**

| Constant | Threshold | Rationale |
|---|---|---|
| `MIN_GRADED_REVIEWS` | ≥ 200 / section | IRT θ needs ~100–200 items for a stable estimate |
| `MIN_COVERAGE` | ≥ 50% of AAMC categories / section | sub-50% means whole subsections untested |
| `MAX_IRT_SE` | SE(θ_s) ≤ 0.5 | above this the 90% CI spans >14 scaled points — uninformative |
| `MIN_REVIEW_RECENCY` | ≥ 50% of due reviews done within 2× interval | stale stability undercounts forgetting |

Give-up display example:

> ⛔ **Readiness unavailable.** You need 200+ graded reviews in CARS (you have 43) and ≥50% coverage of P/S (currently 38%). Next best step: 20 CARS passages on [topic].

### 7c. Coverage map
List every AAMC outline topic; mark which the deck covers; show % per section on the dashboard. A 10,000-card deck that skips a high-weight section must **not** show "ready." Below `MIN_COVERAGE`, the section abstains.

### 7d. Paraphrase test
For 30 cards, author 2 exam-style reworded questions each. Compare card recall vs. reworded accuracy. If the two are basically equal, the performance model is just echoing memory — report the gap explicitly. This is the proof that P measures transfer, not recall.

---

## 8. The Rust change — mastery query (graded 20%)

The brownfield requirement: change the Rust engine, not just the Python screens. Anchor change = **mastery query** in `rslib`, chosen because it powers the dashboard and must run on 50,000 cards within budget — aggregation that belongs in the compiled backend, not Python iteration.

### 8.1 Backend call
```rust
// rslib/src/stats/ (new module)
pub struct TopicMasteryStats {
    pub topic_id: String,
    pub mastered_count: u32,      // cards with R_i > MASTERY_THRESHOLD
    pub mean_retrievability: f32, // weighted mean R_i across topic cards
    pub coverage_fraction: f32,   // covered AAMC categories / total in section
    pub graded_reviews: u32,      // evidence count behind the numbers
}
```
Powers M_s (mean_retrievability), C_s (coverage_fraction), and the abstention check (graded_reviews + coverage), and returns the evidence counts so the dashboard never shows a bare number.

### 8.2 Points-at-stake ordering (secondary, reuses the same aggregation)
Sort due cards by `w_i · (1 − R_i)` (topic weight × forgetting risk) so the highest-readiness-value cards surface first — operationalizing β_M. New protobuf message:
```protobuf
// proto/anki/scheduler.proto
message PointsAtStakeQueueConfig {
  map<string, float> topic_weights = 1;
  float min_retrievability_threshold = 2;
}
```

### 8.3 Required proof (per brief 7a)
- ≥ 3 Rust unit tests + 1 test calling the query from Python.
- Undo still works; no collection corruption (run the 20× crash test, §13.4).
- One-page note on why this belongs in Rust (50k-card aggregation under the dashboard latency budget).
- List of upstream `rslib`/`proto` files touched and merge-difficulty assessment.
- Because the engine is shared, the change ships to AnkiDroid too — verify on the Android build.

---

## 9. The AI layer (additive, sourced, evaluated, off-switchable)

No AI before Friday. The Wednesday build has zero model calls. AI is strictly additive — the app gives a full score with AI off.

### 9.1 Source-grounded card generation (RAG)
Generate cards from one real source (textbook chapter / AAMC outline section) with **named source citations** carried into `EvidencedValue.source`. No source ⇒ not shown (AI section scores zero per brief).

### 9.2 Card checker + gold set (brief 7f)
- Gold set: 50 Q/A pairs from trusted MCAT/AAMC materials with known answers.
- Generate 50 cards from one source; classify each: **correct & useful**, **wrong** (auto-blocked — a wrong fact is worse than no card), **correct but poor teaching** (vague/trivial/duplicate).
- Pre-set cutoff **before** looking: ≥ 80% correct & useful, **0% wrong**. Cards failing the checker are blocked.
- Prompt-injection defense: strip/ignore hidden text in source files (the "trick the generator" attacker).

### 9.3 Eval before exposure + baseline (brief Friday)
- Held-out accuracy + wrong-answer rate with a stated cutoff, run **before** students see anything.
- Beat a simpler method: **Baseline A** keyword retrieval (predict correct iff R_i > 0.7); **Baseline B** vector similarity (nearest-card retrievability). The IRT-θ performance model must beat both on the held-out set.

### 9.4 Offline / failure behavior
AI offline, rate-limited, or returning broken output ⇒ AI features disable cleanly, both apps keep working and still give a score (§13.4).

---

## 10. The study-feature ablation — interleaving (graded 15%)

**Pre-registered hypothesis:** *"Topic-interleaved review (mixing ≥2 MCAT topic categories per session, prioritizing weak high-weight topics) will produce ≥5 percentage points higher accuracy on mixed-topic, passage-style held-out questions than blocked review at equal study time."*

Three builds, same learners, same questions, same time budget:

| Build | Config | Isolates |
|---|---|---|
| V1 — Full app | interleaving ON, spacing ON, testing ON | the complete model |
| V2 — Feature off | α_inter = 1.0, blocked practice | the interleaving contribution |
| V3 — Plain Anki | FSRS + standard review, no scoring model | the obvious baseline |

- Primary metric: accuracy on 60 held-out mixed-topic questions (20/section), stated ahead of time.
- Secondary: weighted coverage, session completion rate. Report means ± SD for all three.
- V1 vs V2 isolates interleaving; V1 vs V3 shows the whole app beats baseline. **Null results are reported honestly** — "interleaving made no difference in CARS here" is a valid, well-scoring result. "Feels better" scores nothing.

---

## 11. Two apps, one engine + sync (graded 10%)

Desktop is the main tool; AnkiDroid is the companion. They share the **same cards, progress, and Rust engine**, and sync. Rewriting the scheduler in Java/Kotlin instead of sharing Rust does **not** count.

- **Android:** build on **AnkiDroid** (AGPL), running Anki's Rust backend on-device; the §8 Rust change ships here automatically.
- **Sync:** use Anki's existing sync or a custom layer; reviews must flow both ways with none lost or double-counted.
- Companion must: run real review sessions on the shared deck, sync both ways, work offline then sync on reconnect, and show the same three scores with ranges under the same give-up rule.

### 11a. Sync test (brief 7b)
Review 10 cards offline on phone, 10 different on desktop, reconnect → all 20 land once, none lost/duplicated. Then review the **same** card on both offline, sync, and show the conflict rule picks a clear, correct, **documented** winner (e.g. latest-review-timestamp wins; tie-break by device id). Handle a phone that goes offline mid-sync or has a wrong clock.

---

## 12. Data model

```ts
// AAMC content outline — the coverage backbone
interface AamcTopic {
  id: string;                    // stable category id
  section: 'BB' | 'CP' | 'PS' | 'CARS';
  weight: number;                // w_i, AAMC-derived, section weights sum to 1
  label: string;
}

// Per-topic mastery (mirrors the Rust TopicMasteryStats)
interface TopicMastery {
  topicId: string;
  masteredCount: number;
  meanRetrievability: number;    // R_i
  coverageFraction: number;      // C contribution
  gradedReviews: number;         // evidence count
  lastReviewedAt: string;
}

// Performance evidence per section
interface SectionPerformance {
  section: string;
  thetaHat: number;              // IRT ability
  thetaSE: number;               // standard error -> abstention + CI
  questionsAnswered: number;
  paraphraseGap: number;         // M_s - P_s
}

// What the dashboard renders — all three layers, all evidenced
interface ReadinessReport {
  memory: Record<string, EvidencedValue>;    // per section
  performance: Record<string, EvidencedValue>;
  readiness: { sections: Record<string, EvidencedValue>; total: EvidencedValue };
  coverage: Record<string, number>;
  nextBestAction: { topicId: string; reason: string; pointsAtStake: number };
  abstained: boolean;
}
```

Cards are tagged to `AamcTopic.id` (topic-to-card mapping is a Wednesday deliverable). User study/review data syncs via the shared engine; the AAMC outline ships in-repo.

---

## 13. Evaluation framework (graded: 20% accuracy/honesty + 12% re-runnable tests)

A single command (e.g. `make bench` / `make eval`) reproduces every number. Temporal splits everywhere (train on earlier reviews/questions, test on later) — never random — to avoid leaking the future.

### 13.1 Memory calibration (required)
Reliability diagram + **ECE**, **Brier score with REL/RES/UNC decomposition**, and **log loss** on held-out reviews per section. Beat the naive constant-p baseline on Brier and log loss. Report all three Brier terms — good BS with bad REL is miscalibration that scored right by luck.

\[ ECE = \sum_m \tfrac{|B_m|}{N}\,|\text{acc}(B_m)-\text{conf}(B_m)|, \qquad BS = REL - RES + UNC \]

### 13.2 Performance model (required)
Held-out accuracy, **AUC-ROC > 0.65** vs. naive, Brier lower than constant-p, wrong-answer rate reported at the chosen cutoff (≤ 20%). Beat Baseline A (keyword) and Baseline B (vector) (§9.3).

### 13.3 Leakage check (brief 7e — leaked data zeroes the score)
A script run **before** any training/eval, on: (a) generated cards vs. test bank, (b) train bank vs. test bank, (c) card fronts/backs vs. all test items. TF-IDF (1–3 gram) cosine; any test item with max similarity > 0.8 to a train item is removed. Report "X of Y test items removed"; if X > 5%, raise a data-quality warning.

### 13.4 Crash / offline / benchmark (brief 7g, 7h)
- Kill each app mid-review **20×** → zero corrupted collections, both platforms.
- Pull the network → AI disables cleanly, both apps keep working and still score.
- `make bench` on the shared 50,000-card deck prints **p50 / p95 / worst** for each action below — no cherry-picked single numbers.

### 13.5 What we grade (and what we honestly don't)
Per the brief, we grade the **steps of the bridge**, not a fabricated final score: (1) memory calibrated, (2) held-out performance prediction, (3) documented score mapping with a range. Real-student longitudinal validation is bonus — and we state plainly: *"We calibrated memory and validated performance on held-out questions; we do not yet have the longitudinal data to prove the projected score is right."* That honesty scores higher than a polished number we can't back.

---

## 14. Performance & reliability targets

Measured on the shared deck; report p50 / p95 / worst.

| Action | Target |
|---|---|
| Button press acknowledged | p95 < 50 ms (desktop + phone) |
| Next card after grading | p95 < 100 ms |
| Dashboard first load | p95 < 1 s |
| Dashboard refresh | p95 < 500 ms, no UI freeze |
| Sync of a normal session | < 5 s on a normal connection |
| Cold start | < 5 s desktop, < 4 s phone |
| Memory on 50k cards | under a stated limit, desktop + mid-range phone |
| Crash test | zero corrupted collections, both platforms |

**Adversarial cases we must survive (from the brief):** card-wording memorizer who fails reworded questions; huge deck skipping a high-weight topic; two cards stating opposite facts; prompt-injection in a source; "Good" tapper; topic with almost no history; accurate-but-too-slow student; correct-but-useless AI cards; leaked test data; AI offline/rate-limited; same card reviewed on two offline devices; phone offline mid-sync or with a wrong clock; crash mid-review; corrupt/50k/broken-image decks.

---

## 15. Deliverable timeline (build the apps, add AI, then prove it)

### Wednesday — core works on both screens, **no AI**
- Anki forked, building from source; Rust mastery query end-to-end (diff + 3 Rust tests + 1 Python test).
- Review loop on the MCAT deck; topic-to-card AAMC tagging.
- Memory model (M_s) displayed as an `EvidencedValue` with range + give-up rule enforced.
- Memory calibration script + leakage script written and passing on simulated reviews.
- Desktop installer runs on a clean machine; AnkiDroid build loads the deck and runs a real review session on the shared engine (two-way sync not required yet).
- **Proof:** commit hash, clean-build recording, test results, clean-install recording, phone review recording.

### Friday — AI added & checked; phone syncs
- IRT model fit; θ_s per section; P_s from held-out questions; α_space/α_inter/α_test toggleable.
- AI card generation + checker + gold set; held-out eval + baseline comparison; ECE/Brier dashboards live.
- Two-way sync working (offline → reconnect, no loss/dupes); phone shows three scores with ranges + give-up rule.
- App still scores with AI off.
- **Proof:** eval + baseline numbers; phone→desktop sync recording.

### Sunday — prove it, ship both
- Three-build interleaving ablation with results table; Brier decomposition + reliability diagram in the report; CI for E_total shipped; no score under abstention.
- Final leakage check on the real split logged in README.
- Packaged desktop installer + signed APK; documented sync conflict handling; both run AI-off.
- **Proof:** results report, model descriptions (one page each: memory, performance, readiness + give-up rule), Brainlift, clean-device install/run recordings.

### Handover (due Sunday 10:59 PM CT)
Public **AGPL-3.0-or-later** fork crediting Anki (BSD-3 parts preserved), exam stated up front, build instructions for both apps, architecture overview, the Rust-change note + touched-files list, a 3–5 min demo video (review session, Rust change in action, phone→desktop sync, three scores with ranges, AI features, test results), the three model descriptions, and the Brainlift.

---

## 16. Grading alignment & later ideas

| Area | Weight | Where addressed |
|---|---|---|
| Rust change fitting Anki | 20% | §8 |
| Score accuracy & honest uncertainty | 20% | §3, §6, §13 |
| Study feature on learning science | 15% | §10 |
| AI checking & safety | 15% | §9 |
| Fair, re-runnable tests | 12% | §13 |
| Shared engine + working sync | 10% | §11 |
| Useful product & clean UX | 8% | §3 evidence UI, dashboard |

**Hard limits respected:** real Rust change (else 50% cap), phone companion sharing engine + sync (else 70% cap), re-runnable tests (else 60% cap), held-out testing (else 60% cap), no made-up readiness numbers (else auto-fail), both apps run on clean devices (else 50% cap), no leaked test data (else zero), AI sources traceable (else AI section zero).

**Later (only if the core is solid):** real-time sync, conflict-free merge, 100k-card scaling with profiling, notarized macOS/Windows/Linux installers, upstreaming a change to Anki/AnkiDroid, a study-planning knowledge graph proven to beat keyword/vector search with real numbers.

---

## 17. Acceptance criteria

1. Desktop and AnkiDroid review the **same deck on the shared Rust engine**; the §8 mastery query runs on both.
2. The dashboard shows **three separate scores** (memory, performance, readiness), each with a range and its evidence; **no bare numbers anywhere**.
3. With coverage or review counts below threshold, readiness **abstains** and names exactly what's missing plus the next-best action.
4. The **paraphrase gap (M−P)** is shown, proving performance ≠ memory.
5. Two-way sync: 10 offline reviews per device merge to 20 with none lost/duplicated; same-card conflict resolves by the documented rule.
6. Memory model is **calibrated** (reliability diagram + Brier/log loss on held-out reviews, beating constant-p); performance beats keyword and vector baselines on held-out questions.
7. The leakage check runs clean and is logged; any contamination is removed and reported.
8. **AI off everywhere** and the app still produces all three scores; AI on, every generated card carries a named source and passed the checker.
9. The interleaving ablation runs across V1/V2/V3 at equal study time with a pre-registered metric, reporting the result honestly — including a null.
10. Both apps install and run on **clean devices**; `make bench` prints p50/p95/worst within the §14 targets.

---

*Product working name: **Readygauge**. Rename freely. One exam (MCAT), two apps on one Rust engine, a real engine change, and three scores — none of them shown without the evidence behind them.*
