"use client"

import { useState } from "react"
import { writebackItems, type RiskLevel } from "@/lib/workbench-data"
import { BookmarkPlus, X, AlertTriangle, Check } from "lucide-react"
import type { CandidateAcceptResponse } from "@/src/generated/sextant-api"
import type { WorkbenchWritebackState } from "@/lib/workbench-api"
import {
  formatRef,
  humanizeIdentifier,
  predicateLabel,
  statusLabel,
  typeLabel,
} from "@/lib/workbench-display"

interface MemoryWritebackProps {
  onClose: () => void
  /** 撤销刚插入的句子（连同记忆一起回退） */
  onUndoAll: () => void
  acceptance?: CandidateAcceptResponse | null
  state?: WorkbenchWritebackState | null
  loading?: boolean
  error?: string | null
  demoMode?: boolean
  onDecision?: (
    itemRef: Record<string, unknown>,
    decision: "accept" | "reject" | "correct",
    details?: WritebackDecisionDetails,
  ) => Promise<void>
}

const dot: Record<RiskLevel, string> = {
  low: "bg-success",
  medium: "bg-[color:var(--warning)]",
  high: "bg-destructive",
}

type PreviewDecisionItem = {
  type: string
  id: string
  label: string
  summary: string
}

type CorrectionDraft = {
  note: string
  correctedText: string
  replacementSourceDeltaId: string
}

export type WritebackDecisionDetails = {
  authorNote?: string | null
  correction?: Record<string, unknown>
  replacementRefs?: Record<string, unknown>[]
}

const emptyCorrectionDraft: CorrectionDraft = {
  note: "",
  correctedText: "",
  replacementSourceDeltaId: "",
}

