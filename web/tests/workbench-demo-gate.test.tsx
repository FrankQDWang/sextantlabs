import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { Workbench } from "../components/workbench"

describe("Workbench demo gate", () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
    window.localStorage.clear()
  })

  it("does not render seed story data without API config or explicit demo mode", () => {
    render(<Workbench />)

    expect(screen.getByText("需要后端 API 配置")).toBeVisible()
    expect(screen.queryByText("Harbor Nine")).toBeNull()
    expect(screen.queryByText("演示")).toBeNull()
    expect(screen.queryByText(/Mira|Kestrel|西档案室|钥匙/)).toBeNull()
  })

  it("requires runtime Supabase login instead of a bundled bearer token for hosted API mode", async () => {
    vi.stubEnv("VITE_SEXTANT_ENABLE_DEMO", "false")
    vi.stubEnv("VITE_SEXTANT_API_BASE_URL", "https://api.test")
    vi.stubEnv("VITE_SEXTANT_PROJECT_ID", "project-1")
    vi.stubEnv("VITE_SEXTANT_ACTOR_ID", "actor-1")
    vi.stubEnv("VITE_SEXTANT_SOURCE_ID", "source-1")
    vi.stubEnv("VITE_SEXTANT_SOURCE_VERSION_ID", "version-1")
    vi.stubEnv("VITE_SEXTANT_SUPABASE_URL", "https://auth.test")
    vi.stubEnv("VITE_SEXTANT_SUPABASE_PUBLISHABLE_KEY", "publishable-key")

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "runtime-jwt",
          refresh_token: "refresh-token",
          expires_in: 600,
          token_type: "bearer",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    )

    render(<Workbench />)

    expect(screen.getByRole("heading", { name: "登录生产工作台" })).toBeVisible()
    expect(screen.queryByText("需要后端 API 配置")).toBeNull()
    expect(screen.queryByText("Harbor Nine")).toBeNull()

    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "author@example.com" },
    })
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "secret-password" },
    })
    fireEvent.click(screen.getByRole("button", { name: "连接生产工作台" }))

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "https://auth.test/auth/v1/token?grant_type=password",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            email: "author@example.com",
            password: "secret-password",
          }),
        }),
      )
    })
    expect(window.localStorage.getItem("sextant.workbench.auth.v1")).toContain("runtime-jwt")
  })
})
