"use client"

import { useRef } from "react"
import { Pencil, RefreshCcw, Save, WandSparkles, X } from "lucide-react"

interface EditorProps {
  /** 在正文里真实选中文字时回调（含视口坐标用于定位浮动菜单） */
  onSelect: (
    sel: { text: string; x: number; y: number; range: { start: number; end: number } } | null,
  ) => void
  onParagraphRewrite: (sel: { text: string; range: { start: number; end: number } }) => void
  /** 引导演示：高亮第二段以示意"选区" */
  demoHighlight: boolean
  /** 是否已局部采纳（句子已插入正文） */
  acceptedSentence: string | null
  text: string
  title: string
  chapter: string
  sourceError: string | null
  isSourceEditing?: boolean
  sourceEditText?: string
  sourceEditPending?: boolean
  sourceEditStatus?: string | null
  sourceEditError?: string | null
  sourceEditRefreshPending?: boolean
  sourceEditRejectedDraftText?: string | null
  onSourceEditStart?: () => void
  onSourceEditChange?: (text: string) => void
  onSourceEditCancel?: () => void
  onSourceEditSave?: () => void
  onSourceEditRefresh?: () => void
  onSourceEditMergeRejectedDraft?: () => void
  onSourceEditApplyRejectedDraft?: () => void
  onSourceEditDismissRejectedDraft?: () => void
}

