export type ApprovalStatus = "review" | "approved" | "rejected";

export interface FrankTask {
  key: string;
  label: string;
  description: string;
  providers: string[];
}

export interface FrankProvider {
  key: string;
  label: string;
  type: "local" | "api";
  status: "ready" | "curated" | "later";
}

export interface ExportPreset {
  key: string;
  label: string;
  size: string;
  format: string;
  media_types?: Array<"image" | "video">;
}

export interface StudioCapabilities {
  generation: boolean;
  edit: boolean;
  masked_edit: boolean;
  video: boolean;
}

export interface StudioModel {
  id: string;
  label: string;
  short_label?: string;
  provider: string;
  provider_model?: string;
  provider_api_version?: string;
  provider_video_model?: string;
  env_vars?: string[];
  status: "ready" | "disabled" | "experimental";
  badge: string;
  max_resolution_label: string;
  description?: string;
  capabilities: StudioCapabilities;
  allowed_aspect_ratios: string[];
  allowed_image_sizes: string[];
  reference_image_limit: number;
  cost_label: string;
  configured?: boolean;
  configured_env_var?: string;
  missing_env_vars?: string[];
  lora_candidate?: boolean;
}

export interface PromptPreset {
  key: string;
  label: string;
  description: string;
  prompt: string;
}

export interface PromptRemixVariant {
  key: string;
  label: string;
  prompt: string;
}

export interface BrandKit {
  style_guidance: string;
  negative_prompt: string;
  reference_notes: string;
  sync_status?: string;
  remote_id?: string | null;
  updated_at?: string;
}

export interface BrandContextReceiptResult {
  receipt: {
    title: string;
    generated_at: string;
    session: Record<string, unknown>;
    summary: {
      style_guidance_chars: number;
      negative_prompt_chars: number;
      reference_notes_chars: number;
      reference_asset_count: number;
      approved_asset_count: number;
      prompt_guided_status: "missing" | "starter" | "ready" | "strong";
      lora_training_status: "missing" | "starter" | "ready" | "strong";
      prompt_guided_target: string;
      lora_training_target: string;
    };
    brand_kit: BrandKit;
    reference_assets: Array<Record<string, unknown>>;
    approved_assets: Array<Record<string, unknown>>;
    training_recommendation: Record<string, string>;
    next_inputs: string[];
  };
  markdown_path: string;
  json_path: string;
  latest_markdown_path?: string;
  latest_json_path?: string;
  markdown_file: string;
  json_file: string;
  latest_markdown_file?: string;
  latest_json_file?: string;
  markdown_url: string;
  json_url: string;
  latest_markdown_url?: string;
  latest_json_url?: string;
}

export interface LocalEngineStatus {
  active_engine: string;
  diffusion_ready: boolean;
  checkpoint_count: number;
  checkpoints: string[];
  ignored_checkpoints?: Array<{
    name: string;
    path?: string;
    size_bytes?: number;
    reason?: string;
  }>;
  minimum_checkpoint_mb?: number;
  checkpoint_dir?: string;
  model_root?: string;
  setup_readme?: string;
  setup_steps?: string[];
  recommended_checkpoints?: Array<{
    label: string;
    use: string;
    folder: string;
  }>;
  note: string;
}

export interface WorkflowBlueprint {
  key: string;
  label: string;
  use: string;
  node_types: string[];
  workflow_json: Record<string, unknown>;
}

export interface WorkflowBlueprintsResponse {
  status: "ready" | "warning" | "fail";
  product: string;
  checkpoint_name: string;
  source_placeholder?: string;
  mask_placeholder?: string;
  note: string;
  blueprints: WorkflowBlueprint[];
}

export interface FrankConfig {
  tasks: FrankTask[];
  providers: FrankProvider[];
  exportPresets: ExportPreset[];
  models: StudioModel[];
  backlogModels: StudioModel[];
  promptPresets: PromptPreset[];
  localEngine: LocalEngineStatus;
  voice: {
    appTitle: string;
    labTitle: string;
    primaryAction: string;
    emptyState: string;
    approved: string;
  };
  advancedGraphUrl: string;
}

