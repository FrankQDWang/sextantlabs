"use client"

import { useEffect } from "react"
import { BookOpen, CheckCircle2, CircleSlash, GitBranch, RefreshCw, X } from "lucide-react"
import type {
  GraphProjectionEdgeListResponse,
  MemoryPageDetailResponse,
  MemoryPageListResponse,
} from "@/src/generated/sextant-api"
import {
  formatRef,
  formatRefToken,
  humanizeIdentifier,
  predicateLabel,
  shortId,
  statusLabel,
  typeLabel,
} from "@/lib/workbench-display"

interface MemoryPagePanelProps {
  pages: MemoryPageListResponse["items"]
  detail: MemoryPageDetailResponse | null
  graphEdges: GraphProjectionEdgeListResponse["items"]
  loading: boolean
  error: string | null
  detailLoading: boolean
  detailError: string | null
  graphEdgesLoading: boolean
  graphEdgesError: string | null
  graphEdgeSearch: string
  graphEdgeStatus: string
  onSelect: (id: string) => void
  onRefresh: () => void
  onGraphEdgeSearchChange: (query: string) => void
  onGraphEdgeStatusChange: (status: string) => void
  onOperateThread?: (
    threadId: string,
    updateType: "pays_off" | "closes",
    summary: string | null,
  ) => void
  operatingThreadId?: string | null
  operationError?: string | null
  onClose: () => void
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function MemoryPagePanel({
  pages,
  detail,
  graphEdges,
  loading,
  error,
  detailLoading,
  detailError,
  graphEdgesLoading,
  graphEdgesError,
  graphEdgeSearch,
  graphEdgeStatus,
  onSelect,
  onRefresh,
  onGraphEdgeSearchChange,
  onGraphEdgeStatusChange,
  onOperateThread,
  operatingThreadId,
  operationError,
  onClose,
}: MemoryPagePanelProps) {
  const visibleGraphEdges = uniqueGraphEdges(graphEdges)
  const firstPageId = pages[0]?.id ?? null

  useEffect(() => {
    if (!firstPageId || detail || detailLoading || detailError) {
      return
    }
    onSelect(firstPageId)
  }, [detail, detailError, detailLoading, firstPageId, onSelect])

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <aside className="fixed right-3 top-14 z-50 max-h-[calc(100vh-72px)] w-[380px] overflow-hidden rounded-xl border border-border bg-popover shadow-xl shadow-foreground/10">
        <div className="flex items-center justify-between border-b border-border px-3.5 py-2.5">
          <div className="flex items-center gap-2">
            <BookOpen className="h-3.5 w-3.5 text-primary" strokeWidth={1.75} />
            <h2 className="text-[12.5px] font-medium text-foreground">记忆页详情</h2>
          </div>
          <div className="flex items-center gap-1">
            <button
              aria-label="刷新记忆页"
              onClick={onRefresh}
              className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.75} />
            </button>
            <button
              aria-label="关闭记忆页"
              onClick={onClose}
              className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" strokeWidth={1.75} />
            </button>
          </div>
        </div>

        <div className="max-h-[calc(100vh-124px)] space-y-3 overflow-y-auto px-3.5 py-3 text-[12px]">
          {loading ? (
            <p className="rounded-md border border-border bg-muted/30 px-2.5 py-2 text-muted-foreground">
              正在读取记忆页…
            </p>
          ) : error ? (
            <p className="rounded-md border border-destructive/30 bg-destructive/8 px-2.5 py-2 text-destructive">
              {error}
            </p>
          ) : pages.length > 0 ? (
            <section data-testid="memory-page-list" className="space-y-1.5">
              {pages.map((page) => (
                <button
                  key={page.id}
                  type="button"
                  onClick={() => onSelect(page.id)}
                  className="w-full rounded-md border border-border bg-card px-2.5 py-2 text-left transition-colors hover:border-primary/40"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="min-w-0 truncate text-[12px] font-medium text-foreground">
                      {humanizeIdentifier(page.title)}
                    </p>
                    <span className="shrink-0 rounded border border-border bg-muted px-1.5 py-0.5 text-[10.5px] text-muted-foreground">
                      {statusLabel(page.canon_status)}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    {typeLabel(page.page_type)} · {memoryDepthLabel(page.memory_depth)} · 证据{" "}
                    {sourceRefCount(page.source_refs)}
                    {" · "}线索 {page.open_thread_count}
                    {page.contradiction_count > 0 ? ` · 冲突 ${page.contradiction_count}` : ""}
                  </p>
                </button>
              ))}
            </section>
          ) : (
            <p className="rounded-md border border-border bg-muted/30 px-2.5 py-2 text-muted-foreground">
              暂无记忆页
            </p>
          )}

