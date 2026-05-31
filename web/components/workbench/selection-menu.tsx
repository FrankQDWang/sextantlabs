"use client"

import { Pencil, FileSearch, ShieldAlert, ArrowDownNarrowWide } from "lucide-react"

interface SelectionMenuProps {
  x: number
  y: number
  onAction: (label: string) => void
}

const actions = [
  { icon: Pencil, label: "改写" },
  { icon: FileSearch, label: "查证据" },
  { icon: ShieldAlert, label: "查风险" },
  { icon: ArrowDownNarrowWide, label: "压低语气" },
]

export function SelectionMenu({ x, y, onAction }: SelectionMenuProps) {
  return (
    <div
      style={{ position: "fixed", top: y - 46, left: x, transform: "translateX(-50%)" }}
      className="animate-slide-up z-50 flex items-center gap-0.5 whitespace-nowrap rounded-lg border border-border bg-popover p-1 shadow-lg shadow-foreground/10"
      role="menu"
    >
      {actions.map(({ icon: Icon, label }) => (
        <button
          key={label}
          onMouseDown={(e) => {
            // 用 mouseDown 防止点击时浏览器先清空选区
            e.preventDefault()
            onAction(label)
          }}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 font-sans text-[12px] text-popover-foreground transition-colors hover:bg-accent"
          role="menuitem"
        >
          <Icon className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
          {label}
        </button>
      ))}
    </div>
  )
}
