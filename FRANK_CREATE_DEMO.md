# Frank Create Demo Runbook

## Launch

### Command Roster

Open `OPEN_FOR_CLIFF.md` first for the shortest call-day instruction.

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

Double-click:

```text
START_FRANK_CREATE.cmd
```

To stop the local Frank Create server safely, double-click:

```text
STOP_FRANK_CREATE.cmd
```

For the clean call-day Cliff demo path, double-click:

```text
START_FRANK_CREATE_DEMO.cmd
```

That launcher resets the local Frank demo data, starts ComfyUI with the Frank shell, opens the studio, and keeps the fallback URL visible if the browser does not open.

For the full pre-call check, double-click:

```text
PREP_FRANK_CREATE_FOR_CLIFF.cmd
```

That runs the workflow smoke, Demo Doctor, visible Cliff Pack validation, evidence generation, and the one-page Cliff call brief, then opens the studio plus the evidence folder when everything passes.

For a quick readiness check without rebuilding proof packs, double-click:

```text
CHECK_FRANK_CREATE.cmd
```

That runs Demo Doctor, starts the server if needed, and pauses with the current readiness status.

To build one ZIP with the latest proof receipts, runbook, and QA screenshots for the call, double-click:

```text
BUILD_FRANK_CREATE_READINESS_PACK.cmd
```

That starts or reuses the local Studio first, runs the prep chain, refreshes the canonical desktop/mobile QA screenshots, proves the visible Studio path in browser QA, proves Provider Setup follows the three-provider Cliff launch plan, proves `Copy run brief` creates a safe selected-output run brief with workflow provenance, proves `Download workflow JSON` creates a safe provenance sidecar, creates a fresh `Cliff Pack` handoff ZIP, then writes timestamped packs plus `user\frank_create\readiness_packs\frank-create-cliff-readiness-latest.zip` with proof receipts, screenshots, and the handoff under `handoffs/`. The workflow smoke, readiness builder, and `VERIFY_CLIFF_PACK.cmd` prove byte-for-byte media integrity: they compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata. A sibling `frank-create-cliff-readiness-latest.zip.sha256` file verifies the ZIP checksum. The wrapper opens the readiness folder, `frank-create-implementation-manifest-latest.md`, `frank-create-demo-evidence-latest.md`, `frank-create-call-brief-latest.md`, `frank-create-provider-readiness-latest.md`, `frank-create-activation-checklist-latest.md`, and `frank-create-brand-context-latest.md`.

Or run from PowerShell:

```powershell
.\scripts\Start-FrankCreate.ps1
```

For a clean Cliff demo, reset the local Frank sessions before launch:

```powershell
.\scripts\Start-FrankCreate.ps1 -ResetDemoData
```

That reset seeds one `Frank Body Demo Studio` session plus local-rendered starter images, so the first screen is visual immediately.

Before the call, run the demo doctor:

```powershell
.\scripts\Test-FrankCreateDemo.ps1 -StartIfDown
```

It checks the local server, Frank shell build, seeded session/assets, local media files, source/docs secret hygiene, the last workflow-smoke receipt, provider-key readiness, and whether the local renderer or full checkpoint path is active.

Then run the end-to-end workflow smoke:

```powershell
.\scripts\Test-FrankCreateWorkflow.ps1 -StartIfDown
```

It creates a temporary smoke session, uploads a product reference through Comfy, creates the Frank reference asset, validates selected-model preflight, generates one local image round, edits that image, approves the edited output, exports `Transparent PNG` and `Email hero` ZIPs, validates the full one-click image channel-set ZIP, creates a local motion storyboard, exports the storyboard ZIP, validates README files and receipt metadata inside each ZIP, creates a mixed-media handoff pack, proves the ZIP includes approved and reference media files, writes `user\frank_create\workflow_smoke_status.json` for Demo Doctor, then archives the smoke session so the seeded Cliff demo stays clean.

After Doctor and smoke pass, write a compact evidence report:

```powershell
.\scripts\Test-FrankCreateEvidence.ps1 -StartIfDown
```

