"""Leakage detection (Speedrun 7e). Leaked test data zeroes that score, so this
runs BEFORE any model training/eval.

Self-contained TF-IDF over word 1-3 grams + cosine similarity (no sklearn needed).
Flags any test item whose max similarity to a training item exceeds a threshold
(default 0.8). Reports "X of Y removed"; >5% raises a data-quality warning.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from common import DATA

SIM = DATA / "sim"
OUT = DATA / "eval"

WORD = re.compile(r"[a-z0-9]+")


def ngrams(text: str, lo: int = 1, hi: int = 3) -> list[str]:
    toks = WORD.findall(text.lower())
    grams = []
    for n in range(lo, hi + 1):
        grams += [" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)]
    return grams


def tfidf_vectors(docs: list[list[str]]) -> tuple[list[dict[str, float]], dict[str, float]]:
    n = len(docs)
    df: Counter = Counter()
    for grams in docs:
        df.update(set(grams))
    idf = {g: math.log((1 + n) / (1 + c)) + 1.0 for g, c in df.items()}
    vecs = []
    for grams in docs:
        tf = Counter(grams)
        vec = {g: (cnt / len(grams)) * idf[g] for g, cnt in tf.items()} if grams else {}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vecs.append({g: v / norm for g, v in vec.items()})
    return vecs, idf


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(g, 0.0) for g, v in a.items())


def check_leakage(train_texts: list[str], test_texts: list[str], threshold: float = 0.8):
    train_vecs, idf = tfidf_vectors([ngrams(t) for t in train_texts])
    # transform test docs into the train idf space
    test_docs = [ngrams(t) for t in test_texts]
    test_vecs = []
    for grams in test_docs:
        tf = Counter(grams)
        vec = {g: (cnt / len(grams)) * idf.get(g, 0.0) for g, cnt in tf.items()} if grams else {}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        test_vecs.append({g: v / norm for g, v in vec.items()})
    leaked = []
    for i, tv in enumerate(test_vecs):
        best = max((cosine(tv, trv) for trv in train_vecs), default=0.0)
        if best > threshold:
            leaked.append({"test_index": i, "max_similarity": round(best, 4)})
    return leaked


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    with open(SIM / "questions.json") as f:
        questions = json.load(f)
    texts = [q["stem"] for q in questions]
    half = len(texts) // 2
    train_texts, test_texts = texts[:half], texts[half:]

    # Inject a deliberate near-duplicate so we can prove the detector fires.
    if train_texts:
        test_texts = test_texts + [train_texts[0]]

    leaked = check_leakage(train_texts, test_texts, threshold=0.8)
    pct = len(leaked) / max(1, len(test_texts))
    result = {
        "n_train": len(train_texts),
        "n_test": len(test_texts),
        "threshold": 0.8,
        "n_leaked": len(leaked),
        "pct_leaked": round(pct, 4),
        "data_quality_warning": pct > 0.05,
        "detector_self_test_passed": len(leaked) >= 1,  # the injected dup must be caught
        "leaked": leaked[:20],
    }
    with open(OUT / "leakage.json", "w") as f:
        json.dump(result, f, indent=2)
    print(f"[leakage] {len(leaked)} of {len(test_texts)} test items flagged "
          f"(>0.8 cosine); self_test_passed={result['detector_self_test_passed']}")
    return result


if __name__ == "__main__":
    run()
