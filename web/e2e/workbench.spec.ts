import { expect, test } from "@playwright/test"

const projectId = "00000000-0000-4000-8000-000000000001"
const actorId = "00000000-0000-4000-8000-000000000002"
const sourceId = "00000000-0000-4000-8000-000000000003"
const aliasReviewId = "00000000-0000-4000-8000-000000000009"
const apiBaseUrl = `http://127.0.0.1:${process.env.SEXTANT_E2E_API_PORT ?? "8011"}`
const localDraftCandidateText = "为了继续推进眼前这一拍，Mira 继续握着地图筒，停在当前阻力前。"

test("workbench runs backend-backed candidate and writeback flow", async ({ page }) => {
  await page.goto("/")

  const topBar = page.getByRole("banner")
  await expect(topBar.getByText("Ch.03 西档案室")).toBeVisible()
  await expect(topBar.getByText("v1")).toBeVisible()
  await expect(topBar.getByText("POV · 当前 POV")).toBeVisible()
  await expect(topBar.getByText("Harbor Nine")).toHaveCount(0)
  await expect(page.getByRole("heading", { name: "Ch.03 西档案室" })).toBeVisible()
  await expect(page.getByText("停在那里，静止得足以算作一种回答。")).toBeVisible()
  await expect(page.getByText("演示")).toHaveCount(0)
  await expect(page.getByText("上下文依据已同步")).toBeVisible()
  const sceneCard = page.getByRole("complementary")
  await expect(sceneCard.getByText("暂无已确认记忆")).toBeVisible()
  await expect(sceneCard.getByText(/Starling · 角色 · 持有 · Lantern Map · 物件/).first()).toBeVisible()
  await expect(sceneCard.getByText("风格样本")).toBeVisible()
  await expect(sceneCard.getByText("叙述样本 · Starling 带着灯图。")).toBeVisible()

  await page.getByRole("button", { name: "2 个待处理" }).click()
  await page
    .getByRole("button", {
      name: "钥匙来源仍未确认，暂不能写成 Mira 已经知道。 知识冲突 · 中",
    })
    .click()
  await expect(page.getByText("默认处理：")).toBeVisible()
  await page.getByRole("button", { name: "暂不处理" }).click()
  await expect(page.getByRole("button", { name: "1 个待处理" })).toBeVisible()
  await page.getByRole("button", { name: "重新打开" }).click()
  await expect(page.getByRole("button", { name: "2 个待处理" })).toBeVisible()
  await page.getByLabel("复核处理说明").fill("作者确认新文本替代旧设定。")
  await page.getByLabel("复核处理方式").selectOption("accepted_as_change")
  await page.getByRole("button", { name: "确认处理" }).click()
  await expect(page.getByRole("button", { name: "1 个待处理" })).toBeVisible()
  await expect(page.getByText("影响")).toBeVisible()
  await page.mouse.click(20, 100)

  await page.getByRole("button", { name: "问 Sextant ⌘K" }).click()
  await page.getByRole("button", { name: "当前 POV 现在知道什么？ 查证据" }).click()
  await expect(page.getByText("Sextant 回答")).toBeVisible()
  await expect(page.getByText("未找到证据")).toBeVisible()
  await expect(page.getByText("需要先指明要追问的角色、物件或事实关系。")).toBeVisible()
  await expect(page.getByText("POV 不可直接用")).toBeVisible()
  await page.getByRole("button", { name: "关闭回答" }).click()

  await page.getByRole("button", { name: "问 Sextant ⌘K" }).click()
  await page.getByRole("button", { name: "续写这一段 给出几条候选" }).click()
  await expect(page.getByText("候选续写")).toBeVisible()
  await expect(page.getByText("正在生成候选，不会写入正文或记忆。")).toBeVisible()
  await expect(
    page.getByTestId("candidate-drawer").getByText(localDraftCandidateText),
  ).toBeVisible({
    timeout: 10_000,
  })
  await page.getByRole("button", { name: "查看依据" }).click()
  await expect(page.getByText("上下文依据", { exact: true })).toBeVisible()
  await expect(page.getByText(/续写小段 · 证据/)).toBeVisible()
  await page.getByRole("button", { name: "解释候选" }).click()
  await expect(page.getByText("候选解释")).toBeVisible()
  await expect(page.getByText("等待作者选择")).toBeVisible()

  await page.getByRole("button", { name: "选这一句" }).first().click()
  await page.getByRole("button", { name: "保存为修订候选" }).click()
  await expect(page.getByText("修订候选已保存，仍需作者采纳。")).toBeVisible()
  await page.getByRole("button", { name: "选这一句" }).first().click()
  await page.getByRole("button", { name: "只采纳所选句" }).click()

  await expect(page.getByText("我准备记住这些")).toBeVisible()
  await expect(page.getByText("正文变更已写入，回写状态由系统读取；处理完成后会显示证据链。")).toBeVisible()
  await expect(page.getByText(/回写任务 · 完成/)).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText("证据段落", { exact: true })).toBeVisible()
  await expect(page.getByText("事实", { exact: true })).toBeVisible()
  await expect(
    page.getByText("真实回写预览 · 不把候选解释当证据。"),
  ).toBeVisible()
  const writebackDeltasResponse = await page.request.get(
    `${apiBaseUrl}/api/projects/${projectId}/source-deltas?source_id=${sourceId}&limit=10`,
    { headers: { "X-Actor-Id": actorId } },
  )
  expect(writebackDeltasResponse.ok()).toBeTruthy()
  await writebackDeltasResponse.json()

  const factSourceResponse = await page.request.post(
    `${apiBaseUrl}/api/projects/${projectId}/sources`,
    {
      headers: {
        "X-Actor-Id": actorId,
        "X-Request-Id": "req-e2e-fact-source",
        "Idempotency-Key": "idem-e2e-fact-source",
      },
      data: {
        title: "Fact Acceptance Fixture",
        source_type: "draft_manuscript",
        source_scope: "user_draft",
        ownership_status: "owned",
        text: "FACT: character:mira | owns | object:lantern-map | low",
        version_label: "v1",
      },
    },
  )
  expect(factSourceResponse.ok()).toBeTruthy()
  const factSource = await factSourceResponse.json()
  await expect
    .poll(async () => {
      const response = await page.request.get(
        `${apiBaseUrl}/api/projects/${projectId}/source-deltas/${factSource.source_delta_id}/memory-writeback-preview`,
        { headers: { "X-Actor-Id": actorId } },
      )
      if (!response.ok()) {
        return "preview-unavailable"
      }
      const body = await response.json()
      return [
        body.source_delta_status,
        body.fact_assertions.length,
        body.memory_pages.length,
        body.graph_edges.length,
      ].join(":")
    })
    .toBe("memory_writeback_completed:1:1:1")

  await page.reload()
  await expect(
    page.locator("[data-editor-para]").filter({
      hasText: localDraftCandidateText,
    }),
  ).toBeVisible()
  await expect(page.getByTestId("editor-version-label")).toHaveText("v2")
  await expect(page.getByRole("button", { name: "1 个待处理" })).toBeVisible()
  await expect(
    page.getByRole("complementary").getByText(/上下文依据(待更新 · [1-9]\d*|已同步)/),
  ).toBeVisible()
  await page.getByRole("button", { name: "打开记忆页" }).click()
  const memoryPages = page.getByTestId("memory-page-list")
  const openThreadMemoryPage = memoryPages.getByRole("button", {
    name: /^Starling 当前 角色 · 场景 · 证据 1 · 线索 1/,
  })
  await expect(openThreadMemoryPage).toBeVisible()
  await openThreadMemoryPage.click()
  const memoryPageDetail = page.getByTestId("memory-page-detail")
  await expect(memoryPageDetail.getByText("记忆页详情")).toBeVisible()
  await expect(memoryPageDetail.getByText(/地图来源仍待确认/)).toBeVisible()
  await memoryPageDetail.getByRole("button", { name: "回收" }).click()
  await expect(memoryPageDetail.getByText(/已回收/)).toBeVisible()
  await expect(memoryPageDetail.getByRole("button", { name: "回收" })).toHaveCount(0)
  const miraMemoryPage = memoryPages.getByRole("button", {
    name: /^Mira 当前 角色/,
  })
  await expect(miraMemoryPage).toBeVisible()
  await miraMemoryPage.click()
  await expect(memoryPageDetail.getByText("记忆页详情")).toBeVisible()
  await expect(memoryPageDetail.getByText("持有")).toBeVisible()
  await expect(memoryPageDetail.locator("p").filter({ hasText: /正文变更/ })).toBeVisible()
  const graphInspector = page.getByTestId("graph-projection-inspector")
  await expect(graphInspector.getByText("关系图谱")).toBeVisible()
  await expect(graphInspector.getByText(/证据段落 [1-9]/).first()).toBeVisible()
  await graphInspector.getByLabel("搜索关系图谱").fill("mira")
  await expect(graphInspector.getByText(/Mira/).first()).toBeVisible()
  await graphInspector.getByLabel("关系状态").selectOption("canon")
  await expect(graphInspector.locator("article").filter({ hasText: "已确认" }).first()).toBeVisible()
  await page.getByRole("complementary").getByRole("button", { name: "关闭记忆页" }).click()

  await page.getByRole("button", { name: "展开项目" }).click()
  await expect(page.getByRole("heading", { name: "项目状态" })).toBeVisible()
  const storySchema = page.getByTestId("project-story-schema")
  await expect(storySchema.getByText("故事规则")).toBeVisible()
  await storySchema.getByLabel("类型规则包").selectOption("00000000-0000-4000-8000-000000000008")
  await expect(storySchema.getByText("类型规则已保存")).toBeVisible()
  await storySchema.getByText("高级规则编辑").click()
  await storySchema.getByLabel("高级规则草稿").fill(
    [
      "规则名称：项目规则",
      "实体类型：物件",
      "事件类型：无",
      "关系：守护",
      "抽取提示：无",
      "风险规则：无",
    ].join("\n"),
  )
  await storySchema.getByRole("button", { name: "保存规则" }).click()
  await expect(storySchema.getByText("规则已保存", { exact: true })).toBeVisible()
  await expect(storySchema.getByLabel("高级规则草稿")).toHaveValue(/守护/)
  const versionHistory = page.getByTestId("source-version-history")
  await expect(versionHistory.getByText("v2")).toBeVisible()
  await expect(versionHistory.getByText("v1")).toBeVisible()
  await versionHistory.getByRole("button", { name: "对比正文版本 v1" }).click()
  await expect(page.getByText("版本对比")).toBeVisible()
  await expect(page.getByText("v1 → v2")).toBeVisible()
  await expect(page.getByText(/\+\d+ \/ -\d+/)).toBeVisible()
  await versionHistory.getByRole("button", { name: "打开正文版本 v1" }).click()
  await expect(page.getByTestId("editor-version-label")).toHaveText("v1")
  await versionHistory.getByRole("button", { name: "打开正文版本 v2" }).click()
  await expect(page.getByTestId("editor-version-label")).toHaveText("v2")
  await versionHistory.getByRole("button", { name: "恢复正文版本 v1" }).click()
  await expect(page.getByText("正文版本已恢复 · 等待记忆回写")).toBeVisible()
  await expect(page.getByTestId("editor-version-label")).toHaveText("v3")
  await expect(page.locator("[data-editor-para='0']")).toContainText(
    "Mira 把空的地图筒推过桌面。",
  )
  await expect(
    page
      .getByTestId("source-delta-detail")
      .getByText("Mira 把空的地图筒推过桌面。"),
  ).toBeVisible()
  await page.getByRole("complementary").getByRole("button", { name: "关闭项目状态" }).click()
  await page.getByRole("button", { name: "编辑当前正文版本" }).click()
  await page.getByLabel("编辑当前正文").fill(
    "Mira 把空的地图筒推过桌面。\n她在页边写下：不要相信第二把钥匙。",
  )
  await expect(page.getByText("编辑预览 · +2 / -4")).toBeVisible()
  await expect(page.getByText("+ 她在页边写下：不要相信第二把钥匙。")).toBeVisible()
  await page.getByRole("button", { name: "保存为正文变更" }).click()
  await expect(page.getByText("正文变更已保存 · 等待记忆回写")).toBeVisible()
  await expect(page.getByTestId("editor-version-label")).toHaveText("v4")
  await page.getByRole("button", { name: "展开项目" }).click()
  await expect(
    page
      .getByTestId("source-delta-detail")
      .getByText("她在页边写下：不要相信第二把钥匙"),
  ).toBeVisible()
  await expect(page.locator("[data-editor-para='1']")).toContainText(
    "她在页边写下：不要相信第二把钥匙。",
  )
  const sourceDeltas = page.getByTestId("project-source-deltas")
  await expect(sourceDeltas.getByText("正文变更", { exact: true })).toBeVisible()
  await expect(sourceDeltas.getByText(localDraftCandidateText)).toBeVisible()
  await expect(sourceDeltas.locator("button").filter({ hasText: "回写完成" }).first()).toBeVisible()
  await page.getByLabel("正文变更状态").selectOption("memory_writeback_completed")
  await page.getByLabel("正文变更类型").selectOption("replace")
  await page.getByLabel("搜索正文变更").fill("钥匙来源")
  await expect(sourceDeltas.getByText("暂无正文变更")).toBeVisible()
  await page.getByLabel("搜索正文变更").fill("地图筒")
  await expect(sourceDeltas.getByText(localDraftCandidateText)).toBeVisible()
  await sourceDeltas.locator("button").filter({ hasText: localDraftCandidateText }).click()
  const sourceDeltaDetail = page.getByTestId("source-delta-detail")
  await expect(sourceDeltaDetail.getByText("正文变更详情")).toBeVisible()
  await expect(sourceDeltaDetail.getByText(localDraftCandidateText)).toBeVisible()
  const sources = page.getByTestId("project-sources")
  await expect(sources.getByText("西档案室")).toBeVisible()
  await page.getByLabel("搜索材料").fill("西档案")
  await expect(sources.getByText("西档案室")).toBeVisible()
  await page.getByLabel("材料标题").fill("角色备忘")
  await page.getByLabel("材料正文").fill("Mira 不确定钥匙来源。")
  await page.getByRole("button", { name: "导入材料" }).click()
  await expect(sources.getByText("角色备忘")).toBeVisible()
  await expect(page.getByText("材料已保存 · 等待记忆回写")).toBeVisible()
  await expect(sourceDeltaDetail.getByText("Mira 不确定钥匙来源。")).toBeVisible()
  await page.getByRole("button", { name: "归档材料 角色备忘" }).click()
  await expect(page.getByText("材料已归档")).toBeVisible()
  await expect(sources.getByText("角色备忘")).toHaveCount(0)
  await page.getByRole("button", { name: "关闭项目状态" }).click()

  await page.getByRole("button", { name: "问 Sextant ⌘K" }).click()
  await page.getByRole("button", { name: "试写有争议版本 需要确认" }).click()
  await expect(page.getByText(localDraftCandidateText)).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText("她确信尚未确认的身份已经暴露，这个判断越过了当前证据。")).toHaveCount(0)
  await page.getByRole("button", { name: "选这一句" }).first().click()
  await expect(page.getByRole("button", { name: "需先处理风险" })).toBeDisabled()
  await page.getByLabel("覆盖原因").fill("作者确认要比较这个有风险的版本。")
  await page.getByRole("button", { name: "确认风险并允许采纳" }).click()
  await expect(page.getByText("覆盖已记录，候选仍保留风险标记。")).toBeVisible()
  await expect(
    page.getByText("高风险 · Draft leaks knowledge the ProseRenderingContract marks as forbidden."),
  ).toBeVisible()
  await expect(page.getByRole("button", { name: "只采纳所选句" })).toBeEnabled()
})

