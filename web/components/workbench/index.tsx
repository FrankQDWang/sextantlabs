"use client"

import { useState, useEffect, useCallback, useMemo, useRef, type FormEvent } from "react"
import { TopBar } from "./top-bar"
import { Editor } from "./editor"
import { SceneCard, type SceneCardState } from "./scene-card"
import { CandidateDrawer } from "./candidate-drawer"
import { AskPalette, type AskSuggestionContext } from "./ask-palette"
import { MemoryWriteback, type WritebackDecisionDetails } from "./memory-writeback"
import type { ReviewResolveDetails } from "./review-badge"
import { MemoryAnswerPanel } from "./memory-answer-panel"
import { MemoryPagePanel } from "./memory-page-panel"
import { ProjectPanel } from "./project-panel"
import { SelectionMenu } from "./selection-menu"
import { StateSwitcher, type DemoState } from "./state-switcher"
import {
  demoAcceptedSentence,
  demoAskSuggestionContext,
  demoSourceTitle,
  manuscript,
  project,
  reviewItems,
  type Candidate,
} from "@/lib/workbench-data"
import {
  acceptCandidateText,
  answerWorkbenchMemory,
  archiveWorkbenchSource,
  buildWorkbenchContextPack,
  createWorkbenchProjectInvitation,
  createWorkbenchSource,
  decideWorkbenchWritebackItem,
  explainWorkbenchCandidate,
  formatContextRefLabel,
  listWorkbenchProjectInvitations,
  loadReviewItemDetail,
  loadWorkbenchGraphProjectionEdges,
  loadWorkbenchMemoryPageDetail,
  loadWorkbenchMemoryPages,
  loadWorkbenchEntities,
  loadWorkbenchContextPack,
  loadWorkbenchContextPackReadiness,
  loadWorkbenchProjectMembers,
  loadWorkbenchSource,
  loadWorkbenchSourceVersionDiff,
  loadWorkbenchSourceDeltaDetail,
  loadWorkbenchSourceDeltaPage,
  loadWorkbenchSourceVersions,
  loadWorkbenchSources,
  loadWorkbenchStorySchema,
  loadWorkbenchStorySchemaPacks,
  loadWorkbenchReviewItems,
  loadWorkbenchSceneOptions,
  operateWorkbenchMemoryPageThread,
  operateWorkbenchReviewItem,
  overrideWorkbenchCandidateBlock,
  readStoredWorkbenchAuthSession,
  readWorkbenchAuthConfig,
  readWorkbenchWritebackState,
  readWorkbenchApiConfig,
  readWorkbenchDemoMode,
  rejectWorkbenchCandidate,
  recordWorkbenchProjectInvitationExternalProof,
  requestNextDirection,
  requestContinuationCandidate,
  requestRiskCheck,
  requestRewriteCandidate,
  restoreWorkbenchSourceVersion,
  revokeWorkbenchProjectMember,
  reviseWorkbenchCandidate,
  saveWorkbenchSourceEdit,
  selectWorkbenchStorySchemaGenrePack,
  signInWorkbenchWithPassword,
  isWorkbenchStaleSourceVersionError,
  toDrawerBeatCandidates,
  toDrawerCandidate,
  toDrawerRiskCandidates,
  upsertWorkbenchProjectMember,
  upsertWorkbenchStorySchemaOverride,
  writeStoredWorkbenchAuthSession,
  workbenchErrorMessage,
  type AskMemoryTarget,
  type ReviewResolution,
  type WorkbenchGraphEdgeFilters,
  type WorkbenchMemoryPageThreadInput,
  type WorkbenchProjectInvitationInput,
  type WorkbenchProjectInvitationProofInput,
  type WorkbenchProjectMemberRole,
  type WorkbenchStorySchemaOverrideInput,
  type WorkbenchSourceCreateInput,
  type WorkbenchSourceDeltaFilters,
  type WorkbenchMemoryPageFilters,
  type WorkbenchWritebackState,
} from "@/lib/workbench-api"
import {
  SextantApiClient,
  type CandidateAcceptResponse,
  type CandidateDetailResponse,
  type CanonicalEntitySummaryResponse,
  type ContextPackReadinessListResponse,
  type GraphProjectionEdgeListResponse,
  type MemoryPageDetailResponse,
  type MemoryPageListResponse,
  type MemoryAnswerResponse,
  type ProjectStorySchemaResponse,
  type ProjectInvitationListResponse,
  type ProjectMemberListResponse,
  type ReviewItemDetailResponse,
  type ReviewItemListResponse,
  type SourceDeltaDetailResponse,
  type SourceDeltaListResponse,
  type SourceListResponse,
  type SourceVersionDiffResponse,
  type SourceVersionListResponse,
  type SourceVersionResponse,
  type StorySceneSummaryResponse,
  type StorySchemaPackResponse,
  type UUID,
  type WritingContextPackResponse,
} from "@/src/generated/sextant-api"
import { formatRef as formatDisplayRef, humanizeIdentifier, predicateLabel } from "@/lib/workbench-display"

interface Selection {
  text: string
  x: number
  y: number
  range: { start: number; end: number }
}

const SOURCE_EDIT_STALE_MESSAGE =
  "正文版本已更新。请刷新最新正文版本后重新编辑；系统没有写入正文变更或记忆。"

