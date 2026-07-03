"""Graph-guided targeted card generation (AI x knowledge graph).

Closes the diagnose->remediate loop:
  1. DIAGNOSE - ask the engine's TopicGraph RPC which nodes are learning_ready
     (prerequisites mastered) but not yet mastered, ranked by points-at-stake.
     These are exactly the highest-value topics you can productively study now.
  2. GENERATE - for each target node, RAG-generate source-grounded cards for its
     concepts (reusing the same grounded generator + injection guard as `make ai`).
  3. CHECK - run every card through the gold-set checker; keep only CORRECT cards.
  4. EXPORT - write the passing cards to an importable, tagged .apkg.

Runs under Anki's Python (needs the engine for TopicGraph + apkg export). The AI
helpers are numpy-free here (TfidfRetriever is not used; we pass the node's
on-topic source passages directly).

Usage: ../anki/out/pyenv/bin/python ai/targeted_gen.py [collection.anki2]
  (defaults to the seeded mcat_base collection; the app must be CLOSED so the
   collection isn't locked).
Outputs: data/ai/MCAT_Targeted.apkg + data/ai/targeted_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # analysis/ for common
sys.path.insert(0, str(Path(__file__).resolve().parent))       # ai/ for aicommon/generate/checker

from common import DATA, ROOT, add_anki_to_path  # noqa: E402

GRAPH = DATA / "knowledge_graph.json"
AI = DATA / "ai"
TOP_N = 3               # number of target nodes to remediate
CARDS_PER_NODE = 3      # max concepts (cards) generated per target node
MASTERY_THRESHOLD = 0.7


def default_collection() -> Path:
    for cand in (ROOT / "mcat_base" / "User 1" / "collection.anki2",
                 DATA / "demo" / "mcat_demo.anki2"):
        if cand.exists():
            return cand
    return ROOT / "mcat_base" / "User 1" / "collection.anki2"


def graph_state(col_path: Path):
    """Call the engine TopicGraph RPC on a live collection -> per-node state."""
    add_anki_to_path()
    from anki.collection import Collection
    from anki import stats_pb2

    g = json.loads(GRAPH.read_text())
    nodes = [stats_pb2.TopicGraphNode(id=n["id"], section=n["section"],
                                      label=n["label"], weight=n["weight"]) for n in g["nodes"]]
    edges = [stats_pb2.TopicGraphEdge(**{"from": e["from"], "to": e["to"]})
             for e in g["edges"] if e["type"] == "prereq"]

    col = Collection(str(col_path))
    try:
        resp = col._backend.topic_graph(
            search="", topic_prefix="mcat", mastered_threshold=0.7,
            mastery_threshold=MASTERY_THRESHOLD, nodes=nodes, prereq_edges=edges)
    finally:
        col.close()

    out = []
    for n in resp.nodes:
        out.append({
            "id": n.id, "section": n.section, "label": n.label, "weight": n.weight,
            "covered": n.covered, "mastered": n.mastered, "learning_ready": n.learning_ready,
            "points_at_stake": n.points_at_stake, "mean_retrievability": n.mean_retrievability,
            "card_count": n.card_count, "unmet_prereqs": list(n.unmet_prereqs),
        })
    return out, list(resp.recommended_path)


def rank_candidates(nodes: list[dict]) -> list[dict]:
    """Graph's remediation priority list: learning_ready AND not mastered, ranked by
    points-at-stake. Uncovered-but-ready nodes (blind spots) score full weight."""
    cand = [n for n in nodes if n["learning_ready"] and not n["mastered"]]
    cand.sort(key=lambda n: n["points_at_stake"], reverse=True)
    return cand


def on_topic_passages(sources: dict, topic: str, k: int = 3) -> list[dict]:
    return [p for p in sources["passages"] if p.get("topic") == topic][:k]


def generate_for_topic(topic: str, sources: dict, gold: list[dict],
                       cards_per: int = CARDS_PER_NODE) -> list[dict]:
    """Generate + check grounded cards for ONE topic; return only CORRECT cards.
    Shared by the CLI pipeline and the in-app one-click hook (no collection I/O)."""
    import checker
    concepts = [g["concept"] for g in gold if g["topic"] == topic][:cards_per]
    passages = on_topic_passages(sources, topic)
    if not concepts or not passages:
        return []
    cards = [gen_card(c, topic, passages) for c in concepts]
    res = checker.run_over(cards)
    src_name = sources.get("source_name", "")
    passing = []
    for card, d in zip(cards, res["detail"]):
        if d["label"] == "correct":
            passing.append({"front": card["front"], "back": card["back"], "topic": topic,
                            "citation": card["citation"], "concept": card["concept"],
                            "source": src_name})
    return passing


def gen_card(concept: str, topic: str, passages: list[dict]) -> dict:
    """Grounded generation (no TfidfRetriever): same prompt/guard as `make ai`."""
    from generate import build_prompt
    from aicommon import extract_json, ollama_generate

    prompt = build_prompt(concept, passages)
    raw = ollama_generate(prompt)
    card = extract_json(raw) or {}
    front = str(card.get("front", "")).strip()
    back = str(card.get("back", "")).strip()
    cit = str(card.get("citation", "")).strip()
    if not front or not back:
        raw = ollama_generate(prompt + "\nRespond with ONLY the JSON object, no prose, no code fences.",
                              seed=8)
        card = extract_json(raw) or {}
        front = str(card.get("front", "")).strip() or front
        back = str(card.get("back", "")).strip() or back
        cit = str(card.get("citation", "")).strip() or cit
    valid = {p["id"] for p in passages}
    if cit not in valid and passages:
        cit = passages[0]["id"]
    return {"method": "llm", "topic": topic, "concept": concept,
            "front": front, "back": back, "citation": cit}


def export_apkg(passing: list[dict]) -> Path:
    add_anki_to_path()
    from anki.collection import Collection
    from ai_export import _export

    work = AI / "targeted_cards.anki2"
    work.parent.mkdir(parents=True, exist_ok=True)
    if work.exists():
        work.unlink()
    col = Collection(str(work))
    deck_id = col.decks.id("MCAT::AI-Targeted (graph-guided)")
    for c in passing:
        note = col.newNote()
        note["Front"] = c["front"]
        note["Back"] = (f"{c['back']}\n\n<small>Targeted remediation for "
                        f"{c['topic']} \u00b7 Source: {c.get('source','')} \u00a7{c.get('citation','')}</small>")
        note.tags = [c["topic"], "mcat::ai_targeted"]
        col.add_note(note, deck_id)
    apkg = AI / "MCAT_Targeted.apkg"
    if apkg.exists():
        apkg.unlink()
    _export(col, str(apkg))
    col.close()
    return apkg


def main() -> None:
    from aicommon import die_if_no_ollama, load_gold, load_sources
    import checker

    col_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_collection()
    if not col_path.exists():
        print(f"[targeted] collection not found: {col_path}\n"
              f"Seed one with analysis/seed_live_demo.py first.")
        sys.exit(1)
    die_if_no_ollama()

    nodes, rec_path = graph_state(col_path)
    cand = rank_candidates(nodes)
    if not cand:
        print("[targeted] no learning_ready, unmastered nodes to remediate (all mastered or blocked).")
        sys.exit(0)

    sources = load_sources()
    gold = load_gold()
    src_name = sources.get("source_name", "")

    def generatable(t: dict) -> bool:
        return (any(g["topic"] == t["id"] for g in gold)
                and bool(on_topic_passages(sources, t["id"])))

    # The graph's true top priorities (for transparency), and the top-N we can
    # actually remediate now (have a gold concept + grounding source).
    top_priorities = [{"node": t["id"], "points_at_stake": round(t["points_at_stake"], 3),
                       "covered": t["covered"], "generatable": generatable(t)} for t in cand[:TOP_N]]
    targets = [t for t in cand if generatable(t)][:TOP_N]
    if not targets:
        print("[targeted] top-priority nodes have no source corpus yet; nothing to generate.")
        sys.exit(0)

    all_cards: list[dict] = []
    per_target: list[dict] = []
    for t in targets:
        concepts = [g["concept"] for g in gold if g["topic"] == t["id"]][:CARDS_PER_NODE]
        passages = on_topic_passages(sources, t["id"])
        tcards = [gen_card(c, t["id"], passages) for c in concepts] if passages else []
        all_cards.extend(tcards)
        per_target.append({
            "node": t["id"], "label": t["label"], "section": t["section"],
            "points_at_stake": round(t["points_at_stake"], 3),
            "covered": t["covered"], "mean_retrievability": round(t["mean_retrievability"], 3),
            "reason": "cover blind spot (no cards yet)" if not t["covered"] else "reinforce weak topic",
            "concepts": concepts, "has_source": bool(passages), "generated": len(tcards),
        })

    res = checker.run_over(all_cards)
    passing = []
    passed_by_topic: dict[str, int] = {}
    for card, d in zip(all_cards, res["detail"]):
        if d["label"] == "correct":
            passing.append({"front": card["front"], "back": card["back"], "topic": card["topic"],
                            "citation": card["citation"], "concept": card["concept"], "source": src_name})
            passed_by_topic[card["topic"]] = passed_by_topic.get(card["topic"], 0) + 1
    for pt in per_target:
        pt["passed"] = passed_by_topic.get(pt["node"], 0)

    apkg = export_apkg(passing) if passing else None
    report = {
        "collection": str(col_path),
        "top_priorities": top_priorities,
        "targets_selected": [t["id"] for t in targets],
        "targets": per_target,
        "recommended_path_head": rec_path[:5],
        "generated": len(all_cards), "passed": len(passing),
        "checker_tally": res["tally"],
        "apkg": str(apkg) if apkg else None,
        "note": ("Targets are the graph's learning_ready, unmastered nodes ranked by "
                 "points-at-stake. Only checker-CORRECT, source-grounded cards are exported."),
    }
    (AI / "targeted_report.json").write_text(json.dumps(report, indent=2))

    print(f"[targeted] targets={[t['id'].split('::')[-1] for t in targets]} "
          f"generated={len(all_cards)} passed={len(passing)} "
          f"tally={res['tally']}"
          + (f" -> {apkg}" if apkg else " (no passing cards to export)"))


if __name__ == "__main__":
    main()
