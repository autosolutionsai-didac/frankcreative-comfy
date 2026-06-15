import type { Asset, BriefFormState } from "./types";

type ComfyPrompt = Record<string, { class_type: string; inputs: Record<string, unknown> }>;

export function createBriefPayload(
  form: BriefFormState,
  projectId: string,
  referenceImagePath?: string
) {
  const productName = clean(form.productName);
  const title = clean(form.title) || (productName ? `${productName} product shot` : "Frank product shot");

  return {
    project_id: projectId,
    title,
    product_name: productName,
    task_type: form.taskType,
    channel: clean(form.channel),
    tone: clean(form.tone),
    prompt: clean(form.prompt),
    negative_prompt: clean(form.negativePrompt),
    reference_image_path: referenceImagePath,
    status: "draft"
  };
}

export function buildAssetRecordFromReference(args: {
  briefId: string;
  runId: string;
  referenceImagePath: string;
  previewUrl: string;
  productName: string;
}): Omit<Asset, "id" | "created_at" | "updated_at"> {
  const productName = clean(args.productName) || "Frank product";

  return {
    brief_id: args.briefId,
    run_id: args.runId,
    kind: "candidate",
    title: `${productName} / Round 1`,
    file_path: args.referenceImagePath,
    preview_url: args.previewUrl,
    approval_status: "review",
    favorite: false,
    sync_status: "local"
  };
}

export function makeViewUrl(upload: { name: string; subfolder?: string; type?: string }) {
  const params = new URLSearchParams({
    filename: upload.name,
    type: upload.type || "input"
  });

  if (upload.subfolder) {
    params.set("subfolder", upload.subfolder);
  }

  return `/api/view?${params.toString()}`;
}

export function makeStoredImagePath(upload: { name: string; subfolder?: string; type?: string }) {
  const folder = upload.subfolder ? `${upload.subfolder}/` : "";
  return `${upload.type || "input"}/${folder}${upload.name}`;
}

export function buildReferenceCopyPrompt(storedImagePath: string, runId: string): ComfyPrompt {
  const image = normalizeLoadImageName(storedImagePath);
  const prefix = sanitizeFilenamePart(runId);

  return {
    "1": {
      class_type: "LoadImage",
      inputs: { image }
    },
    "2": {
      class_type: "SaveImage",
      inputs: {
        images: ["1", 0],
        filename_prefix: `frank_create/${prefix}`
      }
    }
  };
}

export function extractSavedImages(history: unknown, promptId: string) {
  const root = history as Record<string, unknown>;
  const entry = (root[promptId] || history) as { outputs?: Record<string, { images?: SavedImage[] }> };
  const outputs = entry.outputs || {};

  return Object.values(outputs)
    .flatMap((node) => node.images || [])
    .map((image) => {
      const type = image.type || "output";
      const folder = image.subfolder ? `${image.subfolder}/` : "";
      return {
        filePath: `${type}/${folder}${image.filename}`,
        previewUrl: makeViewUrl({ name: image.filename, subfolder: image.subfolder, type }),
        filename: image.filename
      };
    });
}

export function assetStatusCopy(status: Asset["approval_status"]) {
  if (status === "approved") {
    return "Approved. Hot.";
  }
  if (status === "rejected") {
    return "Not the one.";
  }
  return "In review";
}

function clean(value?: string) {
  return (value || "").trim();
}

function normalizeLoadImageName(storedImagePath: string) {
  return storedImagePath.replace(/\\/g, "/").replace(/^input\//, "");
}

function sanitizeFilenamePart(value: string) {
  return value.replace(/[^a-zA-Z0-9_-]+/g, "_").replace(/^_+|_+$/g, "") || "round";
}

interface SavedImage {
  filename: string;
  subfolder?: string;
  type?: string;
}
