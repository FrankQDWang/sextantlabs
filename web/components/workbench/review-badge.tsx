"use client"

import { useEffect, useState } from "react"
import type { ReviewItem } from "@/lib/workbench-data"
import {
  isReviewResolution,
  REVIEW_RESOLUTION_OPTIONS,
  type ReviewResolution,
} from "@/lib/workbench-api"
import { ShieldAlert, ChevronRight } from "lucide-react"
import type {
  CanonicalEntitySummaryResponse,
  ReviewItemDetailResponse,
  SourceDeltaSummaryResponse,
  StorySceneSummaryResponse,
} from "@/src/generated/sextant-api"
import {
  deltaKindLabel,
  formatRef,
  formatRefToken,
  humanizeIdentifier,
  reviewTypeLabel,
  severityLabel,
  statusLabel,
  typeLabel,
} from "@/lib/workbench-display"

export type ReviewResolveDetails = {
  authorNote: string | null
  replacementRefs: Record<string, unknown>[]
  correction?: Record<string, unknown>
}

type ReplacementRefType = "source_delta" | "review_item" | "source_span"

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const HIDDEN_SIDE_EFFECT_KEYS = new Set([
  "alias_record_id",
  "alias_boundary_record_ids",
  "old_entity_id",
  "target_entity_id",
  "graph_projection_run_id",
])

interface ReviewBadgeProps {
  items: ReviewItem[]
  open: boolean
  onToggle: () => void
  detail?: ReviewItemDetailResponse | null
  detailLoading?: boolean
  detailError?: string | null
  entityOptions?: CanonicalEntitySummaryResponse[]
  entityOptionsLoading?: boolean
  entityOptionsError?: string | null
  sceneOptions?: StorySceneSummaryResponse[]
  sceneOptionsLoading?: boolean
  sceneOptionsError?: string | null
  sourceDeltaOptions?: SourceDeltaSummaryResponse[]
  onItemSelect?: (id: string) => void
  operationPending?: boolean
  onResolve?: (
    id: string,
    resolution: ReviewResolution,
    details: ReviewResolveDetails,
  ) => void
  onDismiss?: (id: string) => void
  onReopen?: (id: string) => void
}