It saves timestamped Markdown and JSON under `user\frank_create\demo_evidence\` with the latest Demo Doctor checks, workflow-smoke receipt, warning actions, demo URLs, and a launch model roster showing provider, badge, capabilities, and server-key readiness without exposing secret values. The same content is also copied to `frank-create-demo-evidence-latest.md` and `frank-create-demo-evidence-latest.json` so the newest receipt is always easy to find.

Or run the whole Cliff prep chain in one command:

```powershell
.\scripts\Test-FrankCreateCliffPrep.ps1
```

That runs the workflow smoke, Demo Doctor, validates the visible seeded `Cliff Pack` ZIP, writes the latest evidence report, and writes `frank-create-call-brief-latest.md`. Add `-ResetDemoData` if you want the script to reseed the clean Frank Body demo before running the checks.

To rebuild only the ZIP from already-passing receipts:

```powershell
.\scripts\Build-FrankCreateReadinessPack.ps1 -SkipPrep
```

Use the in-app `Build call pack` button in Demo Doctor for the same package from the browser. For handoff, use:

```text
user\frank_create\readiness_packs\frank-create-cliff-readiness-latest.zip
```

The launcher starts ComfyUI with the Frank Create shell and opens:

```text
http://127.0.0.1:8190
```

Useful demo URLs:

- Studio: `http://127.0.0.1:8190`
- Advanced Graph: `http://127.0.0.1:8190/graph`
- Raw Comfy canvas: `http://127.0.0.1:8190/comfy/`

## Cliff Call-Day Proof

Before the call, run:

```text
PREP_FRANK_CREATE_FOR_CLIFF.cmd
```

Then open:

```text
user\frank_create\demo_evidence\frank-create-demo-evidence-latest.md
```

The receipt should show `Ready for demo: yes`, `Graph branding: verified`, `Launch Model Roster`, the latest workflow-smoke receipt, and the latest `Cliff Pack` export. The provider-readiness receipt should also show the no-spend adapter audit with `5 / 5` launch model runners registered across local fallback, Gemini, OpenAI, and Replicate. The activation checklist should show live key, checkpoint, and Replicate rotation actions. The brand-context brief should show the current reference count plus prompt-guided and future LoRA readiness.

Expected local warnings are okay for the demo: no diffusion checkpoint installed and live providers waiting on server-side keys.

Call-day talk track:

- Local Comfy proves the full generate, edit, approve, export, video storyboard, and mixed-media handoff path without paid provider keys.
- Google Gemini/Nano Banana is the first live API path: install a rotated `GOOGLE_API_KEY`, reload keys, preflight the selected model, then run one real image round.
- Live providers are already server-key gated; the browser only sees readiness and capability badges.
- The launch model roster shows which models are ready now, which need keys, and which support image, edit, mask, or video workflows.
- The same sessions, assets, approvals, references, and provider registry are shaped for later FrankHub/Supabase sync.

## Demo Flow For Cliff

1. Open Frank Create.
2. In `Demo Doctor`, click `Reset demo` if you want a clean seeded Frank Body session without relaunching ComfyUI. After a reset, rerun the workflow smoke so Demo Doctor has a fresh end-to-end receipt.
3. Use Product Shot Lab.
4. Show the `Campaign Brief` job jacket in the left rail: project name, product, channel, and the saved brief linked to the current session.
5. Upload a product/reference image. Click reference thumbnails in the composer to include or skip them for the next round without deleting them from the session.
6. In `Product Image Lab`, click `Background sweep`, `Background glow-up`, `Product polish`, `Campaign remix`, `Crop the goods`, or `Make it bigger` to show the job shortcuts.
7. Open `Brand Kit` in the right panel and show the saved Frank Body guidance, negative guardrails, and reference notes used by Frank Body Mode.
8. In `Provider Setup`, use `Check selected model` on the current model to show server-side capability/key preflight without spending API credits.
9. In Local Comfy, show the downloadable stock-node txt2img, img2img, and inpaint workflow blueprints.
10. Generate a round with Local Comfy. The local renderer works even without paid provider keys or checkpoints.
11. Select an output and click `Edit with selected model`.
12. Approve the best image.
13. Click `Copy run brief` to show the selected output can hand off prompt, settings, model, source/reference names, and workflow provenance without provider secrets.
14. Click `Download workflow JSON` to show the same pick can produce a machine-readable provenance sidecar for DAM, Supabase, or FrankHub sync later.
15. Save a review note.
16. Export a `Transparent PNG` to show background removal, then export a `High-res master` or channel pack.
   Talk track: each ZIP includes a README plus a JSON receipt with prompt, model, settings, preset, notes, references, the project/brief job jacket, and sync-ready metadata.