export interface ProviderReadiness {
  summary: {
    modelCount: number;
    readyModels: number;
    waitingModels: number;
    configuredEnvVars: string[];
    missingEnvVars: string[];
  };
  providers: Array<{
    provider: string;
    configured: boolean;
    model_count: number;
    ready_model_count: number;
    waiting_model_count: number;
    configured_env_vars: string[];
    missing_env_vars: string[];
    models: string[];
  }>;
  models: StudioModel[];
  notes: string[];
}

export interface ProviderReadinessReceiptResult {
  receipt: {
    title: string;
    generated_at: string;
    summary: {
      model_count: number;
      ready_models: number;
      waiting_models: number;
      configured_env_vars: string[];
      missing_env_vars: string[];
    };
    providers: ProviderReadiness["providers"];
    model_roster: Array<Record<string, unknown>>;
    adapter_audit: ProviderAdapterAudit;
    mocked_live_path_coverage: Array<Record<string, unknown>>;
    notes: string[];
  };
  markdown_path: string;
  json_path: string;
  latest_markdown_path?: string;
  latest_json_path?: string;
  markdown_file: string;
  json_file: string;
  latest_markdown_file?: string;
  latest_json_file?: string;
  markdown_url: string;
  json_url: string;
  latest_markdown_url?: string;
  latest_json_url?: string;
}

export interface ActivationChecklist {
  title: string;
  status: "ready" | "action_needed";
  summary: {
    ready_provider_models: number;
    provider_model_count: number;
    waiting_provider_models: number;
    diffusion_ready: boolean;
    checkpoint_count: number;
    server_key_file: string;
    configured_env_vars: string[];
    missing_env_vars: string[];
  };
  steps: Array<{
    key: string;
    label: string;
    status: "ready" | "action_needed" | "recommended";
    detail: string;
    action: string;
    env_vars?: string[];
    path?: string;
    minimum_checkpoint_mb?: number;
  }>;
  notes: string[];
}

export interface ActivationChecklistReceiptResult {
  checklist: ActivationChecklist;
  markdown_path: string;
  json_path: string;
  latest_markdown_path?: string;
  latest_json_path?: string;
  markdown_file: string;
  json_file: string;
  latest_markdown_file?: string;
  latest_json_file?: string;
  markdown_url: string;
  json_url: string;
  latest_markdown_url?: string;
  latest_json_url?: string;
}

export interface ProviderEnvStatus {
  filePath: string;
  fileExists: boolean;
  envVars: string[];
  configuredEnvVars: string[];
  missingEnvVars: string[];
  notes: string[];
  created?: boolean;
  loadedEnvVars?: string[];
  savedEnvVars?: string[];
  ignoredEnvVars?: string[];
  ignoredPlaceholderEnvVars?: string[];
  readiness?: ProviderReadiness;
}

export interface ProviderPreflight {
  status: "ready" | "blocked" | "unsupported";
  ready: boolean;
  provider?: string | null;
  model_id?: string;
  model_label?: string;
  configured_env_var?: string;
  missing_env_vars: string[];
  message: string;
  payloadPreview: {
    provider?: string | null;
    provider_model?: string;
    model_id?: string;
    kind: "generate" | "edit" | "masked_edit" | "video";
    settings?: Record<string, unknown>;
    reference_count: number;
    reference_limit: number;
    source_asset_id?: string;
    mask_asset_id?: string;
    frank_body_mode: boolean;
    preset_key?: string;
    prompt_length: number;
    prompt_preview: string;
  };
}