export function Editor({
  onSelect,
  onParagraphRewrite,
  demoHighlight,
  acceptedSentence,
  text,
  title,
  chapter,
  sourceError,
  isSourceEditing = false,
  sourceEditText = text,
  sourceEditPending = false,
  sourceEditStatus = null,
  sourceEditError = null,
  sourceEditRefreshPending = false,
  sourceEditRejectedDraftText = null,
  onSourceEditStart,
  onSourceEditChange,
  onSourceEditCancel,
  onSourceEditSave,
  onSourceEditRefresh,
  onSourceEditMergeRejectedDraft,
  onSourceEditApplyRejectedDraft,
  onSourceEditDismissRejectedDraft,
}: EditorProps) {
  const articleRef = useRef<HTMLElement>(null)
  const paragraphs = splitParagraphs(text)
  const paragraphRanges = paragraphTextRanges(paragraphs)
  const sourceEditPreview = isSourceEditing
    ? buildSourceEditPreview(text, sourceEditText)
    : null

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
    const root = articleRef.current
    if (!root || !root.contains(sel.anchorNode)) {
      return
    }
    const rect = sel.getRangeAt(0).getBoundingClientRect()
    const range = editorRange(root, sel.getRangeAt(0))
    onSelect({
      text,
      x: rect.left + rect.width / 2,
      y: Math.max(rect.top, 96),
      range,
    })
  }

  return (
    <div className="prose-editor relative flex-1 overflow-y-auto px-[var(--editor-gutter)] py-14">
      <div className="mx-auto max-w-[var(--editor-column)]">
        {/* 章节标题区 — 安静、克制 */}
        <div className="mb-10 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p
              data-testid="editor-version-label"
              className="mb-1 font-mono text-[11px] uppercase tracking-wider text-muted-foreground/70"
            >
              {chapter}
            </p>
            <h1 className="font-serif text-2xl font-semibold leading-snug text-foreground">
              {title}
            </h1>
            {sourceError && (
              <p className="mt-2 text-[12px] text-destructive">
                {sourceError}
              </p>
            )}
            {!isSourceEditing && sourceEditStatus && (
              <p className="mt-2 text-[12px] text-muted-foreground">
                {sourceEditStatus}
              </p>
            )}
            {!isSourceEditing && sourceEditError && (
              <p className="mt-2 text-[12px] text-destructive">
                {sourceEditError}
              </p>
            )}
          </div>
          {onSourceEditStart && !isSourceEditing && (
            <button
              type="button"
              aria-label="编辑当前正文版本"
              title="编辑当前正文版本"
              onClick={onSourceEditStart}
              className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border bg-card text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <Pencil className="h-3.5 w-3.5" strokeWidth={1.75} />
            </button>
          )}
        </div>

        {/* 正文 — 选中任意文字即可唤出菜单 */}
        <article
          ref={articleRef}
          onMouseUp={isSourceEditing ? undefined : handleMouseUp}
          className="font-serif text-[16px] leading-[1.9] text-foreground/90 selection:bg-primary/20"
        >
          {isSourceEditing ? (
            <div className="space-y-2">
              <textarea
                aria-label="编辑当前正文"
                value={sourceEditText}
                onChange={(event) => onSourceEditChange?.(event.target.value)}
                className="min-h-[420px] w-full resize-y rounded-md border border-border bg-card px-4 py-3 font-serif text-[16px] leading-[1.9] text-foreground outline-none focus:border-primary/50"
              />
              {sourceEditPreview?.changed && (
                <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] font-medium text-foreground">
                      {`编辑预览 · +${sourceEditPreview.insertions} / -${sourceEditPreview.deletions}`}
                    </p>
                    <p className="font-mono text-[10px] text-muted-foreground">
                      {sourceEditPreview.changedLineCount} lines
                    </p>
                  </div>
                  <div className="mt-1 max-h-28 space-y-0.5 overflow-y-auto font-mono text-[10.5px] leading-snug">
                    {sourceEditPreview.lines.map((line, index) => (
                      <p
                        key={`${line.kind}-${index}-${line.text}`}
                        className={
                          line.kind === "insert"
                            ? "text-success"
                            : line.kind === "delete"
                              ? "text-destructive"
                              : "text-muted-foreground"
                        }
                      >
                        {linePrefix(line.kind)} {line.text || " "}
                      </p>
                    ))}
                  </div>
                </div>
              )}
              {sourceEditRejectedDraftText && (
                <div
                  data-testid="source-edit-merge-assist"
                  className="rounded-md border border-border bg-card px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[11px] font-medium text-foreground">
                        草稿冲突
                      </p>
                      <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
                        最新正文版本已刷新，未保存草稿仍保留。
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {onSourceEditMergeRejectedDraft && (
                        <button
                          type="button"
                          aria-label="合并被拒绝的草稿"
                          onClick={onSourceEditMergeRejectedDraft}
                          disabled={sourceEditPending || sourceEditRefreshPending}
                          className="rounded-md bg-secondary px-2 py-1 text-[11px] text-secondary-foreground transition-colors hover:bg-accent disabled:cursor-wait disabled:opacity-50"
                        >
                          合并
                        </button>
                      )}
                      {onSourceEditApplyRejectedDraft && (
                        <button
                          type="button"
                          aria-label="套用被拒绝的草稿"
                          onClick={onSourceEditApplyRejectedDraft}
                          disabled={sourceEditPending || sourceEditRefreshPending}
                          className="rounded-md bg-secondary px-2 py-1 text-[11px] text-secondary-foreground transition-colors hover:bg-accent disabled:cursor-wait disabled:opacity-50"
                        >
                          套用草稿
                        </button>
                      )}
                      {onSourceEditDismissRejectedDraft && (
                        <button
                          type="button"
                          aria-label="丢弃被拒绝的草稿"
                          onClick={onSourceEditDismissRejectedDraft}
                          disabled={sourceEditPending || sourceEditRefreshPending}
                          className="rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:cursor-wait disabled:opacity-50"
                        >
                          丢弃
                        </button>
                      )}
                    </div>
                  </div>
                  <p className="mt-1 whitespace-pre-wrap break-words font-mono text-[10.5px] leading-snug text-muted-foreground">
                    {sourceEditRejectedDraftText}
                  </p>
                </div>
              )}
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0 text-[12px]">
                  {sourceEditError ? (
                    <span className="text-destructive">{sourceEditError}</span>
                  ) : sourceEditStatus ? (
                    <span className="text-muted-foreground">{sourceEditStatus}</span>
                  ) : null}
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {onSourceEditRefresh && (
                    <button
                      type="button"
                      aria-label="刷新最新正文版本"
                      title="刷新最新正文版本"
                      onClick={onSourceEditRefresh}
                      disabled={sourceEditPending || sourceEditRefreshPending}
                      className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-card text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:cursor-wait disabled:opacity-50"
                    >
                      <RefreshCcw className="h-3.5 w-3.5" strokeWidth={1.75} />
                    </button>
                  )}
                  {onSourceEditCancel && (
                    <button
                      type="button"
                      aria-label="取消编辑"
                      onClick={onSourceEditCancel}
                      disabled={sourceEditPending}
                      className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-card text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:cursor-wait disabled:opacity-50"
                    >
                      <X className="h-3.5 w-3.5" strokeWidth={1.75} />
                    </button>
                  )}
                  {onSourceEditSave && (
                    <button
                      type="button"
                      aria-label="保存为正文变更"
                      onClick={onSourceEditSave}
                      disabled={sourceEditPending}
                      className="flex h-7 w-7 items-center justify-center rounded-md bg-secondary text-secondary-foreground transition-colors hover:bg-accent disabled:cursor-wait disabled:opacity-50"
                    >
                      <Save className="h-3.5 w-3.5" strokeWidth={1.75} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <>
              {paragraphs.map((para, i) => (
                <p key={i} data-editor-para={i} className="group relative mb-6 [text-indent:0]">
                  <button
                    type="button"
                    aria-label={`改写这一段 ${i + 1}`}
                    title="改写这一段"
                    onClick={() => onParagraphRewrite({ text: para, range: paragraphRanges[i] })}
                    className="absolute -left-8 top-1 flex h-6 w-6 items-center justify-center rounded-md border border-border bg-card text-muted-foreground opacity-0 shadow-sm transition-colors hover:bg-accent hover:text-foreground group-hover:opacity-100 focus:opacity-100"
                  >
                    <WandSparkles className="h-3.5 w-3.5" strokeWidth={1.75} />
                  </button>
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
                <p data-editor-accepted="true" className="mb-6 animate-fade-in">
                  <span className="rounded-sm bg-success/12 box-decoration-clone px-0.5 text-foreground/90">
                    {acceptedSentence}
                  </span>
                </p>
              )}

              {/* 写作光标 */}
              <p className="text-foreground/40">
                <span className="cursor-blink font-sans">|</span>
              </p>
            </>
          )}
        </article>

        <p className="mt-8 text-[12px] text-muted-foreground/60">
          提示：在上面正文里选中任意一句话，试试浮动菜单 · 或按 ⌘K 问 Sextant
        </p>
      </div>
    </div>
  )
}

function editorRange(root: HTMLElement, range: Range): { start: number; end: number } {
  const paragraphs = Array.from(root.querySelectorAll<HTMLElement>("[data-editor-para]"))
  let offset = 0
  let start = 0
  let end = 0

  for (const paragraph of paragraphs) {
    const paraStart = offset
    const paraTextLength = paragraph.textContent?.length ?? 0
    if (paragraph.contains(range.startContainer)) {
      start = paraStart + nodeOffsetWithin(paragraph, range.startContainer, range.startOffset)
    }
    if (paragraph.contains(range.endContainer)) {
      end = paraStart + nodeOffsetWithin(paragraph, range.endContainer, range.endOffset)
      break
    }
    offset += paraTextLength + 1
  }

  return { start, end: Math.max(end, start) }
}

function nodeOffsetWithin(root: Node, target: Node, targetOffset: number): number {
  const range = document.createRange()
  range.setStart(root, 0)
  range.setEnd(target, targetOffset)
  return range.toString().length
}

function splitParagraphs(text: string): string[] {
  return text
    .split(/\n+/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
}

type SourceEditPreviewLine = {
  kind: "context" | "insert" | "delete"
  text: string
}

function buildSourceEditPreview(baseText: string, draftText: string): {
  changed: boolean
  insertions: number
  deletions: number
  changedLineCount: number
  lines: SourceEditPreviewLine[]
} {
  if (baseText === draftText) {
    return { changed: false, insertions: 0, deletions: 0, changedLineCount: 0, lines: [] }
  }
  const baseLines = baseText.split("\n")
  const draftLines = draftText.split("\n")
  let prefix = 0
  while (
    prefix < baseLines.length &&
    prefix < draftLines.length &&
    baseLines[prefix] === draftLines[prefix]
  ) {
    prefix += 1
  }

  let suffix = 0
  while (
    suffix < baseLines.length - prefix &&
    suffix < draftLines.length - prefix &&
    baseLines[baseLines.length - 1 - suffix] === draftLines[draftLines.length - 1 - suffix]
  ) {
    suffix += 1
  }

  const deletedLines = baseLines.slice(prefix, baseLines.length - suffix)
  const insertedLines = draftLines.slice(prefix, draftLines.length - suffix)
  const lines: SourceEditPreviewLine[] = []
  if (prefix > 0) {
    lines.push({ kind: "context", text: baseLines[prefix - 1] })
  }
  lines.push(...deletedLines.map((text) => ({ kind: "delete" as const, text })))
  lines.push(...insertedLines.map((text) => ({ kind: "insert" as const, text })))
  if (suffix > 0) {
    lines.push({ kind: "context", text: baseLines[baseLines.length - suffix] })
  }

  return {
    changed: true,
    insertions: insertedLines.length,
    deletions: deletedLines.length,
    changedLineCount: insertedLines.length + deletedLines.length,
    lines,
  }
}

function linePrefix(kind: SourceEditPreviewLine["kind"]): string {
  if (kind === "insert") return "+"
  if (kind === "delete") return "-"
  return " "
}

function paragraphTextRanges(paragraphs: string[]): Array<{ start: number; end: number }> {
  let offset = 0
  return paragraphs.map((paragraph) => {
    const start = offset
    const end = start + paragraph.length
    offset = end + 1
    return { start, end }
  })
}
