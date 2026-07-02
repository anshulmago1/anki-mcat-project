"""Create a real Anki collection of MCAT-tagged cards with review history, so the
mastery query (Rust) and the dashboard can run end-to-end on the actual engine.

Coverage is intentionally uneven (BB/CP well covered, PS partial, CARS sparse) so
the give-up rule trips on the under-studied sections - exactly the scenario the
Speedrun spec wants the app to refuse to score.

Usage: python make_demo_collection.py [out_path]
Outputs a .anki2 collection (default data/demo/mcat_demo.anki2).
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

from common import DATA, add_anki_to_path, load_outline, all_topics

# how many cards per topic, per section (uneven on purpose)
SECTION_CARDS_PER_TOPIC = {"BB": 12, "CP": 11, "PS": 5, "CARS": 4}
# fraction of a topic's cards that get reviewed (rest stay "new")
SECTION_REVIEW_FRAC = {"BB": 0.95, "CP": 0.9, "PS": 0.6, "CARS": 0.4}
# fraction of a section's TOPICS that get any cards at all -> drives coverage.
# CARS deliberately below the 50% give-up threshold so it abstains on coverage.
SECTION_TOPIC_COVERAGE = {"BB": 1.0, "CP": 1.0, "PS": 0.625, "CARS": 0.34}


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "demo" / "mcat_demo.anki2"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    add_anki_to_path()
    from anki.collection import Collection

    col = Collection(str(out))
    g = random.Random(5)
    try:
        col.set_config("fsrs", True)
    except Exception:
        pass

    total, reviewed = 0, 0
    outline = load_outline()
    # decide which topics get cards, per section, to drive coverage
    covered_topics = set()
    for sec, body in outline["sections"].items():
        topics = [t["id"] for t in body["topics"]]
        k = max(1, round(len(topics) * SECTION_TOPIC_COVERAGE[sec]))
        covered_topics.update(topics[:k])

    for topic in all_topics(outline):
        if topic["id"] not in covered_topics:
            continue
        sec = topic["section"]
        n = SECTION_CARDS_PER_TOPIC[sec]
        for i in range(n):
            note = col.newNote()
            note["Front"] = f"{topic['label']} - probe {i}"
            note["Back"] = f"Answer for {topic['id']} #{i}"
            note.tags = [topic["id"]]
            col.addNote(note)
            total += 1

    # review a fraction of cards a few times to build memory states + revlog
    col.set_config("fsrs", True)
    rounds = 3
    for _ in range(rounds):
        col.reset()
        while True:
            c = col.sched.getCard()
            if c is None:
                break
            note = c.note()
            sec = _section_of(note.tags)
            rev_frac = SECTION_REVIEW_FRAC.get(sec, 0.5)
            if g.random() < rev_frac:
                # mostly "Good" (3) with some "Hard"/"Easy" variety
                rating = int(g.choice([2, 3, 3, 3, 4]))
                col.sched.answerCard(c, rating)
                reviewed += 1
            else:
                # bury so we stop pulling it this round
                col.sched.bury_cards([c.id])
        col.sched.unbury_deck(col.decks.get_current_id())

    col.save()
    n_with_state = _count_with_memory(col)
    col.close()
    print(f"[demo] wrote {out}")
    print(f"[demo] cards={total} reviews_made~={reviewed} cards_with_memory_state={n_with_state}")


def _section_of(tags: list[str]) -> str:
    for t in tags:
        parts = t.split("::")
        if len(parts) >= 2 and parts[0] == "mcat":
            return parts[1].upper()
    return "?"


def _count_with_memory(col) -> int:
    n = 0
    for cid in col.find_cards(""):
        c = col.get_card(cid)
        if getattr(c, "memory_state", None) is not None:
            n += 1
    return n


if __name__ == "__main__":
    main()
