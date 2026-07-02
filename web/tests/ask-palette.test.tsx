import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { AskPalette } from "../components/workbench/ask-palette"

afterEach(() => {
  cleanup()
})

describe("AskPalette", () => {
  it("derives evidence shortcuts from current context instead of seed story names", () => {
    render(
      <AskPalette
        onClose={vi.fn()}
        onPick={vi.fn()}
        suggestionContext={{ povLabel: "Nova", recallLabel: "Archivist" }}
      />,
    )

    expect(screen.getByRole("button", { name: /Nova 现在知道什么？.*查证据/ })).toBeVisible()
    expect(
      screen.getByRole("button", { name: /Archivist 上一次回避是什么时候？.*查前文/ }),
    ).toBeVisible()
    expect(screen.queryByText(/Mira|Kestrel/)).toBeNull()
  })

  it("passes an explicit author-selected memory target with the question", () => {
    const onPick = vi.fn()

    render(
      <AskPalette
        onClose={vi.fn()}
        onPick={onPick}
        memoryTargetOptions={[
          {
            id: "entity-1",
            entityType: "character",
            label: "Mira",
          },
        ]}
      />,
    )

    fireEvent.change(screen.getByLabelText("记忆对象"), {
      target: { value: "character:entity-1" },
    })
    fireEvent.change(screen.getByLabelText("记忆关系"), {
      target: { value: "owns" },
    })
    fireEvent.change(screen.getByPlaceholderText("问 Sextant，或描述你想怎么写…"), {
      target: { value: "她拥有什么？" },
    })
    fireEvent.keyDown(screen.getByPlaceholderText("问 Sextant，或描述你想怎么写…"), {
      key: "Enter",
    })

    expect(onPick).toHaveBeenCalledWith("她拥有什么？", {
      subjectRef: { type: "character", id: "entity-1", label: "Mira" },
      predicate: "owns",
    })
  })
})
