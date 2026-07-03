# Deployment evidence

Captured 2026-07-03. All paths are relative to the repo root. Reproduce the builds
with the commands in the README; this file records the produced artifacts so they
are easy to verify.

## Desktop app (macOS)

| Item | Value |
|---|---|
| Installer | `anki/out/installer/dist/anki-26.05b1-mac-apple.dmg` |
| Size | 237,162,690 bytes (~226 MiB) |
| SHA-256 | `8754d9c5403cd6abdadd6ef044ae910ee50f1bd48847b6e36aebcd600850395b` |
| Built | 2026-07-03 11:52 via `RELEASE=1 ./ninja installer` |
| Signing | ad-hoc (runs on the build machine; a different clean Mac needs right-click -> Open once for Gatekeeper) |
| Installed | `/Applications/Anki.app` (drag from the `.dmg`) |

**Proof the installer is the fork, not stock Anki:** the packaged web bundle inside
the `.dmg` contains the MCAT knowledge-graph code. Verify with:

```bash
DMG=anki/out/installer/dist/anki-26.05b1-mac-apple.dmg
MP=$(hdiutil attach "$DMG" -nobrowse -readonly | grep -o '/Volumes/.*' | head -1)
grep -rl "Show knowledge graph" "$MP/Anki.app/Contents/Resources" | head -1   # -> match = fork features present
hdiutil detach "$MP"
```

After launch, the Statistics page shows the three readiness scores, the give-up
rule, the interactive knowledge graph, and the "Generate AI cards for this topic"
button - none of which exist in stock Anki.

## Phone app (Android)

| Item | Value |
|---|---|
| Signed APK (arm64) | `Anki-Android/AnkiDroid/build/outputs/apk/full/debug/AnkiDroid-full-arm64-v8a-debug.apk` (~146 MB) |
| Other ABIs | armeabi-v7a / x86 / x86_64 debug APKs (~61 MB each) |
| Shared engine | `Anki-Android-Backend/rsdroid/build/outputs/aar/rsdroid-release.aar` (~19 MB) |
| Runs on | Android emulator `mcat_test` (installed + launched as `com.ichi2.anki.debug`) |

The `.aar` is the **same forked Rust engine (`rslib`) compiled for Android** and
bundled via JNI - this is what makes the desktop and phone share one engine. The
Android app loads it with `local_backend=true` in `local.properties`.

## Sync

The self-hosted sync server is compiled from the forked `rslib`
(`from anki.syncserver import run_sync_server`). `analysis/sync_test.py` stands one
up and drives a full two-device round-trip; see `docs/verification/sync_test.txt`
and `docs/SYNC.md` for the conflict rule.

## Installer recording (video)

The screen recording of a clean-machine install is the one artifact that must be
captured by a human. Runbook (≈1 minute):

1. On a clean Mac / fresh user, copy over `anki-26.05b1-mac-apple.dmg`.
2. Double-click it, drag **Anki.app** onto the **Applications** shortcut.
3. Right-click the installed app -> **Open** (ad-hoc signing), confirm once.
4. It launches; open **Stats** to show the readiness card + knowledge graph.

Record steps 1-4. The SHA-256 above lets a grader confirm the recorded `.dmg` is
this exact build.
