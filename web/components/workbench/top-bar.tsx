"use client"

import { BookOpen, Compass, ChevronRight, Search, PanelLeft } from "lucide-react"
import { project as demoProject } from "@/lib/workbench-data"
import { ReviewBadge, type ReviewResolveDetails } from "./review-badge"
import type { ReviewItem } from "@/lib/workbench-data"
import type { ReviewResolution } from "@/lib/workbench-api"
import type {
  CanonicalEntitySummaryResponse,
  ReviewItemDetailResponse,
  SourceDeltaSummaryResponse,
  StorySceneSummaryResponse,
} from "@/src/generated/sextant-api"

export type WorkbenchProjectHeader = {
  name: string
  chapter: string
  pov: string
}

interface TopBarProps {
  projectHeader?: WorkbenchProjectHeader
  onAskOpen: () => void
  memoryOpen?: boolean
  memoryCount?: number | null
  memoryLoading?: boolean
  onMemoryToggle?: () => void
  projectOpen?: boolean
  onProjectToggle?: () => void
  reviewItems: ReviewItem[]
  reviewOpen: boolean
  onReviewToggle: () => void
  reviewDetail?: ReviewItemDetailResponse | null
  reviewDetailLoading?: boolean
  reviewDetailError?: string | null
  reviewEntityOptions?: CanonicalEntitySummaryResponse[]
  reviewEntityOptionsLoading?: boolean
  reviewEntityOptionsError?: string | null
  reviewSceneOptions?: StorySceneSummaryResponse[]
  reviewSceneOptionsLoading?: boolean
  reviewSceneOptionsError?: string | null
  reviewSourceDeltaOptions?: SourceDeltaSummaryResponse[]
  onReviewItemSelect?: (id: string) => void
  reviewOperationPending?: boolean
  onReviewResolve?: (
    id: string,
    resolution: ReviewResolution,
    details: ReviewResolveDetails,
  ) => void
  onReviewDismiss?: (id: string) => void
  onReviewReopen?: (id: string) => void
}

export function TopBar({
  projectHeader = demoProject,
  onAskOpen,
  memoryOpen = false,
  memoryCount = null,
  memoryLoading = false,
  onMemoryToggle,
  projectOpen = false,
  onProjectToggle,
  reviewItems,
  reviewOpen,
  onReviewToggle,
  reviewDetail = null,
  reviewDetailLoading = false,
  reviewDetailError = null,
  reviewEntityOptions = [],
  reviewEntityOptionsLoading = false,
  reviewEntityOptionsError = null,
  reviewSceneOptions = [],
  reviewSceneOptionsLoading = false,
  reviewSceneOptionsError = null,
  reviewSourceDeltaOptions = [],
  onReviewItemSelect,
  reviewOperationPending = false,
  onReviewResolve,
  onReviewDismiss,
  onReviewReopen,
}: TopBarProps) {
  const header = projectHeader
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
      {/* 左：极简项目入口 + 面包屑 */}
      <div className="flex items-center gap-1.5 text-[13px]">
        <button
          onClick={onProjectToggle}
          className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          aria-label="展开项目"
          aria-expanded={projectOpen}
        >
          <PanelLeft className="h-4 w-4" strokeWidth={1.75} />
        </button>
        <div className="flex items-center gap-1.5 pl-1">
          <Compass className="h-4 w-4 text-primary" strokeWidth={1.75} />
          <span className="font-medium text-foreground">{header.name}</span>
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/60" strokeWidth={1.75} />
          <span className="text-muted-foreground">{header.chapter}</span>
        </div>
        <span className="ml-2 inline-flex items-center gap-1.5 rounded-full bg-secondary px-2 py-0.5 text-[12px] text-secondary-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" />
          POV · {header.pov}
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
        {onMemoryToggle && (
          <button
            onClick={onMemoryToggle}
            aria-label={memoryOpen ? "关闭记忆页" : "打开记忆页"}
            aria-expanded={memoryOpen}
            className="flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1.5 text-[12px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            <BookOpen className="h-3.5 w-3.5" strokeWidth={1.75} />
            <span>记忆</span>
            <span className="rounded border border-border bg-muted px-1 py-px font-mono text-[10px]">
              {memoryLoading ? "…" : memoryCount ?? "—"}
            </span>
          </button>
        )}
        <ReviewBadge
          items={reviewItems}
          open={reviewOpen}
          onToggle={onReviewToggle}
          detail={reviewDetail}
          detailLoading={reviewDetailLoading}
          detailError={reviewDetailError}
          entityOptions={reviewEntityOptions}
          entityOptionsLoading={reviewEntityOptionsLoading}
          entityOptionsError={reviewEntityOptionsError}
          sceneOptions={reviewSceneOptions}
          sceneOptionsLoading={reviewSceneOptionsLoading}
          sceneOptionsError={reviewSceneOptionsError}
          sourceDeltaOptions={reviewSourceDeltaOptions}
          onItemSelect={onReviewItemSelect}
          operationPending={reviewOperationPending}
          onResolve={onReviewResolve}
          onDismiss={onReviewDismiss}
          onReopen={onReviewReopen}
        />
      </div>
    </header>
  )
}
