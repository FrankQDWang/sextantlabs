"use client"

import { useState } from "react"
import {
  Archive,
  Braces,
  Eye,
  FileText,
  GitCompareArrows,
  History,
  RefreshCw,
  RotateCcw,
  Shield,
  Trash2,
  UserPlus,
  X,
} from "lucide-react"
import type {
  ProjectMemberListResponse,
  ProjectInvitationResponse,
  ProjectStorySchemaResponse,
  SourceDeltaDetailResponse,
  SourceDeltaSummaryResponse,
  SourceListResponse,
  SourceVersionDiffResponse,
  SourceVersionListResponse,
  SourceVersionResponse,
  StorySchemaPackResponse,
} from "@/src/generated/sextant-api"
import type {
  WorkbenchProjectInvitationInput,
  WorkbenchProjectInvitationProofInput,
  WorkbenchProjectMemberRole,
  WorkbenchSourceCreateInput,
} from "@/lib/workbench-api"
import {
  deltaKindLabel,
  humanizeIdentifier,
  sourceScopeLabel,
  sourceTypeLabel,
  statusLabel,
} from "@/lib/workbench-display"

interface ProjectPanelProps {
  source: SourceVersionResponse | null
  sourceVersions: SourceVersionListResponse["items"]
  sourceVersionsLoading: boolean
  sourceVersionsError: string | null
  sources: SourceListResponse["items"]
  sourceSearch: string
  sourceListLoading: boolean
  sourceListError: string | null
  onSourceSearchChange?: (query: string) => void
  onCreateSource?: (input: WorkbenchSourceCreateInput) => void
  onArchiveSource?: (sourceId: string) => void
  onSourceVersionSelect?: (versionId: string) => void
  onSourceVersionDiff?: (versionId: string) => void
  onSourceVersionRestore?: (versionId: string) => void
  sourceVersionDiff?: SourceVersionDiffResponse | null
  sourceVersionDiffLoading?: boolean
  sourceVersionDiffError?: string | null
  sourceCreatePending?: boolean
  sourceCreateStatus?: string | null
  sourceCreateError?: string | null
  sourceArchivePendingId?: string | null
  sourceRestorePendingId?: string | null
  storySchema?: ProjectStorySchemaResponse | null
  storySchemaLoading?: boolean
  storySchemaError?: string | null
  storySchemaOverrideText?: string
  storySchemaSavePending?: boolean
  storySchemaSaveStatus?: string | null
  storySchemaSaveError?: string | null
  storySchemaGenrePacks?: StorySchemaPackResponse[]
  storySchemaGenrePending?: boolean
  storySchemaGenreStatus?: string | null
  storySchemaGenreError?: string | null
  projectMembers?: ProjectMemberListResponse["items"]
  projectMembersLoading?: boolean
  projectMembersError?: string | null
  projectMemberOperationPendingId?: string | null
  projectMemberOperationStatus?: string | null
  projectMemberOperationError?: string | null
  onProjectMemberUpsert?: (memberActorId: string, role: WorkbenchProjectMemberRole) => void
  onProjectMemberRevoke?: (memberActorId: string) => void
  projectInvitations?: ProjectInvitationResponse[]
  projectInvitationsLoading?: boolean
  projectInvitationsError?: string | null
  projectInvitationOperationPendingId?: string | null
  projectInvitationOperationStatus?: string | null
  projectInvitationOperationError?: string | null
  onProjectInvitationCreate?: (input: WorkbenchProjectInvitationInput) => void
  onProjectInvitationProof?: (
    invitationId: string,
    input: WorkbenchProjectInvitationProofInput,
  ) => void
  onStorySchemaGenreSelect?: (genrePackId: string | null) => void
  onStorySchemaOverrideTextChange?: (text: string) => void
  onStorySchemaOverrideSave?: () => void
  sourceDeltas: SourceDeltaSummaryResponse[]
  sourceDeltaSearch: string
  sourceDeltaStatus: string
  sourceDeltaKind: string
  sourceDeltaDetail: SourceDeltaDetailResponse | null
  sourceDeltasNextCursor: string | null
  sourceDeltaDetailLoading: boolean
  sourceDeltaDetailError: string | null
  loading: boolean
  error: string | null
  onSourceDeltaSearchChange?: (query: string) => void
  onSourceDeltaStatusChange?: (status: string) => void
  onSourceDeltaKindChange?: (kind: string) => void
  onSourceDeltaLoadMore?: () => void
  onRefresh?: () => void
  onSourceDeltaSelect?: (id: string) => void
  onClose: () => void
}

