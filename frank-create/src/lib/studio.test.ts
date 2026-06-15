import { describe, expect, it } from "vitest";

import { fallbackConfig } from "./presets";
import { buildTurnRequest, inferenceStatusCopy, normalizeStudioSettingsForModel, selectModelOptions } from "./studio";
import type { StudioModel } from "./types";

const models: StudioModel[] = [
  {
    id: "google-nb-pro",
    label: "Nano Banana Pro",
    provider: "google",
    status: "ready",
    badge: "4K",
    max_resolution_label: "4K",
    capabilities: { generation: true, edit: true, masked_edit: false, video: false },
    allowed_aspect_ratios: ["1:1", "4:5"],
    allowed_image_sizes: ["1K", "2K", "4K"],
    reference_image_limit: 14,
    cost_label: "premium"
  },
  {
    id: "grok-imagine-quality",
    label: "Grok Imagine",
    provider: "xai",
    status: "ready",
    badge: "2K",
    max_resolution_label: "2K",
    capabilities: { generation: true, edit: true, masked_edit: false, video: true },
    allowed_aspect_ratios: ["1:1", "16:9"],
    allowed_image_sizes: ["1K", "2K"],
    reference_image_limit: 4,
    cost_label: "experimental"
  }
];

describe("studio helpers", () => {
  it("keeps Frank Body Mode off by default in turn requests", () => {
    const request = buildTurnRequest({
      sessionId: "session-1",
      modelId: "google-nb-pro",
      prompt: "Create a clean product shot.",
      promptMode: "generate",
      frankBodyMode: false,
      settings: { aspect_ratio: "1:1", image_size: "4K", count: 4 },
      referenceAssetIds: ["asset-ref"],
      editSourceAssetId: undefined
    });

    expect(request).toMatchObject({
      session_id: "session-1",
      kind: "generate",
      model: "google-nb-pro",
      prompt: "Create a clean product shot.",
      frank_body_mode: false
    });
  });

  it("derives selectable settings from the chosen model", () => {
    expect(selectModelOptions(models, "grok-imagine-quality")).toMatchObject({
      allowedImageSizes: ["1K", "2K"],
      resolutionBadge: "2K",
      referenceLimit: 4,
      canEdit: true
    });
  });

  it("advertises local Comfy as the offline-safe Video Lab option", () => {
    expect(selectModelOptions(fallbackConfig.models, "frank-local-comfy")).toMatchObject({
      canVideo: true,
      resolutionBadge: "Ready"
    });
  });

  it("keeps the fallback launch registry aligned with the Cliff model roster", () => {
    expect(fallbackConfig.models.map((model) => model.id)).toEqual([
      "frank-local-comfy",
      "google-nb-pro",
      "google-nb-2",
      "openai-gpt-image-2",
      "flux-1-1-pro-ultra"
    ]);
    expect(fallbackConfig.backlogModels).toEqual([]);
    expect(fallbackConfig.models.find((model) => model.id === "openai-gpt-image-2")?.provider_model).toBe(
      "gpt-image-2"
    );
    expect(fallbackConfig.models.find((model) => model.id === "google-nb-pro")?.provider_api_version).toBe("v1beta");
    expect(fallbackConfig.models.find((model) => model.id === "google-nb-2")?.provider_api_version).toBe("v1beta");
    expect(fallbackConfig.models.find((model) => model.id === "flux-1-1-pro-ultra")?.provider_model).toBe(
      "black-forest-labs/flux-1.1-pro-ultra"
    );
    expect(fallbackConfig.models.find((model) => model.id === "flux-1-1-pro-ultra")?.missing_env_vars).toEqual([
      "REPLICATE_API_TOKEN"
    ]);
    expect(fallbackConfig.tasks.find((task) => task.key === "prompt-remix")?.providers).toContain("google");
  });

  it("normalizes stale or malformed settings when the selected model changes", () => {
    expect(
      normalizeStudioSettingsForModel(
        { aspect_ratio: "4:5", image_size: "4K", count: Number.NaN },
        models[1]
      )
    ).toEqual({
      aspect_ratio: "1:1",
      image_size: "2K",
      count: 1
    });

    expect(
      normalizeStudioSettingsForModel(
        { aspect_ratio: "16:9", image_size: "2K", count: 99 },
        models[1]
      )
    ).toEqual({
      aspect_ratio: "16:9",
      image_size: "2K",
      count: 4
    });
  });

  it("names the local engine used for completed rounds", () => {
    expect(inferenceStatusCopy({ status: "complete", assetCount: 2, localEngine: "comfy" })).toBe(
      "Comfy round is on the wall."
    );
    expect(
      inferenceStatusCopy({
        status: "complete",
        assetCount: 1,
        localEngine: "fallback",
        fallbackReason: "No Comfy queue"
      })
    ).toBe("Comfy was unavailable, so the fallback renderer made this round.");
  });
});