export interface ProviderAdapterAudit {
  title: string;
  generated_at: string;
  summary: {
    model_count: number;
    runner_registered: number;
    missing_runners: number;
    ready_models: number;
    waiting_for_key: number;
    preview_failures: number;
    operation_preview_count?: number;
    operation_preview_failures?: number;
    no_spend: boolean;
    secret_values_returned: boolean;
  };
  models: Array<{
    model_id: string;
    label: string;
    provider: string;
    provider_model?: string;
    badge?: string;
    status: "ready" | "waiting_for_key" | "adapter_missing" | "preview_failed";
    configured: boolean;
    configured_env_var?: string;
    missing_env_vars: string[];
    runner_registered: boolean;
    operation_kinds: string[];
    capabilities: StudioCapabilities;
    reference_limit: number;
    allowed_aspect_ratios: string[];
    allowed_image_sizes: string[];
    request_preview?: {
      method?: string;
      endpoint?: string;
      fallback_endpoint?: string;
      auth?: string;
      content_type?: string;
      body_preview?: Record<string, unknown>;
    };
    request_preview_error?: string;
    request_previews?: Record<
      string,
      {
        method?: string;
        endpoint?: string;
        fallback_endpoint?: string;
        auth?: string;
        content_type?: string;
        body_preview?: Record<string, unknown>;
      }
    >;
    request_preview_errors?: Record<string, string>;
  }>;
  notes: string[];
}

export interface DemoDoctorStatus {
  status: "ready" | "ready_with_warnings" | "needs_attention";
  readyForDemo: boolean;
  headline: string;
  summary: {
    activeSessionCount: number;
    outputAssetCount: number;
    imageOutputAssetCount?: number;
    approvedAssetCount: number;
    referenceAssetCount: number;
    videoAssetCount?: number;
    demoCurated?: boolean;
    workflowSmokeOk?: boolean;
    workflowSmokeAt?: string;
    workflowSmokeMediaFileCount?: number;
    workflowSmokeChannelExportFileCount?: number;
    secretIssueCount?: number;
    graphBrandingReady?: boolean;
    demoEvidenceReady?: boolean;
    callBriefReady?: boolean;
    providerReadinessReceiptReady?: boolean;
    brandContextReceiptReady?: boolean;
    activationChecklistReady?: boolean;
    readinessPackReady?: boolean;
    readinessPackBytes?: number;
    readinessPackSha256?: string;
    providerAdapterCount?: number;
    missingProviderAdapterCount?: number;
    readyProviderModels: number;
    waitingProviderModels: number;
    diffusionReady?: boolean;
    checkpointCount?: number;
    maskedEditReady?: boolean;
    editProofReady?: boolean;
  };
  checks: Array<{
    key: string;
    label: string;
    status: "ready" | "warning" | "fail";
    detail: string;
    action?: string;
  }>;
  notes: string[];
}

export interface DemoEvidenceResult {
  evidence: {
    title: string;
    generated_at: string;
    headline: string;
    status: string;
    ready_for_demo: boolean;
    summary: Record<string, unknown>;
    workflow_smoke: Record<string, unknown>;
    demo_urls: Record<string, string>;
  };
  markdown_path: string;
  json_path: string;
  latest_markdown_path?: string;
  latest_json_path?: string;
  markdown_file: string;
  json_file: string;
  latest_markdown_file?: string;
  latest_json_file?: string;
  markdown_url: string;
  json_url: string;
  latest_markdown_url?: string;
  latest_json_url?: string;
}

export interface DemoCallDecision {
  status: "GO" | "GO WITH WARNINGS" | "NO-GO" | string;
  headline: string;
  can_present: boolean;
  warning_keys: string[];
  failure_keys: string[];
}

export interface DemoCallBriefResult {
  brief: {
    title: string;
    headline: string;
    ready_for_demo: boolean;
    call_decision?: DemoCallDecision;
    [key: string]: unknown;
  };
  markdown_path: string;
  json_path: string;
  latest_markdown_path?: string;
  latest_json_path?: string;
  markdown_file: string;
  json_file: string;
  latest_markdown_file?: string;
  latest_json_file?: string;
  markdown_url: string;
  json_url: string;
  latest_markdown_url?: string;
  latest_json_url?: string;
}