test("workbench accepts selected-text rewrite through backend ActionRequest", async ({
  page,
}) => {
  await page.goto("/")

  const beforeDeltasResponse = await page.request.get(
    `${apiBaseUrl}/api/projects/${projectId}/source-deltas?source_id=${sourceId}&limit=1`,
    { headers: { "X-Actor-Id": actorId } },
  )
  expect(beforeDeltasResponse.ok()).toBeTruthy()
  const beforeDeltas = await beforeDeltasResponse.json()
  const beforeLatestDeltaId = beforeDeltas.items[0]?.id ?? null

  async function requestSelectedRewrite() {
    const actionRequestPromise = page.waitForResponse(
      (response) =>
        response.url() === `${apiBaseUrl}/api/projects/${projectId}/action-requests` &&
        response.request().method() === "POST",
    )
    const actionRunPromise = page.waitForResponse(
      (response) =>
        response.url().includes(`/api/projects/${projectId}/action-requests/`) &&
        response.url().endsWith("/run") &&
        response.request().method() === "POST",
    )
    const paragraph = page.locator("[data-editor-para='0']")
    await paragraph.selectText()
    await paragraph.dispatchEvent("mouseup")
    await expect(page.getByRole("menu")).toBeVisible()
    await page.getByRole("menuitem", { name: "改写" }).click()

    const actionRequestResponse = await actionRequestPromise
    expect(actionRequestResponse.ok()).toBeTruthy()
    const actionRequest = await actionRequestResponse.json()
    expect(actionRequest.status).toBe("submitted")

    const actionRunResponse = await actionRunPromise
    expect(actionRunResponse.ok()).toBeTruthy()
    const actionRun = await actionRunResponse.json()
    const candidateId = actionRun.draft_candidate_ids[0]
    expect(candidateId).toBeTruthy()

    const actionDetailResponse = await page.request.get(
      `${apiBaseUrl}/api/projects/${projectId}/action-requests/${actionRequest.action_request_id}`,
      { headers: { "X-Actor-Id": actorId } },
    )
    expect(actionDetailResponse.ok()).toBeTruthy()
    const actionDetail = await actionDetailResponse.json()
    expect(actionDetail.trigger).toBe("selection")
    expect(actionDetail.action_type).toBe("rewrite_span")
    expect(actionDetail.expected_output).toBe("draft_candidate")
    expect(actionDetail.target.kind).toBe("selected_text")
    expect(actionDetail.target.source_id).toBe(sourceId)
    expect(actionDetail.target.selected_text.length).toBeGreaterThan(1)
    expect(actionDetail.target.range.start).toBeLessThan(actionDetail.target.range.end)

    const candidateResponse = await page.request.get(
      `${apiBaseUrl}/api/projects/${projectId}/candidates/${candidateId}`,
      { headers: { "X-Actor-Id": actorId } },
    )
    expect(candidateResponse.ok()).toBeTruthy()
    const candidate = await candidateResponse.json()
    expect(candidate.action_request_id).toBe(actionRequest.action_request_id)
    expect(candidate.mode).toBe("rewrite_span")
    expect(candidate.target_source_id).toBe(sourceId)
    expect(candidate.target_version_id).toBe(actionDetail.source_version_id)
    expect(candidate.affected_range).toEqual(actionDetail.target.range)

    await expect(page.getByText("候选续写")).toBeVisible()
    await expect(page.getByText("改写选区，保留证据边界")).toBeVisible()
    await expect(page.getByTestId("candidate-stale-source")).toHaveCount(0)
    await expect(page.getByRole("button", { name: "选这一句" }).first()).toBeVisible()
  }

  async function acceptSelectedSentence() {
    await page.getByRole("button", { name: "选这一句" }).first().click()
    const riskBlockedAccept = page.getByRole("button", { name: "需先处理风险" })
    if (await riskBlockedAccept.isVisible()) {
      await expect(riskBlockedAccept).toBeDisabled()
      await page.getByLabel("覆盖原因").fill("作者确认这个选区改写用于端到端验收。")
      await page.getByRole("button", { name: "确认风险并允许采纳" }).click()
      await expect(page.getByText("覆盖已记录，候选仍保留风险标记。")).toBeVisible()
    }
    const acceptResponsePromise = page.waitForResponse(
      (response) =>
        response.url().includes(`/api/projects/${projectId}/candidates/`) &&
        response.url().endsWith("/accept") &&
        response.request().method() === "POST",
    )
    await page.getByRole("button", { name: "只采纳所选句" }).click()
    const acceptResponse = await acceptResponsePromise
    if (acceptResponse.status() === 409) {
      await expect(page.getByText("正文版本已更新", { exact: true })).toBeVisible()
      return false
    }
    expect(acceptResponse.ok()).toBeTruthy()
    await expect(page.getByText("正文变更已写入，回写状态由系统读取；处理完成后会显示证据链。")).toBeVisible()
    return true
  }

  await requestSelectedRewrite()
  let accepted = false
  for (let attempt = 0; attempt < 3; attempt += 1) {
    accepted = await acceptSelectedSentence()
    if (accepted) {
      break
    }
    await page.getByRole("button", { name: "刷新正文" }).click()
    await expect(page.getByText("已刷新到最新正文版本，请重新生成候选。")).toBeVisible()
    await requestSelectedRewrite()
  }
  expect(accepted).toBeTruthy()

  await expect(page.getByText("正文变更已写入，回写状态由系统读取；处理完成后会显示证据链。")).toBeVisible()
  await expect(page.getByText(/回写任务 · 完成/)).toBeVisible({ timeout: 10_000 })
  const afterDeltasResponse = await page.request.get(
    `${apiBaseUrl}/api/projects/${projectId}/source-deltas?source_id=${sourceId}&limit=1`,
    { headers: { "X-Actor-Id": actorId } },
  )
  expect(afterDeltasResponse.ok()).toBeTruthy()
  const afterDeltas = await afterDeltasResponse.json()
  const latestDelta = afterDeltas.items[0]
  expect(latestDelta.id).not.toBe(beforeLatestDeltaId)
  expect(latestDelta.accepted_fragment_id).toBeTruthy()
  expect(latestDelta.new_version_id).toBeTruthy()
  expect(latestDelta.submitted_text_preview.length).toBeGreaterThan(0)
})

