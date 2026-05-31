"use client"

import type { ReviewItem } from "@/lib/workbench-data"
import { ShieldAlert, ChevronRight } from "lucide-react"

interface ReviewBadgeProps {
  items: ReviewItem[]
  open: boolean
  onToggle: () => void
}

export function ReviewBadge({ items, open, onToggle }: ReviewBadgeProps) {
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
                这些不会写进 canon，先放在这里，不打断你写作。
              </p>
            </div>
            <div className="divide-y divide-border">
              {items.map((item) => (
                <button
                  key={item.id}
                  className="group flex w-full items-start gap-2 px-3.5 py-2.5 text-left transition-colors hover:bg-accent"
                >
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[color:var(--warning)]" />
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] leading-snug text-foreground">{item.text}</p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">{item.hint}</p>
                  </div>
                  <ChevronRight
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground/0 transition-colors group-hover:text-muted-foreground"
                    strokeWidth={1.75}
                  />
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
