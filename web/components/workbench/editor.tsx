"use client"

import { useRef } from "react"
import { manuscript, project } from "@/lib/workbench-data"

interface EditorProps {
  /** 在正文里真实选中文字时回调（含视口坐标用于定位浮动菜单） */
  onSelect: (sel: { text: string; x: number; y: number } | null) => void
  /** 引导演示：高亮第二段以示意"选区" */
  demoHighlight: boolean
  /** 是否已局部采纳（句子已插入正文） */
  acceptedSentence: string | null
}

export function Editor({ onSelect, demoHighlight, acceptedSentence }: EditorProps) {
  const articleRef = useRef<HTMLElement>(null)

  function handleMouseUp() {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed) {
      onSelect(null)
      return
    }
    const text = sel.toString().trim()
    if (text.length < 2) {
      onSelect(null)
      return
    }
    // 仅响应正文内的选择
    if (articleRef.current && !articleRef.current.contains(sel.anchorNode)) {
      return
    }
    const rect = sel.getRangeAt(0).getBoundingClientRect()
    onSelect({
      text,
      x: rect.left + rect.width / 2,
      y: Math.max(rect.top, 96),
    })
  }

  return (
    <div className="prose-editor relative flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[640px] px-8 py-14">
        {/* 章节标题区 — 安静、克制 */}
        <div className="mb-10">
          <p className="mb-1 font-mono text-[11px] uppercase tracking-wider text-muted-foreground/70">
            {project.chapter}
          </p>
          <h1 className="font-serif text-2xl font-semibold leading-snug text-foreground">
            西档案室
          </h1>
        </div>

        {/* 正文 — 选中任意文字即可唤出菜单 */}
        <article
          ref={articleRef}
          onMouseUp={handleMouseUp}
          className="font-serif text-[16px] leading-[1.9] text-foreground/90 selection:bg-primary/20"
        >
          {manuscript.map((para, i) => (
            <p key={i} className="mb-6 [text-indent:0]">
              {i === 1 && demoHighlight ? (
                <span className="rounded-sm bg-primary/15 box-decoration-clone px-0.5">
                  {para}
                </span>
              ) : (
                para
              )}
            </p>
          ))}

          {/* 局部采纳后插入正文的句子 */}
          {acceptedSentence && (
            <p className="mb-6 animate-fade-in">
              <span className="rounded-sm bg-success/12 box-decoration-clone px-0.5 text-foreground/90">
                {acceptedSentence}
              </span>
            </p>
          )}

          {/* 写作光标 */}
          <p className="text-foreground/40">
            <span className="cursor-blink font-sans">|</span>
          </p>
        </article>

        <p className="mt-8 text-[12px] text-muted-foreground/60">
          提示：在上面正文里选中任意一句话，试试浮动菜单 · 或按 ⌘K 问 Sextant
        </p>
      </div>
    </div>
  )
}
