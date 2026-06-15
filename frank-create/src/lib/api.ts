import type {
  ActivationChecklist,
  Asset,
  BrandContextReceiptResult,
  BrandKit,
  Brief,
  DemoCallBriefResult,
  DemoEvidenceResult,
  DemoDoctorStatus,
  DemoReadinessPackResult,
  ExportRecord,
  FrankConfig,
  LocalEngineStatus,
  ProviderAdapterAudit,
  ProviderEnvStatus,
  ProviderReadiness,
  ProviderReadinessReceiptResult,
  ProviderPreflight,
  PromptRemixVariant,
  Project,
  Run,
  StudioSession,
  StudioTurn,
  TurnRequest,
  UploadedImage,
  VideoRequest,
  WorkflowBlueprintsResponse
} from "./types";

const frankBase = "/api/frank";

export async function fetchHealth() {
  return fetchJson<{ ok: boolean; product: string; store: string }>("/health");
}

export async function fetchConfig() {
  return fetchJson<FrankConfig>("/config");
}

export async function fetchModels() {
  return fetchJson<Pick<FrankConfig, "models" | "backlogModels" | "promptPresets">>("/models");
}

export async function prepareLocalEngineFolders() {
  return fetchJson<{ created_dirs: string[]; readme_path: string; localEngine: LocalEngineStatus }>("/local-engine/setup", {
    method: "POST"
  });
}

export async function fetchWorkflowBlueprints() {
  return fetchJson<WorkflowBlueprintsResponse>("/local-engine/workflow-blueprints");
}

export async function fetchProviderStatus() {
  return fetchJson<ProviderReadiness>("/provider-status");
}

export async function fetchProviderAudit() {
  return fetchJson<ProviderAdapterAudit>("/provider-audit");
}

export async function fetchActivationChecklist() {
  return fetchJson<ActivationChecklist>("/activation-checklist");
}

