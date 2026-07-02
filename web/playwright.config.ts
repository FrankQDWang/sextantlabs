import { defineConfig, devices } from "@playwright/test"
import path from "node:path"

const rootDir = path.resolve(__dirname, "..")
const apiPort = process.env.SEXTANT_E2E_API_PORT ?? "8011"
const webPort = process.env.SEXTANT_E2E_WEB_PORT ?? "5810"
const apiBaseUrl = `http://127.0.0.1:${apiPort}`
const webBaseUrl = `http://127.0.0.1:${webPort}`

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: {
    baseURL: webBaseUrl,
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: `bash ${rootDir}/scripts/e2e-backend.sh`,
      url: `${apiBaseUrl}/docs`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        ...process.env,
        SEXTANT_E2E_API_PORT: apiPort,
        SEXTANT_E2E_WEB_PORT: webPort,
      },
    },
    {
      command: `pnpm dev --host 127.0.0.1 --port ${webPort}`,
      url: webBaseUrl,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        ...process.env,
        VITE_SEXTANT_API_BASE_URL: apiBaseUrl,
        VITE_SEXTANT_PROJECT_ID: "00000000-0000-4000-8000-000000000001",
        VITE_SEXTANT_ACTOR_ID: "00000000-0000-4000-8000-000000000002",
        VITE_SEXTANT_SOURCE_ID: "00000000-0000-4000-8000-000000000003",
        VITE_SEXTANT_SOURCE_VERSION_ID: "00000000-0000-4000-8000-000000000004",
        VITE_SEXTANT_SCENE_ID: "00000000-0000-4000-8000-000000000012",
        VITE_SEXTANT_POV_CHARACTER_ID: "00000000-0000-4000-8000-00000000000c",
      },
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
})