17. Open Video Lab with the approved/selected image still active, click `Make Motion`, and show the generated local storyboard GIF in the same session thread.
18. Select the motion board, click `Motion storyboard`, and show that it exports a ZIP with the GIF plus metadata.
19. Approve the motion board if it belongs in the review, then export the Cliff Pack to show the mixed-media handoff ZIP with approved images, motion, references, prompts, notes, project/brief context, and metadata.
    Talk track: this proves the image-to-motion review flow is already wired locally. Live video stays out of the Cliff pack until the image studio is approved.
20. Open Advanced Graph to show the branded Comfy escape hatch.

## What Works Without Keys

- Sessions, prompt thread, references, edits, favorites, approvals, notes, comparison, safe selected-output run brief copying, workflow JSON sidecar downloads, exports, and handoff packs.
- Project/brief job jackets linked to sessions, backed by the local SQLite creative-ops tables.
- Brand Kit guidance for Frank Body Mode, stored locally in `user\frank_create\brand_kit.json` when saved.
- Product Image Lab jobs: background sweep, background glow-up, product polish, campaign remix, crops, and high-res prep.
- Transparent PNG export uses a local background matte for flat product backgrounds.
- Video Lab generates a local storyboard GIF so the image-to-motion flow is demonstrable.
- Advanced Graph opens a Frank-branded Comfy escape hatch and the raw Comfy canvas remains available at `/comfy/`.
- Demo Doctor can reset the seeded local Frank Body demo session from the browser, no terminal required.

## Provider Keys

Provider keys stay server-side. Paste rotated keys only into the local `Provider Setup` save fields, `user\frank_create\provider_keys.env`, or process environment variables. Never put real keys into chat, docs, source files, screenshots, or exported packs.

For the first live API demo, fill `GOOGLE_API_KEY` only. After saving or editing the file, click `Reload keys`, click `Check selected model` with Gemini/Nano Banana selected, then generate one live image round. Other provider keys can stay empty until their paths are needed.

Before using live providers, copy:

```text
config\frank-create.env.example
```

to:

```text
user\frank_create\provider_keys.env
```

Then fill only the providers you want to demo. The launcher loads `provider_keys.env` automatically and the `user` folder is ignored by git.

You can also manage keys from the app without exposing secret values back to the browser:

1. Open the Provider Setup card.
2. Paste a rotated key into the matching server-key field and click `Save server keys`; the fields are limited to Gemini, OpenAI, and Replicate, and the input clears after save.
3. Or click `Create key file`, edit the ignored `user\frank_create\provider_keys.env` file locally, then click `Reload keys`.
4. Click `Check server keys` or `Check selected model` before spending provider credits.

The browser only receives env var names and readiness status, never the secret values.

Demo Doctor also scans the Frank app source/docs for provider-looking tokens. If it flags `Secret hygiene`, remove the token from the reported file, rotate it, and keep real keys only in `user\frank_create\provider_keys.env` or process environment variables.

Use `Check selected model` before a live provider round to validate the chosen model, mode, size, reference count, source/mask requirements, Frank Body prompt composition, and server-side key readiness without calling the provider.

You can also set the relevant environment variables manually:

```powershell
$env:GOOGLE_API_KEY="..."
$env:OPENAI_API_KEY="..."
$env:REPLICATE_API_TOKEN="..."
```

Rotate the exposed Replicate token before using Replicate in the demo.

Without live video provider support, Video Lab still uses the local storyboard renderer for call-day proof.

## Notes

- The local fallback renderer works without paid provider keys.
- The raw Comfy canvas opens cleanly and branded, even when no local diffusion checkpoint is installed.
- In Local Comfy, click `Prepare model folders` to create the checkpoint/LoRA folders plus a local README, then put real checkpoints in the shown `checkpoints` folder when you want full local diffusion: checkpoint txt2img for prompt-only rounds, checkpoint img2img for reference/edit rounds, and checkpoint inpaint for masked edits.
- Logs live in `user\frank_create\logs`.
