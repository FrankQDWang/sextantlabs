import type { Candidate, RiskLevel } from "@/lib/workbench-data"
import type {
  ActionRequestResponse,
  ActionRequestRunResponse,
  ActionRequestCreateBody,
  AgentReviewFindingResponse,
  BeatCandidateResponse,
  CandidateAcceptResponse,
  CandidateDetailResponse,
  CandidateOperationResponse,
  ArchiveSourceResponse,
  CanonicalEntityListResponse,
  ContextPackReadinessListResponse,
  CreateSourceDeltaResponse,
  CreateSourceResponse,
  GraphProjectionEdgeListResponse,
  JobDetailResponse,
  MemoryAnswerResponse,
  MemoryPageDetailResponse,
  MemoryPageListResponse,
  MemoryPageThreadOperationResponse,
  MemoryWritebackDecisionResponse,
  MemoryWritebackPreviewResponse,
  ProjectMemberListResponse,
  ProjectMemberOperationResponse,
  ProjectInvitationCreateBody,
  ProjectInvitationExternalProofBody,
  ProjectInvitationListResponse,
  ProjectInvitationResponse,
  ProjectStorySchemaGenreBody,
  ProjectStorySchemaOverrideBody,
  ProjectStorySchemaResponse,
  ReviewItemDetailResponse,
  ReviewItemListResponse,
  RestoreSourceVersionResponse,
  SextantApiClient,
  SourceDeltaListResponse,
  SourceDeltaDetailResponse,
  SourceListResponse,
  StorySceneListResponse,
  SourceVersionDiffResponse,
  SourceVersionListResponse,
  SourceVersionResponse,
  StorySchemaPackListResponse,
  UUID,
  BuildWritingContextPackBody,
  WritingContextPackResponse,
  ReadHeaders,
  WriteHeaders,
} from "@/src/generated/sextant-api"

export type WorkbenchApiConfig = {
  apiBaseUrl: string
  projectId: UUID
  actorId: UUID
  bearerToken?: string
  sourceId: UUID
  sourceVersionId: UUID
  sceneId?: UUID
  povCharacterId?: UUID
}

export type TextRange = { start: number; end: number }

export type AskMemoryTarget = {
  subjectRef?: Record<string, unknown>
  predicate?: string
}

type EnvLike = Partial<Record<string, string>>

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">

export const WORKBENCH_AUTH_STORAGE_KEY = "sextant.workbench.auth.v1"

export type WorkbenchAuthConfig = {
  supabaseUrl: string
  publishableKey: string
}

export type WorkbenchAuthCredentials = {
  email: string
  password: string
}

export type WorkbenchAuthSession = {
  accessToken: string
  refreshToken?: string
  expiresAt?: number
}

export type WorkbenchApiConfigOptions = {
  bearerToken?: string | null
}

type IdFactory = () => string

type RewriteClient = Pick<
  SextantApiClient,
  "submitActionRequest" | "runActionRequest" | "getCandidate"
>

type AcceptClient = Pick<SextantApiClient, "acceptCandidate">

type SourceClient = Pick<SextantApiClient, "getSourceVersion">

type ProjectMemberClient = Pick<
  SextantApiClient,
  "listProjectMembers" | "upsertProjectMember" | "revokeProjectMember"
>

type ProjectInvitationClient = Pick<
  SextantApiClient,
  "listProjectInvitations" | "createProjectInvitation" | "recordProjectInvitationExternalProof"
>

type SourceVersionDiffClient = Pick<SextantApiClient, "getSourceVersionDiff">

type SourceVersionListClient = Pick<SextantApiClient, "listSourceVersions">

type SourceListClient = Pick<SextantApiClient, "listSources">

type SourceCreateClient = Pick<SextantApiClient, "createSource">

type SourceArchiveClient = Pick<SextantApiClient, "archiveSource">

type SourceRestoreClient = Pick<SextantApiClient, "restoreSourceVersion">

type SourceEditClient = Pick<SextantApiClient, "createSourceDelta">

type SourceDeltaListClient = Pick<SextantApiClient, "listSourceDeltas">

type SourceDeltaDetailClient = Pick<SextantApiClient, "getSourceDelta">

type WritebackClient = Pick<
  SextantApiClient,
  "getJob" | "getMemoryWritebackPreview" | "listReviewItems"
>

type JobOperationClient = Pick<SextantApiClient, "cancelJob" | "retryJob">

type ReviewListClient = Pick<SextantApiClient, "listReviewItems">

type WritebackDecisionClient = Pick<SextantApiClient, "decideMemoryWritebackPreview">

type ReviewDetailClient = Pick<SextantApiClient, "getReviewItem">

type EntityListClient = Pick<SextantApiClient, "listEntities">

type SceneListClient = Pick<SextantApiClient, "listScenes">

type StorySchemaClient = Pick<SextantApiClient, "getProjectStorySchema" | "listStorySchemaPacks">

type StorySchemaWriteClient = Pick<
  SextantApiClient,
  "selectProjectStorySchemaGenrePack" | "upsertProjectStorySchemaOverride"
>

type ReviewOperationClient = Pick<
  SextantApiClient,
  "resolveReviewItem" | "dismissReviewItem" | "reopenReviewItem"
>

type ContextPackClient = Pick<SextantApiClient, "getContextPack">

type ContextPackReadinessClient = Pick<SextantApiClient, "listContextPackReadiness">

type MemoryAnswerClient = Pick<SextantApiClient, "submitActionRequest" | "runActionRequest">

type MemoryPageClient = Pick<SextantApiClient, "listMemoryPages" | "getMemoryPage">

type MemoryPageThreadOperationClient = Pick<SextantApiClient, "operateMemoryPageOpenThread">

type GraphProjectionClient = Pick<SextantApiClient, "listGraphProjectionEdges">

type RiskCheckClient = Pick<SextantApiClient, "submitActionRequest" | "runActionRequest">

type BeatCandidateClient = Pick<SextantApiClient, "submitActionRequest" | "runActionRequest">

type CandidateExplainClient = Pick<
  SextantApiClient,
  "submitActionRequest" | "runActionRequest" | "getCandidate"
>

type CandidateOperationClient = Pick<
  SextantApiClient,
  "rejectCandidate" | "overrideCandidateBlock" | "getCandidate"
>

type CandidateReviseClient = Pick<
  SextantApiClient,
  "submitActionRequest" | "runActionRequest" | "getCandidate"
>

export const STALE_SOURCE_VERSION_MESSAGE =
  "正文版本已更新。请先刷新正文，再重新生成候选；系统没有写入正文或记忆。"

export type WorkbenchWritebackState = {
  job: JobDetailResponse
  preview: MemoryWritebackPreviewResponse
  reviewItems: ReviewItemListResponse["items"]
}

export type WorkbenchWritebackDecisionInput = {
  itemRef: Record<string, unknown>
  decision: "accept" | "reject" | "correct"
  authorNote?: string | null
  correction?: Record<string, unknown>
  replacementRefs?: Record<string, unknown>[]
}

