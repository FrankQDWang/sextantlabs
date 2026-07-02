import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const testDir = dirname(fileURLToPath(import.meta.url))
const workbenchSource = readFileSync(
  join(testDir, "../components/workbench/index.tsx"),
  "utf8",
)

describe("workbench fixture boundary", () => {
  it("keeps seed story literals out of the generic workbench component", () => {
    expect(workbenchSource).not.toMatch(/recallLabel:\s*["']Kestrel["']/)
    expect(workbenchSource).not.toContain("Mira 把钥匙又往他那边推了一寸。")
    expect(workbenchSource).not.toContain('title: "西档案室"')
  })
})
