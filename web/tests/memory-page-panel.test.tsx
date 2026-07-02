import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryPagePanel } from "../components/workbench/memory-page-panel"

afterEach(() => {
  cleanup()
})

describe("MemoryPagePanel", () => {
  it("opens as a MemoryPage detail surface and selects the first page when detail is empty", async () => {
    const onSelect = vi.fn()

    render(
      <MemoryPagePanel
        pages={[
          {
            id: "page-1",
            page_type: "character",
            target_ref: { type: "character", id: "mira" },
            title: "Mira",
            canon_status: "current",
            memory_depth: "scene",
            source_refs: [{ type: "source_span", id: "span-1" }],
            open_thread_count: 0,
            contradiction_count: 0,
          },
        ]}
        detail={null}
        graphEdges={[]}
        loading={false}
        error={null}
        detailLoading={false}
        detailError={null}
        graphEdgesLoading={false}
        graphEdgesError={null}
        graphEdgeSearch=""
        graphEdgeStatus=""
        onSelect={onSelect}
        onRefresh={vi.fn()}
        onGraphEdgeSearchChange={vi.fn()}
        onGraphEdgeStatusChange={vi.fn()}
        onClose={vi.fn()}
      />,
    )

    expect(screen.getByRole("heading", { name: "记忆页详情" })).toBeVisible()
    expect(screen.getByTestId("memory-page-detail")).toHaveTextContent("正在打开第一条记忆页详情")
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith("page-1"))
  })

  it("surfaces GraphProjection edges without replacing MemoryPage detail", () => {
    const onGraphEdgeSearchChange = vi.fn()
    const onGraphEdgeStatusChange = vi.fn()

    render(
      <MemoryPagePanel
        pages={[
          {
            id: "page-1",
            page_type: "character",
            target_ref: { type: "character", id: "mira" },
            title: "Mira",
            canon_status: "current",
            memory_depth: "scene",
            source_refs: [{ type: "source_span", id: "span-1" }],
            open_thread_count: 0,
            contradiction_count: 0,
          },
        ]}
        detail={{
          id: "page-1",
          page_type: "character",
          target_ref: { type: "character", id: "mira" },
          title: "Mira",
          current_canon: { facts: [{ predicate: "owns", object: "lantern-map" }] },
          appearance_log: [],
          event_log: [],
          relationships: [],
          knowledge_state: [
            {
              character_id: "00000000-0000-4000-8000-0000000000dd",
              knows_ref: { type: "secret", id: "harbor-code", label: "Harbor Code" },
              learned_in_scene_id: null,
              evidence_span_id: "span-3",
              certainty: "known",
              hidden_from: [],
              status: "active",
            },
          ],
          open_threads: [],
          contradictions: [
            {
              type: "review_item_resolution",
              review_item_id: "00000000-0000-4000-8000-0000000000bb",
              resolution: "accepted_as_change",
              requires: "memory_page_rewrite",
            },
            {
              type: "memory_writeback_decision",
              source_delta_id: "00000000-0000-4000-8000-0000000000cc",
              decision: "correct",
            },
          ],
          source_refs: [{ type: "source_span", id: "span-1" }],
          canon_status: "current",
          memory_depth: "scene",
        }}
        graphEdges={[
          {
            id: "edge-1",
            run_id: "run-1",
            source_ref: { type: "fact_assertion", id: "fact-1" },
            subject_ref: { type: "character", id: "mira", label: "Mira" },
            relation: "present_at",
            target_ref: {
              type: "scene",
              id: "00000000-0000-4000-8000-0000000000aa",
              label: "scene:00000000-0000-4000-8000-0000000000aa",
            },
            edge_status: "disputed",
            evidence_refs: [{ type: "source_span", id: "span-1" }],
            created_at: "2026-06-04T00:00:00Z",
          },
          {
            id: "edge-2",
            run_id: "run-1",
            source_ref: { type: "fact_assertion", id: "fact-2" },
            subject_ref: { type: "event", id: "event-1", label: "门锁试探" },
            relation: "occurred_at",
            target_ref: { type: "location", id: "west-archive", label: "West Archive" },
            edge_status: "canon",
            evidence_refs: [{ type: "source_span", id: "span-2" }],
            created_at: "2026-06-04T00:00:00Z",
          },
        ]}
        loading={false}
        error={null}
        detailLoading={false}
        detailError={null}
        graphEdgesLoading={false}
        graphEdgesError={null}
        graphEdgeSearch=""
        graphEdgeStatus=""
        onSelect={vi.fn()}
        onRefresh={vi.fn()}
        onGraphEdgeSearchChange={onGraphEdgeSearchChange}
        onGraphEdgeStatusChange={onGraphEdgeStatusChange}
        onClose={vi.fn()}
      />,
    )

    expect(screen.getByTestId("graph-projection-inspector")).toBeVisible()
    expect(screen.getByText("Mira · 角色")).toBeVisible()
    expect(screen.getByText(/角色 · 场景 · 证据 1 · 线索 0/)).toBeVisible()
    expect(screen.getByText("出现于 → 场景")).toBeVisible()
    expect(screen.getByText("发生于 → West Archive · 地点")).toBeVisible()
    expect(screen.getAllByText(/证据段落 1/)).toHaveLength(3)
    const memoryDetail = screen.getByTestId("memory-page-detail")
    expect(within(memoryDetail).getByText("记忆页详情")).toBeVisible()
    expect(screen.getByText("设定 · 持有 · Lantern Map")).toBeVisible()
    expect(screen.getByText("Harbor Code · 秘密 · 已知")).toBeVisible()
    expect(screen.getByText("复核处理 · 按正文变更接受 · 需要重写记忆页")).toBeVisible()
    expect(screen.getByText("记忆回写处理 · 作者修正")).toBeVisible()
    expect(screen.queryByText(/GraphProjection|MemoryPage Detail|fact_assertion|source_span/)).toBeNull()
    expect(screen.queryByText(/present at|occurred at|present_at|occurred_at|scene:/)).toBeNull()
    expect(screen.queryByText(/review item resolution|memory writeback decision|review_item_resolution|memory_writeback_decision/)).toBeNull()
    expect(screen.queryByText(/00000000|span-1|span-2/)).toBeNull()
    expect(screen.queryByText(/character|current|standard|scene|none/)).toBeNull()
    expect(screen.queryByText(/"predicate"/)).toBeNull()

    fireEvent.change(screen.getByLabelText("搜索关系图谱"), {
      target: { value: "archive" },
    })
    fireEvent.change(screen.getByLabelText("关系状态"), {
      target: { value: "disputed" },
    })

    expect(onGraphEdgeSearchChange).toHaveBeenCalledWith("archive")
    expect(onGraphEdgeStatusChange).toHaveBeenCalledWith("disputed")
  })

  it("offers backend-backed open-thread operations when a handler is provided", () => {
    const onOperateThread = vi.fn()

    render(
      <MemoryPagePanel
        pages={[
          {
            id: "page-1",
            page_type: "character",
            target_ref: { type: "character", id: "mira" },
            title: "Mira",
            canon_status: "current",
            memory_depth: "scene",
            source_refs: [{ type: "source_span", id: "span-1" }],
            open_thread_count: 1,
            contradiction_count: 0,
          },
        ]}
        detail={{
          id: "page-1",
          page_type: "character",
          target_ref: { type: "character", id: "mira" },
          title: "Mira",
          current_canon: { facts: [] },
          appearance_log: [],
          event_log: [],
          relationships: [],
          knowledge_state: [],
          open_threads: [
            {
              id: "map-origin",
              summary: "地图来源还没有解释。",
              risk_level: "low",
              status: "open",
              source_span_ids: ["span-1"],
            },
          ],
          contradictions: [],
          source_refs: [{ type: "source_span", id: "span-1" }],
          canon_status: "current",
          memory_depth: "scene",
        }}
        graphEdges={[]}
        loading={false}
        error={null}
        detailLoading={false}
        detailError={null}
        graphEdgesLoading={false}
        graphEdgesError={null}
        graphEdgeSearch=""
        graphEdgeStatus=""
        onSelect={vi.fn()}
        onRefresh={vi.fn()}
        onGraphEdgeSearchChange={vi.fn()}
        onGraphEdgeStatusChange={vi.fn()}
        onOperateThread={onOperateThread}
        operatingThreadId={null}
        operationError={null}
        onClose={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "回收" }))

    expect(onOperateThread).toHaveBeenCalledWith(
      "map-origin",
      "pays_off",
      "地图来源还没有解释。",
    )
    expect(screen.queryByText(/open_threads|source_span_ids|map-origin/)).toBeNull()
  })
})
