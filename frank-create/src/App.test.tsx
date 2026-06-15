import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { fallbackConfig } from "./lib/presets";

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("Comfy offline")))
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.history.pushState({}, "", "/");
  });

  it("renders a guided studio first screen and hides technical setup by default", async () => {
    render(<App />);

    expect(await screen.findByText("Frank Create")).toBeInTheDocument();
    expect(screen.getByText(/Add references, brief the image, generate picks/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^New$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Demo Walkthrough/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Advanced$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Product Shot Lab$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Video Lab$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Generate$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Change model/i })).toBeInTheDocument();
    expect(screen.getByText("Model & output")).toBeInTheDocument();
    expect(screen.queryByText("Provider Setup")).not.toBeInTheDocument();
    expect(screen.queryByText("Demo Doctor")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Workflow Map/i })).not.toBeInTheDocument();
    expect(screen.queryByText("GOOGLE_API_KEY")).not.toBeInTheDocument();
    expect(screen.queryByText(/No diffusion checkpoint detected/i)).not.toBeInTheDocument();
    expect(await screen.findByText("Comfy offline")).toBeInTheDocument();
  });

  it("opens a modal walkthrough that dims the app and points at each real workspace area", async () => {
    const { container } = render(<App />);

    expect(await screen.findByText("Frank Create")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Demo Walkthrough/i }));

    const dialog = screen.getByRole("dialog", { name: /Demo Walkthrough guide/i });
    expect(dialog).toHaveTextContent("Step 1 of 16");
    expect(dialog).toHaveTextContent("Sessions and demo controls");
    expect(screen.getByLabelText("Walkthrough backdrop")).toBeInTheDocument();
    expect(container.querySelector('[data-tour-id="app-header"]')).toHaveAttribute("data-tour-active", "true");
    await waitFor(() => expect(container.querySelector(".walkthrough-target-highlight")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /^Next$/i }));

    expect(dialog).toHaveTextContent("Step 2 of 16");
    expect(dialog).toHaveTextContent("Brief and references");
    expect(container.querySelector('[data-tour-id="composer"]')).toHaveAttribute("data-tour-active", "true");
    expect(container.querySelector('[data-tour-id="app-header"]')).not.toHaveAttribute("data-tour-active");

    fireEvent.click(screen.getByRole("button", { name: /Close walkthrough/i }));

    expect(screen.queryByRole("dialog", { name: /Demo Walkthrough guide/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Walkthrough backdrop")).not.toBeInTheDocument();
  });

  it("walks through every major studio and right-panel feature with targeted popups", async () => {
    const session = {
      id: "session-walkthrough-deep",
      name: "Deep Walkthrough Demo",
      mode: "image",
      status: "active",
      created_at: "2026-06-15T00:00:00Z",
      updated_at: "2026-06-15T00:00:00Z"
    };
    const reference = {
      id: "asset-walkthrough-ref",
      session_id: session.id,
      kind: "reference",
      title: "Coffee scrub reference",
      media_type: "image",
      file_path: "input/frank_create/reference.png",
      preview_url: "/api/view?filename=reference.png&type=input&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local"
    };
    const output = {
      id: "asset-walkthrough-output",
      session_id: session.id,
      turn_id: "turn-walkthrough",
      kind: "candidate",
      title: "Nano Banana product shot",
      media_type: "image",
      provider: "google",
      model: "google-nb-pro",
      prompt: "Create a Frank Body coffee scrub product shot on a soft pink counter.",
      settings_json: JSON.stringify({
        aspect_ratio: "1:1",
        image_size: "1K",
        count: 4,
        workflow_provenance: { workflow_key: "google-nano-banana-live-seed" }
      }),
      reference_asset_ids_json: JSON.stringify([reference.id]),
      file_path: "input/frank_create/frank-body-nano-banana-seed-01.jpg",
      preview_url: "/api/view?filename=frank-body-nano-banana-seed-01.jpg&type=input&subfolder=frank_create",
      width: 1024,
      height: 1024,
      favorite: true,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-15T00:00:00Z",
      updated_at: "2026-06-15T00:00:00Z"
    };

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(readyModelConfig("google-nb-pro", "GOOGLE_API_KEY"));
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({
            turns: [
              {
                id: "turn-walkthrough",
                session_id: session.id,
                kind: "generate",
                provider: "google",
                model: "google-nb-pro",
                prompt: output.prompt,
                settings_json: output.settings_json,
                reference_asset_ids_json: output.reference_asset_ids_json,
                frank_body_mode: true,
                preset_key: "product-shot-lab",
                status: "complete",
                created_at: "2026-06-15T00:00:00Z",
                updated_at: "2026-06-15T00:00:00Z"
              }
            ]
          });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [output, reference] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/demo-doctor")) {
          return jsonResponse({
            status: "ready_with_warnings",
            readyForDemo: true,
            headline: "Ready for Cliff",
            summary: {
              activeSessionCount: 1,
              outputAssetCount: 1,
              imageOutputAssetCount: 1,
              approvedAssetCount: 1,
              referenceAssetCount: 1,
              readyProviderModels: 1,
              waitingProviderModels: 0,
              demoCurated: true
            },
            checks: [],
            notes: []
          });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    expect(await screen.findByText("Nano Banana product shot")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Demo Walkthrough/i }));

    const dialog = screen.getByRole("dialog", { name: /Demo Walkthrough guide/i });
    const expectedSteps: Array<[string, string]> = [
      ["Sessions and demo controls", "app-header"],
      ["Brief and references", "composer"],
      ["Workflow chips and prompt", "composer"],
      ["Generated rounds", "output-thread"],
      ["Model summary", "model-settings"],
      ["Model drawer", "model-settings-drawer"],
      ["Output controls", "model-output-controls"],
      ["Frank Body Mode", "frank-mode-toggle"],
      ["Review desk", "review-panel"],
      ["Approve or reject", "review-actions"],
      ["Run metadata", "review-metadata"],
      ["Make another round", "variant-controls"],
      ["Edit, mask, and reuse", "edit-controls"],
      ["Exports", "export-controls"],
      ["Cliff Pack handoff", "handoff-pack"],
      ["Advanced tools", "advanced-tools"]
    ];

    for (const [index, [title, target]] of expectedSteps.entries()) {
      expect(dialog).toHaveTextContent(`Step ${index + 1} of ${expectedSteps.length}`);
      expect(dialog).toHaveTextContent(title);
      await waitFor(() => expect(container.querySelector(`[data-tour-id="${target}"]`)).toHaveAttribute("data-tour-active", "true"));
      if (title === "Model drawer") {
        expect(screen.getByLabelText("Model and output settings")).toBeInTheDocument();
      }
      if (title === "Review desk") {
        expect(screen.getByRole("button", { name: /Open selected asset/i })).toBeInTheDocument();
      }
      if (title === "Advanced tools") {
        expect(screen.getByLabelText("Advanced tools")).toBeInTheDocument();
      }
      if (index < expectedSteps.length - 1) {
        fireEvent.click(screen.getByRole("button", { name: /^Next$/i }));
      }
    }
  });

  it("can open the walkthrough directly from the URL for demo QA", async () => {
    window.history.pushState({}, "", "/?walkthrough=1");

    render(<App />);

    expect(await screen.findByRole("dialog", { name: /Demo Walkthrough guide/i })).toHaveTextContent("Sessions and demo controls");
    expect(screen.getByLabelText("Walkthrough backdrop")).toBeInTheDocument();
  });

  it("keeps technical setup inside Advanced until requested", async () => {
    render(<App />);

    expect(await screen.findByText("Frank Create")).toBeInTheDocument();
    expect(screen.queryByText("Provider Setup")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^Advanced$/i }));

    const advancedDrawer = screen.getByLabelText("Advanced tools");
    expect(within(advancedDrawer).getByRole("button", { name: /^Close$/i })).toBeInTheDocument();
    expect(screen.getByText("Provider Setup")).toBeInTheDocument();
    expect(screen.getByText("Demo Doctor")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Workflow Map/i })).toBeInTheDocument();
    expect(screen.getByText("Cliff key order")).toBeInTheDocument();
    expect(screen.getAllByText("GOOGLE_API_KEY").length).toBeGreaterThan(0);

    fireEvent.click(within(advancedDrawer).getByRole("button", { name: /^Close$/i }));
    expect(screen.queryByLabelText("Advanced tools")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Advanced$/i })).toBeInTheDocument();
  });

  it("lets users close the model drawer from inside the opened panel", async () => {
    render(<App />);

    expect(await screen.findByText("Frank Create")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Change model/i }));

    const settingsDrawer = screen.getByLabelText("Model and output settings");
    expect(screen.getByRole("button", { name: /Hide model settings/i })).toBeInTheDocument();
    expect(within(settingsDrawer).getByRole("button", { name: /^Done$/i })).toBeInTheDocument();

    fireEvent.click(within(settingsDrawer).getByRole("button", { name: /^Done$/i }));
    expect(screen.queryByLabelText("Model and output settings")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Change model/i })).toBeInTheDocument();
  });

  it("copies a provider key plan without provider secret values", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText }
    });

    render(<App />);

    expect(await screen.findByText("Frank Create")).toBeInTheDocument();
    openAdvanced();
    expect(screen.getByText("Cliff key order")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Copy key plan/i }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copied = writeText.mock.calls[0][0] as string;
    expect(copied).toContain("Frank Create Provider Key Plan");
    expect(copied).toContain("1. Nano Banana Pro + NB 2");
    expect(copied).toContain("GOOGLE_API_KEY");
    expect(copied).toContain("2. FLUX Ultra");
    expect(copied).toContain("REPLICATE_API_TOKEN");
    expect(copied).toContain("3. gpt-image-2");
    expect(copied).toContain("OPENAI_API_KEY");
    expect(copied).not.toMatch(/FAL_KEY|RECRAFT|IDEOGRAM|XAI|RUNWAY|Grok|Recraft|Ideogram|Runway/);
    expect(copied).toContain("Provider secret values are not included");
    expect(copied).not.toMatch(/server-side|sk-|r8_|AIza/);
    expect(await screen.findByText("Provider key plan copied for Cliff. No secret values included.")).toBeInTheDocument();
  });

  it("limits provider key inputs to Gemini, Replicate, and OpenAI", async () => {
    render(<App />);

    expect(await screen.findByText("Frank Create")).toBeInTheDocument();
    openAdvanced();
    expect(screen.getByText("Cliff key order")).toBeInTheDocument();
    const editor = screen.getByLabelText("Save server provider keys");
    const fieldNames = within(editor)
      .getAllByText(/_KEY|_TOKEN|_SECRET/)
      .map((element) => element.textContent ?? "");

    expect(fieldNames).toEqual(["GOOGLE_API_KEY", "REPLICATE_API_TOKEN", "OPENAI_API_KEY"]);
  });

  it("marks the studio shell for provider audit screenshot mode", async () => {
    window.history.pushState({}, "", "/?provider_audit=1");

    const { container } = render(<App />);

    expect(await screen.findByText("Frank Create")).toBeInTheDocument();
    expect(container.querySelector(".studio-shell")).toHaveClass("provider-audit-mode");
    expect(container.querySelector(".studio-shell")).toHaveAttribute("data-provider-audit", "open");
  });

  it("shows no-spend provider audit operation preview coverage", async () => {
    const session = {
      id: "session-provider-audit",
      name: "Provider Audit",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const audit = {
      title: "Frank Create Provider Adapter Audit",
      generated_at: "2026-06-09T00:00:00Z",
      summary: {
        model_count: 9,
        runner_registered: 9,
        missing_runners: 0,
        ready_models: 1,
        waiting_for_key: 8,
        preview_failures: 0,
        operation_preview_count: 18,
        operation_preview_failures: 0,
        no_spend: true,
        secret_values_returned: false
      },
      models: [
        {
          model_id: "openai-gpt-image-2",
          label: "gpt-image-2",
          provider: "openai",
          provider_model: "gpt-image-2",
          status: "waiting_for_key",
          configured: false,
          missing_env_vars: ["OPENAI_API_KEY"],
          runner_registered: true,
          operation_kinds: ["generate", "edit", "masked_edit"],
          capabilities: { generation: true, edit: true, masked_edit: true, video: false },
          reference_limit: 10,
          allowed_aspect_ratios: ["1:1"],
          allowed_image_sizes: ["4096"],
          request_preview: { method: "POST", endpoint: "https://api.openai.com/v1/images/generations" },
          request_previews: {
            generate: { method: "POST", endpoint: "https://api.openai.com/v1/images/generations" },
            edit: { method: "POST", endpoint: "https://api.openai.com/v1/images/edits" },
            masked_edit: { method: "POST", endpoint: "https://api.openai.com/v1/images/edits" }
          },
          request_preview_errors: {}
        }
      ],
      notes: ["No external calls."]
    };

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.endsWith("/api/frank/provider-audit")) {
          return jsonResponse(audit);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Comfy is in the room.");
    openAdvanced();
    fireEvent.click(screen.getByRole("button", { name: /Audit roster/i }));

    const auditCard = await screen.findByLabelText("Provider adapter audit");
    expect(within(auditCard).getByText(/9 \/ 9 runners registered/i)).toBeInTheDocument();
    expect(within(auditCard).getByText(/18 operation previews checked/i)).toBeInTheDocument();
    expect(within(auditCard).getByText(/3 ops: generate, edit, masked edit/i)).toBeInTheDocument();
  });

  it("creates new sessions inside the active campaign brief and current lab mode", async () => {
    const project = { id: "project-campaign", name: "Frank Body Winter Launch", client: "Frank Body", status: "active" };
    const brief = {
      id: "brief-campaign",
      project_id: project.id,
      title: "Original Coffee Scrub launch",
      product_name: "Original Coffee Scrub",
      task_type: "lifestyle_background",
      channel: "Paid social",
      tone: "Cheeky but premium",
      prompt: "Create a warm Frank Body shower-shelf motion board.",
      negative_prompt: "",
      status: "draft"
    };
    const initialSession = {
      id: "session-campaign",
      project_id: project.id,
      name: "Launch campaign",
      mode: "image",
      status: "active",
      created_at: "2026-06-09T00:00:00Z",
      updated_at: "2026-06-09T00:00:00Z"
    };
    const createdSession = {
      id: "session-new-video",
      project_id: project.id,
      name: "Original Coffee Scrub Video Lab",
      mode: "video",
      status: "active",
      summary: brief.title,
      created_at: "2026-06-09T01:00:00Z",
      updated_at: "2026-06-09T01:00:00Z"
    };
    const sessionPosts: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [initialSession] });
        }
        if (url.endsWith("/api/frank/sessions") && method === "POST") {
          sessionPosts.push(JSON.parse(String(init?.body)));
          return jsonResponse({ session: createdSession }, 201);
        }
        if (url.endsWith("/api/frank/projects")) {
          return jsonResponse({ projects: [project] });
        }
        if (url.endsWith(`/api/frank/briefs?project_id=${project.id}`)) {
          return jsonResponse({ briefs: [brief] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    expect(await screen.findByText("Comfy is in the room.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Video Lab$/i }));
    fireEvent.click(screen.getByRole("button", { name: /^New$/i }));

    await waitFor(() =>
      expect(sessionPosts).toEqual([
        expect.objectContaining({
          project_id: project.id,
          mode: "video",
          name: "Original Coffee Scrub Video Lab",
          summary: brief.title
        })
      ])
    );
    expect(screen.getByPlaceholderText(/Brief the image/i)).toHaveValue(brief.prompt);
    expect(screen.getByText("New session in Original Coffee Scrub. Job jacket carried over.")).toBeInTheDocument();
  });

  it("opens Video Lab directly from a URL mode for browser QA", async () => {
    window.history.pushState({}, "", "/?mode=video-lab");

    const { container } = render(<App />);

    expect(await screen.findByText("Frank Create")).toBeInTheDocument();
    expect(navButton(container, "Video Lab")).toHaveClass("active");
    expect(screen.getByRole("button", { name: /^Generate$/i })).toBeInTheDocument();
  });

  it("prepares local Comfy model folders from the studio", async () => {
    const session = {
      id: "session-local-engine",
      name: "Local Engine QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const preparedEngine = {
      ...fallbackConfig.localEngine,
      checkpoint_dir: "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\models\\checkpoints",
      setup_readme: "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\models\\FRANK_CREATE_MODELS_README.txt"
    };
    const calls: string[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({
            filePath: "user/frank_create/provider_keys.env",
            fileExists: false,
            envVars: [],
            configuredEnvVars: [],
            missingEnvVars: [],
            notes: []
          });
        }
        if (url.endsWith("/api/frank/local-engine/setup") && method === "POST") {
          calls.push(url);
          return jsonResponse({
            created_dirs: [
              "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\models\\checkpoints",
              "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\models\\loras"
            ],
            readme_path: preparedEngine.setup_readme,
            localEngine: preparedEngine
          });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Comfy is in the room.");
    openAdvanced();
    fireEvent.click(screen.getByRole("button", { name: /Prepare model folders/i }));

    expect(await screen.findByText("2 local model folders created. Add checkpoints, then run Demo Doctor.")).toBeInTheDocument();
    expect(calls).toEqual(["/api/frank/local-engine/setup"]);
    expect(screen.getByText(preparedEngine.checkpoint_dir)).toBeInTheDocument();
  });

  it("shows and downloads curated Comfy workflow blueprints", async () => {
    const session = {
      id: "session-workflow-blueprints",
      name: "Workflow Blueprint QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const blueprintPayload = {
      status: "ready",
      product: "Frank Create",
      checkpoint_name: "frank-create-placeholder.safetensors",
      note: "Blueprints use stock Comfy nodes.",
      blueprints: [
        {
          key: "comfy-checkpoint-txt2img",
          label: "Checkpoint txt2img",
          use: "Prompt-only campaign generation.",
          node_types: ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler", "VAEDecode", "SaveImage"],
          workflow_json: {
            "1": { class_type: "CheckpointLoaderSimple", inputs: { ckpt_name: "frank-create-placeholder.safetensors" } }
          }
        },
        {
          key: "comfy-checkpoint-img2img",
          label: "Checkpoint img2img",
          use: "Reference-guided product edits.",
          node_types: ["CheckpointLoaderSimple", "LoadImage", "VAEEncode", "KSampler", "SaveImage"],
          workflow_json: {
            "4": { class_type: "VAEEncode", inputs: { pixels: ["3", 0] } }
          }
        },
        {
          key: "comfy-checkpoint-inpaint",
          label: "Checkpoint inpaint",
          use: "Masked retouching.",
          node_types: ["CheckpointLoaderSimple", "LoadImageMask", "InpaintModelConditioning", "KSampler", "SaveImage"],
          workflow_json: {
            "7": { class_type: "InpaintModelConditioning", inputs: { mask: ["4", 0] } }
          }
        }
      ]
    };
    const objectUrls: Blob[] = [];
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const createObjectUrlSpy = vi.spyOn(URL, "createObjectURL").mockImplementation((blob) => {
      objectUrls.push(blob as Blob);
      return `blob:blueprint-${objectUrls.length}`;
    });
    const revokeObjectUrlSpy = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/local-engine/workflow-blueprints")) {
          return jsonResponse(blueprintPayload);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({
            filePath: "user/frank_create/provider_keys.env",
            fileExists: false,
            envVars: [],
            configuredEnvVars: [],
            missingEnvVars: [],
            notes: []
          });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    expect(await screen.findByText("Frank Create")).toBeInTheDocument();
    openAdvanced();
    expect(screen.getByText("Comfy workflow blueprints")).toBeInTheDocument();
    expect(screen.getByText("Checkpoint txt2img")).toBeInTheDocument();
    expect(screen.getByText("Checkpoint img2img")).toBeInTheDocument();
    expect(screen.getByText("Checkpoint inpaint")).toBeInTheDocument();
    expect(screen.getByText(/LoadImageMask/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Download Checkpoint inpaint workflow JSON/i }));

    await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
    expect(createObjectUrlSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectUrlSpy).toHaveBeenCalledWith("blob:blueprint-1");
    const downloaded = JSON.parse(await objectUrls[0].text());
    expect(downloaded.key).toBe("comfy-checkpoint-inpaint");
    expect(downloaded.workflow_json["7"].class_type).toBe("InpaintModelConditioning");
    expect(JSON.stringify(downloaded)).not.toMatch(/sk-|r8_|AIza/i);
    expect(screen.getByText("Comfy workflow blueprint downloaded.")).toBeInTheDocument();
  });

  it("loads and saves the Frank Body Brand Kit guidance", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    const session = {
      id: "session-brand-kit",
      name: "Brand Kit QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const savedBrandKit = {
      style_guidance: "Updated FrankHub pink tiles, direct flash, coffee scrub texture.",
      negative_prompt: "No beige spa stock sets.",
      reference_notes: "Use latest body scrub pack shots first.",
      sync_status: "local",
      remote_id: null
    };
    const referenceAsset = {
      id: "asset-brand-ref",
      session_id: session.id,
      kind: "reference",
      title: "Body scrub pack shot",
      file_path: "input/frank_create/body-scrub.png",
      url: "/api/frank/assets/asset-brand-ref/download",
      media_type: "image",
      approval_status: "review",
      favorite: false,
      notes: "",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const brandKitSaves: unknown[] = [];
    const brandContextRequests: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [referenceAsset] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({ filePath: "user/frank_create/provider_keys.env", fileExists: false, envVars: [], configuredEnvVars: [], missingEnvVars: [], notes: [] });
        }
        if (url.endsWith("/api/frank/brand-kit") && method === "GET") {
          return jsonResponse({
            brandKit: {
              style_guidance: "Initial FrankHub pink tiles and coffee scrub macro language.",
              negative_prompt: "No warped labels.",
              reference_notes: "Use approved pack shots.",
              sync_status: "local",
              remote_id: null
            },
            filePath: "user/frank_create/brand_kit.json"
          });
        }
        if (url.endsWith("/api/frank/brand-kit") && method === "PATCH") {
          const body = JSON.parse(String(init?.body));
          brandKitSaves.push(body);
          return jsonResponse({ brandKit: savedBrandKit, filePath: "user/frank_create/brand_kit.json" });
        }
        if (url.endsWith("/api/frank/demo/brand-context") && method === "POST") {
          brandContextRequests.push(JSON.parse(String(init?.body)));
          return jsonResponse(
            {
              receipt: {
                title: "Frank Create Brand Context Brief",
                generated_at: "2026-06-09T00:00:00Z",
                session: { id: session.id, name: session.name },
                summary: {
                  style_guidance_chars: savedBrandKit.style_guidance.length,
                  negative_prompt_chars: savedBrandKit.negative_prompt.length,
                  reference_notes_chars: savedBrandKit.reference_notes.length,
                  reference_asset_count: 1,
                  approved_asset_count: 0,
                  prompt_guided_status: "starter",
                  lora_training_status: "starter",
                  prompt_guided_target: "30-80 curated references",
                  lora_training_target: "100-300 rights-cleared references"
                },
                brand_kit: savedBrandKit,
                reference_assets: [referenceAsset],
                approved_assets: [],
                training_recommendation: {
                  frank_body_mode: "Use prompt-guided Frank Body Mode first.",
                  lora: "LoRA later for open models.",
                  do_not_train_on: "Do not train on unlicensed material."
                },
                next_inputs: ["Collect 29 more curated references."]
              },
              markdown_path: "F:\\frank-create-brand-context-20260609.md",
              json_path: "F:\\frank-create-brand-context-20260609.json",
              latest_markdown_path: "F:\\frank-create-brand-context-latest.md",
              latest_json_path: "F:\\frank-create-brand-context-latest.json",
              markdown_file: "frank-create-brand-context-20260609.md",
              json_file: "frank-create-brand-context-20260609.json",
              latest_markdown_file: "frank-create-brand-context-latest.md",
              latest_json_file: "frank-create-brand-context-latest.json",
              markdown_url: "/api/frank/demo/brand-context/frank-create-brand-context-20260609.md",
              json_url: "/api/frank/demo/brand-context/frank-create-brand-context-20260609.json",
              latest_markdown_url: "/api/frank/demo/brand-context/frank-create-brand-context-latest.md",
              latest_json_url: "/api/frank/demo/brand-context/frank-create-brand-context-latest.json"
            },
            201
          );
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Frank Create");
    openAdvanced();
    const styleGuidance = screen.getByLabelText("Frank Brand Kit style guidance");
    expect(styleGuidance).toHaveValue("Initial FrankHub pink tiles and coffee scrub macro language.");
    fireEvent.change(styleGuidance, { target: { value: savedBrandKit.style_guidance } });
    fireEvent.click(screen.getByRole("button", { name: /Save Brand Kit/i }));

    await waitFor(() =>
      expect(brandKitSaves).toEqual([
        expect.objectContaining({
          style_guidance: savedBrandKit.style_guidance,
          negative_prompt: "No warped labels.",
          reference_notes: "Use approved pack shots."
        })
      ])
    );
    expect(await screen.findByText("Brand kit saved for Frank Body Mode.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Save context brief/i }));

    await waitFor(() => expect(brandContextRequests).toEqual([{ session_id: session.id }]));
    expect(await screen.findByText("Brand context: frank-create-brand-context-latest.md")).toBeInTheDocument();
    expect(await screen.findByText("Brand context link ready: /api/frank/demo/brand-context/frank-create-brand-context-latest.md")).toBeInTheDocument();
    expect(openSpy).toHaveBeenCalledWith("/api/frank/demo/brand-context/frank-create-brand-context-latest.md", "_blank");
    openSpy.mockRestore();
  });

  it("creates a project brief and links the active session", async () => {
    const session = {
      id: "session-brief",
      name: "Brief QA",
      mode: "image",
      status: "active",
      project_id: null,
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const project = {
      id: "project-campaign",
      name: "Body Scrub Launch",
      client: "Frank Body",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const brief = {
      id: "brief-campaign",
      project_id: project.id,
      title: "Body Scrub Launch product shot",
      product_name: "Body Scrub Launch",
      task_type: "campaign-variants",
      channel: "Paid social",
      tone: "Cheeky but premium",
      prompt: "Coffee scrub product hero on pink bathroom tile.",
      negative_prompt: "No warped labels.",
      status: "draft",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const projectCalls: unknown[] = [];
    const briefCalls: unknown[] = [];
    const sessionPatchCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({ filePath: "user/frank_create/provider_keys.env", fileExists: false, envVars: [], configuredEnvVars: [], missingEnvVars: [], notes: [] });
        }
        if (url.endsWith("/api/frank/brand-kit")) {
          return jsonResponse({ brandKit: { style_guidance: "Frank style", negative_prompt: "", reference_notes: "", sync_status: "local" }, filePath: "user/frank_create/brand_kit.json" });
        }
        if (url.endsWith("/api/frank/projects") && method === "GET") {
          return jsonResponse({ projects: [] });
        }
        if (url.includes("/api/frank/briefs") && method === "GET") {
          return jsonResponse({ briefs: [] });
        }
        if (url.endsWith("/api/frank/projects") && method === "POST") {
          projectCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ project }, 201);
        }
        if (url.endsWith("/api/frank/briefs") && method === "POST") {
          briefCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ brief }, 201);
        }
        if (url.endsWith(`/api/frank/sessions/${session.id}`) && method === "PATCH") {
          sessionPatchCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ session: { ...session, project_id: project.id, summary: "Body Scrub Launch product shot" } });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByRole("heading", { name: "Brief QA" });
    openAdvanced();
    fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "Body Scrub Launch" } });
    fireEvent.change(screen.getByLabelText("Product name"), { target: { value: "Body Scrub Launch" } });
    fireEvent.change(screen.getByLabelText("Brief channel"), { target: { value: "Paid social" } });
    fireEvent.change(screen.getByLabelText("Brief prompt"), { target: { value: "Coffee scrub product hero on pink bathroom tile." } });
    fireEvent.click(screen.getByRole("button", { name: /Save Brief/i }));

    await waitFor(() => {
      expect(projectCalls).toEqual([expect.objectContaining({ name: "Body Scrub Launch", client: "Frank Body" })]);
      expect(briefCalls).toEqual([
        expect.objectContaining({
          project_id: project.id,
          title: "Body Scrub Launch product shot",
          product_name: "Body Scrub Launch",
          channel: "Paid social",
          prompt: "Coffee scrub product hero on pink bathroom tile."
        })
      ]);
      expect(sessionPatchCalls).toEqual([
        expect.objectContaining({ project_id: project.id, summary: "Body Scrub Launch product shot" })
      ]);
    });
    expect(await screen.findByText("Brief saved. The studio has a job jacket now.")).toBeInTheDocument();
  });

  it("updates the active project brief instead of creating duplicates", async () => {
    const project = {
      id: "project-existing",
      name: "Coffee Scrub Launch",
      client: "Frank Body",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const session = {
      id: "session-existing-brief",
      name: "Existing Brief QA",
      mode: "image",
      status: "active",
      project_id: project.id,
      summary: "Original Coffee Scrub product shot",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const brief = {
      id: "brief-existing",
      project_id: project.id,
      title: "Original Coffee Scrub product shot",
      product_name: "Original Coffee Scrub",
      task_type: "product-shot-lab",
      channel: "PDP",
      tone: "Cheeky but premium",
      prompt: "Original product shot.",
      negative_prompt: "No warped labels.",
      status: "draft",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const updatedBrief = {
      ...brief,
      title: "Coconut Coffee Scrub product shot",
      product_name: "Coconut Coffee Scrub",
      channel: "Email hero",
      prompt: "Coconut scrub on pink tile with clean label."
    };
    const projectCreateCalls: unknown[] = [];
    const briefCreateCalls: unknown[] = [];
    const briefPatchCalls: unknown[] = [];
    const sessionPatchCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({ filePath: "user/frank_create/provider_keys.env", fileExists: false, envVars: [], configuredEnvVars: [], missingEnvVars: [], notes: [] });
        }
        if (url.endsWith("/api/frank/brand-kit")) {
          return jsonResponse({ brandKit: { style_guidance: "Frank style", negative_prompt: "", reference_notes: "", sync_status: "local" }, filePath: "user/frank_create/brand_kit.json" });
        }
        if (url.endsWith("/api/frank/projects") && method === "GET") {
          return jsonResponse({ projects: [project] });
        }
        if (url.endsWith(`/api/frank/briefs?project_id=${project.id}`) && method === "GET") {
          return jsonResponse({ briefs: [brief] });
        }
        if (url.endsWith("/api/frank/projects") && method === "POST") {
          projectCreateCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ project }, 201);
        }
        if (url.endsWith("/api/frank/briefs") && method === "POST") {
          briefCreateCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ brief: { ...updatedBrief, id: "brief-duplicate" } }, 201);
        }
        if (url.endsWith(`/api/frank/briefs/${brief.id}`) && method === "PATCH") {
          briefPatchCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ brief: updatedBrief });
        }
        if (url.endsWith(`/api/frank/sessions/${session.id}`) && method === "PATCH") {
          sessionPatchCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ session: { ...session, summary: updatedBrief.title } });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByRole("heading", { name: "Existing Brief QA" });
    openAdvanced();
    fireEvent.change(screen.getByLabelText("Product name"), { target: { value: "Coconut Coffee Scrub" } });
    fireEvent.change(screen.getByLabelText("Brief channel"), { target: { value: "Email hero" } });
    fireEvent.change(screen.getByLabelText("Brief prompt"), {
      target: { value: "Coconut scrub on pink tile with clean label." }
    });
    fireEvent.click(screen.getByRole("button", { name: /Save Brief/i }));

    await waitFor(() => {
      expect(projectCreateCalls).toEqual([]);
      expect(briefCreateCalls).toEqual([]);
      expect(briefPatchCalls).toEqual([
        expect.objectContaining({
          title: "Coconut Coffee Scrub product shot",
          product_name: "Coconut Coffee Scrub",
          channel: "Email hero",
          prompt: "Coconut scrub on pink tile with clean label."
        })
      ]);
      expect(sessionPatchCalls).toEqual([
        expect.objectContaining({ project_id: project.id, summary: "Coconut Coffee Scrub product shot" })
      ]);
    });
    expect(await screen.findByText("Brief updated. Job jacket is current.")).toBeInTheDocument();
  });

  it("hydrates the composer from the active campaign brief on load", async () => {
    const project = {
      id: "project-brief-prompt",
      name: "Coffee Scrub Launch",
      client: "Frank Body",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const session = {
      id: "session-brief-prompt",
      name: "Brief Prompt QA",
      mode: "image",
      status: "active",
      project_id: project.id,
      summary: "Coffee Scrub PDP refresh",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const brief = {
      id: "brief-prompt",
      project_id: project.id,
      title: "Coffee Scrub PDP refresh",
      product_name: "Original Coffee Scrub",
      task_type: "product-shot-lab",
      channel: "PDP",
      tone: "Cheeky but premium",
      prompt: "Place the coffee scrub on soft pink tile with a clean readable label.",
      negative_prompt: "No warped labels.",
      status: "draft",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({ filePath: "user/frank_create/provider_keys.env", fileExists: false, envVars: [], configuredEnvVars: [], missingEnvVars: [], notes: [] });
        }
        if (url.endsWith("/api/frank/brand-kit")) {
          return jsonResponse({ brandKit: { style_guidance: "Frank style", negative_prompt: "", reference_notes: "", sync_status: "local" }, filePath: "user/frank_create/brand_kit.json" });
        }
        if (url.endsWith("/api/frank/projects") && method === "GET") {
          return jsonResponse({ projects: [project] });
        }
        if (url.endsWith(`/api/frank/briefs?project_id=${project.id}`) && method === "GET") {
          return jsonResponse({ briefs: [brief] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    const promptInput = await screen.findByPlaceholderText(/Brief the image/i);
    expect(promptInput).toHaveValue(brief.prompt);
  });

  it("clears the composer when starting a fresh session", async () => {
    const session = {
      id: "session-with-prompt",
      name: "Prompt Carryover QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const createdSession = {
      ...session,
      id: "session-fresh",
      name: "New image session"
    };
    const sessionCreateCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.endsWith("/api/frank/sessions") && method === "POST") {
          sessionCreateCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ session: createdSession }, 201);
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({ filePath: "user/frank_create/provider_keys.env", fileExists: false, envVars: [], configuredEnvVars: [], missingEnvVars: [], notes: [] });
        }
        if (url.endsWith("/api/frank/brand-kit")) {
          return jsonResponse({ brandKit: { style_guidance: "Frank style", negative_prompt: "", reference_notes: "", sync_status: "local" }, filePath: "user/frank_create/brand_kit.json" });
        }
        if (url.endsWith("/api/frank/projects")) {
          return jsonResponse({ projects: [] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    const promptInput = await screen.findByPlaceholderText(/Brief the image/i);
    fireEvent.change(promptInput, { target: { value: "Carryover prompt that should clear." } });
    fireEvent.click(screen.getByRole("button", { name: /^New$/i }));

    await screen.findByText("New session. Fresh canvas.");
    expect(sessionCreateCalls).toEqual([expect.objectContaining({ name: "New image session", mode: "image" })]);
    expect(promptInput).toHaveValue("");
  });

  it("keeps the current session visible when archive fails", async () => {
    const session = {
      id: "session-archive-fail",
      name: "Do Not Lose Me",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.endsWith(`/api/frank/sessions/${session.id}`) && method === "PATCH") {
          return jsonResponse({ error: { message: "Session archive is temporarily locked." } }, 500);
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/projects")) {
          return jsonResponse({ projects: [] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Do Not Lose Me" })).toBeInTheDocument();
    openAdvanced();
    fireEvent.click(screen.getByRole("button", { name: /^Clear$/i }));

    expect(await screen.findByText("Session archive is temporarily locked.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Do Not Lose Me" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Export Cliff Pack/i }).every((button) => button.hasAttribute("disabled"))).toBe(true);
  });

  it("opens a Frank-branded graph surface from the advanced graph control", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

    const { container } = render(<App />);

    expect(await screen.findByText("Frank Create")).toBeInTheDocument();
    openAdvanced();
    fireEvent.click(screen.getByRole("button", { name: /Advanced Graph/i }));

    expect(await screen.findByRole("heading", { name: "Workflow Map" })).toBeInTheDocument();
    expect(screen.getByText("Studio workflow map")).toBeInTheDocument();
    expect(screen.getByText("Real node graph lives in Comfy Canvas.")).toBeInTheDocument();
    expect(container.querySelector(".graph-shell")).toHaveAttribute("data-frank-surface", "workflow-map");
    expect(screen.queryByText("The Raw Goods")).not.toBeInTheDocument();

    const workflow = screen.getByLabelText("Frank Create workflow map");
    expect(within(workflow).getByText("Brief")).toBeInTheDocument();
    expect(within(workflow).getByText("Make")).toBeInTheDocument();
    expect(within(workflow).getByText("Review and export")).toBeInTheDocument();
    expect(within(workflow).getByText("Product refs, approved shots, texture scraps, and edit sources.")).toBeInTheDocument();

    const makeMagicNode = screen.getByRole("button", { name: /Inspect Make Magic/i });
    expect(makeMagicNode).toHaveAttribute("aria-pressed", "true");
    expect(within(makeMagicNode).getByText("View details")).toBeInTheDocument();
    let selectedStage = screen.getByLabelText("Selected workflow stage");
    expect(within(selectedStage).getByText("Selected stage 04")).toBeInTheDocument();
    expect(within(selectedStage).getByText("Comfy queue, provider proxy, model settings, and retry-friendly runs.")).toBeInTheDocument();

    const briefNode = screen.getByRole("button", { name: /Inspect The Brief/i });
    fireEvent.click(briefNode);
    expect(briefNode).toHaveAttribute("aria-pressed", "true");
    expect(makeMagicNode).toHaveAttribute("aria-pressed", "false");
    selectedStage = screen.getByLabelText("Selected workflow stage");
    expect(within(selectedStage).getByText("Selected stage 01")).toBeInTheDocument();
    expect(within(selectedStage).getByText("Product truth, channel, mood, and the part we do not mess with.")).toBeInTheDocument();

    const exportNode = screen.getByRole("button", { name: /Inspect Send It/i });
    fireEvent.click(exportNode);
    expect(exportNode).toHaveAttribute("aria-pressed", "true");
    selectedStage = screen.getByLabelText("Selected workflow stage");
    expect(within(selectedStage).getByText("Selected stage 07")).toBeInTheDocument();
    expect(within(selectedStage).getByText("Channel packs, prompt metadata, and sync-ready files for the next home.")).toBeInTheDocument();

    expect(screen.getByText("What this page is")).toBeInTheDocument();
    expect(screen.getByText("Use it to inspect the Frank Create flow without opening the raw Comfy node canvas.")).toBeInTheDocument();
    expect(screen.getByLabelText("Workflow receipts")).toBeInTheDocument();
    expect(container.querySelectorAll(".graph-node")).toHaveLength(7);
    const makeStageNodes = Array.from(container.querySelectorAll('[data-brand-stage="make"]'));
    expect(makeStageNodes.some((node) => node.textContent?.includes("Make Magic"))).toBe(true);
    expect(container.querySelector('[data-brand-step="04"]')?.textContent).toContain("Make Magic");
    expect(screen.getByRole("button", { name: /Back to Studio/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Use in Studio/i })).toBeInTheDocument();
    expect(openSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getAllByRole("button", { name: /Open Comfy Canvas/i })[0]);

    expect(openSpy).toHaveBeenCalledWith("/comfy/", "_blank");
    expect(screen.getByText("Raw Comfy canvas link ready: /comfy/")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Try Raw Comfy canvas link/i }));
    expect(openSpy).toHaveBeenLastCalledWith("/comfy/", "_blank");
  });

  it("checks provider readiness from the server without exposing key values", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    const session = {
      id: "session-provider-status",
      name: "Provider QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const providerStatus = {
      summary: {
        modelCount: 8,
        readyModels: 3,
        waitingModels: 5,
        configuredEnvVars: ["GOOGLE_API_KEY", "REPLICATE_API_TOKEN"],
        missingEnvVars: ["OPENAI_API_KEY", "XAI_API_KEY"]
      },
      providers: [],
      models: [],
      notes: ["Provider keys are read server-side only."]
    };
    const providerReceipt = {
      receipt: {
        title: "Frank Create Provider Readiness",
        generated_at: "2026-06-09T00:00:00Z",
        summary: {
          model_count: 8,
          ready_models: 3,
          waiting_models: 5,
          configured_env_vars: ["GOOGLE_API_KEY", "REPLICATE_API_TOKEN"],
          missing_env_vars: ["OPENAI_API_KEY", "XAI_API_KEY"]
        },
        providers: [],
        model_roster: [],
        adapter_audit: {
          title: "Frank Create Provider Adapter Audit",
          generated_at: "2026-06-09T00:00:00Z",
          summary: {
            model_count: 8,
            runner_registered: 8,
            missing_runners: 0,
            ready_models: 3,
            waiting_for_key: 5,
            preview_failures: 0,
            no_spend: true,
            secret_values_returned: false
          },
          models: [],
          notes: ["No external calls."]
        },
        mocked_live_path_coverage: [],
        notes: ["Provider keys are read server-side only."]
      },
      markdown_path: "F:\\frank-create-provider-readiness-20260609.md",
      json_path: "F:\\frank-create-provider-readiness-20260609.json",
      latest_markdown_path: "F:\\frank-create-provider-readiness-latest.md",
      latest_json_path: "F:\\frank-create-provider-readiness-latest.json",
      markdown_file: "frank-create-provider-readiness-20260609.md",
      json_file: "frank-create-provider-readiness-20260609.json",
      latest_markdown_file: "frank-create-provider-readiness-latest.md",
      latest_json_file: "frank-create-provider-readiness-latest.json",
      markdown_url: "/api/frank/demo/provider-readiness/frank-create-provider-readiness-20260609.md",
      json_url: "/api/frank/demo/provider-readiness/frank-create-provider-readiness-20260609.json",
      latest_markdown_url: "/api/frank/demo/provider-readiness/frank-create-provider-readiness-latest.md",
      latest_json_url: "/api/frank/demo/provider-readiness/frank-create-provider-readiness-latest.json"
    };

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.endsWith("/api/frank/provider-status")) {
          return jsonResponse(providerStatus);
        }
        if (url.endsWith("/api/frank/demo/provider-readiness") && method === "POST") {
          return jsonResponse(providerReceipt, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Comfy is in the room.");
    openAdvanced();
    fireEvent.click(screen.getByRole("button", { name: /Check server keys/i }));

    expect(await screen.findByText("3 / 8 provider models ready")).toBeInTheDocument();
    expect(screen.getAllByText("OPENAI_API_KEY").length).toBeGreaterThan(0);
    expect(screen.queryByText(/server-side-replicate|server-side-openai/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Save receipt/i }));

    expect(await screen.findByText("Provider receipt: frank-create-provider-readiness-latest.md")).toBeInTheDocument();
    expect(openSpy).toHaveBeenCalledWith(
      "/api/frank/demo/provider-readiness/frank-create-provider-readiness-latest.md",
      "_blank"
    );
    expect(screen.queryByText(/server-side-replicate|server-side-openai/i)).not.toBeInTheDocument();
    openSpy.mockRestore();
  });

  it("shows a no-secret production activation checklist in Provider Setup", async () => {
    const session = {
      id: "session-activation-checklist",
      name: "Activation Checklist QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const activationChecklist = {
      title: "Frank Create Production Unlock Checklist",
      status: "action_needed",
      summary: {
        ready_provider_models: 2,
        waiting_provider_models: 6,
        diffusion_ready: false,
        checkpoint_count: 0,
        server_key_file: "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\provider_keys.env",
        configured_env_vars: ["OPENAI_API_KEY"],
        missing_env_vars: ["GOOGLE_API_KEY", "RECRAFT_API_KEY", "IDEOGRAM_API_KEY"]
      },
      steps: [
        {
          key: "server-provider-keys",
          label: "Paste rotated live provider keys",
          status: "action_needed",
          detail: "6 live provider models are waiting on server-side keys.",
          action: "Use Provider Setup or user\\frank_create\\provider_keys.env, then reload keys.",
          env_vars: ["GOOGLE_API_KEY", "RECRAFT_API_KEY", "IDEOGRAM_API_KEY"]
        },
        {
          key: "local-checkpoint",
          label: "Install one full local checkpoint",
          status: "action_needed",
          detail: "Local Comfy checkpoint workflows are waiting for a full SDXL-style checkpoint.",
          action: "Put a .safetensors file in models\\checkpoints, then run Demo Doctor.",
          path: "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\models\\checkpoints"
        },
        {
          key: "replicate-rotation",
          label: "Rotate the exposed Replicate token",
          status: "recommended",
          detail: "The token shared in chat should be treated as exposed.",
          action: "Create a fresh Replicate token before live Replicate/fal usage."
        }
      ],
      notes: ["No provider secret values are returned by this endpoint."]
    };

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/activation-checklist")) {
          return jsonResponse(activationChecklist);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({ filePath: "user/frank_create/provider_keys.env", fileExists: false, envVars: [], configuredEnvVars: [], missingEnvVars: [], notes: [] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    expect(await screen.findByText("Frank Create")).toBeInTheDocument();
    openAdvanced();
    expect(screen.getByText("Production unlock checklist")).toBeInTheDocument();
    expect(screen.getByText("Activation checklist tracked: 3 unlock steps")).toBeInTheDocument();
    const checklist = screen.getByLabelText("Production activation checklist");
    expect(within(checklist).getByText("2 / 8 live model paths unlocked")).toBeInTheDocument();
    expect(within(checklist).getByText("Paste rotated live provider keys")).toBeInTheDocument();
    expect(within(checklist).getByText("Install one full local checkpoint")).toBeInTheDocument();
    expect(within(checklist).getByText("Rotate the exposed Replicate token")).toBeInTheDocument();
    expect(within(checklist).getByText("GOOGLE_API_KEY")).toBeInTheDocument();
    expect(within(checklist).getByText("models\\checkpoints")).toBeInTheDocument();
    expect(screen.queryByText(/server-side-openai-secret/i)).not.toBeInTheDocument();
  });

  it("copies a no-secret production unlock plan from the activation checklist", async () => {
    const session = {
      id: "session-activation-copy",
      name: "Activation Copy QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const activationChecklist = {
      title: "Frank Create Production Unlock Checklist",
      status: "action_needed",
      summary: {
        ready_provider_models: 1,
        waiting_provider_models: 8,
        diffusion_ready: false,
        checkpoint_count: 0,
        server_key_file: "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\provider_keys.env",
        configured_env_vars: [],
        missing_env_vars: ["GOOGLE_API_KEY", "OPENAI_API_KEY", "REPLICATE_API_TOKEN"]
      },
      steps: [
        {
          key: "server-provider-keys",
          label: "Paste rotated live provider keys",
          status: "action_needed",
          detail: "8 live provider models are waiting on server-side keys.",
          action: "Use Provider Setup or user\\frank_create\\provider_keys.env, then reload keys.",
          env_vars: ["GOOGLE_API_KEY", "OPENAI_API_KEY", "REPLICATE_API_TOKEN"]
        },
        {
          key: "local-checkpoint",
          label: "Install one full local checkpoint",
          status: "action_needed",
          detail: "Local Comfy checkpoint workflows are waiting for a full SDXL-style checkpoint.",
          action: "Put a .safetensors file in models\\checkpoints, then run Demo Doctor.",
          path: "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\models\\checkpoints",
          minimum_checkpoint_mb: 100
        },
        {
          key: "replicate-rotation",
          label: "Rotate the exposed Replicate token",
          status: "recommended",
          detail: "The token shared in chat should be treated as exposed.",
          action: "Create a fresh rotated Replicate token before live Replicate/fal usage.",
          env_vars: ["REPLICATE_API_TOKEN", "FAL_KEY"]
        }
      ],
      notes: ["No provider secret values are returned by this endpoint."]
    };
    let copied = "";
    vi.stubGlobal("navigator", {
      clipboard: {
        writeText: vi.fn(async (text: string) => {
          copied = text;
        })
      }
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/activation-checklist")) {
          return jsonResponse(activationChecklist);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({
            filePath: "user\\frank_create\\provider_keys.env",
            fileExists: false,
            envVars: ["GOOGLE_API_KEY", "OPENAI_API_KEY", "REPLICATE_API_TOKEN"],
            configuredEnvVars: [],
            missingEnvVars: ["GOOGLE_API_KEY", "OPENAI_API_KEY", "REPLICATE_API_TOKEN"],
            notes: []
          });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    expect(await screen.findByText("Frank Create")).toBeInTheDocument();
    openAdvanced();
    expect(screen.getByText("Production unlock checklist")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Copy unlock plan/i }));

    expect(await screen.findByText("Production unlock plan copied for Cliff. No secret values included.")).toBeInTheDocument();
    expect(copied).toContain("Frank Create Production Unlock Plan");
    expect(copied).toContain("GOOGLE_API_KEY, OPENAI_API_KEY, REPLICATE_API_TOKEN");
    expect(copied).toContain("models\\checkpoints");
    expect(copied).toContain("Rotate the exposed Replicate token");
    expect(copied).toContain("No provider secret values are included.");
    expect(copied).not.toMatch(/sk-|r8_|AIza|server-side-openai|server-side-replicate/i);
  });

  it("preflights the selected model with server-side key and capability checks", async () => {
    const session = {
      id: "session-provider-preflight",
      name: "Provider Preflight QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const config = {
      ...fallbackConfig,
      models: fallbackConfig.models.map((model) =>
        model.id === "openai-gpt-image-2"
          ? { ...model, configured: false, missing_env_vars: ["OPENAI_API_KEY"] }
          : model
      )
    };
    const preflightCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(config);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.endsWith("/api/frank/provider-preflight") && method === "POST") {
          preflightCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({
            status: "blocked",
            ready: false,
            provider: "openai",
            model_id: "openai-gpt-image-2",
            model_label: "gpt-image-2",
            missing_env_vars: ["OPENAI_API_KEY"],
            message: "Add OPENAI_API_KEY in the server key file, then reload keys.",
            payloadPreview: {
              provider: "openai",
              model_id: "openai-gpt-image-2",
              provider_model: "gpt-image-2",
              kind: "generate",
              reference_count: 0,
              prompt_length: 27,
              prompt_preview: "Pink tile product shot."
            }
          });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Comfy is in the room.");
    openModelSettings();
    fireEvent.click(screen.getByRole("button", { name: /gpt-image-2/i }));
    fireEvent.change(screen.getByPlaceholderText(/Brief the image/i), { target: { value: "Pink tile product shot." } });
    openAdvanced();
    fireEvent.click(screen.getByRole("button", { name: /Check selected model/i }));

    await waitFor(() =>
      expect(preflightCalls).toEqual([
        expect.objectContaining({
          model: "openai-gpt-image-2",
          kind: "generate",
          prompt: "Pink tile product shot."
        })
      ])
    );
    const preflightCard = screen.getByLabelText("Selected model preflight");
    expect(within(preflightCard).getByText("Preflight blocked")).toBeInTheDocument();
    expect(within(preflightCard).getAllByText(/OPENAI_API_KEY/).length).toBeGreaterThan(0);
    expect(within(preflightCard).getByText(/Pink tile product shot/i)).toBeInTheDocument();
    expect(screen.queryByText(/server-side-openai/i)).not.toBeInTheDocument();
  });

  it("creates and reloads the server-side provider key file without exposing values", async () => {
    const session = {
      id: "session-provider-env",
      name: "Provider Env QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const providerEnvPath = "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\provider_keys.env";
    const providerStatus = {
      summary: {
        modelCount: 8,
        readyModels: 2,
        waitingModels: 6,
        configuredEnvVars: ["OPENAI_API_KEY"],
        missingEnvVars: ["GOOGLE_API_KEY"]
      },
      providers: [],
      models: fallbackConfig.models.map((model) =>
        model.id === "openai-gpt-image-2"
          ? { ...model, configured: true, configured_env_var: "OPENAI_API_KEY", missing_env_vars: [] }
          : model
      ),
      notes: ["Provider keys are read server-side only."]
    };
    const providerEnvCalls: string[] = [];
    const providerSaveBodies: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.endsWith("/api/frank/provider-env") && method === "GET") {
          return jsonResponse({
            filePath: providerEnvPath,
            fileExists: false,
            envVars: ["OPENAI_API_KEY"],
            configuredEnvVars: [],
            missingEnvVars: ["OPENAI_API_KEY"],
            notes: []
          });
        }
        if (url.endsWith("/api/frank/provider-env/template") && method === "POST") {
          providerEnvCalls.push("template");
          return jsonResponse({
            filePath: providerEnvPath,
            fileExists: true,
            created: true,
            envVars: ["OPENAI_API_KEY"],
            configuredEnvVars: [],
            missingEnvVars: ["OPENAI_API_KEY"],
            notes: []
          }, 201);
        }
        if (url.endsWith("/api/frank/provider-env/save") && method === "POST") {
          providerEnvCalls.push("save");
          providerSaveBodies.push(JSON.parse(String(init?.body)));
          return jsonResponse({
            filePath: providerEnvPath,
            fileExists: true,
            envVars: ["OPENAI_API_KEY"],
            configuredEnvVars: ["OPENAI_API_KEY"],
            missingEnvVars: [],
            savedEnvVars: ["OPENAI_API_KEY"],
            ignoredEnvVars: [],
            readiness: providerStatus,
            notes: ["Secret values stay server-side."]
          });
        }
        if (url.endsWith("/api/frank/provider-env/reload") && method === "POST") {
          providerEnvCalls.push("reload");
          return jsonResponse({
            filePath: providerEnvPath,
            fileExists: true,
            envVars: ["OPENAI_API_KEY"],
            configuredEnvVars: ["OPENAI_API_KEY"],
            missingEnvVars: [],
            loadedEnvVars: ["OPENAI_API_KEY"],
            readiness: providerStatus,
            notes: []
          });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Frank Create");
    openAdvanced();
    expect(screen.getByText(providerEnvPath)).toBeInTheDocument();
    expect(screen.getByText("Create the ignored template first.")).toBeInTheDocument();
    expect(screen.getByLabelText("Save server provider keys")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("OPENAI_API_KEY"), { target: { value: "server-side-openai-secret" } });
    fireEvent.click(screen.getByRole("button", { name: /Save server keys/i }));

    expect(await screen.findByText("1 server key name saved. Secret values stayed server-side.")).toBeInTheDocument();
    expect(providerSaveBodies).toEqual([{ keys: { OPENAI_API_KEY: "server-side-openai-secret" } }]);
    expect(screen.queryByDisplayValue("server-side-openai-secret")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Create key file/i }));
    expect(await screen.findByText("Server key file created. Fill it, then reload keys.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Reload keys/i }));

    expect(await screen.findByText("1 server key name reloaded.")).toBeInTheDocument();
    expect(screen.getByText("2 / 8 provider models ready")).toBeInTheDocument();
    expect(providerEnvCalls).toEqual(["save", "template", "reload"]);
    expect(screen.queryByText(/server-side-openai/i)).not.toBeInTheDocument();
  });

  it("warns when provider key placeholders are ignored", async () => {
    const session = {
      id: "session-provider-placeholder",
      name: "Provider Placeholder QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const providerEnvPath = "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\provider_keys.env";

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.endsWith("/api/frank/provider-env") && method === "GET") {
          return jsonResponse({
            filePath: providerEnvPath,
            fileExists: true,
            envVars: ["OPENAI_API_KEY"],
            configuredEnvVars: [],
            missingEnvVars: ["OPENAI_API_KEY"],
            notes: []
          });
        }
        if (url.endsWith("/api/frank/provider-env/save") && method === "POST") {
          return jsonResponse({
            filePath: providerEnvPath,
            fileExists: true,
            envVars: ["OPENAI_API_KEY"],
            configuredEnvVars: [],
            missingEnvVars: ["OPENAI_API_KEY"],
            savedEnvVars: [],
            ignoredPlaceholderEnvVars: ["OPENAI_API_KEY"],
            readiness: {
              summary: {
                modelCount: 8,
                readyModels: 1,
                waitingModels: 7,
                configuredEnvVars: [],
                missingEnvVars: ["OPENAI_API_KEY"]
              },
              providers: [],
              models: fallbackConfig.models,
              notes: []
            },
            notes: []
          });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Frank Create");
    openAdvanced();
    expect(screen.getByText(providerEnvPath)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("OPENAI_API_KEY"), { target: { value: "YOUR_KEY_HERE" } });
    fireEvent.click(screen.getByRole("button", { name: /Save server keys/i }));

    expect(await screen.findByText("1 placeholder key value was ignored. Paste rotated keys before saving.")).toBeInTheDocument();
  });

  it("runs the Demo Doctor readiness check without exposing secrets", async () => {
    const session = {
      id: "session-demo-doctor",
      name: "Doctor QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const doctor = {
      status: "ready_with_warnings",
      readyForDemo: true,
      headline: "Ready for Cliff",
      summary: {
        activeSessionCount: 1,
        outputAssetCount: 12,
        imageOutputAssetCount: 12,
        approvedAssetCount: 0,
        referenceAssetCount: 1,
        demoCurated: false,
        workflowSmokeOk: true,
        workflowSmokeMediaFileCount: 3,
        demoEvidenceReady: true,
        callBriefReady: true,
        activationChecklistReady: true,
        readinessPackReady: true,
        readinessPackBytes: 1668007,
        readinessPackSha256: "dbea14b96e7fe0a78a61f8b85c0497a229b7ad26816e25c59b1ef85fae8e38c5",
        readyProviderModels: 1,
        waitingProviderModels: 8
      },
      checks: [
        { key: "server", label: "Frank server", status: "ready", detail: "Comfy is responding." },
        { key: "demo_session", label: "Demo session", status: "ready", detail: "Frank Body Demo Studio is seeded." },
        {
          key: "workflow_smoke",
          label: "Workflow smoke",
          status: "ready",
          detail: "Frank Create Workflow Smoke 20260608-202251 passed with 3 handoff media files."
        },
        {
          key: "cliff_pack",
          label: "Cliff Pack",
          status: "ready",
          detail: "1 approved asset ready for handoff."
        },
        {
          key: "demo_evidence",
          label: "Demo evidence",
          status: "ready",
          detail: "Latest demo evidence receipt is ready."
        },
        {
          key: "call_brief",
          label: "Call brief",
          status: "ready",
          detail: "Latest one-page Cliff call brief is ready."
        },
        {
          key: "readiness_pack",
          label: "Readiness pack",
          status: "ready",
          detail: "Latest Cliff readiness ZIP is ready."
        },
        {
          key: "curated_demo",
          label: "Curated demo",
          status: "warning",
          detail: "Demo is not in the Cliff-ready curated shape: hide or reset 12 visible image outputs.",
          action: "Reset demo data."
        },
        {
          key: "provider_keys",
          label: "Provider keys",
          status: "warning",
          detail: "8 live models are waiting on server keys.",
          action: "Local renderer still demos end to end."
        }
      ],
      notes: ["No secret values are returned."]
    };
    const doctorCalls: string[] = [];
    const evidenceCalls: string[] = [];
    const callBriefCalls: string[] = [];
    const readinessPackCalls: string[] = [];

    vi.unstubAllGlobals();
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({
            filePath: "user\\frank_create\\provider_keys.env",
            fileExists: true,
            envVars: ["OPENAI_API_KEY"],
            configuredEnvVars: [],
            missingEnvVars: ["OPENAI_API_KEY"],
            notes: []
          });
        }
        if (url.endsWith("/api/frank/demo-doctor")) {
          doctorCalls.push(url);
          return jsonResponse(doctor);
        }
        if (url.endsWith("/api/frank/demo/evidence") && method === "POST") {
          evidenceCalls.push(String(init?.body));
          return jsonResponse({
            evidence: {
              title: "Frank Create Demo Evidence",
              generated_at: "2026-06-08T21:04:38Z",
              headline: "Ready for Cliff",
              status: "ready_with_warnings",
              ready_for_demo: true,
              summary: {},
              workflow_smoke: {},
              demo_urls: {}
            },
            markdown_path: "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-demo-evidence.md",
            json_path: "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-demo-evidence.json",
            latest_markdown_path:
              "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-demo-evidence-latest.md",
            latest_json_path:
              "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-demo-evidence-latest.json",
            markdown_file: "frank-create-demo-evidence.md",
            json_file: "frank-create-demo-evidence.json",
            latest_markdown_file: "frank-create-demo-evidence-latest.md",
            latest_json_file: "frank-create-demo-evidence-latest.json",
            markdown_url: "/api/frank/demo/evidence/frank-create-demo-evidence.md",
            json_url: "/api/frank/demo/evidence/frank-create-demo-evidence.json",
            latest_markdown_url: "/api/frank/demo/evidence/frank-create-demo-evidence-latest.md",
            latest_json_url: "/api/frank/demo/evidence/frank-create-demo-evidence-latest.json"
          });
        }
        if (url.endsWith("/api/frank/demo/call-brief") && method === "POST") {
          callBriefCalls.push(String(init?.body));
          return jsonResponse({
            brief: {
              title: "Frank Create Cliff Call Brief",
              headline: "Ready for Cliff",
              ready_for_demo: true,
              call_decision: {
                status: "GO WITH WARNINGS",
                headline: "Present the local demo; name the expected live-key/checkpoint caveats.",
                can_present: true,
                warning_keys: ["local_engine", "provider_keys"],
                failure_keys: []
              }
            },
            markdown_path:
              "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-call-brief.md",
            json_path:
              "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-call-brief.json",
            latest_markdown_path:
              "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-call-brief-latest.md",
            latest_json_path:
              "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-call-brief-latest.json",
            markdown_file: "frank-create-call-brief.md",
            json_file: "frank-create-call-brief.json",
            latest_markdown_file: "frank-create-call-brief-latest.md",
            latest_json_file: "frank-create-call-brief-latest.json",
            markdown_url: "/api/frank/demo/call-brief/frank-create-call-brief.md",
            json_url: "/api/frank/demo/call-brief/frank-create-call-brief.json",
            latest_markdown_url: "/api/frank/demo/call-brief/frank-create-call-brief-latest.md",
            latest_json_url: "/api/frank/demo/call-brief/frank-create-call-brief-latest.json"
          });
        }
        if (url.endsWith("/api/frank/demo/readiness-pack") && method === "POST") {
          readinessPackCalls.push(String(init?.body));
          return jsonResponse({
            file_path:
              "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\readiness_packs\\frank-create-cliff-readiness-20260608-221808.zip",
            file_name: "frank-create-cliff-readiness-20260608-221808.zip",
            download_url: "/api/frank/demo/readiness-pack/frank-create-cliff-readiness-20260608-221808.zip",
            latest_file_path:
              "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\readiness_packs\\frank-create-cliff-readiness-latest.zip",
            latest_file_name: "frank-create-cliff-readiness-latest.zip",
            latest_download_url: "/api/frank/demo/readiness-pack/frank-create-cliff-readiness-latest.zip",
            latest_checksum_sha256: "370ca38e9dddc96f774239d836d4b18b2a599b68f19544a3281145b2130cc353",
            latest_implementation_manifest_path:
              "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\readiness_packs\\frank-create-implementation-manifest-latest.md",
            latest_implementation_manifest_url: "/api/frank/demo/readiness-pack/frank-create-implementation-manifest-latest.md",
            manifest: {
              product: "Frank Create",
              purpose: "Cliff call-day readiness pack",
              created_at: "2026-06-08T22:18:08Z",
              base_url: "http://localhost:3000",
              includes: ["evidence/frank-create-demo-evidence-latest.md"],
              missing_files: [],
              screenshot_count: 6,
              screenshot_capture: {
                status: "captured",
                generated_at: "2026-06-08T22:18:08Z",
                tool: "playwright screenshot",
                captured: [
                  { key: "studio_desktop", label: "Studio desktop", file: "studio-live-desktop-latest.png" },
                  { key: "studio_mobile", label: "Studio mobile", file: "studio-live-mobile-latest.png" },
                  { key: "provider_audit", label: "Provider Adapter Audit", file: "provider-audit-live-desktop-latest.png" },
                  { key: "advanced_graph", label: "Advanced Graph", file: "graph-live-desktop-latest.png" },
                  { key: "advanced_graph_mobile", label: "Advanced Graph mobile", file: "graph-live-mobile-latest.png" },
                  { key: "raw_comfy", label: "Raw Comfy canvas", file: "raw-comfy-live-quiet-latest.png" }
                ],
                issues: [],
                issue_count: 0
              },
              browser_qa: {
                status: "ready",
                checks: [
                  { key: "studio_model_preflight", label: "Selected model preflight", status: "ready" },
                  { key: "studio_local_generate", label: "Local Generate", status: "ready" },
                  { key: "studio_masked_edit_generate", label: "Masked edit Generate", status: "ready" }
                ]
              },
              notes: ["No provider secrets are included."],
              cliff_pack: {
                status: "included",
                export_id: "export-cliff-pack",
                session_name: "Frank Body Demo Studio",
                archive_path: "handoffs/frank-body-demo-studio-handoff.zip",
                approved_asset_count: 1,
                approved_image_count: 1,
                approved_video_count: 0,
                reference_count: 1
              }
            },
            evidence: {
              evidence: {
                title: "Frank Create Demo Evidence",
                generated_at: "2026-06-08T22:18:08Z",
                headline: "Ready for Cliff",
                status: "ready_with_warnings",
                ready_for_demo: true,
                summary: {},
                workflow_smoke: {},
                demo_urls: {}
              },
              markdown_path: "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-demo-evidence.md",
              json_path: "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-demo-evidence.json",
              latest_markdown_path:
                "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-demo-evidence-latest.md",
              latest_json_path:
                "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-demo-evidence-latest.json",
              markdown_file: "frank-create-demo-evidence.md",
              json_file: "frank-create-demo-evidence.json",
              latest_markdown_file: "frank-create-demo-evidence-latest.md",
              latest_json_file: "frank-create-demo-evidence-latest.json",
              markdown_url: "/api/frank/demo/evidence/frank-create-demo-evidence.md",
              json_url: "/api/frank/demo/evidence/frank-create-demo-evidence.json",
              latest_markdown_url: "/api/frank/demo/evidence/frank-create-demo-evidence-latest.md",
              latest_json_url: "/api/frank/demo/evidence/frank-create-demo-evidence-latest.json"
            },
            call_brief: {
              brief: {
                title: "Frank Create Cliff Call Brief",
                headline: "Ready for Cliff",
                ready_for_demo: true
              },
              markdown_path:
                "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-call-brief.md",
              json_path:
                "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-call-brief.json",
              latest_markdown_path:
                "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-call-brief-latest.md",
              latest_json_path:
                "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-call-brief-latest.json",
              markdown_file: "frank-create-call-brief.md",
              json_file: "frank-create-call-brief.json",
              latest_markdown_file: "frank-create-call-brief-latest.md",
              latest_json_file: "frank-create-call-brief-latest.json",
              markdown_url: "/api/frank/demo/call-brief/frank-create-call-brief.md",
              json_url: "/api/frank/demo/call-brief/frank-create-call-brief.json",
              latest_markdown_url: "/api/frank/demo/call-brief/frank-create-call-brief-latest.md",
              latest_json_url: "/api/frank/demo/call-brief/frank-create-call-brief-latest.json"
            },
            activation_checklist: {
              checklist: {
                title: "Frank Create Production Unlock Checklist",
                status: "action_needed",
                summary: {
                  ready_provider_models: 1,
                  provider_model_count: 8,
                  waiting_provider_models: 7,
                  diffusion_ready: false,
                  checkpoint_count: 0,
                  server_key_file: "user\\frank_create\\provider_keys.env",
                  configured_env_vars: [],
                  missing_env_vars: ["OPENAI_API_KEY"]
                },
                steps: [
                  {
                    key: "server-provider-keys",
                    label: "Paste rotated live provider keys",
                    status: "action_needed",
                    detail: "8 live provider models are waiting on server-side keys.",
                    action: "Use Provider Setup."
                  }
                ],
                notes: []
              },
              markdown_path:
                "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-activation-checklist.md",
              json_path:
                "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-activation-checklist.json",
              latest_markdown_path:
                "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-activation-checklist-latest.md",
              latest_json_path:
                "F:\\AI Project\\Vibe Coding\\frankComfy\\ComfyUI\\user\\frank_create\\demo_evidence\\frank-create-activation-checklist-latest.json",
              markdown_file: "frank-create-activation-checklist.md",
              json_file: "frank-create-activation-checklist.json",
              latest_markdown_file: "frank-create-activation-checklist-latest.md",
              latest_json_file: "frank-create-activation-checklist-latest.json",
              markdown_url: "/api/frank/demo/activation-checklist/frank-create-activation-checklist.md",
              json_url: "/api/frank/demo/activation-checklist/frank-create-activation-checklist.json",
              latest_markdown_url: "/api/frank/demo/activation-checklist/frank-create-activation-checklist-latest.md",
              latest_json_url: "/api/frank/demo/activation-checklist/frank-create-activation-checklist-latest.json"
            }
          });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Comfy is in the room.");
    openAdvanced();
    expect(screen.getByText("Demo Doctor")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Run demo check/i }));

    await waitFor(() => expect(screen.getAllByText("Ready for Cliff").length).toBeGreaterThanOrEqual(2));
    expect(screen.getByText("Reset demo before Cliff")).toBeInTheDocument();
    expect(screen.getByText("12 visible image outputs; use Reset demo for the clean seed.")).toBeInTheDocument();
    expect(screen.getByText("12 outputs, 1 refs, workflow smoke passed, 8 live models waiting.")).toBeInTheDocument();
    const doctorCheckList = screen.getByLabelText("Demo Doctor checks");
    expect(screen.getByText("Workflow smoke")).toBeInTheDocument();
    expect(within(doctorCheckList).getByText("Cliff Pack")).toBeInTheDocument();
    expect(within(doctorCheckList).getByText("1 approved asset ready for handoff.")).toBeInTheDocument();
    expect(within(doctorCheckList).getByText("Demo evidence")).toBeInTheDocument();
    expect(within(doctorCheckList).getByText("Latest demo evidence receipt is ready.")).toBeInTheDocument();
    expect(within(doctorCheckList).getByText("Call brief")).toBeInTheDocument();
    expect(within(doctorCheckList).getByText("Latest one-page Cliff call brief is ready.")).toBeInTheDocument();
    expect(within(doctorCheckList).getByText("Readiness pack")).toBeInTheDocument();
    expect(within(doctorCheckList).getByText("Latest Cliff readiness ZIP is ready.")).toBeInTheDocument();
    expect(screen.getByText("Provider keys")).toBeInTheDocument();
    expect(screen.getByText("Local renderer still demos end to end.")).toBeInTheDocument();
    expect(screen.getByText("Latest receipt: frank-create-demo-evidence-latest.md")).toBeInTheDocument();
    expect(screen.getByText("Call brief: frank-create-call-brief-latest.md")).toBeInTheDocument();
    expect(screen.getByText("Call pack: frank-create-cliff-readiness-latest.zip")).toBeInTheDocument();
    expect(screen.getByText("Verified SHA-256")).toBeInTheDocument();
    expect(screen.getByText("dbea14b96e7fe0a78a61f8b85c0497a229b7ad26816e25c59b1ef85fae8e38c5")).toBeInTheDocument();
    expect(screen.getByText("Implementation manifest: frank-create-implementation-manifest-latest.md")).toBeInTheDocument();
    expect(doctorCalls).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: /^Open latest receipt$/i }));
    expect(openSpy).toHaveBeenCalledWith("/api/frank/demo/evidence/frank-create-demo-evidence-latest.md", "_blank");
    expect(screen.getByText("Latest receipt link ready: /api/frank/demo/evidence/frank-create-demo-evidence-latest.md")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Open call brief$/i }));
    expect(openSpy).toHaveBeenCalledWith("/api/frank/demo/call-brief/frank-create-call-brief-latest.md", "_blank");
    expect(screen.getByText("Call brief link ready: /api/frank/demo/call-brief/frank-create-call-brief-latest.md")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Download call pack$/i }));
    expect(openSpy).toHaveBeenCalledWith("/api/frank/demo/readiness-pack/frank-create-cliff-readiness-latest.zip", "_blank");
    expect(screen.getByText("Call pack link ready: /api/frank/demo/readiness-pack/frank-create-cliff-readiness-latest.zip")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Open manifest$/i }));
    expect(openSpy).toHaveBeenCalledWith("/api/frank/demo/readiness-pack/frank-create-implementation-manifest-latest.md", "_blank");
    expect(screen.getByText("Implementation manifest link ready: /api/frank/demo/readiness-pack/frank-create-implementation-manifest-latest.md")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Save evidence/i }));
    expect(await screen.findByText("Demo evidence link ready: /api/frank/demo/evidence/frank-create-demo-evidence-latest.md")).toBeInTheDocument();
    expect(screen.getByText("Latest receipt: frank-create-demo-evidence-latest.md")).toBeInTheDocument();
    expect(JSON.parse(evidenceCalls[0])).toMatchObject({ base_url: "http://localhost:3000" });
    expect(openSpy).toHaveBeenCalledWith("/api/frank/demo/evidence/frank-create-demo-evidence-latest.md", "_blank");
    fireEvent.click(screen.getByRole("button", { name: /Open latest receipt/i }));
    expect(openSpy).toHaveBeenCalledWith("/api/frank/demo/evidence/frank-create-demo-evidence-latest.md", "_blank");
    fireEvent.click(screen.getByRole("button", { name: /^Call brief$/i }));
    expect(await screen.findByText("Call brief link ready: /api/frank/demo/call-brief/frank-create-call-brief-latest.md")).toBeInTheDocument();
    expect(screen.getByText("Call brief: frank-create-call-brief-latest.md")).toBeInTheDocument();
    expect(screen.getByText("Call decision: GO WITH WARNINGS")).toBeInTheDocument();
    expect(screen.getByText("Present the local demo; name the expected live-key/checkpoint caveats.")).toBeInTheDocument();
    expect(JSON.parse(callBriefCalls[0])).toMatchObject({ base_url: "http://localhost:3000" });
    expect(openSpy).toHaveBeenCalledWith("/api/frank/demo/call-brief/frank-create-call-brief-latest.md", "_blank");
    fireEvent.click(screen.getByRole("button", { name: /Open call brief/i }));
    expect(openSpy).toHaveBeenCalledWith("/api/frank/demo/call-brief/frank-create-call-brief-latest.md", "_blank");
    fireEvent.click(screen.getByRole("button", { name: /Build call pack/i }));
    expect(await screen.findByText("Call pack link ready: /api/frank/demo/readiness-pack/frank-create-cliff-readiness-latest.zip")).toBeInTheDocument();
    expect(screen.getByText("Call pack: frank-create-cliff-readiness-latest.zip")).toBeInTheDocument();
    expect(screen.getByText("Implementation manifest: frank-create-implementation-manifest-latest.md")).toBeInTheDocument();
    expect(screen.getByText("Call brief: frank-create-call-brief-latest.md")).toBeInTheDocument();
    expect(screen.getByText("Activation checklist: frank-create-activation-checklist-latest.md")).toBeInTheDocument();
    expect(screen.getByText("proof files")).toBeInTheDocument();
    expect(screen.getByText("screenshots")).toBeInTheDocument();
    expect(screen.getByText("missing")).toBeInTheDocument();
    expect(screen.getByText("QA capture")).toBeInTheDocument();
    expect(screen.getByText("captured")).toBeInTheDocument();
    expect(screen.getAllByText("Verified SHA-256").length).toBeGreaterThan(0);
    expect(screen.getByText("370ca38e9dddc96f774239d836d4b18b2a599b68f19544a3281145b2130cc353")).toBeInTheDocument();
    expect(screen.getAllByText("Cliff Pack").length).toBeGreaterThan(0);
    expect(screen.getByText("Open evidence first. Handoff included with 1 approved.")).toBeInTheDocument();
    const cliffGuide = screen.getByLabelText("Cliff demo guide");
    expect(within(cliffGuide).getByText("Cliff Run of Show")).toBeInTheDocument();
    expect(within(cliffGuide).getByText("Image Studio")).toBeInTheDocument();
    expect(within(cliffGuide).getByText("Product Shot Lab")).toBeInTheDocument();
    expect(within(cliffGuide).getByText("Paint edit mask")).toBeInTheDocument();
    expect(within(cliffGuide).getByText("Video Lab")).toBeInTheDocument();
    expect(within(cliffGuide).getByText("Advanced Graph")).toBeInTheDocument();
    expect(within(cliffGuide).getByText("Production checklist ready")).toBeInTheDocument();
    expect(within(cliffGuide).getByText("6 QA screenshots ready")).toBeInTheDocument();
    expect(within(cliffGuide).getByText("Model preflight proved")).toBeInTheDocument();
    expect(within(cliffGuide).getByText("Local Generate proved")).toBeInTheDocument();
    expect(within(cliffGuide).getByText("Masked edit proved")).toBeInTheDocument();
    expect(within(cliffGuide).getByText("Cliff Pack included")).toBeInTheDocument();
    expect(JSON.parse(readinessPackCalls[0])).toMatchObject({ base_url: "http://localhost:3000" });
    expect(openSpy).toHaveBeenCalledWith("/api/frank/demo/readiness-pack/frank-create-cliff-readiness-latest.zip", "_blank");
    fireEvent.click(screen.getByRole("button", { name: /Download call pack/i }));
    expect(openSpy).toHaveBeenCalledWith("/api/frank/demo/readiness-pack/frank-create-cliff-readiness-latest.zip", "_blank");
    fireEvent.click(screen.getByRole("button", { name: /Open manifest/i }));
    expect(openSpy).toHaveBeenCalledWith("/api/frank/demo/readiness-pack/frank-create-implementation-manifest-latest.md", "_blank");
    fireEvent.click(screen.getByRole("button", { name: /Open activation checklist/i }));
    expect(openSpy).toHaveBeenCalledWith(
      "/api/frank/demo/activation-checklist/frank-create-activation-checklist-latest.md",
      "_blank"
    );
    expect(
      screen.getByText("Activation checklist link ready: /api/frank/demo/activation-checklist/frank-create-activation-checklist-latest.md")
    ).toBeInTheDocument();
    expect(screen.queryByText(/server-side-openai|sk-|r8_/i)).not.toBeInTheDocument();
  });

  it("resets the local Cliff demo from Demo Doctor", async () => {
    const scratchSession = {
      id: "session-scratch",
      name: "Messy Scratch",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const demoSession = {
      ...scratchSession,
      id: "session-demo-reset",
      name: "Frank Body Demo Studio",
      project_id: "project-demo",
      summary: "Coffee Scrub Product Image Lab"
    };
    const project = { id: "project-demo", name: "Frank Body Demo Campaign", client: "Frank Body", status: "active" };
    const brief = {
      id: "brief-demo",
      project_id: project.id,
      title: "Coffee Scrub Product Image Lab",
      product_name: "Original Coffee Scrub",
      task_type: "product-shot-lab",
      channel: "PDP / paid social",
      tone: "cheeky-director-ready",
      prompt: "Place this Frank Body coffee scrub as a clean ecommerce product shot on a soft pink counter.",
      negative_prompt: "Avoid warped labels.",
      status: "draft"
    };
    const turn = {
      id: "turn-demo-reset",
      session_id: demoSession.id,
      kind: "generate",
      provider: "local",
      model: "frank-local-comfy",
      prompt: brief.prompt,
      settings_json: JSON.stringify({ aspect_ratio: "1:1", image_size: "2K", count: 4 }),
      reference_asset_ids_json: JSON.stringify(["asset-reference"]),
      frank_body_mode: false,
      preset_key: "product-shot-lab",
      status: "complete"
    };
    const reference = {
      id: "asset-reference",
      session_id: demoSession.id,
      kind: "reference",
      title: "Frank Body Coffee Scrub Reference",
      media_type: "image",
      file_path: "input/frank_create/reference.png",
      preview_url: "/api/view?filename=reference.png&type=input&subfolder=frank_create",
      approval_status: "review"
    };
    const output = {
      id: "asset-output",
      session_id: demoSession.id,
      turn_id: turn.id,
      kind: "candidate",
      title: "Local Comfy Product Shot",
      media_type: "image",
      file_path: "output/frank_create/output.png",
      preview_url: "/api/view?filename=output.png&type=output&subfolder=frank_create",
      approval_status: "review"
    };
    const doctor = {
      status: "ready_with_warnings",
      readyForDemo: true,
      headline: "Ready for Cliff",
      summary: {
        activeSessionCount: 1,
        outputAssetCount: 4,
        approvedAssetCount: 0,
        referenceAssetCount: 1,
        workflowSmokeOk: false,
        readyProviderModels: 1,
        waitingProviderModels: 8
      },
      checks: [
        { key: "demo_session", label: "Demo session", status: "ready", detail: "Frank Body Demo Studio is active." },
        {
          key: "workflow_smoke",
          label: "Workflow smoke",
          status: "warning",
          detail: "Demo was reset. Run the workflow smoke again before the call."
        }
      ],
      notes: []
    };
    const resetCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [scratchSession] });
        }
        if (url.endsWith("/api/frank/turns?session_id=session-scratch")) {
          return jsonResponse({ turns: [] });
        }
        if (url.endsWith("/api/frank/assets?session_id=session-scratch")) {
          return jsonResponse({ assets: [] });
        }
        if (url.endsWith("/api/frank/demo/reset") && method === "POST") {
          resetCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse(
            {
              session: demoSession,
              project,
              brief,
              turn,
              reference,
              assets: [reference, output],
              doctor
            },
            201
          );
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({ filePath: "user/frank_create/provider_keys.env", fileExists: false, envVars: [], configuredEnvVars: [], missingEnvVars: [], notes: [] });
        }
        if (url.endsWith("/api/frank/brand-kit")) {
          return jsonResponse({ brandKit: { style_guidance: "Frank style", negative_prompt: "", reference_notes: "", sync_status: "local" }, filePath: "user/frank_create/brand_kit.json" });
        }
        if (url.endsWith("/api/frank/projects")) {
          return jsonResponse({ projects: [] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Messy Scratch" })).toBeInTheDocument();
    openAdvanced();
    fireEvent.click(screen.getByRole("button", { name: /Reset demo/i }));

    await screen.findByText("Demo reset. Fresh Frank Body starter session loaded.");
    expect(resetCalls).toEqual([expect.objectContaining({ create_assets: true })]);
    expect(screen.getByRole("heading", { name: "Frank Body Demo Studio" })).toBeInTheDocument();
    expect(screen.getByText("Local Comfy Product Shot")).toBeInTheDocument();
    expect(screen.getByText("4 outputs, 1 refs, run workflow smoke, 8 live models waiting.")).toBeInTheDocument();
    expect(screen.getByText("Demo was reset. Run the workflow smoke again before the call.")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Brief the image/i)).toHaveValue(brief.prompt);
  });

  it("uses the left rail to switch into Product Shot Lab mode", async () => {
    const { container } = render(<App />);

    expect(await screen.findByText("Comfy offline")).toBeInTheDocument();
    const productNav = navButton(container, "Product Shot Lab");
    fireEvent.click(productNav);

    expect(productNav).toHaveClass("active");
    expect(screen.getByPlaceholderText(/Brief the image/i)).toHaveValue(fallbackConfig.promptPresets[0].prompt);
    expect(screen.getByText("Product Shot Lab is ready.")).toBeInTheDocument();
  });

  it("uses task shortcuts to send the selected Product Image Lab task to inference", async () => {
    const session = {
      id: "session-task-shortcuts",
      name: "Task Shortcut QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const inferenceCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.endsWith("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({
            filePath: "user\\frank_create\\provider_keys.env",
            fileExists: false,
            envVars: [],
            configuredEnvVars: [],
            missingEnvVars: [],
            notes: []
          });
        }
        if (url.endsWith("/api/frank/inference/turn") && method === "POST") {
          const payload = JSON.parse(String(init?.body));
          inferenceCalls.push(payload);
          return jsonResponse({
            status: "queued",
            turn: {
              id: "turn-task-shortcuts",
              session_id: session.id,
              kind: "generate",
              model: payload.model,
              prompt: payload.prompt,
              preset_key: payload.preset_key,
              frank_body_mode: payload.frank_body_mode,
              status: "queued",
              created_at: "2026-06-08T00:00:00Z",
              updated_at: "2026-06-08T00:00:00Z"
            }
          });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    expect(await screen.findByText("Comfy is in the room.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Product Shot Lab$/i }));
    const taskShortcuts = screen.getByLabelText("Product Image Lab task shortcuts");
    fireEvent.click(within(taskShortcuts).getByRole("button", { name: /Background sweep/i }));

    const promptInput = screen.getByPlaceholderText(/Brief the image/i);
    expect((promptInput as HTMLTextAreaElement).value).toContain("transparent PNG");
    expect(screen.getByText("Background sweep is loaded.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^Generate$/i }));

    await waitFor(() =>
      expect(inferenceCalls).toEqual([
        expect.objectContaining({
          preset_key: "background-remove",
          prompt: expect.stringContaining("transparent PNG")
        })
      ])
    );
  });

  it("remixes the current brief and applies a selected direction", async () => {
    const session = {
      id: "session-remix",
      name: "Remix QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const remixCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({
            filePath: "user\\frank_create\\provider_keys.env",
            fileExists: true,
            envVars: [],
            configuredEnvVars: [],
            missingEnvVars: [],
            notes: []
          });
        }
        if (url.endsWith("/api/frank/prompt-remix") && method === "POST") {
          remixCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({
            variants: [
              { key: "clean", label: "Clean Ecom", prompt: "Clean ecommerce remix for coffee scrub." },
              { key: "lifestyle", label: "Lifestyle", prompt: "Warm bathroom lifestyle remix for coffee scrub." },
              { key: "campaign", label: "Campaign", prompt: "Campaign remix with headline space for coffee scrub." }
            ]
          });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    const promptInput = await screen.findByPlaceholderText(/Brief the image/i);
    fireEvent.change(promptInput, { target: { value: "Coffee scrub on a pink counter" } });
    fireEvent.click(screen.getByRole("button", { name: /^Brief remix$/i }));

    await screen.findByText("Campaign");
    expect(remixCalls).toEqual([
      expect.objectContaining({
        prompt: "Coffee scrub on a pink counter",
        preset_key: "product-shot-lab",
        frank_body_mode: false
      })
    ]);

    const remixPanel = screen.getByLabelText("Brief remix directions");
    fireEvent.click(within(remixPanel).getByRole("button", { name: /Campaign/i }));

    expect(promptInput).toHaveValue("Campaign remix with headline space for coffee scrub.");
    expect(screen.getByText("Campaign direction loaded.")).toBeInTheDocument();
  });

  it("uses Video Lab to create a local motion storyboard asset", async () => {
    const session = {
      id: "session-video",
      name: "Video QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const sourceAsset = {
      id: "asset-video-source",
      session_id: session.id,
      turn_id: "turn-source",
      kind: "candidate",
      title: "Approved source image",
      media_type: "image",
      file_path: "output/frank_create/source.png",
      preview_url: "/api/view?filename=source.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const videoTurn = {
      id: "turn-video",
      session_id: session.id,
      kind: "video",
      provider: "local",
      model: "frank-local-comfy",
      prompt: "Create a short Frank Body motion board.",
      settings_json: JSON.stringify({ aspect_ratio: "16:9", image_size: "1K", count: 1 }),
      source_asset_id: sourceAsset.id,
      reference_asset_ids_json: "[]",
      output_asset_ids_json: JSON.stringify(["asset-video"]),
      frank_body_mode: false,
      status: "complete",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const videoAsset = {
      id: "asset-video",
      session_id: session.id,
      turn_id: videoTurn.id,
      kind: "video",
      title: "Local Comfy / Motion storyboard",
      media_type: "video",
      file_path: "output/frank_create/storyboard.gif",
      preview_url: "/api/view?filename=storyboard.gif&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const videoCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [sourceAsset] });
        }
        if (url.endsWith("/api/frank/videos") && method === "POST") {
          const body = JSON.parse(String(init?.body));
          videoCalls.push(body);
          return jsonResponse({ turn: videoTurn, status: "complete", localEngine: "storyboard", assets: [videoAsset] }, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Approved source image");
    fireEvent.click(navButton(container, "Video Lab"));
    expect(navButton(container, "Video Lab")).toHaveClass("active");
    expect(screen.getByText("Video Lab is ready for a motion board.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^Generate$/i }));

    await waitFor(() =>
      expect(videoCalls).toEqual([
        expect.objectContaining({
          source_asset_id: sourceAsset.id,
          settings: expect.objectContaining({ aspect_ratio: "16:9", image_size: "1K" })
        })
      ])
    );
    expect(await screen.findByText("Local Comfy / Motion storyboard")).toBeInTheDocument();
    expect(screen.getByText("Motion round")).toBeInTheDocument();
  });

  it.skip("legacy xAI video providers are outside the three-key app boundary", async () => {
    const session = {
      id: "session-video-missing-key",
      name: "Video missing key QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const sourceAsset = {
      id: "asset-video-source-missing-key",
      session_id: session.id,
      turn_id: "turn-source",
      kind: "candidate",
      title: "Approved source image",
      media_type: "image",
      file_path: "output/frank_create/source.png",
      preview_url: "/api/view?filename=source.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const videoCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [sourceAsset] });
        }
        if (url.endsWith("/api/frank/videos") && method === "POST") {
          videoCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ error: { code: "missing_key", env_vars: ["XAI_API_KEY"] } }, 400);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Approved source image");
    openModelSettings();
    fireEvent.click(screen.getByRole("button", { name: /Grok Imagine/i }));
    fireEvent.click(navButton(container, "Video Lab"));
    fireEvent.click(screen.getByRole("button", { name: /^Generate$/i }));

    await waitFor(() => expect(videoCalls).toEqual([]));
    expect(screen.getByText("Add XAI_API_KEY in the server key file, then reload keys.")).toBeInTheDocument();
  });

  it.skip("legacy Grok Video Lab rounds are outside the three-key app boundary", async () => {
    const session = {
      id: "session-video-grok",
      name: "Video Grok QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const sourceAsset = {
      id: "asset-video-grok-source",
      session_id: session.id,
      turn_id: "turn-source",
      kind: "candidate",
      title: "Approved source image",
      media_type: "image",
      file_path: "output/frank_create/source.png",
      preview_url: "/api/view?filename=source.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const videoTurn = {
      id: "turn-video-grok",
      session_id: session.id,
      kind: "video",
      provider: "xai",
      model: "grok-imagine-quality",
      prompt: "Create a short Frank Body motion board.",
      settings_json: JSON.stringify({ aspect_ratio: "16:9", image_size: "1K", count: 1 }),
      source_asset_id: sourceAsset.id,
      reference_asset_ids_json: "[]",
      output_asset_ids_json: JSON.stringify(["asset-video-grok"]),
      frank_body_mode: false,
      status: "complete",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const videoAsset = {
      id: "asset-video-grok",
      session_id: session.id,
      turn_id: videoTurn.id,
      kind: "video",
      title: "Grok Imagine / Motion",
      media_type: "video",
      file_path: "output/frank_create/grok.mp4",
      preview_url: "/api/view?filename=grok.mp4&type=output&subfolder=frank_create",
      provider: "xai",
      model: "grok-imagine-quality",
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const videoCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(readyModelConfig("grok-imagine-quality", "XAI_API_KEY"));
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [sourceAsset] });
        }
        if (url.endsWith("/api/frank/videos") && method === "POST") {
          const body = JSON.parse(String(init?.body));
          videoCalls.push(body);
          return jsonResponse({ turn: videoTurn, status: "complete", assets: [videoAsset] }, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Approved source image");
    openModelSettings();
    fireEvent.click(screen.getByRole("button", { name: /Grok Imagine/i }));
    fireEvent.click(navButton(container, "Video Lab"));
    fireEvent.click(screen.getByRole("button", { name: /^Generate$/i }));

    await waitFor(() =>
      expect(videoCalls).toEqual([
        expect.objectContaining({
          model: "grok-imagine-quality",
          source_asset_id: sourceAsset.id,
          settings: expect.objectContaining({ aspect_ratio: "16:9", image_size: "1K" })
        })
      ])
    );
    expect(await screen.findByText("Grok Imagine / Motion")).toBeInTheDocument();
  });

  it.skip("legacy live-video missing-key states are outside the three-key app boundary", async () => {
    const session = {
      id: "session-video-grok-blocked",
      name: "Video Grok Blocked QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const sourceAsset = {
      id: "asset-video-grok-blocked-source",
      session_id: session.id,
      turn_id: "turn-source",
      kind: "candidate",
      title: "Approved source image",
      media_type: "image",
      file_path: "output/frank_create/source.png",
      preview_url: "/api/view?filename=source.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const blockedTurn = {
      id: "turn-video-grok-blocked",
      session_id: session.id,
      kind: "video",
      provider: "xai",
      model: "grok-imagine-quality",
      prompt: "Create a short Frank Body motion board.",
      settings_json: JSON.stringify({ aspect_ratio: "16:9", image_size: "1K", count: 1 }),
      source_asset_id: sourceAsset.id,
      reference_asset_ids_json: "[]",
      output_asset_ids_json: "[]",
      frank_body_mode: false,
      status: "blocked",
      error_json: JSON.stringify({ code: "missing_key", env_vars: ["XAI_API_KEY"] }),
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const videoCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(readyModelConfig("grok-imagine-quality", "XAI_API_KEY"));
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [sourceAsset] });
        }
        if (url.endsWith("/api/frank/videos") && method === "POST") {
          videoCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ turn: blockedTurn, status: "blocked", assets: [], error: { code: "missing_key", env_vars: ["XAI_API_KEY"] } }, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Approved source image");
    openModelSettings();
    fireEvent.click(screen.getByRole("button", { name: /Grok Imagine/i }));
    fireEvent.click(navButton(container, "Video Lab"));
    fireEvent.click(screen.getByRole("button", { name: /^Generate$/i }));

    await waitFor(() => expect(videoCalls).toHaveLength(1));
    expect(await screen.findByText("Server key needed: XAI_API_KEY")).toBeInTheDocument();
    expect(screen.queryByText("Motion board is on the wall.")).not.toBeInTheDocument();
  });

  it("uses Approved Hot mode to select an approved output", async () => {
    const session = {
      id: "session-approved",
      name: "Approved QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const approvedAsset = {
      id: "asset-approved",
      session_id: session.id,
      turn_id: "turn-approved",
      kind: "candidate",
      title: "Approved. Hot. PDP",
      media_type: "image",
      file_path: "output/frank_create/approved.png",
      preview_url: "/api/view?filename=approved.png&type=output&subfolder=frank_create",
      favorite: true,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const reviewAsset = {
      ...approvedAsset,
      id: "asset-review",
      title: "Still in review",
      file_path: "output/frank_create/review.png",
      preview_url: "/api/view?filename=review.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "review"
    };

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [reviewAsset, approvedAsset] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Still in review");
    fireEvent.click(navButton(container, "Approved Hot"));

    expect(navButton(container, "Approved Hot")).toHaveClass("active");
    expect(screen.getByRole("heading", { name: "Approved. Hot. PDP" })).toBeInTheDocument();
    expect(screen.getByText("Approved only. Hot.")).toBeInTheDocument();
  });

  it("compares two output variants side by side and approves from compare mode", async () => {
    const session = {
      id: "session-compare",
      name: "Compare QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const turn = {
      id: "turn-compare",
      session_id: session.id,
      kind: "generate",
      provider: "local",
      model: "frank-local-comfy",
      prompt: "Compare the product crops.",
      settings_json: JSON.stringify({ aspect_ratio: "1:1", image_size: "2K", count: 2 }),
      reference_asset_ids_json: "[]",
      output_asset_ids_json: JSON.stringify(["asset-first", "asset-second"]),
      frank_body_mode: false,
      status: "complete",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const firstAsset = {
      id: "asset-first",
      session_id: session.id,
      turn_id: turn.id,
      kind: "candidate",
      title: "First candidate",
      media_type: "image",
      model: "frank-local-comfy",
      settings_json: JSON.stringify({ aspect_ratio: "1:1" }),
      file_path: "output/frank_create/first.png",
      preview_url: "/api/view?filename=first.png&type=output&subfolder=frank_create",
      width: 2048,
      height: 2048,
      favorite: false,
      approval_status: "review",
      notes: "Cleaner product edge.",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const secondAsset = {
      ...firstAsset,
      id: "asset-second",
      title: "Second candidate",
      file_path: "output/frank_create/second.png",
      preview_url: "/api/view?filename=second.png&type=output&subfolder=frank_create",
      notes: "Warmer background."
    };
    const patchCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [turn] });
        }
        if (url.endsWith(`/api/frank/assets/${firstAsset.id}`) && method === "PATCH") {
          patchCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ asset: { ...firstAsset, approval_status: "approved" } });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [firstAsset, secondAsset] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("First candidate");
    fireEvent.click(screen.getByRole("button", { name: /Compare picks/i }));
    expect(screen.getByText(/Choose another output to compare/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Second candidate/i }));

    const dialog = await screen.findByRole("dialog", { name: /Compare picks/i });
    expect(within(dialog).getByText("Base pick")).toBeInTheDocument();
    expect(within(dialog).getByText("Challenger")).toBeInTheDocument();
    expect(within(dialog).getByText("Cleaner product edge.")).toBeInTheDocument();
    expect(within(dialog).getByText("Warmer background.")).toBeInTheDocument();

    fireEvent.click(within(dialog).getAllByRole("button", { name: /^Approve$/i })[0]);

    await waitFor(() => expect(patchCalls).toEqual([expect.objectContaining({ approval_status: "approved" })]));
    expect(within(dialog).getByText("Approved. Hot.")).toBeInTheDocument();
  });

  it("shows blocked provider key details inside the turn card", async () => {
    const session = {
      id: "session-1",
      name: "QA Studio",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const blockedTurn = {
      id: "turn-blocked",
      session_id: session.id,
      kind: "generate",
      provider: "openai",
      model: "openai-gpt-image-2",
      prompt: "Make a clean PDP image.",
      reference_asset_ids_json: "[]",
      output_asset_ids_json: "[]",
      frank_body_mode: false,
      status: "blocked",
      error_json: JSON.stringify({ code: "missing_key", env_vars: ["OPENAI_API_KEY"] }),
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const configWithReadyOpenAi = {
      ...fallbackConfig,
      models: fallbackConfig.models.map((model) =>
        model.id === "openai-gpt-image-2"
          ? { ...model, configured: true, configured_env_var: "OPENAI_API_KEY", missing_env_vars: [] }
          : model
      )
    };

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(configWithReadyOpenAi);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.endsWith("/api/frank/inference/turn") && method === "POST") {
          return jsonResponse({
            turn: blockedTurn,
            status: "blocked",
            error: { code: "missing_key", env_vars: ["OPENAI_API_KEY"] }
          });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Comfy connected");
    openModelSettings();
    fireEvent.click(screen.getByRole("button", { name: /gpt-image-2/i }));
    fireEvent.change(screen.getByPlaceholderText(/Brief the image/i), {
      target: { value: "Make a clean PDP image." }
    });
    fireEvent.click(screen.getByRole("button", { name: /Generate/i }));

    await screen.findByText("blocked");
    const turnCard = container.querySelector(".turn-card");
    expect(turnCard).not.toBeNull();
    expect(within(turnCard as HTMLElement).getByText(/OPENAI_API_KEY/)).toBeInTheDocument();
  });

  it("shows provider error details in the Studio status strip when an image round fails", async () => {
    const session = {
      id: "session-failed-provider",
      name: "Failed Provider QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const failedTurn = {
      id: "turn-failed-provider",
      session_id: session.id,
      kind: "generate",
      provider: "local",
      model: "frank-local-comfy",
      prompt: "Make a clean PDP image.",
      reference_asset_ids_json: "[]",
      output_asset_ids_json: "[]",
      frank_body_mode: false,
      status: "failed",
      error_json: JSON.stringify({ code: "provider_error", message: "Comfy queue refused the workflow." }),
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.endsWith("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/inference/turn") && method === "POST") {
          return jsonResponse({
            turn: failedTurn,
            status: "failed",
            assets: [],
            error: { code: "provider_error", message: "Comfy queue refused the workflow." }
          });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Comfy connected");
    fireEvent.change(screen.getByPlaceholderText(/Brief the image/i), {
      target: { value: "Make a clean PDP image." }
    });
    fireEvent.click(screen.getByRole("button", { name: /Generate/i }));

    await screen.findByText("failed");
    const statusStrip = container.querySelector(".status-strip");
    expect(statusStrip).not.toBeNull();
    await waitFor(() => expect(statusStrip).toHaveTextContent("Comfy queue refused the workflow."));
  });

  it("guides missing-key provider selections without queueing a doomed turn", async () => {
    const session = {
      id: "session-missing-key-preflight",
      name: "Missing Key Preflight QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const inferenceCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [] });
        }
        if (url.endsWith("/api/frank/inference/turn") && method === "POST") {
          inferenceCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ turn: {}, status: "blocked" }, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Comfy connected");
    openModelSettings();
    fireEvent.click(screen.getByRole("button", { name: /gpt-image-2/i }));
    fireEvent.change(screen.getByPlaceholderText(/Brief the image/i), {
      target: { value: "Make a clean PDP image." }
    });
    fireEvent.click(screen.getByRole("button", { name: /Generate/i }));

    await screen.findByText("Add OPENAI_API_KEY in the server key file, then reload keys.");
    expect(inferenceCalls).toEqual([]);
  });

  it("guides over-limit reference sets without queueing a doomed provider turn", async () => {
    const session = {
      id: "session-reference-limit",
      name: "Reference Limit QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const references = Array.from({ length: 11 }, (_, index) => ({
      id: `asset-ref-${index + 1}`,
      session_id: session.id,
      kind: "reference",
      title: `Reference ${index + 1}`,
      media_type: "image",
      file_path: `input/frank_create/reference-${index + 1}.png`,
      preview_url: `/api/view?filename=reference-${index + 1}.png&type=input&subfolder=frank_create`,
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    }));
    const inferenceCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(readyModelConfig("openai-gpt-image-2", "OPENAI_API_KEY"));
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: references });
        }
        if (url.endsWith("/api/frank/inference/turn") && method === "POST") {
          inferenceCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ turn: {}, status: "complete", assets: [] }, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Comfy connected");
    openModelSettings();
    fireEvent.click(screen.getByRole("button", { name: /gpt-image-2/i }));
    fireEvent.change(screen.getByPlaceholderText(/Brief the image/i), {
      target: { value: "Make a clean PDP image." }
    });
    fireEvent.click(screen.getByRole("button", { name: /Generate/i }));

    await screen.findByText("gpt-image-2 can use 10 references. Remove 1 reference before making this round.");
    expect(inferenceCalls).toEqual([]);
  });

  it("sends only selected references with the next image round", async () => {
    const session = {
      id: "session-selected-refs",
      name: "Selected References QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const references = ["Hero pack shot", "Texture scrape"].map((title, index) => ({
      id: `asset-ref-selected-${index + 1}`,
      session_id: session.id,
      kind: "reference",
      title,
      media_type: "image",
      file_path: `input/frank_create/ref-${index + 1}.png`,
      preview_url: `/api/view?filename=ref-${index + 1}.png&type=input&subfolder=frank_create`,
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    }));
    const completeTurn = {
      id: "turn-selected-refs",
      session_id: session.id,
      kind: "generate",
      provider: "local",
      model: "frank-local-comfy",
      prompt: "Make a PDP image.",
      settings_json: JSON.stringify({ aspect_ratio: "1:1", image_size: "2K", count: 1 }),
      reference_asset_ids_json: JSON.stringify([references[0].id]),
      output_asset_ids_json: "[]",
      frank_body_mode: false,
      status: "complete",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const inferenceCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: references });
        }
        if (url.endsWith("/api/frank/inference/turn") && method === "POST") {
          inferenceCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ turn: completeTurn, status: "complete", assets: [] }, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Comfy connected");
    expect(screen.getByText("2 refs selected")).toBeInTheDocument();

    const referenceDock = screen.getByLabelText("Reference images");
    fireEvent.click(within(referenceDock).getByRole("button", { name: /Texture scrape/i }));

    expect(screen.getByText("1 ref selected")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/Brief the image/i), {
      target: { value: "Make a PDP image." }
    });
    fireEvent.click(screen.getByRole("button", { name: /^Generate$/i }));

    await waitFor(() =>
      expect(inferenceCalls).toEqual([
        expect.objectContaining({
          reference_asset_ids: [references[0].id]
        })
      ])
    );
  });

  it("removes a selected reference from the session without deleting other assets", async () => {
    const session = {
      id: "session-remove-reference",
      name: "Remove Reference QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const reference = {
      id: "asset-remove-ref",
      session_id: session.id,
      kind: "reference",
      title: "Wrong pack shot",
      media_type: "image",
      file_path: "input/frank_create/wrong-pack-shot.png",
      preview_url: "/api/view?filename=wrong-pack-shot.png&type=input&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const output = {
      id: "asset-keep-output",
      session_id: session.id,
      kind: "candidate",
      title: "Keep this output",
      media_type: "image",
      file_path: "output/frank_create/keep.png",
      preview_url: "/api/view?filename=keep.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const deleteCalls: string[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets") && method === "GET") {
          return jsonResponse({ assets: [reference, output] });
        }
        if (url.endsWith(`/api/frank/assets/${reference.id}`) && method === "DELETE") {
          deleteCalls.push(reference.id);
          return jsonResponse({ asset: reference });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({ filePath: "user/frank_create/provider_keys.env", fileExists: false, envVars: [], configuredEnvVars: [], missingEnvVars: [], notes: [] });
        }
        if (url.endsWith("/api/frank/brand-kit")) {
          return jsonResponse({ brandKit: { style_guidance: "Frank style", negative_prompt: "", reference_notes: "", sync_status: "local" }, filePath: "user/frank_create/brand_kit.json" });
        }
        if (url.endsWith("/api/frank/projects")) {
          return jsonResponse({ projects: [] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByRole("heading", { name: "Remove Reference QA" });
    const referenceDock = screen.getByLabelText("Reference images");
    fireEvent.click(within(referenceDock).getByRole("button", { name: /Wrong pack shot/i }));
    fireEvent.click(screen.getByRole("button", { name: /Remove from session/i }));

    await waitFor(() => expect(deleteCalls).toEqual([reference.id]));
    expect(screen.queryByRole("button", { name: /Wrong pack shot/i })).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Keep this output/i })).toBeInTheDocument();
    expect(screen.getByText("Reference removed from this session.")).toBeInTheDocument();
  });

  it("uploads product reference images through Comfy and creates Frank reference assets", async () => {
    const session = {
      id: "session-upload",
      name: "Upload QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const referenceAsset = {
      id: "asset-ref",
      session_id: session.id,
      kind: "reference",
      title: "coffee-scrub.png",
      media_type: "image",
      file_path: "input/frank_create/coffee-scrub.png",
      preview_url: "/api/view?filename=coffee-scrub.png&type=input&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const referenceCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:reference-preview") });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets") && method === "GET") {
          return jsonResponse({ assets: [] });
        }
        if (url.endsWith("/api/upload/image") && method === "POST") {
          return jsonResponse({ name: "coffee-scrub.png", subfolder: "frank_create", type: "input" });
        }
        if (url.endsWith("/api/frank/references") && method === "POST") {
          const body = JSON.parse(String(init?.body));
          referenceCalls.push(body);
          return jsonResponse({ asset: referenceAsset }, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Comfy connected");
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    const file = new File(["fake-image"], "coffee-scrub.png", { type: "image/png" });
    fireEvent.change(input as HTMLInputElement, { target: { files: [file] } });

    await screen.findByText("Reference locked. Nice.");
    expect(referenceCalls).toEqual([
      expect.objectContaining({
        session_id: session.id,
        title: "coffee-scrub.png",
        file_path: "input/frank_create/coffee-scrub.png",
        preview_url: "/api/view?filename=coffee-scrub.png&type=input&subfolder=frank_create"
      })
    ]);
    expect(within(container.querySelector(".reference-dock") as HTMLElement).getByRole("button", { name: /coffee-scrub.png/i })).toBeInTheDocument();
  });

  it("does not lock online reference uploads that fail before the backend can store them", async () => {
    const session = {
      id: "session-reference-fail",
      name: "Reference Failure QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const referenceCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:failed-reference-preview") });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets") && method === "GET") {
          return jsonResponse({ assets: [] });
        }
        if (url.endsWith("/api/upload/image") && method === "POST") {
          return jsonResponse({ error: "upload failed" }, 500);
        }
        if (url.endsWith("/api/frank/references") && method === "POST") {
          referenceCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ asset: {} }, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Comfy connected");
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    fireEvent.change(input as HTMLInputElement, {
      target: { files: [new File(["fake-image"], "failed-reference.png", { type: "image/png" })] }
    });

    await screen.findByText("Reference upload failed. Try again after restarting Comfy.");
    expect(referenceCalls).toEqual([]);
    expect(within(container.querySelector(".reference-dock") as HTMLElement).queryByRole("button", { name: /failed-reference.png/i })).not.toBeInTheDocument();
  });

  it("shows every export preset for a selected output and downloads the created pack", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    const writeText = vi.fn().mockResolvedValue(undefined);
    const session = {
      id: "session-export",
      name: "Export QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const outputAsset = {
      id: "asset-output",
      session_id: session.id,
      turn_id: "turn-export",
      kind: "candidate",
      title: "Approved product shot",
      media_type: "image",
      file_path: "output/frank_create/product.png",
      preview_url: "/api/view?filename=product.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const exportCalls: unknown[] = [];

    vi.unstubAllGlobals();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText }
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [outputAsset] });
        }
        if (url.endsWith("/api/frank/exports") && method === "POST") {
          exportCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse(
            {
              export: { id: "export-high-res", asset_id: outputAsset.id, file_path: "user/frank_create/exports/high-res.png" },
              download_url: "/api/frank/exports/export-high-res/signed-download"
            },
            201
          );
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Approved product shot");
    const exportList = container.querySelector(".export-list");
    expect(exportList).not.toBeNull();
    for (const preset of fallbackConfig.exportPresets.filter((item) => (item.media_types ?? ["image"]).includes("image"))) {
      expect(within(exportList as HTMLElement).getByRole("button", { name: new RegExp(preset.label, "i") })).toBeInTheDocument();
    }
    expect(within(exportList as HTMLElement).queryByRole("button", { name: /Motion storyboard/i })).not.toBeInTheDocument();

    fireEvent.click(within(exportList as HTMLElement).getByRole("button", { name: /High-res master/i }));

    await waitFor(() => expect(exportCalls).toHaveLength(1));
    expect(exportCalls[0]).toMatchObject({ asset_id: outputAsset.id, preset: "high-res-master" });
    expect(openSpy).toHaveBeenCalledWith("/api/frank/exports/export-high-res/signed-download", "_blank");
    expect(screen.getByText("High-res master link ready: /api/frank/exports/export-high-res/signed-download")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Try High-res master link/i }));
    expect(openSpy).toHaveBeenLastCalledWith("/api/frank/exports/export-high-res/signed-download", "_blank");
    fireEvent.click(screen.getByRole("button", { name: /Copy High-res master link/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("/api/frank/exports/export-high-res/signed-download"));
    expect(screen.getByText("High-res master link copied.")).toBeInTheDocument();
    const recentExports = screen.getByText("Recent exports").closest("section");
    expect(recentExports).not.toBeNull();
    fireEvent.click(within(recentExports as HTMLElement).getByRole("button", { name: /High-res master/i }));
    expect(openSpy).toHaveBeenLastCalledWith("/api/frank/exports/export-high-res/signed-download", "_blank");
  });

  it("exports all image channel presets as one channel set pack", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    const session = {
      id: "session-channel-set",
      name: "Channel Set QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const outputAsset = {
      id: "asset-channel-set",
      session_id: session.id,
      turn_id: "turn-channel-set",
      kind: "candidate",
      title: "Channel-ready product shot",
      media_type: "image",
      file_path: "output/frank_create/channel.png",
      preview_url: "/api/view?filename=channel.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const exportSetCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets") && method === "GET") {
          return jsonResponse({ assets: [outputAsset] });
        }
        if (url.endsWith(`/api/frank/assets/${outputAsset.id}/export-set`) && method === "POST") {
          exportSetCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse(
            {
              export: {
                id: "export-channel-set",
                asset_id: outputAsset.id,
                preset: "channel-set",
                file_path: "user/frank_create/exports/channel-set.zip",
                metadata_json: JSON.stringify({ preset_count: 7 }),
                created_at: "2026-06-08T09:00:00Z"
              },
              download_url: "/api/frank/exports/export-channel-set/download",
              metadata: { preset_count: 7 }
            },
            201
          );
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Channel-ready product shot");
    fireEvent.click(screen.getByRole("button", { name: /Export channel set/i }));

    await waitFor(() =>
      expect(exportSetCalls).toEqual([
        expect.objectContaining({
          presets: ["pdp", "email-hero", "instagram-feed", "instagram-story", "paid-social", "transparent-png", "high-res-master"]
        })
      ])
    );
    expect(openSpy).toHaveBeenCalledWith("/api/frank/exports/export-channel-set/download", "_blank");
    expect(screen.getByText("Channel set link ready: /api/frank/exports/export-channel-set/download")).toBeInTheDocument();
    const recentExports = screen.getByText("Recent exports").closest("section");
    expect(recentExports).not.toBeNull();
    expect(within(recentExports as HTMLElement).getByRole("button", { name: /Channel Set/i })).toBeInTheDocument();
  });

  it("shows a storyboard export for selected video assets", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    const session = {
      id: "session-video-export",
      name: "Video Export QA",
      mode: "video",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const videoAsset = {
      id: "asset-video-export",
      session_id: session.id,
      turn_id: "turn-video-export",
      kind: "video",
      title: "Motion storyboard",
      media_type: "video",
      file_path: "output/frank_create/storyboard.gif",
      preview_url: "/api/view?filename=storyboard.gif&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const exportCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [videoAsset] });
        }
        if (url.endsWith("/api/frank/exports") && method === "POST") {
          exportCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ export: { id: "export-video", asset_id: videoAsset.id, file_path: "user/frank_create/exports/storyboard.zip" } }, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    expect(await screen.findAllByText("Motion storyboard")).not.toHaveLength(0);
    const exportList = container.querySelector(".export-list");
    expect(exportList).not.toBeNull();
    expect(within(exportList as HTMLElement).getByRole("button", { name: /Motion storyboard/i })).toBeInTheDocument();
    expect(within(exportList as HTMLElement).queryByRole("button", { name: /PDP/i })).not.toBeInTheDocument();

    fireEvent.click(within(exportList as HTMLElement).getByRole("button", { name: /Motion storyboard/i }));

    await waitFor(() => expect(exportCalls).toEqual([expect.objectContaining({ asset_id: videoAsset.id, preset: "video-storyboard" })]));
    expect(openSpy).toHaveBeenCalledWith("/api/frank/exports/export-video/download", "_blank");
    expect(screen.getByText("Motion storyboard link ready: /api/frank/exports/export-video/download")).toBeInTheDocument();
  });

  it("auto-selects an image output before video outputs for review actions", async () => {
    const session = {
      id: "session-image-before-video",
      name: "Mixed Media Selection QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const videoAsset = {
      id: "asset-video-first",
      session_id: session.id,
      turn_id: "turn-video-first",
      kind: "video",
      title: "Motion storyboard first",
      media_type: "video",
      file_path: "output/frank_create/motion-first.gif",
      preview_url: "/api/view?filename=motion-first.gif&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const imageAsset = {
      id: "asset-image-second",
      session_id: session.id,
      turn_id: "turn-image-second",
      kind: "candidate",
      title: "Product image second",
      media_type: "image",
      file_path: "output/frank_create/product-second.png",
      preview_url: "/api/view?filename=product-second.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [videoAsset, imageAsset] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/provider-env")) {
          return jsonResponse({ filePath: "user/frank_create/provider_keys.env", fileExists: false, envVars: [], configuredEnvVars: [], missingEnvVars: [], notes: [] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    expect(await screen.findByText("Product image second")).toBeInTheDocument();
    expect(container.querySelector(".selected-output h3")).toHaveTextContent("Product image second");
    expect(screen.getByRole("button", { name: /Paint edit mask/i })).toBeInTheDocument();
  });

  it("renders live video assets with playable video previews", async () => {
    const session = {
      id: "session-live-video-preview",
      name: "Live Video Preview QA",
      mode: "video",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const videoAsset = {
      id: "asset-live-video-preview",
      session_id: session.id,
      turn_id: "turn-live-video-preview",
      kind: "video",
      title: "Grok Imagine / Motion",
      media_type: "video",
      file_path: "output/frank_create/live-motion.mp4",
      preview_url: "/api/view?filename=live-motion.mp4&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [videoAsset] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    expect(await screen.findByText("Grok Imagine / Motion")).toBeInTheDocument();
    expect(container.querySelector('video[src*="live-motion.mp4"]')).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Open selected asset/i }));

    await waitFor(() => expect(container.querySelector('.lightbox video[controls][src*="live-motion.mp4"]')).not.toBeNull());
  });

  it("exports a session handoff pack for approved images", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    const session = {
      id: "session-handoff",
      name: "Cliff Review",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const approvedAsset = {
      id: "asset-approved",
      session_id: session.id,
      turn_id: "turn-handoff",
      kind: "candidate",
      title: "Approved. Hot.",
      media_type: "image",
      file_path: "output/frank_create/approved.png",
      preview_url: "/api/view?filename=approved.png&type=output&subfolder=frank_create",
      favorite: true,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const handoffCalls: string[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [approvedAsset] });
        }
        if (url.endsWith(`/api/frank/sessions/${session.id}/handoff`) && method === "POST") {
          handoffCalls.push(String(init?.body));
          return jsonResponse(
            {
              handoff: { id: "export-handoff", asset_id: approvedAsset.id, preset: "session-handoff", file_path: "pack.zip" },
              download_url: "/api/frank/exports/export-handoff/download",
              metadata: {
                asset_count: 1,
                image_count: 1,
                video_count: 0,
                reference_count: 2,
                channel_export_set_count: 1,
                channel_export_file_count: 7
              }
            },
            201
          );
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Approved. Hot.");
    const handoffSection = screen.getByText("Cliff Pack").closest("section")!;
    expect(within(handoffSection).getByText("7 channel-ready exports per approved image")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Open review board/i }));
    expect(openSpy).toHaveBeenCalledWith("/api/frank/sessions/session-handoff/review-board", "_blank");
    expect(screen.getByText("Review board link ready: /api/frank/sessions/session-handoff/review-board")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Open sync manifest/i }));
    expect(openSpy).toHaveBeenCalledWith("/api/frank/sessions/session-handoff/sync-manifest", "_blank");
    expect(screen.getByText("Sync manifest link ready: /api/frank/sessions/session-handoff/sync-manifest")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Export Cliff Pack/i }));

    await waitFor(() => expect(handoffCalls).toHaveLength(1));
    expect(JSON.parse(handoffCalls[0])).toMatchObject({ summary: "Approved Frank Create handoff for review." });
    expect(openSpy).toHaveBeenCalledWith("/api/frank/exports/export-handoff/download", "_blank");
    expect(screen.getByText("Cliff Pack link ready: /api/frank/exports/export-handoff/download")).toBeInTheDocument();
    expect(within(handoffSection).getByText("Packed 7 channel-ready exports across 1 approved image.")).toBeInTheDocument();
    const recentExports = screen.getByText("Recent exports").closest("section")!;
    expect(within(recentExports).getByRole("button", { name: /Cliff Pack/i })).toBeInTheDocument();
    expect(within(recentExports).getByText(/1 approved \/ 2 refs/i)).toBeInTheDocument();
  });

  it("exports a mixed image and motion handoff pack for Cliff", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    const session = {
      id: "session-mixed-handoff",
      name: "Cliff Mixed Review",
      mode: "video",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const approvedImage = {
      id: "asset-approved-image",
      session_id: session.id,
      turn_id: "turn-image",
      kind: "candidate",
      title: "Approved image",
      media_type: "image",
      file_path: "output/frank_create/approved.png",
      preview_url: "/api/view?filename=approved.png&type=output&subfolder=frank_create",
      favorite: true,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const approvedVideo = {
      id: "asset-approved-video",
      session_id: session.id,
      turn_id: "turn-video",
      kind: "video",
      title: "Approved motion",
      media_type: "video",
      file_path: "output/frank_create/motion.gif",
      preview_url: "/api/view?filename=motion.gif&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const handoffCalls: string[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [approvedImage, approvedVideo] });
        }
        if (url.endsWith(`/api/frank/sessions/${session.id}/handoff`) && method === "POST") {
          handoffCalls.push(String(init?.body));
          return jsonResponse(
            {
              handoff: { id: "export-mixed-handoff", asset_id: approvedImage.id, preset: "session-handoff", file_path: "pack.zip" },
              download_url: "/api/frank/exports/export-mixed-handoff/download",
              metadata: { asset_count: 2, image_count: 1, video_count: 1 }
            },
            201
          );
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Approved image");
    const handoffSection = screen.getByText("Cliff Pack").closest("section")!;
    expect(within(handoffSection).getByText("1")).toBeInTheDocument();
    expect(within(handoffSection).getByText("motion")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Export Cliff Pack/i }));

    await waitFor(() => expect(handoffCalls).toHaveLength(1));
    expect(openSpy).toHaveBeenCalledWith("/api/frank/exports/export-mixed-handoff/download", "_blank");
    expect(screen.getByText("Cliff Pack link ready: /api/frank/exports/export-mixed-handoff/download")).toBeInTheDocument();
  });

  it("saves review notes for the selected output", async () => {
    const session = {
      id: "session-notes",
      name: "Notes QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const outputAsset = {
      id: "asset-notes",
      session_id: session.id,
      turn_id: "turn-notes",
      kind: "candidate",
      title: "Campaign candidate",
      media_type: "image",
      file_path: "output/frank_create/candidate.png",
      preview_url: "/api/view?filename=candidate.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      notes: "",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const patchCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets") && method === "GET") {
          return jsonResponse({ assets: [outputAsset] });
        }
        if (url.endsWith(`/api/frank/assets/${outputAsset.id}`) && method === "PATCH") {
          const body = JSON.parse(String(init?.body));
          patchCalls.push(body);
          return jsonResponse({ asset: { ...outputAsset, ...body } });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Campaign candidate");
    fireEvent.change(screen.getByLabelText(/Review notes/i), {
      target: { value: "Use this for email, but crop tighter for paid." }
    });
    fireEvent.click(screen.getByRole("button", { name: /Save note/i }));

    await waitFor(() => expect(patchCalls).toEqual([{ notes: "Use this for email, but crop tighter for paid." }]));
    expect(screen.getByText("Note saved for the next round.")).toBeInTheDocument();
  });

  it("rolls back approval state when the backend rejects a review action", async () => {
    const session = {
      id: "session-approval-fail",
      name: "Approval Failure QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const outputAsset = {
      id: "asset-approval-fail",
      session_id: session.id,
      turn_id: "turn-approval-fail",
      kind: "candidate",
      title: "Maybe campaign pick",
      media_type: "image",
      file_path: "output/frank_create/maybe.png",
      preview_url: "/api/view?filename=maybe.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      notes: "",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets") && method === "GET") {
          return jsonResponse({ assets: [outputAsset] });
        }
        if (url.endsWith(`/api/frank/assets/${outputAsset.id}`) && method === "PATCH") {
          return jsonResponse({ error: { message: "Approval store is temporarily locked." } }, 500);
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Maybe campaign pick");
    const cliffPackButton = screen.getByRole("button", { name: /Export Cliff Pack/i });
    expect(cliffPackButton).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /^Approve$/i }));

    expect(await screen.findByText("Approval store is temporarily locked.")).toBeInTheDocument();
    expect(cliffPackButton).toBeDisabled();
    expect(screen.queryByText("Approved. Hot.")).not.toBeInTheDocument();
  });

  it("shows run metadata for the selected output in the review panel", async () => {
    const session = {
      id: "session-provenance",
      name: "Review Metadata QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const referenceAsset = {
      id: "asset-ref-provenance",
      session_id: session.id,
      kind: "reference",
      title: "Coffee scrub reference",
      media_type: "image",
      file_path: "input/frank_create/reference.png",
      preview_url: "/api/view?filename=reference.png&type=input&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local"
    };
    const sourceAsset = {
      id: "asset-source-provenance",
      session_id: session.id,
      kind: "candidate",
      title: "Source pack shot",
      media_type: "image",
      file_path: "output/frank_create/source.png",
      preview_url: "/api/view?filename=source.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "approved",
      sync_status: "local"
    };
    const outputAsset = {
      id: "asset-output-provenance",
      session_id: session.id,
      turn_id: "turn-provenance",
      kind: "candidate",
      title: "Retouched campaign pick",
      media_type: "image",
      provider: "openai",
      model: "openai-gpt-image-2",
      prompt: "Retouch the label and keep the Frank pink bathroom counter.",
      settings_json: JSON.stringify({
        aspect_ratio: "4:5",
        image_size: "4096",
        count: 2,
        workflow_provenance: {
          workflow_key: "comfy-checkpoint-txt2img",
          engine: "checkpoint_diffusion",
          checkpoint_name: "frank-sdxl.safetensors",
          workflow_json: {
            "1": { class_type: "CheckpointLoaderSimple", inputs: { ckpt_name: "frank-sdxl.safetensors" } },
            "2": { class_type: "SaveImage", inputs: { filename_prefix: "frank-create" } }
          }
        }
      }),
      source_asset_id: sourceAsset.id,
      reference_asset_ids_json: JSON.stringify([referenceAsset.id]),
      file_path: "output/frank_create/retouched.png",
      preview_url: "/api/view?filename=retouched.png&type=output&subfolder=frank_create",
      width: 1600,
      height: 2000,
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T09:00:00Z",
      updated_at: "2026-06-08T09:00:00Z"
    };

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({
            turns: [
              {
                id: "turn-provenance",
                session_id: session.id,
                kind: "edit",
                provider: "openai",
                model: "openai-gpt-image-2",
                prompt: outputAsset.prompt,
                reference_asset_ids_json: outputAsset.reference_asset_ids_json,
                frank_body_mode: false,
                preset_key: "product-cleanup",
                status: "complete",
                created_at: "2026-06-08T09:00:00Z",
                updated_at: "2026-06-08T09:00:00Z"
              }
            ]
          });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [outputAsset, referenceAsset, sourceAsset] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    expect(await screen.findByText("Retouched campaign pick")).toBeInTheDocument();
    const metadata = screen.getByLabelText("Selected asset metadata");
    expect(within(metadata).getByText("Run metadata")).toBeInTheDocument();
    expect(within(metadata).getByText("OpenAI / gpt-image-2")).toBeInTheDocument();
    expect(within(metadata).getByText("4:5 / 4096 / 2 variants")).toBeInTheDocument();
    expect(within(metadata).getByText("1600 x 2000")).toBeInTheDocument();
    expect(within(metadata).getByText("Source pack shot")).toBeInTheDocument();
    expect(within(metadata).getByText("comfy-checkpoint-txt2img / checkpoint_diffusion / frank-sdxl.safetensors")).toBeInTheDocument();
    expect(within(metadata).getByText("1 reference")).toBeInTheDocument();
    expect(within(metadata).getByText("Retouch the label and keep the Frank pink bathroom counter.")).toBeInTheDocument();
  });

  it("copies a selected output run brief with provenance for handoff", async () => {
    const session = {
      id: "session-copy-brief",
      name: "Copy Brief QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const referenceAsset = {
      id: "asset-ref-copy-brief",
      session_id: session.id,
      kind: "reference",
      title: "Coffee scrub texture ref",
      media_type: "image",
      file_path: "input/frank_create/texture.png",
      preview_url: "/api/view?filename=texture.png&type=input&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local"
    };
    const sourceAsset = {
      id: "asset-source-copy-brief",
      session_id: session.id,
      kind: "candidate",
      title: "Original pack shot",
      media_type: "image",
      file_path: "output/frank_create/original.png",
      preview_url: "/api/view?filename=original.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "approved",
      sync_status: "local"
    };
    const outputAsset = {
      id: "asset-output-copy-brief",
      session_id: session.id,
      turn_id: "turn-copy-brief",
      kind: "candidate",
      title: "Copied provenance pick",
      media_type: "image",
      provider: "openai",
      model: "openai-gpt-image-2",
      prompt: "Make the coffee scrub pack feel glossy, pink, and campaign-ready.",
      settings_json: JSON.stringify({
        aspect_ratio: "4:5",
        image_size: "4096",
        count: 2,
        workflow_provenance: {
          workflow_key: "comfy-checkpoint-txt2img",
          engine: "checkpoint_diffusion",
          checkpoint_name: "frank-sdxl.safetensors",
          workflow_json: {
            "1": { class_type: "CheckpointLoaderSimple", inputs: { ckpt_name: "frank-sdxl.safetensors" } },
            "2": { class_type: "SaveImage", inputs: { filename_prefix: "frank-create" } }
          }
        }
      }),
      source_asset_id: sourceAsset.id,
      reference_asset_ids_json: JSON.stringify([referenceAsset.id]),
      file_path: "output/frank_create/copied.png",
      preview_url: "/api/view?filename=copied.png&type=output&subfolder=frank_create",
      width: 1600,
      height: 2000,
      favorite: true,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-08T09:00:00Z",
      updated_at: "2026-06-08T09:00:00Z"
    };
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText }
    });
    const objectUrls: Blob[] = [];
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const createObjectUrlSpy = vi.spyOn(URL, "createObjectURL").mockImplementation((blob) => {
      objectUrls.push(blob as Blob);
      return `blob:workflow-${objectUrls.length}`;
    });
    const revokeObjectUrlSpy = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({
            turns: [
              {
                id: "turn-copy-brief",
                session_id: session.id,
                kind: "edit",
                provider: "openai",
                model: "openai-gpt-image-2",
                prompt: outputAsset.prompt,
                reference_asset_ids_json: outputAsset.reference_asset_ids_json,
                frank_body_mode: true,
                preset_key: "campaign-remix",
                status: "complete",
                created_at: "2026-06-08T09:00:00Z",
                updated_at: "2026-06-08T09:00:00Z"
              }
            ]
          });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [outputAsset, referenceAsset, sourceAsset] });
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    expect(await screen.findByText("Copied provenance pick")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Copy run brief/i }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copied = writeText.mock.calls[0][0] as string;
    expect(copied).toContain("Frank Create Run Brief");
    expect(copied).toContain("Asset: Copied provenance pick");
    expect(copied).toContain("Status: Approved / favorite");
    expect(copied).toContain("Model: OpenAI / gpt-image-2");
    expect(copied).toContain("Settings: 4:5 / 4096 / 2 variants");
    expect(copied).toContain("Workflow: comfy-checkpoint-txt2img / checkpoint_diffusion / frank-sdxl.safetensors");
    expect(copied).toContain(`Raw Comfy: /comfy/?frankAssetId=${encodeURIComponent(outputAsset.id)}`);
    expect(copied).toContain(`Workflow receipt: /api/frank/assets/${encodeURIComponent(outputAsset.id)}/workflow`);
    expect(copied).toContain("Source: Original pack shot");
    expect(copied).toContain("References: Coffee scrub texture ref");
    expect(copied).toContain("Prompt: Make the coffee scrub pack feel glossy, pink, and campaign-ready.");
    expect(copied).toContain("Sync: local");
    expect(copied).not.toMatch(/sk-|r8_|AIza/i);
    expect(screen.getByText("Run brief copied for the handoff.")).toBeInTheDocument();

    clickSpy.mockClear();
    createObjectUrlSpy.mockClear();
    revokeObjectUrlSpy.mockClear();
    objectUrls.length = 0;

    fireEvent.click(screen.getByRole("button", { name: /Download workflow JSON/i }));

    await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
    expect(createObjectUrlSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectUrlSpy).toHaveBeenCalledWith("blob:workflow-1");
    const workflowJson = JSON.parse(await objectUrls[0].text());
    expect(workflowJson.asset_id).toBe(outputAsset.id);
    expect(workflowJson.asset_title).toBe("Copied provenance pick");
    expect(workflowJson.workflow_provenance.workflow_key).toBe("comfy-checkpoint-txt2img");
    expect(workflowJson.workflow_provenance.checkpoint_name).toBe("frank-sdxl.safetensors");
    expect(workflowJson.workflow_bridge).toEqual({
      asset_id: outputAsset.id,
      workflow_key: "comfy-checkpoint-txt2img",
      engine: "checkpoint_diffusion",
      can_open_raw_canvas: true,
      can_load_comfy_api_prompt: true,
      raw_canvas_load_status: "api_prompt_attached",
      comfy_node_types: ["CheckpointLoaderSimple", "SaveImage"],
      raw_canvas_url: `/comfy/?frankAssetId=${encodeURIComponent(outputAsset.id)}`,
      workflow_receipt_url: `/api/frank/assets/${encodeURIComponent(outputAsset.id)}/workflow`
    });
    expect(workflowJson.settings.aspect_ratio).toBe("4:5");
    expect(workflowJson.references).toEqual([{ id: referenceAsset.id, title: "Coffee scrub texture ref" }]);
    expect(workflowJson.source).toEqual({ id: sourceAsset.id, title: "Original pack shot" });
    expect(JSON.stringify(workflowJson)).not.toMatch(/sk-|r8_|AIza/i);
    expect(screen.getByText("Workflow JSON downloaded for this pick.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Open in Comfy Canvas/i }));

    expect(openSpy).toHaveBeenCalledWith(`/comfy/?frankAssetId=${encodeURIComponent(outputAsset.id)}`, "_blank");
    expect(screen.getByText(`Comfy canvas link ready: /comfy/?frankAssetId=${encodeURIComponent(outputAsset.id)}`)).toBeInTheDocument();
  });

  it("promotes a selected output into a selected reference for the next round", async () => {
    const session = {
      id: "session-promote-reference",
      name: "Promote Reference QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const outputAsset = {
      id: "asset-output-promote",
      session_id: session.id,
      turn_id: "turn-output-promote",
      kind: "candidate",
      title: "Approved campaign angle",
      media_type: "image",
      provider: "local",
      model: "frank-local-comfy",
      prompt: "Hero product on a pink bathroom counter.",
      settings_json: JSON.stringify({ aspect_ratio: "4:5", image_size: "2K", count: 1 }),
      file_path: "output/frank_create/approved-angle.png",
      preview_url: "/api/view?filename=approved-angle.png&type=output&subfolder=frank_create",
      width: 1600,
      height: 2000,
      favorite: false,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-08T09:00:00Z",
      updated_at: "2026-06-08T09:00:00Z"
    };
    const promotedReference = {
      ...outputAsset,
      id: "asset-reference-promoted",
      kind: "reference",
      title: "Approved campaign angle reference",
      source_asset_id: outputAsset.id,
      approval_status: "review"
    };
    const referenceCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets") && method === "GET") {
          return jsonResponse({ assets: [outputAsset] });
        }
        if (url.endsWith("/api/frank/references") && method === "POST") {
          const body = JSON.parse(String(init?.body));
          referenceCalls.push(body);
          return jsonResponse({ asset: promotedReference }, 201);
        }
        if (url.includes("/api/frank/exports")) {
          return jsonResponse({ exports: [] });
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    expect(await screen.findByText("Approved campaign angle")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Use as reference/i }));

    await waitFor(() =>
      expect(referenceCalls).toEqual([
        expect.objectContaining({
          session_id: session.id,
          title: "Approved campaign angle reference",
          file_path: outputAsset.file_path,
          preview_url: outputAsset.preview_url,
          source_asset_id: outputAsset.id,
          media_type: "image",
          provider: "local",
          model: "frank-local-comfy",
          prompt: outputAsset.prompt
        })
      ])
    );
    const referenceDock = screen.getByLabelText("Reference images");
    expect(within(referenceDock).getByRole("button", { name: /Approved campaign angle reference/i })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByText("Approved campaign angle is ready as a selected reference.")).toBeInTheDocument();
  });

  it("briefs another campaign round from a selected output", async () => {
    const session = {
      id: "session-round-again",
      name: "Round Again QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const outputAsset = {
      id: "asset-round-source",
      session_id: session.id,
      turn_id: "turn-source",
      kind: "candidate",
      title: "Strong product direction",
      media_type: "image",
      file_path: "output/frank_create/round-source.png",
      preview_url: "/api/view?filename=round-source.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      notes: "Keep the pack larger and make the set warmer.",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const roundTurn = {
      id: "turn-round-again",
      session_id: session.id,
      kind: "edit",
      provider: "local",
      model: "frank-local-comfy",
      prompt: "Make another campaign round.",
      reference_asset_ids_json: "[]",
      output_asset_ids_json: "[]",
      source_asset_id: outputAsset.id,
      frank_body_mode: false,
      status: "complete",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const inferenceCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [outputAsset] });
        }
        if (url.endsWith("/api/frank/inference/turn") && method === "POST") {
          const body = JSON.parse(String(init?.body));
          inferenceCalls.push(body);
          return jsonResponse({ turn: roundTurn, status: "complete", localEngine: "comfy", assets: [] }, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    render(<App />);

    await screen.findByText("Strong product direction");
    const roundStarters = screen.getByLabelText("Make another round");
    fireEvent.click(within(roundStarters).getByRole("button", { name: /Campaign remix/i }));

    expect(screen.getByText("Editing Strong product direction")).toBeInTheDocument();
    expect(screen.getByText("Next round is briefed from this pick.")).toBeInTheDocument();
    const preparedPrompt = screen.getByPlaceholderText(/Brief the image/i) as HTMLTextAreaElement;
    expect(preparedPrompt.value).toContain("Make another campaign round");
    expect(preparedPrompt.value).toContain("Keep the pack larger");

    fireEvent.click(screen.getByRole("button", { name: /^Edit$/i }));

    await waitFor(() =>
      expect(inferenceCalls).toEqual([
        expect.objectContaining({
          kind: "edit",
          edit_source_asset_id: outputAsset.id,
          preset_key: "campaign-variants",
          settings: expect.objectContaining({ count: 4 }),
          prompt: expect.stringContaining("Review note to honor: Keep the pack larger")
        })
      ])
    );
  });

  it("sends selected output as the edit source for an edit round", async () => {
    const session = {
      id: "session-edit",
      name: "Edit QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const outputAsset = {
      id: "asset-edit-source",
      session_id: session.id,
      turn_id: "turn-source",
      kind: "candidate",
      title: "Edit source shot",
      media_type: "image",
      file_path: "output/frank_create/edit-source.png",
      preview_url: "/api/view?filename=edit-source.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const editTurn = {
      id: "turn-edit",
      session_id: session.id,
      kind: "edit",
      provider: "local",
      model: "frank-local-comfy",
      prompt: "Retouch the label and keep the Frank pink background.",
      reference_asset_ids_json: "[]",
      output_asset_ids_json: "[]",
      source_asset_id: outputAsset.id,
      frank_body_mode: false,
      status: "complete",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const editOutput = {
      ...outputAsset,
      id: "asset-edit-output",
      turn_id: editTurn.id,
      title: "Edited source shot"
    };
    const inferenceCalls: unknown[] = [];

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [outputAsset] });
        }
        if (url.endsWith("/api/frank/inference/turn") && method === "POST") {
          const body = JSON.parse(String(init?.body));
          inferenceCalls.push(body);
          return jsonResponse({ turn: editTurn, status: "complete", localEngine: "comfy", assets: [editOutput] }, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Edit source shot");
    fireEvent.click(screen.getByRole("button", { name: /Edit with selected model/i }));
    expect(screen.getByText("Editing Edit source shot")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/Brief the image/i), {
      target: { value: "Retouch the label and keep the Frank pink background." }
    });
    fireEvent.click(screen.getByRole("button", { name: /^Edit$/i }));

    await waitFor(() =>
      expect(inferenceCalls).toEqual([
        expect.objectContaining({
          kind: "edit",
          edit_source_asset_id: outputAsset.id,
          prompt: "Retouch the label and keep the Frank pink background."
        })
      ])
    );
    expect(await screen.findByText("Edited source shot")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Editing Edit source shot")).not.toBeInTheDocument());
    expect(container.querySelector(".composer .primary-button")).toHaveTextContent("Generate");
  });

  it("uploads a mask and sends masked edit requests for models that support masks", async () => {
    const session = {
      id: "session-masked-edit",
      name: "Masked Edit QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const outputAsset = {
      id: "asset-mask-source",
      session_id: session.id,
      turn_id: "turn-source",
      kind: "candidate",
      title: "Mask source shot",
      media_type: "image",
      file_path: "output/frank_create/mask-source.png",
      preview_url: "/api/view?filename=mask-source.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const maskAsset = {
      id: "asset-mask",
      session_id: session.id,
      kind: "mask",
      title: "label-mask.png",
      media_type: "image",
      file_path: "input/frank_create/label-mask.png",
      preview_url: "/api/view?filename=label-mask.png&type=input&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const maskedTurn = {
      id: "turn-masked-edit",
      session_id: session.id,
      kind: "masked_edit",
      provider: "openai",
      model: "openai-gpt-image-2",
      prompt: "Only clean the masked label edge.",
      reference_asset_ids_json: "[]",
      output_asset_ids_json: "[]",
      source_asset_id: outputAsset.id,
      frank_body_mode: false,
      status: "blocked",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const assetCalls: unknown[] = [];
    const inferenceCalls: unknown[] = [];
    const configWithReadyOpenAi = readyModelConfig("openai-gpt-image-2", "OPENAI_API_KEY");

    vi.unstubAllGlobals();
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:mask-preview") });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(configWithReadyOpenAi);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets") && method === "GET") {
          return jsonResponse({ assets: [outputAsset] });
        }
        if (url.endsWith("/api/upload/image") && method === "POST") {
          return jsonResponse({ name: "label-mask.png", subfolder: "frank_create", type: "input" });
        }
        if (url.endsWith("/api/frank/assets") && method === "POST") {
          const body = JSON.parse(String(init?.body));
          assetCalls.push(body);
          return jsonResponse({ asset: maskAsset }, 201);
        }
        if (url.endsWith("/api/frank/inference/turn") && method === "POST") {
          const body = JSON.parse(String(init?.body));
          inferenceCalls.push(body);
          return jsonResponse({
            turn: maskedTurn,
            status: "blocked",
            error: { code: "missing_key", env_vars: ["OPENAI_API_KEY"] }
          }, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Mask source shot");
    openModelSettings();
    fireEvent.click(screen.getByRole("button", { name: /gpt-image-2/i }));
    fireEvent.click(screen.getByRole("button", { name: /Edit with selected model/i }));
    expect(screen.getByText("Editing Mask source shot")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Paint edit mask/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Paint mask/i })).toBeInTheDocument();

    const maskInput = container.querySelector<HTMLInputElement>('input[aria-label="Upload edit mask"]');
    expect(maskInput).not.toBeNull();
    fireEvent.change(maskInput as HTMLInputElement, {
      target: { files: [new File(["mask"], "label-mask.png", { type: "image/png" })] }
    });

    await screen.findByText("Mask locked for this edit.");
    expect(screen.getAllByText("Mask label-mask.png").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByPlaceholderText(/Brief the image/i), {
      target: { value: "Only clean the masked label edge." }
    });
    expect(container.querySelector(".composer .primary-button")).toHaveTextContent("Edit");
    fireEvent.click(container.querySelector(".composer .primary-button") as HTMLButtonElement);

    await waitFor(() =>
      expect(inferenceCalls).toEqual([
        expect.objectContaining({
          kind: "masked_edit",
          model: "openai-gpt-image-2",
          edit_source_asset_id: outputAsset.id,
          mask_asset_id: maskAsset.id,
          prompt: "Only clean the masked label edge."
        })
      ])
    );
    expect(assetCalls).toEqual([
      expect.objectContaining({
        kind: "mask",
        session_id: session.id,
        title: "label-mask.png",
        file_path: "input/frank_create/label-mask.png"
      })
    ]);
  });

  it("does not enable masked edit when an online mask upload fails", async () => {
    const session = {
      id: "session-mask-fail",
      name: "Mask Failure QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const outputAsset = {
      id: "asset-mask-fail-source",
      session_id: session.id,
      turn_id: "turn-source",
      kind: "candidate",
      title: "Mask failure source",
      media_type: "image",
      file_path: "output/frank_create/mask-fail-source.png",
      preview_url: "/api/view?filename=mask-fail-source.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "review",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const assetCalls: unknown[] = [];
    const inferenceCalls: unknown[] = [];
    const editTurn = {
      id: "turn-mask-fail-edit",
      session_id: session.id,
      kind: "edit",
      provider: "openai",
      model: "openai-gpt-image-2",
      prompt: "Clean the label edge.",
      reference_asset_ids_json: "[]",
      output_asset_ids_json: "[]",
      source_asset_id: outputAsset.id,
      frank_body_mode: false,
      status: "blocked",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const configWithReadyOpenAi = readyModelConfig("openai-gpt-image-2", "OPENAI_API_KEY");

    vi.unstubAllGlobals();
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:failed-mask-preview") });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(configWithReadyOpenAi);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets") && method === "GET") {
          return jsonResponse({ assets: [outputAsset] });
        }
        if (url.endsWith("/api/upload/image") && method === "POST") {
          return jsonResponse({ error: "upload failed" }, 500);
        }
        if (url.endsWith("/api/frank/assets") && method === "POST") {
          assetCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ asset: {} }, 201);
        }
        if (url.endsWith("/api/frank/inference/turn") && method === "POST") {
          inferenceCalls.push(JSON.parse(String(init?.body)));
          return jsonResponse({ turn: editTurn, status: "blocked" }, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Mask failure source");
    openModelSettings();
    fireEvent.click(screen.getByRole("button", { name: /gpt-image-2/i }));
    fireEvent.click(screen.getByRole("button", { name: /Edit with selected model/i }));
    const maskInput = container.querySelector<HTMLInputElement>('input[aria-label="Upload edit mask"]');
    expect(maskInput).not.toBeNull();
    fireEvent.change(maskInput as HTMLInputElement, {
      target: { files: [new File(["mask"], "failed-mask.png", { type: "image/png" })] }
    });

    await screen.findByText("Mask upload failed. Try again after restarting Comfy.");
    expect(assetCalls).toEqual([]);
    expect(screen.queryByText("Mask failed-mask.png")).not.toBeInTheDocument();
    expect(container.querySelector(".composer .primary-button")).toHaveTextContent("Edit");

    fireEvent.change(screen.getByPlaceholderText(/Brief the image/i), {
      target: { value: "Clean the label edge." }
    });
    fireEvent.click(container.querySelector(".composer .primary-button") as HTMLButtonElement);

    await waitFor(() => expect(inferenceCalls).toHaveLength(1));
    expect(inferenceCalls[0]).toEqual(expect.objectContaining({ kind: "edit", edit_source_asset_id: outputAsset.id }));
    expect(inferenceCalls[0]).not.toHaveProperty("mask_asset_id");
  });

  it("shows recent export packs and appends a newly created export", async () => {
    const session = {
      id: "session-export-trail",
      name: "Export Trail QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const outputAsset = {
      id: "asset-export-trail",
      session_id: session.id,
      turn_id: "turn-export-trail",
      kind: "candidate",
      title: "Approved export shot",
      media_type: "image",
      file_path: "output/frank_create/export-trail.png",
      preview_url: "/api/view?filename=export-trail.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const existingExport = {
      id: "export-existing",
      asset_id: outputAsset.id,
      preset: "instagram-feed",
      file_path: "user/frank_create/exports/existing.zip",
      metadata_json: "{}",
      created_at: "2026-06-08T08:30:00Z"
    };
    const newExport = {
      id: "export-new",
      asset_id: outputAsset.id,
      preset: "high-res-master",
      file_path: "user/frank_create/exports/new.zip",
      metadata_json: "{}",
      created_at: "2026-06-08T08:35:00Z"
    };
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [outputAsset] });
        }
        if (url.endsWith("/api/frank/exports") && method === "GET") {
          return jsonResponse({ exports: [existingExport] });
        }
        if (url.endsWith("/api/frank/exports") && method === "POST") {
          return jsonResponse({ export: newExport }, 201);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    expect(await screen.findByText("Recent exports")).toBeInTheDocument();
    const recentExports = screen.getByText("Recent exports").closest("section")!;
    expect(within(recentExports).getByRole("button", { name: /Instagram feed/i })).toBeInTheDocument();

    fireEvent.click(within(recentExports).getByRole("button", { name: /Instagram feed/i }));
    expect(openSpy).toHaveBeenCalledWith("/api/frank/exports/export-existing/download", "_blank");

    const exportList = container.querySelector(".export-list") as HTMLElement;
    fireEvent.click(within(exportList).getByRole("button", { name: /High-res master/i }));

    expect(await within(recentExports).findByRole("button", { name: /High-res master/i })).toBeInTheDocument();
    expect(screen.getByText("High-res master link ready: /api/frank/exports/export-new/download")).toBeInTheDocument();
    expect(openSpy).toHaveBeenCalledWith("/api/frank/exports/export-new/download", "_blank");
  });

  it("keeps failed export requests inside the Studio status strip", async () => {
    const session = {
      id: "session-export-fail",
      name: "Export Failure QA",
      mode: "image",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const outputAsset = {
      id: "asset-export-fail",
      session_id: session.id,
      turn_id: "turn-export-fail",
      kind: "candidate",
      title: "Export failure shot",
      media_type: "image",
      file_path: "output/frank_create/export-fail.png",
      preview_url: "/api/view?filename=export-fail.png&type=output&subfolder=frank_create",
      favorite: false,
      approval_status: "approved",
      sync_status: "local",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z"
    };
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/frank/health")) {
          return jsonResponse({ ok: true, product: "Frank Create" });
        }
        if (url.endsWith("/api/frank/config")) {
          return jsonResponse(fallbackConfig);
        }
        if (url.endsWith("/api/frank/sessions") && method === "GET") {
          return jsonResponse({ sessions: [session] });
        }
        if (url.includes("/api/frank/turns")) {
          return jsonResponse({ turns: [] });
        }
        if (url.includes("/api/frank/assets")) {
          return jsonResponse({ assets: [outputAsset] });
        }
        if (url.endsWith("/api/frank/exports") && method === "GET") {
          return jsonResponse({ exports: [] });
        }
        if (url.endsWith("/api/frank/exports") && method === "POST") {
          return jsonResponse({ error: { message: "Export disk is full." } }, 500);
        }
        throw new Error(`Unhandled fetch: ${method} ${url}`);
      })
    );

    const { container } = render(<App />);

    await screen.findByText("Export failure shot");
    openSpy.mockClear();
    const exportList = container.querySelector(".export-list") as HTMLElement;
    fireEvent.click(within(exportList).getByRole("button", { name: /High-res master/i }));

    expect(await screen.findByText("Export disk is full.")).toBeInTheDocument();
    expect(openSpy).not.toHaveBeenCalled();
  });
});

function navButton(container: HTMLElement, label: string) {
  const currentLabel = label === "Approved Hot" ? "Approved only" : label;
  const button = Array.from(container.querySelectorAll<HTMLButtonElement>(".nav-item, .task-chip")).find((item) =>
    item.textContent?.includes(currentLabel)
  );
  expect(button).toBeDefined();
  return button as HTMLButtonElement;
}

function openAdvanced() {
  if (!screen.queryByLabelText("Advanced tools")) {
    fireEvent.click(screen.getByRole("button", { name: /^Advanced$/i }));
  }
}

function openModelSettings() {
  if (!screen.queryByLabelText("Model and output settings")) {
    fireEvent.click(screen.getByRole("button", { name: /Change model/i }));
  }
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

function readyModelConfig(modelId: string, envVar: string) {
  return {
    ...fallbackConfig,
    models: fallbackConfig.models.map((model) =>
      model.id === modelId ? { ...model, configured: true, configured_env_var: envVar, missing_env_vars: [] } : model
    )
  };
}