test("workbench manages project members through the backend-backed project panel", async ({
  page,
}) => {
  const managedMemberId = "00000000-0000-4000-8000-00000000e2e1"
  const managedMemberLabel = "编辑者 2"
  const invitedMemberId = "00000000-0000-4000-8000-00000000e2e2"

  await page.goto("/")

  await page.getByRole("button", { name: "展开项目" }).click()
  await expect(page.getByRole("heading", { name: "项目状态" })).toBeVisible()

  const members = page.getByTestId("project-members")
  await expect(members.getByText("所有者 1")).toBeVisible()
  await expect(members.getByText("所有者 · 有效")).toBeVisible()

  await members.getByLabel("成员编号").fill(managedMemberId)
  await members.getByLabel("成员角色").selectOption("editor")
  await members.getByRole("button", { name: "添加或更新成员" }).click()

  await expect(members.getByText("成员已更新。")).toBeVisible()
  await expect(members.getByText(managedMemberLabel)).toBeVisible()
  await expect(members.getByText("编辑者 · 有效")).toBeVisible()

  await page.getByRole("button", { name: "刷新项目状态" }).click()
  await expect(members.getByText(managedMemberLabel)).toBeVisible()
  await expect(members.getByText("编辑者 · 有效")).toBeVisible()

  await members.getByRole("button", { name: `撤销成员 ${managedMemberLabel}` }).click()

  await expect(members.getByText("成员已撤销。")).toBeVisible()
  await expect(members.getByText(managedMemberLabel)).toBeVisible()
  await expect(members.getByText("编辑者 · 已撤销")).toBeVisible()

  await page.getByRole("button", { name: "刷新项目状态" }).click()
  await expect(members.getByText(managedMemberLabel)).toBeVisible()
  await expect(members.getByText("编辑者 · 已撤销")).toBeVisible()
  await expect(
    members.getByRole("button", { name: `撤销成员 ${managedMemberLabel}` }),
  ).toBeDisabled()

  await expect(members.getByText("暂无邀请")).toBeVisible()
  await members.getByLabel("邀请对象编号").fill(invitedMemberId)
  await members.getByLabel("邀请对象角色").selectOption("viewer")
  await members.getByLabel("邀请递送服务").fill("ses://sextant-prod/invitations")
  await members
    .getByLabel("邀请递送目标")
    .fill("ses://sextant-prod/recipient/e2e-viewer")
  await members.getByLabel("邀请 Token 签发").fill("auth0://sextant-prod/clients/web")
  await members.getByRole("button", { name: "记录邀请意图" }).click()

  await expect(members.getByText("邀请已记录。")).toBeVisible()
  await expect(members.getByText("邀请 · 读者")).toBeVisible()
  await expect(members.getByText("递送未记录 · Token 未签发")).toBeVisible()

  await page.getByRole("button", { name: "刷新项目状态" }).click()
  await expect(members.getByText("邀请 · 读者")).toBeVisible()
  await expect(members.getByText("递送未记录 · Token 未签发")).toBeVisible()

  await members.getByLabel("邀请递送证明").fill("ses://sextant-prod/messages/e2e-delivery")
  await members.getByLabel("邀请 Token 证明").fill("auth0://sextant-prod/tickets/e2e-token")
  await members.getByRole("button", { name: "记录外部证明 邀请 1" }).click()

  await expect(members.getByText("外部证明已记录。")).toBeVisible()
  await expect(members.getByText("递送已记录 · Token 已签发")).toBeVisible()

  const invitationsResponse = await page.request.get(
    `${apiBaseUrl}/api/projects/${projectId}/invitations`,
    { headers: { "X-Actor-Id": actorId } },
  )
  expect(invitationsResponse.ok()).toBeTruthy()
  const invitations = await invitationsResponse.json()
  const invitation = invitations.items.find(
    (item: { member_actor_id: string }) => item.member_actor_id === invitedMemberId,
  )
  expect(invitation).toBeTruthy()
  expect(invitation.delivery_status).toBe("sent")
  expect(invitation.token_status).toBe("issued")
  expect(invitation.delivery_proof_ref).toBe("ses://sextant-prod/messages/e2e-delivery")
  expect(invitation.token_proof_ref).toBe("auth0://sextant-prod/tickets/e2e-token")
})

