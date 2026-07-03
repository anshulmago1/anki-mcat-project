# Sync & conflict resolution (Speedrun 7b)

The app inherits Anki's proven sync engine unchanged; the MCAT readiness features
add **no new synced state** of their own (readiness is *computed* on demand from
already-synced review history + card memory state + config), so sync correctness
reduces to Anki's existing guarantees plus one rule for our derived scores.

## What syncs, and how

Anki uses client↔server sync keyed by **USN** (Update Sequence Number). Every
object (note, card, deck, deck-config, tag, revlog entry) carries a USN; a client
sends everything changed since its last sync and receives the server's changes.

Two different merge behaviors matter:

1. **Review log (`revlog`) — union merge, never lost.** Each review is an
   append-only row with a unique millisecond-timestamp id. Reviews done offline on
   *either* device are distinct rows, so a normal (incremental) sync takes the
   **union** of both sides. No review is overwritten. Because our Memory score,
   points-at-stake, and the give-up rule are recomputed from the revlog + FSRS
   memory state, both devices converge to **identical readiness** after sync.

2. **Mutable objects (note text, card scheduling fields, deck config) —
   last-write-wins by modification time.** If the *same* card is edited on two
   devices while both are offline, the version with the later `mod` timestamp wins
   on the next incremental sync (object-level LWW; Anki does not do field-level
   merge). The losing edit to that object is discarded, but the review history of
   that card (point 1) is still unioned.

## Full-sync fallback (the data-loss trap, and how we avoid it)

If the collection **schema** changes (`scm`, e.g. adding/removing a notetype or a
"force full sync" action), Anki cannot do an incremental merge and requires a
**one-directional full sync**: you must pick **Upload** (local wins) or
**Download** (server wins). The non-chosen side's unsynced changes are lost.

This is the failure we reproduced on the phone: an offline AnkiDroid client that
fell back to a full **Download** lost its offline reviews. The mitigation is
operational, not a code change:

- **Sync before and after every study session** so neither side accumulates a
  large offline delta.
- **Never trigger a schema change** on one device while the other has unsynced
  reviews. Our fork adds no notetypes and no schema bumps, so normal use stays on
  the incremental path.
- If a full sync is unavoidable, sync the *most-reviewed* device with **Upload**
  first, then Download onto the other device.

## Our conflict rule for readiness

> **Readiness is a pure function of synced state.** After any incremental sync,
> both devices hold the same unioned revlog and the same (LWW-resolved) cards and
> config, so `compute_readiness` returns the same three scores and the same
> next-best-action list on desktop and phone. There is no separate "readiness
> document" to conflict — nothing to merge, nothing to lose.

The only quantity that can differ transiently is a same-card *edit* made offline
on both devices (LWW by `mod`); this changes at most that card's content, and its
review history is preserved regardless.

## Evidence

`analysis/sync_test.py` exercises 7b directly:

1. Two independent collections review **different** cards offline, then sync
   through a local sync server → the merged collection contains **all** reviews
   from both sides (union; zero loss), and `compute_readiness` is identical on
   both.
2. Two collections edit the **same** card offline → after sync the later-`mod`
   edit wins (documented LWW), while both cards' review rows survive.

See `analysis/RESULTS.md` for the recorded run.

### Live run on the real apps (2026-07-03)

Beyond the harness, the full loop was verified on the **actual apps** — the desktop
fork engine and the **AnkiDroid fork on an emulator**, both pointed at one
self-hosted `syncserver`:

- desktop → server → phone: after resolving the one-time full-sync prompt with
  **Download**, the phone's `collection.anki2` matched the desktop **byte-for-byte on
  schema/mod/card-count** (`scm=1783112626217`, `mod=1783113045335`, `cards=2888`).
- phone → server → desktop: a card graded **"Good"** on the phone propagated to the
  desktop on the next sync — desktop `revlog` went **16 → 17** and the exact review
  row (`cid=1554657681232, ease=3`) appeared on the desktop.

Full transcript and a phone screenshot: [../docs/verification/live_sync.txt](verification/live_sync.txt),
[live_sync_phone.png](verification/live_sync_phone.png). This also directly reproduced
the full-sync fallback dialog described above (and confirmed that, once both sides share
a base, syncs are incremental and lossless).