          <section
            data-testid="graph-projection-inspector"
            className="rounded-md border border-border bg-muted/30 px-3 py-2"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5">
                <GitBranch className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  关系图谱
                </p>
              </div>
              {graphEdgesLoading && (
                <span className="text-[11px] text-muted-foreground">读取中…</span>
              )}
            </div>
            <div className="mt-2 grid grid-cols-[1fr_auto] gap-1.5">
              <input
                aria-label="搜索关系图谱"
                value={graphEdgeSearch}
                onChange={(event) => onGraphEdgeSearchChange(event.target.value)}
                className="h-7 min-w-0 rounded-md border border-border bg-card px-2 text-[12px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
              />
              <select
                aria-label="关系状态"
                value={graphEdgeStatus}
                onChange={(event) => onGraphEdgeStatusChange(event.target.value)}
                className="h-7 w-[90px] rounded-md border border-border bg-card px-1.5 text-[11px] text-foreground outline-none focus:border-primary/50"
              >
                <option value="">全部状态</option>
                <option value="canon">已确认</option>
                <option value="proposed">候选</option>
                <option value="inferred">推断</option>
                <option value="disputed">待复核</option>
                <option value="contradicted">已冲突</option>
                <option value="outdated">已过期</option>
              </select>
            </div>
            {graphEdgesError ? (
              <p className="mt-2 rounded-md border border-destructive/30 bg-destructive/8 px-2.5 py-2 text-destructive">
                {graphEdgesError}
              </p>
            ) : visibleGraphEdges.length > 0 ? (
              <div className="mt-2 max-h-48 space-y-1.5 overflow-y-auto pr-1">
                {visibleGraphEdges.map((edge) => (
                  <article
                    key={edge.id}
                    className="rounded-md border border-border bg-card px-2.5 py-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="min-w-0 truncate text-[12px] font-medium text-foreground">
                        {formatGraphRef(edge.subject_ref)}
                      </p>
                      <span className="shrink-0 rounded border border-border bg-muted px-1.5 py-0.5 text-[10.5px] text-muted-foreground">
                        {statusLabel(edge.edge_status)}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      {predicateLabel(edge.relation)} → {formatGraphRef(edge.target_ref)}
                    </p>
                    <p className="mt-1 truncate text-[10.5px] text-muted-foreground/80">
                      证据段落 {graphEvidenceCount(edge.evidence_refs)} · 来源已记录
                    </p>
                  </article>
                ))}
              </div>
            ) : (
              <p className="mt-2 rounded-md border border-border bg-card px-2.5 py-2 text-muted-foreground">
                暂无关系图谱边
              </p>
            )}
          </section>

          <section data-testid="memory-page-detail" className="rounded-md border border-border bg-muted/30 px-3 py-2">
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
              记忆页详情
            </p>
            {detailLoading ? (
              <p className="mt-2 text-muted-foreground">正在读取详情…</p>
            ) : detailError ? (
              <p className="mt-2 text-destructive">{detailError}</p>
            ) : detail ? (
              <div className="mt-2 space-y-2">
                <div>
                  <p className="font-medium text-foreground">{humanizeIdentifier(detail.title)}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {typeLabel(detail.page_type)} · {statusLabel(detail.canon_status)} ·{" "}
                    {memoryDepthLabel(detail.memory_depth)}
                  </p>
                </div>
                <DetailBlock label="已确认设定" value={detail.current_canon} />
                {detail.knowledge_state.length > 0 && (
                  <DetailBlock label="角色认知" value={detail.knowledge_state} />
                )}
                {detail.open_threads.length > 0 && (
                  <OpenThreadBlock
                    threads={detail.open_threads}
                    onOperateThread={onOperateThread}
                    operatingThreadId={operatingThreadId}
                    operationError={operationError}
                  />
                )}
                {detail.contradictions.length > 0 && (
                  <DetailBlock label="冲突" value={detail.contradictions} />
                )}
                <div className="rounded border border-border bg-card px-2 py-1.5">
                  <p className="text-[10.5px] uppercase tracking-wide text-muted-foreground">
                    证据引用
                  </p>
                  <p className="mt-1 text-[10.5px] leading-relaxed text-foreground/80">
                    {detail.source_refs.map(refLabel).join(" · ") || "无"}
                  </p>
                </div>
              </div>
            ) : (
              <p className="mt-2 text-muted-foreground">
                {pages.length > 0 ? "正在打开第一条记忆页详情…" : "选择一页查看证据引用。"}
              </p>
            )}
          </section>
        </div>
      </aside>
    </>
  )
}

