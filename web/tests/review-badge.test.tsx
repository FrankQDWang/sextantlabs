import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ReviewBadge } from "../components/workbench/review-badge"
import type { ReviewItem } from "../lib/workbench-data"
import type { ReviewItemDetailResponse } from "../src/generated/sextant-api"

const item: ReviewItem = {
  id: "review-1",
  text: "钥匙来源仍未确认，暂不能写成 Mira 已经知道。",
  hint: "knowledge_conflict · medium",
}

const detail: ReviewItemDetailResponse = {
  id: "review-1",
  review_type: "knowledge_conflict",
  severity: "medium",
  status: "open",
  summary: "钥匙来源仍未确认，暂不能写成 Mira 已经知道。",
  affected_refs: {},
  new_evidence: {},
  existing_evidence: {},
  suggested_actions: [{ resolution: "mark_intentional" }],
  default_action: "ask_author",
  resolution: null,
  side_effects: {},
}

afterEach(() => {
  cleanup()
})

describe("ReviewBadge", () => {
  it("lets the author choose a formal ReviewItem resolution", () => {
    const onResolve = vi.fn()

    render(
      <ReviewBadge
        items={[item]}
        open
        onToggle={vi.fn()}
        detail={detail}
        onResolve={onResolve}
      />,
    )

    expect(screen.queryByLabelText(/Review| ID/)).toBeNull()

    fireEvent.change(screen.getByLabelText("复核处理方式"), {
      target: { value: "mark_intentional" },
    })
    expect(screen.queryByLabelText(/复核替代.*编号/)).toBeNull()
    expect(screen.queryByLabelText("别名目标实体编号")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "确认处理" }))

    expect(onResolve).toHaveBeenCalledWith("review-1", "mark_intentional", {
      authorNote: null,
      replacementRefs: [],
    })
  })

  it("submits replacement refs and shows resolved side effects", () => {
    const onResolve = vi.fn()

    render(
      <ReviewBadge
        items={[item]}
        open
        onToggle={vi.fn()}
        detail={{
          ...detail,
          review_type: "event_merge_conflict",
          suggested_actions: [{ resolution: "merge" }],
          default_action: "merge",
          side_effects: {
            memory_pages: "marked_stale",
            memory_pages_marked_stale: 1,
            graph_projection: "marked_stale",
            replacement_refs: [{ type: "source_delta", id: "delta-2" }],
            fact_assertions_updated: 2,
          },
        }}
        onResolve={onResolve}
      />,
    )

    fireEvent.change(screen.getByLabelText("复核处理说明"), {
      target: { value: "作者确认新文本替代旧设定。" },
    })
    fireEvent.change(screen.getByLabelText("复核替代正文变更"), {
      target: { value: "delta-2" },
    })
    expect(screen.queryByLabelText("复核替代正文变更编号")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "确认处理" }))

    expect(onResolve).toHaveBeenCalledWith("review-1", "merge", {
      authorNote: "作者确认新文本替代旧设定。",
      replacementRefs: [{ type: "source_delta", id: "delta-2" }],
    })
    expect(screen.getByText("影响")).toBeVisible()
    expect(screen.getByText("记忆页 · 已标为需重写")).toBeVisible()
    expect(screen.getByText("替代证据 · 正文变更 Delta 2")).toBeVisible()
    expect(screen.getByText("事实 · 2 项已更新")).toBeVisible()
    expect(screen.queryByText(/fact assertions updated|fact_assertions_updated|Review/)).toBeNull()
  })

  it("renders alias correction side effects without backend debug keys", () => {
    render(
      <ReviewBadge
        items={[item]}
        open
        onToggle={vi.fn()}
        detail={{
          ...detail,
          review_type: "alias_conflict",
          status: "resolved",
          side_effects: {
            alias_correction: {
              old_entity_id: "entity-old",
              alias_record_id: "alias-record",
              target_entity: { type: "character", id: "entity-target", label: "Mira" },
              target_entity_id: "entity-target",
              fact_ids: ["fact-1", "fact-2"],
              memory_page_ids: ["page-1"],
              graph_edges_created: 2,
              context_pack_readiness_ids: ["ready-1"],
            },
            old_entity_id: "83061e33-1111-4000-8000-000000000001",
            alias_record_id: "bc0f788d-2222-4000-8000-000000000002",
            target_entity_id: "f480669a-3333-4000-8000-000000000003",
            graph_projection_run_id: "fafaebcf-4444-4000-8000-000000000004",
            alias_boundary_correction: "applied",
            valid_from_scene_id: "11111111-1111-4000-8000-000000000001",
            valid_until_scene_id: "22222222-2222-4000-8000-000000000002",
            mentions_updated: 1,
            context_pack_readiness: "marked_stale",
            author_note: "验收：Starling 与 Mira 指向同一角色。",
            promotion: "none",
            review_queue: "open",
            replacement_refs: [],
          },
        }}
      />,
    )

    expect(screen.getByText("影响")).toBeVisible()
    expect(screen.getByText(/别名修正/)).toBeVisible()
    expect(screen.getByText(/目标实体 Mira · 角色/)).toBeVisible()
    expect(screen.getByText(/事实 2 项已更新/)).toBeVisible()
    expect(screen.getByText("别名边界 · 已应用")).toBeVisible()
    expect(screen.getByText("起始场景 · 已记录")).toBeVisible()
    expect(screen.getByText("结束场景 · 已记录")).toBeVisible()
    expect(screen.getByText("提及 · 1 项已更新")).toBeVisible()
    expect(screen.getByText("上下文依据 · 已标为需重写")).toBeVisible()
    expect(screen.getByText("作者说明 · 验收：Starling 与 Mira 指向同一角色。")).toBeVisible()
    expect(screen.getByText("设定确认 · 无变更")).toBeVisible()
    expect(screen.getByText("复核队列 · 待处理")).toBeVisible()
    expect(screen.queryByText("替代证据 · 无")).toBeNull()
    expect(
      screen.queryByText(
        /old entity id|target entity|fact ids|memory page ids|graph edges created|context pack readiness ids|valid from scene id|valid until scene id|old_entity_id|target_entity_id|target_entity|fact_ids|memory_page_ids|graph_edges_created|context_pack_readiness_ids|graph_projection_run_id|valid_from_scene_id|valid_until_scene_id|mentions updated|context pack readiness|author note|Promotion|Unchanged|review queue|83061e33|bc0f788d|f480669a|fafaebcf|11111111|22222222/,
      ),
    ).toBeNull()
  })

  it("renders ReviewItem source context without exposing raw evidence ids", () => {
    render(
      <ReviewBadge
        items={[item]}
        open
        onToggle={vi.fn()}
        detail={{
          ...detail,
          review_type: "alias_conflict",
          summary: "Starling 应合并为 Mira。",
          affected_refs: {
            memory_page_id: "00000000-0000-4000-8000-000000000001",
            fact_ids: [
              "00000000-0000-4000-8000-000000000002",
              "00000000-0000-4000-8000-000000000003",
            ],
          },
          new_evidence: {
            alias_text: "Starling",
            source_span_ids: ["00000000-0000-4000-8000-000000000004"],
          },
          existing_evidence: {
            alias_text: "Starling",
            source_span_ids: ["00000000-0000-4000-8000-000000000005"],
          },
        }}
      />,
    )

    expect(screen.getByText("证据来源")).toBeVisible()
    expect(screen.getByText("新证据 · 证据段落 1")).toBeVisible()
    expect(screen.getByText("新证据 · 别名 Starling")).toBeVisible()
    expect(screen.getByText("已有依据 · 证据段落 1")).toBeVisible()
    expect(screen.getByText("已有依据 · 别名 Starling")).toBeVisible()
    expect(screen.getByText("关联对象 · 记忆页已记录")).toBeVisible()
    expect(screen.getByText("关联对象 · 事实 2 项")).toBeVisible()
    expect(
      screen.queryByText(
        /source_span_ids|memory_page_id|fact_ids|00000000|source_span|SourceSpan/,
      ),
    ).toBeNull()
  })

  it("lets the author choose replacement SourceDelta evidence from backend results", () => {
    const onResolve = vi.fn()

    render(
      <ReviewBadge
        items={[item]}
        open
        onToggle={vi.fn()}
        detail={{
          ...detail,
          review_type: "event_merge_conflict",
          suggested_actions: [{ resolution: "merge" }],
          default_action: "merge",
        }}
        sourceDeltaOptions={[
          {
            id: "delta-1",
            source_id: "source-1",
            previous_version_id: "version-1",
            new_version_id: "version-2",
            accepted_fragment_id: "fragment-1",
            delta_kind: "replace",
            status: "memory_writeback_completed",
            range_start: 0,
            range_end: 12,
            submitted_text_preview: "她没有说出秘密，只把注意力放回门锁。",
            created_at: "2026-06-11T08:00:00Z",
          },
        ]}
        onResolve={onResolve}
      />,
    )

    fireEvent.change(screen.getByLabelText("替代正文变更"), {
      target: { value: "delta-1" },
    })
    fireEvent.change(screen.getByLabelText("复核处理说明"), {
      target: { value: "用刚写入的正文替代旧冲突。" },
    })
    fireEvent.click(screen.getByRole("button", { name: "确认处理" }))

    expect(onResolve).toHaveBeenCalledWith("review-1", "merge", {
      authorNote: "用刚写入的正文替代旧冲突。",
      replacementRefs: [{ type: "source_delta", id: "delta-1" }],
    })
  })

  it("requires authored note and replacement SourceDelta refs for split and merge", () => {
    const onResolve = vi.fn()

    render(
      <ReviewBadge
        items={[item]}
        open
        onToggle={vi.fn()}
        detail={{
          ...detail,
          review_type: "event_merge_conflict",
          suggested_actions: [{ resolution: "merge" }],
          default_action: "merge",
        }}
        onResolve={onResolve}
      />,
    )

    const submit = screen.getByRole("button", { name: "确认处理" })
    expect(screen.getByText("需要处理说明和替代正文变更。")).toBeVisible()
    expect(submit).toBeDisabled()

    fireEvent.change(screen.getByLabelText("复核处理说明"), {
      target: { value: "合并为一次事件。" },
    })
    expect(submit).toBeDisabled()

    fireEvent.change(screen.getByLabelText("复核替代正文变更"), {
      target: { value: "delta-merge-1" },
    })
    fireEvent.click(submit)

    expect(onResolve).toHaveBeenCalledWith("review-1", "merge", {
      authorNote: "合并为一次事件。",
      replacementRefs: [{ type: "source_delta", id: "delta-merge-1" }],
    })
  })

  it("allows supersede to submit a replacement ReviewItem ref", () => {
    const onResolve = vi.fn()

    render(
      <ReviewBadge
        items={[item]}
        open
        onToggle={vi.fn()}
        detail={{
          ...detail,
          suggested_actions: [{ resolution: "supersede" }],
          default_action: "supersede",
        }}
        onResolve={onResolve}
      />,
    )

    const submit = screen.getByRole("button", { name: "确认处理" })
    expect(screen.getByText("需要处理说明和替代证据。")).toBeVisible()
    expect(submit).toBeDisabled()

    fireEvent.change(screen.getByLabelText("替代证据类型"), {
      target: { value: "review_item" },
    })
    fireEvent.change(screen.getByLabelText("复核替代复核项"), {
      target: { value: "review-2" },
    })
    fireEvent.change(screen.getByLabelText("复核处理说明"), {
      target: { value: "新的复核项已经替代旧风险。" },
    })
    fireEvent.click(submit)

    expect(onResolve).toHaveBeenCalledWith("review-1", "supersede", {
      authorNote: "新的复核项已经替代旧风险。",
      replacementRefs: [{ type: "review_item", id: "review-2" }],
    })
  })

  it("uses backend entity options for alias correction", () => {
    const onResolve = vi.fn()

    render(
      <ReviewBadge
        items={[item]}
        open
        onToggle={vi.fn()}
        detail={{
          ...detail,
          review_type: "alias_conflict",
          affected_refs: { alias_record_id: "alias-1", target_entity_id: "entity-1" },
          suggested_actions: [{ resolution: "accepted_as_change" }],
        }}
        entityOptions={[
          {
            id: "entity-1",
            entity_type: "character",
            display_name: "Mira",
            canonical_status: "provisional",
            cast_tier: "unknown",
            first_seen_scene_id: null,
          },
          {
            id: "entity-2",
            entity_type: "character",
            display_name: "Myra",
            canonical_status: "provisional",
            cast_tier: "unknown",
            first_seen_scene_id: null,
          },
        ]}
        onResolve={onResolve}
      />,
    )

    fireEvent.change(screen.getByLabelText("选择目标角色"), {
      target: { value: "entity-2" },
    })
    expect(screen.queryByLabelText("别名目标实体编号")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "确认处理" }))

    expect(onResolve).toHaveBeenCalledWith("review-1", "accepted_as_change", {
      authorNote: null,
      replacementRefs: [],
      correction: {
        alias_record_id: "alias-1",
        target_entity_id: "entity-2",
      },
    })
    expect(screen.queryByText(/Unknown/)).toBeNull()
  })

  it("submits disguise alias boundary corrections from review detail", () => {
    const onResolve = vi.fn()

    render(
      <ReviewBadge
        items={[item]}
        open
        onToggle={vi.fn()}
        detail={{
          ...detail,
          review_type: "alias_conflict",
          affected_refs: {
            alias_record_id: "alias-1",
            target_entity_id: "entity-1",
            alias_scope: "disguise_arc",
            valid_from_scene_id: "scene-start",
            valid_until_scene_id: "scene-end",
          },
          suggested_actions: [{ resolution: "accepted_as_change" }],
        }}
        entityOptions={[
          {
            id: "entity-1",
            entity_type: "character",
            display_name: "Mira",
            canonical_status: "provisional",
            cast_tier: "unknown",
            first_seen_scene_id: null,
          },
        ]}
        sceneOptions={[
          {
            id: "scene-opening",
            source_id: "source-1",
            version_id: "version-1",
            chapter_id: "chapter-1",
            chapter_index: 0,
            chapter_title: "The Harbor",
            scene_index: 0,
            position_label: "Chapter 1 / Scene 1",
            story_time: "Night 1",
            scene_summary: "Mira enters the harbor.",
            pov_character_id: null,
            pov_mode: null,
          },
          {
            id: "scene-end",
            source_id: "source-1",
            version_id: "version-1",
            chapter_id: "chapter-1",
            chapter_index: 0,
            chapter_title: "The Harbor",
            scene_index: 1,
            position_label: "Chapter 1 / Scene 2",
            story_time: "Night 2",
            scene_summary: "Mira reaches the archive.",
            pov_character_id: null,
            pov_mode: null,
          },
        ]}
        onResolve={onResolve}
      />,
    )

    const startSceneSelect = screen.getByLabelText("起始场景")
    const endSceneSelect = screen.getByLabelText("结束场景")
    expect(
      within(startSceneSelect).getByRole("option", {
        name: "Chapter 1 / Scene 1 · Night 1",
      }),
    ).toBeInTheDocument()
    expect(
      within(startSceneSelect).queryByRole("option", {
        name: "Chapter 1 / Scene 1 · Night 1 · 终点",
      }),
    ).not.toBeInTheDocument()
    expect(
      within(endSceneSelect).getByRole("option", {
        name: "Chapter 1 / Scene 1 · Night 1 · 终点",
      }),
    ).toBeInTheDocument()
    fireEvent.change(startSceneSelect, {
      target: { value: "scene-opening" },
    })
    fireEvent.change(endSceneSelect, {
      target: { value: "" },
    })
    fireEvent.click(screen.getByLabelText("应用到同名伪装弧"))
    fireEvent.click(screen.getByRole("button", { name: "确认处理" }))

    expect(onResolve).toHaveBeenCalledWith("review-1", "accepted_as_change", {
      authorNote: null,
      replacementRefs: [],
      correction: {
        alias_record_id: "alias-1",
        target_entity_id: "entity-1",
        valid_from_scene_id: "scene-opening",
        valid_until_scene_id: null,
        apply_to_matching_aliases: true,
      },
    })
  })
})
