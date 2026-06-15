import type { BrandKit, FrankConfig } from "./types";

export const fallbackBrandKit: BrandKit = {
  style_guidance:
    "Warm off-white, Frank pink, cherry red, coffee brown, and off-black palette. Cheeky but director-ready body-care attitude. Tactile coffee/body-scrub textures, glossy skin-care detail, warm flash, editorial realism, and packaging that stays clean.",
  negative_prompt:
    "Avoid warped logos, extra lids, plastic skin, over-airbrushed bodies, muddy coffee spills, generic beige spa stock-photo styling, and unreadable packaging labels.",
  reference_notes:
    "Use approved Frank Body pack shots first, then lifestyle/body-care references. Keep source product identity more important than style experiments.",
  sync_status: "local",
  remote_id: null
};

export const fallbackConfig: FrankConfig = {
  tasks: [
    {
      key: "product-shot-lab",
      label: "Product Shot Lab",
      description: "Upload product/reference images, generate variants, approve, and export.",
      providers: ["local", "google", "replicate", "openai"]
    },
    {
      key: "background-remove",
      label: "Background sweep",
      description: "Transparent PNGs and clean product isolation.",
      providers: ["local", "openai"]
    },
    {
      key: "background-replace",
      label: "Background glow-up",
      description: "Frank-branded lifestyle and campaign backdrops.",
      providers: ["local", "google", "openai"]
    },
    {
      key: "product-cleanup",
      label: "Product polish",
      description: "Retouch labels, dust, shadows, and product edges.",
      providers: ["local", "openai"]
    },
    {
      key: "campaign-variants",
      label: "Campaign remix",
      description: "Creative rounds from one approved product direction.",
      providers: ["local", "google", "openai", "replicate"]
    },
    {
      key: "aspect-crops",
      label: "Crop the goods",
      description: "PDP, email, feed, story, and paid-social crops.",
      providers: ["local"]
    },
    {
      key: "upscale-enhance",
      label: "Make it bigger",
      description: "High-res masters with product detail intact.",
      providers: ["local", "openai"]
    },
    {
      key: "prompt-remix",
      label: "Brief remix",
      description: "Sharper directions before another creative round.",
      providers: ["local", "openai", "google"]
    }
  ],
  providers: [
    { key: "local", label: "Local RTX", type: "local", status: "ready" },
    { key: "google", label: "Gemini / Nano Banana", type: "api", status: "curated" },
    { key: "replicate", label: "Replicate", type: "api", status: "curated" },
    { key: "openai", label: "OpenAI image/edit", type: "api", status: "curated" }
  ],
  models: [
    {
      id: "frank-local-comfy",
      label: "Frank Local Comfy Studio",
      short_label: "Local Comfy",
      provider: "local",
      provider_model: "frank-local-comfy",
      status: "ready",
      badge: "Ready",
      max_resolution_label: "4K",
      description:
        "Local Comfy-backed product variants, edits, masked retouch demos, crops, export prep, and storyboard motion without API keys.",
      capabilities: { generation: true, edit: true, masked_edit: true, video: true },
      allowed_aspect_ratios: ["1:1", "4:5", "3:4", "16:9", "9:16", "3:2", "2:3"],
      allowed_image_sizes: ["1K", "2K", "4K"],
      reference_image_limit: 8,
      cost_label: "local",
      configured: true,
      missing_env_vars: []
    },
    {
      id: "google-nb-pro",
      label: "Gemini 3 Pro Image / Nano Banana Pro",
      short_label: "Nano Banana Pro",
      provider: "google",
      provider_model: "gemini-3-pro-image",
      provider_api_version: "v1beta",
      status: "ready",
      badge: "4K",
      max_resolution_label: "4K",
      description: "Beauty/editorial generation and broad edits.",
      capabilities: { generation: true, edit: true, masked_edit: false, video: false },
      allowed_aspect_ratios: ["1:1", "4:5", "3:4", "16:9", "9:16"],
      allowed_image_sizes: ["1K", "2K", "4K"],
      reference_image_limit: 14,
      cost_label: "premium",
      configured: false,
      missing_env_vars: ["GOOGLE_API_KEY"]
    },
    {
      id: "google-nb-2",
      label: "Gemini 3.1 Flash Image / NB 2",
      short_label: "NB 2",
      provider: "google",
      provider_model: "gemini-3.1-flash-image",
      provider_api_version: "v1beta",
      status: "ready",
      badge: "4K",
      max_resolution_label: "4K",
      description: "Fast 4K ideation and cheaper rounds.",
      capabilities: { generation: true, edit: true, masked_edit: false, video: false },
      allowed_aspect_ratios: ["1:1", "4:5", "3:4", "16:9", "9:16"],
      allowed_image_sizes: ["1K", "2K", "4K"],
      reference_image_limit: 14,
      cost_label: "fast",
      configured: false,
      missing_env_vars: ["GOOGLE_API_KEY"]
    },
    {
      id: "openai-gpt-image-2",
      label: "OpenAI gpt-image-2",
      short_label: "gpt-image-2",
      provider: "openai",
      provider_model: "gpt-image-2",
      status: "ready",
      badge: "4K",
      max_resolution_label: "4K",
      description: "Generation, edits, and masked inpainting.",
      capabilities: { generation: true, edit: true, masked_edit: true, video: false },
      allowed_aspect_ratios: ["1:1", "4:5", "3:4", "16:9", "9:16"],
      allowed_image_sizes: ["1024", "2048", "4096"],
      reference_image_limit: 10,
      cost_label: "premium",
      configured: false,
      missing_env_vars: ["OPENAI_API_KEY"]
    },
    {
      id: "flux-1-1-pro-ultra",
      label: "FLUX 1.1 Pro Ultra",
      short_label: "FLUX Ultra",
      provider: "replicate",
      provider_model: "black-forest-labs/flux-1.1-pro-ultra",
      status: "ready",
      badge: "4MP",
      max_resolution_label: "4MP",
      description: "Photorealism, 4MP output, and Frank LoRA experiments through Replicate when approved.",
      capabilities: { generation: true, edit: false, masked_edit: false, video: false },
      allowed_aspect_ratios: ["1:1", "4:5", "3:4", "16:9", "9:16"],
      allowed_image_sizes: ["1MP", "4MP"],
      reference_image_limit: 4,
      cost_label: "photo",
      configured: false,
      missing_env_vars: ["REPLICATE_API_TOKEN"],
      lora_candidate: true
    }
  ],
  backlogModels: [],
  promptPresets: [
    {
      key: "product-shot-lab",
      label: "Product Shot Lab",
      description: "Product-first image for PDP, retouching, and crops.",
      prompt: "Product-first composition, clean label, honest skin-care texture, Frank pink accent."
    },
    {
      key: "clean-ecom",
      label: "Clean Ecom",
      description: "Crisp commerce frame with readable packaging.",
      prompt: "Clean Ecom structure: centered product, readable label, soft realistic shadow, no visual clutter."
    },
    {
      key: "fb-lifestyle",
      label: "FB Lifestyle",
      description: "Warm bathroom, beach, or bedroom body-care moment.",
      prompt: "Frank lifestyle scene, tactile surfaces, cheeky confidence, natural skin-care mess kept polished."
    },
    {
      key: "fb-model-image",
      label: "FB Model Image",
      description: "Inclusive beauty/editorial body-care concept.",
      prompt: "Confident body-care model moment, warm direct flash, tactile product use, inclusive casting."
    },
    {
      key: "campaign-variants",
      label: "Campaign Variants",
      description: "Creative rounds from one approved product direction.",
      prompt: "Keep product recognizable, push set styling, leave channel-ready headline space, sharpen the Frank Body attitude."
    },
    {
      key: "product-texture",
      label: "Product Texture",
      description: "Macro scrub, cream, and tactile swipes.",
      prompt: "Macro coffee scrub grains, creamy body-care texture, tactile swipes, high detail."
    },
    {
      key: "retail-mock",
      label: "Retail Mock",
      description: "Packaging, shelf, display, and type exploration.",
      prompt: "Retail mockup, packaging readable, shelf/display context, campaign headline space, sharp typography."
    }
  ],
  exportPresets: [
    { key: "pdp", label: "PDP", size: "1600 x 2000", format: "PNG/JPG", media_types: ["image"] },
    { key: "email-hero", label: "Email hero", size: "2400 x 1350", format: "JPG", media_types: ["image"] },
    { key: "instagram-feed", label: "Instagram feed", size: "1080 x 1350", format: "JPG", media_types: ["image"] },
    { key: "instagram-story", label: "Instagram story", size: "1080 x 1920", format: "JPG", media_types: ["image"] },
    { key: "paid-social", label: "Paid social", size: "1200 x 628", format: "JPG", media_types: ["image"] },
    { key: "transparent-png", label: "Transparent PNG", size: "source", format: "PNG", media_types: ["image"] },
    { key: "high-res-master", label: "High-res master", size: "source/upscaled", format: "PNG/TIFF", media_types: ["image"] },
    { key: "video-storyboard", label: "Motion storyboard", size: "source loop", format: "GIF + JSON", media_types: ["video"] }
  ],
  localEngine: {
    active_engine: "frank_renderer",
    diffusion_ready: false,
    checkpoint_count: 0,
    checkpoints: [],
    ignored_checkpoints: [],
    minimum_checkpoint_mb: 100,
    checkpoint_dir: "models\\checkpoints",
    model_root: "models",
    setup_readme: "models\\FRANK_CREATE_MODELS_README.txt",
    setup_steps: [
      "Put a full SDXL-style .safetensors checkpoint in models\\checkpoints for Local Comfy txt2img, reference/edit img2img, and masked inpaint workflows.",
      "Files smaller than 100 MB are treated as incomplete downloads/placeholders.",
      "Use the raw Comfy canvas for FLUX or custom loader workflows until a curated FLUX app workflow is added.",
      "Run Demo Doctor again after adding model files."
    ],
    recommended_checkpoints: [
      {
        label: "SDXL 1.0 Base or an approved SDXL product checkpoint",
        use: "Best first local checkpoint for campaign/image rounds, reference-guided edits, and masked retouching through built-in Comfy txt2img/img2img/inpaint workflows.",
        folder: "models\\checkpoints"
      },
      {
        label: "Frank-approved SDXL LoRA",
        use: "Later brand-tuning layer for open models after the image set and rights are approved.",
        folder: "models\\loras"
      }
    ],
    note: "No diffusion checkpoint detected. Local Comfy uses the Frank renderer until a checkpoint is installed."
  },
  voice: {
    appTitle: "The Art Dept.",
    labTitle: "Frank Body Image Studio",
    primaryAction: "Generate",
    emptyState: "Waiting for the brief...",
    approved: "Approved. Hot."
  },
  advancedGraphUrl: "/comfy/"
};

export const defaultBrief = {
  title: "",
  productName: "",
  taskType: "background-replace",
  channel: "PDP",
  tone: "Cheeky but director-ready",
  prompt: "",
  negativePrompt: ""
};
