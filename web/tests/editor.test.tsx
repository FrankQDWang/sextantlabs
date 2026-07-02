import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { Editor } from "../components/workbench/editor"

afterEach(() => {
  vi.restoreAllMocks()
  cleanup()
})

describe("Editor", () => {
  it("reports a non-empty range when the browser selection uses paragraph element containers", () => {
    const onSelect = vi.fn()
    Object.defineProperty(Range.prototype, "getBoundingClientRect", {
      configurable: true,
      value: vi.fn(() => ({
        bottom: 120,
        height: 20,
        left: 24,
        right: 124,
        top: 100,
        width: 100,
        x: 24,
        y: 100,
        toJSON: () => ({}),
      })),
    })

    render(
      <Editor
        onSelect={onSelect}
        onParagraphRewrite={vi.fn()}
        demoHighlight={false}
        acceptedSentence={null}
        text={"第一段文字\n第二段文字"}
        title="西档案室"
        chapter="v2"
        sourceError={null}
      />,
    )

    const paragraph = document.querySelector("[data-editor-para='0']")
    if (!paragraph) {
      throw new Error("Expected the first editor paragraph to render.")
    }
    const range = document.createRange()
    range.selectNodeContents(paragraph)
    const selection = window.getSelection()
    selection?.removeAllRanges()
    selection?.addRange(range)
    fireEvent.mouseUp(paragraph)

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "第一段文字",
        range: { start: 0, end: 5 },
      }),
    )
  })

  it("lets the author edit the current source text and save it through a parent action", () => {
    const onSourceEditStart = vi.fn()
    const onSourceEditChange = vi.fn()
    const onSourceEditSave = vi.fn()

    render(
      <Editor
        onSelect={vi.fn()}
        onParagraphRewrite={vi.fn()}
        demoHighlight={false}
        acceptedSentence={null}
        text={"第一行\n第二行"}
        title="西档案室"
        chapter="v2"
        sourceError={null}
        isSourceEditing={false}
        sourceEditText="第一行\n第二行"
        sourceEditPending={false}
        sourceEditStatus={null}
        sourceEditError={null}
        onSourceEditStart={onSourceEditStart}
        onSourceEditChange={onSourceEditChange}
        onSourceEditCancel={vi.fn()}
        onSourceEditSave={onSourceEditSave}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "编辑当前正文版本" }))

    expect(onSourceEditStart).toHaveBeenCalled()
  })

  it("renders controlled source editing controls", () => {
    const onSourceEditChange = vi.fn()
    const onSourceEditSave = vi.fn()
    const onSourceEditRefresh = vi.fn()
    const onSourceEditMergeRejectedDraft = vi.fn()
    const onSourceEditApplyRejectedDraft = vi.fn()
    const onSourceEditDismissRejectedDraft = vi.fn()

    const props = {
      onSelect: vi.fn(),
      onParagraphRewrite: vi.fn(),
      demoHighlight: false,
      acceptedSentence: null,
      text: "第一行\n第二行",
      title: "西档案室",
      chapter: "v2",
      sourceError: null,
      isSourceEditing: true,
      sourceEditText: "第一行\n第二行",
      sourceEditPending: false,
      sourceEditStatus: "source edit ready",
      sourceEditError: null,
      sourceEditRejectedDraftText: null,
      onSourceEditStart: vi.fn(),
      onSourceEditChange,
      onSourceEditCancel: vi.fn(),
      onSourceEditSave,
      onSourceEditRefresh,
      onSourceEditMergeRejectedDraft,
      onSourceEditApplyRejectedDraft,
      onSourceEditDismissRejectedDraft,
    }
    const { rerender } = render(
      <Editor
        {...props}
      />,
    )

    fireEvent.change(screen.getByLabelText("编辑当前正文"), {
      target: { value: "第一行\n第二行改" },
    })
    rerender(<Editor {...props} sourceEditText={"第一行\n第二行改"} />)
    expect(screen.getByText("编辑预览 · +1 / -1")).toBeInTheDocument()
    expect(screen.getByText("+ 第二行改")).toBeInTheDocument()
    expect(screen.getByText("- 第二行")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "保存为正文变更" }))
    fireEvent.click(screen.getByRole("button", { name: "刷新最新正文版本" }))

    expect(onSourceEditChange).toHaveBeenCalledWith("第一行\n第二行改")
    expect(onSourceEditSave).toHaveBeenCalled()
    expect(onSourceEditRefresh).toHaveBeenCalled()
    expect(screen.getByText("source edit ready")).toBeInTheDocument()
  })

  it("surfaces a stale source edit draft for author merge assistance", () => {
    const onSourceEditMergeRejectedDraft = vi.fn()
    const onSourceEditApplyRejectedDraft = vi.fn()
    const onSourceEditDismissRejectedDraft = vi.fn()

    render(
      <Editor
        onSelect={vi.fn()}
        onParagraphRewrite={vi.fn()}
        demoHighlight={false}
        acceptedSentence={null}
        text={"最新版第一行\n并发新增行"}
        title="西档案室"
        chapter="v3"
        sourceError={null}
        isSourceEditing={true}
        sourceEditText={"最新版第一行\n并发新增行"}
        sourceEditPending={false}
        sourceEditStatus="已刷新最新正文版本，请重新编辑后保存。"
        sourceEditError={null}
        sourceEditRejectedDraftText="作者原来的未保存草稿"
        onSourceEditStart={vi.fn()}
        onSourceEditChange={vi.fn()}
        onSourceEditCancel={vi.fn()}
        onSourceEditSave={vi.fn()}
        onSourceEditRefresh={vi.fn()}
        onSourceEditMergeRejectedDraft={onSourceEditMergeRejectedDraft}
        onSourceEditApplyRejectedDraft={onSourceEditApplyRejectedDraft}
        onSourceEditDismissRejectedDraft={onSourceEditDismissRejectedDraft}
      />,
    )

    expect(screen.getByText("草稿冲突")).toBeInTheDocument()
    expect(screen.getByText("作者原来的未保存草稿")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "合并被拒绝的草稿" }))
    fireEvent.click(screen.getByRole("button", { name: "套用被拒绝的草稿" }))
    fireEvent.click(screen.getByRole("button", { name: "丢弃被拒绝的草稿" }))

    expect(onSourceEditMergeRejectedDraft).toHaveBeenCalled()
    expect(onSourceEditApplyRejectedDraft).toHaveBeenCalled()
    expect(onSourceEditDismissRejectedDraft).toHaveBeenCalled()
  })
})
