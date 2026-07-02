import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CandidateDrawer } from "../components/workbench/candidate-drawer"
import type { Candidate } from "../lib/workbench-data"

const candidate: Candidate = {
  id: "candidate-1",
  label: "候选",
  direction: "改写选区，保留证据边界",
  sentences: [{ id: "sentence-1", text: "米拉停在门口。" }],
  usedMemory: ["span-1"],
  avoided: [],
  risk: null,
}

afterEach(() => {
  cleanup()
})

describe("CandidateDrawer", () => {
  it("makes partial sentence acceptance explicit before accepting", () => {
    render(
      <CandidateDrawer
        onClose={vi.fn()}
        onAcceptSentence={vi.fn()}
        candidates={[
          {
            ...candidate,
            sentences: [
              { id: "sentence-1", text: "米拉停在门口。" },
              { id: "sentence-2", text: "她没有越过门槛。" },
            ],
          },
        ]}
      />,
    )

    expect(screen.getByText("选择一句后，只采纳这一句，不会写入整段候选。")).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole("button", { name: "选这一句" })[1])

    expect(screen.getByText("将只采纳：她没有越过门槛。")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "只采纳所选句" })).toBeEnabled()
  })

  it("keeps evidence chips author-facing without raw backend ids", () => {
    render(
      <CandidateDrawer
        onClose={vi.fn()}
        onAcceptSentence={vi.fn()}
        candidates={[
          {
            ...candidate,
            usedMemory: [
              "source_span:a5c3232d-1111-4000-8000-000000000001",
              "review_item:84739bdb-2222-4000-8000-000000000002",
            ],
          },
        ]}
      />,
    )

    expect(screen.getByText("证据段落")).toBeInTheDocument()
    expect(screen.getByText("复核线索")).toBeInTheDocument()
    expect(screen.queryByText(/a5c3232d|84739bdb|source_span|review_item/)).toBeNull()
  })

  it("keeps candidate labels, directions, and risk notes author-facing", () => {
    render(
      <CandidateDrawer
        onClose={vi.fn()}
        onAcceptSentence={vi.fn()}
        candidates={[
          {
            ...candidate,
            label: "后端",
            direction: "revise_candidate",
            risk: {
              level: "high",
              note: "Draft presents risk-context material as if it were canon.",
            },
            avoided: ["Draft presents risk-context material as if it were canon."],
          },
        ]}
      />,
    )

    expect(screen.getByText("修订候选，保留证据边界")).toBeInTheDocument()
    expect(screen.getByText("候选把待确认风险写成了已确认设定。")).toBeInTheDocument()
    expect(
      screen.getAllByText((_, element) =>
        Boolean(element?.textContent?.includes("高风险 · 候选把待确认风险写成了已确认设定。")),
      ).length,
    ).toBeGreaterThan(0)
    expect(
      screen.queryByText(/后端|revise_candidate|Draft presents|risk-context|canon/),
    ).toBeNull()
  })

  it("shows stale source recovery and prevents accepting the old candidate", () => {
    const onRefreshSource = vi.fn()
    const onAcceptSentence = vi.fn()

    render(
      <CandidateDrawer
        onClose={vi.fn()}
        onAcceptSentence={onAcceptSentence}
        candidates={[candidate]}
        staleSourceMessage="正文版本已更新。请先刷新正文，再重新生成候选；系统没有写入正文或记忆。"
        onRefreshSource={onRefreshSource}
      />,
    )

    expect(screen.getByText("正文版本已更新")).toBeInTheDocument()
    expect(screen.getByText(/重新生成候选/)).toBeInTheDocument()
    expect(screen.queryByText(/SourceVersion|Memory/)).toBeNull()

    fireEvent.click(screen.getByRole("button", { name: "选这一句" }))

    expect(screen.getByRole("button", { name: "刷新正文" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "只采纳所选句" })).toBeDisabled()

    fireEvent.click(screen.getByRole("button", { name: "刷新正文" }))

    expect(onRefreshSource).toHaveBeenCalledTimes(1)
    expect(onAcceptSentence).not.toHaveBeenCalled()
  })

  it("disables candidate actions after the author rejects the candidate", () => {
    render(
      <CandidateDrawer
        onClose={vi.fn()}
        onAcceptSentence={vi.fn()}
        onRejectCandidate={vi.fn()}
        onReviseSentence={vi.fn()}
        candidates={[candidate]}
        operationStatus="候选已退回，不会写入正文或记忆。"
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "选这一句" }))

    expect(screen.getByRole("button", { name: "只采纳所选句" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "保存为修订候选" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "退回候选" })).toBeDisabled()
  })
})
