"use client"

export type DemoState = "a" | "b" | "c" | "d" | "e" | "f" | "g"

const states: { id: DemoState; label: string }[] = [
  { id: "a", label: "默认写作" },
  { id: "b", label: "选区菜单" },
  { id: "c", label: "Ask ⌘K" },
  { id: "d", label: "候选抽屉" },
  { id: "e", label: "局部采纳" },
  { id: "f", label: "记忆回写" },
  { id: "g", label: "Review" },
]

interface StateSwitcherProps {
  value: DemoState
  onChange: (s: DemoState) => void
  raised?: boolean
}

export function StateSwitcher({ value, onChange, raised = false }: StateSwitcherProps) {
  return (
    <div
      className={`absolute left-1/2 z-50 flex w-max -translate-x-1/2 items-center gap-0.5 whitespace-nowrap rounded-full border border-border bg-popover/90 p-1 shadow-lg shadow-foreground/5 backdrop-blur ${
        raised ? "bottom-[var(--candidate-drawer-height)]" : "bottom-4"
      }`}
    >
      <span className="px-2 text-[10px] uppercase tracking-wide text-muted-foreground/70">演示</span>
      {states.map((s) => (
        <button
          key={s.id}
          onClick={() => onChange(s.id)}
          className={`rounded-full px-2.5 py-1 text-[11.5px] transition-colors ${
            value === s.id
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-accent hover:text-foreground"
          }`}
        >
          {s.label}
        </button>
      ))}
    </div>
  )
}