export type WorkbenchSourceCreateInput = {
  title: string
  sourceType: string
  sourceScope: string
  text: string
}

export type WorkbenchSourceDeltaFilters = {
  query?: string
  status?: string
  deltaKind?: string
  sourceVersionId?: UUID
  cursor?: string
  acceptedOnly?: boolean
}

export type WorkbenchMemoryPageFilters = {
  pageType?: string
  canonStatus?: string
}

export type WorkbenchMemoryPageThreadInput = {
  threadId: string
  updateType: "keeps_open" | "narrows" | "pays_off" | "closes"
  authorNote: string
  summary?: string | null
}

export type WorkbenchGraphEdgeFilters = {
  query?: string
  relation?: string
  edgeStatus?: string
}

export type WorkbenchStorySchemaOverrideInput = {
  packName?: string
  entityTypes?: Record<string, unknown>[]
  eventTypes?: Array<Record<string, unknown> | string>
  relations?: Array<Record<string, unknown> | string>
  extractionHints?: Record<string, unknown>
  riskRules?: Record<string, unknown>
}

export type WorkbenchProjectMemberRole = "owner" | "editor" | "viewer"

export type WorkbenchProjectInvitationInput = {
  memberActorId: UUID
  role: WorkbenchProjectMemberRole
  deliveryProviderRef: string
  deliveryTargetRef: string
  tokenIssuerRef?: string | null
}

export type WorkbenchProjectInvitationProofInput = {
  deliveryProofRef: string
  tokenProofRef?: string | null
}

export type ReviewResolution =
  | "accept"
  | "reject"
  | "split"
  | "merge"
  | "mark_intentional"
  | "supersede"
  | "needs_memory_update"
  | "fixed_by_text_edit"
  | "accepted_as_change"

export const REVIEW_RESOLUTION_OPTIONS: Array<{ value: ReviewResolution; label: string }> = [
  { value: "accepted_as_change", label: "采纳为变更" },
  { value: "mark_intentional", label: "标记有意" },
  { value: "fixed_by_text_edit", label: "正文已修复" },
  { value: "needs_memory_update", label: "需要记忆更新" },
  { value: "accept", label: "接受" },
  { value: "reject", label: "拒绝" },
  { value: "split", label: "拆分" },
  { value: "merge", label: "合并" },
  { value: "supersede", label: "替换旧项" },
]

export function isReviewResolution(value: unknown): value is ReviewResolution {
  return REVIEW_RESOLUTION_OPTIONS.some((option) => option.value === value)
}

export function reviewResolutionLabel(resolution: ReviewResolution): string {
  return (
    REVIEW_RESOLUTION_OPTIONS.find((option) => option.value === resolution)?.label ?? resolution
  )
}

export function readWorkbenchApiConfig(
  env: EnvLike = import.meta.env,
  options: WorkbenchApiConfigOptions = {},
): WorkbenchApiConfig | null {
  const apiBaseUrl = env.VITE_SEXTANT_API_BASE_URL?.trim()
  const projectId = env.VITE_SEXTANT_PROJECT_ID?.trim()
  const actorId = env.VITE_SEXTANT_ACTOR_ID?.trim()
  const bearerToken = options.bearerToken?.trim() || env.VITE_SEXTANT_BEARER_TOKEN?.trim()
  const sourceId = env.VITE_SEXTANT_SOURCE_ID?.trim()
  const sourceVersionId = env.VITE_SEXTANT_SOURCE_VERSION_ID?.trim()
  const sceneId = env.VITE_SEXTANT_SCENE_ID?.trim()
  const povCharacterId = env.VITE_SEXTANT_POV_CHARACTER_ID?.trim()

  if (!apiBaseUrl || !projectId || !actorId || !sourceId || !sourceVersionId) {
    return null
  }

  return {
    apiBaseUrl,
    projectId,
    actorId,
    ...(bearerToken ? { bearerToken } : {}),
    sourceId,
    sourceVersionId,
    ...(sceneId ? { sceneId } : {}),
    ...(povCharacterId ? { povCharacterId } : {}),
  }
}

export function readWorkbenchAuthConfig(env: EnvLike = import.meta.env): WorkbenchAuthConfig | null {
  const supabaseUrl = env.VITE_SEXTANT_SUPABASE_URL?.trim().replace(/\/+$/, "")
  const publishableKey =
    env.VITE_SEXTANT_SUPABASE_PUBLISHABLE_KEY?.trim() ??
    env.VITE_SEXTANT_SUPABASE_ANON_KEY?.trim()

  if (!supabaseUrl || !publishableKey) {
    return null
  }

  return { supabaseUrl, publishableKey }
}

