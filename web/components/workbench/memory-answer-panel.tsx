"use client"

import { FileSearch, X } from "lucide-react"
import type { MemoryAnswerResponse } from "@/src/generated/sextant-api"
import { formatRef, statusLabel } from "@/lib/workbench-display"

interface MemoryAnswerPanelProps {
  answer: MemoryAnswerResponse | null
  loading: boolean
  error: string | null
  onClose: () => void
}

export function MemoryAnswerPanel({
  answer,
  loading,
  error,
  onClose,
}: MemoryAnswerPanelProps) {
  return (
    <div className="fixed left-1/2 top-[64px] z-50 w-[440px] -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-popover shadow-xl shadow-foreground/10">
      <div className="flex items-center justify-between border-b border-border px-3.5 py-2.5">
        <div className="flex items-center gap-2">
          <FileSearch className="h-3.5 w-3.5 text-primary" strokeWidth={1.75} />
          <p className="text-[12px] font-medium text-foreground">Sextant 回答</p>
        </div>
        <button
          aria-label="关闭回答"
          onClick={onClose}
          className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.75} />
        </button>
      </div>
      <div className="space-y-2 px-3.5 py-3 text-[12px]">
        {loading ? (
          <p className="text-muted-foreground">正在查可追溯证据…</p>
        ) : error ? (
          <p className="text-destructive">{error}</p>
        ) : answer ? (
          <>
            <div className="flex items-center justify-between gap-3">
              <p className="min-w-0 truncate text-foreground">{answer.question}</p>
              <span className="shrink-0 rounded border border-border bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                {answerTypeLabel(answer.answer_type)}
              </span>
            </div>
            <p className="leading-relaxed text-foreground/80">{answerText(answer)}</p>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
              <span>置信度 {confidenceLabel(answer.confidence)}</span>
              <span>证据段落 {answer.source_span_refs.length}</span>
              <span>复核 {answer.related_review_items.length}</span>
              <span>{answer.safe_to_use_in_current_pov ? "POV 可用" : "POV 不可直接用"}</span>
            </div>
            {answer.affected_entities.length > 0 ? (
              <p className="truncate text-[11px] text-muted-foreground">
                关联 {answer.affected_entities.map(formatRef).join("、")}
              </p>
            ) : null}
            {answer.caveats.length > 0 ? (
              <p className="leading-relaxed text-[11px] text-amber-700 dark:text-amber-300">
                注意 {answer.caveats.map(caveatLabel).join("；")}
              </p>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  )
}

function answerTypeLabel(answerType: string): string {
  if (answerType === "unknown") return "未找到证据"
  if (answerType === "canon") return "可用记忆"
  if (answerType === "open_thread") return "开放伏笔"
  if (answerType === "conflict") return "需要复核"
  return statusLabel(answerType)
}

function answerText(answer: MemoryAnswerResponse): string {
  if (answer.answer === "No SourceSpan-backed memory evidence matches this question.") {
    return "没有找到可追溯到原文片段的记忆证据。"
  }
  if (answer.answer === "No structured evidence target was provided.") {
    return "需要先指明要追问的角色、物件或事实关系。"
  }
  return answer.answer
}

function confidenceLabel(confidence: number): string {
  const bounded = Math.max(0, Math.min(1, confidence))
  return `${Math.round(bounded * 100)}%`
}

function caveatLabel(caveat: string): string {
  if (caveat === "structured_subject_or_predicate_required") return "需要明确追问对象或关系"
  if (caveat === "no_matching_evidence") return "没有匹配的证据段落"
  if (caveat === "non_canon_evidence") return "包含未确认或有争议的证据"
  if (caveat === "open_review_item") return "仍有关联复核项待处理"
  if (caveat === "not_safe_for_current_pov") return "当前视角下不可直接使用"
  if (caveat === "suspected_knowledge") return "角色只是怀疑，还不是确认认知"
  if (caveat === "false_belief_knowledge") return "角色当前持有错误认知"
  if (caveat === "misunderstood_knowledge") return "角色当前存在误解"
  if (caveat === "explicit_unknown_knowledge") return "文本明确说明角色不知道"
  if (caveat === "timeline_order_from_scene_position") return "时间顺序来自章节/场景位置"
  if (caveat === "event_overlap_from_scene_or_story_time") return "同场景或同故事时间内发生"
  if (caveat === "scene_local_alias_context") return "局部别名按证据场景缩窄"
  if (caveat === "relationship_explained_by_canonical_event") return "关系解释来自事件证据"
  if (caveat === "relationship_timeline_from_scene_position") {
    return "关系演变顺序来自章节/场景位置"
  }
  if (caveat === "relationship_path_from_fact_evidence") return "关系路径来自事实证据"
  if (caveat === "relationship_fact_without_event_explanation") return "只有关系事实，缺少事件解释"
  if (caveat === "memory_page_open_thread") return "来自 MemoryPage 的开放伏笔"
  if (caveat === "source_mention_lookup") return "来自原文 Mention 的首次出场定位"
  if (caveat === "ambiguous_entity_match") return "命中多个可能实体，需要先澄清"
  if (caveat === "semantic_clarification_needed") return "语义命中多个证据目标，需要先澄清"
  if (caveat === "continuity_review_item") return "存在连续性复核项"
  if (caveat === "high_severity_review") return "高风险复核"
  if (caveat === "medium_severity_review") return "中风险复核"
  if (caveat === "low_severity_review") return "低风险复核"
  if (caveat === "multiple_continuity_reviews") return "存在多条连续性复核"
  if (caveat === "replay-seeded") return "来自幂等回放记录"
  return statusLabel(caveat)
}