export async function preflightProvider(payload: Record<string, unknown>) {
  return fetchJson<ProviderPreflight>("/provider-preflight", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function fetchDemoDoctor() {
  return fetchJson<DemoDoctorStatus>("/demo-doctor");
}

export async function resetDemo(payload: { create_assets: boolean }) {
  return fetchJson<{
    project: Project;
    brief: Brief;
    session: StudioSession;
    turn: StudioTurn;
    reference: Asset | null;
    assets: Asset[];
    doctor: DemoDoctorStatus;
  }>("/demo/reset", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createDemoEvidence(payload: { base_url?: string } = {}) {
  return fetchJson<DemoEvidenceResult>("/demo/evidence", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createDemoCallBrief(payload: { base_url?: string } = {}) {
  return fetchJson<DemoCallBriefResult>("/demo/call-brief", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createDemoReadinessPack(payload: { base_url?: string } = {}) {
  return fetchJson<DemoReadinessPackResult>("/demo/readiness-pack", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createProviderReadinessReceipt() {
  return fetchJson<ProviderReadinessReceiptResult>("/demo/provider-readiness", { method: "POST" });
}

export async function remixPrompt(payload: { prompt: string; preset_key: string; frank_body_mode: boolean }) {
  return fetchJson<{ variants: PromptRemixVariant[] }>("/prompt-remix", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function fetchBrandKit() {
  return fetchJson<{ brandKit: BrandKit; filePath: string }>("/brand-kit");
}

export async function updateBrandKit(payload: BrandKit) {
  return fetchJson<{ brandKit: BrandKit; filePath: string }>("/brand-kit", {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function createBrandContextReceipt(payload: { session_id?: string } = {}) {
  return fetchJson<BrandContextReceiptResult>("/demo/brand-context", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function fetchProviderEnvStatus() {
  return fetchJson<ProviderEnvStatus>("/provider-env");
}

export async function createProviderEnvTemplate() {
  return fetchJson<ProviderEnvStatus>("/provider-env/template", { method: "POST" });
}

export async function reloadProviderEnv() {
  return fetchJson<ProviderEnvStatus>("/provider-env/reload", { method: "POST" });
}

export async function saveProviderEnvKeys(keys: Record<string, string>) {
  return fetchJson<ProviderEnvStatus>("/provider-env/save", {
    method: "POST",
    body: JSON.stringify({ keys })
  });
}

export async function listProjects() {
  return fetchJson<{ projects: Project[] }>("/projects");
}

export async function createProject(payload: Partial<Project> & { name: string }) {
  return fetchJson<{ project: Project }>("/projects", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateProject(projectId: string, payload: Partial<Project>) {
  return fetchJson<{ project: Project }>(`/projects/${projectId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function listBriefs(projectId?: string) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return fetchJson<{ briefs: Brief[] }>(`/briefs${query}`);
}

export async function createBrief(payload: Record<string, unknown>) {
  return fetchJson<{ brief: Brief }>("/briefs", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateBrief(briefId: string, payload: Record<string, unknown>) {
  return fetchJson<{ brief: Brief }>(`/briefs/${briefId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function createRun(payload: Record<string, unknown>) {
  return fetchJson<{ run: Run }>("/runs", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateRun(runId: string, payload: Partial<Run>) {
  return fetchJson<{ run: Run }>(`/runs/${runId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function listRuns(briefId?: string) {
  const query = briefId ? `?brief_id=${encodeURIComponent(briefId)}` : "";
  return fetchJson<{ runs: Run[] }>(`/runs${query}`);
}

export async function listSessions() {
  return fetchJson<{ sessions: StudioSession[] }>("/sessions");
}

export async function createSession(payload: Partial<StudioSession> & { name: string }) {
  return fetchJson<{ session: StudioSession }>("/sessions", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateSession(sessionId: string, payload: Partial<StudioSession>) {
  return fetchJson<{ session: StudioSession }>(`/sessions/${sessionId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function createSessionHandoff(sessionId: string) {
  return fetchJson<{ handoff: ExportRecord; download_url: string; metadata: Record<string, unknown> }>(
    `/sessions/${encodeURIComponent(sessionId)}/handoff`,
    {
      method: "POST",
      body: JSON.stringify({ summary: "Approved Frank Create handoff for review." })
    }
  );
}

export async function listTurns(sessionId?: string) {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return fetchJson<{ turns: StudioTurn[] }>(`/turns${query}`);
}

export async function createTurn(payload: Partial<StudioTurn> & { session_id: string; model: string; prompt: string }) {
  return fetchJson<{ turn: StudioTurn }>("/turns", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateTurn(turnId: string, payload: Partial<StudioTurn>) {
  return fetchJson<{ turn: StudioTurn }>(`/turns/${turnId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function createInferenceTurn(payload: TurnRequest) {
  return fetchJson<{
    turn: StudioTurn;
    status: "queued" | "running" | "blocked" | "failed" | "complete";
    assets?: Asset[];
    providerPayload?: Record<string, unknown>;
    localEngine?: "comfy" | "fallback" | "frank_renderer";
    fallbackReason?: string;
    error?: { code: string; env_vars?: string[]; message?: string };
  }>("/inference/turn", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createVideoStoryboard(payload: VideoRequest) {
  return fetchJson<{
    turn: StudioTurn;
    status: "complete" | "failed" | "blocked";
    assets?: Asset[];
    providerPayload?: Record<string, unknown>;
    localEngine?: "storyboard" | string;
    error?: { code: string; env_vars?: string[]; message?: string };
  }>("/videos", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createAsset(payload: Record<string, unknown>) {
  return fetchJson<{ asset: Asset }>("/assets", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createReference(payload: Record<string, unknown>) {
  return fetchJson<{ asset: Asset }>("/references", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function listAssets(filters: { sessionId?: string; turnId?: string; approvalStatus?: string } = {}) {
  const params = new URLSearchParams();
  if (filters.sessionId) {
    params.set("session_id", filters.sessionId);
  }
  if (filters.turnId) {
    params.set("turn_id", filters.turnId);
  }
  if (filters.approvalStatus) {
    params.set("approval_status", filters.approvalStatus);
  }
  const query = params.size ? `?${params.toString()}` : "";
  return fetchJson<{ assets: Asset[] }>(`/assets${query}`);
}

export async function updateAsset(assetId: string, payload: Partial<Asset>) {
  return fetchJson<{ asset: Asset }>(`/assets/${assetId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function deleteAsset(assetId: string) {
  return fetchJson<{ asset: Asset }>(`/assets/${assetId}`, {
    method: "DELETE"
  });
}

export async function createExport(payload: Record<string, unknown>) {
  return fetchJson<{ export: ExportRecord; download_url?: string; metadata?: Record<string, unknown> }>("/exports", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createAssetChannelSet(
  assetId: string,
  payload: { presets: string[]; metadata?: Record<string, unknown> }
) {
  return fetchJson<{ export: ExportRecord; download_url: string; metadata: Record<string, unknown> }>(
    `/assets/${encodeURIComponent(assetId)}/export-set`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export async function listExports(assetId?: string) {
  const query = assetId ? `?asset_id=${encodeURIComponent(assetId)}` : "";
  return fetchJson<{ exports: ExportRecord[] }>(`/exports${query}`);
}

export function exportDownloadUrl(exportId: string) {
  return `${frankBase}/exports/${encodeURIComponent(exportId)}/download`;
}

export function sessionReviewBoardUrl(sessionId: string) {
  return `${frankBase}/sessions/${encodeURIComponent(sessionId)}/review-board`;
}

export function sessionSyncManifestUrl(sessionId: string) {
  return `${frankBase}/sessions/${encodeURIComponent(sessionId)}/sync-manifest`;
}

export function assetDownloadUrl(assetId: string) {
  return `${frankBase}/assets/${encodeURIComponent(assetId)}/download`;
}

export function assetWorkflowReceiptUrl(assetId: string) {
  return `${frankBase}/assets/${encodeURIComponent(assetId)}/workflow`;
}

export function comfyCanvasAssetUrl(assetId: string) {
  return `/comfy/?frankAssetId=${encodeURIComponent(assetId)}`;
}

export async function uploadImage(file: File) {
  const body = new FormData();
  body.append("image", file);
  body.append("type", "input");
  body.append("subfolder", "frank_create");
  body.append("overwrite", "true");

  const response = await fetch("/api/upload/image", {
    method: "POST",
    body
  });

  if (!response.ok) {
    throw new Error(`Upload failed (${response.status})`);
  }

  return (await response.json()) as UploadedImage;
}

export async function queuePrompt(prompt: Record<string, unknown>, clientId = makeClientId()) {
  const response = await fetch("/api/prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: clientId, prompt })
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Prompt queue failed (${response.status})`);
  }

  return (await response.json()) as { prompt_id: string; number: number; node_errors?: Record<string, unknown> };
}

export async function fetchPromptHistory(promptId: string) {
  const response = await fetch(`/api/history/${encodeURIComponent(promptId)}`);

  if (!response.ok) {
    throw new Error(`Prompt history unavailable (${response.status})`);
  }

  return (await response.json()) as unknown;
}

async function fetchJson<T>(path: string, init: RequestInit = {}) {
  const response = await fetch(`${frankBase}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init.headers
    }
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(apiErrorMessage(text, response.status));
  }

  return (await response.json()) as T;
}

function apiErrorMessage(text: string, status: number) {
  if (!text) {
    return `Frank Create API failed (${status})`;
  }

  try {
    const parsed = JSON.parse(text) as { error?: { message?: string } };
    return parsed.error?.message || text;
  } catch {
    return text;
  }
}

function makeClientId() {
  if ("crypto" in window && "randomUUID" in window.crypto) {
    return `frank-create-${window.crypto.randomUUID()}`;
  }
  return `frank-create-${Date.now()}`;
}
