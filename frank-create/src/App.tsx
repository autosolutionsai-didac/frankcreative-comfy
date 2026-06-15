import {
  ArrowLeft,
  Box,
  CheckCircle2,
  Clipboard,
  Cpu,
  Download,
  ExternalLink,
  Film,
  GitBranch,
  Heart,
  ImageIcon,
  Layers3,
  MessageSquareText,
  Paperclip,
  Paintbrush,
  Plus,
  RefreshCw,
  Sparkles,
  Upload,
  Wand2,
  XCircle
} from "lucide-react";
import {
  CSSProperties,
  ChangeEvent,
  FormEvent,
  PointerEvent as ReactPointerEvent,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";

import {
  fetchActivationChecklist,
  assetDownloadUrl,
  assetWorkflowReceiptUrl,
  comfyCanvasAssetUrl,
  createAsset,
  createAssetChannelSet,
  createBrief,
  createBrandContextReceipt,
  createDemoCallBrief,
  createDemoEvidence,
  createDemoReadinessPack,
  createProviderEnvTemplate,
  createExport,
  createInferenceTurn,
  createProject,
  createProviderReadinessReceipt,
  createReference,
  createSession,
  createSessionHandoff,
  createVideoStoryboard,
  deleteAsset,
  exportDownloadUrl,
  fetchBrandKit,
  fetchConfig,
  fetchDemoDoctor,
  fetchHealth,
  fetchProviderAudit,
  fetchProviderEnvStatus,
  fetchProviderStatus,
  fetchWorkflowBlueprints,
  listBriefs,
  listExports,
  listAssets,
  listProjects,
  listSessions,
  listTurns,
  prepareLocalEngineFolders,
  preflightProvider,
  reloadProviderEnv,
  remixPrompt,
  resetDemo,
  saveProviderEnvKeys,
  sessionReviewBoardUrl,
  sessionSyncManifestUrl,
  updateAsset,
  updateBrief,
  updateBrandKit,
  updateSession,
  uploadImage
} from "./lib/api";
import { fallbackBrandKit, fallbackConfig } from "./lib/presets";
import { assetStatusCopy, createBriefPayload, makeStoredImagePath, makeViewUrl } from "./lib/frankWorkflow";
import {
  buildTurnRequest,
  defaultStudioSettings,
  inferenceStatusCopy,
  makeLocalId,
  normalizeStudioSettingsForModel,
  parseJsonList,
  selectModelOptions
} from "./lib/studio";
import type {
  ActivationChecklist,
  Asset,
  BrandKit,
  Brief,
  BriefFormState,
  DemoDoctorStatus,
  DemoCallDecision,
  DemoReadinessPackResult,
  ExportRecord,
  ExportPreset,
  FrankConfig,
  FrankTask,
  ProviderAdapterAudit,
  ProviderEnvStatus,
  ProviderPreflight,
  ProviderReadiness,
  PromptPreset,
  PromptRemixVariant,
  Project,
  StudioModel,
  StudioSession,
  StudioSettings,
  StudioTurn,
  WorkflowBlueprint,
  WorkflowBlueprintsResponse
} from "./lib/types";

type WalkthroughTarget =
  | "app-header"
  | "composer"
  | "output-thread"
  | "model-settings"
  | "model-settings-drawer"
  | "model-output-controls"
  | "frank-mode-toggle"
  | "review-panel"
  | "review-actions"
  | "review-metadata"
  | "variant-controls"
  | "edit-controls"
  | "export-controls"
  | "handoff-pack"
  | "advanced-tools";

interface WalkthroughStep {
  title: string;
  detail: string;
  points?: string[];
  target: WalkthroughTarget;
  openSettings?: boolean;
  openAdvanced?: boolean;
  selectOutput?: boolean;
}

interface WalkthroughAnchor {
  highlightStyle: CSSProperties;
  popoverStyle: CSSProperties;
  placement: "above" | "below";
}

const WALKTHROUGH_STEPS: WalkthroughStep[] = [
  {
    title: "Sessions and demo controls",
    detail: "This header is the control strip for the call: switch sessions, start fresh, launch this walkthrough, or open Advanced when someone technical asks.",
    points: ["Session keeps each creative thread separate.", "New starts another brief without touching the current one.", "Advanced stays hidden during the normal creative flow."],
    target: "app-header"
  },
  {
    title: "Brief and references",
    detail: "This is the working brief. Add product references, write the ask in plain English, choose the job type, and press Generate when the direction is clear.",
    points: ["References are selectable, so a round can use all refs, some refs, or prompt-only.", "Brief remix gives alternate prompt directions without leaving the Studio.", "Generate uses the selected model and settings from the right panel."],
    target: "composer"
  },
  {
    title: "Workflow chips and prompt",
    detail: "The chips are workflow shortcuts, not separate apps. Product Shot Lab, Video Lab, and Approved only change the current task/filter while keeping one thread.",
    points: ["Product Shot Lab loads product-focused presets.", "Video Lab briefs a storyboard-style round.", "Approved only filters the thread to keepers."],
    target: "composer"
  },
  {
    title: "Generated rounds",
    detail: "Every generate or edit run lands here as a round. The card keeps the prompt, model, status, Frank Body Mode, and reference count attached to the output.",
    points: ["Click an image to open the review desk on the right.", "Rounds stay in order, so the creative conversation remains explainable.", "Approved only can filter this thread when the team wants the shortlist."],
    target: "output-thread"
  },
  {
    title: "Model summary",
    detail: "The right panel starts with the active model, aspect ratio, image size, and number of picks. This is the quick confidence check before spending an API call.",
    points: ["Nano Banana Pro is the recommended live proof.", "Local Comfy stays as the clearly labelled fallback.", "Change model opens the full drawer."],
    target: "model-settings"
  },
  {
    title: "Model drawer",
    detail: "This drawer is where you choose between Gemini, Replicate, OpenAI, or local fallback. It also shows cost labels and readiness badges.",
    points: ["Missing keys stay out of the first screen but are still visible here.", "Model choice changes what sizes, refs, and edit modes are available.", "Use this before a live client-proof generation."],
    target: "model-settings-drawer",
    openSettings: true
  },
  {
    title: "Output controls",
    detail: "Aspect, size, and count control the next round. The app limits choices to what the selected model actually supports.",
    points: ["Aspect is the canvas shape.", "Size is the provider output target.", "Count is how many variants come back in the round."],
    target: "model-output-controls",
    openSettings: true
  },
  {
    title: "Frank Body Mode",
    detail: "This toggle is the brand brain. Off means the app sends only the user prompt. On adds Frank Body style guidance, guardrails, and preset structure.",
    points: ["Leave it off for neutral model tests.", "Turn it on for Frank Body campaign/product work.", "The mode is stored with the run metadata."],
    target: "frank-mode-toggle",
    openSettings: true
  },
  {
    title: "Review desk",
    detail: "After a result is selected, this panel becomes the review desk. It shows the chosen image and all actions for deciding what happens next.",
    points: ["Open selected asset for a larger view.", "Review controls stay beside the image.", "Nothing needs the raw Comfy graph for normal review."],
    target: "review-panel",
    selectOutput: true
  },
  {
    title: "Approve or reject",
    detail: "These are the fast creative-director decisions: favorite, approve, or reject. Approved picks feed the handoff/export flow.",
    points: ["Approve marks the keeper.", "Favorite is a softer shortlist.", "Reject keeps the record without presenting it as a candidate."],
    target: "review-actions",
    selectOutput: true
  },
  {
    title: "Run metadata",
    detail: "This section explains where the image came from. It keeps model, settings, dimensions, source image, workflow, references, and prompt together.",
    points: ["Useful for client notes and repeats.", "Workflow JSON can be downloaded later.", "This is the audit trail for FrankHub or a DAM sync."],
    target: "review-metadata",
    selectOutput: true
  },
  {
    title: "Make another round",
    detail: "These buttons turn a selected result into the next brief. More like this, clean it up, and campaign remix are shortcuts for fast iteration.",
    points: ["They set up edit mode from the selected asset.", "The prompt updates automatically.", "You can still change the model before generating."],
    target: "variant-controls",
    selectOutput: true
  },
  {
    title: "Edit, mask, and reuse",
    detail: "These controls are the production tools: copy the brief, download workflow JSON, open Comfy, edit with the selected model, paint a mask, or reuse a pick as a reference.",
    points: ["Edit with selected model starts image-to-image.", "Paint edit mask appears when the model supports masked edit.", "Use as reference turns a good pick into guidance for the next round."],
    target: "edit-controls",
    selectOutput: true
  },
  {
    title: "Exports",
    detail: "Export controls appear once a pick is selected. Use the channel set for a complete package, or export one format at a time.",
    points: ["Channel set creates the ready-to-share pack.", "Individual presets cover PDP, social, email, transparent PNG, and master files.", "Download original keeps the untouched provider result."],
    target: "export-controls",
    selectOutput: true
  },
  {
    title: "Cliff Pack handoff",
    detail: "This package area collects approved picks, references, prompts, notes, metadata, and channel exports into one handoff route.",
    points: ["Export Cliff Pack is the call-day deliverable.", "Review board gives a visual summary.", "Sync manifest is the future FrankHub/DAM bridge."],
    target: "handoff-pack",
    selectOutput: true
  },
  {
    title: "Advanced tools",
    detail: "Advanced is for setup, diagnostics, raw Comfy access, provider keys, Demo Doctor, readiness packs, and proof receipts. It is intentionally outside the normal creative path.",
    points: ["Provider keys are only Gemini, Replicate, and OpenAI.", "Demo Doctor checks call readiness.", "Workflow Map and raw Comfy are escape hatches for power users."],
    target: "advanced-tools",
    openAdvanced: true
  }
];

export default function App() {
  const [config, setConfig] = useState<FrankConfig>(fallbackConfig);
  const [surface, setSurface] = useState<"studio" | "graph">(() => initialSurface());
  const [connection, setConnection] = useState<"checking" | "online" | "offline">("checking");
  const [projects, setProjects] = useState<Project[]>([]);
  const [briefs, setBriefs] = useState<Brief[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [activeBrief, setActiveBrief] = useState<Brief | null>(null);
  const [projectName, setProjectName] = useState("Frank Body Campaign");
  const [briefDraft, setBriefDraft] = useState<BriefFormState>(() => makeBriefDraft());
  const [sessions, setSessions] = useState<StudioSession[]>([]);
  const [activeSession, setActiveSession] = useState<StudioSession | null>(null);
  const [turns, setTurns] = useState<StudioTurn[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [prompt, setPrompt] = useState("");
  const [promptRemixes, setPromptRemixes] = useState<PromptRemixVariant[]>([]);
  const [selectedModelId, setSelectedModelId] = useState(() => preferredStudioModel(fallbackConfig.models).id);
  const [selectedPresetKey, setSelectedPresetKey] = useState("product-shot-lab");
  const [frankBodyMode, setFrankBodyMode] = useState(false);
  const [studioMode, setStudioMode] = useState<"image-studio" | "product-shot-lab" | "video-lab" | "approved-hot">(() =>
    initialStudioMode()
  );
  const [advancedOpen, setAdvancedOpen] = useState(() => shouldAutoOpenProviderAudit());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [walkthroughOpen, setWalkthroughOpen] = useState(false);
  const [walkthroughStep, setWalkthroughStep] = useState(0);
  const [walkthroughAnchor, setWalkthroughAnchor] = useState<WalkthroughAnchor | null>(null);
  const [reviewFilter, setReviewFilter] = useState<"all" | "approved">("all");
  const [settings, setSettings] = useState<StudioSettings>(defaultStudioSettings(fallbackConfig.models[0]));
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [lightboxAsset, setLightboxAsset] = useState<Asset | null>(null);
  const [compareBaseAsset, setCompareBaseAsset] = useState<Asset | null>(null);
  const [compareTargetAsset, setCompareTargetAsset] = useState<Asset | null>(null);
  const [editSourceAsset, setEditSourceAsset] = useState<Asset | null>(null);
  const [maskAsset, setMaskAsset] = useState<Asset | null>(null);
  const [maskPainterAsset, setMaskPainterAsset] = useState<Asset | null>(null);
  const [selectedReferenceIds, setSelectedReferenceIds] = useState<string[]>([]);
  const [assetNotesDraft, setAssetNotesDraft] = useState("");
  const [providerReadiness, setProviderReadiness] = useState<ProviderReadiness | null>(null);
  const [activationChecklist, setActivationChecklist] = useState<ActivationChecklist | null>(null);
  const [providerEnvStatus, setProviderEnvStatus] = useState<ProviderEnvStatus | null>(null);
  const [providerKeyDraft, setProviderKeyDraft] = useState<Record<string, string>>({});
  const [providerPreflight, setProviderPreflight] = useState<ProviderPreflight | null>(null);
  const [providerAudit, setProviderAudit] = useState<ProviderAdapterAudit | null>(null);
  const [brandKit, setBrandKit] = useState<BrandKit>(fallbackBrandKit);
  const [brandKitDraft, setBrandKitDraft] = useState<BrandKit>(fallbackBrandKit);
  const [demoDoctor, setDemoDoctor] = useState<DemoDoctorStatus | null>(null);
  const [workflowBlueprints, setWorkflowBlueprints] = useState<WorkflowBlueprintsResponse | null>(null);
  const [checkingProviders, setCheckingProviders] = useState(false);
  const [checkingProviderPreflight, setCheckingProviderPreflight] = useState(false);
  const [checkingProviderAudit, setCheckingProviderAudit] = useState(false);
  const [savingProviderReceipt, setSavingProviderReceipt] = useState(false);
  const [checkingDemoDoctor, setCheckingDemoDoctor] = useState(false);
  const [resettingDemo, setResettingDemo] = useState(false);
  const [savingDemoEvidence, setSavingDemoEvidence] = useState(false);
  const [savingCallBrief, setSavingCallBrief] = useState(false);
  const [buildingReadinessPack, setBuildingReadinessPack] = useState(false);
  const [demoEvidencePath, setDemoEvidencePath] = useState("");
  const [demoEvidenceUrl, setDemoEvidenceUrl] = useState("");
  const [callBriefPath, setCallBriefPath] = useState("");
  const [callBriefUrl, setCallBriefUrl] = useState("");
  const [callDecision, setCallDecision] = useState<DemoCallDecision | null>(null);
  const [providerReceiptPath, setProviderReceiptPath] = useState("");
  const [providerReceiptUrl, setProviderReceiptUrl] = useState("");
  const [brandContextPath, setBrandContextPath] = useState("");
  const [brandContextUrl, setBrandContextUrl] = useState("");
  const [activationChecklistPath, setActivationChecklistPath] = useState("");
  const [activationChecklistUrl, setActivationChecklistUrl] = useState("");
  const [readinessPackPath, setReadinessPackPath] = useState("");
  const [readinessPackUrl, setReadinessPackUrl] = useState("");
  const [readinessPackSha, setReadinessPackSha] = useState("");
  const [implementationManifestPath, setImplementationManifestPath] = useState("");
  const [implementationManifestUrl, setImplementationManifestUrl] = useState("");
  const [readinessPackManifest, setReadinessPackManifest] = useState<DemoReadinessPackResult["manifest"] | null>(null);
  const [providerEnvBusy, setProviderEnvBusy] = useState(false);
  const [localEngineBusy, setLocalEngineBusy] = useState(false);
  const [maskPainterBusy, setMaskPainterBusy] = useState(false);
  const [brandKitBusy, setBrandKitBusy] = useState(false);
  const [brandContextBusy, setBrandContextBusy] = useState(false);
  const [briefBusy, setBriefBusy] = useState(false);
  const [handoffBusy, setHandoffBusy] = useState(false);
  const [handoffProofText, setHandoffProofText] = useState("");
  const [remixBusy, setRemixBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [statusText, setStatusText] = useState("Waiting for the brief...");

  useEffect(() => {
    function handleDrawerKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") {
        return;
      }

      setAdvancedOpen(false);
      setSettingsOpen(false);
    }

    window.addEventListener("keydown", handleDrawerKeyDown);
    return () => window.removeEventListener("keydown", handleDrawerKeyDown);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        await fetchHealth();
        const freshConfig = mergeConfig(await fetchConfig());
        const sessionResult = await listSessions();
        let nextSession = sessionResult.sessions[0];
        let nextSessions = sessionResult.sessions;

        if (!nextSession) {
          const created = await createSession({ name: "Launch Image Studio", mode: "image" });
          nextSession = created.session;
          nextSessions = [created.session];
        }

        const [
          turnResult,
          assetResult,
          exportResult,
          providerEnvResult,
          activationChecklistResult,
          brandKitResult,
          projectResult,
          workflowBlueprintResult
        ] = await Promise.all([
          listTurns(nextSession.id),
          listAssets({ sessionId: nextSession.id }),
          listExports().catch(() => ({ exports: [] })),
          fetchProviderEnvStatus().catch(() => null),
          fetchActivationChecklist().catch(() => null),
          fetchBrandKit().catch(() => null),
          listProjects().catch(() => ({ projects: [] })),
          fetchWorkflowBlueprints().catch(() => null)
        ]);
        const projectForSession =
          projectResult.projects.find((project) => project.id === nextSession.project_id) ?? projectResult.projects[0] ?? null;
        const briefResult = projectForSession ? await listBriefs(projectForSession.id).catch(() => ({ briefs: [] })) : { briefs: [] };

        if (cancelled) {
          return;
        }

        setConfig(freshConfig);
        setSelectedModelId(preferredStudioModel(freshConfig.models).id);
        setProjects(projectResult.projects);
        setActiveProject(projectForSession);
        setProjectName(projectForSession?.name ?? "Frank Body Campaign");
        const initialBrief = briefResult.briefs[0] ?? null;
        setBriefs(briefResult.briefs);
        setActiveBrief(initialBrief);
        if (initialBrief) {
          setBriefDraft(briefToDraft(initialBrief));
          hydratePromptFromBrief(initialBrief);
        }
        setSessions(nextSessions);
        setActiveSession(nextSession);
        setTurns(turnResult.turns);
        setAssets(assetResult.assets);
        setSelectedReferenceIds(referenceIdsFromAssets(assetResult.assets));
        setExports(filterExportsForAssets(exportResult.exports, assetResult.assets));
        setProviderEnvStatus(providerEnvResult);
        setActivationChecklist(activationChecklistResult);
        if (brandKitResult?.brandKit) {
          setBrandKit(brandKitResult.brandKit);
          setBrandKitDraft(brandKitResult.brandKit);
        }
        setWorkflowBlueprints(workflowBlueprintResult);
        setSelectedAsset(firstReviewableAsset(assetResult.assets));
        setConnection("online");
        setStatusText("Comfy is in the room.");
      } catch {
        if (cancelled) {
          return;
        }
        const localSession = makeLocalSession();
        setSessions([localSession]);
      setActiveSession(localSession);
      setConnection("offline");
      setExports([]);
      setSelectedReferenceIds([]);
      setStatusText("Start ComfyUI to save sessions and run providers.");
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (connection !== "online" || providerAudit || checkingProviderAudit || !shouldAutoOpenProviderAudit()) {
      return;
    }
    void checkProviderAdapterAudit();
  }, [connection, providerAudit, checkingProviderAudit]);

  useEffect(() => {
    function handlePopState() {
      setSurface(initialSurface());
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const selectedModel = useMemo(
    () => config.models.find((model) => model.id === selectedModelId) ?? config.models[0],
    [config.models, selectedModelId]
  );
  const providerAuditMode = shouldAutoOpenProviderAudit();
  const modelOptions = useMemo(() => selectModelOptions(config.models, selectedModelId), [config.models, selectedModelId]);
  const providerSetupState = useMemo(() => providerSetup(config.models), [config.models]);
  const providerUnlockRows = useMemo(() => providerUnlockPlan(config.models), [config.models]);
  const providerKeyEnvVars = useMemo(() => {
    const missingFromStatus = providerEnvStatus?.missingEnvVars ?? [];
    if (missingFromStatus.length) {
      return orderProviderEnvVars(missingFromStatus, providerUnlockRows);
    }
    if (providerSetupState.envVars.length) {
      return providerSetupState.envVars;
    }
    return orderProviderEnvVars(providerEnvStatus?.envVars ?? [], providerUnlockRows);
  }, [providerEnvStatus?.envVars, providerEnvStatus?.missingEnvVars, providerSetupState.envVars, providerUnlockRows]);
  const providerKeyDraftHasValues = useMemo(
    () => Object.values(providerKeyDraft).some((value) => value.trim().length > 0),
    [providerKeyDraft]
  );
  const activePreset = useMemo(
    () => config.promptPresets.find((preset) => preset.key === selectedPresetKey) ?? config.promptPresets[0],
    [config.promptPresets, selectedPresetKey]
  );
  const productTaskShortcuts = useMemo(
    () => config.tasks.filter((task) => !["product-shot-lab", "prompt-remix"].includes(task.key)),
    [config.tasks]
  );

  function clearEditSource() {
    setEditSourceAsset(null);
    setMaskAsset(null);
    setMaskPainterAsset(null);
  }

  function startEditFromAsset(asset: Asset) {
    setEditSourceAsset(asset);
    setMaskAsset(null);
    setMaskPainterAsset(null);
  }

  function startMaskPainter(asset: Asset) {
    setEditSourceAsset(asset);
    setMaskAsset(null);
    setMaskPainterAsset(asset);
  }

  useEffect(() => {
    if (!selectedModel) {
      return;
    }

    setSettings((current) => normalizeStudioSettingsForModel(current, selectedModel));
    if (!selectedModel.capabilities.masked_edit) {
      setMaskAsset(null);
    }
    setProviderPreflight(null);
  }, [selectedModel]);

  useEffect(() => {
    setAssetNotesDraft(selectedAsset?.notes ?? "");
  }, [selectedAsset?.id]);

  const referenceAssets = assets.filter((asset) => asset.kind === "reference");
  const selectedReferenceIdSet = useMemo(() => new Set(selectedReferenceIds), [selectedReferenceIds]);
  const selectedReferenceAssets = referenceAssets.filter((asset) => selectedReferenceIdSet.has(asset.id));
  const outputAssets = assets.filter((asset) => !["reference", "mask"].includes(asset.kind));
  const firstOutputAsset = outputAssets[0] ?? null;
  const displayOutputAssets =
    reviewFilter === "approved" || studioMode === "approved-hot"
      ? outputAssets.filter((asset) => asset.approval_status === "approved")
      : outputAssets;
  const approvedCount = outputAssets.filter((asset) => asset.approval_status === "approved").length;
  const approvedMotionCount = outputAssets.filter(
    (asset) => asset.approval_status === "approved" && asset.media_type === "video"
  ).length;
  const favoriteCount = outputAssets.filter((asset) => asset.favorite).length;
  const promptMode = editSourceAsset ? (maskAsset ? "masked_edit" : "edit") : "generate";
  const primaryActionLabel =
    studioMode === "video-lab"
      ? "Generate"
      : promptMode === "masked_edit"
        ? "Edit"
        : promptMode === "edit"
          ? "Edit"
          : "Generate";
  const selectedExportPresets = useMemo(
    () => (selectedAsset ? exportPresetsForAsset(config.exportPresets, selectedAsset) : []),
    [config.exportPresets, selectedAsset]
  );
  const imageExportPresetCount = useMemo(
    () => config.exportPresets.filter((preset) => (preset.media_types ?? ["image"]).includes("image")).length,
    [config.exportPresets]
  );
  const selectedAssetMetadata = useMemo(
    () => (selectedAsset ? selectedAssetReviewMetadata(selectedAsset, assets, config, turns) : null),
    [assets, config, selectedAsset, turns]
  );
  const recentExports = useMemo(() => filterExportsForAssets(exports, assets).slice(0, 6), [exports, assets]);
  const showHandoffPanel = Boolean(selectedAsset) || approvedCount > 0 || recentExports.length > 0;
  const cliffGuideSteps = useMemo(
    () => buildCliffGuideSteps(outputAssets, referenceAssets, approvedCount, approvedMotionCount),
    [approvedCount, approvedMotionCount, outputAssets, referenceAssets]
  );
  const cliffGuideProofs = useMemo(
    () => buildCliffGuideProofs(demoDoctor, readinessPackManifest),
    [demoDoctor, readinessPackManifest]
  );
  const launchReadinessItems = useMemo(
    () => buildLaunchReadinessItems(config, providerSetupState.waitingModels.length, demoDoctor, activationChecklist, readinessPackSha),
    [activationChecklist, config, demoDoctor, providerSetupState.waitingModels.length, readinessPackSha]
  );

  function showImageStudio() {
    setStudioMode("image-studio");
    setReviewFilter("all");
    setStatusText("Image Studio is open.");
  }

  function showProductShotLab() {
    const productPreset = config.promptPresets.find((preset) => preset.key === "product-shot-lab") ?? config.promptPresets[0];
    setStudioMode("product-shot-lab");
    setReviewFilter("all");
    if (productPreset) {
      selectPreset(productPreset);
    }
    setStatusText("Product Shot Lab is ready.");
  }

  function showVideoLab() {
    setStudioMode("video-lab");
    setReviewFilter("all");
    clearEditSource();
    setPrompt((current) =>
      current.trim()
        ? current
        : "Create a short Frank Body motion board: product hero, subtle camera push, tactile texture moment, clean end frame."
    );
    setSettings((current) => ({
      ...current,
      aspect_ratio: supportedOption(selectedModel?.allowed_aspect_ratios, current.aspect_ratio === "9:16" ? "9:16" : "16:9", current.aspect_ratio),
      image_size: supportedOption(selectedModel?.allowed_image_sizes, "720p", supportedOption(selectedModel?.allowed_image_sizes, "1K", current.image_size)),
      count: 1
    }));
    setStatusText("Video Lab is ready for a motion board.");
  }

  function showApprovedHot() {
    const firstApproved = firstReviewableAsset(outputAssets.filter((asset) => asset.approval_status === "approved"));
    setStudioMode("approved-hot");
    setReviewFilter("approved");
    setSelectedAsset(firstApproved);
    setLightboxAsset(null);
    clearCompare();
    setStatusText(firstApproved ? "Approved only. Hot." : "No approved images yet.");
  }

  async function handleNewSession() {
    const nextMode = studioMode === "video-lab" ? "video" : "image";
    const sessionSubject =
      activeBrief?.product_name?.trim() || briefDraft.productName.trim() || activeProject?.name.trim();
    const sessionSubjectLabel = sessionSubject || activeBrief?.title || "this campaign";
    const sessionName = sessionSubject
      ? `${sessionSubject} ${nextMode === "video" ? "Video Lab" : "Image Studio"}`
      : nextMode === "video"
        ? "New video session"
        : "New image session";
    const carriedPrompt = activeBrief?.prompt || briefDraft.prompt;
    const sessionPayload = {
      name: sessionName,
      mode: nextMode,
      project_id: activeProject?.id,
      summary: activeBrief?.title
    };

    if (connection === "online") {
      const created = await createSession(sessionPayload);
      setSessions((current) => [created.session, ...current]);
      setActiveSession(created.session);
      setTurns([]);
      setAssets([]);
      setSelectedReferenceIds([]);
      setExports([]);
      setSelectedAsset(null);
      setHandoffProofText("");
      setPrompt(carriedPrompt || "");
      setPromptRemixes([]);
      clearEditSource();
      clearCompare();
      setStatusText(
        activeProject || activeBrief
          ? `New session in ${sessionSubjectLabel}. Job jacket carried over.`
          : "New session. Fresh canvas."
      );
      return;
    }

    const localSession = { ...makeLocalSession(), ...sessionPayload };
    setSessions((current) => [localSession, ...current]);
    setActiveSession(localSession);
    setTurns([]);
    setAssets([]);
    setSelectedReferenceIds([]);
    setExports([]);
    setSelectedAsset(null);
    setHandoffProofText("");
    setPrompt(carriedPrompt || "");
    setPromptRemixes([]);
    clearEditSource();
    clearCompare();
    setStatusText(
      activeProject || activeBrief
        ? `Local preview in ${sessionSubjectLabel}. Job jacket carried over.`
        : "Local preview session ready."
    );
  }

  async function selectSession(session: StudioSession) {
    setActiveSession(session);
    setSelectedAsset(null);
    setHandoffProofText("");
    clearEditSource();
    clearCompare();

    if (connection !== "online") {
      return;
    }

    const projectForSession = projects.find((project) => project.id === session.project_id) ?? activeProject;
    const [turnResult, assetResult, exportResult, briefResult] = await Promise.all([
      listTurns(session.id),
      listAssets({ sessionId: session.id }),
      listExports().catch(() => ({ exports: [] })),
      projectForSession ? listBriefs(projectForSession.id).catch(() => ({ briefs: [] })) : Promise.resolve({ briefs: [] })
    ]);
    setTurns(turnResult.turns);
    setAssets(assetResult.assets);
    setSelectedReferenceIds(referenceIdsFromAssets(assetResult.assets));
    setExports(filterExportsForAssets(exportResult.exports, assetResult.assets));
    setActiveProject(projectForSession ?? null);
    setProjectName(projectForSession?.name ?? "Frank Body Campaign");
    setBriefs(briefResult.briefs);
    setActiveBrief(briefResult.briefs[0] ?? null);
    setBriefDraft(briefResult.briefs[0] ? briefToDraft(briefResult.briefs[0]) : makeBriefDraft());
    setSelectedAsset(firstReviewableAsset(assetResult.assets));
  }

  async function archiveSession(session: StudioSession) {
    try {
      if (connection === "online") {
        await updateSession(session.id, { status: "archived" });
      }
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not archive this session.");
      return;
    }

    const remaining = sessions.filter((item) => item.id !== session.id);
    setSessions(remaining);
    const next = remaining[0] ?? null;
    setActiveSession(next);
    setTurns([]);
    setAssets([]);
    setSelectedReferenceIds([]);
    setExports([]);
    setSelectedAsset(null);
    clearEditSource();
    clearCompare();
    if (next && connection === "online") {
      await selectSession(next);
    }
    setStatusText("Session tucked away.");
  }

  async function clearCurrentSession() {
    if (activeSession) {
      await archiveSession(activeSession);
    }
  }

  async function checkProviderReadiness() {
    setCheckingProviders(true);
    try {
      const readiness = await fetchProviderStatus();
      setProviderReadiness(readiness);
      if (readiness.models.length) {
        setConfig((current) => ({ ...current, models: readiness.models }));
      }
      setStatusText(
        `${readiness.summary.readyModels} provider ${readiness.summary.readyModels === 1 ? "model" : "models"} ready. Keys stay server-side.`
      );
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Provider check failed.");
    } finally {
      setCheckingProviders(false);
    }
  }

  async function checkSelectedModelPreflight() {
    if (!selectedModel) {
      return;
    }
    if (connection !== "online") {
      setStatusText("Start ComfyUI to check the selected model.");
      return;
    }

    const kind = studioMode === "video-lab" ? "video" : promptMode;
    const videoSourceAsset =
      selectedAsset && selectedAsset.kind !== "reference" && selectedAsset.media_type !== "video"
        ? selectedAsset
        : outputAssets.find((asset) => asset.approval_status === "approved" && asset.media_type !== "video") ??
          outputAssets.find((asset) => asset.media_type !== "video");

    setCheckingProviderPreflight(true);
    try {
      const result = await preflightProvider({
        session_id: activeSession?.id,
        kind,
        model: selectedModel.id,
        prompt,
        settings,
        reference_asset_ids: selectedReferenceAssets.map((asset) => asset.id),
        frank_body_mode: frankBodyMode,
        preset_key: selectedPresetKey,
        edit_source_asset_id: kind === "video" ? videoSourceAsset?.id : editSourceAsset?.id,
        mask_asset_id: kind === "masked_edit" ? maskAsset?.id : undefined
      });
      setProviderPreflight(result);
      setStatusText(result.ready ? `${result.model_label ?? selectedModel.short_label ?? selectedModel.label} preflight ready.` : result.message);
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Selected model preflight failed.");
    } finally {
      setCheckingProviderPreflight(false);
    }
  }

  async function checkProviderAdapterAudit() {
    if (connection !== "online") {
      setStatusText("Start ComfyUI to audit provider adapters.");
      return;
    }

    setCheckingProviderAudit(true);
    try {
      const audit = await fetchProviderAudit();
      setProviderAudit(audit);
      setStatusText(
        `${audit.summary.runner_registered} / ${audit.summary.model_count} provider adapters audited with no external calls.`
      );
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Provider adapter audit failed.");
    } finally {
      setCheckingProviderAudit(false);
    }
  }

  async function runDemoDoctor() {
    setCheckingDemoDoctor(true);
    try {
      const report = await fetchDemoDoctor();
      setDemoDoctor(report);
      hydrateLatestDemoArtifacts(report);
      setStatusText(report.readyForDemo ? "Demo Doctor says this is ready for Cliff." : "Demo Doctor found setup jobs.");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Demo Doctor could not run.");
    } finally {
      setCheckingDemoDoctor(false);
    }
  }

  async function resetDemoFromDoctor() {
    setResettingDemo(true);
    try {
      const result = await resetDemo({ create_assets: true });
      const seededAssets = result.assets ?? [];
      const seededOutputs = seededAssets.filter((asset) => !["reference", "mask"].includes(asset.kind));
      const turnSettings = parseJsonRecord(result.turn.settings_json) as Partial<StudioSettings>;

      setSessions([result.session]);
      setActiveSession(result.session);
      setProjects([result.project]);
      setActiveProject(result.project);
      setProjectName(result.project.name);
      setBriefs([result.brief]);
      setActiveBrief(result.brief);
      setBriefDraft(briefToDraft(result.brief));
      setTurns([result.turn]);
      setAssets(seededAssets);
      setSelectedReferenceIds(referenceIdsFromAssets(seededAssets));
      setExports([]);
      setSelectedAsset(firstReviewableAsset(seededOutputs));
      setLightboxAsset(null);
      clearEditSource();
      clearCompare();
      setPrompt(result.brief.prompt ?? result.turn.prompt ?? "");
      setPromptRemixes([]);
      setSelectedPresetKey(result.turn.preset_key ?? result.brief.task_type ?? "product-shot-lab");
      setSettings((current) => ({ ...current, ...turnSettings }));
      setDemoDoctor(result.doctor);
      setDemoEvidencePath("");
      setDemoEvidenceUrl("");
      setCallBriefPath("");
      setCallBriefUrl("");
      setCallDecision(null);
      setProviderReceiptPath("");
      setProviderReceiptUrl("");
      setBrandContextPath("");
      setBrandContextUrl("");
      setActivationChecklistPath("");
      setActivationChecklistUrl("");
      setReadinessPackPath("");
      setReadinessPackUrl("");
      setReadinessPackSha("");
      setImplementationManifestPath("");
      setImplementationManifestUrl("");
      setReadinessPackManifest(null);
      setHandoffProofText("");
      setStatusText("Demo reset. Fresh Frank Body starter session loaded.");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not reset the Frank demo.");
    } finally {
      setResettingDemo(false);
    }
  }

  function hydrateLatestDemoArtifacts(report: DemoDoctorStatus) {
    if (report.summary.demoEvidenceReady) {
      setDemoEvidencePath("frank-create-demo-evidence-latest.md");
      setDemoEvidenceUrl("/api/frank/demo/evidence/frank-create-demo-evidence-latest.md");
    } else {
      setDemoEvidencePath("");
      setDemoEvidenceUrl("");
    }

    if (report.summary.callBriefReady) {
      setCallBriefPath("frank-create-call-brief-latest.md");
      setCallBriefUrl("/api/frank/demo/call-brief/frank-create-call-brief-latest.md");
    } else {
      setCallBriefPath("");
      setCallBriefUrl("");
    }
    setCallDecision(null);

    if (report.summary.providerReadinessReceiptReady) {
      setProviderReceiptPath("frank-create-provider-readiness-latest.md");
      setProviderReceiptUrl("/api/frank/demo/provider-readiness/frank-create-provider-readiness-latest.md");
    } else {
      setProviderReceiptPath("");
      setProviderReceiptUrl("");
    }

    if (report.summary.brandContextReceiptReady) {
      setBrandContextPath("frank-create-brand-context-latest.md");
      setBrandContextUrl("/api/frank/demo/brand-context/frank-create-brand-context-latest.md");
    } else {
      setBrandContextPath("");
      setBrandContextUrl("");
    }

    if (report.summary.activationChecklistReady) {
      setActivationChecklistPath("frank-create-activation-checklist-latest.md");
      setActivationChecklistUrl("/api/frank/demo/activation-checklist/frank-create-activation-checklist-latest.md");
    } else {
      setActivationChecklistPath("");
      setActivationChecklistUrl("");
    }

    if (report.summary.readinessPackReady) {
      setReadinessPackPath("frank-create-cliff-readiness-latest.zip");
      setReadinessPackUrl("/api/frank/demo/readiness-pack/frank-create-cliff-readiness-latest.zip");
      setReadinessPackSha(report.summary.readinessPackSha256 ?? "");
      setImplementationManifestPath("frank-create-implementation-manifest-latest.md");
      setImplementationManifestUrl("/api/frank/demo/readiness-pack/frank-create-implementation-manifest-latest.md");
      setReadinessPackManifest(null);
    } else {
      setReadinessPackPath("");
      setReadinessPackUrl("");
      setReadinessPackSha("");
      setImplementationManifestPath("");
      setImplementationManifestUrl("");
      setReadinessPackManifest(null);
    }
  }

  async function saveDemoEvidence() {
    setSavingDemoEvidence(true);
    try {
      const result = await createDemoEvidence({ base_url: window.location.origin });
      setDemoEvidencePath(result.latest_markdown_file ?? result.latest_markdown_path ?? result.markdown_file ?? result.markdown_path);
      setDemoEvidenceUrl(result.latest_markdown_url ?? result.markdown_url);
      openStudioLink(result.latest_markdown_url ?? result.markdown_url, "Demo evidence", `Demo evidence saved: ${result.markdown_file}`);
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not save demo evidence.");
    } finally {
      setSavingDemoEvidence(false);
    }
  }

  async function saveCallBrief() {
    setSavingCallBrief(true);
    try {
      const result = await createDemoCallBrief({ base_url: window.location.origin });
      setCallBriefPath(result.latest_markdown_file ?? result.latest_markdown_path ?? result.markdown_file ?? result.markdown_path);
      setCallBriefUrl(result.latest_markdown_url ?? result.markdown_url);
      setCallDecision(result.brief.call_decision ?? null);
      openStudioLink(result.latest_markdown_url ?? result.markdown_url, "Call brief", `Call brief saved: ${result.latest_markdown_file ?? result.markdown_file}`);
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not save the call brief.");
    } finally {
      setSavingCallBrief(false);
    }
  }

  async function saveProviderReadinessReceipt() {
    if (connection !== "online") {
      setStatusText("Start ComfyUI to save the provider receipt.");
      return;
    }

    setSavingProviderReceipt(true);
    try {
      const result = await createProviderReadinessReceipt();
      setProviderReceiptPath(result.latest_markdown_file ?? result.latest_markdown_path ?? result.markdown_file ?? result.markdown_path);
      setProviderReceiptUrl(result.latest_markdown_url ?? result.markdown_url);
      setProviderAudit(result.receipt.adapter_audit);
      openStudioLink(
        result.latest_markdown_url ?? result.markdown_url,
        "Provider receipt",
        `Provider receipt saved: ${result.latest_markdown_file ?? result.markdown_file}`
      );
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not save provider readiness receipt.");
    } finally {
      setSavingProviderReceipt(false);
    }
  }

  function openStudioLink(url: string | undefined, label: string, openingText?: string) {
    if (!url) {
      setStatusText(`${label} link is not ready yet.`);
      return null;
    }
    const opened = window.open(url, "_blank");
    setStatusText(opened ? openingText ?? `Opening ${label.toLowerCase()}.` : `${label} link ready: ${url}`);
    return opened;
  }

  async function copyStudioLink(url: string, label: string) {
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard API unavailable");
      }
      await navigator.clipboard.writeText(url);
      setStatusText(`${label} link copied.`);
    } catch {
      setStatusText(`Could not copy ${label.toLowerCase()} link.`);
    }
  }

  async function copyProviderKeyPlan() {
    const plan = providerKeyPlanText({
      rows: providerUnlockRows,
      envVars: providerSetupState.envVars,
      readyModels: providerReadiness?.summary.readyModels,
      modelCount: providerReadiness?.summary.modelCount ?? config.models.filter((model) => model.provider !== "local").length,
      keyFilePath: providerEnvStatus?.filePath ?? "user\\frank_create\\provider_keys.env"
    });

    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard API unavailable");
      }
      await navigator.clipboard.writeText(plan);
      setStatusText("Provider key plan copied for Cliff. No secret values included.");
    } catch {
      setStatusText("Could not copy the provider key plan. Use the visible Cliff key order instead.");
    }
  }

  async function copyProductionUnlockPlan() {
    if (!activationChecklist) {
      setStatusText("Run the activation checklist before copying the production unlock plan.");
      return;
    }

    const plan = productionUnlockPlanText(activationChecklist);
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard API unavailable");
      }
      await navigator.clipboard.writeText(plan);
      setStatusText("Production unlock plan copied for Cliff. No secret values included.");
    } catch {
      setStatusText("Could not copy the production unlock plan. Use the visible activation checklist instead.");
    }
  }

  async function buildReadinessPack() {
    setBuildingReadinessPack(true);
    try {
      const result = await createDemoReadinessPack({ base_url: window.location.origin });
      setDemoEvidencePath(
        result.evidence.latest_markdown_file ??
          result.evidence.markdown_file ??
          result.evidence.latest_markdown_path ??
          result.evidence.markdown_path
      );
      setDemoEvidenceUrl(result.evidence.latest_markdown_url ?? result.evidence.markdown_url);
      if (result.call_brief) {
        setCallBriefPath(
          result.call_brief.latest_markdown_file ??
            result.call_brief.markdown_file ??
            result.call_brief.latest_markdown_path ??
            result.call_brief.markdown_path
        );
        setCallBriefUrl(result.call_brief.latest_markdown_url ?? result.call_brief.markdown_url);
      }
      if (result.provider_readiness) {
        setProviderReceiptPath(
          result.provider_readiness.latest_markdown_file ??
            result.provider_readiness.markdown_file ??
            result.provider_readiness.latest_markdown_path ??
            result.provider_readiness.markdown_path
        );
        setProviderReceiptUrl(result.provider_readiness.latest_markdown_url ?? result.provider_readiness.markdown_url);
        setProviderAudit(result.provider_readiness.receipt.adapter_audit);
      }
      if (result.brand_context) {
        setBrandContextPath(
          result.brand_context.latest_markdown_file ??
            result.brand_context.markdown_file ??
            result.brand_context.latest_markdown_path ??
            result.brand_context.markdown_path
        );
        setBrandContextUrl(result.brand_context.latest_markdown_url ?? result.brand_context.markdown_url);
      }
      if (result.activation_checklist) {
        setActivationChecklistPath(
          result.activation_checklist.latest_markdown_file ??
            result.activation_checklist.markdown_file ??
            result.activation_checklist.latest_markdown_path ??
            result.activation_checklist.markdown_path
        );
        setActivationChecklistUrl(result.activation_checklist.latest_markdown_url ?? result.activation_checklist.markdown_url);
      }
      setReadinessPackPath(result.latest_file_name ?? result.latest_file_path ?? result.file_name ?? result.file_path);
      setReadinessPackUrl(result.latest_download_url ?? result.download_url);
      setReadinessPackSha(result.latest_checksum_sha256 ?? result.checksum_sha256 ?? "");
      setImplementationManifestPath(result.latest_implementation_manifest_path ? "frank-create-implementation-manifest-latest.md" : "");
      setImplementationManifestUrl(result.latest_implementation_manifest_url ?? "");
      setReadinessPackManifest(result.manifest);
      openStudioLink(result.latest_download_url ?? result.download_url, "Call pack", `Call pack built: ${result.latest_file_name ?? result.file_name}`);
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not build the call pack.");
    } finally {
      setBuildingReadinessPack(false);
    }
  }

  async function createServerKeyFile() {
    setProviderEnvBusy(true);
    try {
      const status = await createProviderEnvTemplate();
      setProviderEnvStatus(status);
      setStatusText(status.created ? "Server key file created. Fill it, then reload keys." : "Server key file is already there.");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not create the server key file.");
    } finally {
      setProviderEnvBusy(false);
    }
  }

  async function reloadServerKeys() {
    setProviderEnvBusy(true);
    try {
      const status = await reloadProviderEnv();
      setProviderEnvStatus(status);
      if (status.readiness) {
        setProviderReadiness(status.readiness);
        if (status.readiness.models.length) {
          setConfig((current) => ({ ...current, models: status.readiness!.models }));
        }
      }
      const loadedCount = status.loadedEnvVars?.length ?? 0;
      const ignoredPlaceholderCount = status.ignoredPlaceholderEnvVars?.length ?? 0;
      setStatusText(
        ignoredPlaceholderCount
          ? `${ignoredPlaceholderCount} placeholder key ${ignoredPlaceholderCount === 1 ? "value was" : "values were"} ignored. Paste rotated keys, then reload.`
          : loadedCount
          ? `${loadedCount} server key ${loadedCount === 1 ? "name" : "names"} reloaded.`
          : "No filled server keys found yet."
      );
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not reload server keys.");
    } finally {
      setProviderEnvBusy(false);
    }
  }

  function updateProviderKeyDraft(envVar: string, value: string) {
    setProviderKeyDraft((current) => ({ ...current, [envVar]: value }));
  }

  async function saveServerKeys() {
    const keys = Object.fromEntries(
      Object.entries(providerKeyDraft)
        .map(([envVar, value]) => [envVar, value.trim()])
        .filter(([, value]) => value)
    );

    if (!Object.keys(keys).length) {
      setStatusText("Paste at least one rotated provider key first.");
      return;
    }

    setProviderEnvBusy(true);
    try {
      const status = await saveProviderEnvKeys(keys);
      setProviderEnvStatus(status);
      if (status.readiness) {
        setProviderReadiness(status.readiness);
        if (status.readiness.models.length) {
          setConfig((current) => ({ ...current, models: status.readiness!.models }));
        }
      }
      setProviderKeyDraft({});
      const savedCount = status.savedEnvVars?.length ?? 0;
      const ignoredPlaceholderCount = status.ignoredPlaceholderEnvVars?.length ?? 0;
      setStatusText(
        ignoredPlaceholderCount
          ? `${ignoredPlaceholderCount} placeholder key ${ignoredPlaceholderCount === 1 ? "value was" : "values were"} ignored. Paste rotated keys before saving.`
          : savedCount
          ? `${savedCount} server key ${savedCount === 1 ? "name" : "names"} saved. Secret values stayed server-side.`
          : "No provider keys were saved."
      );
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not save server keys.");
    } finally {
      setProviderEnvBusy(false);
    }
  }

  async function prepareLocalEngine() {
    if (connection !== "online") {
      setStatusText("Start ComfyUI before preparing local model folders.");
      return;
    }

    setLocalEngineBusy(true);
    try {
      const result = await prepareLocalEngineFolders();
      setConfig((current) => ({ ...current, localEngine: result.localEngine }));
      const createdCount = result.created_dirs?.length ?? 0;
      setStatusText(
        createdCount
          ? `${createdCount} local model folders created. Add checkpoints, then run Demo Doctor.`
          : "Local model folders are ready. Add checkpoints, then run Demo Doctor."
      );
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not prepare local model folders.");
    } finally {
      setLocalEngineBusy(false);
    }
  }

  function downloadWorkflowBlueprint(blueprint: WorkflowBlueprint) {
    try {
      const payload = {
        product: "Frank Create",
        key: blueprint.key,
        label: blueprint.label,
        use: blueprint.use,
        node_types: blueprint.node_types,
        workflow_json: blueprint.workflow_json,
        provider_keys: "server-side only; no secrets included"
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${safeFileStem(blueprint.key)}-workflow.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setStatusText("Comfy workflow blueprint downloaded.");
    } catch {
      setStatusText("Could not download that Comfy workflow blueprint.");
    }
  }

  async function saveBrandKit() {
    setBrandKitBusy(true);
    try {
      if (connection !== "online") {
        setBrandKit(brandKitDraft);
        setStatusText("Start ComfyUI to save the Brand Kit server-side.");
        return;
      }
      const updated = await updateBrandKit(brandKitDraft);
      setBrandKit(updated.brandKit);
      setBrandKitDraft(updated.brandKit);
      setStatusText("Brand kit saved for Frank Body Mode.");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not save the Brand Kit.");
    } finally {
      setBrandKitBusy(false);
    }
  }

  async function saveBrandContextBrief() {
    if (connection !== "online") {
      setStatusText("Start ComfyUI to save the brand context brief.");
      return;
    }

    setBrandContextBusy(true);
    try {
      const result = await createBrandContextReceipt({ session_id: activeSession?.id });
      setBrandContextPath(result.latest_markdown_file ?? result.latest_markdown_path ?? result.markdown_file ?? result.markdown_path);
      setBrandContextUrl(result.latest_markdown_url ?? result.markdown_url);
      const refs = result.receipt.summary.reference_asset_count;
      openStudioLink(
        result.latest_markdown_url ?? result.markdown_url,
        "Brand context",
        `Brand context brief saved: ${refs} reference ${refs === 1 ? "asset" : "assets"} counted.`
      );
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not save the brand context brief.");
    } finally {
      setBrandContextBusy(false);
    }
  }

  async function saveProjectBrief() {
    if (!activeSession) {
      setStatusText("Open a session before saving a brief.");
      return;
    }

    setBriefBusy(true);
    try {
      if (connection !== "online") {
        setStatusText("Start ComfyUI to save the brief server-side.");
        return;
      }

      const cleanProjectName = projectName.trim() || briefDraft.productName.trim() || "Frank Body Campaign";
      let project = activeProject;
      if (!project || project.name !== cleanProjectName) {
        const createdProject = await createProject({ name: cleanProjectName, client: "Frank Body", status: "active" });
        project = createdProject.project;
        setProjects((current) => [project!, ...current.filter((item) => item.id !== project!.id)]);
      }

      const briefPayload = createBriefPayload({ ...briefDraft, title: "" }, project.id);
      const savedBrief =
        activeBrief && activeBrief.project_id === project.id
          ? await updateBrief(activeBrief.id, briefPayload)
          : await createBrief(briefPayload);
      const updatedSession = await updateSession(activeSession.id, {
        project_id: project.id,
        summary: savedBrief.brief.title
      });

      setActiveProject(project);
      setProjectName(project.name);
      setActiveBrief(savedBrief.brief);
      setBriefDraft(briefToDraft(savedBrief.brief));
      setBriefs((current) => [savedBrief.brief, ...current.filter((item) => item.id !== savedBrief.brief.id)]);
      setActiveSession(updatedSession.session);
      setSessions((current) => current.map((session) => (session.id === updatedSession.session.id ? updatedSession.session : session)));
      if (!prompt.trim() && savedBrief.brief.prompt) {
        setPrompt(savedBrief.brief.prompt);
      }
      setStatusText(
        activeBrief && activeBrief.project_id === project.id
          ? "Brief updated. Job jacket is current."
          : "Brief saved. The studio has a job jacket now."
      );
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not save the campaign brief.");
    } finally {
      setBriefBusy(false);
    }
  }

  function inspectAsset(asset: Asset) {
    if (compareBaseAsset && asset.kind !== "reference") {
      if (asset.id === compareBaseAsset.id) {
        setStatusText("Pick a different image to compare.");
        return;
      }
      setSelectedAsset(asset);
      setCompareTargetAsset(asset);
      setLightboxAsset(null);
      setStatusText("Compare the picks side by side.");
      return;
    }

    setSelectedAsset(asset);
    setLightboxAsset(asset);
  }

  function startCompare(asset: Asset) {
    setCompareBaseAsset(asset);
    setCompareTargetAsset(null);
    setLightboxAsset(null);
    setStatusText("Choose another output to compare.");
  }

  function clearCompare() {
    setCompareBaseAsset(null);
    setCompareTargetAsset(null);
  }

  function syncCompareAsset(asset: Asset) {
    setCompareBaseAsset((current) => (current?.id === asset.id ? asset : current));
    setCompareTargetAsset((current) => (current?.id === asset.id ? asset : current));
  }

  function hydratePromptFromBrief(brief?: Brief | null) {
    if (!brief?.prompt) {
      return;
    }
    setPrompt((current) => (current.trim() ? current : brief.prompt ?? ""));
  }

  function toggleReferenceForRound(asset: Asset) {
    setSelectedAsset(asset);
    setSelectedReferenceIds((current) => {
      if (current.includes(asset.id)) {
        setStatusText(`${asset.title} skipped for the next round.`);
        return current.filter((id) => id !== asset.id);
      }
      setStatusText(`${asset.title} added to the next round.`);
      return [...current, asset.id];
    });
  }

  async function handleReferenceUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length || !activeSession) {
      return;
    }

    setStatusText("Adding reference images...");
    const createdAssets: Asset[] = [];
    const failedUploads: string[] = [];

    for (const file of files.slice(0, modelOptions.referenceLimit || files.length)) {
      const localPreview = URL.createObjectURL(file);
      if (connection === "online") {
        try {
          const uploaded = await uploadImage(file);
          const created = await createReference({
            session_id: activeSession.id,
            title: file.name,
            file_path: makeStoredImagePath(uploaded),
            preview_url: makeViewUrl(uploaded),
            media_type: "image",
            sync_status: "local"
          });
          createdAssets.push(created.asset);
          continue;
        } catch {
          failedUploads.push(file.name);
          continue;
        }
      }

      createdAssets.push({
        id: makeLocalId("asset"),
        session_id: activeSession.id,
        kind: "reference",
        title: file.name,
        media_type: "image",
        preview_url: localPreview,
        favorite: false,
        approval_status: "review",
        sync_status: "local"
      });
    }

    if (createdAssets.length) {
      setAssets((current) => [...createdAssets, ...current]);
      setSelectedReferenceIds((current) => Array.from(new Set([...createdAssets.map((asset) => asset.id), ...current])));
    }
    if (failedUploads.length && createdAssets.length) {
      setStatusText(`${createdAssets.length} reference${createdAssets.length === 1 ? "" : "s"} locked. ${failedUploads.length} upload${failedUploads.length === 1 ? "" : "s"} failed.`);
    } else if (failedUploads.length) {
      setStatusText("Reference upload failed. Try again after restarting Comfy.");
    } else {
      setStatusText("Reference locked. Nice.");
    }
    event.target.value = "";
  }

  async function saveMaskFile(file: File, sourceAsset: Asset) {
    if (!activeSession) {
      throw new Error("Start a session before adding a mask.");
    }

    setStatusText("Adding edit mask...");

    if (connection === "online") {
      const uploaded = await uploadImage(file);
      const created = await createAsset({
        session_id: sourceAsset.session_id ?? activeSession.id,
        kind: "mask",
        title: file.name,
        file_path: makeStoredImagePath(uploaded),
        preview_url: makeViewUrl(uploaded),
        media_type: "image",
        source_asset_id: sourceAsset.id,
        sync_status: "local"
      });
      setMaskAsset(created.asset);
      setAssets((current) => [created.asset, ...current]);
      setStatusText("Mask locked for this edit.");
      return created.asset;
    }

    const localPreview = URL.createObjectURL(file);
    const localMask: Asset = {
      id: makeLocalId("asset"),
      session_id: sourceAsset.session_id ?? activeSession.id,
      kind: "mask",
      title: file.name,
      media_type: "image",
      preview_url: localPreview,
      source_asset_id: sourceAsset.id,
      favorite: false,
      approval_status: "review",
      sync_status: "local"
    };
    setMaskAsset(localMask);
    setAssets((current) => [localMask, ...current]);
    setStatusText("Mask locked for this edit.");
    return localMask;
  }

  async function handleMaskUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !activeSession || !editSourceAsset) {
      return;
    }

    try {
      await saveMaskFile(file, editSourceAsset);
    } catch {
      setStatusText("Mask upload failed. Try again after restarting Comfy.");
    }
    event.target.value = "";
  }

  async function handlePaintedMaskSave(file: File) {
    if (!maskPainterAsset) {
      return;
    }

    setMaskPainterBusy(true);
    try {
      await saveMaskFile(file, maskPainterAsset);
      setMaskPainterAsset(null);
    } catch {
      setStatusText("Painted mask could not be saved. Try uploading a PNG mask.");
    } finally {
      setMaskPainterBusy(false);
    }
  }

  async function handlePromptRemix() {
    const seedPrompt = prompt.trim() || activePreset?.prompt || "";
    if (!seedPrompt) {
      setStatusText("Give the Art Dept. a brief first.");
      return;
    }

    setRemixBusy(true);
    try {
      const result = await remixPrompt({
        prompt: seedPrompt,
        preset_key: selectedPresetKey,
        frank_body_mode: frankBodyMode
      });
      setPromptRemixes(result.variants);
      setStatusText("Brief remixed. Pick a direction.");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Brief remix needs another look.");
    } finally {
      setRemixBusy(false);
    }
  }

  function applyPromptRemix(variant: PromptRemixVariant) {
    setPrompt(variant.prompt);
    setPromptRemixes([]);
    setStatusText(`${variant.label} direction loaded.`);
  }

  async function handleGenerate(event?: FormEvent) {
    event?.preventDefault();
    if (!activeSession || !selectedModel || !prompt.trim()) {
      setStatusText("Give the studio a prompt first.");
      return;
    }

    if (studioMode === "video-lab") {
      await handleVideoGenerate();
      return;
    }

    if (promptMode === "edit" && !selectedModel.capabilities.edit) {
      setStatusText(`${selectedModel.short_label ?? selectedModel.label} cannot edit images yet.`);
      return;
    }

    if (promptMode === "masked_edit" && !selectedModel.capabilities.masked_edit) {
      setStatusText(`${selectedModel.short_label ?? selectedModel.label} cannot use masks yet.`);
      return;
    }

    const missingKeyMessage = modelMissingKeyAction(selectedModel);
    if (missingKeyMessage) {
      setStatusText(missingKeyMessage);
      return;
    }

    const referenceLimitMessage = modelReferenceLimitAction(selectedModel, selectedReferenceAssets.length);
    if (referenceLimitMessage) {
      setStatusText(referenceLimitMessage);
      return;
    }

    setBusy(true);
    setStatusText(promptMode === "generate" ? "Preparing the next round..." : "Preparing the edit brief...");

    const request = buildTurnRequest({
      sessionId: activeSession.id,
      modelId: selectedModel.id,
      prompt,
      promptMode,
      frankBodyMode,
      presetKey: selectedPresetKey,
      settings,
      referenceAssetIds: selectedReferenceAssets.map((asset) => asset.id),
      editSourceAssetId: editSourceAsset?.id,
      maskAssetId: promptMode === "masked_edit" ? maskAsset?.id : undefined
    });

    try {
      if (connection !== "online") {
        const localTurn = makeLocalTurn(activeSession.id, request);
        setTurns((current) => [...current, localTurn]);
        setStatusText("Comfy offline. The turn is staged locally for the UI.");
        return;
      }

      const result = await createInferenceTurn(request);
      setTurns((current) => [...current, result.turn]);

      if (result.status === "blocked") {
        setStatusText(`Server key needed: ${(result.error?.env_vars ?? []).join(" or ")}`);
      } else if (result.status === "failed") {
        const turnError = turnErrorCopy(result.turn);
        setStatusText(
          result.error?.message ||
            turnError ||
            inferenceStatusCopy({
              status: result.status,
              assetCount: result.assets?.length ?? 0,
              localEngine: result.localEngine,
              fallbackReason: result.fallbackReason
            })
        );
      } else {
        if (result.status === "complete" && result.assets?.length) {
          setAssets((current) => [...result.assets!, ...current]);
          setSelectedAsset(result.assets[0]);
          if (promptMode !== "generate") {
            setEditSourceAsset(null);
            setMaskAsset(null);
          }
          clearCompare();
        }
        setStatusText(
          inferenceStatusCopy({
            status: result.status,
            assetCount: result.assets?.length ?? 0,
            localEngine: result.localEngine,
            fallbackReason: result.fallbackReason
          })
        );
      }
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "This round needs another look.");
    } finally {
      setBusy(false);
    }
  }

  async function handleVideoGenerate() {
    if (!activeSession || !prompt.trim()) {
      setStatusText("Give Video Lab a motion brief first.");
      return;
    }

    if (connection !== "online") {
      setStatusText("Start Comfy/Frank backend to make the motion board.");
      return;
    }

    const sourceAsset =
      selectedAsset && selectedAsset.kind !== "reference" && selectedAsset.media_type !== "video"
        ? selectedAsset
        : outputAssets.find((asset) => asset.approval_status === "approved" && asset.media_type !== "video") ??
          outputAssets.find((asset) => asset.media_type !== "video");
    const localVideoModel = config.models.find((model) => model.id === "frank-local-comfy");
    const videoModel =
      selectedModel && selectedModel.provider !== "local" && selectedModel.capabilities.video
        ? selectedModel
        : localVideoModel ?? selectedModel;

    const missingKeyMessage = modelMissingKeyAction(videoModel);
    if (missingKeyMessage) {
      setStatusText(missingKeyMessage);
      return;
    }

    const referenceLimitMessage = modelReferenceLimitAction(videoModel, selectedReferenceAssets.length);
    if (referenceLimitMessage) {
      setStatusText(referenceLimitMessage);
      return;
    }

    if (videoModel?.provider !== "local" && !sourceAsset) {
      setStatusText("Choose an image before making live motion.");
      return;
    }

    setBusy(true);
    setStatusText("Video Lab is making the motion board...");

    try {
      const result = await createVideoStoryboard({
        session_id: activeSession.id,
        model: videoModel?.id,
        prompt,
        settings,
        source_asset_id: sourceAsset?.id,
        reference_asset_ids: selectedReferenceAssets.map((asset) => asset.id)
      });
      setTurns((current) => [...current, result.turn]);
      if (result.status === "blocked") {
        setStatusText(`Server key needed: ${(result.error?.env_vars ?? []).join(" or ")}`);
        return;
      }
      if (result.status === "failed") {
        setStatusText(result.error?.message ?? "Video Lab returned no motion asset.");
        return;
      }
      if (result.assets?.length) {
        setAssets((current) => [...result.assets!, ...current]);
        setSelectedAsset(result.assets[0]);
        setStatusText("Motion board is on the wall.");
        return;
      }
      setStatusText("Video Lab returned no motion asset.");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Video Lab needs another look.");
    } finally {
      setBusy(false);
    }
  }

  async function changeAssetStatus(asset: Asset, approval_status: Asset["approval_status"]) {
    const optimistic = { ...asset, approval_status };
    setAssets((current) => current.map((item) => (item.id === asset.id ? optimistic : item)));
    setSelectedAsset(optimistic);
    syncCompareAsset(optimistic);

    try {
      if (connection === "online") {
        const updated = await updateAsset(asset.id, { approval_status });
        setAssets((current) => current.map((item) => (item.id === updated.asset.id ? updated.asset : item)));
        setSelectedAsset(updated.asset);
        syncCompareAsset(updated.asset);
      }

      setStatusText(assetStatusCopy(approval_status));
    } catch (error) {
      setAssets((current) => current.map((item) => (item.id === asset.id ? asset : item)));
      setSelectedAsset(asset);
      syncCompareAsset(asset);
      setStatusText(error instanceof Error ? error.message : "Could not update review status.");
    }
  }

  async function toggleFavorite(asset: Asset) {
    const optimistic = { ...asset, favorite: !asset.favorite };
    setAssets((current) => current.map((item) => (item.id === asset.id ? optimistic : item)));
    setSelectedAsset(optimistic);
    syncCompareAsset(optimistic);

    try {
      if (connection === "online") {
        const updated = await updateAsset(asset.id, { favorite: !asset.favorite });
        setAssets((current) => current.map((item) => (item.id === updated.asset.id ? updated.asset : item)));
        setSelectedAsset(updated.asset);
        syncCompareAsset(updated.asset);
      }
    } catch (error) {
      setAssets((current) => current.map((item) => (item.id === asset.id ? asset : item)));
      setSelectedAsset(asset);
      syncCompareAsset(asset);
      setStatusText(error instanceof Error ? error.message : "Could not update favorite.");
    }
  }

  async function saveAssetNotes(asset: Asset) {
    const optimistic = { ...asset, notes: assetNotesDraft };
    setAssets((current) => current.map((item) => (item.id === asset.id ? optimistic : item)));
    setSelectedAsset(optimistic);
    syncCompareAsset(optimistic);

    try {
      if (connection === "online") {
        const updated = await updateAsset(asset.id, { notes: assetNotesDraft });
        setAssets((current) => current.map((item) => (item.id === updated.asset.id ? updated.asset : item)));
        setSelectedAsset(updated.asset);
        syncCompareAsset(updated.asset);
      }

      setStatusText("Note saved for the next round.");
    } catch (error) {
      setAssets((current) => current.map((item) => (item.id === asset.id ? asset : item)));
      setSelectedAsset(asset);
      syncCompareAsset(asset);
      setAssetNotesDraft(asset.notes ?? "");
      setStatusText(error instanceof Error ? error.message : "Could not save review note.");
    }
  }

  async function useAssetAsReference(asset: Asset) {
    if (!activeSession) {
      setStatusText("Start a session before adding references.");
      return;
    }
    if (!asset.file_path) {
      setStatusText("This pick needs a saved file before it can become a reference.");
      return;
    }

    const existingReference = assets.find((item) => item.kind === "reference" && item.source_asset_id === asset.id);
    if (existingReference) {
      setSelectedReferenceIds((current) => Array.from(new Set([existingReference.id, ...current])));
      setStatusText(`${asset.title} is ready as a selected reference.`);
      return;
    }

    const referencePayload = {
      session_id: activeSession.id,
      title: `${asset.title} reference`,
      file_path: asset.file_path,
      preview_url: asset.preview_url,
      media_type: "image",
      provider: asset.provider,
      model: asset.model,
      prompt: asset.prompt,
      settings_json: asset.settings_json,
      source_asset_id: asset.id,
      width: asset.width,
      height: asset.height,
      sync_status: "local"
    };

    try {
      const reference =
        connection === "online"
          ? (await createReference(referencePayload)).asset
          : ({
              id: makeLocalId("asset"),
              kind: "reference",
              favorite: false,
              approval_status: "review",
              ...referencePayload
            } as Asset);

      setAssets((current) => [reference, ...current]);
      setSelectedReferenceIds((current) => Array.from(new Set([reference.id, ...current])));
      setStatusText(`${asset.title} is ready as a selected reference.`);
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not turn this pick into a reference.");
    }
  }

  async function removeAssetFromSession(asset: Asset) {
    try {
      if (connection === "online") {
        await deleteAsset(asset.id);
      }
      setAssets((current) => current.filter((item) => item.id !== asset.id));
      setExports((current) => current.filter((record) => record.asset_id !== asset.id));
      setSelectedReferenceIds((current) => current.filter((id) => id !== asset.id));
      setSelectedAsset((current) => {
        if (current?.id !== asset.id) {
          return current;
        }
        return assets.find((item) => item.id !== asset.id && !["reference", "mask"].includes(item.kind)) ?? null;
      });
      if (lightboxAsset?.id === asset.id) {
        setLightboxAsset(null);
      }
      if (compareBaseAsset?.id === asset.id || compareTargetAsset?.id === asset.id) {
        clearCompare();
      }
      if (editSourceAsset?.id === asset.id) {
        clearEditSource();
      }
      if (maskAsset?.id === asset.id) {
        setMaskAsset(null);
      }
      setStatusText(asset.kind === "reference" ? "Reference removed from this session." : "Asset removed from this session.");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Could not remove this asset.");
    }
  }

  async function copyRunBrief(asset: Asset) {
    const brief = selectedAssetRunBrief(asset, assets, config, turns);
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard API unavailable");
      }
      await navigator.clipboard.writeText(brief);
      setStatusText("Run brief copied for the handoff.");
    } catch {
      setStatusText("Could not copy the run brief. Use the export metadata instead.");
    }
  }

  function downloadWorkflowJson(asset: Asset) {
    try {
      const workflowJson = selectedAssetWorkflowJson(asset, assets, config, turns);
      const blob = new Blob([JSON.stringify(workflowJson, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${safeFileStem(asset.title || asset.id)}-workflow.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setStatusText("Workflow JSON downloaded for this pick.");
    } catch {
      setStatusText("Could not download workflow JSON for this pick.");
    }
  }

  function openAssetInComfyCanvas(asset: Asset) {
    const url = comfyCanvasAssetUrl(asset.id);
    const opened = window.open(url, "_blank");
    setStatusText(opened ? "Opening this pick in the branded Comfy canvas." : `Comfy canvas link ready: ${url}`);
  }

  async function exportAsset(asset: Asset, preset: ExportPreset) {
    if (connection !== "online") {
      setStatusText("Start ComfyUI to export this pick.");
      return;
    }

    try {
      const created = await createExport({
        asset_id: asset.id,
        preset: preset.key,
        file_path: `user/frank_create/exports/${asset.id}-${preset.key}.json`,
        metadata: {
          preset,
          asset,
          session: activeSession,
          model: selectedModel,
          app: "Frank Create Image Studio"
        }
      });
      const exportRecord = normalizeExportRecord(created.export, {
        asset_id: asset.id,
        preset: preset.key,
        download_url: created.download_url
      });
      setExports((current) => [exportRecord, ...current.filter((item) => item.id !== exportRecord.id)]);
      openStudioLink(created.download_url || exportDownloadUrl(created.export.id), preset.label, `${preset.label} export pack saved.`);
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Export pack needs another look.");
    }
  }

  async function exportChannelSet(asset: Asset) {
    const presets = exportPresetsForAsset(config.exportPresets, asset)
      .filter((preset) => preset.key !== "video-storyboard")
      .map((preset) => preset.key);

    if (!presets.length) {
      setStatusText("No image channel presets for this asset.");
      return;
    }

    if (connection !== "online") {
      setStatusText("Start ComfyUI to export a channel set.");
      return;
    }

    try {
      const created = await createAssetChannelSet(asset.id, {
        presets,
        metadata: {
          asset,
          session: activeSession,
          model: selectedModel,
          app: "Frank Create Image Studio"
        }
      });
      const exportRecord = normalizeExportRecord(created.export, {
        asset_id: asset.id,
        preset: "channel-set",
        download_url: created.download_url
      });
      setExports((current) => [exportRecord, ...current.filter((item) => item.id !== exportRecord.id)]);
      const count = Number(created.metadata.preset_count ?? presets.length);
      openStudioLink(created.download_url || exportDownloadUrl(created.export.id), "Channel set", `${count} channel packs saved.`);
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Channel set export needs another look.");
    }
  }

  async function exportSessionHandoff() {
    if (!activeSession) {
      return;
    }

    setHandoffBusy(true);
    setStatusText("Packing the approved direction...");
    try {
      const created = await createSessionHandoff(activeSession.id);
      const exportRecord = normalizeExportRecord(created.handoff, {
        preset: "session-handoff",
        download_url: created.download_url,
        metadata_json: JSON.stringify(created.metadata ?? {})
      });
      setExports((current) => [exportRecord, ...current.filter((item) => item.id !== exportRecord.id)]);
      const assetCount = Number(created.metadata.asset_count ?? approvedCount);
      const videoCount = Number(created.metadata.video_count ?? 0);
      const imageCount = Number(created.metadata.image_count ?? assetCount);
      const channelExportFiles = Number(created.metadata.channel_export_file_count ?? imageCount * imageExportPresetCount);
      const channelExportSets = Number(created.metadata.channel_export_set_count ?? imageCount);
      const label =
        videoCount > 0
          ? `${assetCount} approved asset${assetCount === 1 ? "" : "s"} (${imageCount} image${imageCount === 1 ? "" : "s"}, ${videoCount} motion)`
          : `${assetCount} approved image${assetCount === 1 ? "" : "s"}`;
      setHandoffProofText(
        `Packed ${channelExportFiles} channel-ready exports across ${channelExportSets} approved image${channelExportSets === 1 ? "" : "s"}.`
      );
      openStudioLink(created.download_url || exportDownloadUrl(created.handoff.id), "Cliff Pack", `${label} packed for Cliff.`);
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Approve at least one image before exporting a handoff pack.");
    } finally {
      setHandoffBusy(false);
    }
  }

  function openSessionReviewBoard() {
    if (!activeSession || approvedCount === 0) {
      setStatusText("Approve at least one image before opening a review board.");
      return;
    }
    const url = sessionReviewBoardUrl(activeSession.id);
    const opened = window.open(url, "_blank");
    setStatusText(opened ? "Opening the visual review board." : `Review board link ready: ${url}`);
  }

  function openSessionSyncManifest() {
    if (!activeSession) {
      setStatusText("Start a session before opening a sync manifest.");
      return;
    }
    openStudioLink(sessionSyncManifestUrl(activeSession.id), "Sync manifest", "Opening the FrankHub sync manifest.");
  }

  function selectPreset(preset: PromptPreset) {
    setSelectedPresetKey(preset.key);
    setPrompt((current) => (current.trim() ? current : preset.prompt));
  }

  function selectTaskShortcut(task: FrankTask) {
    const taskPrompt = promptForTask(task);
    setSelectedPresetKey(task.key);
    setStudioMode(task.key === "prompt-remix" ? "image-studio" : "product-shot-lab");
    setPrompt((current) => (current.trim() ? `${current.trim()}\n\n${taskPrompt}` : taskPrompt));
    setSettings((current) => settingsForTask(task.key, current, selectedModel));
    setStatusText(`${task.label} is loaded.`);
  }

  function makeAnotherRound(asset: Asset, direction: "similar" | "cleanup" | "campaign") {
    const presetKey =
      direction === "cleanup" ? "clean-ecom" : direction === "campaign" ? "campaign-variants" : selectedPresetKey;
    const preset = config.promptPresets.find((item) => item.key === presetKey) ?? activePreset;
    const editModel =
      selectedModel?.capabilities.edit
        ? selectedModel
        : config.models.find((model) => model.capabilities.edit && model.configured !== false) ??
          config.models.find((model) => model.capabilities.edit);
    if (editModel) {
      setSelectedModelId(editModel.id);
    }
    setSelectedPresetKey(preset?.key ?? selectedPresetKey);
    startEditFromAsset(asset);
    setPrompt(nextRoundPrompt(asset, direction, preset));
    setSettings((current) => ({ ...current, count: 4 }));
    setLightboxAsset(null);
    clearCompare();
    setStatusText("Next round is briefed from this pick.");
  }

  function showGraph() {
    window.history.pushState({ surface: "graph" }, "", "/graph");
    setSurface("graph");
  }

  function showStudio() {
    window.history.pushState({ surface: "studio" }, "", "/");
    setSurface("studio");
  }

  function startWalkthrough() {
    setWalkthroughStep(0);
    setWalkthroughOpen(true);
  }

  const activeWalkthroughStep = WALKTHROUGH_STEPS[walkthroughStep] ?? WALKTHROUGH_STEPS[0];
  const activeWalkthroughTarget = walkthroughOpen ? activeWalkthroughStep.target : null;
  const tourActive = (target: WalkthroughTarget) => (activeWalkthroughTarget === target ? "true" : undefined);

  useEffect(() => {
    if (!walkthroughOpen) {
      return;
    }
    if (activeWalkthroughStep.openSettings) {
      setSettingsOpen(true);
    }
    if (activeWalkthroughStep.openAdvanced) {
      setAdvancedOpen(true);
    }
    if (activeWalkthroughStep.selectOutput && !selectedAsset && firstOutputAsset) {
      setSelectedAsset(firstOutputAsset);
      setLightboxAsset(null);
    }
  }, [
    activeWalkthroughStep.openAdvanced,
    activeWalkthroughStep.openSettings,
    activeWalkthroughStep.selectOutput,
    firstOutputAsset,
    selectedAsset?.id,
    walkthroughOpen
  ]);

  useEffect(() => {
    if (!walkthroughOpen) {
      setWalkthroughAnchor(null);
      return;
    }

    const updateAnchor = () => {
      setWalkthroughAnchor(measureWalkthroughAnchor(activeWalkthroughStep.target));
    };
    const targetElement = document.querySelector<HTMLElement>(`[data-tour-id="${activeWalkthroughStep.target}"]`);
    if (targetElement) {
      const rect = targetElement.getBoundingClientRect();
      const absoluteTop = rect.top + window.scrollY;
      const centeredTop = Math.max(0, absoluteTop - window.innerHeight / 2 + rect.height / 2);
      if (!navigator.userAgent.toLowerCase().includes("jsdom")) {
        window.scrollTo({ top: centeredTop, behavior: "auto" });
      }
      targetElement.scrollIntoView?.({ block: "center", inline: "nearest" });
    }

    const updateTimer = window.setTimeout(updateAnchor, 140);
    window.addEventListener("resize", updateAnchor);
    window.addEventListener("scroll", updateAnchor, true);
    return () => {
      window.clearTimeout(updateTimer);
      window.removeEventListener("resize", updateAnchor);
      window.removeEventListener("scroll", updateAnchor, true);
    };
  }, [
    activeSession?.id,
    activeWalkthroughStep.target,
    advancedOpen,
    assets.length,
    selectedAsset?.id,
    settingsOpen,
    turns.length,
    walkthroughOpen
  ]);

  useEffect(() => {
    if (!walkthroughOpen) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setWalkthroughOpen(false);
      }
      if (event.key === "ArrowRight") {
        setWalkthroughStep((current) => Math.min(current + 1, WALKTHROUGH_STEPS.length - 1));
      }
      if (event.key === "ArrowLeft") {
        setWalkthroughStep((current) => Math.max(current - 1, 0));
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [walkthroughOpen]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("walkthrough") === "1") {
      setWalkthroughStep(0);
      setWalkthroughOpen(true);
    }
  }, []);

  const statusReadyLink = parseReadyStatusLink(statusText);

  if (surface === "graph") {
    return (
      <FrankGraphView
        activeSession={activeSession}
        assets={assets}
        connection={connection}
        rawGraphUrl={config.advancedGraphUrl}
        selectedModel={selectedModel}
        statusText={statusText}
        statusReadyLink={statusReadyLink}
        turns={turns}
        onBack={showStudio}
        onCopyLink={copyStudioLink}
        onOpenLink={openStudioLink}
      />
    );
  }

  return (
    <div
      className={`studio-shell guided-studio ${providerAuditMode ? "provider-audit-mode" : ""} ${advancedOpen ? "advanced-open" : ""}`}
      data-provider-audit={providerAuditMode ? "open" : undefined}
    >
      <header className="guided-header" data-tour-id="app-header" data-tour-active={tourActive("app-header")}>
        <div className="guided-brand">
          <div className="brand-mark" aria-label="Frank Body">
            <span>frank</span>
            <span>body</span>
          </div>
          <div>
            <p className="eyebrow">{config.voice.appTitle}</p>
            <h1>Frank Create</h1>
            <p>Add references, brief the image, generate picks, edit or approve one, export it.</p>
          </div>
        </div>
        <div className="guided-header-actions">
          <label className="session-picker">
            <span>Session</span>
            <select
              aria-label="Active session"
              value={activeSession?.id ?? ""}
              onChange={(event) => {
                const next = sessions.find((session) => session.id === event.target.value);
                if (next) {
                  void selectSession(next);
                }
              }}
            >
              {sessions.map((session) => (
                <option value={session.id} key={session.id}>
                  {session.name}
                </option>
              ))}
            </select>
          </label>
          <button className="secondary-button compact-action" type="button" onClick={handleNewSession}>
            <Plus size={16} />
            New
          </button>
          <button className="secondary-button compact-action" type="button" onClick={startWalkthrough}>
            <MessageSquareText size={16} />
            Demo Walkthrough
          </button>
          <button
            className="secondary-button compact-action"
            type="button"
            aria-controls="advanced-tools-drawer"
            aria-expanded={advancedOpen}
            onClick={() => setAdvancedOpen((current) => !current)}
          >
            {advancedOpen ? <XCircle size={16} /> : <GitBranch size={16} />}
            {advancedOpen ? "Close Advanced" : "Advanced"}
          </button>
        </div>
      </header>

      <main className="conversation-column">
        <header className="studio-topbar">
          <div>
            <p className="eyebrow">Creative Studio</p>
            <h2>{activeSession?.name ?? config.voice.labTitle}</h2>
            <p className="studio-topbar-copy">
              Brief in plain English. References and settings are optional. Click a pick to edit, approve, or export.
            </p>
          </div>
          <div className="stat-row" aria-label="Studio stats">
            <span>{turns.length} rounds</span>
            <span>{approvedCount} approved</span>
            <span>{favoriteCount} favorites</span>
          </div>
        </header>

        <section
          className="thread-surface"
          aria-label="Prompt and output thread"
          data-tour-id="output-thread"
          data-tour-active={tourActive("output-thread")}
        >
          {compareBaseAsset ? (
            <div className="compare-prompt" role="status">
              <span>
                Comparing from <strong>{compareBaseAsset.title}</strong>
              </span>
              <button type="button" onClick={clearCompare}>
                Cancel
              </button>
            </div>
          ) : null}
          {turns.length ? (
            turns.map((turn) => (
              <article className="turn-card" key={turn.id}>
                <div className="turn-copy">
                  <span className={`status-dot ${turn.status}`} />
                  <div>
                    <p className="eyebrow">{turnKindLabel(turn)}</p>
                    <h3>{modelName(config, turn.model)}</h3>
                    <p>{turn.prompt}</p>
                    <div className="turn-meta">
                      <span>{turn.status}</span>
                      {turn.frank_body_mode ? <span>Frank Body Mode</span> : <span>User prompt</span>}
                      {parseJsonList(turn.reference_asset_ids_json).length ? (
                        <span>{referenceCountLabel(parseJsonList(turn.reference_asset_ids_json).length)}</span>
                      ) : null}
                      {turnErrorCopy(turn) ? <span className="turn-error">{turnErrorCopy(turn)}</span> : null}
                    </div>
                  </div>
                </div>
                <OutputStrip
                  assets={displayOutputAssets.filter((asset) => asset.turn_id === turn.id)}
                  onSelect={inspectAsset}
                  emptyLabel={studioMode === "approved-hot" ? "No approved picks in this round" : turnEmptyLabel(turn)}
                  selectedAssetId={selectedAsset?.id}
                />
              </article>
            ))
          ) : (
            <div className="empty-thread">
              <ImageIcon size={38} />
              <strong>{config.voice.emptyState}</strong>
              <span>Start with a prompt and optional references. Product Shot Lab is now a preset, not a cage.</span>
            </div>
          )}
        </section>

        <form
          className="composer"
          onSubmit={handleGenerate}
          data-tour-id="composer"
          data-tour-active={tourActive("composer")}
        >
          {editSourceAsset ? (
            <div className="edit-banner">
              <ImageIcon size={16} />
              Editing {editSourceAsset.title}
              {maskAsset ? <span className="mask-pill">Mask {maskAsset.title}</span> : null}
              <button type="button" onClick={clearEditSource}>
                Clear
              </button>
            </div>
          ) : null}

          <div className="workflow-chip-row" aria-label="Workflow tasks">
            <button
              className={`task-chip ${studioMode === "image-studio" && reviewFilter === "all" ? "active" : ""}`}
              type="button"
              onClick={showImageStudio}
            >
              <MessageSquareText size={15} />
              Image Studio
            </button>
            <button
              className={`task-chip ${studioMode === "product-shot-lab" ? "active" : ""}`}
              type="button"
              onClick={showProductShotLab}
            >
              <Layers3 size={15} />
              Product Shot Lab
            </button>
            <button
              className={`task-chip ${studioMode === "video-lab" ? "active" : ""}`}
              type="button"
              onClick={showVideoLab}
            >
              <Film size={15} />
              Video Lab
            </button>
            <button
              className={`task-chip ${reviewFilter === "approved" ? "active" : ""}`}
              type="button"
              onClick={() => (reviewFilter === "approved" ? showImageStudio() : showApprovedHot())}
            >
              <CheckCircle2 size={15} />
              Approved only
            </button>
          </div>

          {studioMode === "product-shot-lab" ? (
            <div className="task-shortcut-list composer-task-shortcuts" aria-label="Product Image Lab task shortcuts">
              {productTaskShortcuts.map((task) => (
                <button
                  className={selectedPresetKey === task.key ? "selected" : ""}
                  key={task.key}
                  type="button"
                  onClick={() => selectTaskShortcut(task)}
                >
                  <span className="task-shortcut-icon">{taskShortcutIcon(task.key)}</span>
                  <span>
                    <strong>{task.label}</strong>
                    <small aria-hidden="true">{task.description}</small>
                  </span>
                </button>
              ))}
            </div>
          ) : null}

          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Brief the image: product, context, channel, mood, and what must stay accurate."
          />

          {promptRemixes.length ? (
            <div className="prompt-remix-panel" aria-label="Brief remix directions">
              {promptRemixes.map((variant) => (
                <button key={variant.key} type="button" onClick={() => applyPromptRemix(variant)}>
                  <strong>{variant.label}</strong>
                  <span>{variant.prompt}</span>
                </button>
              ))}
            </div>
          ) : null}

          <div className="composer-actions">
            <label className="upload-button">
              <Upload size={16} />
              Add references
              <input type="file" accept="image/*" multiple onChange={handleReferenceUpload} />
            </label>
            <div className="reference-dock" aria-label="Reference images">
              {referenceAssets.slice(0, 5).map((asset) => (
                <button
                  type="button"
                  key={asset.id}
                  className={selectedReferenceIdSet.has(asset.id) ? "selected" : ""}
                  aria-pressed={selectedReferenceIdSet.has(asset.id)}
                  title={`${selectedReferenceIdSet.has(asset.id) ? "Using" : "Skipping"} ${asset.title}`}
                  onClick={() => toggleReferenceForRound(asset)}
                >
                  {asset.preview_url ? <img src={asset.preview_url} alt={asset.title} /> : <Paperclip size={15} />}
                </button>
              ))}
              {referenceAssets.length ? (
                <span className="reference-selection-count">
                  {selectedReferenceAssets.length
                    ? `${selectedReferenceAssets.length} ref${selectedReferenceAssets.length === 1 ? "" : "s"} selected`
                    : "Prompt-only"}
                </span>
              ) : null}
            </div>
            {editSourceAsset && selectedModel?.capabilities.masked_edit ? (
              <>
                <button className="upload-button mask-paint-button" type="button" onClick={() => setMaskPainterAsset(editSourceAsset)}>
                  <Paintbrush size={16} />
                  Paint mask
                </button>
                <label className="upload-button mask-upload-button">
                  <Box size={16} />
                  Mask
                  <input aria-label="Upload edit mask" type="file" accept="image/png,image/webp,image/jpeg" onChange={handleMaskUpload} />
                </label>
              </>
            ) : null}
            {maskAsset ? (
              <button className="mask-chip" type="button" onClick={() => setMaskAsset(null)} title="Clear edit mask">
                {maskAsset.preview_url ? <img src={maskAsset.preview_url} alt="" aria-hidden="true" /> : <Box size={14} />}
                <span>Mask {maskAsset.title}</span>
                <XCircle size={14} />
              </button>
            ) : null}
            <button className="secondary-button remix-button" type="button" onClick={handlePromptRemix} disabled={remixBusy}>
              {remixBusy ? <RefreshCw className="spin" size={16} /> : <Sparkles size={16} />}
              Brief remix
            </button>
            <button className="primary-button" type="submit" disabled={busy}>
              {busy ? <RefreshCw className="spin" size={18} /> : <Wand2 size={18} />}
              {primaryActionLabel}
            </button>
          </div>
        </form>
      </main>

      <aside className="context-panel" aria-label="Review and settings">
        <section
          className="context-section model-summary"
          data-tour-id="model-settings"
          data-tour-active={tourActive("model-settings")}
        >
          <div className="section-title">
            <p className="eyebrow">Settings</p>
            <h3>Model & output</h3>
          </div>
          <div className="selected-model-summary">
            <span>
              <strong>{selectedModel?.short_label ?? selectedModel?.label ?? "Model pending"}</strong>
              <small>
                {settings.aspect_ratio} / {settings.image_size} / {settings.count} pick{settings.count === 1 ? "" : "s"}
              </small>
            </span>
            <em>{selectedModel?.badge ?? "Ready"}</em>
          </div>
          <button
            className="secondary-button handoff-button"
            type="button"
            aria-controls="model-settings-drawer"
            aria-expanded={settingsOpen}
            onClick={() => setSettingsOpen((current) => !current)}
          >
            {settingsOpen ? <XCircle size={16} /> : <Cpu size={16} />}
            {settingsOpen ? "Hide model settings" : "Change model"}
          </button>
          {settingsOpen ? (
            <div
              id="model-settings-drawer"
              className="settings-drawer"
              aria-label="Model and output settings"
              data-tour-id="model-settings-drawer"
              data-tour-active={tourActive("model-settings-drawer")}
            >
              <div className="drawer-toolbar settings-drawer-toolbar">
                <span>
                  <strong>Model choices</strong>
                  <small>Pick provider, size, refs, and brand mode.</small>
                </span>
                <button className="mini-button drawer-close-button" type="button" onClick={() => setSettingsOpen(false)}>
                  <XCircle size={14} />
                  Done
                </button>
              </div>
              <div className="model-list compact">
                {config.models.map((model) => (
                  <button
                    className={`model-card ${selectedModelId === model.id ? "selected" : ""}`}
                    key={model.id}
                    type="button"
                    onClick={() => setSelectedModelId(model.id)}
                  >
                    <span>
                      <strong>{model.short_label ?? model.label}</strong>
                      <small>{model.provider} / {model.cost_label}</small>
                    </span>
                    <em>{model.badge}</em>
                  </button>
                ))}
              </div>
              <div className="setting-row" data-tour-id="model-output-controls" data-tour-active={tourActive("model-output-controls")}>
                <label>
                  Aspect
                  <select
                    value={settings.aspect_ratio}
                    onChange={(event) => setSettings((current) => ({ ...current, aspect_ratio: event.target.value }))}
                  >
                    {modelOptions.allowedAspectRatios.map((ratio) => (
                      <option key={ratio}>{ratio}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Size
                  <select
                    value={settings.image_size}
                    onChange={(event) => setSettings((current) => ({ ...current, image_size: event.target.value }))}
                  >
                    {modelOptions.allowedImageSizes.map((size) => (
                      <option key={size}>{size}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Count
                  <input
                    min={1}
                    max={4}
                    type="number"
                    value={settings.count}
                    onChange={(event) => setSettings((current) => ({ ...current, count: Number(event.target.value) }))}
                  />
                </label>
              </div>
              <div className="capability-strip">
                <span>{modelOptions.resolutionBadge}</span>
                <span>{modelOptions.canEdit ? "Edits" : "Generate only"}</span>
                <span>{modelOptions.referenceLimit} refs</span>
              </div>
              <div className="context-toggle-row" data-tour-id="frank-mode-toggle" data-tour-active={tourActive("frank-mode-toggle")}>
                <span>
                  <strong>Frank Body Mode</strong>
                  <small>{frankBodyMode ? "Brand guidance on" : "Prompt only"}</small>
                </span>
                <button
                  className={`toggle-button ${frankBodyMode ? "on" : ""}`}
                  type="button"
                  aria-pressed={frankBodyMode}
                  onClick={() => setFrankBodyMode((current) => !current)}
                >
                  <span />
                </button>
              </div>
            </div>
          ) : null}
        </section>

        <section
          className="context-section selected-output"
          data-tour-id="review-panel"
          data-tour-active={tourActive("review-panel")}
        >
          <div className="section-title">
            <p className="eyebrow">Review</p>
            <h3>{selectedAsset ? selectedAsset.title : "Select a pick"}</h3>
          </div>
          {selectedAsset ? (
            <>
              <div className="preview-slot">
                <button type="button" onClick={() => setLightboxAsset(selectedAsset)} aria-label="Open selected asset">
                  <AssetPreviewMedia asset={selectedAsset} fallbackIconSize={30} />
                </button>
              </div>
              <div className="approval-actions" data-tour-id="review-actions" data-tour-active={tourActive("review-actions")}>
                <button type="button" onClick={() => toggleFavorite(selectedAsset)}>
                  <Heart size={15} />
                  {selectedAsset.favorite ? "Favorited" : "Favorite"}
                </button>
                <button type="button" onClick={() => changeAssetStatus(selectedAsset, "approved")}>
                  <CheckCircle2 size={15} />
                  Approve
                </button>
                <button type="button" onClick={() => changeAssetStatus(selectedAsset, "rejected")}>
                  <XCircle size={15} />
                  Reject
                </button>
              </div>
              {selectedAssetMetadata ? (
                <div
                  className="review-metadata"
                  aria-label="Selected asset metadata"
                  data-tour-id="review-metadata"
                  data-tour-active={tourActive("review-metadata")}
                >
                  <div className="review-metadata-heading">
                    <p className="eyebrow">Provenance</p>
                    <h4>Run metadata</h4>
                  </div>
                  <dl>
                    <div>
                      <dt>Model</dt>
                      <dd>{selectedAssetMetadata.modelLabel}</dd>
                    </div>
                    {selectedAssetMetadata.settingsLabel ? (
                      <div>
                        <dt>Settings</dt>
                        <dd>{selectedAssetMetadata.settingsLabel}</dd>
                      </div>
                    ) : null}
                    {selectedAssetMetadata.dimensionsLabel ? (
                      <div>
                        <dt>Size</dt>
                        <dd>{selectedAssetMetadata.dimensionsLabel}</dd>
                      </div>
                    ) : null}
                    {selectedAssetMetadata.sourceLabel ? (
                      <div>
                        <dt>Source</dt>
                        <dd>{selectedAssetMetadata.sourceLabel}</dd>
                      </div>
                    ) : null}
                    {selectedAssetMetadata.workflowLabel ? (
                      <div>
                        <dt>Workflow</dt>
                        <dd>{selectedAssetMetadata.workflowLabel}</dd>
                      </div>
                    ) : null}
                    <div>
                      <dt>Refs</dt>
                      <dd>{selectedAssetMetadata.referenceLabel}</dd>
                    </div>
                  </dl>
                  {selectedAssetMetadata.prompt ? <p>{selectedAssetMetadata.prompt}</p> : null}
                </div>
              ) : null}
              {selectedAsset.kind !== "reference" ? (
                <button
                  className={`secondary-button compare-button ${compareBaseAsset?.id === selectedAsset.id ? "active" : ""}`}
                  type="button"
                  onClick={() => startCompare(selectedAsset)}
                  disabled={outputAssets.length < 2}
                >
                  <Layers3 size={16} />
                  {compareBaseAsset?.id === selectedAsset.id ? "Pick another image" : "Compare picks"}
                </button>
              ) : null}
              {selectedAsset.kind !== "reference" ? (
                <div
                  className="round-starter-list"
                  aria-label="Make another round"
                  data-tour-id="variant-controls"
                  data-tour-active={tourActive("variant-controls")}
                >
                  <button type="button" onClick={() => makeAnotherRound(selectedAsset, "similar")}>
                    <RefreshCw size={15} />
                    More like this
                  </button>
                  <button type="button" onClick={() => makeAnotherRound(selectedAsset, "cleanup")}>
                    <CheckCircle2 size={15} />
                    Clean it up
                  </button>
                  <button type="button" onClick={() => makeAnotherRound(selectedAsset, "campaign")}>
                    <Sparkles size={15} />
                    Campaign remix
                  </button>
                </div>
              ) : null}
              <label className="review-notes">
                <span>Review notes</span>
                <textarea
                  value={assetNotesDraft}
                  onChange={(event) => setAssetNotesDraft(event.target.value)}
                  placeholder="Leave the next-round direction here."
                />
              </label>
              <button className="secondary-button" type="button" onClick={() => saveAssetNotes(selectedAsset)}>
                <CheckCircle2 size={16} />
                Save note
              </button>
              <div className="review-tool-list" data-tour-id="edit-controls" data-tour-active={tourActive("edit-controls")}>
                {selectedAsset.kind !== "reference" ? (
                  <button className="secondary-button" type="button" onClick={() => copyRunBrief(selectedAsset)}>
                    <Clipboard size={16} />
                    Copy run brief
                  </button>
                ) : null}
                {selectedAsset.kind !== "reference" ? (
                  <button className="secondary-button" type="button" onClick={() => downloadWorkflowJson(selectedAsset)}>
                    <Download size={16} />
                    Download workflow JSON
                  </button>
                ) : null}
                {selectedAsset.kind !== "reference" ? (
                  <button className="secondary-button" type="button" onClick={() => openAssetInComfyCanvas(selectedAsset)}>
                    <GitBranch size={16} />
                    Open in Comfy Canvas
                  </button>
                ) : null}
                <button className="secondary-button" type="button" onClick={() => startEditFromAsset(selectedAsset)}>
                  <Sparkles size={16} />
                  Edit with selected model
                </button>
                {selectedAsset.kind !== "reference" && selectedAsset.media_type !== "video" && selectedModel?.capabilities.masked_edit ? (
                  <button className="secondary-button" type="button" onClick={() => startMaskPainter(selectedAsset)}>
                    <Paintbrush size={16} />
                    Paint edit mask
                  </button>
                ) : null}
                {selectedAsset.kind !== "reference" && selectedAsset.media_type !== "video" ? (
                  <button className="secondary-button" type="button" onClick={() => useAssetAsReference(selectedAsset)}>
                    <Paperclip size={16} />
                    Use as reference
                  </button>
                ) : null}
              </div>
              <div className="review-export-list" data-tour-id="export-controls" data-tour-active={tourActive("export-controls")}>
                <button className="secondary-button" type="button" onClick={() => openStudioLink(assetDownloadUrl(selectedAsset.id), "Selected asset")}>
                  <Download size={16} />
                  Download original
                </button>
                <button className="secondary-button danger-button" type="button" onClick={() => removeAssetFromSession(selectedAsset)}>
                  <XCircle size={16} />
                  Remove from session
                </button>
                {selectedAsset.kind !== "reference" && selectedAsset.media_type !== "video" && selectedExportPresets.length > 1 ? (
                  <button className="secondary-button channel-set-button" type="button" onClick={() => exportChannelSet(selectedAsset)}>
                    <Download size={16} />
                    Export channel set
                  </button>
                ) : null}
                <div className="export-list">
                  {selectedExportPresets.map((preset) => (
                    <button key={preset.key} type="button" onClick={() => exportAsset(selectedAsset, preset)}>
                      <span>
                        <strong>{preset.label}</strong>
                        <small>{preset.size}</small>
                      </span>
                      <Download size={15} />
                    </button>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="empty-panel">
              <ImageIcon size={28} />
              <span>Click an output to approve, edit, or export it.</span>
            </div>
          )}
        </section>

        {showHandoffPanel ? (
          <section className="context-section handoff-section" data-tour-id="handoff-pack" data-tour-active={tourActive("handoff-pack")}>
            <div className="section-title">
              <p className="eyebrow">Export</p>
              <h3>Cliff Pack</h3>
            </div>
            <p>
              Package approved images, motion boards, notes, prompts, settings, references, sync-ready metadata, and {imageExportPresetCount}{" "}
              channel-ready exports per approved image into one ZIP.
            </p>
            <div className="handoff-stats" aria-label="Handoff package status">
              <span>
                <strong>{approvedCount}</strong>
                approved
              </span>
              {approvedMotionCount ? (
                <span>
                  <strong>{approvedMotionCount}</strong>
                  motion
                </span>
              ) : null}
              <span>
                <strong>{referenceAssets.length}</strong>
                refs
              </span>
            </div>
            <p className="handoff-proof">{handoffProofText || `${imageExportPresetCount} channel-ready exports per approved image`}</p>
            <button
              className="secondary-button handoff-button"
              type="button"
              onClick={exportSessionHandoff}
              disabled={!activeSession || approvedCount === 0 || handoffBusy}
            >
              {handoffBusy ? <RefreshCw className="spin" size={16} /> : <Download size={16} />}
              Export Cliff Pack
            </button>
            <button
              className="secondary-button handoff-button"
              type="button"
              onClick={openSessionReviewBoard}
              disabled={!activeSession || approvedCount === 0}
            >
              <ImageIcon size={16} />
              Open review board
            </button>
            <button
              className="secondary-button handoff-button"
              type="button"
              onClick={openSessionSyncManifest}
              disabled={!activeSession}
            >
              <GitBranch size={16} />
              Open sync manifest
            </button>
          </section>
        ) : null}

        {recentExports.length ? (
          <section className="context-section recent-exports-section">
            <div className="section-title">
              <p className="eyebrow">Handoff trail</p>
              <h3>Recent exports</h3>
            </div>
            <div className="recent-export-list">
              {recentExports.map((record) => (
                <button key={record.id} type="button" onClick={() => openStudioLink(record.download_url || exportDownloadUrl(record.id), "Export pack")}>
                  <span>
                    <strong>{exportRecordLabel(record, config.exportPresets)}</strong>
                    <small>{exportRecordMeta(record, assets)}</small>
                  </span>
                  <Download size={15} />
                </button>
              ))}
            </div>
          </section>
        ) : null}

        <div className="status-strip">
          <span>{statusText}</span>
          {statusReadyLink ? (
            <button type="button" onClick={() => openStudioLink(statusReadyLink.url, statusReadyLink.label)}>
              <ExternalLink size={13} />
              Try {statusReadyLink.label} link
            </button>
          ) : null}
          {statusReadyLink ? (
            <button type="button" onClick={() => copyStudioLink(statusReadyLink.url, statusReadyLink.label)}>
              <Clipboard size={13} />
              Copy {statusReadyLink.label} link
            </button>
          ) : null}
          <span className={`connection-pill ${connection}`}>
            <span />
            {connection === "online" ? "Comfy connected" : connection === "checking" ? "Checking Comfy" : "Comfy offline"}
          </span>
        </div>
      </aside>

      {advancedOpen ? (
      <aside
        id="advanced-tools-drawer"
        className="control-panel advanced-drawer"
        aria-label="Advanced tools"
        data-tour-id="advanced-tools"
        data-tour-active={tourActive("advanced-tools")}
      >
        <div className="drawer-toolbar advanced-drawer-toolbar">
          <span>
            <strong>Advanced tools</strong>
            <small>Setup, diagnostics, Comfy, and call-day receipts.</small>
          </span>
          <button className="mini-button drawer-close-button" type="button" onClick={() => setAdvancedOpen(false)}>
            <XCircle size={14} />
            Close
          </button>
        </div>
        <section className="control-section advanced-map-section">
          <div className="section-title">
            <p className="eyebrow">Advanced</p>
            <h3>Workflow Map</h3>
          </div>
          <p>Power-user route for the Frank-branded flow map and raw Comfy canvas.</p>
          <div className="provider-action-row">
            <button
              className="mini-button provider-check-button"
              type="button"
              aria-label="Advanced Graph Workflow Map"
              onClick={showGraph}
            >
              <GitBranch size={14} />
              Workflow Map
            </button>
            <button
              className="mini-button provider-check-button"
              type="button"
              onClick={() => openStudioLink(config.advancedGraphUrl, "Raw Comfy canvas")}
            >
              <ExternalLink size={14} />
              Raw Comfy
            </button>
          </div>
        </section>

        <section className="control-section">
          <div className="section-title">
            <p className="eyebrow">Session</p>
            <h3>Current session</h3>
          </div>
          <p>{activeSession?.name ?? "No active session"}</p>
          <button className="secondary-button danger-button" type="button" onClick={clearCurrentSession} disabled={!activeSession}>
            <XCircle size={16} />
            Clear
          </button>
        </section>

        <section className="control-section project-brief-section" aria-label="Project brief">
          <div className="section-title">
            <p className="eyebrow">Job jacket</p>
            <h3>Project brief</h3>
          </div>
          <label>
            <span>Project name</span>
            <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
          </label>
          <label>
            <span>Product name</span>
            <input
              value={briefDraft.productName}
              onChange={(event) => setBriefDraft((current) => ({ ...current, productName: event.target.value }))}
            />
          </label>
          <label>
            <span>Brief channel</span>
            <input
              value={briefDraft.channel}
              onChange={(event) => setBriefDraft((current) => ({ ...current, channel: event.target.value }))}
            />
          </label>
          <label>
            <span>Brief prompt</span>
            <textarea
              value={briefDraft.prompt}
              onChange={(event) => setBriefDraft((current) => ({ ...current, prompt: event.target.value }))}
            />
          </label>
          <label>
            <span>Negative guardrails</span>
            <textarea
              value={briefDraft.negativePrompt}
              onChange={(event) => setBriefDraft((current) => ({ ...current, negativePrompt: event.target.value }))}
            />
          </label>
          <button className="mini-button provider-check-button" type="button" onClick={saveProjectBrief} disabled={briefBusy || !activeSession}>
            {briefBusy ? <RefreshCw className="spin" size={14} /> : <CheckCircle2 size={14} />}
            Save Brief
          </button>
        </section>

        <section className="control-section">
          <div className="section-title">
            <p className="eyebrow">Provider</p>
            <h3>Generation Model</h3>
          </div>
          <div className="model-list">
            {config.models.map((model) => (
              <button
                className={`model-card ${selectedModelId === model.id ? "selected" : ""}`}
                key={model.id}
                type="button"
                onClick={() => setSelectedModelId(model.id)}
              >
                <span>
                  <strong>{model.short_label ?? model.label}</strong>
                  <small title={missingKeyTitle(model)}>
                    {model.provider} / {model.cost_label}
                    {missingKeyCopy(model)}
                  </small>
                </span>
                <em>{model.badge}</em>
              </button>
            ))}
          </div>
        </section>

        <section className="control-section launch-readiness" aria-label="Cliff call readiness">
          <div className="section-title">
            <p className="eyebrow">Call Ready</p>
            <h3>{demoDoctor?.headline ?? "Cliff Call Readiness"}</h3>
          </div>
          <div className="launch-readiness-grid">
            {launchReadinessItems.map((item) => (
              <div className={`launch-readiness-item ${item.status}`} key={item.key}>
                <span>{item.badge}</span>
                <div>
                  <strong>{item.label}</strong>
                  <small>{item.detail}</small>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="control-section provider-setup">
          <div className="section-title">
            <p className="eyebrow">Provider Setup</p>
            <h3>Server keys</h3>
          </div>
          {providerReadiness ? (
            <strong>
              {providerReadiness.summary.readyModels} / {providerReadiness.summary.modelCount} provider models ready
            </strong>
          ) : null}
          <strong>
            {providerSetupState.waitingModels.length
              ? `${providerSetupState.waitingModels.length} models waiting on server keys`
              : "All provider keys ready"}
          </strong>
          {activationChecklist ? <small>{activationChecklistInlineStatus(activationChecklist)}</small> : null}
          {providerSetupState.envVars.length ? (
            <div className="provider-key-list" aria-label="Missing provider environment variables">
              {providerSetupState.envVars.map((envVar) => (
                <code key={envVar}>{envVar}</code>
              ))}
            </div>
          ) : (
            <p>Provider proxy is ready for API rounds.</p>
          )}
          <div className="provider-env-box">
            <span>Server key file</span>
            <code>{providerEnvStatus?.filePath ?? "user\\frank_create\\provider_keys.env"}</code>
            <small>{providerEnvStatus?.fileExists ? "File ready. Edit it locally, then reload." : "Create the ignored template first."}</small>
          </div>
          <div className="provider-unlock-plan" aria-label="Provider unlock plan">
            <div className="provider-unlock-heading">
              <span>Cliff key order</span>
              <small>Gemini, Replicate, OpenAI only.</small>
            </div>
            {providerUnlockRows.length ? (
              providerUnlockRows.map((row, index) => (
                <div className="provider-unlock-row" key={row.id}>
                  <em>{index + 1}</em>
                  <div>
                    <strong>{row.label}</strong>
                    <small>{row.keyCopy}</small>
                  </div>
                  <span>{row.capabilityCopy}</span>
                </div>
              ))
            ) : (
              <div className="provider-unlock-row">
                <em>OK</em>
                <div>
                  <strong>All visible provider rows are unlocked.</strong>
                  <small>No extra API providers are part of this demo.</small>
                </div>
                <span>Local demo remains available without paid keys.</span>
              </div>
            )}
          </div>
          {activationChecklist ? (
            <div className={`activation-checklist ${activationChecklist.status}`} aria-label="Production activation checklist">
              <div className="activation-checklist-heading">
                <span>Production unlock checklist</span>
                <small>
                  {activationChecklist.summary.ready_provider_models} / {activationModelTotal(activationChecklist)} live model paths unlocked
                </small>
              </div>
              {activationChecklist.steps.map((step) => (
                <div className={`activation-step ${step.status}`} key={step.key}>
                  <span>{activationStatusIcon(step.status)}</span>
                  <div>
                    <strong>{step.label}</strong>
                    <small>{step.detail}</small>
                    <em>{step.action}</em>
                    {step.env_vars?.length ? (
                      <div className="provider-key-list compact">
                        {step.env_vars.slice(0, 5).map((envVar) => (
                          <code key={envVar}>{envVar}</code>
                        ))}
                      </div>
                    ) : null}
                    {step.path ? <code className="activation-path">{activationPathLabel(step.path)}</code> : null}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          {providerKeyEnvVars.length ? (
            <form
              className="provider-key-editor"
              aria-label="Save server provider keys"
              onSubmit={(event) => {
                event.preventDefault();
                if (!providerEnvBusy && providerKeyDraftHasValues) {
                  void saveServerKeys();
                }
              }}
            >
              <small>Paste rotated keys here to save them server-side. Values clear after save.</small>
              {providerKeyEnvVars.map((envVar) => (
                <label key={envVar}>
                  <span>{envVar}</span>
                  <input
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    value={providerKeyDraft[envVar] ?? ""}
                    onChange={(event) => updateProviderKeyDraft(envVar, event.target.value)}
                    placeholder="paste key"
                  />
                </label>
              ))}
              <button
                className="mini-button provider-check-button"
                type="submit"
                disabled={providerEnvBusy || !providerKeyDraftHasValues}
              >
                {providerEnvBusy ? <RefreshCw className="spin" size={14} /> : <CheckCircle2 size={14} />}
                Save server keys
              </button>
            </form>
          ) : null}
          <div className="provider-action-row">
            <button className="mini-button provider-check-button" type="button" onClick={checkProviderReadiness} disabled={checkingProviders}>
              {checkingProviders ? <RefreshCw className="spin" size={14} /> : <CheckCircle2 size={14} />}
              Check server keys
            </button>
            <button
              className="mini-button provider-check-button"
              type="button"
              onClick={checkSelectedModelPreflight}
              disabled={checkingProviderPreflight}
            >
              {checkingProviderPreflight ? <RefreshCw className="spin" size={14} /> : <Cpu size={14} />}
              Check selected model
            </button>
            <button
              className="mini-button provider-check-button"
              type="button"
              onClick={checkProviderAdapterAudit}
              disabled={checkingProviderAudit}
            >
              {checkingProviderAudit ? <RefreshCw className="spin" size={14} /> : <GitBranch size={14} />}
              Audit roster
            </button>
            <button
              className="mini-button provider-check-button"
              type="button"
              onClick={saveProviderReadinessReceipt}
              disabled={connection !== "online" || savingProviderReceipt}
            >
              {savingProviderReceipt ? <RefreshCw className="spin" size={14} /> : <Download size={14} />}
              Save receipt
            </button>
            <button className="mini-button provider-check-button" type="button" onClick={copyProviderKeyPlan}>
              <Clipboard size={14} />
              Copy key plan
            </button>
            <button className="mini-button provider-check-button" type="button" onClick={copyProductionUnlockPlan} disabled={!activationChecklist}>
              <Clipboard size={14} />
              Copy unlock plan
            </button>
            <button className="mini-button provider-check-button" type="button" onClick={createServerKeyFile} disabled={providerEnvBusy}>
              {providerEnvBusy ? <RefreshCw className="spin" size={14} /> : <Paperclip size={14} />}
              Create key file
            </button>
            <button className="mini-button provider-check-button" type="button" onClick={reloadServerKeys} disabled={providerEnvBusy}>
              {providerEnvBusy ? <RefreshCw className="spin" size={14} /> : <RefreshCw size={14} />}
              Reload keys
            </button>
          </div>
          {providerPreflight ? (
            <div className={`provider-preflight-card ${providerPreflight.status}`} aria-label="Selected model preflight">
              <strong>{providerPreflightStatusLabel(providerPreflight.status)}</strong>
              <small>{providerPreflight.message}</small>
              {providerPreflight.missing_env_vars.length ? (
                <div className="provider-key-list compact" aria-label="Selected model missing environment variables">
                  {providerPreflight.missing_env_vars.map((envVar) => (
                    <code key={envVar}>{envVar}</code>
                  ))}
                </div>
              ) : null}
              <dl>
                <div>
                  <dt>Mode</dt>
                  <dd>{titleize(providerPreflight.payloadPreview.kind)}</dd>
                </div>
                <div>
                  <dt>Refs</dt>
                  <dd>
                    {providerPreflight.payloadPreview.reference_count} / {providerPreflight.payloadPreview.reference_limit || "local"}
                  </dd>
                </div>
                <div>
                  <dt>Prompt</dt>
                  <dd>{providerPreflight.payloadPreview.prompt_length} chars</dd>
                </div>
              </dl>
              {providerPreflight.payloadPreview.prompt_preview ? <p>{providerPreflight.payloadPreview.prompt_preview}</p> : null}
            </div>
          ) : null}
          {providerAudit ? (
            <div className="provider-audit-card" aria-label="Provider adapter audit">
              <strong>No-spend adapter audit</strong>
              <small>
                {providerAudit.summary.runner_registered} / {providerAudit.summary.model_count} runners registered;
                {" "}
                {providerAudit.summary.waiting_for_key} waiting on keys;
                {" "}
                {providerAudit.summary.preview_failures} preview issues;
                {" "}
                {providerAudit.summary.operation_preview_count ?? 0} operation previews checked
                {providerAudit.summary.operation_preview_failures
                  ? ` / ${providerAudit.summary.operation_preview_failures} operation failures`
                  : ""}.
              </small>
              <div className="provider-audit-list">
                {providerAudit.models.slice(0, 8).map((model) => (
                  <div className={`provider-audit-row ${model.status}`} key={model.model_id}>
                    <span>{model.status === "ready" ? <CheckCircle2 size={13} /> : <Cpu size={13} />}</span>
                    <div>
                      <strong>{model.label}</strong>
                      <small>
                        {model.request_preview?.method ?? "n/a"} {model.provider}
                        {" / "}
                        {providerAuditOperationSummary(model.operation_kinds, model.request_previews)}
                        {model.missing_env_vars.length ? ` / needs ${model.missing_env_vars.join(" or ")}` : " / server-ready"}
                      </small>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {providerReceiptPath ? (
            <div className="demo-evidence-actions provider-receipt-actions">
              <small className="demo-evidence-path">Provider receipt: {providerReceiptPath}</small>
              {providerReceiptUrl ? (
                <button className="mini-button provider-check-button" type="button" onClick={() => openStudioLink(providerReceiptUrl, "Provider receipt")}>
                  <ExternalLink size={14} />
                  Open provider receipt
                </button>
              ) : null}
            </div>
          ) : null}
        </section>

        <section className={`control-section demo-doctor ${demoDoctor?.status ?? "idle"}`}>
          <div className="section-title">
            <p className="eyebrow">Preflight</p>
            <h3>Demo Doctor</h3>
          </div>
          <strong>{demoDoctor?.headline ?? "Check the room"}</strong>
          <p>
            {demoDoctor
              ? demoDoctorSummary(demoDoctor)
              : "Run this before the call to check the local demo path, provider keys, seeded assets, and Comfy shell."}
          </p>
          {demoDoctor ? (
            <div className="doctor-check-list" aria-label="Demo Doctor checks">
              {demoDoctor.checks.map((check) => (
                <div className={`doctor-check ${check.status}`} key={check.key}>
                  <span>{doctorStatusIcon(check.status)}</span>
                  <div>
                    <strong>{check.label}</strong>
                    <small>{check.detail}</small>
                    {check.action ? <em>{check.action}</em> : null}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          <div className="provider-action-row">
            <button className="mini-button provider-check-button" type="button" onClick={runDemoDoctor} disabled={checkingDemoDoctor}>
              {checkingDemoDoctor ? <RefreshCw className="spin" size={14} /> : <CheckCircle2 size={14} />}
              Run demo check
            </button>
            <button className="mini-button provider-check-button" type="button" onClick={resetDemoFromDoctor} disabled={connection !== "online" || resettingDemo}>
              {resettingDemo ? <RefreshCw className="spin" size={14} /> : <RefreshCw size={14} />}
              Reset demo
            </button>
            <button
              className="mini-button provider-check-button"
              type="button"
              onClick={saveDemoEvidence}
              disabled={connection !== "online" || savingDemoEvidence}
            >
              {savingDemoEvidence ? <RefreshCw className="spin" size={14} /> : <Download size={14} />}
              Save evidence
            </button>
            <button
              className="mini-button provider-check-button"
              type="button"
              onClick={saveCallBrief}
              disabled={connection !== "online" || savingCallBrief}
            >
              {savingCallBrief ? <RefreshCw className="spin" size={14} /> : <Download size={14} />}
              Call brief
            </button>
            <button
              className="mini-button provider-check-button"
              type="button"
              onClick={buildReadinessPack}
              disabled={connection !== "online" || buildingReadinessPack}
            >
              {buildingReadinessPack ? <RefreshCw className="spin" size={14} /> : <Download size={14} />}
              Build call pack
            </button>
          </div>
          {demoEvidencePath ? (
            <div className="demo-evidence-actions">
              <small className="demo-evidence-path">Latest receipt: {demoEvidencePath}</small>
              {demoEvidenceUrl ? (
                <button className="mini-button provider-check-button" type="button" onClick={() => openStudioLink(demoEvidenceUrl, "Latest receipt")}>
                  <ExternalLink size={14} />
                  Open latest receipt
              </button>
            ) : null}
          </div>
        ) : null}
          {callBriefPath ? (
            <div className="demo-evidence-actions">
              <small className="demo-evidence-path">Call brief: {callBriefPath}</small>
              {callDecision ? (
                <div className={`call-decision-card ${callDecision.can_present ? "ready" : "fail"}`} aria-label="Call-day decision">
                  <strong>Call decision: {callDecision.status}</strong>
                  <small>{callDecision.headline}</small>
                </div>
              ) : null}
              {callBriefUrl ? (
                <button className="mini-button provider-check-button" type="button" onClick={() => openStudioLink(callBriefUrl, "Call brief")}>
                  <ExternalLink size={14} />
                  Open call brief
                </button>
              ) : null}
            </div>
          ) : null}
          {activationChecklistPath ? (
            <div className="demo-evidence-actions">
              <small className="demo-evidence-path">Activation checklist: {activationChecklistPath}</small>
              {activationChecklistUrl ? (
                <button className="mini-button provider-check-button" type="button" onClick={() => openStudioLink(activationChecklistUrl, "Activation checklist")}>
                  <ExternalLink size={14} />
                  Open activation checklist
                </button>
              ) : null}
            </div>
          ) : null}
          {readinessPackPath ? (
            <div className="demo-evidence-actions">
              <small className="demo-evidence-path">Call pack: {readinessPackPath}</small>
              {readinessPackManifest ? (
                <div className={`readiness-pack-proof ${readinessPackManifest.missing_files.length ? "warning" : "ready"}`}>
                  <span>
                    <strong>{readinessPackManifest.includes.length}</strong>
                    proof files
                  </span>
                  <span>
                    <strong>{readinessPackManifest.screenshot_count}</strong>
                    screenshots
                  </span>
                  <span>
                    <strong>{readinessPackManifest.missing_files.length}</strong>
                    missing
                  </span>
                  <span>
                    <strong>{readinessPackManifest.cliff_pack?.status === "included" ? "yes" : "no"}</strong>
                    Cliff Pack
                  </span>
                  <span>
                    <strong>{readinessPackManifest.screenshot_capture?.status ?? "reused"}</strong>
                    QA capture
                  </span>
                  {readinessPackSha ? (
                    <span className="readiness-pack-sha">
                      <strong>Verified SHA-256</strong>
                      {readinessPackSha}
                    </span>
                  ) : null}
                  <p>
                    {readinessPackManifest.missing_files.length
                      ? `Missing: ${readinessPackManifest.missing_files.join(", ")}`
                      : readinessPackManifest.cliff_pack?.status === "included"
                        ? `Open evidence first. Handoff included with ${readinessPackManifest.cliff_pack.approved_asset_count ?? 0} approved.`
                        : `Open evidence first. Handoff not bundled: ${readinessPackManifest.cliff_pack?.detail ?? "no approved pack available."}`}
                  </p>
                </div>
              ) : readinessPackSha ? (
                <div className="readiness-pack-proof ready">
                  <span className="readiness-pack-sha">
                    <strong>Verified SHA-256</strong>
                    {readinessPackSha}
                  </span>
                </div>
              ) : null}
              {readinessPackUrl ? (
                <button className="mini-button provider-check-button" type="button" onClick={() => openStudioLink(readinessPackUrl, "Call pack")}>
                  <ExternalLink size={14} />
                  Download call pack
                </button>
              ) : null}
              {implementationManifestPath ? (
                <div className="demo-evidence-actions nested">
                  <small className="demo-evidence-path">Implementation manifest: {implementationManifestPath}</small>
                  {implementationManifestUrl ? (
                    <button
                      className="mini-button provider-check-button"
                      type="button"
                      onClick={() => openStudioLink(implementationManifestUrl, "Implementation manifest")}
                    >
                      <ExternalLink size={14} />
                      Open manifest
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}
          <div className="cliff-demo-guide" aria-label="Cliff demo guide" data-cliff-guide="true">
            <div className="cliff-guide-heading">
              <span>Cliff Run of Show</span>
              <strong>{demoDoctor?.readyForDemo ? "Ready, with receipts" : "Run Demo Doctor first"}</strong>
            </div>
            <div className="cliff-guide-steps">
              {cliffGuideSteps.map((step, index) => (
                <div className="cliff-guide-step" key={step.label}>
                  <span>{index + 1}</span>
                  <div>
                    <strong>{step.label}</strong>
                    <small>{step.detail}</small>
                  </div>
                  <em>{step.status}</em>
                </div>
              ))}
            </div>
            <div className="cliff-guide-proofs" aria-label="Cliff demo proof points">
              {cliffGuideProofs.map((proof) => (
                <span key={proof}>{proof}</span>
              ))}
            </div>
          </div>
        </section>

        <section className="control-section handoff-section">
          <div className="section-title">
            <p className="eyebrow">Handoff</p>
            <h3>Cliff Pack</h3>
          </div>
          <p>
            Package approved images, motion boards, notes, prompts, settings, references, sync-ready metadata, and {imageExportPresetCount}{" "}
            channel-ready exports per approved image into one ZIP.
          </p>
          <div className="handoff-stats" aria-label="Handoff package status">
            <span>
              <strong>{approvedCount}</strong>
              approved
            </span>
            {approvedMotionCount ? (
              <span>
                <strong>{approvedMotionCount}</strong>
                motion
              </span>
            ) : null}
            <span>
              <strong>{referenceAssets.length}</strong>
              refs
            </span>
          </div>
          <p className="handoff-proof">{handoffProofText || `${imageExportPresetCount} channel-ready exports per approved image`}</p>
          <button
            className="secondary-button handoff-button"
            type="button"
            onClick={exportSessionHandoff}
            disabled={!activeSession || approvedCount === 0 || handoffBusy}
          >
            {handoffBusy ? <RefreshCw className="spin" size={16} /> : <Download size={16} />}
            Export Cliff Pack
          </button>
          <button
            className="secondary-button handoff-button"
            type="button"
            onClick={openSessionReviewBoard}
            disabled={!activeSession || approvedCount === 0}
          >
            <ImageIcon size={16} />
            Open review board
          </button>
          <button
            className="secondary-button handoff-button"
            type="button"
            onClick={openSessionSyncManifest}
            disabled={!activeSession}
          >
            <GitBranch size={16} />
            Open sync manifest
          </button>
        </section>

        <section className="control-section recent-exports-section">
          <div className="section-title">
            <p className="eyebrow">Handoff trail</p>
            <h3>Recent exports</h3>
          </div>
          {recentExports.length ? (
            <div className="recent-export-list">
              {recentExports.map((record) => (
                <button key={record.id} type="button" onClick={() => openStudioLink(record.download_url || exportDownloadUrl(record.id), "Export pack")}>
                  <span>
                    <strong>{exportRecordLabel(record, config.exportPresets)}</strong>
                    <small>{exportRecordMeta(record, assets)}</small>
                  </span>
                  <Download size={15} />
                </button>
              ))}
            </div>
          ) : (
            <p className="empty-export-trail">No packs yet. Approve something hot, then export.</p>
          )}
        </section>

        <section className="control-section">
          <div className="setting-row">
            <label>
              Aspect
              <select
                value={settings.aspect_ratio}
                onChange={(event) => setSettings((current) => ({ ...current, aspect_ratio: event.target.value }))}
              >
                {modelOptions.allowedAspectRatios.map((ratio) => (
                  <option key={ratio}>{ratio}</option>
                ))}
              </select>
            </label>
            <label>
              Size
              <select
                value={settings.image_size}
                onChange={(event) => setSettings((current) => ({ ...current, image_size: event.target.value }))}
              >
                {modelOptions.allowedImageSizes.map((size) => (
                  <option key={size}>{size}</option>
                ))}
              </select>
            </label>
            <label>
              Count
              <input
                min={1}
                max={4}
                type="number"
                value={settings.count}
                onChange={(event) => setSettings((current) => ({ ...current, count: Number(event.target.value) }))}
              />
            </label>
          </div>
          <div className="capability-strip">
            <span>{modelOptions.resolutionBadge}</span>
            <span>{modelOptions.canEdit ? "Edits" : "Generate only"}</span>
            <span>{modelOptions.referenceLimit} refs</span>
          </div>
          {selectedModel?.provider === "local" ? (
            <div className="local-engine-note">
              <strong>{config.localEngine.diffusion_ready ? "Checkpoint diffusion ready" : "Frank renderer ready"}</strong>
              <span>
                {config.localEngine.note}
                {config.localEngine.diffusion_ready && config.localEngine.checkpoints.length
                  ? ` (${config.localEngine.checkpoints[0]})`
                  : ""}
              </span>
              <code>{config.localEngine.checkpoint_dir ?? "models\\checkpoints"}</code>
              {config.localEngine.setup_steps?.length ? (
                <ul className="local-engine-steps" aria-label="Local model setup steps">
                  {config.localEngine.setup_steps.slice(0, 3).map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ul>
              ) : null}
              {config.localEngine.ignored_checkpoints?.length ? (
                <div className="local-engine-ignored" aria-label="Ignored local checkpoint files">
                  <strong>Ignored incomplete checkpoint</strong>
                  {config.localEngine.ignored_checkpoints.slice(0, 3).map((checkpoint) => (
                    <span key={checkpoint.name}>
                      {checkpoint.name}
                      {checkpoint.reason ? ` / ${checkpoint.reason}` : ""}
                    </span>
                  ))}
                </div>
              ) : null}
              {config.localEngine.recommended_checkpoints?.length ? (
                <div className="local-engine-picks" aria-label="Starter local model picks">
                  {config.localEngine.recommended_checkpoints.slice(0, 2).map((pick) => (
                    <span key={`${pick.label}-${pick.folder}`}>
                      <b>{pick.label}</b>
                      {pick.use}
                    </span>
                  ))}
                </div>
              ) : null}
              {workflowBlueprints?.blueprints?.length ? (
                <div className="workflow-blueprints" aria-label="Comfy workflow blueprints">
                  <strong>Comfy workflow blueprints</strong>
                  <small>{workflowBlueprints.note}</small>
                  {workflowBlueprints.blueprints.map((blueprint) => (
                    <div className="workflow-blueprint-row" key={blueprint.key}>
                      <span>
                        <b>{blueprint.label}</b>
                        <em>{blueprint.node_types.join(" -> ")}</em>
                      </span>
                      <button
                        className="icon-button"
                        type="button"
                        aria-label={`Download ${blueprint.label} workflow JSON`}
                        title={`Download ${blueprint.label} workflow JSON`}
                        onClick={() => downloadWorkflowBlueprint(blueprint)}
                      >
                        <Download size={15} />
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
              <button className="mini-button provider-check-button" type="button" onClick={prepareLocalEngine} disabled={localEngineBusy}>
                {localEngineBusy ? <RefreshCw className="spin" size={14} /> : <Cpu size={14} />}
                Prepare model folders
              </button>
            </div>
          ) : null}
        </section>

        <section className="control-section toggle-section">
          <div>
            <h3>Frank Body Mode</h3>
            <p>Off sends only your prompt. On adds Frank style, preset structure, and negatives server-side.</p>
          </div>
          <button
            className={`toggle-button ${frankBodyMode ? "on" : ""}`}
            type="button"
            aria-pressed={frankBodyMode}
            onClick={() => setFrankBodyMode((current) => !current)}
          >
            <span />
          </button>
        </section>

        <section className="control-section brand-kit-section">
          <div className="section-title">
            <p className="eyebrow">Brand guidance</p>
            <h3>Brand Kit</h3>
          </div>
          <label className="brand-kit-field">
            <span>Style guidance</span>
            <textarea
              aria-label="Frank Brand Kit style guidance"
              value={brandKitDraft.style_guidance}
              onChange={(event) => setBrandKitDraft((current) => ({ ...current, style_guidance: event.target.value }))}
            />
          </label>
          <label className="brand-kit-field">
            <span>Negative guardrails</span>
            <textarea
              aria-label="Frank Brand Kit negative prompt"
              value={brandKitDraft.negative_prompt}
              onChange={(event) => setBrandKitDraft((current) => ({ ...current, negative_prompt: event.target.value }))}
            />
          </label>
          <label className="brand-kit-field">
            <span>Reference notes</span>
            <textarea
              aria-label="Frank Brand Kit reference notes"
              value={brandKitDraft.reference_notes}
              onChange={(event) => setBrandKitDraft((current) => ({ ...current, reference_notes: event.target.value }))}
            />
          </label>
          <div className="brand-kit-actions">
            <small>{brandKit.updated_at ? `Updated ${new Date(brandKit.updated_at).toLocaleString()}` : "Local guidance ready"}</small>
            <button className="mini-button provider-check-button" type="button" onClick={saveBrandKit} disabled={brandKitBusy}>
              {brandKitBusy ? <RefreshCw className="spin" size={14} /> : <CheckCircle2 size={14} />}
              Save Brand Kit
            </button>
            <button
              className="mini-button provider-check-button"
              type="button"
              onClick={saveBrandContextBrief}
              disabled={connection !== "online" || brandContextBusy}
            >
              {brandContextBusy ? <RefreshCw className="spin" size={14} /> : <Download size={14} />}
              Save context brief
            </button>
          </div>
          {brandContextPath ? (
            <div className="demo-evidence-actions brand-context-actions">
              <small className="demo-evidence-path">Brand context: {brandContextPath}</small>
              {brandContextUrl ? (
                <button className="mini-button provider-check-button" type="button" onClick={() => openStudioLink(brandContextUrl, "Brand context")}>
                  <ExternalLink size={14} />
                  Open context brief
                </button>
              ) : null}
            </div>
          ) : null}
        </section>

        <section className="control-section">
          <div className="section-title">
            <p className="eyebrow">Jobs</p>
            <h3>Product Image Lab</h3>
          </div>
          <div className="task-shortcut-list" aria-label="Product Image Lab task shortcuts">
            {productTaskShortcuts.map((task) => (
              <button
                className={selectedPresetKey === task.key ? "selected" : ""}
                key={task.key}
                type="button"
                onClick={() => selectTaskShortcut(task)}
              >
                <span className="task-shortcut-icon">{taskShortcutIcon(task.key)}</span>
                <span>
                  <strong>{task.label}</strong>
                  <small aria-hidden="true">{task.description}</small>
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="control-section">
          <div className="section-title">
            <p className="eyebrow">Presets</p>
            <h3>Brief shape</h3>
          </div>
          <div className="preset-list">
            {config.promptPresets.map((preset) => (
              <button
                className={selectedPresetKey === preset.key ? "selected" : ""}
                key={preset.key}
                type="button"
                onClick={() => selectPreset(preset)}
              >
                <strong>{preset.label}</strong>
                <span>{preset.description}</span>
              </button>
            ))}
          </div>
        </section>

      </aside>
      ) : null}

      {walkthroughOpen ? (
        <WalkthroughOverlay
          anchor={walkthroughAnchor}
          step={activeWalkthroughStep}
          stepIndex={walkthroughStep}
          stepCount={WALKTHROUGH_STEPS.length}
          onClose={() => setWalkthroughOpen(false)}
          onNext={() => {
            if (walkthroughStep === WALKTHROUGH_STEPS.length - 1) {
              setWalkthroughOpen(false);
            } else {
              setWalkthroughStep((current) => Math.min(current + 1, WALKTHROUGH_STEPS.length - 1));
            }
          }}
          onPrevious={() => setWalkthroughStep((current) => Math.max(current - 1, 0))}
        />
      ) : null}

      {lightboxAsset ? (
        <div className="lightbox" role="dialog" aria-modal="true" onClick={() => setLightboxAsset(null)}>
          <div className="lightbox-inner" onClick={(event) => event.stopPropagation()}>
            <button className="lightbox-close" type="button" onClick={() => setLightboxAsset(null)} aria-label="Close preview">
              <XCircle size={18} />
            </button>
            <AssetPreviewMedia asset={lightboxAsset} fallbackIconSize={42} controls />
            <div className="lightbox-actions">
              <button
                type="button"
                onClick={() => {
                  startEditFromAsset(lightboxAsset);
                  setLightboxAsset(null);
                }}
              >
                <Sparkles size={16} />
                Edit this
              </button>
              <button type="button" onClick={() => openStudioLink(assetDownloadUrl(lightboxAsset.id), "Lightbox asset")}>
                <Download size={16} />
                Save
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {maskPainterAsset ? (
        <MaskPainterDialog
          asset={maskPainterAsset}
          busy={maskPainterBusy}
          onClose={() => setMaskPainterAsset(null)}
          onSave={handlePaintedMaskSave}
        />
      ) : null}

      {compareBaseAsset && compareTargetAsset ? (
        <CompareDialog
          baseAsset={compareBaseAsset}
          targetAsset={compareTargetAsset}
          onClose={clearCompare}
          onApprove={(asset) => changeAssetStatus(asset, "approved")}
          onEdit={(asset) => {
            startEditFromAsset(asset);
            clearCompare();
          }}
        />
      ) : null}
    </div>
  );
}

function WalkthroughOverlay({
  anchor,
  step,
  stepIndex,
  stepCount,
  onClose,
  onNext,
  onPrevious
}: {
  anchor: WalkthroughAnchor | null;
  step: WalkthroughStep;
  stepIndex: number;
  stepCount: number;
  onClose: () => void;
  onNext: () => void;
  onPrevious: () => void;
}) {
  const isLastStep = stepIndex === stepCount - 1;

  return (
    <>
      <div className="walkthrough-scrim" aria-label="Walkthrough backdrop" />
      {anchor ? <div className="walkthrough-target-highlight" style={anchor.highlightStyle} aria-hidden="true" /> : null}
      <section
        className={`walkthrough-popover ${anchor?.placement === "above" ? "above" : "below"}`}
        role="dialog"
        aria-modal="true"
        aria-label="Demo Walkthrough guide"
        style={anchor?.popoverStyle}
      >
        <button className="walkthrough-close" type="button" onClick={onClose} aria-label="Close walkthrough">
          <XCircle size={18} />
        </button>
        <p className="eyebrow">Demo Walkthrough</p>
        <span className="walkthrough-step-count">
          Step {stepIndex + 1} of {stepCount}
        </span>
        <h2>{step.title}</h2>
        <p>{step.detail}</p>
        {step.points?.length ? (
          <ul className="walkthrough-points">
            {step.points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        ) : null}
        <div className="walkthrough-progress" aria-label="Walkthrough steps">
          {WALKTHROUGH_STEPS.map((item, index) => (
            <span className={index === stepIndex ? "active" : ""} key={item.title} aria-label={`Step ${index + 1}: ${item.title}`} />
          ))}
        </div>
        <div className="walkthrough-actions">
          <button className="secondary-button" type="button" onClick={onPrevious} disabled={stepIndex === 0}>
            Back
          </button>
          <button className="primary-button" type="button" onClick={onNext}>
            {isLastStep ? "Finish" : "Next"}
          </button>
        </div>
      </section>
    </>
  );
}

function measureWalkthroughAnchor(target: WalkthroughTarget): WalkthroughAnchor | null {
  if (typeof document === "undefined" || typeof window === "undefined") {
    return null;
  }

  const targetElement = document.querySelector<HTMLElement>(`[data-tour-id="${target}"]`);
  if (!targetElement) {
    return null;
  }

  const rect = targetElement.getBoundingClientRect();
  const viewportWidth = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
  const viewportHeight = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);
  const highlightPadding = 8;
  const popoverWidth = Math.min(460, Math.max(300, viewportWidth - 32));
  const popoverHeightEstimate = 360;
  const targetTop = clamp(rect.top - highlightPadding, 10, Math.max(10, viewportHeight - 40));
  const targetLeft = clamp(rect.left - highlightPadding, 10, Math.max(10, viewportWidth - 40));
  const targetWidth = Math.max(48, Math.min(rect.width + highlightPadding * 2, viewportWidth - 20));
  const targetHeight = Math.max(42, Math.min(rect.height + highlightPadding * 2, viewportHeight - 20));
  const targetCenter = targetLeft + targetWidth / 2;
  const preferredBelowTop = targetTop + targetHeight + 18;
  const hasRoomBelow = preferredBelowTop + popoverHeightEstimate < viewportHeight - 16;
  const popoverTop = hasRoomBelow ? preferredBelowTop : clamp(targetTop - popoverHeightEstimate - 18, 16, viewportHeight - popoverHeightEstimate - 16);
  const popoverLeft = clamp(targetCenter - popoverWidth / 2, 16, Math.max(16, viewportWidth - popoverWidth - 16));
  const arrowLeft = clamp(targetCenter - popoverLeft, 26, popoverWidth - 26);

  return {
    highlightStyle: {
      top: targetTop,
      left: targetLeft,
      width: targetWidth,
      height: targetHeight
    },
    popoverStyle: {
      top: popoverTop,
      left: popoverLeft,
      width: popoverWidth,
      "--walkthrough-arrow-left": `${arrowLeft}px`
    } as CSSProperties,
    placement: hasRoomBelow ? "below" : "above"
  };
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function CompareDialog({
  baseAsset,
  targetAsset,
  onClose,
  onApprove,
  onEdit
}: {
  baseAsset: Asset;
  targetAsset: Asset;
  onClose: () => void;
  onApprove: (asset: Asset) => void;
  onEdit: (asset: Asset) => void;
}) {
  return (
    <div className="compare-modal" role="dialog" aria-modal="true" aria-label="Compare picks">
      <div className="compare-modal-inner">
        <header className="compare-header">
          <div>
            <p className="eyebrow">Review</p>
            <h2>Compare picks</h2>
          </div>
          <button className="lightbox-close" type="button" onClick={onClose} aria-label="Close compare">
            <XCircle size={18} />
          </button>
        </header>
        <div className="compare-grid">
          <ComparePane label="Base pick" asset={baseAsset} onApprove={onApprove} onEdit={onEdit} />
          <ComparePane label="Challenger" asset={targetAsset} onApprove={onApprove} onEdit={onEdit} />
        </div>
      </div>
    </div>
  );
}

function ComparePane({
  label,
  asset,
  onApprove,
  onEdit
}: {
  label: string;
  asset: Asset;
  onApprove: (asset: Asset) => void;
  onEdit: (asset: Asset) => void;
}) {
  const settings = parseJsonRecord(asset.settings_json);
  const dimensions = asset.width && asset.height ? `${asset.width} x ${asset.height}` : "size pending";

  return (
    <section className="compare-pane">
      <div className="compare-image">
        <AssetPreviewMedia asset={asset} fallbackIconSize={38} />
      </div>
      <div className="compare-copy">
        <p className="eyebrow">{label}</p>
        <h3>{asset.title}</h3>
        <div className="compare-meta">
          <span>{assetStatusCopy(asset.approval_status)}</span>
          <span>{asset.model ?? "model pending"}</span>
          <span>{dimensions}</span>
          {settings.aspect_ratio ? <span>{String(settings.aspect_ratio)}</span> : null}
        </div>
        {asset.notes ? <p>{asset.notes}</p> : <p>No notes yet.</p>}
        <div className="compare-actions">
          <button type="button" onClick={() => onApprove(asset)}>
            <CheckCircle2 size={15} />
            Approve
          </button>
          <button type="button" onClick={() => onEdit(asset)}>
            <Sparkles size={15} />
            Edit
          </button>
        </div>
      </div>
    </section>
  );
}

function promptForTask(task: FrankTask) {
  const prompts: Record<string, string> = {
    "background-remove":
      "Background sweep: isolate the product cleanly for a transparent PNG and PDP-safe product cutout. Keep packaging edges sharp, shadows soft, and label details honest.",
    "background-replace":
      "Background glow-up: keep the product truthful, replace the set with a Frank Body pink/coffee lifestyle backdrop, and leave useful campaign negative space.",
    "product-cleanup":
      "Product polish: clean dust, label edges, smudges, and small lighting issues while keeping the packaging real and recognizable.",
    "campaign-variants":
      "Campaign remix: create a bolder Frank Body campaign direction from the same product truth, with cheeky attitude and room for headline copy.",
    "aspect-crops":
      "Crop the goods: prepare channel-ready PDP, email hero, Instagram feed/story, and paid social compositions without cutting off the product.",
    "upscale-enhance":
      "Make it bigger: produce a high-res master with crisp packaging, clean texture detail, and no over-sharpened plastic finish.",
    "prompt-remix":
      "Brief remix: rewrite this into sharper creative directions for the Art Dept., keeping the product truth, channel, mood, and Frank voice clear."
  };

  return prompts[task.key] ?? `${task.label}: ${task.description}`;
}

function settingsForTask(taskKey: string, current: StudioSettings, model?: StudioModel): StudioSettings {
  const next = { ...current };
  if (["background-remove", "upscale-enhance"].includes(taskKey)) {
    next.count = 1;
    next.image_size = supportedOption(model?.allowed_image_sizes, "4K", current.image_size);
  } else if (taskKey === "product-cleanup") {
    next.count = 2;
    next.image_size = supportedOption(model?.allowed_image_sizes, "4K", current.image_size);
  } else if (["background-replace", "campaign-variants", "aspect-crops"].includes(taskKey)) {
    next.count = 4;
    next.aspect_ratio = supportedOption(model?.allowed_aspect_ratios, "4:5", current.aspect_ratio);
  }
  return next;
}

function supportedOption(options: string[] | undefined, preferred: string, fallback: string) {
  if (options?.includes(preferred)) {
    return preferred;
  }
  return fallback;
}

function taskShortcutIcon(taskKey: string) {
  if (taskKey === "background-remove") {
    return <ImageIcon size={15} />;
  }
  if (taskKey === "background-replace" || taskKey === "campaign-variants") {
    return <Wand2 size={15} />;
  }
  if (taskKey === "product-cleanup" || taskKey === "upscale-enhance") {
    return <Sparkles size={15} />;
  }
  if (taskKey === "aspect-crops") {
    return <Layers3 size={15} />;
  }
  return <RefreshCw size={15} />;
}

function FrankGraphView({
  activeSession,
  assets,
  connection,
  rawGraphUrl,
  selectedModel,
  statusText,
  statusReadyLink,
  turns,
  onBack,
  onCopyLink,
  onOpenLink
}: {
  activeSession: StudioSession | null;
  assets: Asset[];
  connection: "checking" | "online" | "offline";
  rawGraphUrl: string;
  selectedModel?: StudioModel;
  statusText: string;
  statusReadyLink: ReturnType<typeof parseReadyStatusLink>;
  turns: StudioTurn[];
  onBack: () => void;
  onCopyLink: (url: string, label: string) => Promise<void>;
  onOpenLink: (url: string, label: string, openingText?: string) => Window | null;
}) {
  const motionAssetCount = assets.filter((asset) => asset.media_type === "video").length;
  const referenceAssetCount = assets.filter((asset) => asset.kind === "reference").length;
  const outputAssetCount = assets.filter((asset) => !["reference", "mask"].includes(asset.kind)).length;
  const approvedAssetCount = assets.filter((asset) => !["reference", "mask"].includes(asset.kind) && asset.approval_status === "approved").length;
  const reviewAssetCount = assets.filter((asset) => !["reference", "mask"].includes(asset.kind) && asset.approval_status === "review").length;
  const maskedEditAssetCount = assets.filter((asset) => {
    if (["reference", "mask"].includes(asset.kind)) {
      return false;
    }
    const settings = parseJsonRecord(asset.settings_json);
    const workflow = parseJsonRecord(settings.workflow_provenance);
    return workflow.workflow_key === "frank-local-masked-edit-renderer" || workflow.masked_edit === true;
  }).length;
  const activeSessionName = activeSession?.name ?? "New session";
  const sessionModeLabel = activeSession?.mode === "video" ? "Video Lab" : "Image Studio";
  const sessionSyncLabel = activeSession?.sync_status ?? "local";
  const graphNodes = [
    {
      key: "brief",
      step: "01",
      stage: "brief",
      tone: "pink",
      title: "The Brief",
      meta: activeSessionName,
      detail: "Product truth, channel, mood, and the part we do not mess with.",
      icon: <MessageSquareText size={18} />
    },
    {
      key: "references",
      step: "02",
      stage: "brief",
      tone: "coffee",
      title: "The Goods",
      meta: `${formatCount(referenceAssetCount, "ref")} / ${formatCount(outputAssetCount, "output")}`,
      detail: "Product refs, approved shots, texture scraps, and edit sources.",
      icon: <ImageIcon size={18} />
    },
    {
      key: "frank-mode",
      step: "03",
      stage: "make",
      tone: "cherry",
      title: "Frank Body Mode",
      meta: "Opt-in",
      detail: "Frank tone, soft pink, scrub texture, negatives, and preset structure.",
      icon: <Sparkles size={18} />
    },
    {
      key: "magic",
      step: "04",
      stage: "make",
      tone: "dark",
      title: "Make Magic",
      meta: selectedModel?.short_label ?? "Local Comfy",
      detail: "Comfy queue, provider proxy, model settings, and retry-friendly runs.",
      icon: <Cpu size={18} />
    },
    {
      key: "variants",
      step: "05",
      stage: "make",
      tone: "pink",
      title: "Variants",
      meta: `${turns.length} rounds`,
      detail: maskedEditAssetCount
        ? "Rounds, masked edits, favorites, and the hot little audit trail."
        : "Rounds, edits, favorites, and the hot little audit trail.",
      icon: <Layers3 size={18} />
    },
    {
      key: "review",
      step: "06",
      stage: "send",
      tone: "cherry",
      title: "Approved. Hot.",
      meta: `${approvedAssetCount} hot / ${reviewAssetCount} review`,
      detail: "Review states, notes, director-ready picks, and no mystery files.",
      icon: <CheckCircle2 size={18} />
    },
    {
      key: "export",
      step: "07",
      stage: "send",
      tone: "coffee",
      title: "Send It",
      meta: "PDP / social",
      detail: "Channel packs, prompt metadata, and sync-ready files for the next home.",
      icon: <Download size={18} />
    }
  ];
  const [selectedNodeKey, setSelectedNodeKey] = useState(graphNodes[3].key);
  const selectedNode = graphNodes.find((node) => node.key === selectedNodeKey) ?? graphNodes[3];

  const stageGroups = [
    {
      key: "brief",
      title: "Brief",
      helper: "What comes in",
      nodes: graphNodes.slice(0, 2)
    },
    {
      key: "make",
      title: "Make",
      helper: "Where Comfy and providers work",
      nodes: graphNodes.slice(2, 5)
    },
    {
      key: "send",
      title: "Review and export",
      helper: "What leaves the studio",
      nodes: graphNodes.slice(5)
    }
  ];

  return (
    <div className="graph-shell" data-frank-surface="workflow-map">
      <header className="graph-topbar">
        <button className="secondary-button graph-back" type="button" onClick={onBack}>
          <ArrowLeft size={17} />
          Back to Studio
        </button>
        <div className="graph-brand">
          <div className="brand-mark" aria-label="Frank Body">
            <span>frank</span>
            <span>body</span>
          </div>
          <div>
            <p className="eyebrow">Studio workflow map</p>
            <h1>Workflow Map</h1>
            <p className="graph-kicker">Real node graph lives in Comfy Canvas.</p>
          </div>
        </div>
        <button className="secondary-button graph-raw" type="button" onClick={() => onOpenLink(rawGraphUrl, "Raw Comfy canvas")}>
          <ExternalLink size={16} />
          Open Comfy Canvas
        </button>
      </header>
      <div className="status-strip graph-status-strip">
        <span>{statusText}</span>
        {statusReadyLink ? (
          <button type="button" onClick={() => onOpenLink(statusReadyLink.url, statusReadyLink.label)}>
            <ExternalLink size={13} />
            Try {statusReadyLink.label} link
          </button>
        ) : null}
        {statusReadyLink ? (
          <button type="button" onClick={() => onCopyLink(statusReadyLink.url, statusReadyLink.label)}>
            <Clipboard size={13} />
            Copy {statusReadyLink.label} link
          </button>
        ) : null}
      </div>

      <main className="graph-workspace">
        <section className="graph-canvas" aria-label="Frank Create workflow map">
          <div className="graph-canvas-heading">
            <p className="eyebrow">Frank Create</p>
            <h2>From brief to approved asset</h2>
            <p>Click a stage to see what it owns. Use the Comfy button when you need the raw node canvas.</p>
          </div>
          <div className="graph-flow" aria-label="Studio stages">
            {stageGroups.map((group) => (
              <section className="graph-stage-group" key={group.key} aria-label={`${group.title} stage`}>
                <div className="graph-stage-header">
                  <span>{group.helper}</span>
                  <h3>{group.title}</h3>
                </div>
                <div className="graph-stage-nodes">
                  {group.nodes.map((node) => (
                    <GraphNodeButton
                      key={node.key}
                      node={node}
                      selected={selectedNode.key === node.key}
                      onSelect={() => setSelectedNodeKey(node.key)}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
          <div className="graph-proof-strip" aria-label="Workflow receipts">
            <span>{referenceAssetCount} refs</span>
            <span>{turns.length} rounds</span>
            <span>{outputAssetCount} outputs</span>
            <span>{approvedAssetCount} approved</span>
            <span>{maskedEditAssetCount} masked edits</span>
            <span>{motionAssetCount} motion</span>
          </div>
        </section>

        <aside className="graph-inspector">
          <div className="graph-explainer">
            <p className="eyebrow">What this page is</p>
            <p>Use it to inspect the Frank Create flow without opening the raw Comfy node canvas.</p>
          </div>
          <div className="graph-selected-panel" aria-label="Selected workflow stage">
            <p className="graph-selected-step">Selected stage {selectedNode.step}</p>
            <h2>{selectedNode.title}</h2>
            <p>{selectedNode.detail}</p>
            <div className="graph-inspector-actions">
              <button className="primary-button" type="button" onClick={onBack}>
                <ArrowLeft size={16} />
                Use in Studio
              </button>
              <button className="secondary-button" type="button" onClick={() => onOpenLink(rawGraphUrl, "Raw Comfy canvas")}>
                <ExternalLink size={16} />
                Open Comfy Canvas
              </button>
            </div>
          </div>
          <div className="graph-stat-list">
            <span>
              <strong>{connection === "online" ? "Connected" : connection === "checking" ? "Checking" : "Offline"}</strong>
              Comfy
            </span>
            <span>
              <strong>{selectedModel?.badge ?? "Ready"}</strong>
              Model badge
            </span>
            <span>
              <strong>{turns.length}</strong>
              Rounds
            </span>
            <span>
              <strong>{outputAssetCount}</strong>
              Outputs
            </span>
            <span>
              <strong>{maskedEditAssetCount}</strong>
              Masked edits
            </span>
            <span>
              <strong>{motionAssetCount}</strong>
              Motion boards
            </span>
          </div>
          <div className="graph-job-jacket" aria-label="Workflow session summary">
            <span>
              <small>Session</small>
              <strong>{activeSessionName}</strong>
            </span>
            <span>
              <small>Surface</small>
              <strong>{sessionModeLabel}</strong>
            </span>
            <span>
              <small>Review</small>
              <strong>{approvedAssetCount} approved / {reviewAssetCount} review</strong>
            </span>
            <span>
              <small>Sync</small>
              <strong>{sessionSyncLabel}</strong>
            </span>
          </div>
          <div className="graph-mini-node">
            <Box size={18} />
            <span>
              {selectedModel?.short_label ?? "Local Comfy"} / {selectedModel?.provider ?? "local"}
            </span>
          </div>
        </aside>
      </main>
    </div>
  );
}

function GraphNodeButton({
  node,
  selected,
  onSelect
}: {
  node: { title: string; meta: string; detail: string; icon: JSX.Element; stage: string; step: string; tone: string };
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`graph-node graph-node-${node.tone} ${selected ? "selected" : ""}`}
      type="button"
      aria-label={`Inspect ${node.title}`}
      aria-pressed={selected}
      data-brand-stage={node.stage}
      data-brand-step={node.step}
      onClick={onSelect}
    >
      <span className="graph-node-step" aria-hidden="true">{node.step}</span>
      <span className="graph-node-icon">{node.icon}</span>
      <span className="graph-node-copy">
        <strong>{node.title}</strong>
        <small>{node.meta}</small>
        <p>{node.detail}</p>
      </span>
      <span className="graph-node-action">View details</span>
    </button>
  );
}

function formatCount(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function AssetPreviewMedia({
  asset,
  controls = false,
  fallbackIconSize = 24
}: {
  asset: Asset;
  controls?: boolean;
  fallbackIconSize?: number;
}) {
  if (!asset.preview_url) {
    return <ImageIcon size={fallbackIconSize} />;
  }

  if (isPlayableVideoAsset(asset)) {
    return (
      <video
        aria-label={asset.title}
        autoPlay={!controls}
        className="asset-preview-media"
        controls={controls}
        loop
        muted={!controls}
        playsInline
        preload="metadata"
        src={asset.preview_url}
      />
    );
  }

  return <img className="asset-preview-media" src={asset.preview_url} alt={asset.title} />;
}

function MaskPainterDialog({
  asset,
  busy,
  onClose,
  onSave
}: {
  asset: Asset;
  busy: boolean;
  onClose: () => void;
  onSave: (file: File) => void | Promise<void>;
}) {
  const imageRef = useRef<HTMLImageElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const paintingRef = useRef(false);
  const [brushSize, setBrushSize] = useState(54);
  const [canvasReady, setCanvasReady] = useState(false);
  const [hasMask, setHasMask] = useState(false);

  useEffect(() => {
    setBrushSize(54);
    setCanvasReady(false);
    setHasMask(false);
    paintingRef.current = false;
  }, [asset.id]);

  function prepareCanvas() {
    const image = imageRef.current;
    const canvas = canvasRef.current;
    if (!image || !canvas) {
      return;
    }

    canvas.width = image.naturalWidth || 1200;
    canvas.height = image.naturalHeight || 1200;
    canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    setCanvasReady(true);
    setHasMask(false);
  }

  function pointForEvent(event: ReactPointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas) {
      return null;
    }

    const rect = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * canvas.width,
      y: ((event.clientY - rect.top) / rect.height) * canvas.height
    };
  }

  function paintAt(event: ReactPointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    const point = pointForEvent(event);
    if (!canvas || !point) {
      return;
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = "rgba(196, 17, 47, 0.72)";
    ctx.beginPath();
    ctx.arc(point.x, point.y, brushSize, 0, Math.PI * 2);
    ctx.fill();
    setHasMask(true);
  }

  function startPainting(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (!canvasReady || busy) {
      return;
    }

    paintingRef.current = true;
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Synthetic browser-QA events do not always create an active pointer capture target.
    }
    paintAt(event);
  }

  function continuePainting(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (!paintingRef.current || busy) {
      return;
    }
    paintAt(event);
  }

  function stopPainting(event: ReactPointerEvent<HTMLCanvasElement>) {
    paintingRef.current = false;
    try {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    } catch {
      // Pointer capture can already be gone after synthetic or interrupted input.
    }
  }

  function clearMask() {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    setHasMask(false);
  }

  function saveMask() {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !hasMask) {
      return;
    }

    const output = document.createElement("canvas");
    output.width = canvas.width;
    output.height = canvas.height;
    const outputCtx = output.getContext("2d");
    if (!outputCtx) {
      return;
    }

    outputCtx.fillStyle = "#000000";
    outputCtx.fillRect(0, 0, output.width, output.height);
    const source = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const mask = outputCtx.getImageData(0, 0, output.width, output.height);
    for (let index = 0; index < source.data.length; index += 4) {
      if (source.data[index + 3] > 0) {
        mask.data[index] = 255;
        mask.data[index + 1] = 255;
        mask.data[index + 2] = 255;
        mask.data[index + 3] = 255;
      }
    }
    outputCtx.putImageData(mask, 0, 0);
    output.toBlob((blob) => {
      if (!blob) {
        return;
      }
      void onSave(new File([blob], `painted-mask-${asset.id}.png`, { type: "image/png" }));
    }, "image/png");
  }

  return (
    <div className="mask-painter-backdrop" role="dialog" aria-modal="true" aria-label="Paint edit mask" onClick={onClose}>
      <div className="mask-painter" onClick={(event) => event.stopPropagation()}>
        <div className="mask-painter-header">
          <div>
            <p className="eyebrow">Masked Edit</p>
            <h3>Paint the bits to change</h3>
            <span>{asset.title}</span>
          </div>
          <button className="lightbox-close" type="button" onClick={onClose} aria-label="Close mask painter">
            <XCircle size={18} />
          </button>
        </div>
        <div className="mask-painter-stage">
          {asset.preview_url ? <img ref={imageRef} src={asset.preview_url} alt="" onLoad={prepareCanvas} /> : <ImageIcon size={42} />}
          <canvas
            ref={canvasRef}
            aria-label="Painted edit mask"
            onPointerDown={startPainting}
            onPointerMove={continuePainting}
            onPointerUp={stopPainting}
            onPointerCancel={stopPainting}
          />
        </div>
        <div className="mask-painter-controls">
          <label>
            <span>Brush</span>
            <input
              type="range"
              min="12"
              max="140"
              step="2"
              value={brushSize}
              onChange={(event) => setBrushSize(Number(event.target.value))}
            />
          </label>
          <button className="secondary-button" type="button" onClick={clearMask} disabled={!hasMask || busy}>
            Clear
          </button>
          <button className="primary-button" type="button" onClick={saveMask} disabled={!hasMask || !canvasReady || busy}>
            {busy ? <RefreshCw className="spin" size={16} /> : <Paintbrush size={16} />}
            Use mask
          </button>
        </div>
      </div>
    </div>
  );
}

function isPlayableVideoAsset(asset: Asset) {
  if (asset.media_type !== "video") {
    return false;
  }
  const haystack = decodeURIComponent(`${asset.preview_url ?? ""} ${asset.file_path ?? ""}`).toLowerCase();
  return /\.(mp4|webm|mov|m4v)(?:$|[?#\s&])/.test(haystack) || /filename=[^&\s]+\.(mp4|webm|mov|m4v)/.test(haystack);
}

function OutputStrip({
  assets,
  emptyLabel = "Waiting for provider output",
  selectedAssetId,
  onSelect
}: {
  assets: Asset[];
  emptyLabel?: string;
  selectedAssetId?: string;
  onSelect: (asset: Asset) => void;
}) {
  if (!assets.length) {
    return (
      <div className="output-placeholder">
        <RefreshCw size={18} />
        {emptyLabel}
      </div>
    );
  }

  return (
    <div className="output-grid">
      {assets.map((asset) => (
        <button
          className={selectedAssetId === asset.id ? "selected" : ""}
          key={asset.id}
          type="button"
          onClick={() => onSelect(asset)}
        >
          <AssetPreviewMedia asset={asset} fallbackIconSize={24} />
          <span>{assetStatusCopy(asset.approval_status)}</span>
        </button>
      ))}
    </div>
  );
}

function mergeConfig(config: FrankConfig): FrankConfig {
  return {
    ...fallbackConfig,
    ...config,
    models: config.models?.length ? config.models : fallbackConfig.models,
    backlogModels: config.backlogModels ?? fallbackConfig.backlogModels,
    promptPresets: config.promptPresets?.length ? config.promptPresets : fallbackConfig.promptPresets,
    exportPresets: config.exportPresets?.length ? config.exportPresets : fallbackConfig.exportPresets,
    tasks: config.tasks?.length ? config.tasks : fallbackConfig.tasks,
    providers: config.providers?.length ? config.providers : fallbackConfig.providers,
    localEngine: { ...fallbackConfig.localEngine, ...config.localEngine },
    voice: { ...fallbackConfig.voice, ...config.voice }
  };
}

function makeBriefDraft(overrides: Partial<BriefFormState> = {}): BriefFormState {
  return {
    title: "",
    productName: "",
    taskType: "product-shot-lab",
    channel: "PDP / paid social",
    tone: "Cheeky but premium",
    prompt: "",
    negativePrompt: "",
    ...overrides
  };
}

function briefToDraft(brief: Brief): BriefFormState {
  return makeBriefDraft({
    title: brief.title ?? "",
    productName: brief.product_name ?? "",
    taskType: brief.task_type ?? "product-shot-lab",
    channel: brief.channel ?? "",
    tone: brief.tone ?? "",
    prompt: brief.prompt ?? "",
    negativePrompt: brief.negative_prompt ?? ""
  });
}

function exportPresetsForAsset(presets: ExportPreset[], asset: Asset) {
  const mediaType = asset.media_type ?? "image";
  return presets.filter((preset) => (preset.media_types ?? ["image"]).includes(mediaType));
}

function firstReviewableAsset(assets: Asset[]) {
  const outputAssets = assets.filter((asset) => !["reference", "mask"].includes(asset.kind));
  return outputAssets.find((asset) => (asset.media_type ?? "image") !== "video") ?? outputAssets[0] ?? null;
}

function filterExportsForAssets(records: ExportRecord[], assets: Asset[]) {
  const assetIds = new Set(assets.map((asset) => asset.id));
  return records.filter((record) => assetIds.has(record.asset_id));
}

function normalizeExportRecord(record: ExportRecord, fallback: Partial<ExportRecord>) {
  return {
    ...fallback,
    ...record,
    asset_id: record.asset_id ?? fallback.asset_id ?? "",
    preset: record.preset ?? fallback.preset ?? "export-pack",
    metadata_json: record.metadata_json ?? fallback.metadata_json ?? "{}",
    sync_status: record.sync_status ?? fallback.sync_status ?? "local",
    remote_id: record.remote_id ?? fallback.remote_id,
    created_at: record.created_at ?? new Date().toISOString()
  } as ExportRecord;
}

function exportRecordLabel(record: ExportRecord, presets: ExportPreset[]) {
  if (record.preset === "session-handoff") {
    return "Cliff Pack";
  }
  return presets.find((preset) => preset.key === record.preset)?.label ?? titleize(record.preset ?? "export-pack");
}

function exportRecordMeta(record: ExportRecord, assets: Asset[]) {
  const created = record.created_at ? new Date(record.created_at) : null;
  const createdLabel = created && !Number.isNaN(created.getTime()) ? created.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "saved";
  if (record.preset === "session-handoff") {
    const metadata = parseExportMetadata(record.metadata_json);
    const assetCount = Number(metadata.asset_count ?? metadata.approved_assets ?? 0);
    const referenceCount = Number(metadata.reference_count ?? metadata.references ?? 0);
    const videoCount = Number(metadata.video_count ?? metadata.approved_videos ?? 0);
    const parts = [
      `${assetCount} approved`,
      videoCount > 0 ? `${videoCount} motion` : null,
      `${referenceCount} refs`
    ].filter(Boolean);
    return `${parts.join(" / ")} / ${createdLabel}`;
  }
  const asset = assets.find((item) => item.id === record.asset_id);
  return `${asset?.title ?? "Export pack"} / ${createdLabel}`;
}

function parseExportMetadata(metadataJson?: string) {
  if (!metadataJson) {
    return {} as Record<string, unknown>;
  }
  try {
    const parsed = JSON.parse(metadataJson);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {} as Record<string, unknown>;
  }
}

function titleize(value: string) {
  return value
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function initialSurface() {
  if (typeof window === "undefined") {
    return "studio";
  }

  return window.location.pathname === "/graph" ? "graph" : "studio";
}

function initialStudioMode(): "image-studio" | "product-shot-lab" | "video-lab" | "approved-hot" {
  if (typeof window === "undefined") {
    return "image-studio";
  }

  const mode = new URLSearchParams(window.location.search).get("mode");
  return mode === "product-shot-lab" || mode === "video-lab" || mode === "approved-hot" ? mode : "image-studio";
}

function shouldAutoOpenProviderAudit() {
  if (typeof window === "undefined") {
    return false;
  }

  return new URLSearchParams(window.location.search).get("provider_audit") === "1";
}

function preferredStudioModel(models: StudioModel[]) {
  return (
    models.find((model) => model.id === "google-nb-pro" && model.configured !== false) ??
    models.find((model) => model.id === "frank-local-comfy") ??
    models[0] ??
    fallbackConfig.models[0]
  );
}

function modelName(config: FrankConfig, modelId: string) {
  return config.models.find((model) => model.id === modelId)?.short_label ?? modelId;
}

function selectedAssetReviewMetadata(asset: Asset, assets: Asset[], config: FrankConfig, turns: StudioTurn[]) {
  const turn = turns.find((item) => item.id === asset.turn_id);
  const settings = parseJsonRecord(asset.settings_json ?? turn?.settings_json);
  const workflow = parseJsonRecord(settings.workflow_provenance);
  const referenceIds = parseJsonList(asset.reference_asset_ids_json ?? turn?.reference_asset_ids_json);
  const model = config.models.find((item) => item.id === (asset.model ?? turn?.model));
  const provider = asset.provider ?? turn?.provider ?? model?.provider;
  const modelLabel = `${providerDisplayName(provider)} / ${model?.short_label ?? asset.model ?? turn?.model ?? "model pending"}`;
  const settingsLabel = settingsSummary(settings);
  const dimensionsLabel = asset.width && asset.height ? `${asset.width} x ${asset.height}` : "";
  const sourceId = asset.source_asset_id ?? turn?.source_asset_id;
  const sourceLabel = sourceId ? assets.find((item) => item.id === sourceId)?.title ?? sourceId : "";
  const referenceLabel = `${referenceIds.length} reference${referenceIds.length === 1 ? "" : "s"}`;
  const workflowLabel = workflowSummary(workflow);

  return {
    modelLabel,
    settingsLabel,
    dimensionsLabel,
    sourceLabel,
    workflowLabel,
    referenceLabel,
    prompt: asset.prompt ?? turn?.prompt ?? ""
  };
}

function selectedAssetRunBrief(asset: Asset, assets: Asset[], config: FrankConfig, turns: StudioTurn[]) {
  const turn = turns.find((item) => item.id === asset.turn_id);
  const metadata = selectedAssetReviewMetadata(asset, assets, config, turns);
  const workflowBridge = assetWorkflowBridge(asset, turns);
  const referenceIds = parseJsonList(asset.reference_asset_ids_json ?? turn?.reference_asset_ids_json);
  const referenceNames = referenceIds
    .map((id) => assets.find((item) => item.id === id)?.title ?? id)
    .filter(Boolean);
  const approval = asset.approval_status === "approved" ? "Approved" : titleize(asset.approval_status ?? "review");
  const status = `${approval}${asset.favorite ? " / favorite" : ""}`;
  const lines = [
    "Frank Create Run Brief",
    `Asset: ${asset.title}`,
    `Status: ${status}`,
    `Media: ${asset.media_type ?? "image"}`,
    metadata.modelLabel ? `Model: ${metadata.modelLabel}` : "",
    metadata.settingsLabel ? `Settings: ${metadata.settingsLabel}` : "",
    metadata.dimensionsLabel ? `Size: ${metadata.dimensionsLabel}` : "",
    metadata.workflowLabel ? `Workflow: ${metadata.workflowLabel}` : "",
    workflowBridge.raw_canvas_url ? `Raw Comfy: ${workflowBridge.raw_canvas_url}` : "",
    workflowBridge.workflow_receipt_url ? `Workflow receipt: ${workflowBridge.workflow_receipt_url}` : "",
    metadata.sourceLabel ? `Source: ${metadata.sourceLabel}` : "",
    `References: ${referenceNames.length ? referenceNames.join(", ") : metadata.referenceLabel}`,
    metadata.prompt ? `Prompt: ${metadata.prompt}` : "",
    asset.notes ? `Review notes: ${asset.notes}` : "",
    `Sync: ${asset.sync_status ?? "local"}`,
    asset.file_path ? `File: ${asset.file_path}` : "",
    turn?.id ? `Turn: ${turn.id}` : "",
    "Provider keys: server-side only; no secrets included."
  ];
  return lines.filter(Boolean).join("\n");
}

function selectedAssetWorkflowJson(asset: Asset, assets: Asset[], config: FrankConfig, turns: StudioTurn[]) {
  const turn = turns.find((item) => item.id === asset.turn_id);
  const settings = sanitizeWorkflowPayload(parseJsonRecord(asset.settings_json ?? turn?.settings_json)) as Record<string, unknown>;
  const workflowProvenance = parseJsonRecord(settings.workflow_provenance);
  const referenceIds = parseJsonList(asset.reference_asset_ids_json ?? turn?.reference_asset_ids_json);
  const sourceId = asset.source_asset_id ?? turn?.source_asset_id;
  const model = config.models.find((item) => item.id === (asset.model ?? turn?.model));
  const workflowBridge = assetWorkflowBridge(asset, turns, workflowProvenance);

  return {
    product: "Frank Create",
    asset_id: asset.id,
    asset_title: asset.title,
    media_type: asset.media_type ?? "image",
    provider: asset.provider ?? turn?.provider ?? model?.provider ?? null,
    model: asset.model ?? turn?.model ?? model?.id ?? null,
    prompt: asset.prompt ?? turn?.prompt ?? "",
    settings,
    workflow_provenance: workflowProvenance,
    workflow_bridge: workflowBridge,
    source: sourceId ? assetReferenceSummary(sourceId, assets) : null,
    references: referenceIds.map((id) => assetReferenceSummary(id, assets)),
    approval_status: asset.approval_status ?? "review",
    favorite: Boolean(asset.favorite),
    sync_status: asset.sync_status ?? "local",
    file_path: asset.file_path ?? "",
    created_at: asset.created_at ?? null,
    updated_at: asset.updated_at ?? null,
    turn_id: turn?.id ?? asset.turn_id ?? null,
    provider_keys: "server-side only; no secrets included"
  };
}

function assetWorkflowBridge(asset: Asset, turns: StudioTurn[], workflowProvenance?: Record<string, unknown>) {
  const turn = turns.find((item) => item.id === asset.turn_id);
  const settings = workflowProvenance
    ? { workflow_provenance: workflowProvenance }
    : (parseJsonRecord(asset.settings_json ?? turn?.settings_json) as Record<string, unknown>);
  const workflow = workflowProvenance ?? parseJsonRecord(settings.workflow_provenance);
  const workflowJson = parseJsonRecord(workflow.workflow_json);
  const canLoadComfyApiPrompt = Boolean(Object.keys(workflowJson).length);
  return {
    asset_id: asset.id,
    workflow_key: typeof workflow.workflow_key === "string" ? workflow.workflow_key : asset.model ?? turn?.model ?? null,
    engine: typeof workflow.engine === "string" ? workflow.engine : asset.provider ?? turn?.provider ?? null,
    can_open_raw_canvas: asset.kind !== "reference",
    can_load_comfy_api_prompt: canLoadComfyApiPrompt,
    raw_canvas_load_status: canLoadComfyApiPrompt ? "api_prompt_attached" : "receipt_only",
    comfy_node_types: workflowNodeTypes(workflow, workflowJson),
    raw_canvas_url: comfyCanvasAssetUrl(asset.id),
    workflow_receipt_url: assetWorkflowReceiptUrl(asset.id)
  };
}

function workflowNodeTypes(workflow: Record<string, unknown>, workflowJson: Record<string, unknown>) {
  const localNodeTypes = localWorkflowNodeTypes(typeof workflow.workflow_key === "string" ? workflow.workflow_key : "");
  if (localNodeTypes.length) {
    return localNodeTypes;
  }
  if (Array.isArray(workflow.comfy_node_types)) {
    return workflow.comfy_node_types.filter((item): item is string => typeof item === "string" && item.length > 0);
  }
  return Object.entries(workflowJson)
    .sort(([left], [right]) => workflowNodeSortKey(left).localeCompare(workflowNodeSortKey(right)))
    .map(([, node]) => parseJsonRecord(node).class_type)
    .filter((item): item is string => typeof item === "string" && item.length > 0);
}

function localWorkflowNodeTypes(workflowKey: string) {
  const byWorkflow: Record<string, string[]> = {
    "frank-local-variant-renderer": ["FrankCreateVariant", "SaveImage"],
    "frank-local-background-remove-renderer": ["FrankCreateBackgroundRemove", "SaveImage"],
    "frank-local-background-replace-renderer": ["FrankCreateBackgroundReplace", "SaveImage"],
    "frank-local-masked-edit-renderer": ["FrankCreateMaskedEdit", "SaveImage"],
    "frank-local-video-storyboard": ["FrankCreateVideoStoryboard", "SaveAnimatedImage"]
  };
  return byWorkflow[workflowKey] ?? [];
}

function workflowNodeSortKey(nodeId: string) {
  const numeric = Number.parseInt(nodeId, 10);
  return Number.isFinite(numeric) ? `0-${numeric.toString().padStart(6, "0")}` : `1-${nodeId}`;
}

function assetReferenceSummary(id: string, assets: Asset[]) {
  const asset = assets.find((item) => item.id === id);
  return {
    id,
    title: asset?.title ?? id
  };
}

function safeFileStem(value: string) {
  return (
    value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 72) || "frank-create-workflow"
  );
}

function sanitizeWorkflowPayload(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeWorkflowPayload(item));
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, item]) => [
      key,
      isSensitiveWorkflowKey(key) ? "[server-side secret]" : sanitizeWorkflowPayload(item)
    ])
  );
}

function isSensitiveWorkflowKey(key: string) {
  return /api[_-]?key|token|secret|authorization|bearer|password|credential/i.test(key);
}

function settingsSummary(settings: Record<string, unknown>) {
  const aspect = typeof settings.aspect_ratio === "string" ? settings.aspect_ratio : "";
  const size = typeof settings.image_size === "string" || typeof settings.image_size === "number" ? String(settings.image_size) : "";
  const countValue = Number(settings.count ?? 0);
  const count = Number.isFinite(countValue) && countValue > 0 ? Math.trunc(countValue) : 0;
  const pieces = [aspect, size].filter(Boolean);
  if (count) {
    pieces.push(`${count} ${count === 1 ? "variant" : "variants"}`);
  }
  return pieces.join(" / ");
}

function workflowSummary(workflow: Record<string, unknown>) {
  const workflowKey = typeof workflow.workflow_key === "string" ? workflow.workflow_key : "";
  const engine = typeof workflow.engine === "string" ? workflow.engine : "";
  const checkpoint = typeof workflow.checkpoint_name === "string" ? workflow.checkpoint_name : "";
  if (!workflowKey && !engine) {
    return "";
  }
  const label = [workflowKey, engine].filter(Boolean).join(" / ");
  return checkpoint ? `${label} / ${checkpoint}` : label;
}

function providerDisplayName(provider?: string) {
  const names: Record<string, string> = {
    google: "Google",
    local: "Local",
    openai: "OpenAI",
    replicate: "Replicate"
  };
  return provider ? names[provider] ?? titleize(provider) : "Provider";
}

function turnEmptyLabel(turn: StudioTurn) {
  if (turn.status === "blocked") {
    return "Provider setup needed";
  }
  if (turn.status === "failed") {
    return "Provider returned no image";
  }
  return "Waiting for provider output";
}

function turnKindLabel(turn: StudioTurn) {
  if (turn.kind === "edit") {
    return "Edit round";
  }
  if (turn.kind === "video") {
    return "Motion round";
  }
  return "Generate round";
}

function referenceCountLabel(count: number) {
  return `${count} reference${count === 1 ? "" : "s"}`;
}

function doctorStatusIcon(status: "ready" | "warning" | "fail") {
  if (status === "ready") {
    return "OK";
  }
  if (status === "warning") {
    return "!";
  }
  return "Fix";
}

function activationStatusIcon(status: ActivationChecklist["steps"][number]["status"]) {
  if (status === "ready") {
    return "OK";
  }
  if (status === "recommended") {
    return "Tip";
  }
  return "Do";
}

function activationPathLabel(path: string) {
  return /models[\\/]+checkpoints$/i.test(path) ? "models\\checkpoints" : path;
}

function activationModelTotal(checklist: ActivationChecklist) {
  const explicitTotal = Number(checklist.summary.provider_model_count);
  if (Number.isFinite(explicitTotal) && explicitTotal > 0) {
    return explicitTotal;
  }
  return Number(checklist.summary.ready_provider_models || 0) + Number(checklist.summary.waiting_provider_models || 0);
}

function activationChecklistInlineStatus(checklist: ActivationChecklist) {
  const count = checklist.steps.length;
  return `Activation checklist tracked: ${count} unlock ${count === 1 ? "step" : "steps"}`;
}

function demoDoctorSummary(doctor: DemoDoctorStatus) {
  const smokeCopy = doctor.summary.workflowSmokeOk ? "workflow smoke passed" : "run workflow smoke";
  return `${doctor.summary.outputAssetCount} outputs, ${doctor.summary.referenceAssetCount} refs, ${smokeCopy}, ${doctor.summary.waitingProviderModels} live models waiting.`;
}

function buildLaunchReadinessItems(
  config: FrankConfig,
  waitingModelCount: number,
  doctor: DemoDoctorStatus | null,
  checklist: ActivationChecklist | null,
  readinessPackSha: string
) {
  const hasDiffusionCheckpoint = config.localEngine.diffusion_ready && config.localEngine.checkpoint_count > 0;
  const liveWaiting = checklist?.summary.waiting_provider_models ?? doctor?.summary.waitingProviderModels ?? waitingModelCount;
  const packReady = Boolean(readinessPackSha || doctor?.summary.readinessPackReady);
  const demoIsCurated = doctor ? doctor.summary.demoCurated !== false : true;
  return [
    {
      key: "local-demo",
      status: doctor?.readyForDemo === false || !demoIsCurated ? "warning" : "ready",
      badge: doctor?.readyForDemo === false || !demoIsCurated ? "Do" : "OK",
      label: !demoIsCurated ? "Reset demo before Cliff" : "Local demo ready",
      detail: !demoIsCurated
        ? `${doctor?.summary.imageOutputAssetCount ?? doctor?.summary.outputAssetCount ?? 0} visible image outputs; use Reset demo for the clean seed.`
        : doctor?.summary.workflowSmokeOk
          ? "Smoke-tested generate, edit, approve, export, and handoff."
          : "Local Comfy renderer is the fallback path for the call."
    },
    {
      key: "live-keys",
      status: liveWaiting ? "warning" : "ready",
      badge: liveWaiting ? "Do" : "OK",
      label: liveWaiting ? `${liveWaiting} live key models waiting` : "Live APIs unlocked",
      detail: liveWaiting
        ? "Use Provider Setup for rotated server-side keys; no browser secrets."
        : "Provider proxy can run the visible live model roster."
    },
    {
      key: "checkpoint",
      status: hasDiffusionCheckpoint ? "ready" : "recommended",
      badge: hasDiffusionCheckpoint ? "OK" : "Tip",
      label: hasDiffusionCheckpoint ? "Checkpoint installed" : "Checkpoint optional",
      detail: hasDiffusionCheckpoint
        ? `${config.localEngine.checkpoint_count} local checkpoint file ready for Comfy workflows.`
        : "Frank renderer works now; add a checkpoint later for native txt2img/img2img/inpaint."
    },
    {
      key: "proof-pack",
      status: packReady ? "ready" : "recommended",
      badge: packReady ? "OK" : "Tip",
      label: packReady ? "Proof pack ready" : "Build proof pack",
      detail: readinessPackSha ? `Verified SHA-256 ${readinessPackSha.slice(0, 12)}...` : "Run Demo Doctor, then build the call pack before sending."
    }
  ];
}

function buildCliffGuideSteps(outputAssets: Asset[], referenceAssets: Asset[], approvedCount: number, approvedMotionCount: number) {
  const reviewableImages = outputAssets.filter((asset) => (asset.media_type ?? "image") !== "video");
  return [
    {
      label: "Image Studio",
      detail: "Open with sessions, prompt thread, references, model picker, and Frank Body Mode.",
      status: outputAssets.length ? `${outputAssets.length} outputs` : "seed demo"
    },
    {
      label: "Product Shot Lab",
      detail: "Use the product presets, run a local round, then approve the best shot.",
      status: referenceAssets.length ? `${referenceAssets.length} refs` : "add refs"
    },
    {
      label: "Paint edit mask",
      detail: "Select an image, paint a retouch mask, save it into Masked Edit, then make another round.",
      status: reviewableImages.length ? "image ready" : "need image"
    },
    {
      label: "Video Lab",
      detail: "Turn an approved image into a motion storyboard and export the storyboard ZIP.",
      status: approvedMotionCount ? `${approvedMotionCount} motion` : "storyboard path"
    },
    {
      label: "Advanced Graph",
      detail: "Open the Frank-branded Comfy escape hatch and raw canvas for power users.",
      status: approvedCount ? `${approvedCount} approved` : "show escape"
    }
  ];
}

function buildCliffGuideProofs(doctor: DemoDoctorStatus | null, manifest: DemoReadinessPackResult["manifest"] | null) {
  const screenshots = manifest?.screenshot_count ?? 0;
  const browserQaChecks = new Set(
    (manifest?.browser_qa?.checks ?? [])
      .filter((check) => check.status === "ready" || check.browser_status === "ready")
      .map((check) => check.key)
  );
  return [
    doctor?.summary.workflowSmokeOk ? "Workflow smoke passed" : "Run workflow smoke",
    doctor?.summary.activationChecklistReady ? "Production checklist ready" : "Build call pack for checklist",
    screenshots > 0 ? `${screenshots} QA screenshots ready` : "Build call pack for screenshots",
    manifest?.cliff_pack?.status === "included" ? "Cliff Pack included" : "Export Cliff Pack before sending",
    browserQaChecks.has("studio_model_preflight") ? "Model preflight proved" : "Run selected model preflight",
    browserQaChecks.has("studio_local_generate") ? "Local Generate proved" : "Run local Generate proof",
    browserQaChecks.has("studio_masked_edit_generate") ? "Masked edit proved" : "Run masked edit proof"
  ];
}

function turnErrorCopy(turn: StudioTurn) {
  if (!turn.error_json) {
    return "";
  }

  try {
    const error = JSON.parse(turn.error_json) as { code?: string; env_vars?: string[]; message?: string };
    if (error.code === "missing_key" && error.env_vars?.length) {
      return `Needs ${error.env_vars.join(" or ")}`;
    }
    return error.message ?? error.code ?? "";
  } catch {
    return turn.error_json;
  }
}

function parseJsonRecord(value?: unknown) {
  if (!value) {
    return {} as Record<string, unknown>;
  }
  if (typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  if (typeof value !== "string") {
    return {} as Record<string, unknown>;
  }

  try {
    const parsed = JSON.parse(value) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function nextRoundPrompt(asset: Asset, direction: "similar" | "cleanup" | "campaign", preset?: PromptPreset) {
  const note = asset.notes?.trim();
  const base =
    direction === "cleanup"
      ? "Make another round from this selected image. Clean up product edges, label clarity, lighting, and small retouching issues while keeping the product structure accurate."
      : direction === "campaign"
        ? "Make another campaign round from this selected image. Keep the product recognizable, push the set styling, and create director-ready variants with Frank Body attitude."
        : "Make another round like this selected image. Preserve the strongest composition, product scale, label plausibility, and Frank Body palette while exploring better variants.";
  const parts = [base];
  if (preset?.prompt) {
    parts.push(`Preset direction: ${preset.prompt}`);
  }
  if (note) {
    parts.push(`Review note to honor: ${note}`);
  }
  return parts.join("\n\n");
}

function missingKeyCopy(model: StudioModel) {
  if (model.configured !== false) {
    return "";
  }

  const envVars = model.missing_env_vars ?? [];
  if (!envVars.length) {
    return " / needs key";
  }

  return ` / needs ${envVars[0]}${envVars.length > 1 ? ` (+${envVars.length - 1})` : ""}`;
}

function missingKeyTitle(model: StudioModel) {
  return model.configured === false ? (model.missing_env_vars ?? []).join(" or ") : undefined;
}

function modelMissingKeyAction(model?: StudioModel) {
  if (!model || model.provider === "local" || model.configured !== false) {
    return "";
  }

  const envVars = (model.missing_env_vars?.length ? model.missing_env_vars : model.env_vars) ?? [];
  if (!envVars.length) {
    return `${model.short_label ?? model.label} needs a server key before live API rounds.`;
  }

  return `Add ${envVars.join(" or ")} in the server key file, then reload keys.`;
}

function modelReferenceLimitAction(model: StudioModel | undefined, referenceCount: number) {
  const limit = Number(model?.reference_image_limit ?? 0);
  if (!model || !Number.isFinite(limit) || limit <= 0 || referenceCount <= limit) {
    return "";
  }

  const extraCount = referenceCount - limit;
  return `${model.short_label ?? model.label} can use ${limit} references. Remove ${extraCount} ${
    extraCount === 1 ? "reference" : "references"
  } before making this round.`;
}

function providerPreflightStatusLabel(status: ProviderPreflight["status"]) {
  if (status === "ready") {
    return "Preflight ready";
  }
  if (status === "blocked") {
    return "Preflight blocked";
  }
  return "Preflight unsupported";
}

function providerSetup(models: StudioModel[]) {
  const waitingModels = models.filter((model) => model.configured === false);
  const envVars = orderProviderEnvVars(
    Array.from(new Set(waitingModels.flatMap((model) => model.missing_env_vars ?? []))),
    providerUnlockPlan(models)
  );

  return { waitingModels, envVars };
}

function providerUnlockPlan(models: StudioModel[]) {
  const groups = new Map<
    string,
    {
      id: string;
      envVars: string[];
      models: StudioModel[];
      priority: number;
    }
  >();

  for (const model of models) {
    if (model.provider === "local") {
      continue;
    }

    const envVars = providerModelEnvVars(model);
    if (!envVars.length) {
      continue;
    }

    const key = envVars.join("|");
    const existing = groups.get(key);
    if (existing) {
      existing.models.push(model);
      existing.priority = Math.min(existing.priority, providerUnlockPriority(model));
    } else {
      groups.set(key, {
        id: key,
        envVars,
        models: [model],
        priority: providerUnlockPriority(model)
      });
    }
  }

  return Array.from(groups.values())
    .sort((left, right) => left.priority - right.priority || left.id.localeCompare(right.id))
    .map((group) => {
      const modelLabels = group.models.map((model) => model.short_label ?? model.label);
      const capabilityCopy = capabilitySummary(group.models);
      const groupReady = group.models.every((model) => model.configured);
      return {
        id: group.id,
        envVars: group.envVars,
        label: modelLabels.join(" + "),
        keyCopy: groupReady
          ? `${joinWithOr(group.envVars)} ready`
          : group.envVars.length === 1
            ? `Add ${group.envVars[0]}`
            : `Use one of ${joinWithOr(group.envVars)}`,
        capabilityCopy
      };
    });
}

function orderProviderEnvVars(envVars: string[], rows: ReturnType<typeof providerUnlockPlan>) {
  const desiredOrder = rows.flatMap((row) => row.envVars);
  const priority = new Map(desiredOrder.map((envVar, index) => [envVar, index]));
  return Array.from(new Set(envVars)).sort((left, right) => {
    const leftPriority = priority.get(left) ?? Number.MAX_SAFE_INTEGER;
    const rightPriority = priority.get(right) ?? Number.MAX_SAFE_INTEGER;
    return leftPriority - rightPriority || left.localeCompare(right);
  });
}

function providerModelEnvVars(model: StudioModel) {
  const envVars = model.env_vars?.length
    ? model.env_vars
    : model.missing_env_vars?.length
      ? model.missing_env_vars
      : model.configured_env_var
        ? [model.configured_env_var]
        : [];

  return Array.from(new Set(envVars));
}

function providerKeyPlanText({
  rows,
  envVars,
  readyModels,
  modelCount,
  keyFilePath
}: {
  rows: ReturnType<typeof providerUnlockPlan>;
  envVars: string[];
  readyModels?: number;
  modelCount: number;
  keyFilePath: string;
}) {
  const lines = [
    "Frank Create Provider Key Plan",
    "",
    `Server key file: ${keyFilePath}`,
    `Provider readiness: ${readyModels ?? 0} / ${modelCount} live provider models ready`,
    "Provider secret values are not included. Paste rotated keys only into Provider Setup or the local server key file.",
    ""
  ];

  if (rows.length) {
    lines.push("Cliff key order:");
    rows.forEach((row, index) => {
      lines.push(`${index + 1}. ${row.label}`);
      lines.push(`   Keys: ${row.keyCopy}`);
      lines.push(`   Unlocks: ${row.capabilityCopy}`);
    });
  } else {
    lines.push("Cliff key order: all visible provider rows are unlocked.");
  }

  if (envVars.length) {
    lines.push("", `Missing env vars: ${envVars.join(", ")}`);
  }

  lines.push("", "Rotate any exposed token before live provider use.");
  return lines.join("\n");
}

function productionUnlockPlanText(checklist: ActivationChecklist) {
  const summary = checklist.summary;
  const lines = [
    "Frank Create Production Unlock Plan",
    "",
    `Status: ${checklist.status}`,
    `Live model paths unlocked: ${summary.ready_provider_models} / ${activationModelTotal(checklist)}`,
    `Server key file: ${summary.server_key_file || "user\\frank_create\\provider_keys.env"}`,
    `Local checkpoints detected: ${summary.checkpoint_count}`,
    "Allowed provider env vars: GOOGLE_API_KEY, REPLICATE_API_TOKEN, OPENAI_API_KEY",
    "No provider secret values are included.",
    ""
  ];

  lines.push("Actions:");
  checklist.steps.forEach((step, index) => {
    lines.push(`${index + 1}. ${step.label} (${step.status})`);
    lines.push(`   ${step.detail}`);
    lines.push(`   Action: ${step.action}`);
    if (step.env_vars?.length) {
      lines.push(`   Env vars: ${step.env_vars.join(", ")}`);
    }
    if (step.path) {
      const checkpointNote = step.minimum_checkpoint_mb ? `; minimum ${step.minimum_checkpoint_mb} MB` : "";
      lines.push(`   Path: ${activationPathLabel(step.path)}${checkpointNote}`);
    }
  });

  if (summary.missing_env_vars?.length) {
    lines.push("", `Missing env vars: ${summary.missing_env_vars.join(", ")}`);
  }
  if (checklist.notes.length) {
    lines.push("", "Notes:");
    checklist.notes.forEach((note) => lines.push(`- ${note}`));
  }
  lines.push("", "Paste rotated keys only into Provider Setup or the local server key file.");
  return lines.join("\n");
}

function parseReadyStatusLink(text: string) {
  const match = text.match(/^(.+?) link ready: (.+)$/);
  if (!match) {
    return null;
  }
  return { label: match[1], url: match[2] };
}

function providerUnlockPriority(model: StudioModel) {
  const priorities: Record<string, number> = {
    "google-nb-pro": 1,
    "google-nb-2": 1,
    "flux-1-1-pro-ultra": 2,
    "openai-gpt-image-2": 3
  };

  return priorities[model.id] ?? 99;
}

function capabilitySummary(models: StudioModel[]) {
  const capabilities = models.reduce(
    (result, model) => ({
      generation: result.generation || model.capabilities.generation,
      edit: result.edit || model.capabilities.edit,
      masked_edit: result.masked_edit || model.capabilities.masked_edit,
      video: result.video || model.capabilities.video
    }),
    { generation: false, edit: false, masked_edit: false, video: false }
  );
  const labels = [
    capabilities.generation ? "gen" : "",
    capabilities.edit ? "edit" : "",
    capabilities.masked_edit ? "mask" : "",
    capabilities.video ? "video" : ""
  ].filter(Boolean);
  const badges = Array.from(new Set(models.map((model) => model.badge).filter(Boolean)));

  return [labels.join(" + "), badges.join(" / ")].filter(Boolean).join(" / ");
}

function providerAuditOperationSummary(operationKinds: string[] = [], requestPreviews?: Record<string, unknown>) {
  const previewCount = Object.keys(requestPreviews ?? {}).length || operationKinds.length;
  const labels = operationKinds.map((kind) => kind.replace(/_/g, " "));
  return `${previewCount} ops: ${labels.join(", ") || "none"}`;
}

function joinWithOr(values: string[]) {
  if (values.length <= 1) {
    return values[0] ?? "";
  }

  return `${values.slice(0, -1).join(", ")} or ${values[values.length - 1]}`;
}

function referenceIdsFromAssets(assets: Asset[]) {
  return assets.filter((asset) => asset.kind === "reference").map((asset) => asset.id);
}

function makeLocalSession(): StudioSession {
  const now = new Date().toISOString();
  return {
    id: makeLocalId("session"),
    name: "Local image session",
    mode: "image",
    status: "preview",
    created_at: now,
    updated_at: now,
    sync_status: "local"
  };
}

function makeLocalTurn(sessionId: string, request: ReturnType<typeof buildTurnRequest>): StudioTurn {
  const now = new Date().toISOString();
  return {
    id: makeLocalId("turn"),
    session_id: sessionId,
    kind: request.kind,
    provider: "local-preview",
    model: request.model,
    prompt: request.prompt,
    settings_json: JSON.stringify(request.settings),
    reference_asset_ids_json: JSON.stringify(request.reference_asset_ids),
    output_asset_ids_json: "[]",
    frank_body_mode: request.frank_body_mode,
    preset_key: request.preset_key,
    status: "blocked",
    error_json: JSON.stringify({ code: "offline" }),
    sync_status: "local",
    created_at: now,
    updated_at: now
  };
}
