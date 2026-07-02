import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { TopBar } from "../components/workbench/top-bar"

describe("TopBar", () => {
  it("renders the current workbench header instead of reading demo project data", () => {
    render(
      <TopBar
        projectHeader={{ name: "Observatory Draft", chapter: "v7", pov: "Nova" }}
        onAskOpen={vi.fn()}
        reviewItems={[]}
        reviewOpen={false}
        onReviewToggle={vi.fn()}
      />,
    )

    expect(screen.getByText("Observatory Draft")).toBeVisible()
    expect(screen.getByText("v7")).toBeVisible()
    expect(screen.getByText("POV · Nova")).toBeVisible()
    expect(screen.queryByText("Harbor Nine")).toBeNull()
    expect(screen.queryByText("POV · Mira")).toBeNull()
  })
})
