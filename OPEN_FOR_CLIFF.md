# Open For Cliff

Double-click `CLIFF_START_HERE.cmd`.

That starts or reuses the local Studio, runs prep, rebuilds the readiness pack, then opens:

- Frank Create Studio: `http://127.0.0.1:8190/`
- `FRANK_CREATE_CALL_DAY.md`
- `user\frank_create\readiness_packs\frank-create-implementation-manifest-latest.md`
- `user\frank_create\demo_evidence\frank-create-demo-evidence-latest.md`
- `user\frank_create\demo_evidence\frank-create-call-brief-latest.md`
- `user\frank_create\demo_evidence\frank-create-provider-readiness-latest.md`
- `user\frank_create\demo_evidence\frank-create-activation-checklist-latest.md`
- `user\frank_create\demo_evidence\frank-create-brand-context-latest.md`
- `user\frank_create\readiness_packs`

Send or open:

- `user\frank_create\readiness_packs\frank-create-cliff-readiness-latest.zip`
- `user\frank_create\readiness_packs\frank-create-cliff-readiness-latest.zip.sha256`

Optional final check before sending: double-click `VERIFY_CLIFF_PACK.cmd`.

In Studio, click `Open review board` for a visual board of approved picks. Click `Open sync manifest` for the live `frank-create.sync.v1` JSON contract that FrankHub, Supabase, or a DAM can mirror later. In the readiness ZIP, open `handoff-review/frank-create-review-board-latest.png` for the same contact sheet without digging. Inside the nested `handoffs/` ZIP, the same board is bundled as `review/frank-create-review-board.png`.

The workflow smoke, readiness builder, and `VERIFY_CLIFF_PACK.cmd` prove byte-for-byte media integrity: they compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata.

The latest pack includes a browser QA receipt proving:

- Studio loads with the provider key plan visible
- Provider Setup key fields are limited to Gemini, OpenAI, and Replicate
- Provider Setup copies a safe provider key plan with env-var names and no provider secrets
- Provider Setup runs a no-spend selected model preflight with a safe payload preview
- the local Studio Generate button creates output assets with Local Comfy selected
- the masked edit Generate button creates output assets after a painted mask is saved
- the Cliff Pack panel opens the direct visual review-board PNG
- the Cliff Pack panel opens the FrankHub sync manifest as `frank-create.sync.v1`
- a selected output copies a safe selected-output run brief with workflow provenance and no provider secrets
- a selected output downloads a safe workflow JSON sidecar with workflow provenance and no provider secrets
- a seeded output opens the mask painter
- a painted mask saves into the `Masked Edit` composer
- QA-created mask assets and files are cleaned up afterward
- Advanced Graph and raw Comfy canvas render without console warnings

Expected warnings are okay for the local demo:

- no local diffusion checkpoint installed
- `GOOGLE_API_KEY` not loaded yet for live Gemini/Nano Banana rounds
- `OPENAI_API_KEY` and `REPLICATE_API_TOKEN` not loaded yet

The local Frank renderer still proves the full flow: reference upload, generate, edit, approve, export, storyboard, and handoff. Once a valid rotated `GOOGLE_API_KEY` is saved in Provider Setup or `user\frank_create\provider_keys.env`, Gemini/Nano Banana is the first live API path to test. OpenAI and Replicate are the only other live API options in this pack. If a Comfy checkpoint is added under `models\checkpoints`, Local Comfy rounds use checkpoint txt2img for prompt-only work, checkpoint img2img for reference/edit work, and checkpoint inpaint for masked edits.
