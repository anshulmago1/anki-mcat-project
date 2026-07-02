"""Smallest-version proof of the MEMORY -> PERFORMANCE bridge.

The differentiated core of the readiness model is the claim that being able to
*recall* a fact does not mean you can *apply* it to a novel exam-style question -
and that our performance layer measures that transfer, not just memory. Real
paywalled data (UWorld/AAMC graded responses) is unavailable, so this proves the
*smallest honest version* on real matched items with real graded responses:

  data/questions/bridge_pilot.json holds, per concept, a RECALL item (straight
  from the flashcard fact) and a TRANSFER item (a novel application question using
  the same fact). Both are 4-option MC with an objective key, so any respondent is
  graded automatically - no fabricated numbers.

Respondents (mix and match; more is better):
  * `run_llm`  - the LOCAL llama3 answers every item k times (real, non-human,
    non-paywalled graded responses you can generate today). Clearly labeled.
  * `quiz <name>` - a human takes the same MC quiz in the terminal (~15 min);
    run it on yourself + a few friends for the real human claim.

Then `analyze` tests the bridge:
  * gap = recall_acc - transfer_acc  (is transfer actually harder?)
  * P(transfer correct | recall correct)  (does knowing the fact guarantee using it?)
  * McNemar exact test on paired recall/transfer discordances
  * corr(recall_rate, transfer_rate) across concepts (are memory & performance separable?)

Usage:
  ../.venv/bin/python perf_bridge.py run_llm 5      # local-LLM respondent, 5 samples/item
  ../.venv/bin/python perf_bridge.py quiz anshul    # human quiz
  ../.venv/bin/python perf_bridge.py analyze        # -> data/eval/perf_bridge.json
"""
from __future__ import annotations

import csv
import json
import math
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "ai"))
from common import DATA  # noqa: E402

ITEMS = DATA / "questions" / "bridge_pilot.json"
BRIDGE = DATA / "bridge"
RESP = BRIDGE / "responses.csv"
OUT = DATA / "eval"
FIELDS = ["respondent", "item_id", "kind", "sample", "chosen", "correct", "ts"]
_LETTER = re.compile(r"(?<![A-Za-z])([ABCD])(?![A-Za-z])")


def load_items() -> list[dict]:
    return json.loads(ITEMS.read_text())["concepts"]


def mc_prompt(item_kind: dict) -> str:
    ch = item_kind["choices"]
    lines = [f"{k}) {ch[k]}" for k in ("A", "B", "C", "D")]
    return ("You are taking the MCAT. Choose the single best answer.\n"
            "Respond with ONLY the letter (A, B, C, or D).\n\n"
            f"Q: {item_kind['q']}\n" + "\n".join(lines) + "\n\nAnswer:")


def parse_letter(text: str) -> str | None:
    m = _LETTER.search(text.strip().upper())
    return m.group(1) if m else None


