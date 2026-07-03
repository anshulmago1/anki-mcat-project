"""Two-device sync test through a real local Anki sync server (Speedrun 7b).

1. Base deck is uploaded to a self-hosted sync server; a second collection
   downloads it (two "devices", one engine).
2. OFFLINE: device A reviews 10 cards, device B reviews 10 DIFFERENT cards.
3. Reconnect and sync both. Assert all 20 reviews land in one place, none lost,
   none double-counted (revlog is unioned by unique id; both devices converge).
4. CONFLICT: both devices edit the SAME card offline; after sync the object-level
   last-write-wins-by-modification-time rule picks the later edit on both devices
   (documented in docs/SYNC.md).

Run: `../anki/out/pyenv/bin/python sync_test.py`. Outputs data/eval/sync_test.json.
Uses Anki's built-in Rust sync server, i.e. the same engine that ships to the phone.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path

from common import ANKI, DATA, add_anki_to_path, load_outline

OUT = DATA / "eval"
SYNC = DATA / "sync"
USER, PW = "tester", "pw"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_server(port: int, base: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env["SYNC_USER1"] = f"{USER}:{PW}"
    env["SYNC_BASE"] = str(base)
    env["SYNC_HOST"] = "127.0.0.1"
    env["SYNC_PORT"] = str(port)
    env["PYTHONPATH"] = f"{ANKI / 'out' / 'pylib'}:{ANKI / 'pylib'}"
    env["MAX_SYNC_PAYLOAD_MEGS"] = "1000"
    proc = subprocess.Popen(
        [os.sys.executable, "-c", "from anki.syncserver import run_sync_server; run_sync_server()"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # wait until the port accepts connections
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.25)
    time.sleep(0.5)
    return proc


def new_col(path: Path):
    from anki.collection import Collection
    if path.exists():
        path.unlink()
    col = Collection(str(path))
    col.set_config("fsrs", True)
    return col


def open_col(path: Path):
    from anki.collection import Collection
    return Collection(str(path))


def do_sync(col, auth):
    """Run a sync, handling first-time full upload/download. Returns the action."""
    out = col.sync_collection(auth, sync_media=False)
    req = out.required
    # 3 = FULL_DOWNLOAD, 4 = FULL_UPLOAD, 2 = FULL_SYNC (choose upload by default)
    if req in (2, 3, 4):
        upload = req != 3  # download only when server has data and we don't
        col.full_upload_or_download(auth=auth, server_usn=out.server_media_usn, upload=upload)
        return "full_upload" if upload else "full_download"
    return {0: "no_changes", 1: "normal"}.get(req, str(req))


def revlog_count(col) -> int:
    return col.db.scalar("select count() from revlog") or 0


def reviewed_card_ids(col) -> set[int]:
    return set(col.db.list("select distinct cid from revlog"))


def review_from_deck(col, deck_name: str, n: int) -> list[int]:
    """Review n cards from a specific deck via the normal scheduler queue (reliable
    and deterministic). Returns the reviewed card ids. Two devices use two disjoint
    subdecks so their offline reviews never overlap."""
    did = col.decks.id(deck_name)
    col.decks.set_current(did)
    conf = col.decks.config_dict_for_deck_id(did)
    conf["new"]["perDay"] = 1000
    conf["rev"]["perDay"] = 1000
    col.decks.update_config(conf)
    done = []
    for _ in range(n):
        c = col.sched.getCard()
        if c is None:
            break
        col.sched.answerCard(c, 3)
        done.append(c.id)
    return done


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    add_anki_to_path()
    SYNC.mkdir(parents=True, exist_ok=True)
    port = free_port()
    server = start_server(port, SYNC / "server")
    endpoint = f"http://127.0.0.1:{port}/"
    result = {"endpoint": endpoint}
    try:
        outline = load_outline()
        topics = [t["id"] for s in outline["sections"].values() for t in s["topics"]]

        # --- device A: base deck (two disjoint subdecks), upload ---
        colA = new_col(SYNC / "deviceA.anki2")
        did_a = colA.decks.id("MCAT::Sync::DeviceA")
        did_b = colA.decks.id("MCAT::Sync::DeviceB")
        for i in range(30):
            n = colA.newNote(); n["Front"] = f"qA{i}"; n["Back"] = "a"
            n.tags = [topics[i % len(topics)]]
            colA.add_note(n, did_a)
        for i in range(30):
            n = colA.newNote(); n["Front"] = f"qB{i}"; n["Back"] = "a"
            n.tags = [topics[i % len(topics)]]
            colA.add_note(n, did_b)
        authA = colA.sync_login(USER, PW, endpoint)
        result["A_first_sync"] = do_sync(colA, authA)

        # --- device B: download the same collection ---
        colB = new_col(SYNC / "deviceB.anki2")
        authB = colB.sync_login(USER, PW, endpoint)
        result["B_first_sync"] = do_sync(colB, authB)
        colB.close()
        colB = open_col(SYNC / "deviceB.anki2")  # reopen after full download

        base_rev = revlog_count(colA)

        # --- OFFLINE: disjoint reviews on each device (A studies DeviceA subdeck,
        #     B studies DeviceB subdeck -> different cards, no overlap) ---
        a_done = review_from_deck(colA, "MCAT::Sync::DeviceA", 10)
        b_done = review_from_deck(colB, "MCAT::Sync::DeviceB", 10)
        expected = set(a_done) | set(b_done)

        # --- reconnect + sync both ways ---
        do_sync(colA, authA)               # push A's 10
        do_sync(colB, authB)               # pull A's 10, push B's 10
        do_sync(colA, authA)               # pull B's 10

        a_rev, b_rev = revlog_count(colA), revlog_count(colB)
        a_ids, b_ids = reviewed_card_ids(colA), reviewed_card_ids(colB)
        # unique revlog ids == row count -> nothing double-counted
        a_unique = colA.db.scalar("select count(distinct id) from revlog") or 0
        b_unique = colB.db.scalar("select count(distinct id) from revlog") or 0

        merge = {
            "reviewed_on_A": len(a_done), "reviewed_on_B": len(b_done),
            "revlog_A": a_rev, "revlog_B": b_rev,
            "converged": a_rev == b_rev,
            "all_20_present_both": expected.issubset(a_ids) and expected.issubset(b_ids),
            "no_double_count_A": a_rev == a_unique,
            "no_double_count_B": b_rev == b_unique,
            "gained_20": (a_rev - base_rev) == 20,
        }
        merge["pass"] = (merge["converged"] and merge["all_20_present_both"]
                         and merge["no_double_count_A"] and merge["no_double_count_B"]
                         and merge["gained_20"])

        # --- CONFLICT: both edit the same card's note offline; later mod wins ---
        # pick a card both sides have but neither reviewed (avoid the studied sets)
        studied = set(a_done) | set(b_done)
        pool = [c for c in colA.find_cards("deck:MCAT::Sync::*") if c not in studied]
        conflict_cid = pool[0]
        nidA = colA.get_card(conflict_cid).nid
        nidB = colB.get_card(conflict_cid).nid
        nB = colB.get_note(nidB); nB["Front"] = "EDIT_B"; colB.update_note(nB)
        time.sleep(1.1)  # ensure A's edit has a strictly later modification time
        nA = colA.get_note(nidA); nA["Front"] = "EDIT_A"; colA.update_note(nA)
        do_sync(colB, authB)   # push B's edit first
        do_sync(colA, authA)   # push A's edit (later mod -> wins)
        do_sync(colB, authB)   # pull the resolved value
        winner_A = colA.get_note(nidA)["Front"]
        winner_B = colB.get_note(nidB)["Front"]
        conflict = {
            "rule": "object-level last-write-wins by modification time",
            "later_edit": "EDIT_A", "winner_on_A": winner_A, "winner_on_B": winner_B,
            "pass": winner_A == "EDIT_A" and winner_B == "EDIT_A",
        }

        colA.close(); colB.close()
        result["merge"] = merge
        result["conflict"] = conflict
        result["passes"] = merge["pass"] and conflict["pass"]
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except Exception:
            server.kill()

    (OUT / "sync_test.json").write_text(json.dumps(result, indent=2))
    print(f"[sync] merge: A_rev={result.get('merge',{}).get('revlog_A')} "
          f"B_rev={result.get('merge',{}).get('revlog_B')} "
          f"all_20_both={result.get('merge',{}).get('all_20_present_both')} "
          f"no_double_count={result.get('merge',{}).get('no_double_count_A')} "
          f"| conflict winner={result.get('conflict',{}).get('winner_on_A')} "
          f"| overall pass={result.get('passes')}")
    return result


if __name__ == "__main__":
    run()
