# Frank Create Browser QA

Run the browser-level QA through the dependency-light PowerShell wrapper:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\Test-FrankCreateBrowserQa.ps1
```

The script uses `npx --package @playwright/cli` and verifies:

- Provider Adapter Audit in `?provider_audit=1` mode
- Advanced Graph Frank branding
- Raw Comfy canvas, run controls, light Frank badge, and absence of blocking Frank overlays
- No browser console warnings/errors on those checked surfaces
