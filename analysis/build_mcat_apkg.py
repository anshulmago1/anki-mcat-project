"""Build a REAL (small, curated) MCAT flashcard deck, tagged per the AAMC outline,
and export it as an importable .apkg so you can try the app hands-on.

Coverage is intentionally uneven (BB/CP broad, PS partial, CARS sparse) so the
give-up rule visibly trips on the under-studied sections. A chunk of cards are
reviewed so FSRS memory states exist and the Memory score is non-trivial.

Usage: python build_mcat_apkg.py
Outputs: data/demo/MCAT_Readygauge_Demo.apkg  (+ the working .anki2 collection)
"""
from __future__ import annotations

import random
from pathlib import Path

from common import DATA, add_anki_to_path

# (topic_tag, front, back) - genuine MCAT facts across the four sections.
CARDS = [
    # --- B/B: Biological and Biochemical ---
    ("mcat::bb::amino_acids_proteins", "Which amino acids are positively charged (basic) at physiological pH?", "Lysine, Arginine, Histidine"),
    ("mcat::bb::amino_acids_proteins", "Which amino acid is achiral?", "Glycine (its R-group is H)"),
    ("mcat::bb::amino_acids_proteins", "What bond links amino acids in a protein?", "Peptide (amide) bond"),
    ("mcat::bb::enzymes", "How does a competitive inhibitor affect Km and Vmax?", "Increases apparent Km; Vmax unchanged"),
    ("mcat::bb::enzymes", "How does a noncompetitive inhibitor affect Km and Vmax?", "Km unchanged; decreases Vmax"),
    ("mcat::bb::enzymes", "At [S] = Km, what fraction of Vmax is the rate?", "One half (Vmax/2)"),
    ("mcat::bb::nucleic_acids", "In which direction is DNA synthesized?", "5' to 3'"),
    ("mcat::bb::nucleic_acids", "Which enzyme unwinds the DNA double helix?", "Helicase"),
    ("mcat::bb::metabolism", "Net ATP yield from glycolysis (per glucose)?", "2 ATP (and 2 NADH)"),
    ("mcat::bb::metabolism", "Where does the citric acid cycle occur?", "Mitochondrial matrix"),
    ("mcat::bb::metabolism", "Rate-limiting enzyme of glycolysis?", "Phosphofructokinase-1 (PFK-1)"),
    ("mcat::bb::cell_biology", "Function of the smooth endoplasmic reticulum?", "Lipid synthesis and detoxification"),
    ("mcat::bb::cell_biology", "Which organelle is the site of oxidative phosphorylation?", "Mitochondrion (inner membrane)"),
    ("mcat::bb::genetics", "In a dihybrid cross, expected phenotypic ratio?", "9:3:3:1"),
    ("mcat::bb::organ_systems", "Site of filtration in the nephron?", "Glomerulus (Bowman's capsule)"),
    ("mcat::bb::organ_systems", "Which node is the heart's pacemaker?", "Sinoatrial (SA) node"),
    # --- C/P: Chemical and Physical ---
    ("mcat::cp::thermodynamics", "Sign of delta-G for a spontaneous process?", "Negative"),
    ("mcat::cp::thermodynamics", "Relationship between delta-G, delta-H, delta-S?", "dG = dH - T*dS"),
    ("mcat::cp::kinetics", "What does a catalyst do to activation energy?", "Lowers it (does not change delta-G)"),
    ("mcat::cp::kinetics", "Effect of temperature on reaction rate (rule of thumb)?", "Rate roughly doubles per 10 C increase"),
    ("mcat::cp::acids_bases", "Henderson-Hasselbalch equation?", "pH = pKa + log([A-]/[HA])"),
    ("mcat::cp::acids_bases", "At the half-equivalence point of a titration, pH equals?", "pKa"),
    ("mcat::cp::atomic_structure", "Quantum number that determines orbital shape?", "Azimuthal / angular momentum (l)"),
    ("mcat::cp::bonding", "Hybridization of a carbon with one double bond?", "sp2"),
    ("mcat::cp::mechanics", "Work-energy theorem?", "Net work = change in kinetic energy"),
    ("mcat::cp::electrostatics_circuits", "Ohm's law?", "V = I * R"),
    ("mcat::cp::electrostatics_circuits", "Equivalent resistance of resistors in parallel?", "1/Req = sum(1/Ri)"),
    ("mcat::cp::optics_sound", "In which medium is the speed of sound greatest?", "Solids (then liquids, then gases)"),
    ("mcat::cp::organic_chemistry", "IR absorption near 1700 cm^-1 indicates?", "Carbonyl (C=O) stretch"),
    ("mcat::cp::organic_chemistry", "What does an SN1 reaction's rate depend on?", "Only the substrate concentration (first order)"),
    # --- P/S: Psychological, Social, Biological (partial coverage) ---
    ("mcat::ps::learning_memory", "Classical vs operant conditioning?", "Classical: involuntary stimulus association; Operant: behavior shaped by consequences"),
    ("mcat::ps::learning_memory", "What is the spacing effect?", "Better long-term retention from distributed vs massed practice"),
    ("mcat::ps::sensation_perception", "Weber's law states?", "The just-noticeable difference is a constant proportion of stimulus intensity"),
    ("mcat::ps::cognition_language", "Whorfian (linguistic relativity) hypothesis?", "Language influences thought/perception"),
    ("mcat::ps::social_processes", "What is the bystander effect?", "Individuals less likely to help when others are present"),
    # --- CARS: sparse on purpose (1 of 3 reasoning skills) -> coverage gate trips ---
    ("mcat::cars::reasoning_beyond_text", "CARS 'reasoning beyond the text' tasks ask you to?", "Apply, extrapolate, or assess the author's argument in a new context"),
]