test("workbench resolves alias correction reviews through backend side effects", async ({
  page,
}) => {
  await page.goto("/")

  await page.getByRole("button", { name: /个待处理/ }).click()
  await page
    .getByRole("button", {
      name: /Starling 应合并为 Mira。 别名冲突 · 中/,
    })
    .click()

  await expect(page.getByText("默认处理：")).toBeVisible()
  await expect(page.getByLabel("选择目标角色", { exact: true })).toContainText(
    "Mira · 角色",
  )
  const startSceneSelect = page.getByLabel("起始场景")
  const endSceneSelect = page.getByLabel("结束场景")
  await expect(startSceneSelect).toContainText("Chapter 1 / Scene 1")
  await expect(startSceneSelect).not.toContainText("终点")
  await expect(endSceneSelect).toContainText("Chapter 1 / Scene 1")
  await expect(endSceneSelect).toContainText("终点")
  const boundarySceneId = await startSceneSelect.locator("option").nth(1).getAttribute("value")
  if (!boundarySceneId) {
    throw new Error("Expected the backend scene option to include a scene id.")
  }
  await startSceneSelect.selectOption(boundarySceneId)
  await endSceneSelect.selectOption("")
  await page.getByLabel("应用到同名伪装弧").check()
  await page.getByLabel("复核处理说明").fill("Starling 是 Mira 的旧称。")
  await page.getByLabel("复核处理方式").selectOption("accepted_as_change")
  await page.getByRole("button", { name: "确认处理" }).click()

  await expect(page.getByText("别名修正 · 已应用")).toBeVisible()
  await expect(page.getByText("别名边界 · 已应用")).toBeVisible()
  await expect(page.getByText("别名记录 · 1 项已更新")).toBeVisible()
  await expect(page.getByText("关系图谱 · 已重建")).toBeVisible()
  await expect(page.getByText("记忆页 · 已标为需重写")).toBeVisible()
  const reviewResponse = await page.request.get(
    `${apiBaseUrl}/api/projects/${projectId}/review-items/${aliasReviewId}`,
    { headers: { "X-Actor-Id": actorId } },
  )
  expect(reviewResponse.ok()).toBeTruthy()
  const review = await reviewResponse.json()
  expect(review.side_effects.alias_boundary_correction).toBe("applied")
  expect(review.side_effects.alias_boundary_records_updated).toBe(1)
  expect(review.side_effects.valid_from_scene_id).toBe(boundarySceneId)
  expect(review.side_effects.valid_until_scene_id).toBeNull()
})