function OpenThreadBlock({
  threads,
  onOperateThread,
  operatingThreadId,
  operationError,
}: {
  threads: Record<string, unknown>[]
  onOperateThread?: (
    threadId: string,
    updateType: "pays_off" | "closes",
    summary: string | null,
  ) => void
  operatingThreadId?: string | null
  operationError?: string | null
}) {
  return (
    <div className="rounded border border-border bg-card px-2 py-1.5">
      <p className="text-[10.5px] uppercase tracking-wide text-muted-foreground">待处理线索</p>
      {operationError && (
        <p className="mt-1 rounded border border-destructive/30 bg-destructive/8 px-1.5 py-1 text-[10.5px] leading-snug text-destructive">
          {operationError}
        </p>
      )}
      <ul className="mt-1 max-h-40 space-y-1.5 overflow-auto text-[11px] leading-relaxed text-foreground/80">
        {threads.map((thread, index) => {
          const threadId = stringField(thread.id) || `thread-${index + 1}`
          const rawSummary = openThreadRawSummary(thread)
          const summary = openThreadSummary(thread)
          const canOperate = Boolean(onOperateThread) && openThreadCanOperate(thread)
          const busy = operatingThreadId === threadId
          return (
            <li key={`${threadId}-${index}`} className="rounded border border-border/70 bg-muted/20 p-1.5">
              <div className="flex gap-1.5">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-current opacity-40" />
                <span className="min-w-0 flex-1">{summary}</span>
              </div>
              {canOperate && (
                <div className="mt-1 flex justify-end gap-1">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => onOperateThread?.(threadId, "pays_off", rawSummary)}
                    className="inline-flex h-6 items-center gap-1 rounded border border-border bg-card px-1.5 text-[10.5px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <CheckCircle2 className="h-3 w-3" strokeWidth={1.75} />
                    回收
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => onOperateThread?.(threadId, "closes", rawSummary)}
                    className="inline-flex h-6 items-center gap-1 rounded border border-border bg-card px-1.5 text-[10.5px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <CircleSlash className="h-3 w-3" strokeWidth={1.75} />
                    关闭
                  </button>
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function DetailBlock({ label, value }: { label: string; value: unknown }) {
  const lines = detailLines(label, value)
  return (
    <div className="rounded border border-border bg-card px-2 py-1.5">
      <p className="text-[10.5px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <ul className="mt-1 max-h-28 space-y-1 overflow-auto text-[11px] leading-relaxed text-foreground/80">
        {lines.map((line, index) => (
          <li key={`${line}-${index}`} className="flex gap-1.5">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-current opacity-40" />
            <span>{line}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function openThreadCanOperate(thread: Record<string, unknown>): boolean {
  const status = stringField(thread.status) || stringField(thread.thread_status)
  return !["closed", "resolved", "dismissed", "obsolete", "superseded"].includes(status)
}

function openThreadSummary(thread: Record<string, unknown>): string {
  return [
    openThreadRawSummary(thread),
    threadStatusLabel(stringField(thread.status) || stringField(thread.thread_status)),
    stringField(thread.risk_level) ? `风险 ${stringField(thread.risk_level)}` : "",
  ].filter(Boolean).join(" · ")
}

function openThreadRawSummary(thread: Record<string, unknown>): string {
  return stringField(thread.summary) || stringField(thread.description) || "未命名线索"
}

function threadStatusLabel(status: string): string {
  if (status === "open") return "开放"
  if (status === "resolved") return "已回收"
  if (status === "closed") return "已关闭"
  return status ? statusLabel(status) : ""
}

function detailLines(label: string, value: unknown): string[] {
  if (label === "角色认知" && Array.isArray(value)) {
    const lines = value.map(knowledgeStateLine).filter(Boolean)
    return lines.length > 0 ? lines : ["无"]
  }
  if (isRecord(value)) {
    const facts = Array.isArray(value.facts) ? value.facts.filter(isRecord) : []
    if (facts.length > 0) {
      return facts.map((fact) => `设定 · ${factLine(fact)}`)
    }
    return [recordLine(value, label)]
  }
  if (Array.isArray(value)) {
    const lines = value.map((item) => recordLine(item, label)).filter(Boolean)
    return lines.length > 0 ? lines : ["无"]
  }
  const primitive = primitiveLine(value)
  return primitive ? [primitive] : ["无"]
}

function knowledgeStateLine(value: unknown): string {
  if (!isRecord(value)) {
    return primitiveLine(value)
  }
  const target = refValue(value.knows_ref) ?? "已记录认知"
  const certainty = knowledgeCertaintyLabel(value.certainty)
  const learnedIn = learnedInSceneLabel(value.learned_in_scene_id)
  const hiddenCount = Array.isArray(value.hidden_from) ? value.hidden_from.length : 0
  return [
    target,
    certainty,
    learnedIn,
    hiddenCount > 0 ? `对 ${hiddenCount} 个视角隐藏` : "",
  ].filter(Boolean).join(" · ")
}

function factLine(fact: Record<string, unknown>): string {
  const predicate = predicateLabel(fact.predicate)
  const target = refValue(fact.object_ref) ?? refValue(fact.object) ?? refValue(fact.target_ref)
  return [predicate, target].filter(Boolean).join(" · ")
}

function recordLine(value: unknown, label: string): string {
  if (!isRecord(value)) {
    return primitiveLine(value)
  }
  const memoryLine = memoryRecordLine(value)
  if (memoryLine) {
    return memoryLine
  }
  const summary =
    stringRefField(value.summary) ??
    stringRefField(value.title) ??
    stringRefField(value.thread) ??
    stringRefField(value.author_note) ??
    stringRefField(value.note)
  if (summary) {
    return summary
  }
  if (stringRefField(value.predicate)) {
    return factLine(value)
  }
  const ref = refValue(value)
  if (ref) {
    return ref
  }
  return `${label} · 已记录`
}

function stringField(value: unknown): string {
  return typeof value === "string" ? value.trim() : ""
}

function memoryRecordLine(value: Record<string, unknown>): string {
  const type = stringRefField(value.type)
  if (type === "review_item_resolution") {
    return [
      "复核处理",
      statusLabel(value.resolution),
      requirementLabel(value.requires),
      stringRefField(value.author_note),
    ].filter(Boolean).join(" · ")
  }
  if (type === "memory_writeback_decision") {
    return [
      "记忆回写处理",
      decisionLabel(value.decision),
      requirementLabel(value.requires),
      stringRefField(value.author_note),
    ].filter(Boolean).join(" · ")
  }
  return ""
}

function primitiveLine(value: unknown): string {
  if (typeof value === "string") {
    if (UUID_PATTERN.test(value.trim())) {
      return "已记录"
    }
    return humanizeIdentifier(shortId(value))
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value)
  }
  return ""
}

function refValue(value: unknown): string | null {
  if (isRecord(value)) {
    return formatGraphRef(value)
  }
  if (typeof value === "string" && value.trim()) {
    if (UUID_PATTERN.test(value.trim())) {
      return "已记录"
    }
    return humanizeIdentifier(shortId(value))
  }
  return null
}

function sourceRefCount(refs: Record<string, unknown>[]): number {
  return refs.filter((ref) => ref.type === "source_span").length
}

function refLabel(ref: Record<string, unknown>, index: number): string {
  if (ref.type === "source_span") {
    return `证据段落 ${index + 1}`
  }
  if (ref.type === "scene") {
    return formatRef(ref)
  }
  return formatRefToken(ref)
}

function formatGraphRef(ref: Record<string, unknown>): string {
  return formatRef(ref)
}

function stringRefField(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function graphEvidenceCount(refs: Record<string, unknown>[]): number {
  return refs.filter((ref) => ref.type === "source_span").length
}

function uniqueGraphEdges(
  edges: GraphProjectionEdgeListResponse["items"],
): GraphProjectionEdgeListResponse["items"] {
  const seen = new Set<string>()
  return edges.filter((edge) => {
    const key = [
      JSON.stringify(edge.subject_ref),
      edge.relation,
      JSON.stringify(edge.target_ref),
      edge.edge_status,
    ].join("|")
    if (seen.has(key)) {
      return false
    }
    seen.add(key)
    return true
  })
}

function memoryDepthLabel(depth: unknown): string {
  if (depth === "standard") return "标准"
  if (depth === "deep") return "深入"
  if (depth === "shallow") return "简要"
  if (depth === "scene") return "场景"
  if (depth === "chapter") return "章节"
  if (depth === "project") return "项目"
  return statusLabel(depth)
}

function decisionLabel(decision: unknown): string {
  if (decision === "accept") return "确认"
  if (decision === "reject") return "不写入"
  if (decision === "correct") return "作者修正"
  return statusLabel(decision)
}

function requirementLabel(requirement: unknown): string {
  if (requirement === "new_source_delta_or_memory_rewrite") return "需要新正文变更或重写记忆页"
  if (requirement === "memory_page_rewrite") return "需要重写记忆页"
  return typeof requirement === "string" && requirement.trim()
    ? humanizeIdentifier(requirement)
    : ""
}

function knowledgeCertaintyLabel(certainty: unknown): string {
  if (certainty === "known") return "已知"
  if (certainty === "suspected") return "怀疑"
  if (certainty === "false_belief") return "错误认知"
  if (certainty === "misunderstands") return "误解"
  if (certainty === "does_not_know") return "不知道"
  return statusLabel(certainty)
}

function learnedInSceneLabel(value: unknown): string {
  if (typeof value === "string" && value.trim()) {
    return UUID_PATTERN.test(value.trim()) ? "相关场景后" : `${humanizeIdentifier(shortId(value))} 后`
  }
  if (isRecord(value)) {
    return `${formatGraphRef(value)} 后`
  }
  return ""
}
