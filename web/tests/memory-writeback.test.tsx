import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryWriteback } from "../components/workbench/memory-writeback"
import type { WorkbenchWritebackState } from "../lib/workbench-api"

const state: WorkbenchWritebackState = {
  job: {
    id: "job-1",
    job_type: "run_memory_writeback",
    status: "succeeded",
    payload: {},
    attempt_count: 1,
    max_attempts: 5,
    run_after: null,
    leased_by: null,
    leased_until: null,
    last_error: null,
  },
  preview: {
    source_delta_id: "delta-1",
    source_delta_status: "memory_writeback_completed",
    source_delta: {},
    job: null,
    source_spans: [],
    evidence_log_entries: [],
    fact_assertions: [],
    review_items: [
      {
        id: "review-1",
        review_type: "knowledge_conflict",
        severity: "medium",
        status: "open",
        summary: "钥匙来源仍未确认。",
        affected_refs: {},
        new_evidence: {},
        existing_evidence: {},
        suggested_actions: [],
        default_action: "ask_author",
        resolution: null,
        side_effects: {},
      },
    ],
    memory_pages: [],
    graph_edges: [],
  },
  reviewItems: [],
}

afterEach(() => {
  cleanup()
})

describe("MemoryWriteback", () => {
  it("does not render demo writeback items in backend mode without an acceptance", () => {
    render(
      <MemoryWriteback
        onClose={vi.fn()}
        onUndoAll={vi.fn()}
        demoMode={false}
      />,
    )

    expect(screen.getByText("等待后端回写状态")).toBeVisible()
    expect(screen.queryByText("Mira 注意到 Kestrel 的迟疑。")).toBeNull()
  })

  it("persists decisions for non-fact preview items", () => {
    const onDecision = vi.fn().mockResolvedValue(undefined)

    render(
      <MemoryWriteback
        onClose={vi.fn()}
        onUndoAll={vi.fn()}
        acceptance={{
          accepted_fragment_id: "fragment-1",
          source_delta_id: "delta-1",
          new_version_id: "version-2",
          memory_writeback_job_id: "job-1",
        }}
        state={state}
        onDecision={onDecision}
      />,
    )

    const reviewItem = screen.getByTestId("writeback-preview-review_item-review-1")
    fireEvent.click(within(reviewItem).getByRole("button", { name: /确认 复核项/ }))

    expect(onDecision).toHaveBeenCalledWith(
      { type: "review_item", id: "review-1" },
      "accept",
    )
  })

  it("submits authored correction details for non-fact preview items", () => {
    const onDecision = vi.fn().mockResolvedValue(undefined)

    render(
      <MemoryWriteback
        onClose={vi.fn()}
        onUndoAll={vi.fn()}
        acceptance={{
          accepted_fragment_id: "fragment-1",
          source_delta_id: "delta-1",
          new_version_id: "version-2",
          memory_writeback_job_id: "job-1",
        }}
        state={state}
        onDecision={onDecision}
      />,
    )

    const reviewItem = screen.getByTestId("writeback-preview-review_item-review-1")
    fireEvent.click(within(reviewItem).getByRole("button", { name: /需改 复核项/ }))
    fireEvent.change(within(reviewItem).getByLabelText("修正说明 复核项"), {
      target: { value: "钥匙来源改成页边批注。" },
    })
    fireEvent.change(within(reviewItem).getByLabelText("修正值 复核项"), {
      target: { value: "页边批注说明不要相信第二把钥匙。" },
    })
    fireEvent.change(within(reviewItem).getByLabelText("替代正文变更 复核项"), {
      target: { value: "delta-2" },
    })
    fireEvent.click(within(reviewItem).getByRole("button", { name: /提交修正 复核项/ }))

    expect(onDecision).toHaveBeenCalledWith(
      { type: "review_item", id: "review-1" },
      "correct",
      {
        authorNote: "钥匙来源改成页边批注。",
        correction: {
          status: "author_corrected",
          note: "钥匙来源改成页边批注。",
          corrected_text: "页边批注说明不要相信第二把钥匙。",
          replacement_refs: [{ type: "source_delta", id: "delta-2" }],
        },
        replacementRefs: [{ type: "source_delta", id: "delta-2" }],
      },
    )
  })

  it("renders backend writeback evidence in author-facing language", () => {
    render(
      <MemoryWriteback
        onClose={vi.fn()}
        onUndoAll={vi.fn()}
        acceptance={{
          accepted_fragment_id: "fragment-1",
          source_delta_id: "00000000-0000-4000-8000-000000000001",
          new_version_id: "version-2",
          memory_writeback_job_id: "00000000-0000-4000-8000-000000000002",
        }}
        state={{
          ...state,
          preview: {
            ...state.preview,
            source_spans: [{ id: "span-1", text_preview: "米拉停在西档案室门口。" }],
            fact_assertions: [
              {
                id: "fact-1",
                subject_ref: { type: "character", id: "mira" },
                predicate: "owns",
                object_ref: { type: "object", id: "lantern-map" },
              },
            ],
            memory_pages: [{ id: "mira", title: "mira", canon_status: "current" }],
          },
        }}
        onDecision={vi.fn()}
      />,
    )

    expect(screen.getByText("正文变更已写入，回写状态由系统读取；处理完成后会显示证据链。")).toBeVisible()
    expect(screen.getByText("证据段落")).toBeVisible()
    expect(screen.getByText("事实")).toBeVisible()
    expect(screen.getByText("复核")).toBeVisible()
    expect(screen.getByText("记忆页 ·")).toBeVisible()
    expect(screen.getByText("Mira · 角色 · 持有 · Lantern Map · 物件")).toBeVisible()
    expect(screen.queryByText(/SourceDelta|MemoryPage|SourceSpan|ReviewItem|Fact/)).toBeNull()
    expect(screen.queryByText(/00000000-0000-4000-8000-00000000000/)).toBeNull()
    expect(screen.queryByText(/正文变更 · 00000000|证据记录|evidence/i)).toBeNull()
  })

  it("shows pending evidence-chain copy instead of empty zero counters while writeback is still settling", () => {
    render(
      <MemoryWriteback
        onClose={vi.fn()}
        onUndoAll={vi.fn()}
        acceptance={{
          accepted_fragment_id: "fragment-1",
          source_delta_id: "delta-1",
          new_version_id: "version-2",
          memory_writeback_job_id: "job-1",
        }}
        state={{
          ...state,
          job: {
            ...state.job,
            status: "running",
          },
          preview: {
            ...state.preview,
            source_spans: [],
            fact_assertions: [],
            review_items: [],
            memory_pages: [],
            graph_edges: [],
          },
        }}
        onDecision={vi.fn()}
      />,
    )

    expect(screen.getByText("证据链整理中")).toBeVisible()
    expect(screen.queryByText(/^0$/)).toBeNull()
  })
})