export function Workbench() {
  const authConfig = useMemo(() => readWorkbenchAuthConfig(), [])
  const [authSession, setAuthSession] = useState(() => readStoredWorkbenchAuthSession())
  const configuredApiConfig = useMemo(
    () => readWorkbenchApiConfig(import.meta.env, { bearerToken: authSession?.accessToken }),
    [authSession?.accessToken],
  )
  const runtimeAuthRequired = Boolean(
    configuredApiConfig && authConfig && !configuredApiConfig.bearerToken,
  )
  const baseApiConfig = runtimeAuthRequired ? null : configuredApiConfig
  const demoMode = useMemo(() => !baseApiConfig && readWorkbenchDemoMode(), [baseApiConfig])
  const [authEmail, setAuthEmail] = useState("")
  const [authPassword, setAuthPassword] = useState("")
  const [authPending, setAuthPending] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)
  const [activeSourceVersionId, setActiveSourceVersionId] = useState<UUID | null>(
    () => baseApiConfig?.sourceVersionId ?? null,
  )
  const activeSourceVersionRef = useRef<UUID | null>(baseApiConfig?.sourceVersionId ?? null)
  const setCurrentSourceVersionId = useCallback((versionId: UUID | null) => {
    activeSourceVersionRef.current = versionId
    setActiveSourceVersionId(versionId)
  }, [])
  const apiConfig = useMemo(
    () =>
      baseApiConfig
        ? {
            ...baseApiConfig,
            sourceVersionId: activeSourceVersionId ?? baseApiConfig.sourceVersionId,
          }
        : null,
    [activeSourceVersionId, baseApiConfig],
  )
  const apiClient = useMemo(
    () => (baseApiConfig ? new SextantApiClient(baseApiConfig.apiBaseUrl) : null),
    [baseApiConfig],
  )

  // 真实、相互独立的交互状态
  const [selection, setSelection] = useState<Selection | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [projectOpen, setProjectOpen] = useState(false)
  const [memoryOpen, setMemoryOpen] = useState(false)
  const [askOpen, setAskOpen] = useState(false)
  const [writebackOpen, setWritebackOpen] = useState(false)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [acceptedSentence, setAcceptedSentence] = useState<string | null>(null)
  const [demoHighlight, setDemoHighlight] = useState(false)
  const [candidateDetail, setCandidateDetail] = useState<CandidateDetailResponse | null>(null)
  const [candidateLoading, setCandidateLoading] = useState(false)
  const [candidateError, setCandidateError] = useState<string | null>(null)
  const [candidateStaleSourceMessage, setCandidateStaleSourceMessage] = useState<string | null>(
    null,
  )
  const [candidateSourceRefreshPending, setCandidateSourceRefreshPending] = useState(false)
  const [candidateOperationPending, setCandidateOperationPending] = useState(false)
  const [candidateOperationStatus, setCandidateOperationStatus] = useState<string | null>(null)
  const [candidateOperationError, setCandidateOperationError] = useState<string | null>(null)
  const [actionResultCandidates, setActionResultCandidates] = useState<Candidate[] | null>(null)
  const [candidateExplanation, setCandidateExplanation] = useState<CandidateDetailResponse | null>(null)
  const [candidateExplanationLoading, setCandidateExplanationLoading] = useState(false)
  const [candidateExplanationError, setCandidateExplanationError] = useState<string | null>(null)
  const [contextPackDetail, setContextPackDetail] = useState<WritingContextPackResponse | null>(null)
  const [contextPackLoading, setContextPackLoading] = useState(false)
  const [contextPackError, setContextPackError] = useState<string | null>(null)
  const [memoryAnswer, setMemoryAnswer] = useState<MemoryAnswerResponse | null>(null)
  const [memoryAnswerLoading, setMemoryAnswerLoading] = useState(false)
  const [memoryAnswerError, setMemoryAnswerError] = useState<string | null>(null)
  const [memoryAnswerOpen, setMemoryAnswerOpen] = useState(false)
  const [memoryPages, setMemoryPages] = useState<MemoryPageListResponse["items"]>([])
  const [memoryPagesLoading, setMemoryPagesLoading] = useState(false)
  const [memoryPagesLoaded, setMemoryPagesLoaded] = useState(false)
  const [memoryPagesError, setMemoryPagesError] = useState<string | null>(null)
  const [memoryPageDetail, setMemoryPageDetail] = useState<MemoryPageDetailResponse | null>(null)
  const [memoryPageDetailLoading, setMemoryPageDetailLoading] = useState(false)
  const [memoryPageDetailError, setMemoryPageDetailError] = useState<string | null>(null)
  const [memoryThreadOperatingId, setMemoryThreadOperatingId] = useState<string | null>(null)
  const [memoryThreadOperationError, setMemoryThreadOperationError] = useState<string | null>(null)
  const [graphEdges, setGraphEdges] = useState<GraphProjectionEdgeListResponse["items"]>([])
  const [graphEdgesLoading, setGraphEdgesLoading] = useState(false)
  const [graphEdgesError, setGraphEdgesError] = useState<string | null>(null)
  const [graphEdgeSearch, setGraphEdgeSearch] = useState("")
  const [graphEdgeStatus, setGraphEdgeStatus] = useState("")
  const [acceptance, setAcceptance] = useState<CandidateAcceptResponse | null>(null)
  const [sourceDetail, setSourceDetail] = useState<SourceVersionResponse | null>(null)
  const [sourceError, setSourceError] = useState<string | null>(null)
  const [sourceDeltas, setSourceDeltas] = useState<SourceDeltaListResponse["items"]>([])
  const [sourceDeltasNextCursor, setSourceDeltasNextCursor] = useState<string | null>(null)
  const [sourceDeltasLoading, setSourceDeltasLoading] = useState(false)
  const [sourceDeltasError, setSourceDeltasError] = useState<string | null>(null)
  const [sourceVersions, setSourceVersions] = useState<SourceVersionListResponse["items"]>([])
  const [sourceVersionsLoading, setSourceVersionsLoading] = useState(false)
  const [sourceVersionsError, setSourceVersionsError] = useState<string | null>(null)
  const [sourceVersionDiff, setSourceVersionDiff] = useState<SourceVersionDiffResponse | null>(
    null,
  )
  const [sourceVersionDiffLoading, setSourceVersionDiffLoading] = useState(false)
  const [sourceVersionDiffError, setSourceVersionDiffError] = useState<string | null>(null)
  const [sourceDeltaSearch, setSourceDeltaSearch] = useState("")
  const [sourceDeltaStatus, setSourceDeltaStatus] = useState("")
  const [sourceDeltaKind, setSourceDeltaKind] = useState("")
  const [sourceDeltaDetail, setSourceDeltaDetail] = useState<SourceDeltaDetailResponse | null>(
    null,
  )
  const [sourceDeltaDetailLoading, setSourceDeltaDetailLoading] = useState(false)
  const [sourceDeltaDetailError, setSourceDeltaDetailError] = useState<string | null>(null)
  const sourceDeltasRequestSeq = useRef(0)
  const [sourceItems, setSourceItems] = useState<SourceListResponse["items"]>([])
  const [sourceSearch, setSourceSearch] = useState("")
  const [sourceListLoading, setSourceListLoading] = useState(false)
  const [sourceListError, setSourceListError] = useState<string | null>(null)
  const [sourceCreatePending, setSourceCreatePending] = useState(false)
  const [sourceCreateStatus, setSourceCreateStatus] = useState<string | null>(null)
  const [sourceCreateError, setSourceCreateError] = useState<string | null>(null)
  const [sourceArchivePendingId, setSourceArchivePendingId] = useState<string | null>(null)
  const [sourceRestorePendingId, setSourceRestorePendingId] = useState<string | null>(null)
  const [storySchema, setStorySchema] = useState<ProjectStorySchemaResponse | null>(null)
  const [storySchemaLoading, setStorySchemaLoading] = useState(false)
  const [storySchemaError, setStorySchemaError] = useState<string | null>(null)
  const [storySchemaOverrideText, setStorySchemaOverrideText] = useState("")
  const [storySchemaSavePending, setStorySchemaSavePending] = useState(false)
  const [storySchemaSaveStatus, setStorySchemaSaveStatus] = useState<string | null>(null)
  const [storySchemaSaveError, setStorySchemaSaveError] = useState<string | null>(null)
  const [storySchemaGenrePacks, setStorySchemaGenrePacks] = useState<StorySchemaPackResponse[]>(
    [],
  )
  const [storySchemaGenrePending, setStorySchemaGenrePending] = useState(false)
  const [storySchemaGenreStatus, setStorySchemaGenreStatus] = useState<string | null>(null)
  const [storySchemaGenreError, setStorySchemaGenreError] = useState<string | null>(null)
  const [projectMembers, setProjectMembers] = useState<ProjectMemberListResponse["items"]>([])
  const [projectMembersLoading, setProjectMembersLoading] = useState(false)
  const [projectMembersError, setProjectMembersError] = useState<string | null>(null)
  const [projectMemberOperationPendingId, setProjectMemberOperationPendingId] = useState<
    string | null
  >(null)
  const [projectMemberOperationStatus, setProjectMemberOperationStatus] = useState<string | null>(
    null,
  )
  const [projectMemberOperationError, setProjectMemberOperationError] = useState<string | null>(
    null,
  )
  const [projectInvitations, setProjectInvitations] = useState<
    ProjectInvitationListResponse["items"]
  >([])
  const [projectInvitationsLoading, setProjectInvitationsLoading] = useState(false)
  const [projectInvitationsError, setProjectInvitationsError] = useState<string | null>(null)
  const [projectInvitationOperationPendingId, setProjectInvitationOperationPendingId] = useState<
    string | null
  >(null)
  const [projectInvitationOperationStatus, setProjectInvitationOperationStatus] = useState<
    string | null
  >(null)
  const [projectInvitationOperationError, setProjectInvitationOperationError] = useState<
    string | null
  >(null)
  const [sourceEditOpen, setSourceEditOpen] = useState(false)
  const [sourceEditText, setSourceEditText] = useState("")
  const [sourceEditPending, setSourceEditPending] = useState(false)
  const [sourceEditRefreshPending, setSourceEditRefreshPending] = useState(false)
  const [sourceEditStatus, setSourceEditStatus] = useState<string | null>(null)
  const [sourceEditError, setSourceEditError] = useState<string | null>(null)
  const [sourceEditRejectedDraftText, setSourceEditRejectedDraftText] = useState<string | null>(
    null,
  )
  const [sourceEditRejectedBaseText, setSourceEditRejectedBaseText] = useState<string | null>(null)
  const [sceneContextPack, setSceneContextPack] = useState<WritingContextPackResponse | null>(null)
  const [sceneContextLoading, setSceneContextLoading] = useState(false)
  const [sceneContextError, setSceneContextError] = useState<string | null>(null)
  const [contextReadinessItems, setContextReadinessItems] = useState<
    ContextPackReadinessListResponse["items"]
  >([])
  const [contextReadinessLoading, setContextReadinessLoading] = useState(false)
  const [contextReadinessError, setContextReadinessError] = useState<string | null>(null)
  const [writebackState, setWritebackState] = useState<WorkbenchWritebackState | null>(null)
  const [writebackLoading, setWritebackLoading] = useState(false)
  const [writebackError, setWritebackError] = useState<string | null>(null)
  const [reviewDetail, setReviewDetail] = useState<ReviewItemDetailResponse | null>(null)
  const [reviewDetailLoading, setReviewDetailLoading] = useState(false)
  const [reviewDetailError, setReviewDetailError] = useState<string | null>(null)
  const [reviewEntityOptions, setReviewEntityOptions] = useState<CanonicalEntitySummaryResponse[]>(
    [],
  )
  const [askMemoryTargetOptions, setAskMemoryTargetOptions] = useState<
    CanonicalEntitySummaryResponse[]
  >([])
  const [askMemoryTargetOptionsLoading, setAskMemoryTargetOptionsLoading] = useState(false)
  const [askMemoryTargetOptionsError, setAskMemoryTargetOptionsError] = useState<string | null>(
    null,
  )
  const [reviewEntityOptionsLoading, setReviewEntityOptionsLoading] = useState(false)
  const [reviewEntityOptionsError, setReviewEntityOptionsError] = useState<string | null>(null)
  const [reviewSceneOptions, setReviewSceneOptions] = useState<StorySceneSummaryResponse[]>([])
  const [reviewSceneOptionsLoading, setReviewSceneOptionsLoading] = useState(false)
  const [reviewSceneOptionsError, setReviewSceneOptionsError] = useState<string | null>(null)
  const [apiReviewItems, setApiReviewItems] = useState<ReviewItemListResponse["items"]>([])
  const [reviewOperationPending, setReviewOperationPending] = useState(false)
  const editorSource = useMemo(
    () => workbenchEditorSourceView(Boolean(apiConfig), demoMode, sourceDetail),
    [apiConfig, demoMode, sourceDetail],
  )
  const editorText = editorSource.text
  const visibleAcceptedSentence = demoMode ? acceptedSentence : null
  const sceneCardState = useMemo(
    () => (apiConfig && sceneContextPack ? sceneCardFromContextPack(sceneContextPack) : undefined),
    [apiConfig, sceneContextPack],
  )
  const projectHeader = useMemo(
    () =>
      apiConfig
        ? {
            name: editorSource.title,
            chapter: editorSource.chapter,
            pov: sceneCardState?.pov?.trim() || "等待上下文",
          }
        : project,
    [apiConfig, editorSource.chapter, editorSource.title, sceneCardState?.pov],
  )
  const askSuggestionContext = useMemo<AskSuggestionContext>(() => {
    if (!apiConfig) {
      return demoAskSuggestionContext
    }
    const povLabel = sceneCardState?.pov
    const recallLabel =
      askMemoryTargetOptions.find(
        (entity) =>
          entity.entity_type === "character" &&
          entity.display_name.trim() &&
          entity.display_name !== povLabel,
      )?.display_name ??
      askMemoryTargetOptions.find((entity) => entity.display_name.trim())?.display_name
    return { povLabel, recallLabel }
  }, [apiConfig, askMemoryTargetOptions, sceneCardState])
  const contextReadinessState = useMemo(
    () =>
      apiConfig
        ? {
            pending: contextReadinessItems.filter((item) => item.status === "pending").length,
            stale: contextReadinessItems.filter((item) => item.status === "stale").length,
            consumed: contextReadinessItems.filter((item) => item.status === "consumed").length,
            loading: contextReadinessLoading,
            error: contextReadinessError,
          }
        : undefined,
    [apiConfig, contextReadinessError, contextReadinessItems, contextReadinessLoading],
  )
  const visibleReviewItems = useMemo(
    () =>
      (apiConfig ? (writebackState?.reviewItems ?? apiReviewItems) : reviewItems).map((item) => ({
        id: item.id,
        text: "summary" in item ? item.summary : item.text,
        hint: "review_type" in item ? `${item.review_type} · ${item.severity}` : item.hint,
      })),
    [apiConfig, apiReviewItems, writebackState],
  )

  const closeAll = useCallback(() => {
    setSelection(null)
    setProjectOpen(false)
    setMemoryOpen(false)
    setDrawerOpen(false)
    setAskOpen(false)
    setWritebackOpen(false)
    setReviewOpen(false)
    setAcceptedSentence(null)
    setDemoHighlight(false)
    setCandidateDetail(null)
    setActionResultCandidates(null)
    setCandidateError(null)
    setCandidateStaleSourceMessage(null)
    setCandidateSourceRefreshPending(false)
    setCandidateOperationPending(false)
    setCandidateOperationStatus(null)
    setCandidateOperationError(null)
    setCandidateExplanation(null)
    setCandidateExplanationLoading(false)
    setCandidateExplanationError(null)
    setContextPackDetail(null)
    setContextPackLoading(false)
    setContextPackError(null)
    setContextReadinessItems([])
    setContextReadinessLoading(false)
    setContextReadinessError(null)
    setMemoryAnswer(null)
    setMemoryAnswerLoading(false)
    setMemoryAnswerError(null)
    setMemoryAnswerOpen(false)
    setMemoryPageDetail(null)
    setMemoryPageDetailError(null)
    setGraphEdges([])
    setGraphEdgesError(null)
    setGraphEdgeSearch("")
    setGraphEdgeStatus("")
    setAcceptance(null)
    setWritebackState(null)
    setWritebackError(null)
    setReviewDetail(null)
    setReviewDetailError(null)
    setSourceDeltaDetail(null)
    setSourceDeltaDetailLoading(false)
    setSourceDeltaDetailError(null)
    setSourceDeltaSearch("")
    setSourceDeltaStatus("")
    setSourceDeltaKind("")
    setSourceDeltasNextCursor(null)
    setSourceVersions([])
    setSourceVersionsLoading(false)
    setSourceVersionsError(null)
    setSourceVersionDiff(null)
    setSourceVersionDiffLoading(false)
    setSourceVersionDiffError(null)
    setSourceCreateStatus(null)
    setSourceCreateError(null)
    setSourceArchivePendingId(null)
    setSourceRestorePendingId(null)
    setStorySchema(null)
    setStorySchemaError(null)
    setStorySchemaOverrideText("")
    setStorySchemaSaveStatus(null)
    setStorySchemaSaveError(null)
    setStorySchemaGenrePacks([])
    setStorySchemaGenrePending(false)
    setStorySchemaGenreStatus(null)
    setStorySchemaGenreError(null)
    setProjectInvitations([])
    setProjectInvitationsLoading(false)
    setProjectInvitationsError(null)
    setProjectInvitationOperationPendingId(null)
    setProjectInvitationOperationStatus(null)
    setProjectInvitationOperationError(null)
    setSourceEditOpen(false)
    setSourceEditText("")
    setSourceEditPending(false)
    setSourceEditStatus(null)
    setSourceEditError(null)
    setSourceEditRejectedDraftText(null)
  }, [])

  const handleRuntimeAuthSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      if (!authConfig) {
        setAuthError("缺少 Supabase Auth 运行时配置。")
        return
      }
      setAuthPending(true)
      setAuthError(null)
      try {
        const nextSession = await signInWorkbenchWithPassword(authConfig, {
          email: authEmail,
          password: authPassword,
        })
        writeStoredWorkbenchAuthSession(nextSession)
        setAuthSession(nextSession)
        setAuthPassword("")
      } catch (error) {
        setAuthError(errorMessage(error))
      } finally {
        setAuthPending(false)
      }
    },
    [authConfig, authEmail, authPassword],
  )

  const refreshSourceDeltas = useCallback(
    async (filters?: WorkbenchSourceDeltaFilters, options: { append?: boolean } = {}) => {
      if (!apiConfig || !apiClient) {
        return
      }
      const nextFilters =
        filters ?? {
          query: sourceDeltaSearch,
          status: sourceDeltaStatus || undefined,
          deltaKind: sourceDeltaKind || undefined,
        }
      const requestSeq = sourceDeltasRequestSeq.current + 1
      sourceDeltasRequestSeq.current = requestSeq
      setSourceDeltasLoading(true)
      setSourceDeltasError(null)
      try {
        const page = await loadWorkbenchSourceDeltaPage(apiClient, apiConfig, nextFilters)
        if (requestSeq !== sourceDeltasRequestSeq.current) {
          return
        }
        setSourceDeltas((current) => (options.append ? [...current, ...page.items] : page.items))
        setSourceDeltasNextCursor(page.next_cursor)
      } catch (error) {
        if (requestSeq !== sourceDeltasRequestSeq.current) {
          return
        }
        setSourceDeltasError(errorMessage(error))
      } finally {
        if (requestSeq === sourceDeltasRequestSeq.current) {
          setSourceDeltasLoading(false)
        }
      }
    },
    [apiClient, apiConfig, sourceDeltaKind, sourceDeltaSearch, sourceDeltaStatus],
  )

  const refreshSourceVersions = useCallback(async () => {
    if (!apiConfig || !apiClient) {
      return
    }
    setSourceVersionsLoading(true)
    setSourceVersionsError(null)
    try {
      setSourceVersions(await loadWorkbenchSourceVersions(apiClient, apiConfig))
    } catch (error) {
      setSourceVersionsError(errorMessage(error))
    } finally {
      setSourceVersionsLoading(false)
    }
  }, [apiClient, apiConfig])

  const refreshSources = useCallback(
    async (query?: string) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setSourceListLoading(true)
      setSourceListError(null)
      try {
        setSourceItems(await loadWorkbenchSources(apiClient, apiConfig, query ?? sourceSearch))
      } catch (error) {
        setSourceListError(errorMessage(error))
      } finally {
        setSourceListLoading(false)
      }
    },
    [apiClient, apiConfig, sourceSearch],
  )

  const refreshStorySchema = useCallback(async () => {
    if (!apiConfig || !apiClient) {
      return
    }
    setStorySchemaLoading(true)
    setStorySchemaError(null)
    setStorySchemaGenreError(null)
    try {
      const schema = await loadWorkbenchStorySchema(apiClient, apiConfig)
      setStorySchema(schema)
      setStorySchemaOverrideText(storySchemaOverrideTextFromResponse(schema))
      setStorySchemaGenrePacks(await loadWorkbenchStorySchemaPacks(apiClient, apiConfig))
    } catch (error) {
      setStorySchemaError(errorMessage(error))
    } finally {
      setStorySchemaLoading(false)
    }
  }, [apiClient, apiConfig])

  const refreshProjectMembers = useCallback(async () => {
    if (!apiConfig || !apiClient) {
      return
    }
    setProjectMembersLoading(true)
    setProjectMembersError(null)
    try {
      setProjectMembers(await loadWorkbenchProjectMembers(apiClient, apiConfig))
    } catch (error) {
      setProjectMembersError(errorMessage(error))
    } finally {
      setProjectMembersLoading(false)
    }
  }, [apiClient, apiConfig])

  const refreshProjectInvitations = useCallback(async () => {
    if (!apiConfig || !apiClient) {
      return
    }
    setProjectInvitationsLoading(true)
    setProjectInvitationsError(null)
    try {
      setProjectInvitations(await listWorkbenchProjectInvitations(apiClient, apiConfig))
    } catch (error) {
      setProjectInvitationsError(errorMessage(error))
    } finally {
      setProjectInvitationsLoading(false)
    }
  }, [apiClient, apiConfig])

  const handleProjectMemberUpsert = useCallback(
    async (memberActorId: string, role: WorkbenchProjectMemberRole) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setProjectMemberOperationPendingId(memberActorId)
      setProjectMemberOperationStatus(null)
      setProjectMemberOperationError(null)
      try {
        await upsertWorkbenchProjectMember(apiClient, apiConfig, memberActorId, role)
        setProjectMemberOperationStatus("成员已更新。")
        await refreshProjectMembers()
      } catch (error) {
        setProjectMemberOperationError(errorMessage(error))
      } finally {
        setProjectMemberOperationPendingId(null)
      }
    },
    [apiClient, apiConfig, refreshProjectMembers],
  )

  const handleProjectMemberRevoke = useCallback(
    async (memberActorId: string) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setProjectMemberOperationPendingId(memberActorId)
      setProjectMemberOperationStatus(null)
      setProjectMemberOperationError(null)
      try {
        await revokeWorkbenchProjectMember(apiClient, apiConfig, memberActorId)
        setProjectMemberOperationStatus("成员已撤销。")
        await refreshProjectMembers()
      } catch (error) {
        setProjectMemberOperationError(errorMessage(error))
      } finally {
        setProjectMemberOperationPendingId(null)
      }
    },
    [apiClient, apiConfig, refreshProjectMembers],
  )

  const handleProjectInvitationCreate = useCallback(
    async (input: WorkbenchProjectInvitationInput) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setProjectInvitationOperationPendingId(input.memberActorId)
      setProjectInvitationOperationStatus(null)
      setProjectInvitationOperationError(null)
      try {
        await createWorkbenchProjectInvitation(apiClient, apiConfig, input)
        setProjectInvitationOperationStatus("邀请已记录。")
        await refreshProjectInvitations()
      } catch (error) {
        setProjectInvitationOperationError(errorMessage(error))
      } finally {
        setProjectInvitationOperationPendingId(null)
      }
    },
    [apiClient, apiConfig, refreshProjectInvitations],
  )

  const handleProjectInvitationProof = useCallback(
    async (invitationId: string, input: WorkbenchProjectInvitationProofInput) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setProjectInvitationOperationPendingId(invitationId)
      setProjectInvitationOperationStatus(null)
      setProjectInvitationOperationError(null)
      try {
        await recordWorkbenchProjectInvitationExternalProof(
          apiClient,
          apiConfig,
          invitationId,
          input,
        )
        setProjectInvitationOperationStatus("外部证明已记录。")
        await refreshProjectInvitations()
      } catch (error) {
        setProjectInvitationOperationError(errorMessage(error))
      } finally {
        setProjectInvitationOperationPendingId(null)
      }
    },
    [apiClient, apiConfig, refreshProjectInvitations],
  )

  const handleStorySchemaGenreSelect = useCallback(
    async (genreSchemaPackId: string | null) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setStorySchemaGenrePending(true)
      setStorySchemaGenreStatus(null)
      setStorySchemaGenreError(null)
      setStorySchemaSaveError(null)
      try {
        const schema = await selectWorkbenchStorySchemaGenrePack(
          apiClient,
          apiConfig,
          genreSchemaPackId,
        )
        setStorySchema(schema)
        setStorySchemaOverrideText(storySchemaOverrideTextFromResponse(schema))
        setStorySchemaGenreStatus(genreSchemaPackId ? "类型规则已保存" : "已恢复基础规则")
      } catch (error) {
        setStorySchemaGenreError(errorMessage(error))
      } finally {
        setStorySchemaGenrePending(false)
      }
    },
    [apiClient, apiConfig],
  )

  const handleStorySchemaOverrideSave = useCallback(async () => {
    if (!apiConfig || !apiClient) {
      return
    }
    setStorySchemaSavePending(true)
    setStorySchemaSaveStatus(null)
    setStorySchemaSaveError(null)
    try {
      const input = parseStorySchemaOverrideText(storySchemaOverrideText)
      const schema = await upsertWorkbenchStorySchemaOverride(apiClient, apiConfig, input)
      setStorySchema(schema)
      setStorySchemaOverrideText(storySchemaOverrideTextFromResponse(schema))
      setStorySchemaSaveStatus("规则已保存")
    } catch (error) {
      setStorySchemaSaveError(errorMessage(error))
    } finally {
      setStorySchemaSavePending(false)
    }
  }, [apiClient, apiConfig, storySchemaOverrideText])

  const handleSourceVersionSelect = useCallback(
    async (versionId: string) => {
      if (!apiConfig || !apiClient || versionId === apiConfig.sourceVersionId) {
        return
      }
      const nextConfig = { ...apiConfig, sourceVersionId: versionId }
      setSourceError(null)
      setDrawerOpen(false)
      setCandidateDetail(null)
      setActionResultCandidates(null)
      setCandidateError(null)
      setCandidateStaleSourceMessage(null)
      setAcceptance(null)
      setWritebackOpen(false)
      setWritebackState(null)
      setSourceVersionDiff(null)
      setSourceVersionDiffError(null)
      setSourceEditOpen(false)
      setSourceEditStatus(null)
      setSourceEditError(null)
      setSourceEditRejectedDraftText(null)
      setSourceEditRejectedBaseText(null)
      try {
        setSourceDetail(await loadWorkbenchSource(apiClient, nextConfig))
        setCurrentSourceVersionId(versionId)
      } catch (error) {
        setSourceError(errorMessage(error))
      }
    },
    [apiClient, apiConfig, setCurrentSourceVersionId],
  )

  const handleSourceEditStart = useCallback(() => {
    if (!apiConfig || !sourceDetail) {
      return
    }
    setSourceEditText(sourceDetail.text)
    setSourceEditOpen(true)
    setSourceEditStatus(null)
    setSourceEditError(null)
    setSourceEditRejectedDraftText(null)
    setSourceEditRejectedBaseText(null)
    setDrawerOpen(false)
    setSelection(null)
  }, [apiConfig, sourceDetail])

  const handleSourceEditCancel = useCallback(() => {
    if (sourceEditPending) {
      return
    }
    setSourceEditOpen(false)
    setSourceEditText(sourceDetail?.text ?? "")
    setSourceEditError(null)
    setSourceEditRejectedDraftText(null)
    setSourceEditRejectedBaseText(null)
  }, [sourceDetail, sourceEditPending])

  const handleSourceEditRefresh = useCallback(async () => {
    if (!apiConfig || !apiClient) {
      return
    }
    setSourceEditRefreshPending(true)
    setSourceEditError(null)
    try {
      const sources = await loadWorkbenchSources(apiClient, apiConfig, "")
      setSourceItems(sources)
      const currentSource = sources.find((item) => item.source_id === apiConfig.sourceId)
      const latestVersionId = currentSource?.latest_version_id
      if (!latestVersionId) {
        throw new Error("没有找到最新正文版本。")
      }
      const nextConfig = { ...apiConfig, sourceVersionId: latestVersionId }
      const latestSource = await loadWorkbenchSource(apiClient, nextConfig)
      setCurrentSourceVersionId(latestVersionId)
      setSourceDetail(latestSource)
      setSourceEditText(latestSource.text)
      await refreshSourceVersions()
      await refreshSourceDeltas()
      setSourceEditStatus(
        sourceEditRejectedDraftText
          ? "已刷新最新正文版本，草稿已保留用于合并。"
          : "已刷新最新正文版本，请重新编辑后保存。",
      )
    } catch (error) {
      setSourceEditError(errorMessage(error))
    } finally {
      setSourceEditRefreshPending(false)
    }
  }, [
    apiClient,
    apiConfig,
    refreshSourceDeltas,
    refreshSourceVersions,
    setCurrentSourceVersionId,
    sourceEditRejectedDraftText,
  ])

  const handleSourceEditApplyRejectedDraft = useCallback(() => {
    if (!sourceEditRejectedDraftText) {
      return
    }
    setSourceEditText(sourceEditRejectedDraftText)
    setSourceEditRejectedDraftText(null)
    setSourceEditRejectedBaseText(null)
    setSourceEditError(null)
    setSourceEditStatus("已套用被拒绝的草稿，请检查预览后保存。")
  }, [sourceEditRejectedDraftText])

  const handleSourceEditMergeRejectedDraft = useCallback(() => {
    if (!sourceEditRejectedDraftText) {
      return
    }
    setSourceEditText(
      mergeSourceEditDraft(
        sourceEditText,
        sourceEditRejectedDraftText,
        sourceEditRejectedBaseText,
      ),
    )
    setSourceEditRejectedDraftText(null)
    setSourceEditRejectedBaseText(null)
    setSourceEditError(null)
    setSourceEditStatus("已合并最新正文版本和被拒绝草稿，请检查预览后保存。")
  }, [sourceEditRejectedBaseText, sourceEditRejectedDraftText, sourceEditText])

  const handleSourceEditDismissRejectedDraft = useCallback(() => {
    setSourceEditRejectedDraftText(null)
    setSourceEditRejectedBaseText(null)
    setSourceEditStatus("已丢弃被拒绝的草稿。")
  }, [])

  const handleSourceEditSave = useCallback(async () => {
    if (!apiConfig || !apiClient || !sourceDetail) {
      return
    }
    setSourceEditPending(true)
    setSourceEditError(null)
    setSourceEditStatus(null)
    setCandidateDetail(null)
    setActionResultCandidates(null)
    setCandidateError(null)
    setCandidateStaleSourceMessage(null)
    setAcceptance(null)
    setWritebackOpen(false)
    setWritebackState(null)
    setSourceVersionDiff(null)
    setSourceVersionDiffError(null)
    setSourceDeltaDetailError(null)
    try {
      const saved = await saveWorkbenchSourceEdit(
        apiClient,
        apiConfig,
        sourceDetail,
        sourceEditText,
      )
      const nextConfig = { ...apiConfig, sourceVersionId: saved.new_version_id }
      setCurrentSourceVersionId(saved.new_version_id)
      setSourceDetail(await loadWorkbenchSource(apiClient, nextConfig))
      setSourceDeltaDetailLoading(true)
      setSourceDeltaDetail(
        await loadWorkbenchSourceDeltaDetail(apiClient, apiConfig, saved.source_delta_id),
      )
      await refreshSourceVersions()
      await refreshSourceDeltas()
      setSourceEditOpen(false)
      setSourceEditStatus("正文变更已保存 · 等待记忆回写")
      setSourceEditRejectedDraftText(null)
      setSourceEditRejectedBaseText(null)
    } catch (error) {
      const staleSourceVersion = isWorkbenchStaleSourceVersionError(error)
      const message = staleSourceVersion ? SOURCE_EDIT_STALE_MESSAGE : errorMessage(error)
      if (staleSourceVersion) {
        setSourceEditRejectedDraftText(sourceEditText)
        setSourceEditRejectedBaseText(sourceDetail.text)
      }
      setSourceEditError(message)
      setSourceDeltaDetailError(message)
    } finally {
      setSourceEditPending(false)
      setSourceDeltaDetailLoading(false)
    }
  }, [
    apiClient,
    apiConfig,
    refreshSourceDeltas,
    refreshSourceVersions,
    setCurrentSourceVersionId,
    sourceDetail,
    sourceEditText,
  ])

  const handleSourceVersionDiff = useCallback(
    async (versionId: string) => {
      if (!apiConfig || !apiClient) {
        return
      }
      const compareVersionId = sourceDetail?.version_id ?? apiConfig.sourceVersionId
      if (versionId === compareVersionId) {
        return
      }
      setSourceVersionDiffLoading(true)
      setSourceVersionDiffError(null)
      try {
        setSourceVersionDiff(
          await loadWorkbenchSourceVersionDiff(
            apiClient,
            apiConfig,
            versionId,
            compareVersionId,
          ),
        )
      } catch (error) {
        setSourceVersionDiffError(errorMessage(error))
      } finally {
        setSourceVersionDiffLoading(false)
      }
    },
    [apiClient, apiConfig, sourceDetail],
  )

  const refreshMemoryPages = useCallback(
    async (filters: WorkbenchMemoryPageFilters = {}) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setMemoryPagesLoading(true)
      setMemoryPagesError(null)
      try {
        const pages = await loadWorkbenchMemoryPages(apiClient, apiConfig, filters)
        setMemoryPages(pages)
        setMemoryPagesLoaded(true)
        if (!memoryPageDetail && pages[0]) {
          setMemoryPageDetailLoading(true)
          setMemoryPageDetail(
            await loadWorkbenchMemoryPageDetail(apiClient, apiConfig, pages[0].id),
          )
        }
      } catch (error) {
        setMemoryPagesError(errorMessage(error))
        setMemoryPagesLoaded(true)
      } finally {
        setMemoryPagesLoading(false)
        setMemoryPageDetailLoading(false)
      }
    },
    [apiClient, apiConfig, memoryPageDetail],
  )

  const refreshGraphEdges = useCallback(
    async (filters?: WorkbenchGraphEdgeFilters) => {
      if (!apiConfig || !apiClient) {
        return
      }
      const nextFilters =
        filters ?? {
          query: graphEdgeSearch,
          edgeStatus: graphEdgeStatus || undefined,
        }
      setGraphEdgesLoading(true)
      setGraphEdgesError(null)
      try {
        setGraphEdges(await loadWorkbenchGraphProjectionEdges(apiClient, apiConfig, nextFilters))
      } catch (error) {
        setGraphEdgesError(errorMessage(error))
      } finally {
        setGraphEdgesLoading(false)
      }
    },
    [apiClient, apiConfig, graphEdgeSearch, graphEdgeStatus],
  )

  const handleSourceDeltaSelect = useCallback(
    async (id: string) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setSourceDeltaDetailLoading(true)
      setSourceDeltaDetailError(null)
      try {
        setSourceDeltaDetail(await loadWorkbenchSourceDeltaDetail(apiClient, apiConfig, id))
      } catch (error) {
        setSourceDeltaDetailError(errorMessage(error))
      } finally {
        setSourceDeltaDetailLoading(false)
      }
    },
    [apiClient, apiConfig],
  )

  const handleMemoryPageSelect = useCallback(
    async (id: string) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setMemoryPageDetailLoading(true)
      setMemoryPageDetailError(null)
      try {
        setMemoryPageDetail(await loadWorkbenchMemoryPageDetail(apiClient, apiConfig, id))
      } catch (error) {
        setMemoryPageDetailError(errorMessage(error))
      } finally {
        setMemoryPageDetailLoading(false)
      }
    },
    [apiClient, apiConfig],
  )

  const handleMemoryPageThreadOperation = useCallback(
    async (
      threadId: string,
      updateType: WorkbenchMemoryPageThreadInput["updateType"],
      summary: string | null,
    ) => {
      if (!apiConfig || !apiClient || !memoryPageDetail) {
        return
      }
      setMemoryThreadOperatingId(threadId)
      setMemoryThreadOperationError(null)
      try {
        const result = await operateWorkbenchMemoryPageThread(
          apiClient,
          apiConfig,
          memoryPageDetail.id,
          {
            threadId,
            updateType,
            authorNote:
              updateType === "pays_off"
                ? "作者从记忆页面板标记此开放线索已回收。"
                : "作者从记忆页面板关闭此开放线索。",
            summary,
          },
        )
        setMemoryPageDetail(result.memory_page)
        void refreshMemoryPages()
        void refreshGraphEdges()
      } catch (error) {
        setMemoryThreadOperationError(errorMessage(error))
      } finally {
        setMemoryThreadOperatingId(null)
      }
    },
    [apiClient, apiConfig, memoryPageDetail, refreshGraphEdges, refreshMemoryPages],
  )

  const refreshContextReadiness = useCallback(
    async (options: { status?: "pending" | "stale" | "consumed" | null } = {}) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setContextReadinessLoading(true)
      setContextReadinessError(null)
      try {
        const readiness = await loadWorkbenchContextPackReadiness(apiClient, apiConfig, {
          status: "status" in options ? options.status : "pending",
          limit: 20,
        })
        setContextReadinessItems(readiness.items)
      } catch (error) {
        setContextReadinessError(errorMessage(error))
      } finally {
        setContextReadinessLoading(false)
      }
    },
    [apiClient, apiConfig],
  )

  useEffect(() => {
    if (!baseApiConfig || !apiClient) {
      return
    }
    let cancelled = false
    loadWorkbenchSources(apiClient, baseApiConfig)
      .then((items) => {
        const currentSource = items.find((item) => item.source_id === baseApiConfig.sourceId)
        if (!cancelled && currentSource?.latest_version_id) {
          setCurrentSourceVersionId(currentSource.latest_version_id)
        }
      })
      .catch((error) => {
        if (!cancelled) setSourceListError(errorMessage(error))
      })
    return () => {
      cancelled = true
    }
  }, [apiClient, baseApiConfig, setCurrentSourceVersionId])

  useEffect(() => {
    void refreshContextReadiness({ status: null })
  }, [refreshContextReadiness])

  useEffect(() => {
    if (!apiConfig || !apiClient) {
      return
    }
    let cancelled = false
    setSourceError(null)
    loadWorkbenchSource(apiClient, apiConfig)
      .then((source) => {
        if (!cancelled) setSourceDetail(source)
      })
      .catch((error) => {
        if (!cancelled) setSourceError(errorMessage(error))
      })
    return () => {
      cancelled = true
    }
  }, [apiClient, apiConfig])

  useEffect(() => {
    if (!apiConfig || !apiClient || !sourceDetail) {
      return
    }
    let cancelled = false
    setSceneContextLoading(true)
    setSceneContextError(null)
    buildWorkbenchContextPack(apiClient, apiConfig, {
      mode: "review",
      currentTextWindow: sourceDetail.text,
    })
      .then((contextPack) => {
        if (!cancelled) {
          setSceneContextPack(contextPack)
          void refreshContextReadiness({ status: null })
        }
      })
      .catch((error) => {
        if (!cancelled) setSceneContextError(errorMessage(error))
      })
      .finally(() => {
        if (!cancelled) setSceneContextLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [apiClient, apiConfig, refreshContextReadiness, sourceDetail])

  useEffect(() => {
    if (!apiConfig || !apiClient) {
      return
    }
    let cancelled = false
    loadWorkbenchReviewItems(apiClient, apiConfig)
      .then((items) => {
        if (!cancelled) setApiReviewItems(items)
      })
      .catch((error) => {
        if (!cancelled) setReviewDetailError(errorMessage(error))
      })
    return () => {
      cancelled = true
    }
  }, [apiClient, apiConfig])

  useEffect(() => {
    if (!apiConfig || !apiClient || !acceptance || !writebackOpen) {
      return
    }
    let cancelled = false

    async function refresh() {
      if (!apiConfig || !apiClient || !acceptance) return
      setWritebackLoading(true)
      try {
        const state = await readWorkbenchWritebackState(apiClient, apiConfig, acceptance)
        if (!cancelled) {
          setWritebackState(state)
          setWritebackError(null)
          if (state.job.status === "succeeded") {
            void refreshContextReadiness({ status: null })
            if (memoryOpen) {
              void refreshMemoryPages()
              void refreshGraphEdges()
            }
          }
        }
      } catch (error) {
        if (!cancelled) setWritebackError(errorMessage(error))
      } finally {
        if (!cancelled) setWritebackLoading(false)
      }
    }

    void refresh()
    const interval = window.setInterval(() => {
      const status = writebackState?.job.status
      if (status === "succeeded" || status === "failed_terminal") {
        window.clearInterval(interval)
        return
      }
      void refresh()
    }, 2000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [
    acceptance,
    apiClient,
    apiConfig,
    memoryOpen,
    refreshContextReadiness,
    refreshGraphEdges,
    refreshMemoryPages,
    writebackOpen,
    writebackState?.job.status,
  ])

  const handleProjectToggle = useCallback(() => {
    setProjectOpen((open) => {
      const nextOpen = !open
      if (nextOpen) {
        void refreshSourceDeltas()
        void refreshSourceVersions()
        void refreshSources()
        void refreshStorySchema()
        void refreshProjectMembers()
        void refreshProjectInvitations()
      } else {
        setSourceDeltaDetail(null)
        setSourceDeltaDetailError(null)
      }
      return nextOpen
    })
  }, [
    refreshProjectInvitations,
    refreshProjectMembers,
    refreshSourceDeltas,
    refreshSourceVersions,
    refreshSources,
    refreshStorySchema,
  ])

  const handleMemoryToggle = useCallback(() => {
    setMemoryOpen((open) => {
      const nextOpen = !open
      if (nextOpen) {
        void refreshMemoryPages()
        void refreshGraphEdges()
      } else {
        setMemoryPageDetail(null)
        setMemoryPageDetailError(null)
      }
      return nextOpen
    })
  }, [refreshGraphEdges, refreshMemoryPages])

  const handleSourceSearchChange = useCallback(
    (query: string) => {
      setSourceSearch(query)
      void refreshSources(query)
    },
    [refreshSources],
  )

  const sourceDeltaFilterInput = useCallback(
    (next: Partial<WorkbenchSourceDeltaFilters> = {}): WorkbenchSourceDeltaFilters => ({
      query: "query" in next ? next.query : sourceDeltaSearch,
      status: "status" in next ? next.status : sourceDeltaStatus || undefined,
      deltaKind: "deltaKind" in next ? next.deltaKind : sourceDeltaKind || undefined,
      cursor: "cursor" in next ? next.cursor : undefined,
    }),
    [sourceDeltaKind, sourceDeltaSearch, sourceDeltaStatus],
  )

  const handleSourceDeltaSearchChange = useCallback(
    (query: string) => {
      setSourceDeltaSearch(query)
      setSourceDeltaDetail(null)
      setSourceDeltaDetailError(null)
      void refreshSourceDeltas(sourceDeltaFilterInput({ query }))
    },
    [refreshSourceDeltas, sourceDeltaFilterInput],
  )

  const handleSourceDeltaStatusChange = useCallback(
    (status: string) => {
      setSourceDeltaStatus(status)
      setSourceDeltaDetail(null)
      setSourceDeltaDetailError(null)
      void refreshSourceDeltas(sourceDeltaFilterInput({ status: status || undefined }))
    },
    [refreshSourceDeltas, sourceDeltaFilterInput],
  )

  const handleSourceDeltaKindChange = useCallback(
    (deltaKind: string) => {
      setSourceDeltaKind(deltaKind)
      setSourceDeltaDetail(null)
      setSourceDeltaDetailError(null)
      void refreshSourceDeltas(sourceDeltaFilterInput({ deltaKind: deltaKind || undefined }))
    },
    [refreshSourceDeltas, sourceDeltaFilterInput],
  )

  const handleSourceDeltaLoadMore = useCallback(() => {
    if (!sourceDeltasNextCursor) {
      return
    }
    void refreshSourceDeltas(
      sourceDeltaFilterInput({ cursor: sourceDeltasNextCursor }),
      { append: true },
    )
  }, [refreshSourceDeltas, sourceDeltaFilterInput, sourceDeltasNextCursor])

  const graphEdgeFilterInput = useCallback(
    (next: Partial<WorkbenchGraphEdgeFilters> = {}): WorkbenchGraphEdgeFilters => ({
      query: "query" in next ? next.query : graphEdgeSearch,
      edgeStatus: "edgeStatus" in next ? next.edgeStatus : graphEdgeStatus || undefined,
      relation: "relation" in next ? next.relation : undefined,
    }),
    [graphEdgeSearch, graphEdgeStatus],
  )

  const handleGraphEdgeSearchChange = useCallback(
    (query: string) => {
      setGraphEdgeSearch(query)
      void refreshGraphEdges(graphEdgeFilterInput({ query }))
    },
    [graphEdgeFilterInput, refreshGraphEdges],
  )

  const handleGraphEdgeStatusChange = useCallback(
    (status: string) => {
      setGraphEdgeStatus(status)
      void refreshGraphEdges(graphEdgeFilterInput({ edgeStatus: status || undefined }))
    },
    [graphEdgeFilterInput, refreshGraphEdges],
  )

  const handleCreateSource = useCallback(
    async (input: WorkbenchSourceCreateInput) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setSourceCreatePending(true)
      setSourceCreateError(null)
      setSourceCreateStatus(null)
      setSourceDeltaDetailError(null)
      try {
        const created = await createWorkbenchSource(apiClient, apiConfig, input)
        setSourceSearch("")
        await refreshSources("")
        setSourceDeltaDetailLoading(true)
        setSourceDeltaDetail(
          await loadWorkbenchSourceDeltaDetail(apiClient, apiConfig, created.source_delta_id),
        )
        setSourceCreateStatus("材料已保存 · 等待记忆回写")
      } catch (error) {
        setSourceCreateError(errorMessage(error))
        setSourceDeltaDetailError(errorMessage(error))
      } finally {
        setSourceCreatePending(false)
        setSourceDeltaDetailLoading(false)
      }
    },
    [apiClient, apiConfig, refreshSources],
  )

  const handleArchiveSource = useCallback(
    async (sourceId: string) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setSourceArchivePendingId(sourceId)
      setSourceCreateError(null)
      setSourceCreateStatus(null)
      try {
        await archiveWorkbenchSource(apiClient, apiConfig, sourceId)
        await refreshSources("")
        setSourceCreateStatus("材料已归档")
      } catch (error) {
        setSourceCreateError(errorMessage(error))
      } finally {
        setSourceArchivePendingId(null)
      }
    },
    [apiClient, apiConfig, refreshSources],
  )

  const handleRestoreSourceVersion = useCallback(
    async (versionId: string) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setSourceRestorePendingId(versionId)
      setSourceCreateError(null)
      setSourceCreateStatus(null)
      setSourceDeltaDetailError(null)
      setDrawerOpen(false)
      setCandidateDetail(null)
      setActionResultCandidates(null)
      setCandidateError(null)
      setCandidateStaleSourceMessage(null)
      setAcceptance(null)
      setWritebackOpen(false)
      setWritebackState(null)
      setSourceVersionDiff(null)
      setSourceVersionDiffError(null)
      setSourceEditOpen(false)
      setSourceEditStatus(null)
      setSourceEditError(null)
      setSourceEditRejectedDraftText(null)
      try {
        const restored = await restoreWorkbenchSourceVersion(apiClient, apiConfig, versionId)
        const nextConfig = { ...apiConfig, sourceVersionId: restored.new_version_id }
        setCurrentSourceVersionId(restored.new_version_id)
        setSourceDetail(await loadWorkbenchSource(apiClient, nextConfig))
        setSourceDeltaDetailLoading(true)
        setSourceDeltaDetail(
          await loadWorkbenchSourceDeltaDetail(apiClient, apiConfig, restored.source_delta_id),
        )
        await refreshSources("")
        await refreshSourceVersions()
        await refreshSourceDeltas()
        setSourceCreateStatus("正文版本已恢复 · 等待记忆回写")
      } catch (error) {
        const message = errorMessage(error)
        setSourceCreateError(message)
        setSourceDeltaDetailError(message)
      } finally {
        setSourceRestorePendingId(null)
        setSourceDeltaDetailLoading(false)
      }
    },
    [
      apiClient,
      apiConfig,
      refreshSourceDeltas,
      refreshSourceVersions,
      refreshSources,
      setCurrentSourceVersionId,
    ],
  )

  // 在正文里真实选中文字 → 弹出浮动菜单
  const handleSelect = useCallback((sel: Selection | null) => {
    setDemoHighlight(false)
    setSelection(sel)
  }, [])

  const requestSelectedTextCandidate = useCallback(
    async (
      label: string,
      currentSelection: { text: string; range: { start: number; end: number } },
    ) => {
      setDemoHighlight(false)
      setDrawerOpen(true)
      setMemoryAnswerOpen(false)
      setWritebackOpen(false)
      setAcceptance(null)
      setWritebackState(null)

      if (!apiConfig || !apiClient) {
        return
      }
      const currentSourceVersionId = activeSourceVersionRef.current
      const currentApiConfig = currentSourceVersionId
        ? { ...apiConfig, sourceVersionId: currentSourceVersionId }
        : apiConfig

      setCandidateDetail(null)
      setActionResultCandidates(null)
      setCandidateError(null)
      setCandidateStaleSourceMessage(null)
      setCandidateSourceRefreshPending(false)
      setCandidateOperationStatus(null)
      setCandidateOperationError(null)
      setCandidateExplanation(null)
      setCandidateExplanationLoading(false)
      setCandidateExplanationError(null)
      setContextPackDetail(null)
      setContextPackLoading(false)
      setContextPackError(null)
      setCandidateLoading(true)
      try {
        const detail = await requestRewriteCandidate(apiClient, currentApiConfig, {
          text: currentSelection.text,
          range: currentSelection.range,
          actorIntent: label,
          currentTextWindow: currentEditorText(editorText, visibleAcceptedSentence),
        })
        setCandidateDetail(detail)
      } catch (error) {
        setCandidateError(errorMessage(error))
      } finally {
        setCandidateLoading(false)
      }
    },
    [apiClient, apiConfig, editorText, visibleAcceptedSentence],
  )

  // 选区菜单里的动作 → 打开候选抽屉
  const handleSelectionAction = useCallback(
    async (label: string) => {
      const currentSelection = selection
      setSelection(null)
      if (!currentSelection) {
        return
      }
      await requestSelectedTextCandidate(label, currentSelection)
    },
    [requestSelectedTextCandidate, selection],
  )

  const handleParagraphRewrite = useCallback(
    async (currentSelection: { text: string; range: { start: number; end: number } }) => {
      setSelection(null)
      await requestSelectedTextCandidate("改写这一段", currentSelection)
    },
    [requestSelectedTextCandidate],
  )

  const handleAskPick = useCallback(
    async (label: string, memoryTarget?: AskMemoryTarget) => {
      setAskOpen(false)
      setSelection(null)
      setDemoHighlight(false)
      setWritebackOpen(false)
      setAcceptance(null)
      setWritebackState(null)

      if (!apiConfig || !apiClient) {
        setDrawerOpen(true)
        return
      }

      const currentTextWindow = currentEditorText(editorText, visibleAcceptedSentence)

      if (isRiskCheckAsk(label)) {
        setDrawerOpen(true)
        setMemoryAnswerOpen(false)
        setCandidateDetail(null)
        setActionResultCandidates(null)
        setCandidateError(null)
        setCandidateStaleSourceMessage(null)
        setCandidateSourceRefreshPending(false)
        setCandidateOperationStatus(null)
        setCandidateOperationError(null)
        setCandidateExplanation(null)
        setCandidateExplanationLoading(false)
        setCandidateExplanationError(null)
        setContextPackDetail(null)
        setContextPackLoading(false)
        setContextPackError(null)
        setCandidateLoading(true)
        try {
          const findings = await requestRiskCheck(apiClient, apiConfig, {
            actorIntent: label,
            currentTextWindow,
            range: { start: 0, end: currentTextWindow.length },
          })
          setActionResultCandidates(toDrawerRiskCandidates(findings))
        setCandidateOperationStatus("风险检查已完成，没有写入正文或记忆。")
        } catch (error) {
          setCandidateError(errorMessage(error))
        } finally {
          setCandidateLoading(false)
        }
        return
      }

      if (isDirectionAsk(label)) {
        setDrawerOpen(true)
        setMemoryAnswerOpen(false)
        setCandidateDetail(null)
        setActionResultCandidates(null)
        setCandidateError(null)
        setCandidateStaleSourceMessage(null)
        setCandidateSourceRefreshPending(false)
        setCandidateOperationStatus(null)
        setCandidateOperationError(null)
        setCandidateExplanation(null)
        setCandidateExplanationLoading(false)
        setCandidateExplanationError(null)
        setContextPackDetail(null)
        setContextPackLoading(false)
        setContextPackError(null)
        setCandidateLoading(true)
        try {
          const beats = await requestNextDirection(apiClient, apiConfig, {
            actorIntent: label,
            currentTextWindow,
            insertOffset: currentTextWindow.length,
          })
          setActionResultCandidates(toDrawerBeatCandidates(beats))
          setCandidateOperationStatus("方向候选已生成；需要先生成正文候选，再由作者采纳。")
        } catch (error) {
          setCandidateError(errorMessage(error))
        } finally {
          setCandidateLoading(false)
        }
        return
      }

      if (!isWritingAsk(label)) {
        setDrawerOpen(false)
        setMemoryAnswerOpen(true)
        setMemoryAnswer(null)
        setMemoryAnswerError(null)
        setMemoryAnswerLoading(true)
        try {
          const answer = await answerWorkbenchMemory(apiClient, apiConfig, label, memoryTarget)
          setMemoryAnswer(answer)
        } catch (error) {
          setMemoryAnswerError(errorMessage(error))
        } finally {
          setMemoryAnswerLoading(false)
        }
        return
      }

      setDrawerOpen(true)
      setMemoryAnswerOpen(false)
      setCandidateDetail(null)
      setActionResultCandidates(null)
      setCandidateError(null)
      setCandidateStaleSourceMessage(null)
      setCandidateSourceRefreshPending(false)
      setCandidateOperationStatus(null)
      setCandidateOperationError(null)
      setCandidateExplanation(null)
      setCandidateExplanationLoading(false)
      setCandidateExplanationError(null)
      setContextPackDetail(null)
      setContextPackLoading(false)
      setContextPackError(null)
      setCandidateLoading(true)
      try {
        const detail = await requestContinuationCandidate(apiClient, apiConfig, {
          actorIntent: label,
          currentTextWindow,
          insertOffset: currentTextWindow.length,
        })
        setCandidateDetail(detail)
      } catch (error) {
        setCandidateError(errorMessage(error))
      } finally {
        setCandidateLoading(false)
      }
    },
    [apiClient, apiConfig, editorText, visibleAcceptedSentence],
  )

  // 候选抽屉里"选这句加入" → 插入正文 + 弹出记忆回写
  const handleAcceptSentence = useCallback(
    async (text: string) => {
      if (apiConfig && apiClient && candidateDetail) {
        setCandidateError(null)
        setCandidateStaleSourceMessage(null)
        try {
          const result = await acceptCandidateText(apiClient, apiConfig, candidateDetail, text)
          const nextConfig = { ...apiConfig, sourceVersionId: result.new_version_id }
          setCurrentSourceVersionId(result.new_version_id)
          setSourceDetail(await loadWorkbenchSource(apiClient, nextConfig))
          setAcceptance(result)
          setAcceptedSentence(null)
          setDrawerOpen(false)
          setWritebackOpen(true)
          if (projectOpen) {
            void refreshSourceDeltas()
          }
          if (memoryOpen) {
            void refreshMemoryPages()
            void refreshGraphEdges()
          }
        } catch (error) {
          if (isWorkbenchStaleSourceVersionError(error)) {
            setCandidateStaleSourceMessage(errorMessage(error))
            setCandidateOperationStatus(null)
            setCandidateOperationError(null)
            return
          }
          setCandidateError(errorMessage(error))
        }
        return
      }

      setAcceptedSentence(text)
      setDrawerOpen(false)
      setWritebackOpen(true)
    },
    [
      apiClient,
      apiConfig,
      candidateDetail,
      memoryOpen,
      projectOpen,
      refreshMemoryPages,
      refreshGraphEdges,
      refreshSourceDeltas,
      setCurrentSourceVersionId,
    ],
  )

  const handleRefreshCandidateSource = useCallback(async () => {
    if (!apiConfig || !apiClient) {
      return
    }
    setCandidateSourceRefreshPending(true)
    setCandidateOperationError(null)
    try {
      const sources = await loadWorkbenchSources(apiClient, apiConfig, "")
      setSourceItems(sources)
      const currentSource = sources.find((item) => item.source_id === apiConfig.sourceId)
      const latestVersionId = currentSource?.latest_version_id
      if (!latestVersionId) {
        throw new Error("没有找到最新正文版本。")
      }
      const nextConfig = { ...apiConfig, sourceVersionId: latestVersionId }
      setCurrentSourceVersionId(latestVersionId)
      setSourceDetail(await loadWorkbenchSource(apiClient, nextConfig))
      await refreshSourceVersions()
      if (projectOpen) {
        await refreshSourceDeltas()
      }
      setCandidateOperationStatus("已刷新到最新正文版本，请重新生成候选。")
    } catch (error) {
      setCandidateOperationError(errorMessage(error))
    } finally {
      setCandidateSourceRefreshPending(false)
    }
  }, [
    apiClient,
    apiConfig,
    projectOpen,
    refreshSourceDeltas,
    refreshSourceVersions,
    setCurrentSourceVersionId,
  ])

  const handleShowContext = useCallback(async () => {
    if (!apiConfig || !apiClient || !candidateDetail?.context_pack_id) {
      setContextPackError("候选缺少上下文依据。")
      return
    }
    setContextPackLoading(true)
    setContextPackError(null)
    try {
      const detail = await loadWorkbenchContextPack(
        apiClient,
        apiConfig,
        candidateDetail.context_pack_id,
      )
      setContextPackDetail(detail)
    } catch (error) {
      setContextPackError(errorMessage(error))
    } finally {
      setContextPackLoading(false)
    }
  }, [apiClient, apiConfig, candidateDetail])

  const handleExplainCandidate = useCallback(async () => {
    if (!apiConfig || !apiClient || !candidateDetail) {
      return
    }
    setCandidateExplanationLoading(true)
    setCandidateExplanationError(null)
    try {
      const detail = await explainWorkbenchCandidate(apiClient, apiConfig, candidateDetail.id)
      setCandidateExplanation(detail)
    } catch (error) {
      setCandidateExplanationError(errorMessage(error))
    } finally {
      setCandidateExplanationLoading(false)
    }
  }, [apiClient, apiConfig, candidateDetail])

  const handleRejectCandidate = useCallback(async () => {
    if (!apiConfig || !apiClient || !candidateDetail) {
      return
    }
    setCandidateOperationPending(true)
    setCandidateOperationError(null)
    try {
      const operation = await rejectWorkbenchCandidate(apiClient, apiConfig, candidateDetail.id)
      setCandidateDetail({ ...candidateDetail, status: operation.status })
      setCandidateOperationStatus("候选已退回，不会写入正文或记忆。")
    } catch (error) {
      setCandidateOperationError(errorMessage(error))
    } finally {
      setCandidateOperationPending(false)
    }
  }, [apiClient, apiConfig, candidateDetail])

  const handleOverrideCandidate = useCallback(
    async (reason: string) => {
      if (!apiConfig || !apiClient || !candidateDetail) {
        return
      }
      setCandidateOperationPending(true)
      setCandidateOperationError(null)
      try {
        const detail = await overrideWorkbenchCandidateBlock(
          apiClient,
          apiConfig,
          candidateDetail.id,
          reason,
        )
        setCandidateDetail(detail)
        setCandidateExplanation(detail)
        setCandidateOperationStatus("覆盖已记录，候选仍保留风险标记。")
      } catch (error) {
        setCandidateOperationError(errorMessage(error))
      } finally {
        setCandidateOperationPending(false)
      }
    },
    [apiClient, apiConfig, candidateDetail],
  )

  const handleReviseCandidate = useCallback(
    async (text: string) => {
      if (!apiConfig || !apiClient || !candidateDetail) {
        return
      }
      setCandidateOperationPending(true)
      setCandidateOperationError(null)
      try {
        const replacement = await reviseWorkbenchCandidate(
          apiClient,
          apiConfig,
          candidateDetail.id,
          text,
        )
        setCandidateDetail(replacement)
        setContextPackDetail(null)
        setCandidateOperationStatus("修订候选已保存，仍需作者采纳。")
      } catch (error) {
        setCandidateOperationError(errorMessage(error))
      } finally {
        setCandidateOperationPending(false)
      }
    },
    [apiClient, apiConfig, candidateDetail],
  )

  // 撤销刚插入的句子
  const handleUndoAccept = useCallback(() => {
    setAcceptedSentence(null)
    setWritebackOpen(false)
  }, [])

  const handleWritebackDecision = useCallback(
    async (
      itemRef: Record<string, unknown>,
      decision: "accept" | "reject" | "correct",
      details?: WritebackDecisionDetails,
    ) => {
      if (!apiConfig || !apiClient || !acceptance) {
        throw new Error("缺少系统写回上下文。")
      }
      await decideWorkbenchWritebackItem(apiClient, apiConfig, acceptance, {
        itemRef,
        decision,
        authorNote: details?.authorNote ?? writebackDecisionNote(decision),
        correction:
          details?.correction ?? (decision === "correct" ? { status: "author_flagged" } : {}),
        replacementRefs: details?.replacementRefs ?? [],
      })
      const nextState = await readWorkbenchWritebackState(apiClient, apiConfig, acceptance)
      setWritebackState(nextState)
      setWritebackError(null)
      if (nextState.job.status === "succeeded") {
        void refreshContextReadiness({ status: null })
      }
      if (projectOpen) {
        void refreshSourceDeltas()
      }
      if (memoryOpen) {
        void refreshMemoryPages()
        void refreshGraphEdges()
      }
    },
    [
      acceptance,
      apiClient,
      apiConfig,
      memoryOpen,
      projectOpen,
      refreshMemoryPages,
      refreshGraphEdges,
      refreshSourceDeltas,
      refreshContextReadiness,
    ],
  )

  const handleReviewItemSelect = useCallback(
    async (id: string) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setReviewDetailLoading(true)
      setReviewDetailError(null)
      try {
        const detail = await loadReviewItemDetail(apiClient, apiConfig, id)
        setReviewDetail(detail)
      } catch (error) {
        setReviewDetailError(errorMessage(error))
      } finally {
        setReviewDetailLoading(false)
      }
    },
    [apiClient, apiConfig],
  )

  const handleReviewOperation = useCallback(
    async (
      id: string,
      operation: "resolve" | "dismiss" | "reopen",
      resolution?: ReviewResolution,
      details?: ReviewResolveDetails,
    ) => {
      if (!apiConfig || !apiClient) {
        return
      }
      setReviewOperationPending(true)
      setReviewDetailError(null)
      try {
        await operateWorkbenchReviewItem(apiClient, apiConfig, id, {
          operation,
          resolution,
          authorNote: details?.authorNote ?? undefined,
          replacementRefs: details?.replacementRefs ?? [],
          correction: details?.correction ?? {},
        })
        const detail = await loadReviewItemDetail(apiClient, apiConfig, id)
        setReviewDetail(detail)
        setApiReviewItems(await loadWorkbenchReviewItems(apiClient, apiConfig))
        if (acceptance) {
          const nextState = await readWorkbenchWritebackState(apiClient, apiConfig, acceptance)
          setWritebackState(nextState)
        }
      } catch (error) {
        setReviewDetailError(errorMessage(error))
      } finally {
        setReviewOperationPending(false)
      }
    },
    [acceptance, apiClient, apiConfig],
  )

  useEffect(() => {
    if (!askOpen || !apiConfig || !apiClient) {
      setAskMemoryTargetOptions([])
      setAskMemoryTargetOptionsLoading(false)
      setAskMemoryTargetOptionsError(null)
      return
    }

    let cancelled = false
    setAskMemoryTargetOptionsLoading(true)
    setAskMemoryTargetOptionsError(null)
    loadWorkbenchEntities(apiClient, apiConfig, { limit: 25 })
      .then((response) => {
        if (!cancelled) {
          setAskMemoryTargetOptions(response.items)
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setAskMemoryTargetOptions([])
          setAskMemoryTargetOptionsError(errorMessage(error))
        }
      })
      .finally(() => {
        if (!cancelled) {
          setAskMemoryTargetOptionsLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [apiClient, apiConfig, askOpen])

  useEffect(() => {
    if (!apiConfig || !apiClient || reviewDetail?.review_type !== "alias_conflict") {
      setReviewEntityOptions([])
      setReviewEntityOptionsLoading(false)
      setReviewEntityOptionsError(null)
      return
    }

    let cancelled = false
    setReviewEntityOptionsLoading(true)
    setReviewEntityOptionsError(null)
    loadWorkbenchEntities(apiClient, apiConfig, {
      query: aliasEntityQuery(reviewDetail),
      limit: 25,
    })
      .then((response) => {
        if (!cancelled) {
          setReviewEntityOptions(response.items)
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setReviewEntityOptions([])
          setReviewEntityOptionsError(errorMessage(error))
        }
      })
      .finally(() => {
        if (!cancelled) {
          setReviewEntityOptionsLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [apiClient, apiConfig, reviewDetail])

  useEffect(() => {
    if (!apiConfig || !apiClient || reviewDetail?.review_type !== "alias_conflict") {
      setReviewSceneOptions([])
      setReviewSceneOptionsLoading(false)
      setReviewSceneOptionsError(null)
      return
    }

    let cancelled = false
    setReviewSceneOptionsLoading(true)
    setReviewSceneOptionsError(null)
    loadWorkbenchSceneOptions(apiClient, apiConfig)
      .then((response) => {
        if (!cancelled) {
          setReviewSceneOptions(response.items)
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setReviewSceneOptions([])
          setReviewSceneOptionsError(errorMessage(error))
        }
      })
      .finally(() => {
        if (!cancelled) {
          setReviewSceneOptionsLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [apiClient, apiConfig, reviewDetail])

  // ⌘K 打开 Ask，Esc 关闭浮层
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setAskOpen(true)
      }
      if (e.key === "Escape") {
        setSelection(null)
        setProjectOpen(false)
        setMemoryOpen(false)
        setAskOpen(false)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  // 引导演示：把每个状态映射到真实状态组合
  const goToDemo = useCallback(
    (s: DemoState) => {
      closeAll()
      switch (s) {
        case "a":
          break
        case "b":
          setDemoHighlight(true)
          setSelection({
            text: "demo",
            x: window.innerWidth * 0.32,
            y: 250,
            range: { start: 0, end: 4 },
          })
          break
        case "c":
          setAskOpen(true)
          break
        case "d":
          setDrawerOpen(true)
          break
        case "e":
          setAcceptedSentence(demoAcceptedSentence)
          setDrawerOpen(true)
          break
        case "f":
          setAcceptedSentence(demoAcceptedSentence)
          setWritebackOpen(true)
          break
        case "g":
          setReviewOpen(true)
          break
      }
    },
    [closeAll],
  )

  if (runtimeAuthRequired && configuredApiConfig && authConfig) {
    return (
      <div className="flex h-screen flex-col bg-background text-foreground">
        <main className="flex flex-1 items-center justify-center px-6">
          <section className="w-full max-w-md space-y-5 rounded-xl border border-border bg-card/80 p-6 text-left shadow-sm">
            <div className="space-y-2">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                Sextant Workbench
              </p>
              <h1 className="text-[18px] font-medium">登录生产工作台</h1>
              <p className="text-[13px] leading-relaxed text-muted-foreground">
                项目和正文上下文已配置。请用 Supabase Auth 会话连接；静态前端包不会包含
                bearer token。
              </p>
            </div>
            <form className="space-y-4" onSubmit={handleRuntimeAuthSubmit}>
              <div className="space-y-1.5">
                <label htmlFor="workbench-auth-email" className="text-[12px] text-muted-foreground">
                  邮箱
                </label>
                <input
                  id="workbench-auth-email"
                  value={authEmail}
                  onChange={(event) => setAuthEmail(event.target.value)}
                  autoComplete="email"
                  inputMode="email"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-[13px] outline-none transition-colors focus:border-primary/60"
                />
              </div>
              <div className="space-y-1.5">
                <label
                  htmlFor="workbench-auth-password"
                  className="text-[12px] text-muted-foreground"
                >
                  密码
                </label>
                <input
                  id="workbench-auth-password"
                  type="password"
                  value={authPassword}
                  onChange={(event) => setAuthPassword(event.target.value)}
                  autoComplete="current-password"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-[13px] outline-none transition-colors focus:border-primary/60"
                />
              </div>
              {authError && (
                <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
                  {authError}
                </p>
              )}
              <button
                type="submit"
                disabled={authPending}
                className="w-full rounded-md bg-primary px-3 py-2 text-[13px] font-medium text-primary-foreground transition-opacity disabled:cursor-not-allowed disabled:opacity-60"
              >
                {authPending ? "正在连接…" : "连接生产工作台"}
              </button>
            </form>
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              API：{configuredApiConfig.apiBaseUrl}
            </p>
          </section>
        </main>
      </div>
    )
  }

  if (!apiConfig && !demoMode) {
    return (
      <div className="flex h-screen flex-col bg-background text-foreground">
        <main className="flex flex-1 items-center justify-center px-6">
          <section className="max-w-md space-y-3 text-center">
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
              Sextant Workbench
            </p>
            <h1 className="text-[18px] font-medium">需要后端 API 配置</h1>
            <p className="text-[13px] leading-relaxed text-muted-foreground">
              生产工作台未连接。请通过后端配置提供项目、作者、正文和版本上下文。
            </p>
          </section>
        </main>
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      <TopBar
        projectHeader={projectHeader}
        onAskOpen={() => setAskOpen(true)}
        memoryOpen={memoryOpen}
        memoryCount={memoryPagesLoaded ? memoryPages.length : null}
        memoryLoading={memoryPagesLoading}
        onMemoryToggle={apiConfig ? handleMemoryToggle : undefined}
        projectOpen={projectOpen}
        onProjectToggle={handleProjectToggle}
        reviewItems={visibleReviewItems}
        reviewOpen={reviewOpen}
        onReviewToggle={() => setReviewOpen((v) => !v)}
        reviewDetail={reviewDetail}
        reviewDetailLoading={reviewDetailLoading}
        reviewDetailError={reviewDetailError}
        reviewEntityOptions={reviewEntityOptions}
        reviewEntityOptionsLoading={reviewEntityOptionsLoading}
        reviewEntityOptionsError={reviewEntityOptionsError}
        reviewSceneOptions={reviewSceneOptions}
        reviewSceneOptionsLoading={reviewSceneOptionsLoading}
        reviewSceneOptionsError={reviewSceneOptionsError}
        reviewSourceDeltaOptions={sourceDeltas}
        onReviewItemSelect={handleReviewItemSelect}
        reviewOperationPending={reviewOperationPending}
        onReviewResolve={(id, resolution, details) =>
          handleReviewOperation(id, "resolve", resolution, details)
        }
        onReviewDismiss={(id) => handleReviewOperation(id, "dismiss")}
        onReviewReopen={(id) => handleReviewOperation(id, "reopen")}
      />
      {projectOpen && (
        <ProjectPanel
          source={sourceDetail}
          sourceVersions={sourceVersions}
          sourceVersionsLoading={sourceVersionsLoading}
          sourceVersionsError={sourceVersionsError}
          sources={sourceItems}
          sourceSearch={sourceSearch}
          sourceListLoading={sourceListLoading}
          sourceListError={sourceListError}
          onSourceSearchChange={apiConfig ? handleSourceSearchChange : undefined}
          onCreateSource={apiConfig ? handleCreateSource : undefined}
          onArchiveSource={apiConfig ? handleArchiveSource : undefined}
          onSourceVersionSelect={apiConfig ? handleSourceVersionSelect : undefined}
          onSourceVersionDiff={apiConfig ? handleSourceVersionDiff : undefined}
          onSourceVersionRestore={apiConfig ? handleRestoreSourceVersion : undefined}
          sourceVersionDiff={sourceVersionDiff}
          sourceVersionDiffLoading={sourceVersionDiffLoading}
          sourceVersionDiffError={sourceVersionDiffError}
          sourceCreatePending={sourceCreatePending}
          sourceCreateStatus={sourceCreateStatus}
          sourceCreateError={sourceCreateError}
          sourceArchivePendingId={sourceArchivePendingId}
          sourceRestorePendingId={sourceRestorePendingId}
          sourceDeltas={sourceDeltas}
          sourceDeltaSearch={sourceDeltaSearch}
          sourceDeltaStatus={sourceDeltaStatus}
          sourceDeltaKind={sourceDeltaKind}
          sourceDeltaDetail={sourceDeltaDetail}
          sourceDeltasNextCursor={sourceDeltasNextCursor}
          sourceDeltaDetailLoading={sourceDeltaDetailLoading}
          sourceDeltaDetailError={sourceDeltaDetailError}
          loading={sourceDeltasLoading}
          error={sourceDeltasError}
          onSourceDeltaSearchChange={apiConfig ? handleSourceDeltaSearchChange : undefined}
          onSourceDeltaStatusChange={apiConfig ? handleSourceDeltaStatusChange : undefined}
          onSourceDeltaKindChange={apiConfig ? handleSourceDeltaKindChange : undefined}
          onSourceDeltaLoadMore={apiConfig ? handleSourceDeltaLoadMore : undefined}
          onRefresh={
            apiConfig
              ? () => {
                  void refreshSourceDeltas()
                  void refreshSourceVersions()
                  void refreshStorySchema()
                  void refreshProjectMembers()
                  void refreshProjectInvitations()
                }
              : undefined
          }
          storySchema={storySchema}
          storySchemaLoading={storySchemaLoading}
          storySchemaError={storySchemaError}
          storySchemaOverrideText={storySchemaOverrideText}
          storySchemaSavePending={storySchemaSavePending}
          storySchemaSaveStatus={storySchemaSaveStatus}
          storySchemaSaveError={storySchemaSaveError}
          storySchemaGenrePacks={storySchemaGenrePacks}
          storySchemaGenrePending={storySchemaGenrePending}
          storySchemaGenreStatus={storySchemaGenreStatus}
          storySchemaGenreError={storySchemaGenreError}
          projectMembers={projectMembers}
          projectMembersLoading={projectMembersLoading}
          projectMembersError={projectMembersError}
          projectMemberOperationPendingId={projectMemberOperationPendingId}
          projectMemberOperationStatus={projectMemberOperationStatus}
          projectMemberOperationError={projectMemberOperationError}
          projectInvitations={projectInvitations}
          projectInvitationsLoading={projectInvitationsLoading}
          projectInvitationsError={projectInvitationsError}
          projectInvitationOperationPendingId={projectInvitationOperationPendingId}
          projectInvitationOperationStatus={projectInvitationOperationStatus}
          projectInvitationOperationError={projectInvitationOperationError}
          onProjectMemberUpsert={apiConfig ? handleProjectMemberUpsert : undefined}
          onProjectMemberRevoke={apiConfig ? handleProjectMemberRevoke : undefined}
          onProjectInvitationCreate={apiConfig ? handleProjectInvitationCreate : undefined}
          onProjectInvitationProof={apiConfig ? handleProjectInvitationProof : undefined}
          onStorySchemaGenreSelect={apiConfig ? handleStorySchemaGenreSelect : undefined}
          onStorySchemaOverrideTextChange={setStorySchemaOverrideText}
          onStorySchemaOverrideSave={apiConfig ? handleStorySchemaOverrideSave : undefined}
          onSourceDeltaSelect={apiConfig ? handleSourceDeltaSelect : undefined}
          onClose={() => {
            setProjectOpen(false)
            setSourceDeltaDetail(null)
            setSourceDeltaDetailError(null)
          }}
        />
      )}
      {memoryOpen && (
        <MemoryPagePanel
          pages={memoryPages}
          detail={memoryPageDetail}
          graphEdges={graphEdges}
          loading={memoryPagesLoading}
          error={memoryPagesError}
          detailLoading={memoryPageDetailLoading}
          detailError={memoryPageDetailError}
          graphEdgesLoading={graphEdgesLoading}
          graphEdgesError={graphEdgesError}
          graphEdgeSearch={graphEdgeSearch}
          graphEdgeStatus={graphEdgeStatus}
          onOperateThread={apiConfig ? handleMemoryPageThreadOperation : undefined}
          operatingThreadId={memoryThreadOperatingId}
          operationError={memoryThreadOperationError}
          onSelect={handleMemoryPageSelect}
          onRefresh={() => {
            void refreshMemoryPages()
            void refreshGraphEdges()
          }}
          onGraphEdgeSearchChange={handleGraphEdgeSearchChange}
          onGraphEdgeStatusChange={handleGraphEdgeStatusChange}
          onClose={() => {
            setMemoryOpen(false)
            setMemoryPageDetail(null)
            setMemoryPageDetailError(null)
          }}
        />
      )}

      {/* 主体：编辑器为绝对主角，右侧场景小卡为辅 */}
      <div className="flex min-h-0 flex-1">
        <div className="relative flex min-w-0 flex-1 flex-col [--editor-column:576px] [--editor-gutter:2rem]">
          <Editor
            onSelect={handleSelect}
            onParagraphRewrite={handleParagraphRewrite}
            demoHighlight={demoHighlight}
            acceptedSentence={visibleAcceptedSentence}
            text={editorText}
            title={editorSource.title}
            chapter={editorSource.chapter}
            sourceError={sourceError}
            isSourceEditing={sourceEditOpen}
            sourceEditText={sourceEditText}
            sourceEditPending={sourceEditPending}
            sourceEditRefreshPending={sourceEditRefreshPending}
            sourceEditStatus={sourceEditStatus}
            sourceEditError={sourceEditError}
            sourceEditRejectedDraftText={sourceEditRejectedDraftText}
            onSourceEditStart={apiConfig && sourceDetail ? handleSourceEditStart : undefined}
            onSourceEditChange={setSourceEditText}
            onSourceEditCancel={handleSourceEditCancel}
            onSourceEditSave={handleSourceEditSave}
            onSourceEditRefresh={apiConfig ? handleSourceEditRefresh : undefined}
            onSourceEditMergeRejectedDraft={handleSourceEditMergeRejectedDraft}
            onSourceEditApplyRejectedDraft={handleSourceEditApplyRejectedDraft}
            onSourceEditDismissRejectedDraft={handleSourceEditDismissRejectedDraft}
          />
          {drawerOpen && (
            <CandidateDrawer
              onClose={() => setDrawerOpen(false)}
              onAcceptSentence={handleAcceptSentence}
              onRejectCandidate={apiConfig && candidateDetail ? handleRejectCandidate : undefined}
              onReviseSentence={apiConfig && candidateDetail ? handleReviseCandidate : undefined}
              candidates={
                apiConfig
                  ? candidateDetail
                    ? [toDrawerCandidate(candidateDetail)]
                    : actionResultCandidates ?? []
                  : undefined
              }
              loading={candidateLoading}
              error={candidateError}
              operationPending={candidateOperationPending}
              operationStatus={candidateOperationStatus}
              operationError={candidateOperationError}
              acceptDisabled={candidateAcceptDisabled(candidateDetail) || candidateOperationPending}
              acceptDisabledReason="高风险候选需要确认覆盖后才能采纳"
              staleSourceMessage={candidateStaleSourceMessage}
              sourceRefreshPending={candidateSourceRefreshPending}
              onRefreshSource={apiConfig ? handleRefreshCandidateSource : undefined}
              contextPack={contextPackDetail}
              contextLoading={contextPackLoading}
              contextError={contextPackError}
              onShowContext={apiConfig && candidateDetail ? handleShowContext : undefined}
              candidateExplanation={candidateExplanation}
              explanationLoading={candidateExplanationLoading}
              explanationError={candidateExplanationError}
              onExplainCandidate={apiConfig && candidateDetail ? handleExplainCandidate : undefined}
              canOverrideCandidate={candidateCanOverride(candidateDetail)}
              onOverrideCandidate={apiConfig && candidateDetail ? handleOverrideCandidate : undefined}
            />
          )}
          {demoMode && (
            <StateSwitcher
              value={resolveDemo({ selection, drawerOpen, askOpen, writebackOpen, reviewOpen, acceptedSentence: visibleAcceptedSentence })}
              onChange={goToDemo}
            />
          )}
        </div>
        <SceneCard
          data={sceneCardState}
          loading={Boolean(apiConfig) && sceneContextLoading}
          error={apiConfig ? sceneContextError : null}
          readiness={contextReadinessState}
          onUseDirection={handleAskPick}
        />
      </div>

      {/* 浮层 */}
      {selection && (
        <SelectionMenu x={selection.x} y={selection.y} onAction={handleSelectionAction} />
      )}
      {askOpen && (
        <AskPalette
          onClose={() => setAskOpen(false)}
          onPick={handleAskPick}
          memoryTargetOptions={askMemoryTargetOptions.map(askMemoryTargetOption)}
          memoryTargetsLoading={askMemoryTargetOptionsLoading}
          memoryTargetsError={askMemoryTargetOptionsError}
          suggestionContext={askSuggestionContext}
        />
      )}
      {memoryAnswerOpen && (
        <MemoryAnswerPanel
          answer={memoryAnswer}
          loading={memoryAnswerLoading}
          error={memoryAnswerError}
          onClose={() => setMemoryAnswerOpen(false)}
        />
      )}
      {writebackOpen && (
        <MemoryWriteback
          onClose={() => setWritebackOpen(false)}
          onUndoAll={handleUndoAccept}
          acceptance={acceptance}
          state={writebackState}
          loading={writebackLoading}
          error={writebackError}
          demoMode={demoMode}
          onDecision={apiConfig ? handleWritebackDecision : undefined}
        />
      )}

    </div>
  )
}

function storySchemaOverrideTextFromResponse(schema: ProjectStorySchemaResponse): string {
  const pack = schema.project_override_pack
  const entityTypes = pack?.entity_types ?? []
  const eventTypes = pack?.event_types ?? []
  const relations = pack?.relations ?? []
  return [
    "规则名称：项目规则",
    `实体类型：${schemaDefinitionNames(entityTypes, entityTypeDisplayName)}`,
    `事件类型：${schemaDefinitionNames(eventTypes, schemaNameDisplayName)}`,
    `关系：${schemaDefinitionNames(relations, relationDisplayName)}`,
    `抽取提示：${hasSchemaRecord(pack?.extraction_hints) ? "已配置" : "无"}`,
    `风险规则：${hasSchemaRecord(pack?.risk_rules) ? "已配置" : "无"}`,
  ].join("\n")
}

function parseStorySchemaOverrideText(text: string): WorkbenchStorySchemaOverrideInput {
  const trimmed = text.trim()
  if (trimmed && !trimmed.startsWith("{")) {
    return parseAuthorSchemaOverrideText(trimmed)
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed || "{}")
  } catch (error) {
    throw new Error(`高级规则无法解析：${errorMessage(error)}`)
  }
  if (!isRecord(parsed)) {
    throw new Error("高级规则必须是对象。")
  }
  const packName = typeof parsed.pack_name === "string" ? parsed.pack_name : "project-overrides"
  return {
    packName,
    entityTypes: recordDefinitionArray(parsed.entity_types, "entity_types"),
    eventTypes: storySchemaDefinitionArray(parsed.event_types, "event_types"),
    relations: storySchemaDefinitionArray(parsed.relations, "relations"),
    extractionHints: storySchemaRecordField(parsed.extraction_hints, "extraction_hints"),
    riskRules: storySchemaRecordField(parsed.risk_rules, "risk_rules"),
  }
}

function parseAuthorSchemaOverrideText(text: string): WorkbenchStorySchemaOverrideInput {
  const fields = new Map<string, string>()
  for (const line of text.split(/\r?\n/)) {
    const separator = line.indexOf("：") >= 0 ? line.indexOf("：") : line.indexOf(":")
    if (separator <= 0) continue
    fields.set(line.slice(0, separator).trim(), line.slice(separator + 1).trim())
  }
  return {
    packName: "project-overrides",
    entityTypes: parseAuthorList(fields.get("实体类型")).map(authorEntityType),
    eventTypes: parseAuthorList(fields.get("事件类型")).map((name) => ({ name })),
    relations: parseAuthorList(fields.get("关系")).map(authorRelation),
    extractionHints: {},
    riskRules: {},
  }
}

function schemaDefinitionNames(
  values: unknown[],
  labeler: (value: unknown) => string,
): string {
  const names = values.map(labeler).filter(Boolean)
  return names.length ? names.join("、") : "无"
}

function schemaNameDisplayName(value: unknown): string {
  if (!isRecord(value)) return typeof value === "string" ? schemaTermDisplayName(value) : ""
  const name = typeof value.name === "string" ? value.name : ""
  return schemaTermDisplayName(name)
}

function entityTypeDisplayName(value: unknown): string {
  const name = schemaNameDisplayName(value)
  if (name === "Artifact") return "物件"
  if (name === "Object") return "物件"
  if (name === "Character") return "角色"
  if (name === "Location") return "地点"
  return name
}

function relationDisplayName(value: unknown): string {
  const name = schemaNameDisplayName(value)
  if (name === "Guards") return "守护"
  if (name === "Owns") return "持有"
  if (name === "Knows") return "知道"
  return name
}

function schemaTermDisplayName(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/[_\s-]+/g, "_")
  if (!normalized) return ""
  if (normalized === "artifact") return "物件"
  if (normalized === "object") return "物件"
  if (normalized === "character") return "角色"
  if (normalized === "location") return "地点"
  if (normalized === "guards") return "守护"
  if (normalized === "owns") return "持有"
  if (normalized === "knows") return "知道"
  return humanReadableSchemaName(value)
}

function humanReadableSchemaName(value: string): string {
  return value
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase())
}

function hasSchemaRecord(value: unknown): boolean {
  return isRecord(value) && Object.keys(value).length > 0
}

function parseAuthorList(value: string | undefined): string[] {
  if (!value || value === "无" || value === "已配置") return []
  return value
    .split(/[、,，\n]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map(schemaTermName)
}

function schemaTermName(value: string): string {
  const normalized = value.trim().toLowerCase()
  if (normalized === "物件" || normalized === "artifact") return "artifact"
  if (normalized === "角色" || normalized === "character") return "character"
  if (normalized === "地点" || normalized === "location") return "location"
  if (normalized === "守护" || normalized === "guards") return "guards"
  if (normalized === "持有" || normalized === "owns") return "owns"
  if (normalized === "知道" || normalized === "knows") return "knows"
  return normalized.replace(/[\s-]+/g, "_")
}

function authorEntityType(name: string): Record<string, unknown> {
  if (name === "artifact") return { name, subtype_of: "object" }
  return { name }
}

function authorRelation(name: string): Record<string, unknown> {
  if (name === "guards") {
    return { name, subject_types: ["character"], object_types: ["artifact"] }
  }
  return { name }
}

function recordDefinitionArray(
  value: unknown,
  label: string,
): Array<Record<string, unknown>> {
  if (value === undefined) {
    return []
  }
  if (!Array.isArray(value) || value.some((item) => !isRecord(item))) {
    throw new Error(`${label} 必须是对象数组。`)
  }
  return value as Array<Record<string, unknown>>
}

function storySchemaDefinitionArray(
  value: unknown,
  label: string,
): Array<Record<string, unknown> | string> {
  if (value === undefined) {
    return []
  }
  if (!Array.isArray(value)) {
    throw new Error(`${label} 必须是数组。`)
  }
  for (const item of value) {
    if (typeof item !== "string" && !isRecord(item)) {
      throw new Error(`${label} 只能包含字符串或对象。`)
    }
  }
  return value as Array<Record<string, unknown> | string>
}

function storySchemaRecordField(value: unknown, label: string): Record<string, unknown> {
  if (value === undefined) {
    return {}
  }
  if (!isRecord(value)) {
    throw new Error(`${label} 必须是对象。`)
  }
  return value
}

function currentEditorText(sourceText: string, acceptedSentence: string | null): string {
  return [sourceText, acceptedSentence].filter(Boolean).join("\n")
}

export type WorkbenchEditorSourceView = {
  text: string
  title: string
  chapter: string
}

export function workbenchEditorSourceView(
  apiEnabled: boolean,
  demoEnabled: boolean,
  sourceDetail: Pick<SourceVersionResponse, "text" | "title" | "version_label"> | null,
): WorkbenchEditorSourceView {
  if (sourceDetail) {
    return {
      text: sourceDetail.text,
      title: sourceDetail.title,
      chapter: sourceDetail.version_label,
    }
  }
  if (apiEnabled) {
    return {
      text: "",
      title: "正文未加载",
      chapter: "等待后端正文",
    }
  }
  if (!demoEnabled) {
    return {
      text: "",
      title: "需要后端 API 配置",
      chapter: "生产工作台未连接",
    }
  }
  return {
    text: manuscript.join("\n"),
    title: demoSourceTitle,
    chapter: project.chapter,
  }
}

function candidateAcceptDisabled(candidate: CandidateDetailResponse | null): boolean {
  if (!candidate) {
    return false
  }
  const hasBlockingRisk = candidate.agent_review_findings.some(
    (finding) => finding.risk_level === "high" && !finding.can_offer_to_author,
  )
  return Boolean(
    candidate.status !== "offered_to_author" || (hasBlockingRisk && !candidate.override_reason),
  )
}

function candidateCanOverride(candidate: CandidateDetailResponse | null): boolean {
  if (!candidate || candidate.override_reason) {
    return false
  }
  return candidate.status === "blocked" && candidate.agent_review_findings.some(
    (finding) => finding.risk_level === "high" && !finding.can_offer_to_author,
  )
}

function aliasEntityQuery(detail: ReviewItemDetailResponse): string | undefined {
  if (stringField(detail.affected_refs, "target_entity_id")) return undefined
  const existingAlias = stringField(detail.existing_evidence, "alias_text")
  if (existingAlias) return existingAlias
  return stringField(detail.new_evidence, "alias_text") ?? undefined
}

function stringField(record: Record<string, unknown>, key: string): string | null {
  const value = record[key]
  return typeof value === "string" && value.trim() ? value : null
}

function errorMessage(error: unknown): string {
  return workbenchErrorMessage(error)
}

export function sceneCardFromContextPack(contextPack: WritingContextPackResponse): SceneCardState {
  const allowedKnowledge = recordArray(contextPack.pov_constraint, "allowed_knowledge")
    .map(formatAllowedKnowledgeEntry)
    .filter(Boolean)
  const forbiddenKnowledge = recordArray(contextPack.pov_constraint, "forbidden_knowledge")
    .map(formatMemoryEntry)
  const riskFacts = recordArray(contextPack.risk_context, "facts").map(formatMemoryEntry)
  const reviewItems = recordArray(contextPack.risk_context, "review_items").map((item) =>
    String(item.summary ?? item.review_type ?? "需要作者确认的记忆风险"),
  )
  const openThreads = contextPack.open_threads.map((item) =>
    String(item.title ?? item.summary ?? item.id ?? "待追踪线索"),
  )
  const recentEvents = contextPack.recent_events.map(formatEventEntry).filter(Boolean).slice(0, 3)
  const objectState = contextPack.object_location_state
    .map(formatObjectStateEntry)
    .filter(Boolean)
    .slice(0, 3)
  const agency = formatAgencyEntries(contextPack.character_agency_state).slice(0, 3)
  const styleNotes = recordArray(contextPack.style_memory, "samples")
    .map(formatStyleSample)
    .filter(Boolean)
    .slice(0, 2)
  const pitfalls = [...reviewItems, ...riskFacts].slice(0, 3).filter(Boolean)

  return {
    pov: contextPackPovLabel(contextPack) ?? "当前 POV",
    knows: allowedKnowledge.length > 0 ? allowedKnowledge : ["暂无已确认记忆"],
    notKnows: forbiddenKnowledge.length > 0 ? forbiddenKnowledge : ["未找到更多已确认证据"],
    pitfalls: pitfalls.length > 0 ? pitfalls : ["暂无开放风险"],
    pressurePoints: reviewItems.length > 0 ? reviewItems : ["继续保持证据边界"],
    openThreads: openThreads.length > 0 ? openThreads : ["等待新的正文变更"],
    recentEvents,
    objectState,
    agency,
    styleNotes,
  }
}

function contextPackPovLabel(contextPack: WritingContextPackResponse): string | null {
  const povCharacterId = stringValue(contextPack.pov_constraint.pov_character_id)
  if (povCharacterId) {
    const activePov = contextPack.active_characters.find(
      (character) => stringValue(character.id) === povCharacterId,
    )
    const activeLabel = refDisplayLabel(activePov)
    if (activeLabel) {
      return activeLabel
    }
    const agencyCharacter = recordArray(contextPack.character_agency_state, "characters")
      .map((entry) => entry.character_ref)
      .filter(isRecord)
      .find((character) => stringValue(character.id) === povCharacterId)
    const agencyLabel = refDisplayLabel(agencyCharacter)
    if (agencyLabel) {
      return agencyLabel
    }
  }

  const scene = contextPack.current_position.scene
  if (isRecord(scene)) {
    const sceneLabel = stringValue(scene.pov_character_label) ?? stringValue(scene.pov_character_name)
    if (sceneLabel) {
      return sceneLabel
    }
  }
  return null
}

function refDisplayLabel(ref: Record<string, unknown> | undefined): string | null {
  if (!ref) {
    return null
  }
  return (
    stringValue(ref.display_name) ??
    stringValue(ref.label) ??
    stringValue(ref.name) ??
    stringValue(ref.title) ??
    stringValue(ref.id)
  )
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null
}

function recordArray(section: Record<string, unknown>, key: string): Array<Record<string, unknown>> {
  const value = section[key]
  return Array.isArray(value) ? value.filter(isRecord) : []
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function formatMemoryEntry(entry: Record<string, unknown>): string {
  const subject = formatRef(entry.subject_ref)
  const predicate = predicateLabel(entry.predicate)
  const object = formatRef(entry.object_ref)
  if (subject || object) {
    return [subject, predicate, object].filter(Boolean).join(" · ")
  }
  return String(entry.summary ?? entry.id ?? "证据项")
}

function formatAllowedKnowledgeEntry(entry: Record<string, unknown>): string {
  const summary = String(entry.summary ?? "").trim()
  if (summary) {
    return summary
  }
  const knownRef = formatRef(entry.knows_ref)
  if (knownRef) {
    return knownRef === "事实" ? "已确认记忆" : `知道 · ${knownRef}`
  }
  return ""
}

function formatEventEntry(entry: Record<string, unknown>): string {
  const title = String(entry.title ?? entry.summary ?? entry.event_type ?? "").trim()
  const consequence = String(entry.consequence_summary ?? "").trim()
  if (title && consequence) {
    return `${title} · ${consequence}`
  }
  if (title) {
    return `事件 · ${title}`
  }
  return ""
}

function formatObjectStateEntry(entry: Record<string, unknown>): string {
  const subject = formatRef(entry.subject_ref)
  const relation = predicateLabel(entry.relation)
  const target = formatRef(entry.target_ref)
  if (!subject && !target) {
    return ""
  }
  return [subject, relation, target].filter(Boolean).join(" · ")
}

function formatAgencyEntries(state: Record<string, unknown>): string[] {
  return recordArray(state, "characters")
    .map((entry) => {
      const character = formatRef(entry.character_ref) || "角色"
      const nextAction = String(entry.natural_next_action ?? "").trim()
      return nextAction ? `${character} · ${nextAction}` : ""
    })
    .filter(Boolean)
}

function formatStyleSample(entry: Record<string, unknown>): string {
  const preview = String(entry.text_preview ?? "").trim()
  return preview ? `叙述样本 · ${preview}` : ""
}

function formatRef(value: unknown): string {
  return formatDisplayRef(value) || humanizeIdentifier(formatContextRefLabel(value))
}

function isWritingAsk(label: string): boolean {
  return label.includes("续写") || label.includes("改写") || label.includes("重写") || label.includes("试写")
}

function isRiskCheckAsk(label: string): boolean {
  return label.includes("查风险") || label.includes("写得太实") || label.includes("风险")
}

function isDirectionAsk(label: string): boolean {
  return label.includes("下面可以发生什么") || label.includes("下一步") || label.includes("方向")
}

function writebackDecisionNote(decision: "accept" | "reject" | "correct"): string {
  if (decision === "accept") {
    return "作者确认写回项"
  }
  if (decision === "reject") {
    return "作者拒绝写回项"
  }
  return "作者标记写回项需修正"
}

function mergeSourceEditDraft(
  latestText: string,
  rejectedDraftText: string,
  rejectedBaseText: string | null,
): string {
  const latestLines = latestText.split(/\r?\n/)
  const latestKeys = new Set(latestLines.map(normalizeMergeLine).filter(Boolean))
  const baseKeys = new Set(
    (rejectedBaseText ?? "").split(/\r?\n/).map(normalizeMergeLine).filter(Boolean),
  )
  const draftOnlyLines = rejectedDraftText
    .split(/\r?\n/)
    .filter((line) => {
      const key = normalizeMergeLine(line)
      return key && !latestKeys.has(key) && !baseKeys.has(key)
    })

  if (draftOnlyLines.length === 0) {
    return latestText
  }
  return `${latestText.replace(/\s+$/, "")}\n${draftOnlyLines.join("\n")}`
}

function normalizeMergeLine(line: string): string {
  return line.trim()
}

// 根据真实状态反推当前最接近的演示标记（用于高亮切换器）
function resolveDemo(s: {
  selection: Selection | null
  drawerOpen: boolean
  askOpen: boolean
  writebackOpen: boolean
  reviewOpen: boolean
  acceptedSentence: string | null
}): DemoState {
  if (s.reviewOpen) return "g"
  if (s.writebackOpen) return "f"
  if (s.drawerOpen) return s.acceptedSentence ? "e" : "d"
  if (s.askOpen) return "c"
  if (s.selection) return "b"
  return "a"
}

function askMemoryTargetOption(entity: CanonicalEntitySummaryResponse) {
  return {
    id: entity.id,
    entityType: entity.entity_type,
    label: entity.display_name,
  }
}
