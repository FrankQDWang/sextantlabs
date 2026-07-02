import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { SceneCard } from "../components/workbench/scene-card"
import { sceneCardFromContextPack } from "../components/workbench"

const scene = {
  pov: "Mira",
  knows: ["Mira · 持有 · Lantern Map"],
  notKnows: ["Orrin · 知道 · Harbor Code"],
  pitfalls: ["不要提前确认钥匙来源"],
  pressurePoints: ["继续保持证据边界"],
  openThreads: ["谁移动了灯图"],
}

describe("SceneCard", () => {
  it("derives POV section labels and avatar from the current scene card state", () => {
    render(
      <SceneCard
        data={{
          pov: "Nova",
          knows: ["已经确认门后的脚步声"],
          notKnows: ["还不知道钥匙来源"],
          pitfalls: ["不要提前确认身份"],
          pressurePoints: ["继续压住证据边界"],
          openThreads: ["谁移动了灯图"],
        }}
      />,
    )

    expect(screen.getByText("Nova 现在知道")).toBeVisible()
    expect(screen.getByText("Nova 还不知道")).toBeVisible()
    expect(screen.getByText("N")).toBeVisible()
    expect(screen.queryByText("Mira 现在知道")).toBeNull()
  })

  it("maps POV knowledge from allowed knowledge instead of all canon facts", () => {
    const mapped = sceneCardFromContextPack({
      context_pack_id: "context-1",
      schema_version: "writing-context-pack.v1",
      current_position: {},
      canonical_context: {
        facts: [
          {
            subject_ref: {
              type: "character",
              id: "bff4cfc2-1c42-46a6-8c33-4d1ab05d8e5a",
              label: "Starling",
            },
            predicate: "owns",
            object_ref: { type: "object", id: "lantern-map", label: "Lantern Map" },
          },
        ],
      },
      pov_constraint: {
        allowed_knowledge: [],
        forbidden_knowledge: [
          {
            subject_ref: {
              type: "character",
              id: "bff4cfc2-1c42-46a6-8c33-4d1ab05d8e5a",
              label: "Starling",
            },
            predicate: "owns",
            object_ref: { type: "object", id: "lantern-map", label: "Lantern Map" },
          },
        ],
      },
      risk_context: { facts: [], review_items: [] },
      open_threads: [],
      recent_events: [],
      object_location_state: [],
      character_agency_state: {},
      style_memory: {},
      evidence_refs: [],
      token_budget: 0,
      created_at: "2026-06-11T00:00:00Z",
    })

    expect(mapped.knows).toEqual(["暂无已确认记忆"])
    expect(mapped.notKnows).toEqual(["Starling · 角色 · 持有 · Lantern Map · 物件"])
  })

  it("surfaces backend ContextPackReadiness without changing scene card structure", () => {
    render(
      <SceneCard
        data={scene}
        readiness={{ pending: 2, stale: 1, consumed: 4, loading: false, error: null }}
      />,
    )

    expect(screen.getByText("上下文依据待更新 · 3")).toBeVisible()
  })

  it("shows synced ContextPack state when no pending or stale readiness remains", () => {
    render(
      <SceneCard
        data={scene}
        readiness={{ pending: 0, stale: 0, consumed: 4, loading: false, error: null }}
      />,
    )

    expect(screen.getByText("上下文依据已同步")).toBeVisible()
  })

  it("shows deeper backend ContextPack sections when they are populated", () => {
    render(
      <SceneCard
        data={{
          ...scene,
          recentEvents: ["事件 · Mira finds the Lantern Map"],
          objectState: ["Mira · 持有 · Lantern Map"],
          agency: ["Mira · 依据已确认事实行动"],
          styleNotes: ["叙述样本 · 钥匙是冷的"],
        }}
      />,
    )

    expect(screen.getByText("最近事件")).toBeVisible()
    expect(screen.getByText("事件 · Mira finds the Lantern Map")).toBeVisible()
    expect(screen.getByText("物件与地点")).toBeVisible()
    expect(screen.getAllByText("Mira · 持有 · Lantern Map").length).toBeGreaterThan(0)
    expect(screen.getByText("角色动因")).toBeVisible()
    expect(screen.getByText("Mira · 依据已确认事实行动")).toBeVisible()
    expect(screen.getByText("风格样本")).toBeVisible()
    expect(screen.getByText("叙述样本 · 钥匙是冷的")).toBeVisible()
  })
})
