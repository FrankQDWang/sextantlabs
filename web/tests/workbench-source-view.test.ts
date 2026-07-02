import { describe, expect, it } from "vitest"
import { workbenchEditorSourceView } from "../components/workbench"

describe("workbenchEditorSourceView", () => {
  it("does not show demo manuscript or seed title while API source is not loaded", () => {
    const view = workbenchEditorSourceView(true, false, null)

    expect(view).toEqual({
      text: "",
      title: "正文未加载",
      chapter: "等待后端正文",
    })
    expect(`${view.text} ${view.title} ${view.chapter}`).not.toMatch(/Mira|Kestrel|西档案室|钥匙/)
  })

  it("does not show demo manuscript unless demo mode is explicit", () => {
    const view = workbenchEditorSourceView(false, false, null)

    expect(view).toEqual({
      text: "",
      title: "需要后端 API 配置",
      chapter: "生产工作台未连接",
    })
    expect(`${view.text} ${view.title} ${view.chapter}`).not.toMatch(/Mira|Kestrel|西档案室|钥匙/)
  })

  it("keeps the explicit no-API demo fallback visually available", () => {
    const view = workbenchEditorSourceView(false, true, null)

    expect(view.title).toBe("西档案室")
    expect(view.text).toContain("Mira 把空的地图筒推过桌面。")
  })

  it("uses backend source detail when API source is loaded", () => {
    expect(
      workbenchEditorSourceView(true, false, {
        text: "Nova opened the observatory door.",
        title: "观测塔",
        version_label: "v7",
      }),
    ).toEqual({
      text: "Nova opened the observatory door.",
      title: "观测塔",
      chapter: "v7",
    })
  })
})