export async function signInWorkbenchWithPassword(
  config: WorkbenchAuthConfig,
  credentials: WorkbenchAuthCredentials,
  fetcher: FetchLike = globalThis.fetch.bind(globalThis),
): Promise<WorkbenchAuthSession> {
  const email = credentials.email.trim()
  const password = credentials.password
  if (!email || !password) {
    throw new Error("请填写邮箱和密码。")
  }

  const response = await fetcher(`${config.supabaseUrl.replace(/\/+$/, "")}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: config.publishableKey,
    },
    body: JSON.stringify({ email, password }),
  })

  if (!response.ok) {
    throw new Error(`登录失败：${await readAuthErrorMessage(response)}`)
  }

  const payload = (await response.json()) as {
    access_token?: unknown
    refresh_token?: unknown
    expires_in?: unknown
  }
  const accessToken = typeof payload.access_token === "string" ? payload.access_token.trim() : ""
  if (!accessToken) {
    throw new Error("登录响应缺少 access_token。")
  }

  const refreshToken =
    typeof payload.refresh_token === "string" && payload.refresh_token.trim()
      ? payload.refresh_token
      : undefined
  const expiresIn = Number(payload.expires_in)

  return {
    accessToken,
    ...(refreshToken ? { refreshToken } : {}),
    ...(Number.isFinite(expiresIn) && expiresIn > 0
      ? { expiresAt: Math.floor(Date.now() / 1000) + expiresIn }
      : {}),
  }
}

export function readStoredWorkbenchAuthSession(
  storage: StorageLike | null = defaultWorkbenchAuthStorage(),
): WorkbenchAuthSession | null {
  if (!storage) return null
  const raw = storage.getItem(WORKBENCH_AUTH_STORAGE_KEY)
  if (!raw) return null

  try {
    const parsed = JSON.parse(raw) as Partial<WorkbenchAuthSession>
    const accessToken =
      typeof parsed.accessToken === "string" ? parsed.accessToken.trim() : ""
    if (!accessToken) return null
    if (
      typeof parsed.expiresAt === "number" &&
      parsed.expiresAt <= Math.floor(Date.now() / 1000) + 30
    ) {
      storage.removeItem(WORKBENCH_AUTH_STORAGE_KEY)
      return null
    }
    return {
      accessToken,
      ...(typeof parsed.refreshToken === "string" && parsed.refreshToken
        ? { refreshToken: parsed.refreshToken }
        : {}),
      ...(typeof parsed.expiresAt === "number" ? { expiresAt: parsed.expiresAt } : {}),
    }
  } catch {
    storage.removeItem(WORKBENCH_AUTH_STORAGE_KEY)
    return null
  }
}

export function writeStoredWorkbenchAuthSession(
  session: WorkbenchAuthSession,
  storage: StorageLike | null = defaultWorkbenchAuthStorage(),
): void {
  if (!storage) return
  storage.setItem(WORKBENCH_AUTH_STORAGE_KEY, JSON.stringify(session))
}

export function clearStoredWorkbenchAuthSession(
  storage: StorageLike | null = defaultWorkbenchAuthStorage(),
): void {
  storage?.removeItem(WORKBENCH_AUTH_STORAGE_KEY)
}

export function readWorkbenchDemoMode(env: EnvLike = import.meta.env): boolean {
  return env.VITE_SEXTANT_ENABLE_DEMO === "true"
}

async function readAuthErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { error_description?: unknown; msg?: unknown; message?: unknown }
    const message =
      typeof payload.error_description === "string"
        ? payload.error_description
        : typeof payload.message === "string"
          ? payload.message
          : typeof payload.msg === "string"
            ? payload.msg
            : null
    return message?.trim() || response.statusText || `HTTP ${response.status}`
  } catch {
    return response.statusText || `HTTP ${response.status}`
  }
}

function defaultWorkbenchAuthStorage(): StorageLike | null {
  if (typeof window === "undefined") return null
  return window.localStorage
}

type WorkbenchActionContext = Pick<
  ActionRequestCreateBody,
  "source_id" | "source_version_id" | "scene_id" | "pov_character_id"
>

type WorkbenchContextPackPosition = Pick<
  BuildWritingContextPackBody,
  "current_source_id" | "current_version_id" | "current_scene_id" | "current_pov_character_id"
>

function workbenchActionContext(config: WorkbenchApiConfig): WorkbenchActionContext {
  return {
    source_id: config.sourceId,
    source_version_id: config.sourceVersionId,
    ...(config.sceneId ? { scene_id: config.sceneId } : {}),
    ...(config.povCharacterId ? { pov_character_id: config.povCharacterId } : {}),
  }
}

function workbenchContextPackPosition(
  config: WorkbenchApiConfig,
): WorkbenchContextPackPosition {
  return {
    current_source_id: config.sourceId,
    current_version_id: config.sourceVersionId,
    ...(config.sceneId ? { current_scene_id: config.sceneId } : {}),
    ...(config.povCharacterId ? { current_pov_character_id: config.povCharacterId } : {}),
  }
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function formatContextRefLabel(value: unknown): string {
  if (!isPlainRecord(value)) {
    return ""
  }

  const label =
    stringRefField(value.label) ??
    stringRefField(value.display_name) ??
    stringRefField(value.name) ??
    stringRefField(value.title)
  if (label) {
    return label
  }

  const slug = stringRefField(value.slug)
  if (slug) {
    return slug
  }

  const id = stringRefField(value.id)
  if (id && !UUID_PATTERN.test(id)) {
    return id
  }

  return stringRefField(value.type) ?? ""
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function stringRefField(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null
}

export async function requestRewriteCandidate(
  client: RewriteClient,
  config: WorkbenchApiConfig,
  input: {
    text: string
    range: TextRange
    actorIntent: string
    currentTextWindow: string
  },
  newId: IdFactory = createId,
): Promise<CandidateDetailResponse> {
  const headers = writeHeaders(config, newId())
  const actionRequest: ActionRequestResponse = await idempotentWriteWithRetry(() => client.submitActionRequest(
    config.projectId,
    {
      trigger: "selection",
      action_type: "rewrite_span",
      target: {
        kind: "selected_text",
        source_id: config.sourceId,
        source_version_id: config.sourceVersionId,
        range: input.range,
        selected_text: input.text,
      },
      constraints: { ui_surface: "workbench.selection_menu" },
      expected_output: "draft_candidate",
      actor_intent: input.actorIntent,
      ...workbenchActionContext(config),
    },
    headers,
  ))
  const run: ActionRequestRunResponse = await idempotentWriteWithRetry(() => client.runActionRequest(
    config.projectId,
    actionRequest.action_request_id,
    { current_text_window: input.currentTextWindow },
    headers,
  ))
  const candidateId = run.draft_candidate_ids[0]
  if (!candidateId) {
    throw new Error("ActionRequest returned no DraftCandidate.")
  }
  return readWithRetry(() => client.getCandidate(config.projectId, candidateId, readHeaders(config)))
}

export async function requestContinuationCandidate(
  client: RewriteClient,
  config: WorkbenchApiConfig,
  input: {
    actorIntent: string
    currentTextWindow: string
    insertOffset: number
  },
  newId: IdFactory = createId,
): Promise<CandidateDetailResponse> {
  const headers = writeHeaders(config, newId())
  const actionRequest: ActionRequestResponse = await idempotentWriteWithRetry(() => client.submitActionRequest(
    config.projectId,
    {
      trigger: "natural_language",
      action_type: "continue_small_passage",
      target: {
        kind: "current_position",
        source_id: config.sourceId,
        source_version_id: config.sourceVersionId,
        range: {
          start: input.insertOffset,
          end: input.insertOffset,
        },
      },
      constraints: {
        ui_surface: "workbench.ask_palette",
      },
      expected_output: "draft_candidate",
      actor_intent: input.actorIntent,
      ...workbenchActionContext(config),
    },
    headers,
  ))
  const run: ActionRequestRunResponse = await idempotentWriteWithRetry(() => client.runActionRequest(
    config.projectId,
    actionRequest.action_request_id,
    { current_text_window: input.currentTextWindow },
    headers,
  ))
  const candidateId = run.draft_candidate_ids[0]
  if (!candidateId) {
    throw new Error("ActionRequest returned no DraftCandidate.")
  }
  return readWithRetry(() => client.getCandidate(config.projectId, candidateId, readHeaders(config)))
}

export async function loadWorkbenchSource(
  client: SourceClient,
  config: WorkbenchApiConfig,
): Promise<SourceVersionResponse> {
  return readWithRetry(() =>
    client.getSourceVersion(
      config.projectId,
      config.sourceId,
      config.sourceVersionId,
      readHeaders(config),
    ),
  )
}

export async function loadWorkbenchProjectMembers(
  client: ProjectMemberClient,
  config: WorkbenchApiConfig,
): Promise<ProjectMemberListResponse["items"]> {
  return (await readWithRetry(() => client.listProjectMembers(config.projectId, readHeaders(config)))).items
}

export async function upsertWorkbenchProjectMember(
  client: ProjectMemberClient,
  config: WorkbenchApiConfig,
  memberActorId: UUID,
  role: WorkbenchProjectMemberRole,
  newId: IdFactory = createId,
): Promise<ProjectMemberOperationResponse> {
  return client.upsertProjectMember(
    config.projectId,
    memberActorId,
    { role },
    writeHeaders(config, newId()),
  )
}

export async function revokeWorkbenchProjectMember(
  client: ProjectMemberClient,
  config: WorkbenchApiConfig,
  memberActorId: UUID,
  newId: IdFactory = createId,
): Promise<ProjectMemberOperationResponse> {
  return client.revokeProjectMember(config.projectId, memberActorId, writeHeaders(config, newId()))
}

export async function listWorkbenchProjectInvitations(
  client: ProjectInvitationClient,
  config: WorkbenchApiConfig,
): Promise<ProjectInvitationListResponse["items"]> {
  return (
    await readWithRetry(() => client.listProjectInvitations(config.projectId, readHeaders(config)))
  ).items
}

export async function createWorkbenchProjectInvitation(
  client: ProjectInvitationClient,
  config: WorkbenchApiConfig,
  input: WorkbenchProjectInvitationInput,
  newId: IdFactory = createId,
): Promise<ProjectInvitationResponse> {
  const body: ProjectInvitationCreateBody = {
    member_actor_id: input.memberActorId,
    role: input.role,
    delivery_provider_ref: input.deliveryProviderRef,
    delivery_target_ref: input.deliveryTargetRef,
    token_issuer_ref: input.tokenIssuerRef?.trim() || null,
  }
  return client.createProjectInvitation(config.projectId, body, writeHeaders(config, newId()))
}

export async function recordWorkbenchProjectInvitationExternalProof(
  client: ProjectInvitationClient,
  config: WorkbenchApiConfig,
  invitationId: UUID,
  input: WorkbenchProjectInvitationProofInput,
  newId: IdFactory = createId,
): Promise<ProjectInvitationResponse> {
  const body: ProjectInvitationExternalProofBody = {
    delivery_proof_ref: input.deliveryProofRef,
    token_proof_ref: input.tokenProofRef?.trim() || null,
  }
  return client.recordProjectInvitationExternalProof(
    config.projectId,
    invitationId,
    body,
    writeHeaders(config, newId()),
  )
}

export async function loadWorkbenchSourceVersions(
  client: SourceVersionListClient,
  config: WorkbenchApiConfig,
): Promise<SourceVersionListResponse["items"]> {
  return (
    await readWithRetry(() => client.listSourceVersions(
      config.projectId,
      config.sourceId,
      readHeaders(config),
      { limit: 12 },
    ))
  ).items
}

export async function loadWorkbenchSourceVersionDiff(
  client: SourceVersionDiffClient,
  config: WorkbenchApiConfig,
  baseVersionId: UUID,
  compareVersionId: UUID,
): Promise<SourceVersionDiffResponse> {
  return readWithRetry(() =>
    client.getSourceVersionDiff(
      config.projectId,
      config.sourceId,
      baseVersionId,
      compareVersionId,
      readHeaders(config),
    ),
  )
}

export async function loadWorkbenchSources(
  client: SourceListClient,
  config: WorkbenchApiConfig,
  query = "",
): Promise<SourceListResponse["items"]> {
  return (
    await readWithRetry(() => client.listSources(
      config.projectId,
      readHeaders(config),
      { query, limit: 20 },
    ))
  ).items
}

export async function createWorkbenchSource(
  client: SourceCreateClient,
  config: WorkbenchApiConfig,
  input: WorkbenchSourceCreateInput,
  newId: IdFactory = createId,
): Promise<CreateSourceResponse> {
  return client.createSource(
    config.projectId,
    {
      title: input.title,
      source_type: input.sourceType,
      source_scope: input.sourceScope,
      ownership_status: "owned",
      text: input.text,
      version_label: "v1",
    },
    writeHeaders(config, newId()),
  )
}

export async function archiveWorkbenchSource(
  client: SourceArchiveClient,
  config: WorkbenchApiConfig,
  sourceId: UUID,
  newId: IdFactory = createId,
): Promise<ArchiveSourceResponse> {
  return client.archiveSource(
    config.projectId,
    sourceId,
    { author_note: "作者将材料从当前项目列表归档；证据和版本仍保留。" },
    writeHeaders(config, newId()),
  )
}

export async function restoreWorkbenchSourceVersion(
  client: SourceRestoreClient,
  config: WorkbenchApiConfig,
  versionId: UUID,
  newId: IdFactory = createId,
): Promise<RestoreSourceVersionResponse> {
  return client.restoreSourceVersion(
    config.projectId,
    config.sourceId,
    versionId,
    { author_note: "作者从正文版本历史恢复此版本。" },
    writeHeaders(config, newId()),
  )
}

export async function saveWorkbenchSourceEdit(
  client: SourceEditClient,
  config: WorkbenchApiConfig,
  source: SourceVersionResponse,
  nextText: string,
  newId: IdFactory = createId,
): Promise<CreateSourceDeltaResponse> {
  const delta = sourceEditDelta(source.text, nextText)
  return client.createSourceDelta(
    config.projectId,
    source.source_id,
    source.version_id,
    {
      delta_kind: delta.deltaKind,
      range_start: delta.rangeStart,
      range_end: delta.rangeEnd,
      base_hash: source.raw_hash,
      submitted_text: delta.submittedText,
      source_type: source.source_type,
      source_scope: source.source_scope,
      provenance: {
        source_edit_surface: "workbench_editor",
        previous_version_id: source.version_id,
      },
    },
    writeHeaders(config, newId()),
  )
}

export async function loadWorkbenchSourceDeltas(
  client: SourceDeltaListClient,
  config: WorkbenchApiConfig,
  filters: WorkbenchSourceDeltaFilters = {},
): Promise<SourceDeltaListResponse["items"]> {
  return (await loadWorkbenchSourceDeltaPage(client, config, filters)).items
}

export async function loadWorkbenchSourceDeltaPage(
  client: SourceDeltaListClient,
  config: WorkbenchApiConfig,
  filters: WorkbenchSourceDeltaFilters = {},
): Promise<SourceDeltaListResponse> {
  const options: NonNullable<Parameters<SourceDeltaListClient["listSourceDeltas"]>[2]> = {
    sourceId: config.sourceId,
    limit: 10,
  }
  if (filters.sourceVersionId) options.sourceVersionId = filters.sourceVersionId
  if (filters.query) options.query = filters.query
  if (filters.status) options.status = filters.status
  if (filters.deltaKind) options.deltaKind = filters.deltaKind
  if (filters.cursor) options.cursor = filters.cursor
  if (filters.acceptedOnly !== undefined) options.acceptedOnly = filters.acceptedOnly
  return readWithRetry(() => client.listSourceDeltas(config.projectId, readHeaders(config), options))
}

export async function loadWorkbenchSourceDeltaDetail(
  client: SourceDeltaDetailClient,
  config: WorkbenchApiConfig,
  sourceDeltaId: UUID,
): Promise<SourceDeltaDetailResponse> {
  return readWithRetry(() => client.getSourceDelta(config.projectId, sourceDeltaId, readHeaders(config)))
}

function sourceEditDelta(
  previousText: string,
  nextText: string,
): { deltaKind: "insert" | "replace" | "delete"; rangeStart: number; rangeEnd: number; submittedText: string } {
  const previous = Array.from(previousText)
  const next = Array.from(nextText)
  let start = 0
  while (start < previous.length && start < next.length && previous[start] === next[start]) {
    start += 1
  }
  if (start === previous.length && start === next.length) {
    throw new Error("正文没有变化。")
  }
  let previousEnd = previous.length
  let nextEnd = next.length
  while (
    previousEnd > start &&
    nextEnd > start &&
    previous[previousEnd - 1] === next[nextEnd - 1]
  ) {
    previousEnd -= 1
    nextEnd -= 1
  }
  const submittedText = next.slice(start, nextEnd).join("")
  const removedLength = previousEnd - start
  const deltaKind = submittedText.length === 0 ? "delete" : removedLength === 0 ? "insert" : "replace"
  return {
    deltaKind,
    rangeStart: start,
    rangeEnd: previousEnd,
    submittedText,
  }
}

export async function loadLatestAcceptedText(
  client: SourceDeltaListClient,
  config: WorkbenchApiConfig,
): Promise<string | null> {
  const latest = (await loadWorkbenchSourceDeltas(client, config)).find(
    (delta) => Boolean(delta.accepted_fragment_id),
  )
  return latest?.submitted_text_preview ?? null
}

export async function loadWorkbenchReviewItems(
  client: ReviewListClient,
  config: WorkbenchApiConfig,
  status = "open",
): Promise<ReviewItemListResponse["items"]> {
  return (
    await readWithRetry(() => client.listReviewItems(config.projectId, readHeaders(config), status))
  ).items
}

export async function loadWorkbenchContextPack(
  client: ContextPackClient,
  config: WorkbenchApiConfig,
  contextPackId: UUID,
): Promise<WritingContextPackResponse> {
  return readWithRetry(() => client.getContextPack(config.projectId, contextPackId, readHeaders(config)))
}

export async function loadWorkbenchContextPackReadiness(
  client: ContextPackReadinessClient,
  config: WorkbenchApiConfig,
  options: {
    status?: "pending" | "stale" | "consumed" | null
    reason?: string | null
    sourceDeltaId?: UUID | null
    limit?: number
  } = {},
): Promise<ContextPackReadinessListResponse> {
  const requestOptions: {
    status?: string | null
    reason?: string | null
    sourceDeltaId?: UUID | null
    limit?: number
  } = {
    limit: options.limit ?? 20,
  }
  if ("status" in options) {
    if (options.status) requestOptions.status = options.status
  } else {
    requestOptions.status = "pending"
  }
  if (options.reason) requestOptions.reason = options.reason
  if (options.sourceDeltaId) requestOptions.sourceDeltaId = options.sourceDeltaId
  return readWithRetry(() =>
    client.listContextPackReadiness(config.projectId, readHeaders(config), requestOptions),
  )
}

export async function buildWorkbenchContextPack(
  client: ContextPackClient & Pick<SextantApiClient, "buildContextPack">,
  config: WorkbenchApiConfig,
  input: { mode: string; currentTextWindow: string },
  newId: IdFactory = createId,
): Promise<WritingContextPackResponse> {
  return idempotentWriteWithRetry(() => client.buildContextPack(
    config.projectId,
    {
      ...workbenchContextPackPosition(config),
      mode: input.mode,
      current_text_window: input.currentTextWindow,
    },
    writeHeaders(config, newId()),
  ))
}

export async function answerWorkbenchMemory(
  client: MemoryAnswerClient,
  config: WorkbenchApiConfig,
  question: string,
  targetOrNewId: AskMemoryTarget | IdFactory = createId,
  maybeNewId?: IdFactory,
): Promise<MemoryAnswerResponse> {
  const memoryTarget = typeof targetOrNewId === "function" ? {} : targetOrNewId
  const newId = typeof targetOrNewId === "function" ? targetOrNewId : (maybeNewId ?? createId)
  const constraints: Record<string, unknown> = {
    ui_surface: "workbench.ask_palette",
    question,
  }
  if (memoryTarget.subjectRef) {
    constraints.subject_ref = memoryTarget.subjectRef
  }
  if (memoryTarget.predicate) {
    constraints.predicate = memoryTarget.predicate
  }
  const headers = writeHeaders(config, newId())
  const actionRequest: ActionRequestResponse = await idempotentWriteWithRetry(() => client.submitActionRequest(
    config.projectId,
    {
      trigger: "natural_language",
      action_type: "ask_memory",
      target: null,
      constraints,
      expected_output: "memory_answer",
      actor_intent: question,
      ...workbenchActionContext(config),
    },
    headers,
  ))
  const run: ActionRequestRunResponse = await idempotentWriteWithRetry(() => client.runActionRequest(
    config.projectId,
    actionRequest.action_request_id,
    { current_text_window: "" },
    headers,
  ))
  if (!run.memory_answer) {
    throw new Error("ActionRequest returned no MemoryAnswer.")
  }
  return run.memory_answer
}

export async function requestRiskCheck(
  client: RiskCheckClient,
  config: WorkbenchApiConfig,
  input: {
    actorIntent: string
    currentTextWindow: string
    range?: TextRange
  },
  newId: IdFactory = createId,
): Promise<AgentReviewFindingResponse[]> {
  const headers = writeHeaders(config, newId())
  const range = input.range ?? { start: 0, end: input.currentTextWindow.length }
  const actionRequest: ActionRequestResponse = await idempotentWriteWithRetry(() => client.submitActionRequest(
    config.projectId,
    {
      trigger: "natural_language",
      action_type: "check_risk",
      target: {
        kind: "selected_text",
        source_id: config.sourceId,
        source_version_id: config.sourceVersionId,
        range,
        selected_text: input.currentTextWindow,
      },
      constraints: { ui_surface: "workbench.ask_palette" },
      expected_output: "risk_findings",
      actor_intent: input.actorIntent,
      ...workbenchActionContext(config),
    },
    headers,
  ))
  const run: ActionRequestRunResponse = await idempotentWriteWithRetry(() => client.runActionRequest(
    config.projectId,
    actionRequest.action_request_id,
    { current_text_window: input.currentTextWindow },
    headers,
  ))
  return run.risk_findings ?? []
}

export async function requestNextDirection(
  client: BeatCandidateClient,
  config: WorkbenchApiConfig,
  input: {
    actorIntent: string
    currentTextWindow: string
    insertOffset: number
  },
  newId: IdFactory = createId,
): Promise<BeatCandidateResponse[]> {
  const headers = writeHeaders(config, newId())
  const actionRequest: ActionRequestResponse = await idempotentWriteWithRetry(() => client.submitActionRequest(
    config.projectId,
    {
      trigger: "natural_language",
      action_type: "suggest_next_direction",
      target: {
        kind: "cursor_position",
        source_id: config.sourceId,
        source_version_id: config.sourceVersionId,
        range: {
          start: input.insertOffset,
          end: input.insertOffset,
        },
      },
      constraints: { ui_surface: "workbench.ask_palette" },
      expected_output: "beat_candidates",
      actor_intent: input.actorIntent,
      ...workbenchActionContext(config),
    },
    headers,
  ))
  const run: ActionRequestRunResponse = await idempotentWriteWithRetry(() => client.runActionRequest(
    config.projectId,
    actionRequest.action_request_id,
    { current_text_window: input.currentTextWindow },
    headers,
  ))
  return run.beat_candidates ?? []
}

export async function loadWorkbenchMemoryPages(
  client: MemoryPageClient,
  config: WorkbenchApiConfig,
  filters: WorkbenchMemoryPageFilters = {},
): Promise<MemoryPageListResponse["items"]> {
  return (
    await readWithRetry(() => client.listMemoryPages(
      config.projectId,
      readHeaders(config),
      {
        pageType: filters.pageType,
        canonStatus: filters.canonStatus,
        limit: 20,
      },
    ))
  ).items
}

export async function loadWorkbenchMemoryPageDetail(
  client: MemoryPageClient,
  config: WorkbenchApiConfig,
  memoryPageId: UUID,
): Promise<MemoryPageDetailResponse> {
  return readWithRetry(() => client.getMemoryPage(config.projectId, memoryPageId, readHeaders(config)))
}

export async function operateWorkbenchMemoryPageThread(
  client: MemoryPageThreadOperationClient,
  config: WorkbenchApiConfig,
  memoryPageId: UUID,
  input: WorkbenchMemoryPageThreadInput,
  newId: IdFactory = createId,
): Promise<MemoryPageThreadOperationResponse> {
  return idempotentWriteWithRetry(() =>
    client.operateMemoryPageOpenThread(
      config.projectId,
      memoryPageId,
      input.threadId,
      {
        update_type: input.updateType,
        author_note: input.authorNote,
        ...(input.summary ? { summary: input.summary } : {}),
      },
      writeHeaders(config, newId()),
    ),
  )
}

export async function loadWorkbenchGraphProjectionEdges(
  client: GraphProjectionClient,
  config: WorkbenchApiConfig,
  filters: WorkbenchGraphEdgeFilters = {},
): Promise<GraphProjectionEdgeListResponse["items"]> {
  return (
    await readWithRetry(() =>
      client.listGraphProjectionEdges(config.projectId, readHeaders(config), {
        q: filters.query,
        relation: filters.relation,
        edgeStatus: filters.edgeStatus,
        limit: 30,
      }),
    )
  ).items
}

export async function acceptCandidateText(
  client: AcceptClient,
  config: WorkbenchApiConfig,
  candidate: CandidateDetailResponse,
  acceptedText: string,
  newId: IdFactory = createId,
): Promise<CandidateAcceptResponse> {
  if (
    candidate.status === "blocked" ||
    (candidate.agent_review_findings.some(
      (finding) => finding.risk_level === "high" && !finding.can_offer_to_author,
    ) && !candidate.override_reason)
  ) {
    throw new Error("Blocked candidate requires override before accept.")
  }
  if (!candidate.target_source_id || !candidate.target_version_id) {
    throw new Error("Candidate is missing target source information.")
  }
  if (!candidate.affected_range) {
    throw new Error("Candidate is missing an affected range.")
  }
  const targetSourceId = candidate.target_source_id
  const targetVersionId = candidate.target_version_id
  const affectedRange = candidate.affected_range

  return idempotentWriteWithRetry(() => client.acceptCandidate(
    config.projectId,
    candidate.id,
    {
      accepted_text_ref: null,
      accepted_text: acceptedText,
      accept_mode: "partial",
      target_source_id: targetSourceId,
      target_version_id: targetVersionId,
      insert_or_replace_range: affectedRange,
      base_hash: candidate.base_hash,
      source_type: "draft_manuscript",
      source_scope: "user_draft",
      author_edited: true,
    },
    writeHeaders(config, newId()),
  ))
}

export function isWorkbenchStaleSourceVersionError(error: unknown): boolean {
  if (!error || typeof error !== "object" || !("code" in error)) {
    return false
  }
  return (error as { code?: unknown }).code === "stale_source_version"
}

export function workbenchErrorMessage(
  error: unknown,
  fallback = "请求系统失败，请稍后重试。",
): string {
  if (isWorkbenchStaleSourceVersionError(error)) {
    return STALE_SOURCE_VERSION_MESSAGE
  }
  if (error instanceof Error) {
    return error.message
  }
  return fallback
}

export async function readWorkbenchWritebackState(
  client: WritebackClient,
  config: WorkbenchApiConfig,
  acceptance: CandidateAcceptResponse,
): Promise<WorkbenchWritebackState> {
  const headers = readHeaders(config)
  const [job, preview, reviews] = await Promise.all([
    readWithRetry(() => client.getJob(config.projectId, acceptance.memory_writeback_job_id, headers)),
    readWithRetry(() =>
      client.getMemoryWritebackPreview(config.projectId, acceptance.source_delta_id, headers),
    ),
    readWithRetry(() => client.listReviewItems(config.projectId, headers, "open")),
  ])
  return { job, preview, reviewItems: reviews.items }
}

export async function cancelWorkbenchJob(
  client: JobOperationClient,
  config: WorkbenchApiConfig,
  jobId: UUID,
  authorNote: string | null = null,
  newId: IdFactory = createId,
): Promise<JobDetailResponse> {
  return client.cancelJob(
    config.projectId,
    jobId,
    { author_note: authorNote },
    writeHeaders(config, newId()),
  )
}

export async function retryWorkbenchJob(
  client: JobOperationClient,
  config: WorkbenchApiConfig,
  jobId: UUID,
  authorNote: string | null = null,
  newId: IdFactory = createId,
): Promise<JobDetailResponse> {
  return client.retryJob(
    config.projectId,
    jobId,
    { author_note: authorNote },
    writeHeaders(config, newId()),
  )
}

export async function decideWorkbenchWritebackItem(
  client: WritebackDecisionClient,
  config: WorkbenchApiConfig,
  acceptance: CandidateAcceptResponse,
  input: WorkbenchWritebackDecisionInput,
  newId: IdFactory = createId,
): Promise<MemoryWritebackDecisionResponse> {
  return idempotentWriteWithRetry(() => client.decideMemoryWritebackPreview(
    config.projectId,
    acceptance.source_delta_id,
    {
      item_ref: input.itemRef,
      decision: input.decision,
      author_note: input.authorNote ?? null,
      correction: input.correction ?? {},
      replacement_refs: input.replacementRefs ?? [],
    },
    writeHeaders(config, newId()),
  ))
}

export async function loadReviewItemDetail(
  client: ReviewDetailClient,
  config: WorkbenchApiConfig,
  reviewItemId: UUID,
): Promise<ReviewItemDetailResponse> {
  return readWithRetry(() => client.getReviewItem(config.projectId, reviewItemId, readHeaders(config)))
}

export async function loadWorkbenchEntities(
  client: EntityListClient,
  config: WorkbenchApiConfig,
  filters: { query?: string; entityType?: string; limit?: number } = {},
): Promise<CanonicalEntityListResponse> {
  return readWithRetry(() =>
    client.listEntities(config.projectId, readHeaders(config), {
      q: filters.query,
      entity_type: filters.entityType,
      limit: filters.limit,
    }),
  )
}

export async function loadWorkbenchSceneOptions(
  client: SceneListClient,
  config: WorkbenchApiConfig,
): Promise<StorySceneListResponse> {
  return readWithRetry(() =>
    client.listScenes(config.projectId, readHeaders(config), {
      source_id: config.sourceId,
      version_id: config.sourceVersionId,
      limit: 100,
    }),
  )
}

export async function loadWorkbenchStorySchema(
  client: StorySchemaClient,
  config: WorkbenchApiConfig,
): Promise<ProjectStorySchemaResponse> {
  return readWithRetry(() => client.getProjectStorySchema(config.projectId, readHeaders(config)))
}

export async function loadWorkbenchStorySchemaPacks(
  client: StorySchemaClient,
  config: WorkbenchApiConfig,
  packType = "genre",
): Promise<StorySchemaPackListResponse["items"]> {
  const response = await readWithRetry(() =>
    client.listStorySchemaPacks(config.projectId, readHeaders(config), { packType }),
  )
  return response.items
}

export async function selectWorkbenchStorySchemaGenrePack(
  client: StorySchemaWriteClient,
  config: WorkbenchApiConfig,
  genreSchemaPackId: UUID | null,
  newId: IdFactory = createId,
): Promise<ProjectStorySchemaResponse> {
  const body: ProjectStorySchemaGenreBody = {
    genre_schema_pack_id: genreSchemaPackId,
  }
  return client.selectProjectStorySchemaGenrePack(
    config.projectId,
    body,
    writeHeaders(config, newId()),
  )
}

export async function upsertWorkbenchStorySchemaOverride(
  client: StorySchemaWriteClient,
  config: WorkbenchApiConfig,
  input: WorkbenchStorySchemaOverrideInput,
  newId: IdFactory = createId,
): Promise<ProjectStorySchemaResponse> {
  const body: ProjectStorySchemaOverrideBody = {
    pack_name: input.packName ?? "project-overrides",
    entity_types: input.entityTypes ?? [],
    event_types: input.eventTypes ?? [],
    relations: input.relations ?? [],
    extraction_hints: input.extractionHints ?? {},
    risk_rules: input.riskRules ?? {},
  }
  return client.upsertProjectStorySchemaOverride(
    config.projectId,
    body,
    writeHeaders(config, newId()),
  )
}

export async function operateWorkbenchReviewItem(
  client: ReviewOperationClient,
  config: WorkbenchApiConfig,
  reviewItemId: UUID,
  input: {
    operation: "resolve" | "dismiss" | "reopen"
    resolution?: ReviewResolution
    authorNote?: string | null
    replacementRefs?: Record<string, unknown>[]
    correction?: Record<string, unknown>
  },
  newId: IdFactory = createId,
): Promise<void> {
  const headers = writeHeaders(config, newId())
  if (input.operation === "resolve") {
    const resolution = input.resolution ?? "accepted_as_change"
    await idempotentWriteWithRetry(() => client.resolveReviewItem(
      config.projectId,
      reviewItemId,
      {
        resolution,
        author_note:
          input.authorNote?.trim() ||
          `作者确认此复核已按「${reviewResolutionLabel(resolution)}」处理。`,
        replacement_refs: input.replacementRefs ?? [],
        correction: input.correction ?? {},
      },
      headers,
    ))
    return
  }
  if (input.operation === "reopen") {
    await idempotentWriteWithRetry(() => client.reopenReviewItem(
      config.projectId,
      reviewItemId,
      { author_note: "作者重新打开此复核。" },
      headers,
    ))
    return
  }
  await idempotentWriteWithRetry(() => client.dismissReviewItem(
    config.projectId,
    reviewItemId,
    { author_note: "作者暂不处理此复核。" },
    headers,
  ))
}

export async function rejectWorkbenchCandidate(
  client: CandidateOperationClient,
  config: WorkbenchApiConfig,
  candidateId: UUID,
  newId: IdFactory = createId,
): Promise<CandidateOperationResponse> {
  return client.rejectCandidate(
    config.projectId,
    candidateId,
    { author_note: "作者退回这个候选。" },
    writeHeaders(config, newId()),
  )
}

export async function explainWorkbenchCandidate(
  client: CandidateExplainClient,
  config: WorkbenchApiConfig,
  candidateId: UUID,
  newId: IdFactory = createId,
): Promise<CandidateDetailResponse> {
  const headers = writeHeaders(config, newId())
  const actionRequest: ActionRequestResponse = await idempotentWriteWithRetry(() => client.submitActionRequest(
    config.projectId,
    {
      trigger: "candidate_action",
      action_type: "explain_candidate",
      target: { kind: "candidate", candidate_id: candidateId },
      constraints: { ui_surface: "workbench.candidate_drawer" },
      expected_output: "candidate_explanation",
      actor_intent: "为什么这个候选合理？",
      ...workbenchActionContext(config),
    },
    headers,
  ))
  const run: ActionRequestRunResponse = await idempotentWriteWithRetry(() => client.runActionRequest(
    config.projectId,
    actionRequest.action_request_id,
    { current_text_window: "" },
    headers,
  ))
  if (!run.candidate_explanation) {
    throw new Error("ActionRequest returned no CandidateExplanation.")
  }
  return readWithRetry(() => client.getCandidate(config.projectId, candidateId, readHeaders(config)))
}

export async function overrideWorkbenchCandidateBlock(
  client: CandidateOperationClient,
  config: WorkbenchApiConfig,
  candidateId: UUID,
  overrideReason: string,
  newId: IdFactory = createId,
): Promise<CandidateDetailResponse> {
  await idempotentWriteWithRetry(() => client.overrideCandidateBlock(
    config.projectId,
    candidateId,
    { override_reason: overrideReason },
    writeHeaders(config, newId()),
  ))
  return readWithRetry(() => client.getCandidate(config.projectId, candidateId, readHeaders(config)))
}

export async function reviseWorkbenchCandidate(
  client: CandidateReviseClient,
  config: WorkbenchApiConfig,
  candidateId: UUID,
  revisionInstruction: string,
  newId: IdFactory = createId,
): Promise<CandidateDetailResponse> {
  const headers = writeHeaders(config, newId())
  const actionRequest: ActionRequestResponse = await idempotentWriteWithRetry(() => client.submitActionRequest(
    config.projectId,
    {
      trigger: "candidate_action",
      action_type: "revise_candidate",
      target: { kind: "candidate", candidate_id: candidateId },
      constraints: { ui_surface: "workbench.candidate_drawer" },
      expected_output: "draft_candidate",
      actor_intent: "按作者选择的修订文本重写候选。",
      ...workbenchActionContext(config),
    },
    headers,
  ))
  const run: ActionRequestRunResponse = await idempotentWriteWithRetry(() => client.runActionRequest(
    config.projectId,
    actionRequest.action_request_id,
    { current_text_window: revisionInstruction },
    headers,
  ))
  const replacementCandidateId = run.draft_candidate_ids[0]
  if (!replacementCandidateId) {
    throw new Error("ActionRequest returned no replacement DraftCandidate.")
  }
  return readWithRetry(() => client.getCandidate(
    config.projectId,
    replacementCandidateId,
    readHeaders(config),
  ))
}

export function toDrawerCandidate(candidate: CandidateDetailResponse): Candidate {
  const findings = candidate.agent_review_findings
  const highestRisk = findings.find((finding) => finding.risk_level === "high")
    ?? findings.find((finding) => finding.risk_level === "medium")
    ?? findings.find((finding) => finding.risk_level === "low")
  return {
    id: candidate.id,
    label: candidate.status === "blocked" ? "需确认" : "候选",
    direction: modeLabel(candidate.mode),
    sentences: splitCandidateSentences(candidate.text).map((text, index) => ({
      id: `${candidate.id}-${index}`,
      text,
    })),
    usedMemory: candidate.evidence_refs.map(refLabel).filter(Boolean),
    avoided: findings.map((finding) => finding.summary),
    risk: highestRisk
      ? {
          level: riskLevel(highestRisk.risk_level),
          note: highestRisk.summary,
        }
      : null,
  }
}

export function toDrawerRiskCandidates(findings: AgentReviewFindingResponse[]): Candidate[] {
  if (findings.length === 0) {
    return [
      {
        id: "risk-none",
        label: "风险",
        direction: "未发现需要拦截的风险",
        sentences: [],
        usedMemory: [],
        avoided: ["没有写入正文或 Memory"],
        risk: { level: "low", note: "本次检查没有返回风险项" },
      },
    ]
  }

  return findings.map((finding, index) => ({
    id: finding.id,
    label: `风险 ${index + 1}`,
    direction: finding.summary,
    sentences: [],
    usedMemory: [
      ...recordLabels(finding.memory_refs),
      ...recordLabels(finding.storytelling_refs),
    ],
    avoided: [
      finding.suggested_revision ?? "不把风险检查结果写入 Memory 或 Canon",
    ],
    risk: {
      level: riskLevel(finding.risk_level),
      note: `${finding.risk_type} · ${finding.summary}`,
    },
  }))
}

export function toDrawerBeatCandidates(beats: BeatCandidateResponse[]): Candidate[] {
  if (beats.length === 0) {
    return [
      {
        id: "beat-none",
        label: "方向",
        direction: "暂时没有可用的下一步方向",
        sentences: [],
        usedMemory: [],
        avoided: ["需要先生成正文候选，再由作者采纳"],
        risk: null,
      },
    ]
  }

  return beats.map((beat, index) => {
    const highestRisk = beat.agent_review_findings.find((finding) => finding.risk_level === "high")
      ?? beat.agent_review_findings.find((finding) => finding.risk_level === "medium")
      ?? beat.agent_review_findings.find((finding) => finding.risk_level === "low")
    return {
      id: beat.id,
      label: `方向 ${index + 1}`,
      direction: beat.summary,
      sentences: [],
      usedMemory: [
        ...beat.memory_refs.map(refLabel),
        ...beat.evidence_refs.map(refLabel),
      ].filter(Boolean),
      avoided: [
        beat.agency_rationale ? `角色能动性：${beat.agency_rationale}` : "",
        beat.storytelling_rationale ? `叙事控制：${beat.storytelling_rationale}` : "",
      ].filter(Boolean),
      risk: highestRisk
        ? {
            level: riskLevel(highestRisk.risk_level),
            note: highestRisk.summary,
          }
        : null,
    }
  })
}

function readHeaders(config: WorkbenchApiConfig): ReadHeaders {
  return {
    actorId: config.actorId,
    ...(config.bearerToken ? { bearerToken: config.bearerToken } : {}),
  }
}

function writeHeaders(config: WorkbenchApiConfig, id: string): WriteHeaders {
  return {
    ...readHeaders(config),
    requestId: `req-${id}`,
    idempotencyKey: `idem-${id}`,
  }
}

function createId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
}

async function readWithRetry<T>(operation: () => Promise<T>): Promise<T> {
  return transientFetchWithRetry(operation)
}

async function idempotentWriteWithRetry<T>(operation: () => Promise<T>): Promise<T> {
  return transientFetchWithRetry(operation)
}

async function transientFetchWithRetry<T>(operation: () => Promise<T>): Promise<T> {
  const retryDelaysMs = [150, 500]
  let lastError: unknown
  for (let attempt = 0; attempt <= retryDelaysMs.length; attempt += 1) {
    if (attempt > 0) {
      await delay(retryDelaysMs[attempt - 1])
    }
    try {
      return await operation()
    } catch (error) {
      lastError = error
      if (!isTransientFetchError(error)) {
        throw error
      }
    }
  }
  throw lastError
}

function isTransientFetchError(error: unknown): boolean {
  return error instanceof TypeError && error.message.toLowerCase().includes("fetch")
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function splitCandidateSentences(text: string): string[] {
  const matches = text.match(/[^。！？!?]+[。！？!?]?/g) ?? [text]
  return matches.map((sentence) => sentence.trim()).filter(Boolean)
}

function refLabel(ref: Record<string, unknown>): string {
  const readable = formatContextRefLabel(ref)
  const id = stringRefField(ref.id)
  const type = stringRefField(ref.type)
  if (id && type && UUID_PATTERN.test(id) && readable === type) {
    return `${type}:${id.slice(0, 8)}`
  }
  return readable
}

function recordLabels(record: Record<string, unknown>): string[] {
  return Object.values(record)
    .map((value) => {
      if (typeof value === "string") {
        return value
      }
      if (isRecord(value)) {
        return refLabel(value)
      }
      return ""
    })
    .filter(Boolean)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function riskLevel(level: string): RiskLevel {
  if (level === "low" || level === "medium" || level === "high") {
    return level
  }
  return "medium"
}

function modeLabel(mode: string): string {
  return {
    rewrite_span: "改写选区，保留证据边界",
    continue_small_passage: "续写小段，保持当前 POV",
    draft_next_passage: "续写下一段，先给候选",
    rewrite_current_page: "重写当前页，保留 base hash",
    render_current_beat: "把当前 beat 写成正文",
    revise_candidate: "修订候选，保留证据边界",
  }[mode] ?? mode
}
