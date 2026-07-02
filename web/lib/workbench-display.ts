const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const TYPE_LABELS: Record<string, string> = {
  accepted_fragment: "采纳片段",
  alias_record: "别名记录",
  canon_promotion: "设定确认",
  canonical_entity: "实体",
  character: "角色",
  draft_manuscript: "正文草稿",
  evidence_log_entry: "证据记录",
  event: "事件",
  fact_assertion: "事实",
  graph_edge: "关系边",
  location: "地点",
  memory_page: "记忆页",
  object: "物件",
  review_item: "复核项",
  scene: "场景",
  secret: "秘密",
  source_delta: "正文变更",
  source_span: "证据段落",
  source_version: "正文版本",
}

const STATUS_LABELS: Record<string, string> = {
  accepted_as_change: "按正文变更接受",
  active: "有效",
  archived: "已归档",
  applied: "已应用",
  ask_author: "询问作者",
  author_corrected: "作者已修正",
  canon: "已确认",
  completed: "完成",
  contradicted: "已冲突",
  current: "当前",
  dismissed: "暂不处理",
  disputed: "待复核",
  failed: "失败",
  fixed_by_text_edit: "已由正文修正",
  inferred: "推断",
  mark_intentional: "标为有意保留",
  marked_stale: "已标为需重写",
  memory_writeback_completed: "回写完成",
  memory_writeback_queued: "等待回写",
  merge: "合并处理",
  none: "无变更",
  normalized: "已规范化",
  open: "待处理",
  offered_to_author: "等待作者选择",
  outdated: "已过期",
  outdated_rebuild_queued: "已排队重建",
  proposed: "候选",
  queued: "排队中",
  rebuild_queued: "已排队重建",
  rejected_stale_base: "版本已过期",
  rebuilt: "已重建",
  revoked: "已撤销",
  resolved: "已处理",
  span_extracted: "证据已抽取",
  split: "拆分处理",
  stale: "需重写",
  submitted: "已提交",
  succeeded: "完成",
  supersede: "由新证据替代",
  stale_rewrite_queued: "已排队重写",
  unchanged: "无变更",
  unchanged_pending_rewrite: "等待记忆页重写",
  unknown: "未知",
}

const DELTA_KIND_LABELS: Record<string, string> = {
  delete: "删除",
  insert: "插入",
  replace: "替换",
}

const PREDICATE_LABELS: Record<string, string> = {
  appears_in: "出现于",
  associated_with: "关联",
  guards: "守护",
  knows: "知道",
  located_in: "位于",
  occurred_at: "发生于",
  "occurred at": "发生于",
  owns: "持有",
  present_at: "出现于",
  "present at": "出现于",
  relates_to: "关联",
}

const REVIEW_TYPE_LABELS: Record<string, string> = {
  alias_conflict: "别名冲突",
  event_merge_conflict: "事件合并冲突",
  knowledge_conflict: "知识冲突",
  memory_correction: "记忆修正",
  missing_source_span: "缺少证据段落",
}

const SEVERITY_LABELS: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
}

const SOURCE_SCOPE_LABELS: Record<string, string> = {
  author_note: "作者笔记",
  outline_plan: "大纲计划",
  reference_only: "参考材料",
  user_draft: "用户草稿",
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  author_notes: "作者笔记",
  character_sheet: "角色卡",
  draft_manuscript: "正文草稿",
  worldbuilding: "世界设定",
}

export function shortId(value: string): string {
  return UUID_PATTERN.test(value) ? value.slice(0, 8) : value
}

export function humanizeIdentifier(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) return ""
  const normalized = trimmed.toLowerCase().replace(/[_\s-]+/g, "_")
  if (normalized === "canon") return "已确认设定"
  if (normalized === "risk_context") return "待确认风险"
  if (normalized === "review_item_resolution") return "复核处理"
  if (normalized === "memory_writeback_decision") return "记忆回写处理"
  if (normalized === "author_note") return "作者说明"
  if (normalized === "mentions_updated") return "提及已更新"
  if (normalized === "context_pack_readiness") return "上下文依据"
  if (normalized === "context_pack_readiness_marked") return "上下文依据已更新"
  if (normalized === "graph_projection_run") return "关系图谱已更新"
  if (normalized === "unknown") return "未知"
  if (normalized === "rewrite_span") return "改写选区"
  if (normalized === "rewrite_current_page") return "重写当前页"
  if (normalized === "source_version") return "正文版本"
  if (normalized === "review_item") return "复核项"
  if (UUID_PATTERN.test(trimmed)) return trimmed.slice(0, 8)
  if (trimmed.includes("://")) return "对象存储已记录"
  if (/[\u4e00-\u9fff]/.test(trimmed)) return trimmed
  if (/^[a-z][a-z0-9-]*$/.test(trimmed)) {
    return trimmed
      .split("-")
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ")
  }
  return trimmed
}

