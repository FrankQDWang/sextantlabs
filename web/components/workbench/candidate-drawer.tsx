"use client"

import { useState } from "react"
import { candidates, type RiskLevel } from "@/lib/workbench-data"
import {
  Plus,
  Replace,
  Shuffle,
  FileSearch,
  ChevronDown,
  Sparkles,
  ShieldAlert,
} from "lucide-react"

interface CandidateDrawerProps {
  onClose: () => void
  onAcceptSentence: (text: string) => void
}

const riskStyle: Record<RiskLevel, { dot: string; text: string; label: string }> = {
  low: { dot: "bg-success", text: "text-success", label: "低风险" },
  medium: { dot: "bg-[color:var(--warning)]", text: "text-[color:var(--warning)]", label: "中风险" },
  high: { dot: "bg-destructive", text: "text-destructive", label: "高风险" },
}

export function CandidateDrawer({ onClose, onAcceptSentence }: CandidateDrawerProps) {
  const [activeId, setActiveId] = useState(candidates[0].id)
  const [selectedSentence, setSelectedSentence] = useState<string | null>(null)
  const active = candidates.find((c) => c.id === activeId)!

  return (
    <div className="animate-slide-up relative z-[60] shrink-0 border-t border-border bg-card">
      {/* 抽屉头 */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-primary" strokeWidth={1.75} />
          <span className="text-[12px] font-medium text-foreground">候选续写</span>
          <span className="text-[11px] text-muted-foreground">· 选一句加入，或借方向重写</span>
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
                {c.label}
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
          <p className="mb-2 text-[11px] text-muted-foreground">
            方向：<span className="text-foreground/70">{active.direction}</span>
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
              disabled={!selectedSentence}
              onClick={() => {
                const s = active.sentences.find((x) => x.id === selectedSentence)
                if (s) onAcceptSentence(s.text)
              }}
              className="flex items-center gap-1.5 rounded-md bg-primary px-2.5 py-1.5 text-[12px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Plus className="h-3.5 w-3.5" strokeWidth={2} />
              选这句加入
            </button>
            <button className="flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1.5 text-[12px] text-foreground transition-colors hover:bg-accent">
              <Replace className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
              替换当前句
            </button>
            <button className="flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1.5 text-[12px] text-foreground transition-colors hover:bg-accent">
              <Shuffle className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
              借这个方向重写
            </button>
            <button className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[12px] text-muted-foreground transition-colors hover:text-foreground">
              <FileSearch className="h-3.5 w-3.5" strokeWidth={1.75} />
              查看依据
            </button>
            {/* 次要动作：全文采纳 */}
            <button className="ml-auto rounded px-2 py-1 text-[11px] text-muted-foreground/70 underline-offset-2 transition-colors hover:text-muted-foreground hover:underline">
              全文采纳
            </button>
          </div>
        </div>

        {/* 右：依据 / 避开 / 风险 */}
        <div className="w-[260px] shrink-0 space-y-2.5 border-l border-border pl-5 text-[12px]">
          <div>
            <p className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">用到的 Memory</p>
            <div className="flex flex-wrap gap-1">
              {active.usedMemory.map((m) => (
                <span
                  key={m}
                  className="rounded border border-success/30 bg-success/8 px-1.5 py-0.5 text-[11px] text-success"
                >
                  {m}
                </span>
              ))}
            </div>
          </div>
          <div>
            <p className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">避开了未证实</p>
            <div className="flex flex-wrap gap-1">
              {active.avoided.map((m) => (
                <span
                  key={m}
                  className="rounded border border-border bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground line-through decoration-muted-foreground/40"
                >
                  {m}
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
                {active.risk.note}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
