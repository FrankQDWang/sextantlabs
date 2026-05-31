"use client"

import { useState, useEffect, useCallback } from "react"
import { TopBar } from "./top-bar"
import { Editor } from "./editor"
import { SceneCard } from "./scene-card"
import { CandidateDrawer } from "./candidate-drawer"
import { AskPalette } from "./ask-palette"
import { MemoryWriteback } from "./memory-writeback"
import { SelectionMenu } from "./selection-menu"
import { StateSwitcher, type DemoState } from "./state-switcher"
import { reviewItems } from "@/lib/workbench-data"

interface Selection {
  text: string
  x: number
  y: number
}

export function Workbench() {
  // 真实、相互独立的交互状态
  const [selection, setSelection] = useState<Selection | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [askOpen, setAskOpen] = useState(false)
  const [writebackOpen, setWritebackOpen] = useState(false)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [acceptedSentence, setAcceptedSentence] = useState<string | null>(null)
  const [demoHighlight, setDemoHighlight] = useState(false)

  const closeAll = useCallback(() => {
    setSelection(null)
    setDrawerOpen(false)
    setAskOpen(false)
    setWritebackOpen(false)
    setReviewOpen(false)
    setAcceptedSentence(null)
    setDemoHighlight(false)
  }, [])

  // 在正文里真实选中文字 → 弹出浮动菜单
  const handleSelect = useCallback((sel: Selection | null) => {
    setDemoHighlight(false)
    setSelection(sel)
  }, [])

  // 选区菜单里的动作 → 打开候选抽屉
  const handleSelectionAction = useCallback(() => {
    setSelection(null)
    setDemoHighlight(false)
    setDrawerOpen(true)
  }, [])

  // 候选抽屉里"选这句加入" → 插入正文 + 弹出记忆回写
  const handleAcceptSentence = useCallback((text: string) => {
    setAcceptedSentence(text)
    setDrawerOpen(false)
    setWritebackOpen(true)
  }, [])

  // 撤销刚插入的句子
  const handleUndoAccept = useCallback(() => {
    setAcceptedSentence(null)
    setWritebackOpen(false)
  }, [])

  // ⌘K 打开 Ask，Esc 关闭浮层
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setAskOpen(true)
      }
      if (e.key === "Escape") {
        setSelection(null)
        setAskOpen(false)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  // 引导演示：把每个状态映射到真实状态组合
  const goToDemo = useCallback(
    (s: DemoState) => {
      closeAll()
      switch (s) {
        case "a":
          break
        case "b":
          setDemoHighlight(true)
          setSelection({ text: "demo", x: window.innerWidth * 0.32, y: 250 })
          break
        case "c":
          setAskOpen(true)
          break
        case "d":
          setDrawerOpen(true)
          break
        case "e":
          setAcceptedSentence("Mira 把钥匙又往他那边推了一寸。")
          setDrawerOpen(true)
          break
        case "f":
          setAcceptedSentence("Mira 把钥匙又往他那边推了一寸。")
          setWritebackOpen(true)
          break
        case "g":
          setReviewOpen(true)
          break
      }
    },
    [closeAll],
  )

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      <TopBar
        onAskOpen={() => setAskOpen(true)}
        reviewItems={reviewItems}
        reviewOpen={reviewOpen}
        onReviewToggle={() => setReviewOpen((v) => !v)}
      />

      {/* 主体：编辑器为绝对主角，右侧场景小卡为辅 */}
      <div className="flex min-h-0 flex-1">
        <div className="relative flex min-w-0 flex-1 flex-col [--editor-column:576px] [--editor-gutter:2rem]">
          <Editor
            onSelect={handleSelect}
            demoHighlight={demoHighlight}
            acceptedSentence={acceptedSentence}
          />
          {drawerOpen && (
            <CandidateDrawer
              onClose={() => setDrawerOpen(false)}
              onAcceptSentence={handleAcceptSentence}
            />
          )}
          <StateSwitcher
            value={resolveDemo({ selection, drawerOpen, askOpen, writebackOpen, reviewOpen, acceptedSentence })}
            onChange={goToDemo}
          />
        </div>
        <SceneCard onUseDirection={() => setDrawerOpen(true)} />
      </div>

      {/* 浮层 */}
      {selection && (
        <SelectionMenu x={selection.x} y={selection.y} onAction={handleSelectionAction} />
      )}
      {askOpen && (
        <AskPalette
          onClose={() => setAskOpen(false)}
          onPick={() => {
            setAskOpen(false)
            setDrawerOpen(true)
          }}
        />
      )}
      {writebackOpen && (
        <MemoryWriteback onClose={() => setWritebackOpen(false)} onUndoAll={handleUndoAccept} />
      )}

    </div>
  )
}

// 根据真实状态反推当前最接近的演示标记（用于高亮切换器）
function resolveDemo(s: {
  selection: Selection | null
  drawerOpen: boolean
  askOpen: boolean
  writebackOpen: boolean
  reviewOpen: boolean
  acceptedSentence: string | null
}): DemoState {
  if (s.reviewOpen) return "g"
  if (s.writebackOpen) return "f"
  if (s.drawerOpen) return s.acceptedSentence ? "e" : "d"
  if (s.askOpen) return "c"
  if (s.selection) return "b"
  return "a"
}
