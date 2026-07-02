#!/usr/bin/env python3
"""Generate the OUTLINE / SECTION_NAMES maps in the desktop (Svelte) and
Android (Kotlin) readiness UIs from the single source of truth,
`data/aamc_outline.json`.

Both surfaces render the same AAMC content outline. Keeping three hand-written
copies in sync is error prone, so this script rewrites the region between the
`OUTLINE-GEN` marker comments in each file. The Rust engine and the Python
harness already read the JSON directly, so after running this the JSON is the
only place topic weights are defined.

Usage:
    python analysis/gen_outline_maps.py            # rewrite the maps in place
    python analysis/gen_outline_maps.py --check    # fail if anything is stale
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTLINE_JSON = ROOT / "data" / "aamc_outline.json"
SVELTE = ROOT / "anki" / "ts" / "routes" / "graphs" / "ReadinessCard.svelte"
KOTLIN = (
    ROOT
    / "Anki-Android"
    / "AnkiDroid"
    / "src"
    / "main"
    / "java"
    / "com"
    / "ichi2"
    / "anki"
    / "McatReadinessActivity.kt"
)

START = "<OUTLINE-GEN>"
END = "</OUTLINE-GEN>"


def load_outline() -> dict:
    return json.loads(OUTLINE_JSON.read_text())


def _fmt(w: float) -> str:
    # keep trailing precision compact but exact (0.1 not 0.10) for TS/JSON
    return ("%g" % round(float(w), 4))


def svelte_block(outline: dict) -> str:
    secs = outline["sections"]
    lines = [
        f"    // {START} generated from data/aamc_outline.json by analysis/gen_outline_maps.py -- do not edit by hand",
        "    const SECTION_NAMES: Record<string, string> = {",
    ]
    for code, sec in secs.items():
        lines.append(f'        {code}: "{sec["short_name"]}",')
    lines.append("    };")
    lines.append("")
    lines.append("    // AAMC outline weights (section -> {topic_id: within-section weight}).")
    lines.append("    const OUTLINE: Record<string, Record<string, number>> = {")
    for code, sec in secs.items():
        lines.append(f"        {code}: {{")
        for t in sec["topics"]:
            lines.append(f'            "{t["id"]}": {_fmt(t["weight"])},')
        lines.append("        },")
    lines.append("    };")
    lines.append(f"    // {END}")
    return "\n".join(lines)


def kotlin_block(outline: dict) -> str:
    secs = outline["sections"]
    lines = [
        f"        // {START} generated from data/aamc_outline.json by analysis/gen_outline_maps.py -- do not edit by hand",
        "        val SECTION_NAMES =",
        "            mapOf(",
    ]
    for code, sec in secs.items():
        lines.append(f'                "{code}" to "{sec["short_name"]}",')
    lines.append("            )")
    lines.append("")
    lines.append("        // AAMC outline weights (section -> {topic_id: within-section weight}).")
    lines.append("        val OUTLINE: Map<String, Map<String, Float>> =")
    lines.append("            mapOf(")
    for code, sec in secs.items():
        lines.append(f'                "{code}" to')
        lines.append("                    mapOf(")
        for t in sec["topics"]:
            lines.append(f'                        "{t["id"]}" to {_fmt(t["weight"])}f,')
        lines.append("                    ),")
    lines.append("            )")
    lines.append(f"        // {END}")
    return "\n".join(lines)


def replace_region(text: str, new_block: str) -> str:
    pattern = re.compile(
        r"[^\n]*" + re.escape(START) + r".*?" + re.escape(END) + r"[^\n]*",
        re.DOTALL,
    )
    if not pattern.search(text):
        raise SystemExit(f"markers {START}/{END} not found")
    return pattern.sub(lambda _m: new_block, text, count=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if files are stale")
    args = ap.parse_args()

    outline = load_outline()
    targets = [(SVELTE, svelte_block(outline)), (KOTLIN, kotlin_block(outline))]

    stale = []
    for path, block in targets:
        if not path.exists():
            print(f"skip (missing): {path}")
            continue
        current = path.read_text()
        updated = replace_region(current, block)
        if updated != current:
            stale.append(path)
            if not args.check:
                path.write_text(updated)
                print(f"updated: {path.relative_to(ROOT)}")
        else:
            print(f"in sync: {path.relative_to(ROOT)}")

    if args.check and stale:
        print("\nOUTLINE maps are STALE. Run: python analysis/gen_outline_maps.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
