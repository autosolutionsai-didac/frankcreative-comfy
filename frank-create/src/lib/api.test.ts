import { afterEach, describe, expect, it, vi } from "vitest";

import { createInferenceTurn } from "./api";
import { fallbackConfig } from "./presets";

describe("api", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("throws the server error message instead of raw JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            error: {
              code: "unsupported_capability",
              message: "google-nb-2 does not support image size 4K"
            }
          }),
          {
            status: 400,
            headers: { "Content-Type": "application/json" }
          }
        )
      )
    );

    let thrown: unknown;
    try {
      await createInferenceTurn({
        kind: "generate",
        model: "google-nb-2",
        prompt: "Fast idea",
        preset_key: "campaign-variants",
        frank_body_mode: false,
        settings: { aspect_ratio: "1:1", image_size: "4K", count: 1 },
        reference_asset_ids: []
      });
    } catch (error) {
      thrown = error;
    }

    expect(thrown).toBeInstanceOf(Error);
    expect((thrown as Error).message).toBe("google-nb-2 does not support image size 4K");
  });

  it("keeps fallback task providers declared in the provider registry", () => {
    const declared = new Set(fallbackConfig.providers.map((provider) => provider.key));
    const used = new Set(fallbackConfig.tasks.flatMap((task) => task.providers));
    const planned = new Set(fallbackConfig.providers.filter((provider) => provider.status === "later").map((provider) => provider.key));

    expect([...used].filter((provider) => !declared.has(provider))).toEqual([]);
    expect([...declared]).toEqual(["local", "google", "replicate", "openai"]);
    expect([...planned]).toEqual([]);
  });
});
