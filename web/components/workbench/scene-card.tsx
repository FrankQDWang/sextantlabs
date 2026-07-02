"use client"

import { sceneCard } from "@/lib/workbench-data"
import {
  AlertTriangle,
  Clock,
  Eye,
  EyeOff,
  Flame,
  HelpCircle,
  MapPin,
  PenLine,
  UserCheck,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"

export interface SceneCardState {
  pov: string
  knows: string[]
  notKnows: string[]
  pitfalls: string[]
  pressurePoints: string[]
  openThreads: string[]
  recentEvents?: string[]
  objectState?: string[]
  agency?: string[]
  styleNotes?: string[]
}

export type ContextReadinessState = {
  pending: number
  stale: number
  consumed: number
  loading: boolean
  error: string | null
}

function Section({
  icon: Icon,
  title,
  items,
  tone = "default",
  onItemClick,
}: {
  icon: LucideIcon
  title: string
  items: string[]
  tone?: "default" | "muted" | "warning" | "pressure"
  onItemClick?: (item: string) => void
}) {
  const toneMap = {
    default: "text-foreground/80",
    muted: "text-muted-foreground",
    warning: "text-[color:var(--warning)]",
    pressure: "text-primary",
  }
  const iconTone = {
    default: "text-success",
    muted: "text-muted-foreground/70",
    warning: "text-[color:var(--warning)]",
    pressure: "text-primary",
  }
  return (
    <section className="px-4 py-3">
      <div className="mb-2 flex items-center gap-1.5">
        <Icon className={`h-3.5 w-3.5 ${iconTone[tone]}`} strokeWidth={1.75} />
        <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {title}
        </h3>
      </div>
      <ul className="space-y-1.5">
        {items.map((item, index) =>
          onItemClick ? (
            <li key={`${item}-${index}`}>
              <button
                onClick={() => onItemClick(item)}
                className={`flex w-full items-start gap-1.5 rounded-md px-1.5 py-1 -mx-1.5 text-left text-[12.5px] leading-snug transition-colors hover:bg-primary/8 ${toneMap[tone]}`}
              >
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-current opacity-40" />
                <span>{item}</span>
              </button>
            </li>
          ) : (
            <li
              key={`${item}-${index}`}
              className={`flex gap-1.5 text-[12.5px] leading-snug ${toneMap[tone]}`}
            >
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-current opacity-40" />
              <span>{item}</span>
            </li>
          ),
        )}
      </ul>
    </section>
  )
}

export function SceneCard({
  data,
  loading = false,
  error = null,
  readiness,
  onUseDirection,
}: {
  data?: SceneCardState
  loading?: boolean
  error?: string | null
  readiness?: ContextReadinessState
  onUseDirection?: (direction: string) => void
}) {
  const card: SceneCardState = data ?? sceneCard
  const readinessText = contextReadinessText(readiness)
  const povLabel = card.pov.trim() || "当前 POV"
  const povInitial = povLabel.slice(0, 1).toLocaleUpperCase()
  return (
    <aside className="hidden w-[264px] shrink-0 overflow-y-auto border-l border-border bg-sidebar/40 lg:block">
      {/* 卡头 */}
      <div className="sticky top-0 z-10 border-b border-border bg-sidebar/80 px-4 py-3 backdrop-blur">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">当前场景</p>
        <div className="mt-1 flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/12 text-[11px] font-medium text-primary">
            {povInitial}
          </span>
          <div className="leading-tight">
            <p className="text-[13px] font-medium text-foreground">POV · {povLabel}</p>
          </div>
        </div>
        {loading && <p className="mt-1 text-[11px] text-muted-foreground">读取上下文…</p>}
        {error && <p className="mt-1 text-[11px] text-destructive">{error}</p>}
        {readinessText && (
          <p
            className={`mt-1 text-[11px] ${readinessText.tone === "warning" ? "text-[color:var(--warning)]" : "text-muted-foreground"}`}
          >
            {readinessText.label}
          </p>
        )}
      </div>

      <div className="divide-y divide-border">
        <Section icon={Eye} title={`${povLabel} 现在知道`} items={card.knows} />
        <Section icon={EyeOff} title={`${povLabel} 还不知道`} items={card.notKnows} tone="muted" />
        <Section icon={AlertTriangle} title="可能穿帮" items={card.pitfalls} tone="warning" />
        <Section
          icon={Flame}
          title="可用压力点"
          items={card.pressurePoints}
          tone="pressure"
          onItemClick={onUseDirection}
        />
        <Section icon={HelpCircle} title="开放悬念" items={card.openThreads} tone="muted" />
        {card.recentEvents?.length ? (
          <Section icon={Clock} title="最近事件" items={card.recentEvents} />
        ) : null}
        {card.objectState?.length ? (
          <Section icon={MapPin} title="物件与地点" items={card.objectState} />
        ) : null}
        {card.agency?.length ? (
          <Section icon={UserCheck} title="角色动因" items={card.agency} tone="pressure" />
        ) : null}
        {card.styleNotes?.length ? (
          <Section icon={PenLine} title="风格样本" items={card.styleNotes} tone="muted" />
        ) : null}
      </div>
    </aside>
  )
}

function contextReadinessText(
  readiness: ContextReadinessState | undefined,
): { label: string; tone: "default" | "warning" } | null {
  if (!readiness) {
    return null
  }
  if (readiness.loading) {
    return { label: "上下文依据状态读取中…", tone: "default" }
  }
  if (readiness.error) {
    return { label: "上下文依据状态读取失败", tone: "warning" }
  }
  const waiting = readiness.pending + readiness.stale
  if (waiting > 0) {
    return { label: `上下文依据待更新 · ${waiting}`, tone: "warning" }
  }
  return { label: "上下文依据已同步", tone: "default" }
}
