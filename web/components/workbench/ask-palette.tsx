"use client"

import { Search, PenLine, FileSearch, ShieldAlert, History, CornerDownLeft } from "lucide-react"

interface AskPaletteProps {
  onClose: () => void
  onPick: (label: string) => void
}

const suggestions = [
  { icon: PenLine, label: "续写这一段", hint: "给出几条候选" },
  { icon: FileSearch, label: "Mira 现在知道钥匙的来源吗？", hint: "查证据" },
  { icon: ShieldAlert, label: "这里有没有写得太实的暗示？", hint: "查风险" },
  { icon: History, label: "Kestrel 上一次回避是什么时候？", hint: "查前文" },
]

export function AskPalette({ onClose, onPick }: AskPaletteProps) {
  return (
    <div
      className="animate-fade-in fixed inset-0 z-50 flex items-start justify-center bg-foreground/10 pt-[16vh] backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className="animate-slide-up w-full max-w-[560px] overflow-hidden rounded-xl border border-border bg-popover shadow-2xl shadow-foreground/10"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 输入行 */}
        <div className="flex items-center gap-2.5 border-b border-border px-4 py-3">
          <Search className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
          <input
            autoFocus
            placeholder="问 Sextant，或描述你想怎么写…"
            onKeyDown={(e) => {
              if (e.key === "Enter" && e.currentTarget.value.trim()) {
                onPick(e.currentTarget.value.trim())
              }
            }}
            className="flex-1 bg-transparent text-[14px] text-foreground placeholder:text-muted-foreground/70 focus:outline-none"
          />
          <kbd className="rounded border border-border bg-muted px-1.5 py-px font-mono text-[10px] text-muted-foreground">
            esc
          </kbd>
        </div>

        {/* 建议 */}
        <div className="p-1.5">
          <p className="px-2.5 py-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
            建议
          </p>
          {suggestions.map(({ icon: Icon, label, hint }) => (
            <button
              key={label}
              onClick={() => onPick(label)}
              className="group flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors hover:bg-accent"
            >
              <Icon className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
              <span className="flex-1 text-[13px] text-foreground">{label}</span>
              <span className="text-[11px] text-muted-foreground">{hint}</span>
              <CornerDownLeft className="h-3 w-3 text-muted-foreground/0 transition-colors group-hover:text-muted-foreground" strokeWidth={1.75} />
            </button>
          ))}
        </div>

        <div className="border-t border-border px-4 py-2 text-[11px] text-muted-foreground">
          Sextant 只给候选和解释，不会直接改你的正文。
        </div>
      </div>
    </div>
  )
}