export function ReviewBadge({
  items,
  open,
  onToggle,
  detail = null,
  detailLoading = false,
  detailError = null,
  entityOptions = [],
  entityOptionsLoading = false,
  entityOptionsError = null,
  sceneOptions = [],
  sceneOptionsLoading = false,
  sceneOptionsError = null,
  sourceDeltaOptions = [],
  onItemSelect,
  operationPending = false,
  onResolve,
  onDismiss,
  onReopen,
}: ReviewBadgeProps) {
  const [selectedResolution, setSelectedResolution] =
    useState<ReviewResolution>("accepted_as_change")
  const [authorNote, setAuthorNote] = useState("")
  const [replacementSourceDeltaIds, setReplacementSourceDeltaIds] = useState("")
  const [replacementRefType, setReplacementRefType] =
    useState<ReplacementRefType>("source_delta")
  const [aliasTargetEntityId, setAliasTargetEntityId] = useState("")
  const [aliasValidFromSceneId, setAliasValidFromSceneId] = useState("")
  const [aliasValidUntilSceneId, setAliasValidUntilSceneId] = useState("")
  const [aliasApplyToMatchingAliases, setAliasApplyToMatchingAliases] = useState(false)
  const requiresReplacementEvidence = reviewResolutionRequiresReplacementEvidence(
    selectedResolution,
  )
  const replacementRefLabel = replacementTypeLabel(replacementRefType)
  const aliasRecordId = stringRef(detail?.affected_refs?.alias_record_id)
  const aliasCorrectionRequired = detail?.review_type === "alias_conflict"
  const aliasBoundaryEditorVisible =
    aliasCorrectionRequired &&
    (hasRefKey(detail?.affected_refs, "valid_from_scene_id") ||
      hasRefKey(detail?.affected_refs, "valid_until_scene_id") ||
      detail?.affected_refs?.alias_scope === "disguise_arc")
  const replacementRefs = parseReplacementRefs(replacementSourceDeltaIds, replacementRefType)
  const aliasBoundaryCorrection = aliasBoundaryEditorVisible
    ? aliasBoundaryCorrectionPayload(
        detail,
        aliasValidFromSceneId,
        aliasValidUntilSceneId,
        aliasApplyToMatchingAliases,
      )
    : {}
  const aliasCorrection =
    aliasCorrectionRequired && aliasRecordId && aliasTargetEntityId.trim()
      ? {
          alias_record_id: aliasRecordId,
          target_entity_id: aliasTargetEntityId.trim(),
          ...aliasBoundaryCorrection,
        }
      : undefined
  const canResolve =
    (!requiresReplacementEvidence ||
      (authorNote.trim().length > 0 && replacementRefs.length > 0)) &&
    (!aliasCorrectionRequired || Boolean(aliasCorrection))

  useEffect(() => {
    setSelectedResolution(defaultReviewResolution(detail))
    setAuthorNote("")
    setReplacementSourceDeltaIds("")
    setReplacementRefType("source_delta")
    setAliasTargetEntityId(stringRef(detail?.affected_refs?.target_entity_id) ?? "")
    setAliasValidFromSceneId(stringRef(detail?.affected_refs?.valid_from_scene_id) ?? "")
    setAliasValidUntilSceneId(stringRef(detail?.affected_refs?.valid_until_scene_id) ?? "")
    setAliasApplyToMatchingAliases(false)
  }, [detail])

  return (
    <div className="relative">
      <button
        onClick={onToggle}
        className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[12px] transition-colors ${
          open
            ? "border-[color:var(--warning)]/40 bg-[color:var(--warning)]/10 text-[color:var(--warning)]"
            : "border-border bg-card text-muted-foreground hover:text-foreground"
        }`}
      >
        <ShieldAlert className="h-3.5 w-3.5 text-[color:var(--warning)]" strokeWidth={1.75} />
        <span>{items.length} 个待处理</span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={onToggle} />
          <div className="animate-slide-up absolute right-0 top-[calc(100%+6px)] z-40 w-[340px] overflow-hidden rounded-xl border border-border bg-popover shadow-xl shadow-foreground/10">
            <div className="border-b border-border px-3.5 py-2.5">
              <p className="text-[12.5px] font-medium text-foreground">需要你看一眼</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                这些不会直接写进正式设定，先放在这里，不打断你写作。
              </p>
            </div>
            <div className="divide-y divide-border">
              {items.map((item, index) => (
                <button
                  key={`review:${item.id}:${index}`}
                  onClick={() => onItemSelect?.(item.id)}
                  className="group flex w-full items-start gap-2 px-3.5 py-2.5 text-left transition-colors hover:bg-accent"
                >
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[color:var(--warning)]" />
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] leading-snug text-foreground">{item.text}</p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {reviewHintLabel(item.hint)}
                    </p>
                  </div>
                  <ChevronRight
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground/0 transition-colors group-hover:text-muted-foreground"
                    strokeWidth={1.75}
                  />
                </button>
              ))}
            </div>
            {(detail || detailLoading || detailError) && (
              <div className="border-t border-border bg-muted/30 px-3.5 py-2.5">
                {detailLoading ? (
                  <p className="text-[11px] text-muted-foreground">读取复核详情…</p>
                ) : detailError ? (
                  <p className="text-[11px] text-destructive">{detailError}</p>
                ) : detail ? (
                  <div className="space-y-1">
                    <p className="text-[12px] font-medium text-foreground">{detail.summary}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {reviewTypeLabel(detail.review_type)} · {severityLabel(detail.severity)} ·{" "}
                      {statusLabel(detail.status)}
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      默认处理：
                      <span className="text-foreground/70">{statusLabel(detail.default_action)}</span>
                    </p>
                    {reviewEvidenceRows(detail).length > 0 && (
                      <div className="rounded-md border border-border bg-background/60 px-2 py-1.5">
                        <p className="text-[11px] font-medium text-foreground">证据来源</p>
                        <div className="mt-1 space-y-0.5">
                          {reviewEvidenceRows(detail).map((row, index) => (
                            <p
                              key={`${row}:${index}`}
                              className="text-[10.5px] text-muted-foreground"
                            >
                              {row}
                            </p>
                          ))}
                        </div>
                      </div>
                    )}
                    {sideEffectRows(detail.side_effects).length > 0 && (
                      <div className="rounded-md border border-border bg-background/60 px-2 py-1.5">
                        <p className="text-[11px] font-medium text-foreground">影响</p>
                        <div className="mt-1 space-y-0.5">
                          {sideEffectRows(detail.side_effects).map((row, index) => (
                            <p
                              key={`${row}:${index}`}
                              className="text-[10.5px] text-muted-foreground"
                            >
                              {row}
                            </p>
                          ))}
                        </div>
                      </div>
                    )}
                    {detail.status === "open" && (
                      <div className="space-y-1.5 pt-1">
                        <textarea
                          aria-label="复核处理说明"
                          value={authorNote}
                          onChange={(event) => setAuthorNote(event.target.value)}
                          rows={2}
                          placeholder="处理说明"
                          className="min-h-12 w-full resize-none rounded border border-border bg-background px-2 py-1 text-[11px] leading-snug text-foreground outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-primary/50"
                        />
                        {selectedResolution === "supersede" && (
                          <select
                            aria-label="替代证据类型"
                            value={replacementRefType}
                            onChange={(event) => {
                              if (isReplacementRefType(event.target.value)) {
                                setReplacementRefType(event.target.value)
                              }
                            }}
                            className="h-7 w-full rounded border border-border bg-background px-2 text-[11px] text-foreground outline-none transition-colors focus:border-primary/50"
                          >
                            <option value="source_delta">正文变更</option>
                            <option value="review_item">复核项</option>
                            <option value="source_span">证据段落</option>
                          </select>
                        )}
                        {replacementRefType === "source_delta" && sourceDeltaOptions.length > 0 && (
                          <select
                            aria-label="替代正文变更"
                            value={singleSourceDeltaSelection(replacementSourceDeltaIds)}
                            onChange={(event) => setReplacementSourceDeltaIds(event.target.value)}
                            className="h-7 w-full rounded border border-border bg-background px-2 text-[11px] text-foreground outline-none transition-colors focus:border-primary/50"
                          >
                            <option value="">选择最近的正文变更</option>
                            {sourceDeltaOptions.map((delta) => (
                              <option key={delta.id} value={delta.id}>
                                {sourceDeltaOptionLabel(delta)}
                              </option>
                            ))}
                          </select>
                        )}
                        {requiresReplacementEvidence &&
                          (replacementRefType !== "source_delta" ||
                            sourceDeltaOptions.length === 0) && (
                            <input
                              aria-label={`复核替代${replacementRefLabel}`}
                              value={replacementSourceDeltaIds}
                              onChange={(event) =>
                                setReplacementSourceDeltaIds(event.target.value)
                              }
                              placeholder={`替代 ${replacementRefLabel}`}
                              className="h-7 w-full rounded border border-border bg-background px-2 text-[11px] text-foreground outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-primary/50"
                            />
                          )}
                        {aliasCorrectionRequired && (
                          <div className="space-y-1">
                            <select
                              aria-label="选择目标角色"
                              value={entityOptionValue(aliasTargetEntityId, entityOptions)}
                              onChange={(event) => setAliasTargetEntityId(event.target.value)}
                              className="h-7 w-full rounded border border-border bg-background px-2 text-[11px] text-foreground outline-none transition-colors focus:border-primary/50"
                            >
                              <option value="">选择目标实体</option>
                              {entityOptions.map((entity) => (
                                <option key={entity.id} value={entity.id}>
                                  {entityOptionLabel(entity)}
                                </option>
                              ))}
                            </select>
                            {aliasBoundaryEditorVisible && (
                              <div className="space-y-1">
                                {sceneOptions.length > 0 ? (
                                  <div className="grid grid-cols-2 gap-1">
                                    <select
                                      aria-label="起始场景"
                                      value={aliasValidFromSceneId}
                                      onChange={(event) =>
                                        setAliasValidFromSceneId(event.target.value)
                                      }
                                      className="h-7 min-w-0 rounded border border-border bg-background px-2 text-[11px] text-foreground outline-none transition-colors focus:border-primary/50"
                                    >
                                      <option value="">不限定起点</option>
                                      {missingSceneOption(
                                        aliasValidFromSceneId,
                                        sceneOptions,
                                        "当前起点",
                                      )}
                                      {sceneOptions.map((scene) => (
                                        <option key={scene.id} value={scene.id}>
                                          {sceneOptionLabel(scene)}
                                        </option>
                                      ))}
                                    </select>
                                    <select
                                      aria-label="结束场景"
                                      value={aliasValidUntilSceneId}
                                      onChange={(event) =>
                                        setAliasValidUntilSceneId(event.target.value)
                                      }
                                      className="h-7 min-w-0 rounded border border-border bg-background px-2 text-[11px] text-foreground outline-none transition-colors focus:border-primary/50"
                                    >
                                      <option value="">不限定终点</option>
                                      {missingSceneOption(
                                        aliasValidUntilSceneId,
                                        sceneOptions,
                                        "当前终点",
                                      )}
                                      {sceneOptions.map((scene) => (
                                        <option key={scene.id} value={scene.id}>
                                          {sceneOptionLabel(scene, "end")}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                ) : (
                                  <div className="grid grid-cols-2 gap-1">
                                    <input
                                      aria-label="起始场景"
                                      value={aliasValidFromSceneId}
                                      onChange={(event) =>
                                        setAliasValidFromSceneId(event.target.value)
                                      }
                                      placeholder="起始场景 ID"
                                      className="h-7 min-w-0 rounded border border-border bg-background px-2 text-[11px] text-foreground outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-primary/50"
                                    />
                                    <input
                                      aria-label="结束场景"
                                      value={aliasValidUntilSceneId}
                                      onChange={(event) =>
                                        setAliasValidUntilSceneId(event.target.value)
                                      }
                                      placeholder="结束场景 ID"
                                      className="h-7 min-w-0 rounded border border-border bg-background px-2 text-[11px] text-foreground outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-primary/50"
                                    />
                                  </div>
                                )}
                                {detail.affected_refs?.alias_scope === "disguise_arc" && (
                                  <label className="flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
                                    <input
                                      aria-label="应用到同名伪装弧"
                                      type="checkbox"
                                      checked={aliasApplyToMatchingAliases}
                                      onChange={(event) =>
                                        setAliasApplyToMatchingAliases(event.target.checked)
                                      }
                                      className="h-3.5 w-3.5 rounded border-border accent-[color:var(--primary)]"
                                    />
                                    <span>应用到同名伪装弧</span>
                                  </label>
                                )}
                              </div>
                            )}
                            {entityOptionsLoading && (
                              <p className="text-[10.5px] text-muted-foreground">
                                正在读取实体候选…
                              </p>
                            )}
                            {entityOptionsError && (
                              <p className="text-[10.5px] text-destructive">
                                {entityOptionsError}
                              </p>
                            )}
                            {!entityOptionsLoading &&
                              !entityOptionsError &&
                              entityOptions.length === 0 && (
                                <p className="text-[10.5px] text-muted-foreground">
                                  暂无实体候选，稍后再处理。
                                </p>
                              )}
                            {sceneOptionsLoading && (
                              <p className="text-[10.5px] text-muted-foreground">
                                正在读取场景候选…
                              </p>
                            )}
                            {sceneOptionsError && (
                              <p className="text-[10.5px] text-destructive">
                                {sceneOptionsError}
                              </p>
                            )}
                          </div>
                        )}
                        {requiresReplacementEvidence && (
                          <p className="text-[10.5px] text-muted-foreground">
                            {selectedResolution === "supersede"
                              ? "需要处理说明和替代证据。"
                              : "需要处理说明和替代正文变更。"}
                          </p>
                        )}
                        <div className="flex items-center gap-1.5">
                          <select
                            aria-label="复核处理方式"
                            value={selectedResolution}
                            onChange={(event) => {
                              if (isReviewResolution(event.target.value)) {
                                const nextResolution = event.target.value
                                setSelectedResolution(nextResolution)
                                if (nextResolution !== "supersede") {
                                  setReplacementRefType("source_delta")
                                }
                              }
                            }}
                            className="h-6 min-w-0 rounded-md border border-border bg-card px-1.5 text-[11px] text-foreground outline-none focus:border-primary/50"
                          >
                            {REVIEW_RESOLUTION_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                          <button
                            disabled={operationPending || !canResolve}
                            onClick={() => {
                              const details: ReviewResolveDetails = {
                                authorNote: authorNote.trim() || null,
                                replacementRefs,
                              }
                              if (aliasCorrection) {
                                details.correction = aliasCorrection
                              }
                              onResolve?.(detail.id, selectedResolution, details)
                            }}
                            className="rounded-md bg-secondary px-2 py-0.5 text-[11px] font-medium text-secondary-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {operationPending ? "处理中" : "确认处理"}
                          </button>
                          <button
                            disabled={operationPending}
                            onClick={() => onDismiss?.(detail.id)}
                            className="rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            暂不处理
                          </button>
                        </div>
                      </div>
                    )}
                    {detail.status === "dismissed" && (
                      <div className="flex items-center gap-1.5 pt-1">
                        <button
                          disabled={operationPending}
                          onClick={() => onReopen?.(detail.id)}
                          className="rounded-md bg-secondary px-2 py-0.5 text-[11px] font-medium text-secondary-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {operationPending ? "处理中" : "重新打开"}
                        </button>
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function defaultReviewResolution(detail: ReviewItemDetailResponse | null): ReviewResolution {
  for (const action of detail?.suggested_actions ?? []) {
    const resolution = action.resolution
    if (isReviewResolution(resolution)) {
      return resolution
    }
  }
  if (isReviewResolution(detail?.default_action)) {
    return detail.default_action
  }
  return "accepted_as_change"
}

function parseReplacementRefs(
  value: string,
  defaultType: ReplacementRefType,
): Record<string, unknown>[] {
  return value
    .split(/[\s,]+/)
    .map((token) => token.trim())
    .filter(Boolean)
    .map((token) => {
      const separator = token.indexOf(":")
      if (separator > 0 && separator < token.length - 1) {
        return {
          type: token.slice(0, separator),
          id: token.slice(separator + 1),
        }
      }
      return { type: defaultType, id: token }
    })
}

function isReplacementRefType(value: unknown): value is ReplacementRefType {
  return value === "source_delta" || value === "review_item" || value === "source_span"
}

function replacementTypeLabel(type: ReplacementRefType): string {
  if (type === "review_item") return typeLabel("review_item")
  if (type === "source_span") return typeLabel("source_span")
  return typeLabel("source_delta")
}

function stringRef(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null
}

function hasRefKey(
  refs: ReviewItemDetailResponse["affected_refs"] | undefined,
  key: string,
): boolean {
  return Object.prototype.hasOwnProperty.call(refs ?? {}, key)
}

function aliasBoundaryCorrectionPayload(
  detail: ReviewItemDetailResponse | null,
  validFromSceneId: string,
  validUntilSceneId: string,
  applyToMatchingAliases: boolean,
): Record<string, unknown> {
  const correction: Record<string, unknown> = {}
  addAliasBoundaryCorrection(
    correction,
    detail?.affected_refs,
    "valid_from_scene_id",
    validFromSceneId,
  )
  addAliasBoundaryCorrection(
    correction,
    detail?.affected_refs,
    "valid_until_scene_id",
    validUntilSceneId,
  )
  if (applyToMatchingAliases) {
    correction.apply_to_matching_aliases = true
  }
  return correction
}

function addAliasBoundaryCorrection(
  correction: Record<string, unknown>,
  refs: ReviewItemDetailResponse["affected_refs"] | undefined,
  key: string,
  value: string,
): void {
  const trimmed = value.trim()
  if (trimmed) {
    correction[key] = trimmed
  } else if (hasRefKey(refs, key)) {
    correction[key] = null
  }
}

function entityOptionValue(
  value: string,
  options: CanonicalEntitySummaryResponse[],
): string {
  return options.some((option) => option.id === value) ? value : ""
}

function entityOptionLabel(entity: CanonicalEntitySummaryResponse): string {
  const castTier =
    entity.cast_tier && entity.cast_tier !== "unknown"
      ? ` · ${humanizeIdentifier(entity.cast_tier)}`
      : ""
  return `${entity.display_name} · ${typeLabel(entity.entity_type)}${castTier}`
}

function missingSceneOption(
  value: string,
  options: StorySceneSummaryResponse[],
  label: string,
) {
  const trimmed = value.trim()
  if (!trimmed || options.some((option) => option.id === trimmed)) {
    return null
  }
  return <option value={trimmed}>{`${label} · ${formatRefToken(trimmed)}`}</option>
}

function sceneOptionLabel(scene: StorySceneSummaryResponse, boundary?: "end"): string {
  const qualifier = scene.story_time ?? scene.scene_summary ?? scene.chapter_title
  const label = qualifier ? `${scene.position_label} · ${qualifier}` : scene.position_label
  return boundary === "end" ? `${label} · 终点` : label
}

function singleSourceDeltaSelection(value: string): string {
  const refs = parseReplacementRefs(value, "source_delta")
  if (refs.length !== 1) {
    return ""
  }
  const ref = refs[0]
  return ref.type === "source_delta" && typeof ref.id === "string" ? ref.id : ""
}

function sourceDeltaOptionLabel(delta: SourceDeltaSummaryResponse): string {
  const preview = delta.submitted_text_preview.trim()
  const compactPreview = preview.length > 24 ? `${preview.slice(0, 24)}...` : preview
  return `${deltaKindLabel(delta.delta_kind)} · ${statusLabel(delta.status)} · ${
    compactPreview || "无预览"
  }`
}

function reviewResolutionRequiresReplacementEvidence(resolution: ReviewResolution): boolean {
  return (
    resolution === "split" ||
    resolution === "merge" ||
    resolution === "fixed_by_text_edit" ||
    resolution === "supersede"
  )
}

function sideEffectRows(sideEffects: Record<string, unknown>): string[] {
  return Object.entries(sideEffects)
    .filter(([, value]) => value !== null && value !== undefined)
    .filter(([, value]) => !Array.isArray(value) || value.length > 0)
    .filter(([key]) => !HIDDEN_SIDE_EFFECT_KEYS.has(key))
    .map(([key, value]) => `${sideEffectLabel(key)} · ${sideEffectValue(value, key)}`)
}

function reviewEvidenceRows(detail: ReviewItemDetailResponse): string[] {
  return [
    ...evidenceRecordRows("新证据", detail.new_evidence),
    ...evidenceRecordRows("已有依据", detail.existing_evidence),
    ...affectedRefRows(detail.affected_refs),
  ]
}

function evidenceRecordRows(label: string, evidence: Record<string, unknown>): string[] {
  const rows: string[] = []
  const spanCount = valueCount(evidence.source_span_ids) + valueCount(evidence.source_span_refs)
  if (spanCount > 0) {
    rows.push(`${label} · 证据段落 ${spanCount}`)
  }
  const deltaCount = valueCount(evidence.source_delta_ids) + valueCount(evidence.source_delta_refs)
  if (deltaCount > 0) {
    rows.push(`${label} · 正文变更 ${deltaCount}`)
  }
  const replacementCount =
    valueCount(evidence.resolution_replacement_refs) + valueCount(evidence.replacement_refs)
  if (replacementCount > 0) {
    rows.push(`${label} · 替代证据 ${replacementCount}`)
  }
  const aliasText = evidenceText(evidence.alias_text)
  if (aliasText) {
    rows.push(`${label} · 别名 ${aliasText}`)
  }
  const textPreview =
    evidenceText(evidence.text_preview) ??
    evidenceText(evidence.local_context) ??
    evidenceText(evidence.source_text)
  if (textPreview) {
    rows.push(`${label} · 正文片段 ${textPreview}`)
  }
  return rows
}

function affectedRefRows(refs: Record<string, unknown>): string[] {
  const rows: string[] = []
  const factCount = valueCount(refs.fact_ids) + valueCount(refs.fact_id)
  if (factCount > 0) {
    rows.push(`关联对象 · 事实 ${factCount} 项`)
  }
  const pageCount = valueCount(refs.memory_page_ids) + valueCount(refs.memory_page_id)
  if (pageCount === 1) {
    rows.push("关联对象 · 记忆页已记录")
  } else if (pageCount > 1) {
    rows.push(`关联对象 · 记忆页 ${pageCount} 项`)
  }
  const deltaCount =
    valueCount(refs.source_delta_ids) +
    valueCount(refs.source_delta_id) +
    valueCount(refs.replacement_source_delta_ids)
  if (deltaCount > 0) {
    rows.push(`关联对象 · 正文变更 ${deltaCount}`)
  }
  const reviewCount =
    valueCount(refs.review_item_ids) +
    valueCount(refs.review_item_id) +
    valueCount(refs.replacement_review_item_ids)
  if (reviewCount > 0) {
    rows.push(`关联对象 · 复核项 ${reviewCount}`)
  }
  if (refs.source_id || refs.source_version_id || refs.raw_source_id) {
    rows.push("关联对象 · 正文来源已记录")
  }
  return rows
}

function valueCount(value: unknown): number {
  if (Array.isArray(value)) return value.length
  return value === null || value === undefined || value === "" ? 0 : 1
}

function evidenceText(value: unknown): string | null {
  if (typeof value !== "string") {
    return null
  }
  const trimmed = value.trim()
  if (!trimmed || UUID_PATTERN.test(trimmed)) {
    return null
  }
  return trimmed.length > 42 ? `${trimmed.slice(0, 42)}...` : trimmed
}

function sideEffectValue(value: unknown, key = ""): string {
  if (Array.isArray(value)) {
    if (value.length === 0) return "无"
    if (key.endsWith("_ids")) return `${value.length} 项已更新`
    return value.map((item) => refValue(item)).join(", ")
  }
  if (value && typeof value === "object") {
    return refValue(value)
  }
  if (typeof value === "number") return `${value} 项已更新`
  if (typeof value === "string") {
    return UUID_PATTERN.test(value.trim()) ? "已记录" : statusLabel(value)
  }
  return String(value)
}

function refValue(value: unknown): string {
  if (!value || typeof value !== "object") {
    if (typeof value === "string") {
      return UUID_PATTERN.test(value.trim()) ? "已记录" : statusLabel(value)
    }
    return String(value)
  }
  const ref = value as Record<string, unknown>
  if (typeof ref.type === "string" && typeof ref.id === "string") {
    if (
      typeof ref.label === "string" ||
      typeof ref.name === "string" ||
      typeof ref.title === "string"
    ) {
      return formatRef(ref)
    }
    return formatRefToken(ref)
  }
  return Object.entries(ref)
    .filter(([key]) => !HIDDEN_SIDE_EFFECT_KEYS.has(key))
    .map(([key, item]) => `${sideEffectLabel(key)} ${sideEffectValue(item, key)}`)
    .join(" · ") || "已记录"
}

function reviewHintLabel(hint: string): string {
  const [type, severity] = hint.split(" · ")
  if (!type || !severity) return hint
  return `${reviewTypeLabel(type)} · ${severityLabel(severity)}`
}

function sideEffectLabel(key: string): string {
  if (key === "memory_pages") return "记忆页"
  if (key === "memory_pages_marked_stale") return "需重写记忆页"
  if (key === "graph_projection") return "关系图谱"
  if (key === "promotion") return "设定确认"
  if (key === "review_queue") return "复核队列"
  if (key === "alias_correction") return "别名修正"
  if (key === "alias_boundary_correction") return "别名边界"
  if (key === "alias_boundary_records_updated") return "别名记录"
  if (key === "replacement_refs") return "替代证据"
  if (key === "fact_assertions_updated") return "事实"
  if (key === "alias_record_id") return "别名记录"
  if (key === "target_entity_id") return "目标实体"
  if (key === "old_entity_id") return "旧实体"
  if (key === "previous_valid_from_scene_id") return "原起始场景"
  if (key === "previous_valid_until_scene_id") return "原结束场景"
  if (key === "valid_from_scene_id") return "起始场景"
  if (key === "valid_until_scene_id") return "结束场景"
  if (key === "target_entity") return "目标实体"
  if (key === "fact_ids") return "事实"
  if (key === "memory_page_ids") return "记忆页"
  if (key === "graph_edges_created") return "关系边"
  if (key === "context_pack_readiness_ids") return "上下文依据"
  if (key === "context_pack_readiness") return "上下文依据"
  if (key === "context_pack_readiness_marked") return "上下文依据"
  if (key === "mentions_updated") return "提及"
  if (key === "author_note") return "作者说明"
  if (key === "graph_projection_run_id") return "关系图谱运行"
  if (key === "memory_page_rewrite_job_ids") return "记忆页重写任务"
  return humanizeIdentifier(key.replace(/_/g, " "))
}
