"use client"

import { Compass, ChevronRight, Search, PanelLeft } from "lucide-react"
import { project } from "@/lib/workbench-data"
import { ReviewBadge } from "./review-badge"
import type { ReviewItem } from "@/lib/workbench-data"

interface TopBarProps {
  onAskOpen: () => void
  reviewItems: ReviewItem[]
  reviewOpen: boolean
  onReviewToggle: () => void
}

export function TopBar({ onAskOpen, reviewItems, reviewOpen, onReviewToggle }: TopBarProps) {
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
      {/* 左：极简项目入口 + 面包屑 */}
      <div className="flex items-center gap-1.5 text-[13px]">
        <button
          className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          aria-label="展开项目"
        >
          <PanelLeft className="h-4 w-4" strokeWidth={1.75} />
        </button>
        <div className="flex items-center gap-1.5 pl-1">
          <Compass className="h-4 w-4 text-primary" strokeWidth={1.75} />
          <span className="font-medium text-foreground">{project.name}</span>
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/60" strokeWidth={1.75} />
          <span className="text-muted-foreground">{project.chapter}</span>
        </div>
        <span className="ml-2 inline-flex items-center gap-1.5 rounded-full bg-secondary px-2 py-0.5 text-[12px] text-secondary-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" />
          POV · {project.pov}
        </span>
      </div>

      {/* 右：Ask / ⌘K 入口 + Review */}
      <div className="flex items-center gap-2">
        <button
          onClick={onAskOpen}
          className="group flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 text-[12px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
        >
          <Search className="h-3.5 w-3.5" strokeWidth={1.75} />
          <span>问 Sextant</span>
          <kbd className="ml-1 rounded border border-border bg-muted px-1.5 py-px font-mono text-[10px] text-muted-foreground">
            ⌘K
          </kbd>
        </button>
        <ReviewBadge
          items={reviewItems}
          open={reviewOpen}
          onToggle={onReviewToggle}
        />
      </div>
    </header>
  )
}
