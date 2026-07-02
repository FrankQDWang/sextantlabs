"use client"

import { useEffect, useState } from "react"
import { candidates as demoCandidates, type Candidate, type RiskLevel } from "@/lib/workbench-data"
import {
  Plus,
  Replace,
  FileSearch,
  ChevronDown,
  RefreshCw,
  Sparkles,
  ShieldAlert,
} from "lucide-react"
import type { CandidateDetailResponse, WritingContextPackResponse } from "@/src/generated/sextant-api"
import { humanizeIdentifier, statusLabel } from "@/lib/workbench-display"

interface CandidateDrawerProps {
  onClose: () => void
  onAcceptSentence: (text: string) => void
  onRejectCandidate?: () => void
  onReviseSentence?: (text: string) => void
  candidates?: Candidate[]
  loading?: boolean
  error?: string | null
  operationPending?: boolean
  operationStatus?: string | null
  operationError?: string | null
  acceptDisabled?: boolean
  acceptDisabledReason?: string
  contextPack?: WritingContextPackResponse | null
  contextLoading?: boolean
  contextError?: string | null
  onShowContext?: () => void
  candidateExplanation?: CandidateDetailResponse | null
  explanationLoading?: boolean
  explanationError?: string | null
  onExplainCandidate?: () => void
  canOverrideCandidate?: boolean
  onOverrideCandidate?: (reason: string) => void
  staleSourceMessage?: string | null
  sourceRefreshPending?: boolean
  onRefreshSource?: () => void
}

const riskStyle: Record<RiskLevel, { dot: string; text: string; label: string }> = {
  low: { dot: "bg-success", text: "text-success", label: "低风险" },
  medium: { dot: "bg-[color:var(--warning)]", text: "text-[color:var(--warning)]", label: "中风险" },
  high: { dot: "bg-destructive", text: "text-destructive", label: "高风险" },
}