def append_rows(rows: list[dict]) -> None:
    BRIDGE.mkdir(parents=True, exist_ok=True)
    new = not RESP.exists()
    with open(RESP, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def run_llm(k: int = 5, model: str = "llama3", temp: float = 0.7) -> None:
    from aicommon import die_if_no_ollama, ollama_generate
    die_if_no_ollama()
    items = load_items()
    respondent = f"llm:{model}"
    rows = []
    for c in items:
        for kind in ("recall", "transfer"):
            it = c[kind]
            prompt = mc_prompt(it)
            for i in range(k):
                raw = ollama_generate(prompt, temperature=temp, seed=1000 + i)
                chosen = parse_letter(raw) or "?"
                correct = int(chosen == it["answer"])
                rows.append({"respondent": respondent, "item_id": c["id"], "kind": kind,
                             "sample": i, "chosen": chosen, "correct": correct,
                             "ts": int(time.time())})
        print(f"[bridge] {respondent} answered {c['id']} ({k}x recall + {k}x transfer)")
    append_rows(rows)
    print(f"[bridge] wrote {len(rows)} graded responses -> {RESP}")


def quiz(subject: str) -> None:
    items = load_items()
    rows = []
    print(f"\nMCAT bridge quiz for '{subject}'. Type A/B/C/D and Enter. No peeking.\n")
    for c in items:
        for kind in ("recall", "transfer"):
            it = c[kind]
            print(mc_prompt(it), end=" ")
            ans = ""
            while ans not in ("A", "B", "C", "D"):
                ans = input().strip().upper()[:1]
            correct = int(ans == it["answer"])
            rows.append({"respondent": subject, "item_id": c["id"], "kind": kind,
                         "sample": 0, "chosen": ans, "correct": correct, "ts": int(time.time())})
            print()
    append_rows(rows)
    print(f"[bridge] recorded {len(rows)} responses for {subject}")


def binom_two_sided(b: int, n: int) -> float:
    """Exact two-sided binomial p at prob 0.5 (McNemar exact)."""
    if n == 0:
        return 1.0
    probs = [math.comb(n, i) * 0.5 ** n for i in range(n + 1)]
    obs = probs[b]
    return float(min(1.0, sum(p for p in probs if p <= obs + 1e-12)))


def analyze() -> dict:
    if not RESP.exists():
        print("[bridge] no responses yet. Run `run_llm` and/or `quiz <name>` first.")
        return {}
    OUT.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(RESP)))
    for r in rows:
        r["correct"] = int(r["correct"])

    respondents = sorted(set(r["respondent"] for r in rows))
    # pooled accuracies
    rec = [r["correct"] for r in rows if r["kind"] == "recall"]
    tra = [r["correct"] for r in rows if r["kind"] == "transfer"]
    recall_acc = float(np.mean(rec)) if rec else 0.0
    transfer_acc = float(np.mean(tra)) if tra else 0.0

    # pair recall & transfer by (respondent, item, sample)
    idx: dict[tuple, dict] = {}
    for r in rows:
        idx.setdefault((r["respondent"], r["item_id"], r["sample"]), {})[r["kind"]] = r["correct"]
    pairs = [(v["recall"], v["transfer"]) for v in idx.values() if "recall" in v and "transfer" in v]
    n_pairs = len(pairs)
    rec_right = [t for (rr, t) in pairs if rr == 1]
    rec_wrong = [t for (rr, t) in pairs if rr == 0]
    p_transfer_given_recall = float(np.mean(rec_right)) if rec_right else None
    p_transfer_given_wrong = float(np.mean(rec_wrong)) if rec_wrong else None
    # McNemar discordances: b = recall right & transfer wrong, c = recall wrong & transfer right
    b = sum(1 for (rr, t) in pairs if rr == 1 and t == 0)
    c = sum(1 for (rr, t) in pairs if rr == 0 and t == 1)
    mcnemar_p = binom_two_sided(min(b, c), b + c)

    # per-concept rates -> are memory and performance separable?
    per = defaultdict(lambda: {"recall": [], "transfer": []})
    for r in rows:
        per[r["item_id"]][r["kind"]].append(r["correct"])
    concept_rows = []
    rrates, trates = [], []
    for cid, v in sorted(per.items()):
        rr = float(np.mean(v["recall"])) if v["recall"] else 0.0
        tr = float(np.mean(v["transfer"])) if v["transfer"] else 0.0
        concept_rows.append({"concept": cid, "recall_rate": round(rr, 2),
                             "transfer_rate": round(tr, 2), "gap": round(rr - tr, 2)})
        rrates.append(rr); trates.append(tr)
    corr = (float(np.corrcoef(rrates, trates)[0, 1])
            if len(rrates) > 2 and np.std(rrates) > 0 and np.std(trates) > 0 else None)

    # per-respondent summary
    by_resp = {}
    for rp in respondents:
        rq = [r["correct"] for r in rows if r["respondent"] == rp and r["kind"] == "recall"]
        tq = [r["correct"] for r in rows if r["respondent"] == rp and r["kind"] == "transfer"]
        by_resp[rp] = {"recall_acc": round(float(np.mean(rq)), 3) if rq else None,
                       "transfer_acc": round(float(np.mean(tq)), 3) if tq else None,
                       "n_recall": len(rq), "n_transfer": len(tq)}

    bridge_holds = (transfer_acc < recall_acc
                    and p_transfer_given_recall is not None and p_transfer_given_recall < 0.95)

    result = {
        "respondents": respondents,
        "human_respondents": [r for r in respondents if not r.startswith("llm:")],
        "n_concepts": len(per), "n_paired_observations": n_pairs,
        "recall_acc": round(recall_acc, 3), "transfer_acc": round(transfer_acc, 3),
        "memory_minus_performance_gap": round(recall_acc - transfer_acc, 3),
        "p_transfer_given_recall_correct": None if p_transfer_given_recall is None else round(p_transfer_given_recall, 3),
        "p_transfer_given_recall_wrong": None if p_transfer_given_wrong is None else round(p_transfer_given_wrong, 3),
        "mcnemar": {"recall_right_transfer_wrong": b, "recall_wrong_transfer_right": c,
                    "exact_two_sided_p": round(mcnemar_p, 4)},
        "concept_rate_correlation": None if corr is None else round(corr, 3),
        "by_respondent": by_resp,
        "by_concept": concept_rows,
        "bridge_supported": bool(bridge_holds),
        "interpretation": ("Transfer accuracy is below recall accuracy and recalling the fact does "
                           "NOT guarantee applying it (conditional < 1): memory and performance are "
                           "distinct, so the performance layer measures something the memory layer "
                           "cannot. Readiness confidence bands sit downstream of this."),
        "honesty": ("Real matched items + real graded responses; no fabricated data. Human rows are "
                    "the primary claim; llm:* rows are a real non-human respondent used to demonstrate "
                    "the pipeline and pattern when human n is small. Paywalled banks not required."),
    }
    (OUT / "perf_bridge.json").write_text(json.dumps(result, indent=2))
    print(f"[bridge] respondents={respondents} concepts={result['n_concepts']} pairs={n_pairs}")
    print(f"[bridge] recall={result['recall_acc']} transfer={result['transfer_acc']} "
          f"gap={result['memory_minus_performance_gap']} "
          f"| P(transfer|recall right)={result['p_transfer_given_recall_correct']} "
          f"| McNemar b={b} c={c} p={result['mcnemar']['exact_two_sided_p']} "
          f"| corr(recall,transfer)={result['concept_rate_correlation']} "
          f"| bridge_supported={result['bridge_supported']}")
    return result


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd = args[0]
    if cmd == "run_llm":
        run_llm(int(args[1]) if len(args) > 1 else 5)
    elif cmd == "quiz":
        quiz(args[1] if len(args) > 1 else "subject")
    elif cmd == "analyze":
        analyze()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
