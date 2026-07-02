# Speedrun Readiness Model: Learning Science Variables, Composite Formula, and Evaluation Framework

## Executive Summary

This report constructs a principled, formula-based readiness model for Speedrun targeting the MCAT. The model treats exam readiness as a weighted product of three independently measurable signals — memory (via FSRS retrievability), performance transfer (via IRT-based question accuracy), and coverage (topic breadth) — each modulated by learning-science variables drawn from Bjork's desirable difficulties framework and Dunlosky's utility hierarchy. Every component is assigned a quantifiable role, a measurement method, an evaluation metric, and a hard abstention threshold. The evaluation section is expanded to full rigor: calibration, Brier decomposition, leakage detection, and the three-build ablation design required by the assignment.

***

## Part I — The Score Architecture

### 1.1 Why Three Separate Signals

The assignment explicitly prohibits blending memory, performance, and readiness into a single number. This maps cleanly onto a three-layer psychometric model that cognitive science supports independently:[1]

- **Memory (M):** Probability that a trained fact is accessible right now, modeled via FSRS retrievability R.[2][3]
- **Performance (P):** Probability that a student correctly answers a new, exam-style question that *uses* that fact — transfer, not recall.[4][5]
- **Readiness (E):** A projected MCAT total score on the 472–528 scale, derived from per-section performance estimates weighted by exam structure.[6][7]

The distinction between M and P is empirically validated by the paraphrase test: Pan & Rickard (2018) meta-analysis found a grand weighted effect size of d = 0.40 for retrieval-practice transfer, but crucially, when response congruency is absent (i.e., the final question is reworded), the effect drops to d = 0.28 — confirming that card recall and novel-question accuracy are measurably different. Your performance model must capture that gap, not assume it away.[4]

### 1.2 The MCAT Scoring System

The MCAT produces five scores: one per section and one total:[6]

| Section | Score Range | Midpoint | Question Count | Time |
|---|---|---|---|---|
| Biological & Biochemical Foundations (B/B) | 118–132 | 125 | 59 | 95 min |
| Chemical & Physical Foundations (C/P) | 118–132 | 125 | 59 | 95 min |
| Psych/Social/Bio Foundations (P/S) | 118–132 | 125 | 59 | 95 min |
| Critical Analysis & Reasoning (CARS) | 118–132 | 125 | 53 | 90 min |
| **Total** | **472–528** | **500** | 230 | 375 min |

Raw scores (count correct) are scaled to 118–132 per section; the four section scores sum directly to the total. There is no penalty for wrong answers. This means your readiness model can work section-by-section and then sum — no nonlinear transformation needed at the total level.[8]

***

## Part II — The Formula

### 2.1 Variable Definitions

Let the following variables be defined for a student at time t across topic i:

| Symbol | Name | Range | Source |
|---|---|---|---|
| R_i | FSRS Retrievability for topic i | [1] | Anki FSRS engine[9][3] |
| S_i | FSRS Stability for topic i (days) | [0, ∞) | Anki FSRS engine[9] |
| D_i | FSRS Difficulty for topic i | [1][10] | Anki FSRS engine[9] |
| θ_s | IRT ability estimate, section s | logit scale | 2PL/3PL model[11][12] |
| b_j | IRT difficulty of question j | logit scale | Calibrated on question bank[11] |
| a_j | IRT discrimination of question j | [0, ∞) | Calibrated on question bank[11] |
| c_j | 3PL guessing parameter (MCAT MCQ) | [0, 0.25] | Calibrated on question bank[11] |
| w_i | Topic weight from AAMC outline | [1], sums to 1 | AAMC content outline[13][14] |
| α_space | Spacing bonus multiplier | [1, 1.4] | Cepeda 2008 empirical curve[15] |
| α_inter | Interleaving multiplier | [1, 1.3] | Bjork lab meta-analysis[16] |
| α_test | Testing effect multiplier | [1, 1.5] | Dunlosky high utility[5][17] |
| C_s | Coverage fraction for section s | [1] | Topic map vs AAMC outline[14] |

### 2.2 Memory Score M_i (per topic)

FSRS-6 defines retrievability as a power-law forgetting curve:[9][3]

\[ R_i(t, S_i) = \left(1 + \text{factor} \cdot \frac{t}{S_i}\right)^{-w_{20}} \]

