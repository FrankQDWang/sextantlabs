import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryAnswerPanel } from "../components/workbench/memory-answer-panel"

afterEach(() => {
  cleanup()
})

describe("MemoryAnswerPanel", () => {
  it("renders backend memory answers in author-facing language", () => {
    render(
      <MemoryAnswerPanel
        answer={{
          question: "Mira 现在知道钥匙的来源吗？",
          answer: "No SourceSpan-backed memory evidence matches this question.",
          answer_type: "unknown",
          confidence: 0,
          source_span_refs: [],
          affected_entities: [],
          caveats: [
            "no_matching_evidence",
            "misunderstood_knowledge",
            "timeline_order_from_scene_position",
            "event_overlap_from_scene_or_story_time",
            "scene_local_alias_context",
            "relationship_explained_by_canonical_event",
            "relationship_timeline_from_scene_position",
            "relationship_path_from_fact_evidence",
            "continuity_review_item",
            "high_severity_review",
            "source_mention_lookup",
            "ambiguous_entity_match",
            "semantic_clarification_needed",
          ],
          unknowns: [],
          related_review_items: [],
          safe_to_use_in_current_pov: false,
        }}
        loading={false}
        error={null}
        onClose={vi.fn()}
      />,
    )

    expect(screen.getByText("未找到证据")).toBeVisible()
    expect(screen.getByText("没有找到可追溯到原文片段的记忆证据。")).toBeVisible()
    expect(screen.getByText("置信度 0%")).toBeVisible()
    expect(screen.getByText("证据段落 0")).toBeVisible()
    expect(screen.getByText("复核 0")).toBeVisible()
    expect(
      screen.getByText(
        "注意 没有匹配的证据段落；角色当前存在误解；时间顺序来自章节/场景位置；同场景或同故事时间内发生；局部别名按证据场景缩窄；关系解释来自事件证据；关系演变顺序来自章节/场景位置；关系路径来自事实证据；存在连续性复核项；高风险复核；来自原文 Mention 的首次出场定位；命中多个可能实体，需要先澄清；语义命中多个证据目标，需要先澄清",
      ),
    ).toBeVisible()
    expect(
      screen.queryByText("No SourceSpan-backed memory evidence matches this question."),
    ).toBeNull()
    expect(screen.queryByText("unknown")).toBeNull()
    expect(screen.queryByText("no_matching_evidence")).toBeNull()
    expect(screen.queryByText("misunderstood_knowledge")).toBeNull()
    expect(screen.queryByText("timeline_order_from_scene_position")).toBeNull()
    expect(screen.queryByText("event_overlap_from_scene_or_story_time")).toBeNull()
    expect(screen.queryByText("scene_local_alias_context")).toBeNull()
    expect(screen.queryByText("relationship_explained_by_canonical_event")).toBeNull()
    expect(screen.queryByText("relationship_timeline_from_scene_position")).toBeNull()
    expect(screen.queryByText("relationship_path_from_fact_evidence")).toBeNull()
    expect(screen.queryByText("continuity_review_item")).toBeNull()
    expect(screen.queryByText("high_severity_review")).toBeNull()
    expect(screen.queryByText("source_mention_lookup")).toBeNull()
    expect(screen.queryByText("ambiguous_entity_match")).toBeNull()
    expect(screen.queryByText("semantic_clarification_needed")).toBeNull()
    expect(screen.queryByText(/SourceSpan|Span|Review/)).toBeNull()
  })

  it("renders open-thread memory answers without raw backend labels", () => {
    render(
      <MemoryAnswerPanel
        answer={{
          question: "What open threads remain for Mira?",
          answer:
            "Open threads: Mira: Kestrel still has the Lantern Map.; The buyer behind the map remains unknown.",
          answer_type: "open_thread",
          confidence: 0.8,
          source_span_refs: [{ type: "source_span", id: "span-1" }],
          affected_entities: [{ type: "character", id: "mira", label: "Mira" }],
          caveats: ["memory_page_open_thread"],
          unknowns: [],
          related_review_items: [],
          safe_to_use_in_current_pov: true,
        }}
        loading={false}
        error={null}
        onClose={vi.fn()}
      />,
    )

    expect(screen.getByText("开放伏笔")).toBeVisible()
    expect(screen.getByText("置信度 80%")).toBeVisible()
    expect(screen.getByText("证据段落 1")).toBeVisible()
    expect(screen.getByText("注意 来自 MemoryPage 的开放伏笔")).toBeVisible()
    expect(screen.queryByText("open_thread")).toBeNull()
    expect(screen.queryByText("memory_page_open_thread")).toBeNull()
  })
})