export function MemoryWriteback({
  onClose,
  onUndoAll,
  acceptance = null,
  state = null,
  loading = false,
  error = null,
  demoMode = true,
  onDecision,
}: MemoryWritebackProps) {
  // 每条都可被处理（记住/撤销/进入复核），处理完即从列表移除
  const [items, setItems] = useState(writebackItems)
  const [done, setDone] = useState(false)
  const [pendingDecisionId, setPendingDecisionId] = useState<string | null>(null)
  const [decidedIds, setDecidedIds] = useState<Set<string>>(() => new Set())
  const [decisionError, setDecisionError] = useState<string | null>(null)
  const [activeCorrectionKey, setActiveCorrectionKey] = useState<string | null>(null)
  const [correctionDrafts, setCorrectionDrafts] = useState<Record<string, CorrectionDraft>>({})
  const memoryPage = state?.preview.memory_pages[0]
  const memoryPageStatus = String(memoryPage?.canon_status ?? "")
  const previewDecisionItems = state ? previewItems(state) : []

  function resolveItem(id: string, undo: boolean) {
    if (undo) {
      onUndoAll()
      return
    }
    const next = items.filter((it) => it.id !== id)
    setItems(next)
    if (next.length === 0) {
      setDone(true)
    }
  }

  async function persistDecision(
    key: string,
    itemRef: Record<string, unknown>,
    decision: "accept" | "reject" | "correct",
    details?: WritebackDecisionDetails,
  ) {
    if (!onDecision) return
    setPendingDecisionId(key)
    setDecisionError(null)
    try {
      if (details) {
        await onDecision(itemRef, decision, details)
      } else {
        await onDecision(itemRef, decision)
      }
      setDecidedIds((current) => new Set(current).add(key))
      if (decision === "correct") {
        setActiveCorrectionKey(null)
      }
    } catch (decisionFailure) {
      setDecisionError(errorMessage(decisionFailure))
    } finally {
      setPendingDecisionId(null)
    }
  }

  function openCorrection(key: string) {
    setDecisionError(null)
    setActiveCorrectionKey(key)
    setCorrectionDrafts((current) => ({
      ...current,
      [key]: current[key] ?? emptyCorrectionDraft,
    }))
  }

  function updateCorrectionDraft(key: string, patch: Partial<CorrectionDraft>) {
    setCorrectionDrafts((current) => ({
      ...current,
      [key]: {
        ...(current[key] ?? emptyCorrectionDraft),
        ...patch,
      },
    }))
  }

  async function submitCorrection(
    key: string,
    itemRef: Record<string, unknown>,
    label: string,
  ) {
    const draft = correctionDrafts[key] ?? emptyCorrectionDraft
    const note = draft.note.trim()
    const correctedText = draft.correctedText.trim()
    const replacementRefs = parseReplacementRefs(draft.replacementSourceDeltaId)
    if (!note && !correctedText) {
      setDecisionError("请先写修正说明或修正值。")
      return
    }
    const correction: Record<string, unknown> = {
      status: "author_corrected",
    }
    if (note) {
      correction.note = note
    }
    if (correctedText) {
      correction.corrected_text = correctedText
    }
    if (replacementRefs.length) {
      correction.replacement_refs = replacementRefs
    }
    await persistDecision(key, itemRef, "correct", {
      authorNote: note || `作者提交 ${label} 修正。`,
      correction,
      replacementRefs,
    })
  }

  async function decideFact(fact: Record<string, unknown>, decision: "accept" | "reject") {
    const id = factId(fact)
    if (!id || !onDecision) return
    const key = `fact_assertion:${id}`
    await persistDecision(key, { type: "fact_assertion", id }, decision)
  }

  async function decidePreviewItem(
    item: PreviewDecisionItem,
    decision: "accept" | "reject",
  ) {
    if (!onDecision) return
    const key = `${item.type}:${item.id}`
    await persistDecision(key, { type: item.type, id: item.id }, decision)
  }

  function renderCorrectionEditor(
    key: string,
    itemRef: Record<string, unknown>,
    label: string,
    disabled: boolean,
  ) {
    const draft = correctionDrafts[key] ?? emptyCorrectionDraft
    return (
      <div className="mt-1.5 space-y-1.5 rounded-md border border-border bg-background/60 p-1.5">
        <textarea
          aria-label={`修正说明 ${label}`}
          value={draft.note}
          onChange={(event) => updateCorrectionDraft(key, { note: event.target.value })}
          rows={2}
          placeholder="作者修正说明"
          className="min-h-12 w-full resize-none rounded border border-border bg-background px-2 py-1 text-[11px] leading-snug text-foreground outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-primary/50"
        />
        <textarea
          aria-label={`修正值 ${label}`}
          value={draft.correctedText}
          onChange={(event) =>
            updateCorrectionDraft(key, { correctedText: event.target.value })
          }
          rows={2}
          placeholder="修正后的记忆内容"
          className="min-h-12 w-full resize-none rounded border border-border bg-background px-2 py-1 text-[11px] leading-snug text-foreground outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-primary/50"
        />
        <input
          aria-label={`替代正文变更 ${label}`}
          value={draft.replacementSourceDeltaId}
          onChange={(event) =>
            updateCorrectionDraft(key, { replacementSourceDeltaId: event.target.value })
          }
          placeholder="可选：正文变更引用"
          className="h-7 w-full rounded border border-border bg-background px-2 text-[11px] text-foreground outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-primary/50"
        />
        <div className="flex items-center gap-1.5">
          <button
            aria-label={`提交修正 ${label}`}
            disabled={disabled}
            onClick={() => submitCorrection(key, itemRef, label)}
            className="rounded-md bg-secondary px-2 py-0.5 text-[11px] font-medium text-secondary-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
          >
            {pendingDecisionId === key ? "记录中" : "提交修正"}
          </button>
          <button
            aria-label={`取消修正 ${label}`}
            disabled={disabled}
            onClick={() => setActiveCorrectionKey(null)}
            className="rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline disabled:cursor-not-allowed disabled:opacity-50"
          >
            取消
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="animate-slide-up fixed bottom-4 right-4 z-40 w-[340px] overflow-hidden rounded-xl border border-border bg-popover shadow-xl shadow-foreground/10">
      {/* 头 */}
      <div className="flex items-center justify-between border-b border-border px-3.5 py-2.5">
        <div className="flex items-center gap-2">
          <BookmarkPlus className="h-3.5 w-3.5 text-primary" strokeWidth={1.75} />
          <span className="text-[12.5px] font-medium text-foreground">我准备记住这些</span>
        </div>
        <button
          onClick={onClose}
          className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          aria-label="关闭"
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.75} />
        </button>
      </div>

      {acceptance ? (
        <div className="px-3.5 py-3">
          <div className="flex items-start gap-2">
            <span className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-success/12 text-success">
              <Check className="h-3 w-3" strokeWidth={2} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-medium text-foreground">已创建正文变更</p>
              <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
                正文变更已写入，回写状态由系统读取；处理完成后会显示证据链。
              </p>
              <div className="mt-2 space-y-1 font-mono text-[10.5px] text-muted-foreground">
                <p>正文变更 · 已记录</p>
                <p>
                  回写任务
                  {state
                    ? ` · ${statusLabel(state.job.status)}`
                    : loading
                      ? " · 读取中"
                      : " · 已排队"}
                </p>
              </div>
              {error && (
                <p className="mt-2 text-[11px] leading-snug text-destructive">{error}</p>
              )}
              {state && (
                <div className="mt-2 grid grid-cols-3 gap-1.5 text-center text-[10.5px]">
                  <div className="rounded border border-border bg-muted/40 px-1 py-1">
                    <p className="font-medium text-foreground">
                      {previewCountLabel(state, state.preview.source_spans.length)}
                    </p>
                    <p className="text-muted-foreground">证据段落</p>
                  </div>
                  <div className="rounded border border-border bg-muted/40 px-1 py-1">
                    <p className="font-medium text-foreground">
                      {previewCountLabel(state, state.preview.fact_assertions.length)}
                    </p>
                    <p className="text-muted-foreground">事实</p>
                  </div>
                  <div className="rounded border border-border bg-muted/40 px-1 py-1">
                    <p className="font-medium text-foreground">
                      {previewCountLabel(state, state.preview.review_items.length)}
                    </p>
                    <p className="text-muted-foreground">复核</p>
                  </div>
                </div>
              )}
              {state && previewIsEmpty(state) && (
                <p className="mt-2 rounded border border-border bg-muted/30 px-2 py-1.5 text-[11px] text-muted-foreground">
                  {state.job.status === "succeeded" || state.job.status === "completed"
                    ? "未生成新的事实或复核项"
                    : "证据链整理中"}
                </p>
              )}
              {memoryPage && (
                <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
                  记忆页 ·{" "}
                  <span className="text-foreground/75">
                    {humanizeIdentifier(String(memoryPage.title ?? memoryPage.id))}
                  </span>
                  {memoryPageStatus === "stale" && (
                    <span className="text-destructive"> · 需重写</span>
                  )}
                </p>
              )}
              {state?.preview.fact_assertions.length ? (
                <div className="mt-2 space-y-1.5">
                  {state.preview.fact_assertions.slice(0, 3).map((fact) => {
                    const id = factId(fact)
                    const key = `fact_assertion:${id}`
                    const decided = Boolean(id && decidedIds.has(key))
                    return (
                      <div
                        key={id ? key : `fact_assertion:${factLabel(fact)}`}
                        className="rounded border border-border bg-muted/30 px-2 py-1.5"
                      >
                        <p className="truncate text-[11px] text-foreground/80">
                          {factLabel(fact)}
                        </p>
                        <div className="mt-1 flex items-center gap-1.5">
                          <button
                            disabled={!onDecision || !id || pendingDecisionId === key || decided}
                            onClick={() => decideFact(fact, "accept")}
                            className="rounded-md bg-secondary px-2 py-0.5 text-[11px] font-medium text-secondary-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {decided ? "已记录" : pendingDecisionId === key ? "记录中" : "确认"}
                          </button>
                          <button
                            disabled={!onDecision || !id || pendingDecisionId === key || decided}
                            onClick={() => openCorrection(key)}
                            className="rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            需改
                          </button>
                          <button
                            disabled={!onDecision || !id || pendingDecisionId === key || decided}
                            onClick={() => decideFact(fact, "reject")}
                            className="rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            不写入
                          </button>
                        </div>
                        {activeCorrectionKey === key &&
                          renderCorrectionEditor(
                            key,
                            { type: "fact_assertion", id },
                            "事实",
                            !onDecision || !id || pendingDecisionId === key || decided,
                          )}
                      </div>
                    )
                  })}
                </div>
              ) : null}
              {previewDecisionItems.length ? (
                <div className="mt-2 space-y-1.5">
                  {previewDecisionItems.slice(0, 4).map((item) => {
                    const key = `${item.type}:${item.id}`
                    const decided = decidedIds.has(key)
                    return (
                      <div
                        key={key}
                        data-testid={`writeback-preview-${item.type}-${item.id}`}
                        className="rounded border border-border bg-muted/30 px-2 py-1.5"
                      >
                        <p className="truncate text-[11px] text-foreground/80">
                          {item.label} · {item.summary}
                        </p>
                        <div className="mt-1 flex items-center gap-1.5">
                          <button
                            aria-label={`确认 ${item.label} ${item.summary}`}
                            disabled={!onDecision || pendingDecisionId === key || decided}
                            onClick={() => decidePreviewItem(item, "accept")}
                            className="rounded-md bg-secondary px-2 py-0.5 text-[11px] font-medium text-secondary-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {decided ? "已记录" : pendingDecisionId === key ? "记录中" : "确认"}
                          </button>
                          <button
                            aria-label={`需改 ${item.label} ${item.summary}`}
                            disabled={!onDecision || pendingDecisionId === key || decided}
                            onClick={() => openCorrection(key)}
                            className="rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            需改
                          </button>
                          <button
                            aria-label={`不写入 ${item.label} ${item.summary}`}
                            disabled={!onDecision || pendingDecisionId === key || decided}
                            onClick={() => decidePreviewItem(item, "reject")}
                            className="rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            不写入
                          </button>
                        </div>
                        {activeCorrectionKey === key &&
                          renderCorrectionEditor(
                            key,
                            { type: item.type, id: item.id },
                            item.label,
                            !onDecision || pendingDecisionId === key || decided,
                          )}
                      </div>
                    )
                  })}
                </div>
              ) : null}
              {decisionError && (
                <p className="mt-2 text-[11px] leading-snug text-destructive">
                  {decisionError}
                </p>
              )}
            </div>
          </div>
        </div>
      ) : !demoMode ? (
        <div className="flex flex-col items-center gap-1.5 px-3.5 py-7 text-center">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <BookmarkPlus className="h-4 w-4" strokeWidth={1.75} />
          </span>
          <p className="text-[13px] font-medium text-foreground">等待后端回写状态</p>
          <p className="max-w-[260px] text-[11px] leading-snug text-muted-foreground">
            采纳候选后，这里会显示 SourceDelta、证据段落、事实和复核项的真实回写预览。
          </p>
        </div>
      ) : done ? (
        <div className="flex flex-col items-center gap-1.5 px-3.5 py-7 text-center">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-success/12 text-success">
            <Check className="h-4 w-4" strokeWidth={2} />
          </span>
          <p className="text-[13px] font-medium text-foreground">都处理好了</p>
          <p className="text-[11px] text-muted-foreground">继续写就好，Sextant 会帮你记着。</p>
        </div>
      ) : (
        <div className="max-h-[360px] divide-y divide-border overflow-y-auto">
          {items.map((item) => (
            <div key={item.id} className="px-3.5 py-2.5">
              <div className="flex items-start gap-2">
                <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${dot[item.level]}`} />
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] leading-snug text-foreground">{item.text}</p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">{item.kindLabel}</p>

                  {item.evidence && (
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      证据：<span className="text-foreground/70">{item.evidence}</span>
                    </p>
                  )}
                  {item.status && (
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      状态：<span className="text-foreground/70">{item.status}</span>
                    </p>
                  )}
                  {item.risk && (
                    <p className="mt-1 flex items-start gap-1 text-[11px] text-[color:var(--warning)]">
                      <AlertTriangle className="mt-px h-3 w-3 shrink-0" strokeWidth={1.75} />
                      {item.risk}
                    </p>
                  )}

                  {/* 操作 */}
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {item.actions.map((a) => (
                      <button
                        key={a.label}
                        onClick={() => resolveItem(item.id, a.label.includes("撤销"))}
                        className={
                          a.primary
                            ? "rounded-md bg-secondary px-2 py-0.5 text-[11.5px] font-medium text-secondary-foreground transition-colors hover:bg-accent"
                            : "rounded-md px-1.5 py-0.5 text-[11.5px] text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline"
                        }
                      >
                        {a.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 底部说明 */}
      <div className="border-t border-border bg-muted/40 px-3.5 py-2 text-[11px] text-muted-foreground">
        {acceptance
          ? "真实回写预览 · 不把候选解释当证据。"
          : demoMode
            ? "低风险已记住，可撤销 · 有风险的会进入复核，不打断你写作。"
            : "等待真实回写预览 · 不显示 demo 记忆项。"}
      </div>
    </div>
  )
}

function factId(fact: Record<string, unknown>): string {
  const id = fact.fact_id ?? fact.id
  return typeof id === "string" ? id : ""
}

function factLabel(fact: Record<string, unknown>): string {
  const subject = formatRef(fact.subject_ref)
  const predicate = predicateLabel(fact.predicate)
  const object = formatRef(fact.object_ref)
  return [subject, predicate, object].filter(Boolean).join(" · ")
}

function previewItems(state: WorkbenchWritebackState): PreviewDecisionItem[] {
  return [
    ...state.preview.source_spans.map((item) => ({
      type: "source_span",
      id: stringField(item, "id"),
      label: typeLabel("source_span"),
      summary: stringField(item, "text_preview") || stringField(item, "id"),
    })),
    ...state.preview.review_items.map((item) => ({
      type: "review_item",
      id: item.id,
      label: typeLabel("review_item"),
      summary: item.summary,
    })),
    ...state.preview.memory_pages.map((item) => ({
      type: "memory_page",
      id: stringField(item, "id"),
      label: typeLabel("memory_page"),
      summary: humanizeIdentifier(stringField(item, "title") || stringField(item, "id")),
    })),
    ...state.preview.graph_edges.map((item) => ({
      type: "graph_edge",
      id: stringField(item, "id"),
      label: typeLabel("graph_edge"),
      summary: predicateLabel(stringField(item, "relation") || stringField(item, "id")),
    })),
  ].filter((item) => item.id)
}

function previewIsEmpty(state: WorkbenchWritebackState): boolean {
  return (
    state.preview.source_spans.length === 0 &&
    state.preview.fact_assertions.length === 0 &&
    state.preview.review_items.length === 0 &&
    state.preview.memory_pages.length === 0 &&
    state.preview.graph_edges.length === 0
  )
}

function previewCountLabel(state: WorkbenchWritebackState, count: number): string {
  if (count > 0) return String(count)
  if (state.job.status === "succeeded" || state.job.status === "completed") return "无"
  return "整理中"
}

function stringField(item: Record<string, unknown>, key: string): string {
  const value = item[key]
  return typeof value === "string" ? value : ""
}

function parseReplacementRefs(value: string): Record<string, unknown>[] {
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
      return { type: "source_delta", id: token }
    })
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return "写回决定保存失败。"
}
