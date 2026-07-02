"use client"

import { useMemo, useState } from "react"
import { Search, PenLine, FileSearch, ShieldAlert, History, CornerDownLeft, Compass } from "lucide-react"
import type { AskMemoryTarget } from "@/lib/workbench-api"

export type AskMemoryTargetOption = {
  id: string
  entityType: string
  label: string
}

export type AskSuggestionContext = {
  povLabel?: string | null
  recallLabel?: string | null
}

interface AskPaletteProps {
  onClose: () => void
  onPick: (label: string, memoryTarget?: AskMemoryTarget) => void
  memoryTargetOptions?: AskMemoryTargetOption[]
  memoryTargetsLoading?: boolean
  memoryTargetsError?: string | null
  suggestionContext?: AskSuggestionContext
}

export function AskPalette({
  onClose,
  onPick,
  memoryTargetOptions = [],
  memoryTargetsLoading = false,
  memoryTargetsError = null,
  suggestionContext,
}: AskPaletteProps) {
  const [selectedTarget, setSelectedTarget] = useState("")
  const [selectedPredicate, setSelectedPredicate] = useState("")
  const suggestions = useMemo(
    () => askSuggestions(suggestionContext),
    [suggestionContext],
  )
  const targetByValue = useMemo(() => {
    const entries = memoryTargetOptions.map((option) => [
      memoryTargetValue(option),
      option,
    ] as const)
    return new Map(entries)
  }, [memoryTargetOptions])

  function pick(label: string) {
    onPick(label, selectedMemoryTarget(targetByValue.get(selectedTarget), selectedPredicate))
  }

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
                pick(e.currentTarget.value.trim())
              }
            }}
            className="flex-1 bg-transparent text-[14px] text-foreground placeholder:text-muted-foreground/70 focus:outline-none"
          />
          <kbd className="rounded border border-border bg-muted px-1.5 py-px font-mono text-[10px] text-muted-foreground">
            esc
          </kbd>
        </div>

        {memoryTargetOptions.length > 0 || memoryTargetsLoading || memoryTargetsError ? (
          <div className="grid grid-cols-[minmax(0,1fr)_150px] gap-2 border-b border-border bg-muted/20 px-4 py-2">
            <label className="sr-only" htmlFor="ask-memory-target">记忆对象</label>
            <select
              id="ask-memory-target"
              aria-label="记忆对象"
              value={selectedTarget}
              disabled={memoryTargetsLoading}
              onChange={(event) => setSelectedTarget(event.target.value)}
              className="h-7 min-w-0 rounded-md border border-border bg-background px-2 text-[12px] text-foreground outline-none transition-colors focus:border-primary/50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">
                {memoryTargetsLoading ? "读取记忆对象…" : memoryTargetsError ? "对象读取失败" : "不指定对象"}
              </option>
              {memoryTargetOptions.map((option) => (
                <option key={memoryTargetValue(option)} value={memoryTargetValue(option)}>
                  {option.label}
                </option>
              ))}
            </select>
            <label className="sr-only" htmlFor="ask-memory-predicate">记忆关系</label>
            <select
              id="ask-memory-predicate"
              aria-label="记忆关系"
              value={selectedPredicate}
              onChange={(event) => setSelectedPredicate(event.target.value)}
              className="h-7 rounded-md border border-border bg-background px-2 text-[12px] text-foreground outline-none transition-colors focus:border-primary/50"
            >
              <option value="">不指定关系</option>
              {memoryPredicateOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        {/* 建议 */}
        <div className="p-1.5">
          <p className="px-2.5 py-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
            建议
          </p>
          {suggestions.map(({ icon: Icon, label, hint }) => (
            <button
              key={label}
              onClick={() => pick(label)}
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

const memoryPredicateOptions = [
  { value: "owns", label: "拥有 / 携带" },
  { value: "knows", label: "知道 / 认为" },
  { value: "located_in", label: "所在位置" },
  { value: "appears_in", label: "出场" },
  { value: "open_thread", label: "开放伏笔" },
]

function askSuggestions(context: AskSuggestionContext | undefined) {
  const povLabel = cleanLabel(context?.povLabel) ?? "当前 POV"
  const recallLabel = cleanLabel(context?.recallLabel) ?? "当前角色"
  return [
    { icon: PenLine, label: "续写这一段", hint: "给出几条候选" },
    { icon: Compass, label: "下面可以发生什么？", hint: "方向" },
    { icon: ShieldAlert, label: "试写有争议版本", hint: "需要确认" },
    { icon: FileSearch, label: `${povLabel} 现在知道什么？`, hint: "查证据" },
    { icon: ShieldAlert, label: "这里有没有写得太实的暗示？", hint: "查风险" },
    { icon: History, label: `${recallLabel} 上一次回避是什么时候？`, hint: "查前文" },
  ]
}

function cleanLabel(value: string | null | undefined): string | null {
  const label = value?.trim()
  return label ? label : null
}

function memoryTargetValue(option: AskMemoryTargetOption): string {
  return `${option.entityType}:${option.id}`
}

function selectedMemoryTarget(
  option: AskMemoryTargetOption | undefined,
  predicate: string,
): AskMemoryTarget | undefined {
  const trimmedPredicate = predicate.trim()
  if (!option && !trimmedPredicate) return undefined
  return {
    ...(option
      ? { subjectRef: { type: option.entityType, id: option.id, label: option.label } }
      : {}),
    ...(trimmedPredicate ? { predicate: trimmedPredicate } : {}),
  }
}