export function CandidateDrawer({
  onClose,
  onAcceptSentence,
  onRejectCandidate,
  onReviseSentence,
  candidates = demoCandidates,
  loading = false,
  error = null,
  operationPending = false,
  operationStatus = null,
  operationError = null,
  acceptDisabled = false,
  acceptDisabledReason = "这个候选暂时不能采纳",
  contextPack = null,
  contextLoading = false,
  contextError = null,
  onShowContext,
  candidateExplanation = null,
  explanationLoading = false,
  explanationError = null,
  onExplainCandidate,
  canOverrideCandidate = false,
  onOverrideCandidate,
  staleSourceMessage = null,
  sourceRefreshPending = false,
  onRefreshSource,
}: CandidateDrawerProps) {
  const [activeId, setActiveId] = useState(candidates[0]?.id ?? "")
  const [selectedSentence, setSelectedSentence] = useState<string | null>(null)
  const [overrideReason, setOverrideReason] = useState("")
  const active = candidates.find((c) => c.id === activeId) ?? candidates[0]
  const selectedSentenceText =
    active?.sentences.find((sentence) => sentence.id === selectedSentence)?.text ?? null
  const staleSourceBlocked = Boolean(staleSourceMessage)
  const candidateRejected = Boolean(operationStatus?.includes("候选已退回"))

  useEffect(() => {
    if (candidates[0] && !candidates.some((candidate) => candidate.id === activeId)) {
      setActiveId(candidates[0].id)
      setSelectedSentence(null)
      setOverrideReason("")
    }
  }, [activeId, candidates])

  return (
    <div
      className="animate-slide-up relative z-[60] shrink-0 border-t border-border bg-card"
      data-testid="candidate-drawer"
    >
      {/* 抽屉头 */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-primary" strokeWidth={1.75} />
          <span className="text-[12px] font-medium text-foreground">候选续写</span>
          <span className="text-[11px] text-muted-foreground">
            · {loading ? "正在生成候选" : "选一句加入，或借方向重写"}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {/* tabs */}
          <div className="mr-2 flex items-center gap-0.5 rounded-md bg-muted p-0.5">
            {candidates.map((c) => (
              <button
                key={c.id}
                onClick={() => {
                  setActiveId(c.id)
                  setSelectedSentence(null)
                }}
                className={`flex items-center gap-1.5 rounded px-2 py-1 text-[12px] transition-colors ${
                  activeId === c.id
                    ? "bg-card font-medium text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {candidateTabLabel(c.label)}
                {c.risk && (
                  <span className={`h-1.5 w-1.5 rounded-full ${riskStyle[c.risk.level].dot}`} />
                )}
              </button>
            ))}
          </div>
          <button
            onClick={onClose}
            className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            aria-label="收起候选"
          >
            <ChevronDown className="h-4 w-4" strokeWidth={1.75} />
          </button>
        </div>
      </div>

      {/* 内容区 */}
      <div className="mx-auto flex max-w-[900px] gap-5 px-4 py-3">
        {/* 左：候选文本（逐句可选） */}
        <div className="min-w-0 flex-1">
          {loading && (
            <div className="rounded-md border border-border bg-muted/50 px-3 py-2 text-[12px] text-muted-foreground">
              正在生成候选，不会写入正文或记忆。
            </div>
          )}
          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/8 px-3 py-2 text-[12px] text-destructive">
              {error}
            </div>
          )}
          {staleSourceMessage && (
            <div
              data-testid="candidate-stale-source"
              className="mb-2 rounded-md border border-[color:var(--warning)]/40 bg-[color:var(--warning)]/10 px-3 py-2 text-[12px] text-foreground"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium text-[color:var(--warning)]">正文版本已更新</p>
                  <p className="mt-0.5 leading-snug text-muted-foreground">
                    {authorFacingSourceMessage(staleSourceMessage)}
                  </p>
                </div>
                <button
                  disabled={!onRefreshSource || sourceRefreshPending}
                  onClick={onRefreshSource}
                  className="flex shrink-0 items-center gap-1.5 rounded-md border border-border bg-card px-2 py-1 text-[11px] text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <RefreshCw className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
                  {sourceRefreshPending ? "刷新中" : "刷新正文"}
                </button>
              </div>
            </div>
          )}
          {!loading && !error && !active && (
            <div className="rounded-md border border-border bg-muted/50 px-3 py-2 text-[12px] text-muted-foreground">
              还没有可显示的候选。
            </div>
          )}
          {active && (
            <>
              <p className="mb-2 text-[11px] text-muted-foreground">
                方向：<span className="text-foreground/70">{candidateDirectionLabel(active.direction)}</span>
              </p>
              <p className="mb-2 text-[11px] text-muted-foreground">
                {selectedSentenceText
                  ? `将只采纳：${selectedSentenceText}`
                  : "选择一句后，只采纳这一句，不会写入整段候选。"}
              </p>
              <div className="space-y-1.5 font-serif text-[14.5px] leading-relaxed">
                {active.sentences.map((s) => {
                  const isSel = selectedSentence === s.id
                  return (
                    <div
                      key={s.id}
                      className={`group flex items-start gap-2 rounded-md border px-2.5 py-1.5 transition-colors ${
                        isSel
                          ? "border-primary/40 bg-primary/8"
                          : "border-transparent hover:border-border hover:bg-muted/60"
                      }`}
                    >
                      <button
                        onClick={() => setSelectedSentence(isSel ? null : s.id)}
                        className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors ${
                          isSel
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border text-transparent group-hover:border-muted-foreground"
                        }`}
                        aria-label="选这一句"
                      >
                        <Plus className="h-2.5 w-2.5" strokeWidth={2.5} />
                      </button>
                      <span className="text-foreground/90">{s.text}</span>
                    </div>
                  )
                })}
              </div>

          {/* 主动作行 — 句子级是主，全文采纳是次 */}
          <div className="mt-3 flex items-center gap-1.5">
            <button
              disabled={!selectedSentence || acceptDisabled || staleSourceBlocked || candidateRejected}
              onClick={() => {
                const s = active.sentences.find((x) => x.id === selectedSentence)
                if (s) onAcceptSentence(s.text)
              }}
              className="flex items-center gap-1.5 rounded-md bg-primary px-2.5 py-1.5 text-[12px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              title={
                staleSourceBlocked
                  ? "请先刷新正文并重新生成候选"
                  : acceptDisabled
                    ? acceptDisabledReason
                    : undefined
              }
            >
              <Plus className="h-3.5 w-3.5" strokeWidth={2} />
              {acceptDisabled ? "需先处理风险" : selectedSentence ? "只采纳所选句" : "选这句加入"}
            </button>
            <button
              disabled={!selectedSentence || !onReviseSentence || operationPending || candidateRejected}
              onClick={() => {
                const s = active.sentences.find((x) => x.id === selectedSentence)
                if (s && onReviseSentence) onReviseSentence(s.text)
              }}
              className="flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1.5 text-[12px] text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Replace className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
              保存为修订候选
            </button>
            <button
              disabled={!onShowContext}
              onClick={onShowContext}
              className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[12px] text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
            >
              <FileSearch className="h-3.5 w-3.5" strokeWidth={1.75} />
              查看依据
            </button>
            <button
              disabled={!onExplainCandidate}
              onClick={onExplainCandidate}
              className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[12px] text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
            >
              <FileSearch className="h-3.5 w-3.5" strokeWidth={1.75} />
              解释候选
            </button>
            {/* 次要动作：全文采纳 */}
            <button
              disabled={!onRejectCandidate || operationPending || candidateRejected}
              onClick={onRejectCandidate}
              className="ml-auto rounded px-2 py-1 text-[11px] text-muted-foreground/70 underline-offset-2 transition-colors hover:text-muted-foreground hover:underline disabled:cursor-not-allowed disabled:opacity-40"
            >
              {operationPending ? "处理中" : "退回候选"}
            </button>
          </div>
          {(operationStatus || operationError) && (
            <p
              className={`mt-2 text-[11px] ${
                operationError ? "text-destructive" : "text-muted-foreground"
              }`}
            >
              {operationError ?? operationStatus}
            </p>
          )}
            </>
          )}
        </div>

        {/* 右：依据 / 避开 / 风险 */}
        <div className="w-[260px] shrink-0 space-y-2.5 border-l border-border pl-5 text-[12px]">
          {active && (
            <>
          <div>
            <p className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">用到的记忆</p>
            <div className="flex flex-wrap gap-1">
              {active.usedMemory.map((m, index) => (
                <span
                  key={`${m}-${index}`}
                  className="rounded border border-success/30 bg-success/8 px-1.5 py-0.5 text-[11px] text-success"
                >
                  {memoryChipLabel(m)}
                </span>
              ))}
            </div>
          </div>
          <div>
            <p className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">避开了未证实</p>
            <div className="flex flex-wrap gap-1">
              {active.avoided.map((m, index) => (
                <span
                  key={`${m}-${index}`}
                  className="rounded border border-border bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground line-through decoration-muted-foreground/40"
                >
                  {authorFacingRiskNote(m)}
                </span>
              ))}
            </div>
          </div>
          {active.risk && (
            <div className="flex items-start gap-1.5 rounded-md border border-border bg-muted/60 px-2 py-1.5">
              <ShieldAlert
                className={`mt-px h-3.5 w-3.5 shrink-0 ${riskStyle[active.risk.level].text}`}
                strokeWidth={1.75}
              />
              <p className="leading-snug text-foreground/80">
                <span className={`font-medium ${riskStyle[active.risk.level].text}`}>
                  {riskStyle[active.risk.level].label}
                </span>
                {" · "}
                {authorFacingRiskNote(active.risk.note)}
              </p>
            </div>
          )}
          {(contextPack || contextLoading || contextError) && (
            <div className="rounded-md border border-border bg-muted/40 px-2 py-1.5">
              <p className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">
                上下文依据
              </p>
              {contextLoading ? (
                <p className="text-[11px] text-muted-foreground">读取上下文依据…</p>
              ) : contextError ? (
                <p className="text-[11px] text-destructive">{contextError}</p>
              ) : contextPack ? (
                <div className="space-y-1 text-[11px] text-muted-foreground">
                  <p>
                    {modeLabel(contextPack.current_position.mode)} · 证据{" "}
                    {contextPack.evidence_refs.length}
                  </p>
                  <p>
                    已确认 {contextPackCount(contextPack.canonical_context, "facts")} · 风险{" "}
                    {contextPackCount(contextPack.risk_context, "facts")} · 复核{" "}
                    {contextPackCount(contextPack.risk_context, "review_items")}
                  </p>
                </div>
              ) : null}
            </div>
          )}
          {(candidateExplanation || explanationLoading || explanationError) && (
            <div className="rounded-md border border-border bg-muted/40 px-2 py-1.5">
              <p className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">
                候选解释
              </p>
              {explanationLoading ? (
                <p className="text-[11px] text-muted-foreground">读取候选边界…</p>
              ) : explanationError ? (
                <p className="text-[11px] text-destructive">{explanationError}</p>
              ) : candidateExplanation ? (
                <div className="space-y-1 text-[11px] text-muted-foreground">
                  <p>
                    {statusLabel(candidateExplanation.status)} · {modeLabel(candidateExplanation.mode)}
                  </p>
                  {candidateExplanation.affected_range && (
                    <p>
                      范围 {candidateExplanation.affected_range.start}-
                      {candidateExplanation.affected_range.end}
                    </p>
                  )}
                  <p>
                    证据 {candidateExplanation.evidence_refs.length} · 风险复核{" "}
                    {candidateExplanation.agent_review_findings.length}
                  </p>
                  {candidateExplanation.override_reason && (
                    <p>覆盖说明 · {candidateExplanation.override_reason}</p>
                  )}
                  {candidateExplanation.agent_review_findings.map((finding) => (
                    <p key={finding.id}>
                      {riskLevelLabel(finding.risk_level)} · {riskTypeLabel(finding.risk_type)} ·{" "}
                      {authorFacingRiskNote(finding.summary)}
                    </p>
                  ))}
                </div>
              ) : null}
            </div>
          )}
          {canOverrideCandidate && onOverrideCandidate && (
            <div className="rounded-md border border-destructive/30 bg-destructive/8 px-2 py-1.5">
              <p className="mb-1 text-[11px] uppercase tracking-wide text-destructive">
                显式覆盖
              </p>
              <input
                aria-label="覆盖原因"
                value={overrideReason}
                onChange={(event) => setOverrideReason(event.target.value)}
                placeholder="写明保留风险候选的原因"
                className="h-7 w-full rounded-md border border-border bg-card px-2 text-[12px] text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
              />
              <button
                disabled={!overrideReason.trim() || operationPending}
                onClick={() => onOverrideCandidate(overrideReason.trim())}
                className="mt-1.5 rounded-md bg-destructive px-2 py-1 text-[11px] font-medium text-destructive-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                确认风险并允许采纳
              </button>
            </div>
          )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function contextPackCount(section: Record<string, unknown>, key: string): number {
  const value = section[key]
  return Array.isArray(value) ? value.length : 0
}

function authorFacingSourceMessage(message: string): string {
  return message
    .replaceAll("SourceVersion", "正文版本")
    .replaceAll("SourceDelta", "正文变更")
    .replaceAll("Memory", "记忆")
    .replaceAll("Canon", "已确认设定")
    .replaceAll("canon", "已确认设定")
    .replaceAll("正文版本 已", "正文版本已")
    .replaceAll("正文变更 或", "正文变更或")
    .replaceAll("正文或 记忆", "正文或记忆")
}

function candidateDirectionLabel(direction: string): string {
  if (direction === "revise_candidate") return "修订候选，保留证据边界"
  if (direction === "continue_small_passage") return "续写小段，保持当前视角"
  if (direction === "rewrite_span") return "改写选区，保留证据边界"
  return authorFacingRiskNote(direction)
}

function candidateTabLabel(label: string): string {
  if (label === "后端" || label.toLowerCase() === "backend") return "候选"
  return label
}

function authorFacingRiskNote(note: string): string {
  return note
    .replaceAll(
      "Draft presents risk-context material as if it were canon.",
      "候选把待确认风险写成了已确认设定。",
    )
    .replaceAll("risk-context", "待确认风险")
    .replaceAll("canon", "已确认设定")
    .replaceAll("Memory", "记忆")
    .replaceAll("Canon", "已确认设定")
}

function memoryChipLabel(value: string): string {
  const separator = value.indexOf(":")
  if (separator <= 0 || separator === value.length - 1) {
    return humanizeIdentifier(value)
  }
  const type = value.slice(0, separator)
  if (type === "source_span") return "证据段落"
  if (type === "review_item") return "复核线索"
  if (type === "fact_assertion") return "事实依据"
  return humanizeIdentifier(value.replace(/_/g, " "))
}

function modeLabel(mode: unknown): string {
  if (typeof mode !== "string" || !mode.trim()) return "未知模式"
  if (mode === "continue_small_passage") return "续写小段"
  if (mode === "rewrite_selection") return "改写选区"
  if (mode === "revise_candidate") return "修订候选"
  return humanizeIdentifier(mode.replace(/_/g, " "))
}

function riskLevelLabel(level: string): string {
  if (level === "high") return "高风险"
  if (level === "medium") return "中风险"
  if (level === "low") return "低风险"
  return statusLabel(level)
}

function riskTypeLabel(type: string): string {
  if (type === "canon_risk") return "设定风险"
  if (type === "pov_leak") return "视角越界"
  if (type === "unsupported_fact") return "缺少证据"
  return humanizeIdentifier(type.replace(/_/g, " "))
}
