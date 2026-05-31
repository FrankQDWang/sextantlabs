"use client"

import { sceneCard } from "@/lib/workbench-data"
import { Eye, EyeOff, AlertTriangle, Flame, HelpCircle } from "lucide-react"
import type { LucideIcon } from "lucide-react"

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
  onItemClick?: () => void
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
        {items.map((item) =>
          onItemClick ? (
            <li key={item}>
              <button
                onClick={onItemClick}
                className={`flex w-full items-start gap-1.5 rounded-md px-1.5 py-1 -mx-1.5 text-left text-[12.5px] leading-snug transition-colors hover:bg-primary/8 ${toneMap[tone]}`}
              >
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-current opacity-40" />
                <span>{item}</span>
              </button>
            </li>
          ) : (
            <li
              key={item}
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

export function SceneCard({ onUseDirection }: { onUseDirection?: () => void }) {
  return (
    <aside className="hidden w-[264px] shrink-0 overflow-y-auto border-l border-border bg-sidebar/40 lg:block">
      {/* 卡头 */}
      <div className="sticky top-0 z-10 border-b border-border bg-sidebar/80 px-4 py-3 backdrop-blur">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">当前场景</p>
        <div className="mt-1 flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/12 text-[11px] font-medium text-primary">
            M
          </span>
          <div className="leading-tight">
            <p className="text-[13px] font-medium text-foreground">POV · {sceneCard.pov}</p>
          </div>
        </div>
      </div>

      <div className="divide-y divide-border">
        <Section icon={Eye} title="Mira 现在知道" items={sceneCard.knows} />
        <Section icon={EyeOff} title="Mira 还不知道" items={sceneCard.notKnows} tone="muted" />
        <Section icon={AlertTriangle} title="可能穿帮" items={sceneCard.pitfalls} tone="warning" />
        <Section
          icon={Flame}
          title="可用压力点"
          items={sceneCard.pressurePoints}
          tone="pressure"
          onItemClick={onUseDirection}
        />
        <Section icon={HelpCircle} title="开放悬念" items={sceneCard.openThreads} tone="muted" />
      </div>
    </aside>
  )
}
