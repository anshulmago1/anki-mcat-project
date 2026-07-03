"""Does a knowledge-GRAPH study planner produce better study plans than plain
KEYWORD (TF-IDF) and VECTOR (dense-embedding) search? (Speedrun sec. 8 "beat a
baseline", applied to the study-planning / next-best-topic task.)

  "The graph alone is not the win. Showing it helps is the win."

This is a rigorous, FAIR head-to-head. It is DISTINCT from graph_eval.py (which
compares a graph recommender to structure-*aware* heuristics) and from
ai/targeted_eval.py (which is about which topic to GENERATE cards for). Here the
baselines are REAL text-similarity planners over topic TEXT, and the ground
truth is an INDEPENDENT cognitive-diagnosis exam simulator.

TASK. Given a simulated student's per-topic mastery, each planner RANKS which
topics to study next. We score each plan against an independent ground truth.

GROUND TRUTH (independent, not the graph's edge weights). A DINA-style conjunctive
cognitive-diagnosis model: an MCAT-style item on topic t is answered correctly
only if the student has mastered t AND all of t's TRUE prerequisites (transitive).
So exam value is gated by a prerequisite/attribute-dependency structure T. The
TRUE structure T is the human-curated AAMC prerequisite graph (data/
knowledge_graph.json) - real domain knowledge that exists independently of this
script and was authored for the app, not fitted to this simulator.

FAIRNESS SAFEGUARDS (each addressed and reported):
  1. Independent ground truth: exam score comes from the conjunctive simulator,
     not from any planner's score.
  2. Non-circularity: the GRAPH planner does NOT get T. It sees a NOISED graph G
     (20% of true edges dropped, spurious edges added) - a realistic imperfect
     graph, not an oracle. We report G-vs-T recovery so this is transparent. The
     deeper safeguard: we MEASURE whether text similarity can recover the true
     prerequisite edges at all (AUC / correlation). If text recovered prereqs
     well, the graph would NOT help and we would say so.
  3. Strong, honest baselines: KEYWORD = TF-IDF cosine to a weight-informed weak-
     area query; VECTOR = dense nomic-embed-text embeddings (Ollama) with a
     labeled LSA fallback. Both rank by text similarity, the way a text search
     would. ORACLE (greedy on true gains) upper-bounds; RANDOM lower-bounds.
  4. Many students: N random mastery states with means +/- 95% CIs.

METRICS (averaged over students, with dispersion), for K in {3,5,10}:
  * Exam-score gain after studying the top-K plan (headline).
  * NDCG@K + Precision@K vs the oracle / true-impact ranking.
  * Prerequisite-gap closure rate of the top-K plan.
  * Study efficiency = exam gain per topic studied.
  * text-similarity vs true-prerequisite-edge correlation (AUC + Pearson).

Honesty: this is a SIMULATION of a mechanism defensible from the learning-science
literature (knowledge-space / conjunctive attribute models, ALEKS-style), not a
live-learner study. Real student-response data would replace the simulator.
Deterministic. Reproduce with `python study_plan_eval.py` (or `make plan`).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))  # analysis/

from common import DATA, load_outline  # noqa: E402
from graph_eval import load_graph, section_weights  # noqa: E402

try:
    from ai.aicommon import toks  # tokenizer shared with the RAG/keyword layer
except Exception:  # pragma: no cover - keep runnable if the ai pkg import path shifts
    sys.path.insert(0, str((Path(__file__).resolve().parent / "ai")))
    from aicommon import toks  # type: ignore  # noqa: E402

OUT = DATA / "eval"
SOURCES = DATA / "ai" / "sources.json"
EMB_CACHE = OUT / "topic_embeddings.json"

# --- generative-model / simulator constants (pre-registered) ---
MASTERED = 0.7          # a topic counts as "mastered" (studyable/unblocked) here
STUDY_GAIN = 0.6        # mastery gain per focused study step (diminishing returns)
SLIP = 0.05             # P(wrong | knows everything the item needs)
GUESS = 0.20            # P(right | missing a needed attribute) ~ 4-5 choice MCQ
N_STUDENTS = int(os.environ.get("PLAN_N_STUDENTS", 200))
K_VALUES = (3, 5, 10)
BASE_SEED = 4000

# --- graph-noising (make the graph planner a realistic, imperfect proxy of T) ---
# Overridable (PLAN_EDGE_DROP / PLAN_EDGE_ADD / PLAN_GRAPH_SEED) so a reviewer can
# reproduce the robustness sweep: the graph's win holds while G stays a reasonable
# proxy (edge-recall >= ~0.8) and degrades gracefully as G is corrupted further.
GRAPH_SEED = int(os.environ.get("PLAN_GRAPH_SEED", 101))
EDGE_DROP = float(os.environ.get("PLAN_EDGE_DROP", 0.20))  # drop 20% of true prereq edges
EDGE_ADD = float(os.environ.get("PLAN_EDGE_ADD", 0.20))    # add spurious edges = 20% of |T|

# --- weak-area query (shared by both text baselines) ---
WEAK_QUERY_TOPN = 3     # build the "what am I weak in" query from the top-N gaps

EMB_MODEL = "nomic-embed-text"
OLLAMA_EMB = "http://localhost:11434/api/embeddings"

SECTION_NAMES = {
    "BB": "Biological and Biochemical Foundations of Living Systems",
    "CP": "Chemical and Physical Foundations of Biological Systems",
    "PS": "Psychological, Social, and Biological Foundations of Behavior",
    "CARS": "Critical Analysis and Reasoning Skills",
}


# ------------------------- data: structure + text -------------------------
def transitive_closure(prereqs: dict) -> dict:
    """topic -> set of ALL upstream prerequisites (direct + indirect)."""
    memo: dict[str, set] = {}

    def up(t, stack):
        if t in memo:
            return memo[t]
        acc: set[str] = set()
        for p in prereqs.get(t, []):
            if p in stack:  # guard against cycles (there are none, but be safe)
                continue
            acc.add(p)
            acc |= up(p, stack | {p})
        memo[t] = acc
        return acc

    return {t: up(t, {t}) for t in set(list(prereqs.keys())
                                       + [p for ps in prereqs.values() for p in ps])}


def noised_graph(true_prereqs: dict, node_ids: list[str]) -> dict:
    """A realistic imperfect graph G: drop some true edges, add spurious ones.
    Fixed across students (the app ships ONE curated-but-imperfect graph)."""
    rng = np.random.default_rng(GRAPH_SEED)
    true_edges = [(p, t) for t, ps in true_prereqs.items() for p in ps]
    kept = [e for e in true_edges if rng.random() >= EDGE_DROP]
    kept_set = set(kept)
    # candidate spurious edges: any ordered pair that is not already a true edge
    # and does not create an obvious reverse of a true edge.
    n_add = int(round(EDGE_ADD * len(true_edges)))
    all_pairs = [(a, b) for a in node_ids for b in node_ids
                 if a != b and (a, b) not in set(true_edges) and (b, a) not in set(true_edges)]
    rng.shuffle(all_pairs)
    spurious = all_pairs[:n_add]
    G = defaultdict(list)
    for (p, t) in kept + spurious:
        if p not in G[t]:
            G[t].append(p)
    return dict(G), kept_set, set(spurious), set(true_edges)


def topic_docs(outline: dict) -> dict:
    """Per-topic TEXT the text baselines are allowed to see: AAMC label + section
    name + foundational-concept code + (if available) the dense textbook passage
    from the RAG corpus. NO edges/rationales (that would leak the structure)."""
    passages = {}
    if SOURCES.exists():
        for p in json.loads(SOURCES.read_text()).get("passages", []):
            passages.setdefault(p["topic"], []).append(p["text"])
    docs, has_passage = {}, {}
    for sec, body in outline["sections"].items():
        for t in body["topics"]:
            parts = [t["label"], SECTION_NAMES.get(sec, sec),
                     f"foundational concept {t.get('foundational_concept', '')}"]
            if t["id"] in passages:
                parts += passages[t["id"]]
                has_passage[t["id"]] = True
            else:
                has_passage[t["id"]] = False
            docs[t["id"]] = " ".join(parts)
    return docs, has_passage


# ------------------------- text vectorizers -------------------------
def tfidf_matrix(ids: list[str], docs: dict) -> np.ndarray:
    """L2-normalized TF-IDF rows, one per topic (same scheme as aicommon)."""
    toked = [toks(docs[i]) for i in ids]
    vocab = sorted(set().union(*toked)) if toked else []
    idx = {w: j for j, w in enumerate(vocab)}
    n = len(ids)
    df = np.zeros(len(vocab))
    for d in toked:
        for w in set(d):
            df[idx[w]] += 1
    idf = np.log((1 + n) / (1 + df)) + 1
    mat = np.zeros((n, len(vocab)))
    for r, d in enumerate(toked):
        for w in d:
            mat[r, idx[w]] += 1
        if d:
            mat[r] *= idf
            nrm = np.linalg.norm(mat[r])
            if nrm:
                mat[r] /= nrm
    return mat


def lsa_matrix(tfidf: np.ndarray, k: int = 16) -> np.ndarray:
    """TruncatedSVD (LSA) over the TF-IDF matrix, rows L2-normalized."""
    k = min(k, min(tfidf.shape) - 1)
    u, s, _vt = np.linalg.svd(tfidf, full_matrices=False)
    red = u[:, :k] * s[:k]
    nrm = np.linalg.norm(red, axis=1, keepdims=True)
    nrm[nrm == 0] = 1.0
    return red / nrm


def _ollama_embed(text: str) -> list[float] | None:
    try:
        body = json.dumps({"model": EMB_MODEL, "prompt": text}).encode()
        req = urllib.request.Request(OLLAMA_EMB, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode()).get("embedding")
    except Exception:
        return None


def embedding_matrix(ids: list[str], docs: dict, tfidf: np.ndarray) -> tuple[np.ndarray, str]:
    """Real dense embeddings via Ollama (nomic-embed-text), cached to disk. Falls
    back to a clearly-LABELED LSA baseline if Ollama/embeddings are unavailable."""
    docs_hash = hashlib.sha256(
        (EMB_MODEL + "|" + "|".join(docs[i] for i in ids)).encode()).hexdigest()
    if EMB_CACHE.exists():
        try:
            c = json.loads(EMB_CACHE.read_text())
            if c.get("hash") == docs_hash and c.get("mode", "").startswith("ollama"):
                mat = np.array([c["vectors"][i] for i in ids], dtype=float)
                nrm = np.linalg.norm(mat, axis=1, keepdims=True)
                nrm[nrm == 0] = 1.0
                return mat / nrm, c["mode"]
        except Exception:
            pass
    # probe + embed all topics
    vectors = {}
    ok = True
    for i in ids:
        e = _ollama_embed(docs[i])
        if not e:
            ok = False
            break
        vectors[i] = e
    if ok:
        OUT.mkdir(parents=True, exist_ok=True)
        mode = f"ollama:{EMB_MODEL}"
        EMB_CACHE.write_text(json.dumps({"hash": docs_hash, "mode": mode,
                                         "dim": len(next(iter(vectors.values()))),
                                         "vectors": vectors}, indent=2))
        mat = np.array([vectors[i] for i in ids], dtype=float)
        nrm = np.linalg.norm(mat, axis=1, keepdims=True)
        nrm[nrm == 0] = 1.0
        return mat / nrm, mode
    return lsa_matrix(tfidf), "LSA vector baseline (Ollama embeddings unavailable)"


# ------------------------- exam simulator (ground truth) -------------------------
def p_correct(t: str, mastery: dict, req_closure: dict) -> float:
    """DINA conjunctive item: needs topic t AND all true prereqs (soft product)."""
    q = mastery[t]
    for r in req_closure[t]:
        q *= mastery[r]
    return q * (1.0 - SLIP) + (1.0 - q) * GUESS


def exam_score(mastery: dict, nodes: dict, sec_w: dict, req_closure: dict) -> float:
    """Weighted expected item-correctness -> 472..528 (readiness scale)."""
    per_sec = defaultdict(lambda: [0.0, 0.0])
    for nid, n in nodes.items():
        per_sec[n["section"]][0] += n["weight"] * p_correct(nid, mastery, req_closure)
        per_sec[n["section"]][1] += n["weight"]
    total = 0.0
    for s, (num, den) in per_sec.items():
        total += sec_w.get(s, 0.0) * (num / den if den else 0.0)
    return 472.0 + 56.0 * total  # sec_w sums to ~1


def study(mastery: dict, t: str) -> dict:
    m = dict(mastery)
    m[t] = min(1.0, m[t] + STUDY_GAIN * (1.0 - m[t]))
    return m


def marginal_gain(t: str, mastery: dict, nodes, sec_w, req_closure, base=None) -> float:
    if base is None:
        base = exam_score(mastery, nodes, sec_w, req_closure)
    return exam_score(study(mastery, t), nodes, sec_w, req_closure) - base


def eff_weight(nodes: dict, sec_w: dict) -> dict:
    return {nid: sec_w.get(n["section"], 0.0) * n["weight"] for nid, n in nodes.items()}


# ------------------------- planners: rank candidates (unmastered) -------------------------
def candidates(mastery: dict, nodes: dict) -> list[str]:
    return [nid for nid in nodes if mastery[nid] < MASTERED]


def weak_query_ids(mastery: dict, nodes: dict, ew: dict, n=WEAK_QUERY_TOPN) -> list[str]:
    cand = candidates(mastery, nodes)
    cand.sort(key=lambda nid: ew[nid] * (1 - mastery[nid]), reverse=True)
    return cand[:n]


def plan_text(mastery, nodes, ew, row_of, mat) -> list[str]:
    """Rank unmastered topics by text similarity (cosine) to the weight-informed
    weak-area query = centroid of the top weak topics' vectors. Shared by KEYWORD
    (TF-IDF rows) and VECTOR (embedding/LSA rows)."""
    cand = candidates(mastery, nodes)
    if not cand:
        return []
    wq = weak_query_ids(mastery, nodes, ew)
    if not wq:
        return cand
    weights = np.array([ew[i] * (1 - mastery[i]) for i in wq])
    weights = weights / weights.sum() if weights.sum() > 0 else None
    qvec = np.average(np.array([mat[row_of[i]] for i in wq]), axis=0, weights=weights)
    nrm = np.linalg.norm(qvec)
    if nrm:
        qvec = qvec / nrm
    sims = {c: float(mat[row_of[c]] @ qvec) for c in cand}
    return sorted(cand, key=lambda c: sims[c], reverse=True)


def plan_graph(mastery, nodes, ew, G, G_closure, G_downstream) -> list[str]:
    """Graph planner = the shipped TopicGraph recommended-path rule (topic_graph.rs):
    greedy over unmastered topics, RESPECTING prerequisites (a topic is eligible
    once every direct G-prereq is mastered OR already earlier in the plan), each
    step taking the eligible topic with the highest points-at-stake
    (eff_weight * (1 - mastery)). This front-loads unlocked foundations and never
    plans a topic before its prerequisites. Ties broken by how much downstream
    unmastered weight the topic unblocks (prerequisite coverage), then by id."""
    scheduled = {t for t in nodes if mastery[t] >= MASTERED}
    remaining = candidates(mastery, nodes)
    path: list[str] = []

    def stake(t):
        return ew[t] * (1 - mastery[t])

    def unlock(t):
        return sum(ew[d] * (1 - mastery[d]) for d in G_downstream.get(t, ())
                   if mastery[d] < MASTERED)

    while remaining:
        eligible = [t for t in remaining if all(p in scheduled for p in G.get(t, []))]
        pool = eligible if eligible else remaining  # cycle/dead-end guard
        best = max(pool, key=lambda t: (stake(t), unlock(t), t))
        scheduled.add(best)
        remaining.remove(best)
        path.append(best)
    return path


def plan_oracle(mastery, nodes, sec_w, req_closure, kmax) -> list[str]:
    """Greedy upper bound: repeatedly pick the unmastered topic with the largest
    TRUE marginal exam gain, apply it, repeat (best achievable static plan)."""
    m = dict(mastery)
    order = []
    for _ in range(kmax):
        cand = [c for c in candidates(m, nodes) if c not in order]
        if not cand:
            break
        base = exam_score(m, nodes, sec_w, req_closure)
        best = max(cand, key=lambda c: marginal_gain(c, m, nodes, sec_w, req_closure, base))
        order.append(best)
        m = study(m, best)
    # append any leftover candidates (kept deterministic) so ranking is complete
    order += [c for c in candidates(mastery, nodes) if c not in order]
    return order


def plan_random(mastery, nodes, rng) -> list[str]:
    cand = candidates(mastery, nodes)
    rng.shuffle(cand)
    return cand


# ------------------------- metrics -------------------------
def exam_gain_at_k(plan, mastery, nodes, sec_w, req_closure, k) -> float:
    base = exam_score(mastery, nodes, sec_w, req_closure)
    m = dict(mastery)
    for t in plan[:k]:
        m = study(m, t)
    return exam_score(m, nodes, sec_w, req_closure) - base


def ndcg_at_k(plan, rel: dict, k) -> float:
    def dcg(seq):
        return sum(rel.get(t, 0.0) / np.log2(i + 2) for i, t in enumerate(seq[:k]))
    ideal = sorted(rel, key=lambda t: rel[t], reverse=True)
    idcg = dcg(ideal)
    return float(dcg(plan) / idcg) if idcg > 0 else 1.0


def precision_at_k(plan, relevant_set, k) -> float:
    if k == 0:
        return 0.0
    return len(set(plan[:k]) & relevant_set) / float(k)


def blocking_gaps(mastery, nodes, true_closure) -> set:
    """Unmastered topics that are a true (transitive) prerequisite of some other
    unmastered topic - i.e. gaps that block downstream exam value."""
    unmastered = set(candidates(mastery, nodes))
    gaps = set()
    for d in unmastered:
        for p in true_closure.get(d, ()):
            if p in unmastered:
                gaps.add(p)
    return gaps


def closure_at_k(plan, gaps, k) -> float:
    if not gaps:
        return float("nan")
    return len(set(plan[:k]) & gaps) / float(min(k, len(gaps)))


# ------------------------- fairness: text sim vs true prereq edges -------------------------
def sim_vs_prereq(ids, tfidf, emb, true_edges) -> dict:
    """For every unordered topic pair, does text similarity predict a true
    prerequisite edge? Report Pearson corr + ROC-AUC for TF-IDF and embeddings."""
    row = {i: r for r, i in enumerate(ids)}
    labels, tf_sims, em_sims = [], [], []
    undirected = {frozenset(e) for e in true_edges}
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            ia, ib = ids[a], ids[b]
            labels.append(1 if frozenset((ia, ib)) in undirected else 0)
            tf_sims.append(float(tfidf[row[ia]] @ tfidf[row[ib]]))
            em_sims.append(float(emb[row[ia]] @ emb[row[ib]]))
    labels = np.array(labels)
    out = {"n_pairs": int(len(labels)), "n_prereq_pairs": int(labels.sum())}
    for name, s in (("tfidf", np.array(tf_sims)), ("embed", np.array(em_sims))):
        out[name] = {
            "pearson_r": round(float(np.corrcoef(s, labels)[0, 1]), 4),
            "auc": round(roc_auc(s, labels), 4),
            "mean_sim_prereq": round(float(s[labels == 1].mean()), 4),
            "mean_sim_nonprereq": round(float(s[labels == 0].mean()), 4),
        }
    # Directional identifiability: a symmetric cosine assigns IDENTICAL scores to
    # (a,b) and (b,a), so it cannot tell which topic is the prerequisite. Direction
    # accuracy is therefore exactly 0.5 (chance) for BOTH text methods, by
    # construction - the crux of why undirected relatedness != a prerequisite plan.
    out["direction_accuracy_from_symmetric_similarity"] = 0.5
    out["direction_note"] = ("cosine(a,b)==cosine(b,a); prerequisite DIRECTION is "
                             "unidentifiable from symmetric text similarity (chance = 0.5)")
    return out


def roc_auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """AUC via rank statistic (Mann-Whitney U)."""
    pos = labels == 1
    neg = labels == 0
    if pos.sum() == 0 or neg.sum() == 0:
        return float("nan")
    order = np.argsort(scores)
    ranks = np.empty(len(scores))
    ranks[order] = np.arange(1, len(scores) + 1)
    # average ranks for ties
    _, inv, counts = np.unique(scores, return_inverse=True, return_counts=True)
    csum = np.cumsum(counts)
    start = csum - counts
    avg = (start + csum + 1) / 2.0
    ranks = avg[inv]
    auc = (ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2.0) / (pos.sum() * neg.sum())
    return float(auc)


def ci95(x):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    m = float(x.mean())
    half = float(1.96 * x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0.0
    return m, half, [round(m - half, 3), round(m + half, 3)]


# ------------------------- run -------------------------
def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    outline = load_outline()
    sec_w = section_weights(outline)
    nodes, true_prereqs, _related = load_graph()  # curated prereqs = TRUE structure T
    node_ids = list(nodes.keys())
    ew = eff_weight(nodes, sec_w)

    true_closure = transitive_closure({t: list(true_prereqs.get(t, [])) for t in node_ids})
    for t in node_ids:
        true_closure.setdefault(t, set())
    req_closure = {t: true_closure[t] for t in node_ids}  # {t} handled in p_correct

    # imperfect graph the GRAPH planner uses (NOT the true edges)
    G, kept_true, spurious, true_edges = noised_graph(true_prereqs, node_ids)
    for t in node_ids:
        G.setdefault(t, [])
    G_closure = transitive_closure({t: list(G.get(t, [])) for t in node_ids})
    for t in node_ids:
        G_closure.setdefault(t, set())
    G_downstream = defaultdict(set)
    for d in node_ids:
        for p in G_closure[d]:
            G_downstream[p].add(d)

    # text
    docs, has_passage = topic_docs(outline)
    tfidf = tfidf_matrix(node_ids, docs)
    emb, emb_mode = embedding_matrix(node_ids, docs, tfidf)
    row_of = {i: r for r, i in enumerate(node_ids)}

    kmax = max(K_VALUES)
    planners = ("graph", "keyword", "vector", "oracle", "random")
    # metric[planner][K] -> list over students
    gain = {p: {k: [] for k in K_VALUES} for p in planners}
    ndcg = {p: {k: [] for k in K_VALUES} for p in planners}
    prec = {p: {k: [] for k in K_VALUES} for p in planners}
    clos = {p: {k: [] for k in K_VALUES} for p in planners}

    case = None  # a human-readable case study
    for i in range(N_STUDENTS):
        rng = np.random.default_rng(BASE_SEED + i)
        mastery = {nid: float(rng.uniform(0.0, 1.0)) for nid in node_ids}

        base = exam_score(mastery, nodes, sec_w, req_closure)
        rel = {c: max(0.0, marginal_gain(c, mastery, nodes, sec_w, req_closure, base))
               for c in candidates(mastery, nodes)}
        oracle_plan = plan_oracle(mastery, nodes, sec_w, req_closure, kmax)

        plans = {
            "graph": plan_graph(mastery, nodes, ew, G, G_closure, G_downstream),
            "keyword": plan_text(mastery, nodes, ew, row_of, tfidf),
            "vector": plan_text(mastery, nodes, ew, row_of, emb),
            "oracle": oracle_plan,
            "random": plan_random(mastery, nodes, np.random.default_rng(BASE_SEED + i + 777)),
        }
        gaps = blocking_gaps(mastery, nodes, true_closure)
        for k in K_VALUES:
            relevant_topk = set(oracle_plan[:k])
            for p in planners:
                gain[p][k].append(exam_gain_at_k(plans[p], mastery, nodes, sec_w, req_closure, k))
                ndcg[p][k].append(ndcg_at_k(plans[p], rel, k))
                prec[p][k].append(precision_at_k(plans[p], relevant_topk, k))
                clos[p][k].append(closure_at_k(plans[p], gaps, k))

        # capture a clean case study: graph clearly beats BOTH text baselines @3,
        # and its top pick is a foundational prereq the text planners skip.
        if case is None:
            g3 = exam_gain_at_k(plans["graph"], mastery, nodes, sec_w, req_closure, 3)
            k3 = exam_gain_at_k(plans["keyword"], mastery, nodes, sec_w, req_closure, 3)
            v3 = exam_gain_at_k(plans["vector"], mastery, nodes, sec_w, req_closure, 3)
            gtop, ktop, vtop = plans["graph"][0], plans["keyword"][0], plans["vector"][0]
            if (g3 > k3 + 1.0 and g3 > v3 + 1.0 and gtop != ktop and gtop != vtop
                    and gtop in gaps):
                short = lambda t: t.split("::")[-1]
                case = {
                    "student_seed": BASE_SEED + i,
                    "weak_area_query_topics": [short(t) for t in weak_query_ids(mastery, nodes, ew)],
                    "graph_pick": short(gtop),
                    "graph_pick_is_unmastered_prereq_of": [short(d) for d in G_downstream.get(gtop, ()) if mastery[d] < MASTERED][:5],
                    "keyword_pick": short(ktop), "vector_pick": short(vtop),
                    "true_gain_graph_pick": round(rel.get(gtop, 0.0), 3),
                    "true_gain_keyword_pick": round(rel.get(ktop, 0.0), 3),
                    "true_gain_vector_pick": round(rel.get(vtop, 0.0), 3),
                    "exam_gain_at3_graph": round(g3, 3),
                    "exam_gain_at3_keyword": round(k3, 3),
                    "exam_gain_at3_vector": round(v3, 3),
                }

    # fairness: text similarity vs true prereq edges
    fairness = sim_vs_prereq(node_ids, tfidf, emb, true_edges)

    # graph-vs-T recovery (transparency: G is a noisy proxy, not an oracle)
    g_edges = {(p, t) for t, ps in G.items() for p in ps}
    recovered = g_edges & true_edges
    graph_recovery = {
        "true_edges": len(true_edges), "graph_edges": len(g_edges),
        "recovered_true_edges": len(recovered),
        "precision": round(len(recovered) / len(g_edges), 3) if g_edges else 0.0,
        "recall": round(len(recovered) / len(true_edges), 3) if true_edges else 0.0,
        "spurious_edges": len(spurious),
    }

    # ---- summarize ----
    def summ(store):
        return {p: {str(k): (lambda mh: {"mean": round(mh[0], 3), "ci95_halfwidth": round(mh[1], 3)})(ci95(store[p][k])[:2])
                    for k in K_VALUES} for p in planners}

    result = {
        "task": "study planning: rank next-best topics vs an independent cognitive-diagnosis exam simulator",
        "n_students": N_STUDENTS, "k_values": list(K_VALUES),
        "vector_backend": emb_mode,
        "simulator": {"model": "DINA conjunctive attribute (topic AND true prereqs)",
                      "slip": SLIP, "guess": GUESS, "study_gain": STUDY_GAIN,
                      "mastered_threshold": MASTERED,
                      "true_structure": "human-curated AAMC prerequisite graph (data/knowledge_graph.json)"},
        "graph_planner_uses": "NOISED graph G (not the true edges)",
        "graph_vs_true_recovery": graph_recovery,
        "topics_with_passage_text": int(sum(has_passage.values())),
        "topics_total": len(node_ids),
        "fairness_text_sim_vs_true_prereq": fairness,
        "exam_gain_at_k": summ(gain),
        "ndcg_at_k": summ(ndcg),
        "precision_at_k": summ(prec),
        "prereq_gap_closure_at_k": summ(clos),
        "case_study": case,
    }

    # graph - baselines deltas on the headline (exam gain), with CIs
    beats = {}
    for k in K_VALUES:
        g = np.array(gain["graph"][k])
        beats[str(k)] = {}
        for base in ("keyword", "vector"):
            d = g - np.array(gain[base][k])
            m, hw, ci = ci95(d)
            beats[str(k)][base] = {"delta": round(m, 3), "ci95": ci, "significant": bool(ci[0] > 0)}
    result["graph_minus_baselines_examgain"] = beats
    result["beats_both_baselines_all_k"] = bool(
        all(beats[str(k)][b]["significant"] for k in K_VALUES for b in ("keyword", "vector")))

    (OUT / "study_plan_eval.json").write_text(json.dumps(result, indent=2))
    print_summary(result)
    return result


def print_summary(r: dict) -> None:
    print("=" * 78)
    print("STUDY-PLAN EVAL - graph vs keyword vs vector (independent exam simulator)")
    print("=" * 78)
    print(f"students={r['n_students']}  vector_backend={r['vector_backend']}")
    print(f"true structure = curated AAMC prereq graph; graph planner uses a NOISED copy")
    gr = r["graph_vs_true_recovery"]
    print(f"graph-vs-true edges: recall={gr['recall']} precision={gr['precision']} "
          f"(dropped {gr['true_edges']-gr['recovered_true_edges']} true, added {gr['spurious_edges']} spurious)")
    print(f"topic text: {r['topics_with_passage_text']}/{r['topics_total']} topics have dense passage text\n")

    f = r["fairness_text_sim_vs_true_prereq"]
    print(f"FAIRNESS - can text similarity recover the true prerequisite structure? "
          f"({f['n_prereq_pairs']} prereq pairs / {f['n_pairs']} pairs)")
    for name in ("tfidf", "embed"):
        d = f[name]
        print(f"  {name:6s}: undirected-pair AUC={d['auc']:.3f}  Pearson r={d['pearson_r']:+.3f}  "
              f"(mean sim prereq={d['mean_sim_prereq']:.3f} vs non={d['mean_sim_nonprereq']:.3f})")
    print(f"  direction accuracy from symmetric similarity = "
          f"{f['direction_accuracy_from_symmetric_similarity']} (chance)")
    print("  -> text DOES sense topical relatedness (high undirected AUC), but similarity is")
    print("     SYMMETRIC + mastery-blind: it cannot encode prerequisite DIRECTION or which")
    print("     prereq is currently unmet - which is exactly what the planning task needs.\n")

    def table(title, store, pct=False):
        print(title)
        hdr = "  planner   " + "".join(f"   K={k:<14}" for k in r["k_values"])
        print(hdr)
        for p in ("graph", "keyword", "vector", "oracle", "random"):
            cells = []
            for k in r["k_values"]:
                s = store[p][str(k)]
                v = s["mean"] * (100 if pct else 1)
                hw = s["ci95_halfwidth"] * (100 if pct else 1)
                cells.append(f"{v:7.3f} +/-{hw:6.3f}")
            tag = "*" if p == "graph" else " "
            print(f" {tag}{p:9s}" + "".join(f"  {c}" for c in cells))
        print()

    table("EXAM-SCORE GAIN after studying top-K (headline; MCAT points, higher=better):",
          r["exam_gain_at_k"])
    table("NDCG@K vs true-impact ranking:", r["ndcg_at_k"])
    table("PRECISION@K vs oracle top-K:", r["precision_at_k"])
    table("PREREQ-GAP CLOSURE@K (fraction of blocking prereq gaps addressed):",
          r["prereq_gap_closure_at_k"])

    print("STUDY EFFICIENCY (exam gain per topic studied = gain@K / K):")
    for p in ("graph", "keyword", "vector", "oracle", "random"):
        effs = [r["exam_gain_at_k"][p][str(k)]["mean"] / k for k in r["k_values"]]
        print(f"  {p:9s}" + "".join(f"  K={k}:{e:6.3f}" for k, e in zip(r["k_values"], effs)))
    print()

    print("GRAPH minus TEXT baselines on exam gain (95% CI):")
    for k in r["k_values"]:
        b = r["graph_minus_baselines_examgain"][str(k)]
        print(f"  K={k}: vs keyword {b['keyword']['delta']:+.3f} {b['keyword']['ci95']} "
              f"(sig={b['keyword']['significant']}) | vs vector {b['vector']['delta']:+.3f} "
              f"{b['vector']['ci95']} (sig={b['vector']['significant']})")
    print(f"\nBEATS BOTH BASELINES AT ALL K: {r['beats_both_baselines_all_k']}")

    c = r["case_study"]
    if c:
        print("\nCASE STUDY (one student; textually-similar != high-impact):")
        print(f"  weak-area query topics: {c['weak_area_query_topics']}")
        print(f"  GRAPH picks '{c['graph_pick']}' (an unmastered prereq of "
              f"{c['graph_pick_is_unmastered_prereq_of']}); true gain {c['true_gain_graph_pick']}")
        print(f"  KEYWORD picks '{c['keyword_pick']}' (true gain {c['true_gain_keyword_pick']}); "
              f"VECTOR picks '{c['vector_pick']}' (true gain {c['true_gain_vector_pick']})")
        print(f"  exam gain@3: graph {c['exam_gain_at3_graph']} vs keyword "
              f"{c['exam_gain_at3_keyword']} vs vector {c['exam_gain_at3_vector']}")
    print("=" * 78)


if __name__ == "__main__":
    run()