where factor \(= 0.9^{-1/w_{20}} - 1\) to ensure \(R(S_i, S_i) = 0.90\), and w_{20} is a trainable user-specific parameter (default ≈ 0.2). Stability S_i after a successful review grows as:[9]

\[ S'_i = S_i \cdot e^{w_8 \cdot (11 - D_i) \cdot S_i^{-w_9} \cdot (e^{w_{10}(1-R_i)} - 1)} \]

This formalizes three desirable-difficulty insights: (1) harder items (high D) stabilize more slowly, (2) memory already well-consolidated (high S) is harder to strengthen further, and (3) reviewing near the forgetting threshold (low R) produces the largest stability gains — the core principle Bjork calls "new theory of disuse".[16][3]

The **aggregate memory score** for section s is:

\[ M_s = \sum_{i \in s} w_i \cdot R_i(t, S_i) \]

where w_i is AAMC-derived topic weight.

### 2.3 Performance Score P_s (per section)

The performance score bridges memory to novel-question success using Item Response Theory. For a student with estimated ability θ_s, the 3-parameter logistic model predicts probability of correct response on question j as:[11]

\[ P(correct | \theta_s, a_j, b_j, c_j) = c_j + \frac{1 - c_j}{1 + e^{-a_j(\theta_s - b_j)}} \]

The guessing parameter c_j ≈ 0.25 for a 4-choice MCQ, which is appropriate for the MCAT's discrete-answer sections. CARS questions require a separate reading comprehension model and should not share θ with the science sections.[11]

**Ability θ_s is estimated** from the student's history of question-bank performance using maximum likelihood estimation or, for online updating, an online IRT approach. Section-level ability estimates feed directly into the readiness projection.[18]

The performance score for section s across n_s held-out questions is:

\[ P_s = \frac{1}{n_s} \sum_{j=1}^{n_s} P(correct | \theta_s, a_j, b_j, c_j) \]

### 2.4 Learning-Science Multipliers

Three desirable-difficulty manipulations modulate the effective study signal fed into both M and θ updates. These are not arbitrary weights — each has empirical effect sizes from controlled experiments:[19][5][17]

**α_space (Spacing Multiplier)**
Cepeda et al. (2008) showed that the optimal inter-study gap is approximately 10–20% of the test delay for short intervals and 5–10% for long intervals. Cards reviewed on the FSRS-optimal schedule implicitly respect this. The multiplier reflects how well the actual review history matches the optimal spacing profile:[20][15]

\[ \alpha_{space,i} = 1 + 0.4 \cdot \text{clamp}\!\left(\frac{t_{actual}}{t_{optimal}} - 1,\ -0.5,\ 0.5\right) \]

An optimal gap improved final recall by up to 150% over massed practice in Cepeda's studies. Practically, this means a card reviewed exactly on its FSRS due date earns α_space = 1.0; reviewed optimally early or with a gap matching test delay gets up to 1.4.[21]

**α_inter (Interleaving Multiplier)**
Bjork lab research shows interleaving vs. blocking yields differential effects depending on whether the goal is inductive or factual learning. For MCAT, where questions mix topics within passages, the interleaving benefit is strongest for inductive discrimination (e.g., distinguishing enzyme kinetics from thermodynamics in the same passage). The effect applies when ≥2 distinct topics are mixed per study session:[16]

\[ \alpha_{inter} = 1 + 0.3 \cdot \mathbb{1}[\text{session mixes} \geq 2\ \text{topic categories}] \]

A controlled study from the Bjork lab found interleaving raised accuracy on transfer tests from 20% to 63% (a 43-point gain) compared to blocked practice one week later.[22]

**α_test (Testing Effect Multiplier)**
Dunlosky et al. (2013) rated practice testing and distributed practice as the only "high utility" techniques out of ten evaluated, with effects generalizing across formats, age groups, subject areas, and retention intervals. The testing multiplier is engaged whenever a card is answered under test conditions (no preview) rather than passively restudied:[5][17]

\[ \alpha_{test} = 1 + 0.5 \cdot \mathbb{1}[\text{active retrieval mode}] \]

The multiplier is zero for re-read, passive review, or immediate post-learning re-exposure — which have near-zero marginal benefit once learned.[17]

### 2.5 Coverage-Adjusted Readiness Formula

The MCAT has 10 foundational concepts across ~600+ content categories in the AAMC outline. Coverage C_s for section s is the fraction of official AAMC content categories with ≥1 card in the deck:[13][14]

\[ C_s = \frac{|\{i \in s : \text{deck covers topic } i\}|}{|\{i \in s : i \in \text{AAMC outline}\}|} \]

The full readiness formula for a single section score estimate is:

\[ \hat{E}_s = 118 + 14 \cdot \sigma\!\left(\beta_0 + \beta_M \cdot M_s \cdot \alpha_{space} \cdot \alpha_{inter} \cdot \alpha_{test} + \beta_P \cdot P_s + \beta_C \cdot C_s\right) \]

where σ is the logistic function mapping the linear combination to, and the coefficients {β_0, β_M, β_P, β_C} are fit via logistic regression on held-out practice-test performance data. The section range  is linearly rescaled onto  before transformation.[23][24][25][1]

The **total projected MCAT** is simply:

\[ \hat{E}_{total} = \sum_{s=1}^{4} \hat{E}_s \]

This is honest because it is a sum of four section models, each with its own uncertainty, exactly matching how the MCAT itself is constructed.[7]

### 2.6 Confidence Interval and Display

The readiness estimate must be displayed with a range, not a point estimate alone. A 90% prediction interval is formed by propagating uncertainty through each layer:[1]

\[ \hat{E}_{total} \pm z_{0.95} \cdot \sqrt{\text{Var}(\hat{E}_{B/B}) + \text{Var}(\hat{E}_{C/P}) + \text{Var}(\hat{E}_{P/S}) + \text{Var}(\hat{E}_{CARS})} \]

Section variance is estimated from:
1. IRT standard error: \(SE(\theta_s) = 1 / \sqrt{I(\theta_s)}\), where I(θ) is the test information function[11]
2. Coverage uncertainty: a Dirichlet-multinomial model over topic coverage fractions
3. Bootstrap variance of regression coefficients from the held-out calibration set

A practical display example:
> **Projected MCAT: 508**
> Likely range: 503–513
> Confidence: moderate — 62% of content categories covered, 287 graded reviews logged.

***

## Part III — The Abstention Rule

### 3.1 Theoretical Basis

The assignment's "give-up rule" is not a UX decision — it is a formal abstention condition grounded in selective prediction theory. A model should abstain when the expected cost of a wrong prediction exceeds the cost of withholding. For exam readiness, a falsely confident score (showing 510 when the student is genuinely at 495 due to insufficient data) is meaningfully more harmful than displaying "insufficient data."[26][27]

### 3.2 Recommended Thresholds

Write these into code as named constants:

| Condition | Threshold | Rationale |
|---|---|---|
| Minimum graded reviews | ≥ 200 per section | IRT ability estimates require ≥100–200 items for stable θ estimates[28] |
| Minimum topic coverage | ≥ 50% of AAMC categories for each section | Sub-50% coverage means entire subsections may be untested |
| Minimum IRT standard error | SE(θ_s) ≤ 0.5 | Above this, the 90% CI spans >14 scaled points — uninformative |
| Minimum review recency | ≥ 50% of due reviews completed within 2× the recommended interval | Stale stability estimates undercount forgetting |

The Mendelacademy readiness model (analogous to USMLE Step 1 QBanks) requires 150–200 items for a first estimate and >600 for a stable prediction with narrow CI. Their UX mirrors the spec exactly: `FMGE Readiness: 150 ± 20 → volatile, needs more data`.[28]

When any threshold is unmet, the app shows:
> ⛔ **Readiness unavailable.** You need 200+ graded reviews in CARS (you have 43) and ≥50% coverage of P/S (currently 38%). See below for what to study next.

***

## Part IV — The Learning Science Variables as Modulators

### 4.1 Hierarchy of Evidence

Based on Dunlosky et al.'s (2013) utility ratings, the learning-science variables in this model are assigned weights proportional to their effect-size evidence:[29][5][17]

| Technique | Dunlosky Utility | Effect in Model | Typical d or Improvement |
|---|---|---|---|
| Practice testing (retrieval) | **High** | α_test multiplier (1.0–1.5), IRT θ update | d = 0.55–0.60 over restudying[17] |
| Distributed practice (spacing) | **High** | α_space multiplier (1.0–1.4), FSRS interval | Up to 150% recall improvement[21] |
| Interleaved practice | **Moderate** | α_inter multiplier (1.0–1.3), session design | Blocked 20% → Interleaved 63%[22] |
| Elaborative interrogation | **Moderate** | Card generation prompt style | d ≈ 0.30 for factual material[29] |
| Self-explanation | **Moderate** | Post-answer feedback mode | Similar to elaborative interrogation[29] |
| Re-reading / highlighting | **Low** | Not implemented | Near-zero marginal benefit[17] |

**Critical caveat from Bjork**: desirable difficulties are only desirable when the student has sufficient background knowledge to overcome them. If the student has never seen a topic, interleaving it with advanced content is *undesirable*. This means α_inter should be gated: apply only when R_i > 0.4 for all topics in the session.[19]

### 4.2 Transfer-Appropriate Processing

The theoretical grounding for why P_s ≠ M_s is Morris, Bransford, and Franks' (1977) transfer-appropriate processing principle: retention is best when encoding processes match retrieval processes. Card recall (question: front → answer: back in a constant context) does not match MCAT passage-based retrieval. This is why:[30]

- The memory model measures recall in the context of the card prompt.
- The performance model measures accuracy in a passage-reading + inference context.
- The gap between M_s and P_s (the "paraphrase gap") is a first-class model output, required by the assignment's 7d paraphrase test.[1]

When the paraphrase gap is large (M_s high, P_s low), the student is "surface-learning" card wording without building transferable knowledge. The app should surface this explicitly rather than hiding it in an average.

### 4.3 The Metacognitive Problem

A subtle danger the spec identifies: students who tap "Good" without reading. FSRS cannot detect this — it models memory behavior, not intentionality. Rapid-fire "Good" responses inflate R without reflecting actual learning. Mitigations:[1]

1. Flag review sessions where the median response time < 2 seconds per card.
2. Discount α_test = 1.0 (no multiplier) when response time is below a minimum threshold.
3. Use the divergence between M_s and P_s as a behavioral signal: large gaps with high review counts should trigger a "verify your reviews" warning.

***

## Part V — Evaluation Framework

This is the most technically demanding component of the rubric, weighted at 12% (fair, re-runnable tests) plus 20% (score accuracy and honest uncertainty).[1]

### 5.1 Memory Model Calibration

**Goal:** When FSRS predicts R_i = 0.80, approximately 80% of reviews at that retrievability should succeed. This is the definition of a calibrated probability model.[31][32]

**Metric 1 — Expected Calibration Error (ECE):**

\[ ECE = \sum_{m=1}^{M} \frac{|B_m|}{N} \left| \text{acc}(B_m) - \text{conf}(B_m) \right| \]

where B_m is a bin of predictions in a confidence range, acc(B_m) is empirical accuracy in that bin, and conf(B_m) is mean predicted probability. An ECE near 0 means perfect calibration. Report ECE alongside a **reliability diagram** (calibration curve) as required by the Sunday deliverable.[31][1]

**Metric 2 — Brier Score:**

\[ BS = \frac{1}{N} \sum_{i=1}^{N} (f_i - o_i)^2 \]

where f_i is the predicted recall probability and o_i ∈ {0, 1} is the actual outcome. Lower is better. The Brier score decomposes into:[33][34][35]

\[ BS = \underbrace{REL}_{\text{calibration error}} - \underbrace{RES}_{\text{resolution}} + \underbrace{UNC}_{\text{irreducible uncertainty}} \]

- **REL** (reliability): how much predicted probabilities deviate from observed frequencies — should approach 0.
- **RES** (resolution): how much your predictions vary around the base rate — higher means more informative.
- **UNC** (uncertainty): the base rate variance, fixed by data.

Report all three decomposition terms, not just BS. A model with good BS but poor REL has miscalibrated probabilities that happen to get the scoring right by chance — exactly what the assignment penalizes.[1]

**Metric 3 — Log Loss (Binary Cross-Entropy):**

\[ \mathcal{L} = -\frac{1}{N} \sum_{i=1}^{N} \left[o_i \log f_i + (1 - o_i) \log(1 - f_i)\right] \]

Log loss penalizes confident wrong predictions more severely than Brier score, which matches FSRS's own training objective (binary cross-entropy). Report this alongside Brier.[9]

**Baseline to beat:** A naive baseline predicts a constant p = overall_recall_rate for all cards. Your calibrated FSRS model should beat this on both Brier and log loss on a held-out review set.

### 5.2 Performance Model Evaluation

**Goal:** Predict whether the student answers a held-out exam-style question correctly, using the IRT-derived θ_s estimate and question parameters.

**Held-out split strategy:**
- Use a **temporal split**, not random split, because question performance is ordered in time. All questions answered before date T form the training set; questions after T form the test set. This prevents the future from leaking into the model.[36][37]
- Maintain a strict **leakage check** (Assignment 7e): scan training questions and test questions for near-duplicate text using MinHash or Jaccard similarity at the n-gram level. Any test item with cosine similarity > 0.8 to a training item must be removed from test.[1]

**Evaluation metrics:**

| Metric | Formula | Target |
|---|---|---|
| Accuracy | (TP + TN) / N | Baseline: overall_correct_rate |
| AUC-ROC | Area under ROC curve | > 0.65 vs. naive baseline |
| Brier Score | As above, on Q correct/wrong | Lower than constant-p model |
| Wrong-answer rate | FP / (FP + TN) | Report at chosen cutoff; must not exceed 20% |

**Baseline comparison required by the assignment:**[1]
- Baseline A: keyword search — retrieve the most keyword-matching card for each question, predict correct iff R_i > 0.7.
- Baseline B: vector similarity — embed questions and cards, predict correct based on nearest-card retrievability.
- Your model: IRT θ_s from the full review history.

The assignment requires showing your model beats both baselines on the held-out set.

### 5.3 Score Mapping Evaluation

**Goal:** Map section-level question performance to a projected score on the 118–132 scale.

The empirically validated approach is a **linear regression from practice-test percentage correct to scaled score**. Community data from Reddit (n=98) shows FL1+FL2 average correlates with actual MCAT at r = 0.86. A 2020 peer-reviewed study found practice exam performance predicted actual MCAT with β = 0.74 (p < 0.001). That same paper found the median of all practice exam scores was the single best predictor of real performance (r = approximately 0.8+).[38][39][40]

This gives you an empirically grounded regression for the score mapping step that doesn't require your own longitudinal data:

\[ \hat{\text{scaled}}_s = \beta_0 + \beta_1 \cdot \bar{P}_s + \epsilon \]

where \(\bar{P}_s\) is fraction correct in section s. Fit β on AAMC sample test conversion tables, then derive a prediction interval from the residuals (σ ≈ ±3–4 scaled points for individual students).[41]

### 5.4 Leakage Detection (Assignment 7e)

A script must run before any model training or evaluation to flag contaminated data:[1]

```python
# Pseudocode for leakage check
def check_leakage(train_texts, test_texts, threshold=0.8):
    vectorizer = TfidfVectorizer(ngram_range=(1, 3))
    train_vecs = vectorizer.fit_transform(train_texts)
    test_vecs = vectorizer.transform(test_texts)
    sims = cosine_similarity(test_vecs, train_vecs)  # shape: (n_test, n_train)
    leaked = np.where(sims.max(axis=1) > threshold)[0]
    return leaked  # indices of contaminated test items
```

Run on:
1. Generated AI cards vs. test question bank
2. Training question bank vs. test question bank
3. Card fronts and backs vs. all test items

Flag and remove any contaminated items. Report: "X of Y test items removed as near-duplicates." If X > 5% of test items, flag a data quality warning.

### 5.5 The Three-Build Ablation (Section 8 of Assignment)

The assignment requires three parallel builds compared on the same questions, same time budget, same learners:[1]

| Build | Configuration | Purpose |
|---|---|---|
| **V1 — Full app** | Interleaving ON, spacing ON, testing effect ON | The complete model |
| **V2 — Feature off** | Turn off interleaving (α_inter = 1.0, blocked practice) | Isolate the interleaving contribution |
| **V3 — Plain Anki** | FSRS + standard Anki review, no scoring model | The obvious baseline |

**Hypothesis to state upfront (pre-registration):**
> "Topic-interleaved review (V1) will produce ≥5 percentage points higher accuracy on mixed-topic held-out questions than blocked review (V2) at equal study time."

**Evaluation on V1 vs. V2 vs. V3:**
- Primary metric: accuracy on 60 held-out mixed-topic exam-style questions (20 per section)
- Secondary: mean weighted coverage, session completion rate
- Report means ± standard deviations for all three builds

The critical comparison is V1 vs. V2. If V1 ≠ V2, you have isolated the interleaving feature's contribution. If V1 = V2 ≠ V3, your deck quality drives the benefit, not the interleaving feature. If all three are equal, report that result honestly — the assignment scores "interleaving made no difference here" as a valid scientific result.[1]

***

## Part VI — Connecting the Formula to Rust Implementation

### 6.1 Mastery Query (Best Rust Change)

The mastery query (Assignment 7a) integrates directly into the formula above. The required backend call returns, per topic, the weighted average recall and mastered card count:[1]

```rust
// In rslib/src/scheduler/ or rslib/src/stats/
pub struct TopicMasteryStats {
    pub topic_id: String,
    pub mastered_count: u32,      // cards with R_i > threshold
    pub mean_retrievability: f32, // weighted mean R_i across cards in topic
    pub coverage_fraction: f32,   // cards covered / AAMC topics in section
}
```

This output powers: M_s (uses mean_retrievability), C_s (uses coverage_fraction), and the dashboard abstention check. The justification for doing this in Rust rather than Python: the query must run on 50,000 cards within 500 ms for the dashboard, which requires efficient aggregation in the compiled backend rather than Python iteration.[1]

### 6.2 Points-at-Stake Queue

The points-at-stake queue (also Assignment 7a) sorts due cards by `w_i * (1 - R_i)`: topic weight times forgetting risk. This directly operationalizes the formula: topics where M_s is dragging down readiness the most get reviewed first. New protobuf message:[1]

```protobuf
// In proto/anki/scheduler.proto
message PointsAtStakeQueueConfig {
  map<string, float> topic_weights = 1;  // MCAT section weights
  float min_retrievability_threshold = 2;
}
```

This aligns the queue ordering with the formula's β_M coefficient — cards that most reduce M_s get priority.

***

## Part VII — Implementation Checklist

### Deliverable Timeline Alignment

**Wednesday (core, no AI):**
- [ ] FSRS R_i values exposed from rslib to Python via new backend call
- [ ] Topic-to-card mapping implemented (AAMC category tags on all cards)
- [ ] M_s computed and displayed with CI; abstention rule enforced
- [ ] Memory model calibration script written and validated on simulated reviews
- [ ] Leakage detection script complete and passing

**Friday (AI added, sync working):**
- [ ] IRT model fit on question bank; θ_s estimated per section per student
- [ ] P_s computed from held-out question performance
- [ ] α_space, α_inter, α_test multipliers implemented and toggleable
- [ ] Baseline comparisons (keyword, vector) implemented and run
- [ ] ECE and Brier score dashboards live in UI

**Sunday (prove it, ship):**
- [ ] Three-build ablation complete (V1/V2/V3) with results table
- [ ] Brier decomposition chart shipped with desktop installer
- [ ] CI for Ê_total displayed; no score shown under abstention threshold
- [ ] Leakage check run on final training + test split; result logged in README
- [ ] Calibration reliability diagram in results report

***

## Appendix: Formula Summary

\[ M_s = \sum_{i \in s} w_i \cdot R_i(t, S_i) \]

\[ P(correct | \theta_s, a_j, b_j, c_j) = c_j + \frac{1-c_j}{1 + e^{-a_j(\theta_s - b_j)}} \]

\[ P_s = \frac{1}{n_s} \sum_{j} P(correct | \theta_s, a_j, b_j, c_j) \]

\[ \hat{E}_s = 118 + 14 \cdot \sigma\!\left(\beta_0 + \beta_M \cdot M_s \cdot \alpha_{space} \cdot \alpha_{inter} \cdot \alpha_{test} + \beta_P \cdot P_s + \beta_C \cdot C_s\right) \]

\[ \hat{E}_{total} = \sum_{s=1}^{4} \hat{E}_s \]

\[ ECE = \sum_{m=1}^{M} \frac{|B_m|}{N} \left| \text{acc}(B_m) - \text{conf}(B_m) \right| \]

\[ BS = \frac{1}{N}\sum_i (f_i - o_i)^2 = REL - RES + UNC \]

**Abstention condition:** Show no score unless all four conditions hold:
1. ≥ 200 graded questions per section
2. ≥ 50% AAMC topic coverage per section  
3. SE(θ_s) ≤ 0.5 for all sections
4. ≥ 50% of due reviews completed within 2× recommended interval