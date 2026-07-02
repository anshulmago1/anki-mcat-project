"""Test-drive setup: import the real MileDown MCAT deck, map its hierarchical
tags to our mcat::<section>::<topic> scheme, and pre-seed realistic FSRS history
so the readiness engine shows live scores on real cards.

MileDown tags look like `MileDown::Biochemistry::Amino_Acids`, so we map by the
subject/topic path (no fragile keyword guessing needed for the section).

Builds everything into a dedicated Anki base dir so your real profile is untouched:
    <root>/mcat_base/User 1/collection.anki2
Then launch with:  cd anki && ./run -b <root>/mcat_base

Usage: python build_real_deck.py
"""
from __future__ import annotations

import random
import time
from pathlib import Path

from common import ROOT, add_anki_to_path, load_outline

APKG = ROOT / "data" / "decks" / "MileDown.apkg"
BASE = ROOT / "mcat_base"
COLL = BASE / "User 1" / "collection.anki2"
DAY = 86400

# MileDown subject (tag component [1]) -> our section
SUBJECT_SECTION = {
    "Biochemistry": "BB", "Biology": "BB",
    "General_Chemistry": "CP", "Physics": "CP", "OChem": "CP", "Organic_Chemistry": "CP",
    "Behavioral": "PS",
}

# keyword (found anywhere in the MileDown tag path, lowercased) -> our topic id.
# first match wins; order matters (specific before generic).
TOPIC_RULES = [
    # BB
    ("amino_acid", "mcat::bb::amino_acids_proteins"), ("protein", "mcat::bb::amino_acids_proteins"),
    ("enzyme", "mcat::bb::enzymes"),
    ("dna", "mcat::bb::nucleic_acids"), ("rna", "mcat::bb::nucleic_acids"), ("nucleic", "mcat::bb::nucleic_acids"),
    ("metabolism", "mcat::bb::metabolism"), ("carbohydrate", "mcat::bb::metabolism"), ("lipid_metab", "mcat::bb::metabolism"),
    ("membrane", "mcat::bb::cell_biology"), ("biosignaling", "mcat::bb::cell_biology"), ("lipid", "mcat::bb::cell_biology"), ("cell", "mcat::bb::cell_biology"),
    ("genetic", "mcat::bb::genetics"), ("hered", "mcat::bb::genetics"),
    ("microbio", "mcat::bb::microbiology"), ("virus", "mcat::bb::microbiology"),
    ("organ", "mcat::bb::organ_systems"), ("physiol", "mcat::bb::organ_systems"), ("system", "mcat::bb::organ_systems"),
    # CP - general chem / physics
    ("atomic", "mcat::cp::atomic_structure"), ("nuclear", "mcat::cp::atomic_structure"),
    ("bonding", "mcat::cp::bonding"),
    ("thermo", "mcat::cp::thermodynamics"), ("energy", "mcat::cp::thermodynamics"), ("work", "mcat::cp::thermodynamics"), ("gas", "mcat::cp::thermodynamics"),
    ("kinetic", "mcat::cp::kinetics"), ("equilibr", "mcat::cp::kinetics"),
    ("acid", "mcat::cp::acids_bases"), ("base", "mcat::cp::acids_bases"),
    ("electrochem", "mcat::cp::electrochemistry"), ("solution", "mcat::cp::electrochemistry"),
    ("circuit", "mcat::cp::electrostatics_circuits"), ("electrostat", "mcat::cp::electrostatics_circuits"), ("magnet", "mcat::cp::electrostatics_circuits"),
    ("light", "mcat::cp::optics_sound"), ("optic", "mcat::cp::optics_sound"), ("wave", "mcat::cp::optics_sound"), ("sound", "mcat::cp::optics_sound"),
    ("mechanic", "mcat::cp::mechanics"), ("kinematic", "mcat::cp::mechanics"), ("dynamic", "mcat::cp::mechanics"), ("fluid", "mcat::cp::mechanics"), ("motion", "mcat::cp::mechanics"),
    # PS - behavioral
    ("sensation", "mcat::ps::sensation_perception"), ("perception", "mcat::ps::sensation_perception"), ("attention", "mcat::ps::sensation_perception"),
    ("learning", "mcat::ps::learning_memory"), ("memory", "mcat::ps::learning_memory"),
    ("cognition", "mcat::ps::cognition_language"), ("language", "mcat::ps::cognition_language"), ("consciousness", "mcat::ps::cognition_language"), ("intelligence", "mcat::ps::cognition_language"),
    ("motivation", "mcat::ps::motivation_emotion"), ("emotion", "mcat::ps::motivation_emotion"), ("stress", "mcat::ps::motivation_emotion"),
    ("identity", "mcat::ps::identity_personality"), ("personality", "mcat::ps::identity_personality"), ("development", "mcat::ps::identity_personality"), ("disorder", "mcat::ps::identity_personality"),
    ("stratification", "mcat::ps::social_structure"), ("social_structure", "mcat::ps::social_structure"), ("demographic", "mcat::ps::demographics_inequality"), ("inequal", "mcat::ps::demographics_inequality"),
    ("social", "mcat::ps::social_processes"), ("behavior", "mcat::ps::social_processes"), ("attitude", "mcat::ps::social_processes"),
]

# section -> a default topic when subject is known but no keyword matched
SECTION_DEFAULT = {
    "BB": "mcat::bb::cell_biology",
    "CP": "mcat::cp::mechanics",
    "PS": "mcat::ps::social_processes",
}