export function typeLabel(type: unknown): string {
  if (typeof type !== "string" || !type.trim()) return "引用"
  return TYPE_LABELS[type] ?? humanizeIdentifier(type.replace(/_/g, " "))
}

export function statusLabel(status: unknown): string {
  if (typeof status !== "string" || !status.trim()) return "未知"
  return STATUS_LABELS[status] ?? humanizeIdentifier(status.replace(/_/g, " "))
}

export function deltaKindLabel(kind: unknown): string {
  if (typeof kind !== "string" || !kind.trim()) return "变更"
  return DELTA_KIND_LABELS[kind] ?? humanizeIdentifier(kind.replace(/_/g, " "))
}

export function predicateLabel(predicate: unknown): string {
  if (typeof predicate !== "string" || !predicate.trim()) return "事实"
  return PREDICATE_LABELS[predicate] ?? humanizeIdentifier(predicate.replace(/_/g, " "))
}

export function reviewTypeLabel(reviewType: unknown): string {
  if (typeof reviewType !== "string" || !reviewType.trim()) return "复核"
  return REVIEW_TYPE_LABELS[reviewType] ?? humanizeIdentifier(reviewType.replace(/_/g, " "))
}

export function severityLabel(severity: unknown): string {
  if (typeof severity !== "string" || !severity.trim()) return "未知"
  return SEVERITY_LABELS[severity] ?? humanizeIdentifier(severity.replace(/_/g, " "))
}

export function sourceTypeLabel(sourceType: unknown): string {
  if (typeof sourceType !== "string" || !sourceType.trim()) return "材料"
  return SOURCE_TYPE_LABELS[sourceType] ?? humanizeIdentifier(sourceType.replace(/_/g, " "))
}

export function sourceScopeLabel(sourceScope: unknown): string {
  if (typeof sourceScope !== "string" || !sourceScope.trim()) return "范围"
  return SOURCE_SCOPE_LABELS[sourceScope] ?? humanizeIdentifier(sourceScope.replace(/_/g, " "))
}

export function formatRef(value: unknown): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return typeof value === "string" ? humanizeIdentifier(value) : ""
  }
  const ref = value as Record<string, unknown>
  const label = stringField(ref.label) ?? stringField(ref.name) ?? stringField(ref.title)
  const id = stringField(ref.id)
  const type = stringField(ref.type)
  if (type === "scene") {
    const sceneName = sceneDisplayName(label) ?? sceneDisplayName(id)
    return sceneName ? `${sceneName} · 场景` : "场景"
  }
  const humanLabel = label ? humanizeIdentifier(label) : id ? humanizeIdentifier(id) : ""
  const humanType = type ? typeLabel(type) : ""
  if (humanLabel && humanType) return `${humanLabel} · ${humanType}`
  return humanLabel || humanType || "引用"
}

export function formatRefToken(value: unknown): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return typeof value === "string" ? humanizeIdentifier(value) : "引用"
  }
  const ref = value as Record<string, unknown>
  const type = typeLabel(ref.type)
  const rawId = typeof ref.id === "string" && ref.id.trim() ? ref.id.trim() : ""
  const id = rawId && !UUID_PATTERN.test(rawId) ? shortId(rawId) : ""
  return id ? `${type} ${humanizeIdentifier(id)}` : type
}

export function stringField(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null
}

function sceneDisplayName(value: string | null): string | null {
  if (!value) return null
  if (value.startsWith("scene:")) return null
  if (UUID_PATTERN.test(value)) return null
  return humanizeIdentifier(value)
}
