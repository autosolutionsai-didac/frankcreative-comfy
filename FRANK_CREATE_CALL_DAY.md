# Frank Create Call-Day Checklist

## One-Minute Setup

Open `OPEN_FOR_CLIFF.md` if you want the shortest possible start note.

1. Double-click `CLIFF_START_HERE.cmd` for the safest call-day path; it starts or reuses the local Studio, runs prep, rebuilds the readiness pack, then opens the studio and handoff docs.
2. Use `START_FRANK_CREATE_DEMO.cmd` only when you want a clean seeded demo without rebuilding the pack, or `START_FRANK_CREATE.cmd` to keep the current local state.
3. Open `http://127.0.0.1:8190`; if the browser does not open automatically, the launcher keeps this fallback URL visible.
4. Optional fast check: double-click `CHECK_FRANK_CREATE.cmd`; expect `ready_with_warnings` and `ReadyForDemo=true`.
5. In Demo Doctor, expect the same `ready_with_warnings` state.
6. Expected warnings are okay: no local diffusion checkpoint, and live provider keys not loaded.
7. To rebuild only the shareable proof pack, double-click `BUILD_FRANK_CREATE_READINESS_PACK.cmd`; it refreshes the QA screenshots before zipping, then opens the readiness folder, implementation manifest, evidence receipt, one-page call brief, provider-readiness receipt, activation checklist, and brand-context brief.
8. Optional final file check: double-click `VERIFY_CLIFF_PACK.cmd` before sending the ZIP.
9. Send or open `user\frank_create\readiness_packs\frank-create-cliff-readiness-latest.zip`; include `frank-create-cliff-readiness-latest.zip.sha256` if Cliff wants checksum proof.
10. After the call, double-click `STOP_FRANK_CREATE.cmd` to stop only the Frank Create server on port `8190`.

## Command Roster

| Need | Double-click |
| --- | --- |
| Cliff call-day start | `CLIFF_START_HERE.cmd` |
| Clean demo start | `START_FRANK_CREATE_DEMO.cmd` |
| Keep current state | `START_FRANK_CREATE.cmd` |
| Fast readiness check | `CHECK_FRANK_CREATE.cmd` |
| Verify latest pack | `VERIFY_CLIFF_PACK.cmd` |
| Full prep receipt | `PREP_FRANK_CREATE_FOR_CLIFF.cmd` |
| Shareable proof pack | `BUILD_FRANK_CREATE_READINESS_PACK.cmd` |
| Stop local server | `STOP_FRANK_CREATE.cmd` |

## What To Show

1. Start in Image Studio: session thread, model picker, references, Frank Body Mode, output rounds.
2. Show Product Shot Lab as the practical product workflow: upload/reference, task presets, generate, edit, approve, export.
3. Show Video Lab with the approved image flowing into a local motion storyboard.
4. In Local Comfy, show the downloadable txt2img, img2img, and inpaint workflow blueprints.
5. Open Advanced Graph to show the Frank-branded Comfy escape hatch.
6. Mention raw Comfy remains available at `/comfy/` for power users.
7. In Provider Setup, show the Gemini, OpenAI, and Replicate key fields, `Copy key plan`, and `Check selected model`; browser QA proves the three-provider launch plan, env-var names/model order without provider secrets, and the no-spend selected model preflight.
8. Select an output and show `Copy run brief`; browser QA proves it copies safe workflow provenance without provider secrets.
9. Show `Download workflow JSON`; browser QA proves it downloads a safe machine-readable provenance sidecar without provider secrets.
10. Click `Open review board` for the instant visual contact sheet, click `Open sync manifest` for the `frank-create.sync.v1` FrankHub/Supabase/DAM contract, then export `Cliff Pack` and mention the readiness ZIP also exposes both the visual board and `sync/frank-create-sync-manifest-latest.json`.
11. If Cliff asks about selective retouching, select an output and show `Paint edit mask`; browser QA proves paint, save, masked-edit composer handoff, masked edit Generate output, and QA cleanup.

## What To Say

- The local demo proves the full loop without paid API calls: prompt, reference, generate, edit, approve, export, motion, and handoff pack.
- Google Gemini/Nano Banana is the first real API path: save a rotated `GOOGLE_API_KEY`, reload keys, run `Check selected model`, then run one live image round.
- Provider keys stay server-side; the browser only sees model readiness, env var names, and capability badges.
- The only live key names in this pack are `GOOGLE_API_KEY`, `OPENAI_API_KEY`, and `REPLICATE_API_TOKEN`.
- The workflow smoke, readiness builder, and `VERIFY_CLIFF_PACK.cmd` prove byte-for-byte media integrity: they compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata.
- The readiness ZIP exposes `handoff-review/frank-create-review-board-latest.png` and `sync/frank-create-sync-manifest-latest.json`; the nested handoff ZIP includes the same visual review board, approved media, channel-ready approved-image exports, references, workflow sidecars, and sync-ready metadata.
- The latest browser QA receipt proves the visible Studio path, Provider Setup key fields for Gemini, OpenAI, and Replicate, safe provider key-plan copy, no-spend selected model preflight, local Studio Generate button, masked edit Generate button, direct review-board open, safe run-brief copy, workflow JSON download, mask painter save, Advanced Graph, and raw Comfy canvas.
- The Local Comfy blueprint card exposes the actual stock-node txt2img, img2img, and inpaint workflow JSONs.
- The architecture is local-first today and sync-ready for FrankHub or Supabase later.
- Two-kilopixel models are allowed when clearly badged; 4K-capable models remain preferred for production paths.

## Quick Fixes

- If state looks messy, click `Reset demo` in Demo Doctor or restart with `START_FRANK_CREATE_DEMO.cmd`.
- If you only need a quick status read, run `CHECK_FRANK_CREATE.cmd`.
- If proof receipts are stale, run `PREP_FRANK_CREATE_FOR_CLIFF.cmd`.
- If the readiness ZIP is missing, run `BUILD_FRANK_CREATE_READINESS_PACK.cmd` again.
- If the server gets wedged, run `STOP_FRANK_CREATE.cmd`, then start again with `START_FRANK_CREATE_DEMO.cmd`.
- If you want full local diffusion, click `Prepare model folders` under Local Comfy, put checkpoint files in the shown `checkpoints` folder, then rerun Demo Doctor.
- For live providers, paste rotated keys only into the local `Provider Setup` save fields or `user\frank_create\provider_keys.env`; never into chat, docs, source, screenshots, or exported packs.
- If Gemini/Nano Banana is not ready, check that `GOOGLE_API_KEY` is saved locally, click `Reload keys`, and run `Check selected model` before spending on a live round.
- Rotate the exposed Replicate token before any live Replicate usage.