test("workbench shows stale source recovery without applying old candidate", async ({
  page,
}) => {
  await page.goto("/")

  await page.getByRole("button", { name: "问 Sextant ⌘K" }).click()
  await page.getByRole("button", { name: "续写这一段 给出几条候选" }).click()
  await expect(
    page.getByTestId("candidate-drawer").getByText(localDraftCandidateText),
  ).toBeVisible({
    timeout: 10_000,
  })

  const versionsResponse = await page.request.get(
    `${apiBaseUrl}/api/projects/${projectId}/sources/${sourceId}/versions`,
    { headers: { "X-Actor-Id": actorId } },
  )
  expect(versionsResponse.ok()).toBeTruthy()
  const versions = await versionsResponse.json()
  const latestVersionId = versions.items[0].version_id
  const latestSourceResponse = await page.request.get(
    `${apiBaseUrl}/api/projects/${projectId}/sources/${sourceId}/versions/${latestVersionId}`,
    { headers: { "X-Actor-Id": actorId } },
  )
  expect(latestSourceResponse.ok()).toBeTruthy()
  const latestSource = await latestSourceResponse.json()
  const concurrentText = `${latestSource.text}\n并发保存的测试尾句。`
  const createVersionResponse = await page.request.post(
    `${apiBaseUrl}/api/projects/${projectId}/sources/${sourceId}/versions`,
    {
      headers: {
        "X-Actor-Id": actorId,
        "X-Request-Id": "req-e2e-stale-version",
        "Idempotency-Key": "idem-e2e-stale-version",
      },
      data: {
        text: concurrentText,
        version_label: "v-stale-e2e",
        supersedes_version_id: latestVersionId,
      },
    },
  )
  expect(createVersionResponse.ok()).toBeTruthy()

  await page.getByRole("button", { name: "选这一句" }).first().click()
  await expect(page.getByRole("button", { name: "需先处理风险" })).toBeDisabled()
  await page.getByLabel("覆盖原因").fill("作者确认要测试旧正文版本拒绝。")
  await page.getByRole("button", { name: "确认风险并允许采纳" }).click()
  await expect(page.getByText("覆盖已记录，候选仍保留风险标记。")).toBeVisible()
  await expect(page.getByRole("button", { name: "只采纳所选句" })).toBeEnabled()
  await page.getByRole("button", { name: "只采纳所选句" }).click()

  await expect(page.getByText("正文版本已更新", { exact: true })).toBeVisible()
  await expect(page.getByText(/系统没有写入正文或记忆/)).toBeVisible()
  await expect(page.getByRole("button", { name: "只采纳所选句" })).toBeDisabled()
  await expect(page.getByText("我准备记住这些")).toHaveCount(0)

  await page.getByRole("button", { name: "刷新正文" }).click()

  await expect(page.getByText("已刷新到最新正文版本，请重新生成候选。")).toBeVisible()
  await expect(page.getByTestId("editor-version-label")).toHaveText("v-stale-e2e")
  await expect(page.getByText("并发保存的测试尾句。")).toBeVisible()
})

