"use client"

import { useState } from "react"
import { writebackItems, type RiskLevel } from "@/lib/workbench-data"
import { BookmarkPlus, X, AlertTriangle, Check } from "lucide-react"

interface MemoryWritebackProps {
  onClose: () => void
  /** 撤销刚插入的句子（连同记忆一起回退） */
  onUndoAll: () => void
}

const dot: Record<RiskLevel, string> = {
  low: "bg-success",
  medium: "bg-[color:var(--warning)]",
  high: "bg-destructive",
}

export function MemoryWriteback({ onClose, onUndoAll }: MemoryWritebackProps) {
  // 每条都可被处理（记住/撤销/进入 Review），处理完即从列表移除
  const [items, setItems] = useState(writebackItems)
  const [done, setDone] = useState(false)

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

      {done ? (
        <div className="flex flex-col items-center gap-1.5 px-3.5 py-7 text-center">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-success/12 text-success">
            <Check className="h-4 w-4" strokeWidth={2} />
          </span>
          <p className="text-[13px] font-medium text-foreground">都处理好了</p>
          <p className="text-[11px] text-muted-foreground">继续写就好，Sextant 在后台帮你记着。</p>
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
        低风险已记住，可撤销 · 有风险的会进入 Review，不打断你写作。
      </div>
    </div>
  )
}