export interface DemoReadinessPackResult {
  file_path: string;
  file_name: string;
  download_url: string;
  latest_file_path?: string;
  latest_file_name?: string;
  latest_download_url?: string;
  checksum_path?: string;
  checksum_sha256?: string;
  latest_checksum_path?: string;
  latest_checksum_sha256?: string;
  latest_file_size_bytes?: number;
  latest_implementation_manifest_path?: string;
  latest_implementation_manifest_url?: string;
  manifest: {
    product: string;
    purpose: string;
    created_at: string;
    base_url: string;
    includes: string[];
    missing_files: string[];
    screenshot_count: number;
    screenshot_capture?: {
      status: "captured" | "partial" | "skipped" | "failed";
      generated_at?: string;
      tool?: string;
      base_url?: string;
      captured?: Array<{ key: string; label: string; file: string; url?: string; viewport?: string }>;
      issues?: Array<{ key: string; label: string; file: string; reason: string }>;
      issue_count?: number;
      notes?: string[];
    };
    notes: string[];
    screenshots?: string[];
    browser_qa?: {
      status: string;
      checks: Array<{
        key: string;
        label?: string;
        status?: string;
        browser_status?: string;
        detail?: string;
      }>;
    };
    cliff_pack?: {
      status: "included" | "missing";
      export_id?: string;
      session_id?: string;
      session_name?: string;
      archive_path?: string | null;
      approved_asset_count?: number;
      approved_image_count?: number;
      approved_video_count?: number;
      reference_count?: number;
      detail?: string;
    };
  };
  evidence: DemoEvidenceResult;
  call_brief?: DemoCallBriefResult;
  provider_readiness?: ProviderReadinessReceiptResult;
  activation_checklist?: ActivationChecklistReceiptResult;
  brand_context?: BrandContextReceiptResult;
}

export interface Project {
  id: string;
  name: string;
  client?: string;
  status: string;
  sync_status?: string;
  remote_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Brief {
  id: string;
  project_id: string;
  title: string;
  product_name?: string;
  task_type: string;
  channel?: string;
  tone?: string;
  prompt?: string;
  negative_prompt?: string;
  reference_image_path?: string;
  status: string;
  sync_status?: string;
  remote_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Run {
  id: string;
  brief_id: string;
  workflow_key: string;
  provider: string;
  prompt_id?: string;
  status: string;
  notes?: string;
  sync_status?: string;
  remote_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface StudioSession {
  id: string;
  project_id?: string | null;
  name: string;
  mode: string;
  status: string;
  summary?: string | null;
  sync_status?: string;
  remote_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface StudioTurn {
  id: string;
  session_id: string;
  kind: "generate" | "edit" | "masked_edit" | "video";
  provider?: string;
  model: string;
  prompt: string;
  settings_json?: string;
  source_asset_id?: string | null;
  reference_asset_ids_json?: string;
  output_asset_ids_json?: string;
  frank_body_mode: boolean;
  preset_key?: string | null;
  status: "queued" | "running" | "complete" | "blocked" | "failed" | "review";
  error_json?: string | null;
  sync_status?: string;
  remote_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Asset {
  id: string;
  run_id?: string;
  brief_id?: string;
  session_id?: string;
  turn_id?: string;
  kind: string;
  title: string;
  media_type?: "image" | "video";
  provider?: string;
  model?: string;
  prompt?: string;
  settings_json?: string;
  source_asset_id?: string;
  reference_asset_ids_json?: string;
  file_path?: string;
  preview_url?: string;
  width?: number;
  height?: number;
  favorite: boolean;
  approval_status: ApprovalStatus;
  notes?: string;
  sync_status?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ExportRecord {
  id: string;
  asset_id: string;
  preset: string;
  file_path: string;
  download_url?: string;
  metadata_json: string;
  sync_status?: string;
  remote_id?: string;
  created_at: string;
}

export interface BriefFormState {
  title: string;
  productName: string;
  taskType: string;
  channel: string;
  tone: string;
  prompt: string;
  negativePrompt: string;
}

export interface UploadedImage {
  name: string;
  subfolder?: string;
  type?: string;
}

export interface StudioSettings {
  aspect_ratio: string;
  image_size: string;
  count: number;
}

export interface TurnRequest {
  session_id?: string;
  kind: "generate" | "edit" | "masked_edit";
  model: string;
  prompt: string;
  frank_body_mode: boolean;
  preset_key?: string;
  settings: StudioSettings;
  reference_asset_ids: string[];
  edit_source_asset_id?: string;
  mask_asset_id?: string;
}

export interface VideoRequest {
  session_id?: string;
  model?: string;
  prompt: string;
  settings: StudioSettings;
  source_asset_id?: string;
  reference_asset_ids: string[];
}