def map_tag(md_tag: str) -> str | None:
    parts = md_tag.split("::")
    if len(parts) < 2 or parts[0] != "MileDown":
        return None
    section = SUBJECT_SECTION.get(parts[1])
    if not section:
        return None
    path = "::".join(parts[2:]).lower()
    for kw, topic in TOPIC_RULES:
        if kw in path:
            # only accept a topic that belongs to this section
            if topic.split("::")[1] == section.lower():
                return topic
    return SECTION_DEFAULT.get(section)


def main() -> None:
    add_anki_to_path()
    from anki.collection import Collection, ImportAnkiPackageRequest
    from anki.cards import FSRSMemoryState

    if BASE.exists():
        import shutil
        shutil.rmtree(BASE)
    (BASE / "User 1").mkdir(parents=True)

    col = Collection(str(COLL))
    col.set_config("fsrs", True)
    print("importing MileDown (227MB, ~1 min)...")
    col.import_anki_package(ImportAnkiPackageRequest(package_path=str(APKG)))
    print(f"imported: {col.note_count()} notes, {col.card_count()} cards")

    # --- map MileDown tags -> our scheme, grouped for efficient bulk tagging ---
    groups: dict[str, list[int]] = {}
    for nid in col.find_notes(""):
        note = col.get_note(nid)
        target = None
        for t in note.tags:
            target = map_tag(t)
            if target:
                break
        if target:
            groups.setdefault(target, []).append(nid)
    for topic, nids in groups.items():
        col.tags.bulk_add(nids, topic)
    print(f"tagged {sum(len(v) for v in groups.values())} notes across {len(groups)} topics")

    # --- pre-seed FSRS memory + reps + performance so BB/CP/PS pass the gate ---
    g = random.Random(7)
    now = int(time.time())
    section_reviews = {"BB": 0, "CP": 0, "PS": 0, "CARS": 0}
    target_reviews = 260  # comfortably above the 200 give-up threshold
    for section in ("BB", "CP", "PS"):
        # cards whose note carries any tag for this section
        cids = list(col.find_cards(f'"tag:mcat::{section.lower()}::*"'))
        g.shuffle(cids)
        batch = []
        for cid in cids:
            if section_reviews[section] >= target_reviews:
                break
            card = col.get_card(cid)
            stability = float(min(400.0, max(2.0, g.lognormvariate(2.4, 0.7))))
            days_since = g.choice([0, 1, 2, 4, 7, 14, 21, 35])  # varied -> forgetting visible
            reps = g.randint(2, 5)
            card.memory_state = FSRSMemoryState(stability=stability, difficulty=float(g.uniform(4, 7)))
            card.decay = 0.2
            card.last_review_time = now - days_since * DAY
            card.reps = reps
            batch.append(card)
            section_reviews[section] += reps
        col.update_cards(batch)
        print(f"  seeded {section}: {len(batch)} cards, ~{section_reviews[section]} graded reviews")

    # performance from "in-app question checks" (theta_se passes at total>=8)
    col.set_config("mcat_perf", {
        "BB": {"correct": 19, "total": 26},
        "CP": {"correct": 17, "total": 25},
        "PS": {"correct": 20, "total": 27},
        # CARS intentionally omitted -> stays withheld (MileDown has no CARS)
    })

    _report(col)
    col.close()
    print(f"\n[done] launch with:  cd anki && ./run -b '{BASE}'")


def _report(col) -> None:
    """Quick engine check that BB/CP/PS score and CARS abstains."""
    from anki import stats_pb2
    outline = load_outline()
    secs = []
    for s, b in outline["sections"].items():
        tw = {t["id"]: t["weight"] for t in b["topics"]}
        perf = col.get_config("mcat_perf", {}).get(s, {})
        total = perf.get("total", 0)
        p_s = (perf.get("correct", 0) / total) if total else 0.0
        se = (1.5 / (total + 1) ** 0.5) if total else 9.9
        secs.append(stats_pb2.ReadinessSectionInput(
            section=s, topic_prefix=f"mcat::{s.lower()}", topic_weights=tw,
            performance=p_s, theta_se=se, alpha_space=1.0, alpha_inter=1.3, alpha_test=1.5))
    params = stats_pb2.ReadinessParams(b0=-1.0, b_m=1.3, b_p=2.2, b_c=0.5,
                                       min_graded_reviews=200, min_coverage=0.5, max_irt_se=0.5)
    r = col._backend.compute_readiness(search="", mastered_threshold=0.7, sections=secs, params=params)
    print("\n=== engine readiness on the real deck ===")
    for s in r.sections:
        rd = "WITHHELD" if s.readiness.abstained else f"{s.readiness.value:.0f} [{s.readiness.range_lo:.0f}-{s.readiness.range_hi:.0f}]"
        print(f"  {s.section}: coverage {s.memory.coverage_pct:.0f}% | mem {s.memory.value:.2f} | reviews {s.memory.graded_reviews} | readiness {rd}")
    t = r.total
    print(f"  TOTAL: {'WITHHELD ('+','.join(t.missing)+')' if t.abstained else f'{t.value:.0f} [{t.range_lo:.0f}-{t.range_hi:.0f}]'}")
    print(f"  next actions: {len(r.next_actions)} (top: {r.next_actions[0].action_type} {r.next_actions[0].section} {r.next_actions[0].topic_id.split('::')[-1] if r.next_actions[0].topic_id else ''})" if r.next_actions else "  next actions: none")


if __name__ == "__main__":
    main()