# review the first N cards (mostly B/B and C/P) so memory states populate
REVIEW_FIRST = 22


def main() -> None:
    add_anki_to_path()
    from anki.collection import Collection

    work = DATA / "demo" / "mcat_demo.anki2"
    work.parent.mkdir(parents=True, exist_ok=True)
    if work.exists():
        work.unlink()

    col = Collection(str(work))
    col.set_config("fsrs", True)
    g = random.Random(5)

    deck_id = col.decks.id("MCAT::Readygauge Demo")
    note_ids = []
    for tag, front, back in CARDS:
        note = col.newNote()
        note["Front"] = front
        note["Back"] = back
        note.tags = [tag]
        col.add_note(note, deck_id)
        note_ids.append(note.id)

    # review a chunk so FSRS memory states + revlog exist
    col.set_config("fsrs", True)
    col.decks.set_current(deck_id)
    # raise the daily new-card limit so we can review the intended chunk
    conf = col.decks.config_dict_for_deck_id(deck_id)
    conf["new"]["perDay"] = 200
    conf["rev"]["perDay"] = 500
    col.decks.update_config(conf)
    reviewed = 0
    for _ in range(3):
        while True:
            c = col.sched.getCard()
            if c is None:
                break
            col.sched.answerCard(c, g.choice([3, 3, 3, 4]))
            reviewed += 1
            if reviewed >= REVIEW_FIRST:
                break
        if reviewed >= REVIEW_FIRST:
            break

    apkg = DATA / "demo" / "MCAT_Readygauge_Demo.apkg"
    if apkg.exists():
        apkg.unlink()
    _export_apkg(col, str(apkg))
    n_state = sum(1 for cid in col.find_cards("") if getattr(col.get_card(cid), "memory_state", None))
    col.close()
    print(f"[apkg] cards={len(CARDS)} reviewed={reviewed} with_memory_state={n_state}")
    print(f"[apkg] importable deck -> {apkg}")
    print(f"[apkg] working collection -> {work}")


def _export_apkg(col, out_path: str) -> None:
    """Export with scheduling (so review history / memory states survive import)."""
    try:
        from anki.collection import ExportAnkiPackageOptions
        from anki.import_export_pb2 import ExportLimit
        from anki.generic_pb2 import Empty
        col.export_anki_package(
            out_path=out_path,
            options=ExportAnkiPackageOptions(
                with_scheduling=True, with_deck_configs=True, with_media=False, legacy=True
            ),
            limit=ExportLimit(whole_collection=Empty()),
        )
    except Exception as e:
        # fall back to the legacy exporter
        print(f"[apkg] modern export failed ({e}); using legacy exporter")
        from anki.exporting import AnkiPackageExporter
        exp = AnkiPackageExporter(col)
        exp.includeSched = True
        exp.includeMedia = False
        exp.exportInto(out_path)


if __name__ == "__main__":
    main()