export function ProjectPanel({
  source,
  sourceVersions,
  sourceVersionsLoading,
  sourceVersionsError,
  sources,
  sourceSearch,
  sourceListLoading,
  sourceListError,
  onSourceSearchChange,
  onCreateSource,
  onArchiveSource,
  onSourceVersionSelect,
  onSourceVersionDiff,
  onSourceVersionRestore,
  sourceVersionDiff = null,
  sourceVersionDiffLoading = false,
  sourceVersionDiffError = null,
  sourceCreatePending = false,
  sourceCreateStatus = null,
  sourceCreateError = null,
  sourceArchivePendingId = null,
  sourceRestorePendingId = null,
  storySchema = null,
  storySchemaLoading = false,
  storySchemaError = null,
  storySchemaOverrideText = "",
  storySchemaSavePending = false,
  storySchemaSaveStatus = null,
  storySchemaSaveError = null,
  storySchemaGenrePacks = [],
  storySchemaGenrePending = false,
  storySchemaGenreStatus = null,
  storySchemaGenreError = null,
  projectMembers = [],
  projectMembersLoading = false,
  projectMembersError = null,
  projectMemberOperationPendingId = null,
  projectMemberOperationStatus = null,
  projectMemberOperationError = null,
  onProjectMemberUpsert,
  onProjectMemberRevoke,
  projectInvitations = [],
  projectInvitationsLoading = false,
  projectInvitationsError = null,
  projectInvitationOperationPendingId = null,
  projectInvitationOperationStatus = null,
  projectInvitationOperationError = null,
  onProjectInvitationCreate,
  onProjectInvitationProof,
  onStorySchemaGenreSelect,
  onStorySchemaOverrideTextChange,
  onStorySchemaOverrideSave,
  sourceDeltas,
  sourceDeltaSearch,
  sourceDeltaStatus,
  sourceDeltaKind,
  sourceDeltaDetail,
  sourceDeltasNextCursor,
  sourceDeltaDetailLoading,
  sourceDeltaDetailError,
  loading,
  error,
  onSourceDeltaSearchChange,
  onSourceDeltaStatusChange,
  onSourceDeltaKindChange,
  onSourceDeltaLoadMore,
  onRefresh,
  onSourceDeltaSelect,
  onClose,
}: ProjectPanelProps) {
  const [title, setTitle] = useState("")
  const [text, setText] = useState("")
  const [sourceType, setSourceType] = useState("author_notes")
  const [sourceScope, setSourceScope] = useState("author_note")
  const [memberActorId, setMemberActorId] = useState("")
  const [memberRole, setMemberRole] = useState<WorkbenchProjectMemberRole>("viewer")
  const [invitationActorId, setInvitationActorId] = useState("")
  const [invitationRole, setInvitationRole] = useState<WorkbenchProjectMemberRole>("viewer")
  const [invitationDeliveryProviderRef, setInvitationDeliveryProviderRef] = useState("")
  const [invitationDeliveryTargetRef, setInvitationDeliveryTargetRef] = useState("")
  const [invitationTokenIssuerRef, setInvitationTokenIssuerRef] = useState("")
  const [invitationDeliveryProofRef, setInvitationDeliveryProofRef] = useState("")
  const [invitationTokenProofRef, setInvitationTokenProofRef] = useState("")
  const [advancedSchemaOpen, setAdvancedSchemaOpen] = useState(false)

  const canCreate = Boolean(title.trim() && text.trim() && onCreateSource && !sourceCreatePending)
  const canUpsertMember = Boolean(
    memberActorId.trim() && onProjectMemberUpsert && !projectMemberOperationPendingId,
  )
  const canCreateInvitation = Boolean(
    invitationActorId.trim() &&
    invitationDeliveryProviderRef.trim() &&
    invitationDeliveryTargetRef.trim() &&
    onProjectInvitationCreate &&
    !projectInvitationOperationPendingId,
  )
  const canRecordInvitationProof = Boolean(
    invitationDeliveryProofRef.trim() &&
    onProjectInvitationProof &&
    !projectInvitationOperationPendingId,
  )

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <aside className="animate-slide-up fixed left-3 top-14 z-50 max-h-[calc(100vh-72px)] w-[380px] overflow-hidden rounded-xl border border-border bg-popover shadow-xl shadow-foreground/10">
        <div className="flex items-center justify-between border-b border-border px-3.5 py-2.5">
          <div className="flex items-center gap-2">
            <FileText className="h-3.5 w-3.5 text-primary" strokeWidth={1.75} />
            <h2 className="text-[12.5px] font-medium text-foreground">项目状态</h2>
          </div>
          <div className="flex items-center gap-1">
            {onRefresh && (
              <button
                aria-label="刷新项目状态"
                onClick={onRefresh}
                className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.75} />
              </button>
            )}
            <button
              aria-label="关闭项目状态"
              onClick={onClose}
              className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" strokeWidth={1.75} />
            </button>
          </div>
        </div>

        <div className="max-h-[calc(100vh-124px)] space-y-3 overflow-y-auto px-3.5 py-3 text-[12px]">
          <section className="rounded-md border border-border bg-muted/30 px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                正文版本
              </p>
              {sourceVersionsLoading && (
                <span className="text-[11px] text-muted-foreground">读取历史…</span>
              )}
            </div>
            {source ? (
              <div className="mt-1 space-y-1">
                <p className="font-medium text-foreground">{source.title}</p>
                <p className="text-[11px] text-muted-foreground">
                  {source.version_label} · {sourceTypeLabel(source.source_type)} ·{" "}
                  {sourceScopeLabel(source.source_scope)}
                </p>
                <p className="truncate text-[10.5px] text-muted-foreground/80">
                  版本指纹已记录
                </p>
              </div>
            ) : (
              <p className="mt-1 text-muted-foreground">正在读取正文版本…</p>
            )}
            {sourceVersionsError ? (
              <p className="mt-2 text-[11px] text-destructive">{sourceVersionsError}</p>
            ) : sourceVersions.length > 0 ? (
              <div className="mt-2 space-y-1" data-testid="source-version-history">
                {sourceVersions.slice(0, 4).map((version) => {
                  const isCurrent = version.version_id === source?.version_id
                  return (
                    <div
                      key={version.version_id}
                      className={`flex w-full items-center gap-1 rounded border transition-colors ${
                        isCurrent
                          ? "border-primary/30 bg-primary/8"
                          : "border-border bg-card hover:border-primary/40 hover:bg-accent/40"
                      }`}
                    >
                      <button
                        aria-label={`打开正文版本 ${version.version_label}`}
                        disabled={!onSourceVersionSelect || isCurrent}
                        onClick={() => onSourceVersionSelect?.(version.version_id)}
                        className="flex min-w-0 flex-1 items-center justify-between gap-2 px-2 py-1 text-left disabled:cursor-default"
                      >
                        <span className="min-w-0 truncate text-[11px] text-foreground">
                          {version.version_label}
                        </span>
                        <span className="flex shrink-0 items-center gap-1.5">
                          {isCurrent ? (
                            <span className="text-[10px] text-primary">当前</span>
                          ) : (
                            <Eye
                              className="h-3 w-3 text-muted-foreground"
                              strokeWidth={1.75}
                            />
                          )}
                          <span className="text-[10px] text-muted-foreground">
                            版本指纹
                          </span>
                        </span>
                      </button>
                      {!isCurrent && onSourceVersionRestore && (
                        <button
                          aria-label={`恢复正文版本 ${version.version_label}`}
                          disabled={sourceRestorePendingId === version.version_id}
                          onClick={() => onSourceVersionRestore(version.version_id)}
                          className="mr-1 flex h-6 w-6 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-background hover:text-foreground disabled:cursor-wait disabled:opacity-40"
                        >
                          <RotateCcw className="h-3 w-3" strokeWidth={1.75} />
                        </button>
                      )}
                      {!isCurrent && onSourceVersionDiff && (
                        <button
                          aria-label={`对比正文版本 ${version.version_label}`}
                          disabled={sourceVersionDiffLoading}
                          onClick={() => onSourceVersionDiff(version.version_id)}
                          className="mr-1 flex h-6 w-6 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-background hover:text-foreground disabled:cursor-wait disabled:opacity-40"
                        >
                          <GitCompareArrows className="h-3 w-3" strokeWidth={1.75} />
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            ) : null}
            {(sourceVersionDiff || sourceVersionDiffLoading || sourceVersionDiffError) && (
              <div className="mt-2 rounded-md border border-border bg-card px-2 py-1.5">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    版本对比
                  </p>
                  {sourceVersionDiffLoading ? (
                    <span className="text-[10.5px] text-muted-foreground">读取中…</span>
                  ) : sourceVersionDiff ? (
                    <span className="font-mono text-[10.5px] text-muted-foreground">
                      +{sourceVersionDiff.summary.insertions} / -
                      {sourceVersionDiff.summary.deletions}
                    </span>
                  ) : null}
                </div>
                {sourceVersionDiffError ? (
                  <p className="mt-1 text-[11px] text-destructive">{sourceVersionDiffError}</p>
                ) : sourceVersionDiff ? (
                  <div className="mt-1.5 space-y-1">
                    <div className="flex items-center justify-between gap-2 text-[10.5px] text-muted-foreground">
                      <span>
                        {sourceVersionDiff.base_version_label} →{" "}
                        {sourceVersionDiff.compare_version_label}
                      </span>
                      <span>版本指纹已对齐</span>
                    </div>
                    <div className="max-h-36 overflow-y-auto rounded border border-border bg-muted/30 font-mono text-[10.5px] leading-5">
                      {sourceVersionDiff.hunks.length > 0 ? (
                        sourceVersionDiff.hunks.flatMap((hunk) =>
                          hunk.lines.map((line, index) => (
                            <div
                              key={`${hunk.old_start}-${hunk.new_start}-${index}`}
                              className={`grid grid-cols-[34px_34px_18px_1fr] gap-1 px-1.5 ${
                                line.kind === "insert"
                                  ? "bg-emerald-500/8 text-emerald-700"
                                  : line.kind === "delete"
                                    ? "bg-destructive/8 text-destructive"
                                    : "text-muted-foreground"
                              }`}
                            >
                              <span>{line.old_line ?? ""}</span>
                              <span>{line.new_line ?? ""}</span>
                              <span>
                                {line.kind === "insert"
                                  ? "+"
                                  : line.kind === "delete"
                                    ? "-"
                                    : " "}
                              </span>
                              <span className="whitespace-pre-wrap break-words text-foreground/85">
                                {line.text}
                              </span>
                            </div>
                          )),
                        )
                      ) : (
                        <p className="px-1.5 py-1 text-muted-foreground">无文本差异</p>
                      )}
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </section>

          <section data-testid="project-members" className="rounded-md border border-border bg-muted/30 px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5">
                <Shield className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  成员
                </p>
              </div>
              {projectMembersLoading && (
                <span className="text-[11px] text-muted-foreground">读取中…</span>
              )}
            </div>

            {projectMembersError ? (
              <p className="mt-2 rounded-md border border-destructive/30 bg-destructive/8 px-2.5 py-2 text-destructive">
                {projectMembersError}
              </p>
            ) : projectMembers.length > 0 ? (
              <div className="mt-2 space-y-1.5">
                {projectMembers.map((member, index) => {
                  const displayLabel = memberDisplayLabel(member.role, index)
                  return (
                  <div
                    key={member.actor_id}
                    className="grid grid-cols-[1fr_auto_auto] items-center gap-2 rounded-md border border-border bg-card px-2 py-1.5"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-[10.5px] text-foreground">
                        {displayLabel}
                      </p>
                      <p className="mt-0.5 text-[10.5px] text-muted-foreground">
                        {memberRoleLabel(member.role)} · {statusLabel(member.status)}
                      </p>
                    </div>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] ${
                        member.status === "active"
                          ? "bg-emerald-500/10 text-emerald-700"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {memberRoleLabel(member.role)}
                    </span>
                    <button
                      aria-label={`撤销成员 ${displayLabel}`}
                      disabled={
                        !onProjectMemberRevoke ||
                        member.status !== "active" ||
                        projectMemberOperationPendingId === member.actor_id
                      }
                      onClick={() => onProjectMemberRevoke?.(member.actor_id)}
                      className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-35"
                    >
                      <Trash2 className="h-3 w-3" strokeWidth={1.75} />
                    </button>
                  </div>
                  )
                })}
              </div>
            ) : (
              <p className="mt-2 rounded-md border border-border bg-card px-2.5 py-2 text-muted-foreground">
                暂无成员
              </p>
            )}

            <div className="mt-2 grid grid-cols-[1fr_86px_auto] gap-1.5">
              <input
                aria-label="成员编号"
                value={memberActorId}
                onChange={(event) => setMemberActorId(event.target.value)}
                className="h-7 min-w-0 rounded-md border border-border bg-card px-2 font-mono text-[11px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
              />
              <select
                aria-label="成员角色"
                value={memberRole}
                onChange={(event) =>
                  setMemberRole(event.target.value as WorkbenchProjectMemberRole)
                }
                className="h-7 rounded-md border border-border bg-card px-1.5 text-[11px] text-foreground outline-none focus:border-primary/50"
              >
                <option value="viewer">读者</option>
                <option value="editor">编辑者</option>
                <option value="owner">所有者</option>
              </select>
              <button
                aria-label="添加或更新成员"
                disabled={!canUpsertMember}
                onClick={() => {
                  onProjectMemberUpsert?.(memberActorId.trim(), memberRole)
                  setMemberActorId("")
                }}
                className="flex h-7 w-7 items-center justify-center rounded-md bg-secondary text-secondary-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
              >
                <UserPlus className="h-3.5 w-3.5" strokeWidth={1.75} />
              </button>
            </div>
            {projectMemberOperationStatus && (
              <p className="mt-1.5 text-[11px] text-muted-foreground">
                {projectMemberOperationStatus}
              </p>
            )}
            {projectMemberOperationError && (
              <p className="mt-1.5 text-[11px] text-destructive">
                {projectMemberOperationError}
              </p>
            )}

            <div className="mt-3 border-t border-border/70 pt-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  邀请
                </p>
                {projectInvitationsLoading && (
                  <span className="text-[11px] text-muted-foreground">读取中…</span>
                )}
              </div>
              {projectInvitationsError ? (
                <p className="mt-2 rounded-md border border-destructive/30 bg-destructive/8 px-2.5 py-2 text-destructive">
                  {projectInvitationsError}
                </p>
              ) : projectInvitations.length > 0 ? (
                <div className="mt-2 space-y-1.5">
                  {projectInvitations.slice(0, 3).map((invitation, index) => {
                    const invitationLabel = `邀请 ${index + 1}`
                    return (
                      <div
                        key={invitation.id}
                        className="rounded-md border border-border bg-card px-2 py-1.5"
                      >
                        <div className="grid grid-cols-[1fr_auto] items-center gap-2">
                          <div className="min-w-0">
                            <p className="truncate text-[10.5px] text-foreground">
                              邀请 · {memberRoleLabel(invitation.role)}
                            </p>
                            <p className="mt-0.5 text-[10.5px] text-muted-foreground">
                              {invitationDeliveryLabel(invitation.delivery_status)} ·{" "}
                              {invitationTokenLabel(invitation)}
                            </p>
                          </div>
                          <button
                            aria-label={`记录外部证明 ${invitationLabel}`}
                            disabled={
                              !canRecordInvitationProof ||
                              invitation.status !== "pending_external_delivery" ||
                              projectInvitationOperationPendingId === invitation.id
                            }
                            onClick={() => {
                              onProjectInvitationProof?.(invitation.id, {
                                deliveryProofRef: invitationDeliveryProofRef.trim(),
                                tokenProofRef: invitationTokenProofRef.trim() || null,
                              })
                              setInvitationDeliveryProofRef("")
                              setInvitationTokenProofRef("")
                            }}
                            className="rounded-md bg-secondary px-2 py-1 text-[10.5px] font-medium text-secondary-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            证明
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="mt-2 rounded-md border border-border bg-card px-2.5 py-2 text-muted-foreground">
                  暂无邀请
                </p>
              )}

              <div className="mt-2 grid grid-cols-[1fr_86px_auto] gap-1.5">
                <input
                  aria-label="邀请对象编号"
                  value={invitationActorId}
                  onChange={(event) => setInvitationActorId(event.target.value)}
                  className="h-7 min-w-0 rounded-md border border-border bg-card px-2 font-mono text-[11px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
                />
                <select
                  aria-label="邀请对象角色"
                  value={invitationRole}
                  onChange={(event) =>
                    setInvitationRole(event.target.value as WorkbenchProjectMemberRole)
                  }
                  className="h-7 rounded-md border border-border bg-card px-1.5 text-[11px] text-foreground outline-none focus:border-primary/50"
                >
                  <option value="viewer">读者</option>
                  <option value="editor">编辑者</option>
                  <option value="owner">所有者</option>
                </select>
                <button
                  aria-label="记录邀请意图"
                  disabled={!canCreateInvitation}
                  onClick={() => {
                    onProjectInvitationCreate?.({
                      memberActorId: invitationActorId.trim(),
                      role: invitationRole,
                      deliveryProviderRef: invitationDeliveryProviderRef.trim(),
                      deliveryTargetRef: invitationDeliveryTargetRef.trim(),
                      tokenIssuerRef: invitationTokenIssuerRef.trim() || null,
                    })
                    setInvitationActorId("")
                    setInvitationDeliveryProviderRef("")
                    setInvitationDeliveryTargetRef("")
                    setInvitationTokenIssuerRef("")
                  }}
                  className="flex h-7 w-7 items-center justify-center rounded-md bg-secondary text-secondary-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <UserPlus className="h-3.5 w-3.5" strokeWidth={1.75} />
                </button>
              </div>
              <div className="mt-1.5 grid grid-cols-1 gap-1.5">
                <input
                  aria-label="邀请递送服务"
                  value={invitationDeliveryProviderRef}
                  onChange={(event) => setInvitationDeliveryProviderRef(event.target.value)}
                  className="h-7 rounded-md border border-border bg-card px-2 text-[11px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
                />
                <input
                  aria-label="邀请递送目标"
                  value={invitationDeliveryTargetRef}
                  onChange={(event) => setInvitationDeliveryTargetRef(event.target.value)}
                  className="h-7 rounded-md border border-border bg-card px-2 text-[11px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
                />
                <input
                  aria-label="邀请 Token 签发"
                  value={invitationTokenIssuerRef}
                  onChange={(event) => setInvitationTokenIssuerRef(event.target.value)}
                  className="h-7 rounded-md border border-border bg-card px-2 text-[11px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
                />
              </div>
              <div className="mt-1.5 grid grid-cols-2 gap-1.5">
                <input
                  aria-label="邀请递送证明"
                  value={invitationDeliveryProofRef}
                  onChange={(event) => setInvitationDeliveryProofRef(event.target.value)}
                  className="h-7 min-w-0 rounded-md border border-border bg-card px-2 text-[11px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
                />
                <input
                  aria-label="邀请 Token 证明"
                  value={invitationTokenProofRef}
                  onChange={(event) => setInvitationTokenProofRef(event.target.value)}
                  className="h-7 min-w-0 rounded-md border border-border bg-card px-2 text-[11px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
                />
              </div>
              {projectInvitationOperationStatus && (
                <p className="mt-1.5 text-[11px] text-muted-foreground">
                  {projectInvitationOperationStatus}
                </p>
              )}
              {projectInvitationOperationError && (
                <p className="mt-1.5 text-[11px] text-destructive">
                  {projectInvitationOperationError}
                </p>
              )}
            </div>
          </section>

          <section
            data-testid="project-story-schema"
            className="rounded-md border border-border bg-muted/30 px-3 py-2"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5">
                <Braces className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  故事规则
                </p>
              </div>
              {storySchemaLoading && (
                <span className="text-[11px] text-muted-foreground">读取中…</span>
              )}
            </div>
            {storySchemaError ? (
              <p className="mt-2 rounded-md border border-destructive/30 bg-destructive/8 px-2.5 py-2 text-destructive">
                {storySchemaError}
              </p>
            ) : storySchema ? (
              <div className="mt-2 space-y-2">
                <div className="grid grid-cols-3 gap-1.5">
                  <SchemaCount
                    label="实体"
                    value={schemaArrayCount(storySchema, "entity_types")}
                  />
                  <SchemaCount
                    label="事件"
                    value={schemaArrayCount(storySchema, "event_types")}
                  />
                  <SchemaCount
                    label="关系"
                    value={schemaArrayCount(storySchema, "relations")}
                  />
                </div>
                <div className="space-y-1.5">
                  <div className="grid grid-cols-[1fr_auto] items-center gap-1.5">
                    <select
                      aria-label="类型规则包"
                      value={storySchema.genre_schema_pack_id ?? ""}
                      disabled={!onStorySchemaGenreSelect || storySchemaGenrePending}
                      onChange={(event) =>
                        onStorySchemaGenreSelect?.(event.target.value || null)
                      }
                      className="h-7 min-w-0 rounded-md border border-border bg-card px-2 text-[11px] text-foreground outline-none focus:border-primary/50 disabled:cursor-not-allowed disabled:opacity-45"
                    >
                      <option value="">基础规则</option>
                      {storySchemaGenrePacks.map((pack) => (
                        <option key={pack.id} value={pack.id}>
                          {storySchemaPackLabel(pack)}
                        </option>
                      ))}
                    </select>
                    {storySchemaGenrePending && (
                      <span className="text-[10.5px] text-muted-foreground">保存中</span>
                    )}
                  </div>
                  {storySchemaGenreStatus && (
                    <p className="text-[11px] text-muted-foreground">
                      {storySchemaGenreStatus}
                    </p>
                  )}
                  {storySchemaGenreError && (
                    <p className="text-[11px] text-destructive">{storySchemaGenreError}</p>
                  )}
                </div>
                <div className="rounded-md border border-border bg-card px-2 py-1.5">
                  <button
                    type="button"
                    onClick={() => setAdvancedSchemaOpen((open) => !open)}
                    className="flex w-full items-center justify-between text-left text-[11px] text-muted-foreground transition-colors hover:text-foreground"
                  >
                    <span>高级规则编辑</span>
                    <span>{advancedSchemaOpen ? "收起" : "展开"}</span>
                  </button>
                  {advancedSchemaOpen && (
                    <div className="mt-1.5 space-y-1.5">
                      <textarea
                        aria-label="高级规则草稿"
                        value={storySchemaOverrideText}
                        onChange={(event) => onStorySchemaOverrideTextChange?.(event.target.value)}
                        className="min-h-36 w-full resize-y rounded-md border border-border bg-background px-2 py-1.5 text-[11px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
                      />
                      <div className="flex items-center justify-between gap-2">
                        <button
                          disabled={!onStorySchemaOverrideSave || storySchemaSavePending}
                          onClick={onStorySchemaOverrideSave}
                          className="rounded-md bg-secondary px-2 py-1 text-[11px] font-medium text-secondary-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          {storySchemaSavePending ? "保存中" : "保存规则"}
                        </button>
                        {storySchemaSaveStatus && (
                          <span className="text-[11px] text-muted-foreground">
                            {storySchemaSaveStatus}
                          </span>
                        )}
                      </div>
                      {storySchemaSaveError && (
                        <p className="text-[11px] text-destructive">{storySchemaSaveError}</p>
                      )}
                    </div>
                  )}
                </div>
                {!advancedSchemaOpen && storySchemaSaveStatus && (
                  <p className="text-[11px] text-muted-foreground">{storySchemaSaveStatus}</p>
                )}
              </div>
            ) : (
              <p className="mt-2 rounded-md border border-border bg-card px-2.5 py-2 text-muted-foreground">
                暂无高级规则覆盖
              </p>
            )}
          </section>

          <section data-testid="project-sources" className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                材料
              </p>
              {sourceListLoading && (
                <span className="text-[11px] text-muted-foreground">读取中…</span>
              )}
            </div>
            <input
              aria-label="搜索材料"
              value={sourceSearch}
              onChange={(event) => onSourceSearchChange?.(event.target.value)}
              className="h-7 w-full rounded-md border border-border bg-card px-2 text-[12px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
            />
            {sourceListError ? (
              <p className="rounded-md border border-destructive/30 bg-destructive/8 px-2.5 py-2 text-[12px] text-destructive">
                {sourceListError}
              </p>
            ) : sources.length > 0 ? (
              <div className="space-y-1.5">
                {sources.map((item) => (
                  <article key={item.source_id} className="rounded-md border border-border bg-card px-2.5 py-2">
                    <div className="flex items-center justify-between gap-3">
                      <p className="min-w-0 truncate text-[12px] font-medium text-foreground">
                        {item.title}
                      </p>
                      <div className="flex shrink-0 items-center gap-1">
                        <span className="text-[10.5px] text-muted-foreground">
                          {item.latest_version_label ?? "无版本"}
                        </span>
                        {onArchiveSource && !item.is_archived && item.source_id !== source?.source_id && (
                          <button
                            aria-label={`归档材料 ${item.title}`}
                            disabled={sourceArchivePendingId === item.source_id}
                            onClick={() => onArchiveSource(item.source_id)}
                            className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:cursor-wait disabled:opacity-40"
                          >
                            <Archive className="h-3 w-3" strokeWidth={1.75} />
                          </button>
                        )}
                      </div>
                    </div>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {sourceTypeLabel(item.source_type)} · {sourceScopeLabel(item.source_scope)} ·{" "}
                      {item.version_count} 个版本
                      {item.is_archived ? " · 已归档" : ""}
                    </p>
                  </article>
                ))}
              </div>
            ) : (
              <p className="rounded-md border border-border bg-muted/30 px-2.5 py-2 text-muted-foreground">
                暂无匹配材料
              </p>
            )}

            <div className="space-y-1.5 rounded-md border border-border bg-muted/30 px-2.5 py-2">
              <input
                aria-label="材料标题"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                className="h-7 w-full rounded-md border border-border bg-card px-2 text-[12px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
              />
              <div className="grid grid-cols-2 gap-1.5">
                <select
                  aria-label="材料类型"
                  value={sourceType}
                  onChange={(event) => setSourceType(event.target.value)}
                  className="h-7 rounded-md border border-border bg-card px-2 text-[12px] text-foreground outline-none focus:border-primary/50"
                >
                  <option value="author_notes">作者笔记</option>
                  <option value="draft_manuscript">正文草稿</option>
                  <option value="worldbuilding">世界设定</option>
                  <option value="character_sheet">角色卡</option>
                </select>
                <select
                  aria-label="材料范围"
                  value={sourceScope}
                  onChange={(event) => setSourceScope(event.target.value)}
                  className="h-7 rounded-md border border-border bg-card px-2 text-[12px] text-foreground outline-none focus:border-primary/50"
                >
                  <option value="author_note">作者笔记</option>
                  <option value="user_draft">用户草稿</option>
                  <option value="outline_plan">大纲计划</option>
                  <option value="reference_only">参考材料</option>
                </select>
              </div>
              <textarea
                aria-label="材料正文"
                value={text}
                onChange={(event) => setText(event.target.value)}
                className="min-h-16 w-full resize-none rounded-md border border-border bg-card px-2 py-1.5 text-[12px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
              />
              <div className="flex items-center justify-between gap-2">
                <button
                  disabled={!canCreate}
                  onClick={() => {
                    onCreateSource?.({
                      title: title.trim(),
                      sourceType,
                      sourceScope,
                      text: text.trim(),
                    })
                    setTitle("")
                    setText("")
                  }}
                  className="rounded-md bg-secondary px-2 py-1 text-[11px] font-medium text-secondary-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {sourceCreatePending ? "导入中" : "导入材料"}
                </button>
                {sourceCreateStatus && (
                  <span className="text-[11px] text-muted-foreground">{sourceCreateStatus}</span>
                )}
              </div>
              {sourceCreateError && (
                <p className="text-[11px] text-destructive">{sourceCreateError}</p>
              )}
            </div>
          </section>

          <section data-testid="project-source-deltas" className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <History className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  正文变更
                </p>
              </div>
              {loading && <span className="text-[11px] text-muted-foreground">读取中…</span>}
            </div>

            <div className="grid grid-cols-[1fr_auto_auto] gap-1.5">
              <input
                aria-label="搜索正文变更"
                value={sourceDeltaSearch}
                onChange={(event) => onSourceDeltaSearchChange?.(event.target.value)}
                className="h-7 min-w-0 rounded-md border border-border bg-card px-2 text-[12px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
              />
              <select
                aria-label="正文变更状态"
                value={sourceDeltaStatus}
                onChange={(event) => onSourceDeltaStatusChange?.(event.target.value)}
                className="h-7 w-[92px] rounded-md border border-border bg-card px-1.5 text-[11px] text-foreground outline-none focus:border-primary/50"
              >
                <option value="">全部状态</option>
                <option value="memory_writeback_queued">等待回写</option>
                <option value="memory_writeback_completed">回写完成</option>
                <option value="submitted">已提交</option>
                <option value="normalized">已规范化</option>
                <option value="span_extracted">证据已抽取</option>
                <option value="rejected_stale_base">版本已过期</option>
              </select>
              <select
                aria-label="正文变更类型"
                value={sourceDeltaKind}
                onChange={(event) => onSourceDeltaKindChange?.(event.target.value)}
                className="h-7 w-[74px] rounded-md border border-border bg-card px-1.5 text-[11px] text-foreground outline-none focus:border-primary/50"
              >
                <option value="">全部</option>
                <option value="insert">插入</option>
                <option value="replace">替换</option>
                <option value="delete">删除</option>
              </select>
            </div>

            {error ? (
              <p className="rounded-md border border-destructive/30 bg-destructive/8 px-2.5 py-2 text-[12px] text-destructive">
                {error}
              </p>
            ) : sourceDeltas.length > 0 ? (
              <div className="max-h-[300px] space-y-1.5 overflow-y-auto pr-1">
                {sourceDeltas.map((delta, index) => (
                  <button
                    key={delta.id}
                    aria-label={`打开正文变更 ${index + 1}`}
                    disabled={!onSourceDeltaSelect}
                    onClick={() => onSourceDeltaSelect?.(delta.id)}
                    className="w-full rounded-md border border-border bg-card px-2.5 py-2 text-left transition-colors hover:border-primary/40 hover:bg-accent/40 disabled:cursor-default disabled:hover:border-border disabled:hover:bg-card"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="min-w-0 truncate text-[12px] font-medium text-foreground">
                        {deltaKindLabel(delta.delta_kind)} · {statusLabel(delta.status)}
                      </p>
                      <span className="shrink-0 font-mono text-[10.5px] text-muted-foreground">
                        {delta.range_start}-{delta.range_end}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-foreground/80">
                      {delta.submitted_text_preview}
                    </p>
                    <div className="mt-1.5 flex items-center gap-2 text-[10.5px] text-muted-foreground">
                      <span>{delta.accepted_fragment_id ? "采纳片段" : "手动写入"}</span>
                      {delta.job && <span>任务 · {statusLabel(delta.job.status)}</span>}
                    </div>
                  </button>
                ))}
                {sourceDeltasNextCursor && (
                  <button
                    onClick={onSourceDeltaLoadMore}
                    disabled={loading || !onSourceDeltaLoadMore}
                    className="h-7 w-full rounded-md border border-border bg-muted/30 text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:bg-accent/40 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {loading ? "读取中…" : "加载更多"}
                  </button>
                )}
              </div>
            ) : (
              <p className="rounded-md border border-border bg-muted/30 px-2.5 py-2 text-muted-foreground">
                暂无正文变更
              </p>
            )}

            {(sourceDeltaDetail || sourceDeltaDetailLoading || sourceDeltaDetailError) && (
              <div
                data-testid="source-delta-detail"
                className="rounded-md border border-border bg-muted/30 px-2.5 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    正文变更详情
                  </p>
                  {sourceDeltaDetailLoading && (
                    <span className="text-[11px] text-muted-foreground">读取中…</span>
                  )}
                </div>
                {sourceDeltaDetailError ? (
                  <p className="mt-1.5 text-[12px] text-destructive">
                    {sourceDeltaDetailError}
                  </p>
                ) : sourceDeltaDetail ? (
                  <div className="mt-1.5 space-y-1.5">
                    <div className="flex flex-wrap gap-x-2 gap-y-1 text-[10.5px] text-muted-foreground">
                      <span>{deltaKindLabel(sourceDeltaDetail.delta_kind)}</span>
                      <span>{statusLabel(sourceDeltaDetail.status)}</span>
                      <span>
                        {sourceDeltaDetail.range_start}-{sourceDeltaDetail.range_end}
                      </span>
                      <span>{sourceTypeLabel(sourceDeltaDetail.source_type)}</span>
                      {sourceDeltaDetail.new_version_id && <span>新版本 · 已记录</span>}
                    </div>
                    <p className="whitespace-pre-wrap rounded-md bg-card px-2 py-1.5 text-[12px] leading-relaxed text-foreground/85">
                      {sourceDeltaDetail.submitted_text}
                    </p>
                    <p className="truncate text-[10.5px] text-muted-foreground/80">
                      正文对象已保存
                    </p>
                  </div>
                ) : null}
              </div>
            )}
          </section>
        </div>
      </aside>
    </>
  )
}

function SchemaCount({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-border bg-card px-2 py-1">
      <p className="text-[10.5px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 font-mono text-[12px] text-foreground">{value}</p>
    </div>
  )
}

function schemaArrayCount(schema: ProjectStorySchemaResponse, key: string): number {
  const value = schema.effective_schema[key]
  return Array.isArray(value) ? value.length : 0
}

function storySchemaPackLabel(pack: StorySchemaPackResponse): string {
  const name = pack.pack_name === "mystery" ? "悬疑" : humanizeIdentifier(pack.pack_name)
  const version = pack.version.replace(`${pack.pack_name}.`, "")
  return `${name} · ${version || "当前版"}`
}

function memberRoleLabel(role: string): string {
  if (role === "owner") return "所有者"
  if (role === "editor") return "编辑者"
  if (role === "viewer") return "读者"
  return humanizeIdentifier(role)
}

function memberDisplayLabel(role: string, index: number): string {
  return `${memberRoleLabel(role)} ${index + 1}`
}

function invitationDeliveryLabel(status: string): string {
  if (status === "sent") return "递送已记录"
  if (status === "not_sent") return "递送未记录"
  return statusLabel(status)
}

function invitationTokenLabel(invitation: ProjectInvitationResponse): string {
  if (!invitation.token_issuer_ref) return "无 Token 签发"
  if (invitation.token_status === "issued") return "Token 已签发"
  if (invitation.token_status === "not_issued") return "Token 未签发"
  return statusLabel(invitation.token_status)
}