test("workbench rejects stale source edit, refreshes latest, and preserves draft for merge", async ({
  page,
}) => {
  await page.goto("/")

  await page.getByRole("button", { name: "编辑当前正文版本" }).click()
  await page.getByLabel("编辑当前正文").fill("Mira typed a stale source edit.")

  const versionsResponse = await page.request.get(
    `${apiBaseUrl}/api/projects/${projectId}/sources/${sourceId}/versions`,
    { headers: { "X-Actor-Id": actorId } },
  )
  expect(versionsResponse.ok()).toBeTruthy()
  const versions = await versionsResponse.json()
  const latestVersionId = versions.items[0].version_id
  const latestSourceResponse = await page.request.get(
    `${apiBaseUrl}/api/projects/${projectId}/sources/${sourceId}/versions/${latestVersionId}`,
    { headers: { "X-Actor-Id": actorId } },
  )
  expect(latestSourceResponse.ok()).toBeTruthy()
  const latestSource = await latestSourceResponse.json()
  const concurrentText = `${latestSource.text}\nsource edit concurrent line.`
  const createVersionResponse = await page.request.post(
    `${apiBaseUrl}/api/projects/${projectId}/sources/${sourceId}/versions`,
    {
      headers: {
        "X-Actor-Id": actorId,
        "X-Request-Id": "req-e2e-stale-source-edit",
        "Idempotency-Key": "idem-e2e-stale-source-edit",
      },
      data: {
        text: concurrentText,
        version_label: "v-stale-source-edit",
        supersedes_version_id: latestVersionId,
      },
    },
  )
  expect(createVersionResponse.ok()).toBeTruthy()

  await page.getByRole("button", { name: "保存为正文变更" }).click()

  await expect(
    page.getByText(
      "正文版本已更新。请刷新最新正文版本后重新编辑；系统没有写入正文变更或记忆。",
    ),
  ).toBeVisible()
  await expect(page.getByText("正文变更已保存 · 等待记忆回写")).toHaveCount(0)

  await page.getByRole("button", { name: "刷新最新正文版本" }).click()

  await expect(page.getByText("已刷新最新正文版本，草稿已保留用于合并。")).toBeVisible()
  await expect(page.getByTestId("editor-version-label")).toHaveText("v-stale-source-edit")
  await expect(page.getByLabel("编辑当前正文")).toHaveValue(concurrentText)
  await expect(page.getByText("草稿冲突")).toBeVisible()
  await expect(page.getByText("Mira typed a stale source edit.")).toBeVisible()

  await page.getByRole("button", { name: "合并被拒绝的草稿" }).click()

  await expect(
    page.getByText("已合并最新正文版本和被拒绝草稿，请检查预览后保存。"),
  ).toBeVisible()
  await expect(page.getByLabel("编辑当前正文")).toHaveValue(
    `${concurrentText}\nMira typed a stale source edit.`,
  )
  await expect(page.getByText("编辑预览 · +1 / -0")).toBeVisible()
  await expect(page.getByText("+ Mira typed a stale source edit.")).toBeVisible()

  await page.getByRole("button", { name: "保存为正文变更" }).click()

  await expect(page.getByText("正文变更已保存 · 等待记忆回写")).toBeVisible()
  await expect(
    page.locator("[data-editor-para]").filter({ hasText: "source edit concurrent line." }),
  ).toBeVisible()
  await expect(
    page.locator("[data-editor-para]").filter({ hasText: "Mira typed a stale source edit." }),
  ).toBeVisible()
})
