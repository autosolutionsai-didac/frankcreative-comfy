import { describe, expect, it } from "vitest";

import {
  buildAssetRecordFromReference,
  buildReferenceCopyPrompt,
  createBriefPayload,
  extractSavedImages
} from "./frankWorkflow";

describe("frankWorkflow", () => {
  it("normalizes a product-shot brief for persistence", () => {
    const payload = createBriefPayload(
      {
        productName: "  Cacao Coffee Scrub  ",
        title: "",
        taskType: "background-replace",
        channel: "PDP",
        tone: "Cheeky but premium",
        prompt: "  Warm tiled bathroom, soft flash.  ",
        negativePrompt: "messy counter"
      },
      "project-1",
      "input/cacao.png"
    );

    expect(payload).toMatchObject({
      project_id: "project-1",
      title: "Cacao Coffee Scrub product shot",
      product_name: "Cacao Coffee Scrub",
      task_type: "background-replace",
      channel: "PDP",
      tone: "Cheeky but premium",
      prompt: "Warm tiled bathroom, soft flash.",
      negative_prompt: "messy counter",
      reference_image_path: "input/cacao.png",
      status: "draft"
    });
  });

  it("creates a review asset from an uploaded product reference", () => {
    const asset = buildAssetRecordFromReference({
      briefId: "brief-1",
      runId: "run-1",
      referenceImagePath: "input/cacao.png",
      previewUrl: "/api/view?filename=cacao.png&type=input",
      productName: "Cacao Coffee Scrub"
    });

    expect(asset).toMatchObject({
      brief_id: "brief-1",
      run_id: "run-1",
      kind: "candidate",
      title: "Cacao Coffee Scrub / Round 1",
      file_path: "input/cacao.png",
      preview_url: "/api/view?filename=cacao.png&type=input",
      approval_status: "review",
      favorite: false
    });
  });

  it("builds a lightweight Comfy prompt for the local first round", () => {
    const prompt = buildReferenceCopyPrompt("input/frank_create/cacao.png", "run-1");

    expect(prompt["1"]).toMatchObject({
      class_type: "LoadImage",
      inputs: { image: "frank_create/cacao.png" }
    });
    expect(prompt["2"]).toMatchObject({
      class_type: "SaveImage",
      inputs: {
        images: ["1", 0],
        filename_prefix: "frank_create/run-1"
      }
    });
  });

  it("extracts saved output images from Comfy history", () => {
    const outputs = extractSavedImages(
      {
        "prompt-1": {
          outputs: {
            "2": {
              images: [{ filename: "round_00001_.png", subfolder: "frank_create", type: "output" }]
            }
          }
        }
      },
      "prompt-1"
    );

    expect(outputs).toEqual([
      {
        filePath: "output/frank_create/round_00001_.png",
        previewUrl: "/api/view?filename=round_00001_.png&type=output&subfolder=frank_create",
        filename: "round_00001_.png"
      }
    ]);
  });
});
