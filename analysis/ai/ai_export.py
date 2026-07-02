"""Export the AI-generated cards that PASSED the checker into an importable
.apkg (Speedrun 7f: "export passing cards"). Uses the real Anki engine, so the
deck imports into desktop and AnkiDroid unchanged. Each card keeps its AAMC topic
tag and a note recording the grounding citation.

Run with Anki's Python: `../anki/out/pyenv/bin/python ai_export.py`
(the Makefile `ai` target wires this up as ANKI_PY).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import DATA, add_anki_to_path  # noqa: E402

PASSING = DATA / "ai" / "passing_cards.json"


def main() -> None:
    if not PASSING.exists():
        print(f"[ai.export] no passing cards at {PASSING}; run ai_eval first")
        return
    cards = json.loads(PASSING.read_text())
    add_anki_to_path()
    from anki.collection import Collection

    work = DATA / "ai" / "ai_cards.anki2"
    work.parent.mkdir(parents=True, exist_ok=True)
    if work.exists():
        work.unlink()
    col = Collection(str(work))
    deck_id = col.decks.id("MCAT::AI-Generated (grounded)")
    for c in cards:
        note = col.newNote()
        note["Front"] = c["front"]
        note["Back"] = f"{c['back']}\n\n<small>Source: {c.get('source','')} \u00a7{c.get('citation','')}</small>"
        note.tags = [c["topic"], "mcat::ai_generated"]
        col.add_note(note, deck_id)

    apkg = DATA / "ai" / "MCAT_AI_Generated.apkg"
    if apkg.exists():
        apkg.unlink()
    _export(col, str(apkg))
    col.close()
    print(f"[ai.export] {len(cards)} passing cards -> {apkg}")


def _export(col, out_path: str) -> None:
    try:
        from anki.collection import ExportAnkiPackageOptions
        from anki.generic_pb2 import Empty
        from anki.import_export_pb2 import ExportLimit
        col.export_anki_package(
            out_path=out_path,
            options=ExportAnkiPackageOptions(
                with_scheduling=False, with_deck_configs=True, with_media=False, legacy=True
            ),
            limit=ExportLimit(whole_collection=Empty()),
        )
    except Exception as e:
        print(f"[ai.export] modern export failed ({e}); using legacy exporter")
        from anki.exporting import AnkiPackageExporter
        exp = AnkiPackageExporter(col)
        exp.includeSched = False
        exp.includeMedia = False
        exp.exportInto(out_path)


if __name__ == "__main__":
    main()
