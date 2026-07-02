import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ProjectPanel } from "../components/workbench/project-panel"
import type {
  ProjectInvitationResponse,
  ProjectStorySchemaResponse,
  SourceVersionDiffResponse,
  SourceVersionResponse,
} from "../src/generated/sextant-api"

const source: SourceVersionResponse = {
  source_id: "source-1",
  version_id: "version-2",
  title: "Ch.03 西档案室",
  source_type: "draft_manuscript",
  source_scope: "user_draft",
  version_label: "v2",
  raw_hash: "hash-v2",
  raw_text_ref: "object://raw/v2",
  text: "v2 text",
}

const diff: SourceVersionDiffResponse = {
  source_id: "source-1",
  base_version_id: "version-1",
  compare_version_id: "version-2",
  base_version_label: "v1",
  compare_version_label: "v2",
  base_raw_hash: "hash-v1",
  compare_raw_hash: "hash-v2",
  summary: { insertions: 2, deletions: 1, changed: true },
  hunks: [
    {
      old_start: 1,
      old_lines: 3,
      new_start: 1,
      new_lines: 4,
      lines: [
        { kind: "context", old_line: 1, new_line: 1, text: "第一行" },
        { kind: "delete", old_line: 2, new_line: null, text: "第二行" },
        { kind: "insert", old_line: null, new_line: 2, text: "第二行改" },
      ],
    },
  ],
}

const storySchema: ProjectStorySchemaResponse = {
  project_id: "project-1",
  binding_id: "binding-1",
  base_schema_pack_id: "base-pack-1",
  genre_schema_pack_id: "genre-pack-1",
  genre_schema_pack: {
    id: "genre-pack-1",
    project_id: null,
    pack_type: "genre",
    pack_name: "mystery",
    version: "mystery.v1",
    status: "active",
    entity_types: [{ name: "clue", subtype_of: "object" }],
    event_types: ["revelation"],
    relations: ["points_to"],
    extraction_hints: {},
    risk_rules: {},
  },
  project_override_pack_id: "override-pack-1",
  project_override_pack: {
    id: "override-pack-1",
    project_id: "project-1",
    pack_type: "project_override",
    pack_name: "harbor-nine-overrides",
    version: "project-override.v1",
    status: "active",
    entity_types: [{ name: "artifact", subtype_of: "object" }],
    event_types: [],
    relations: [{ name: "guards", subject_types: ["character"], object_types: ["artifact"] }],
    extraction_hints: {},
    risk_rules: {},
  },
  effective_schema: {
    entity_types: [{ name: "character" }, { name: "artifact" }],
    event_types: ["movement"],
    relations: ["owns", { name: "guards" }],
  },
}

afterEach(() => {
  cleanup()
})

describe("ProjectPanel", () => {
  it("lets the author open an older SourceVersion from history", () => {
    const onSourceVersionSelect = vi.fn()

    render(
      <ProjectPanel
        source={source}
        sourceVersions={[
          {
            source_id: "source-1",
            version_id: "version-2",
            version_label: "v2",
            raw_hash: "hash-v2",
            raw_text_ref: "object://raw/v2",
            supersedes_version_id: "version-1",
            created_at: "2026-06-01T00:00:00Z",
          },
          {
            source_id: "source-1",
            version_id: "version-1",
            version_label: "v1",
            raw_hash: "hash-v1",
            raw_text_ref: "object://raw/v1",
            supersedes_version_id: null,
            created_at: "2026-05-31T00:00:00Z",
          },
        ]}
        sourceVersionsLoading={false}
        sourceVersionsError={null}
        sources={[]}
        sourceSearch=""
        sourceListLoading={false}
        sourceListError={null}
        sourceDeltas={[]}
        sourceDeltaSearch=""
        sourceDeltaStatus=""
        sourceDeltaKind=""
        sourceDeltaDetail={null}
        sourceDeltasNextCursor={null}
        sourceDeltaDetailLoading={false}
        sourceDeltaDetailError={null}
        loading={false}
        error={null}
        onSourceVersionSelect={onSourceVersionSelect}
        onClose={vi.fn()}
      />,
    )

    expect(screen.queryByText(/SourceVersion|object:\/\/|hash-v/)).toBeNull()

    fireEvent.click(screen.getByRole("button", { name: "打开正文版本 v1" }))

    expect(onSourceVersionSelect).toHaveBeenCalledWith("version-1")
  })

  it("lets the author restore an older SourceVersion from history", () => {
    const onSourceVersionRestore = vi.fn()

    render(
      <ProjectPanel
        source={source}
        sourceVersions={[
          {
            source_id: "source-1",
            version_id: "version-2",
            version_label: "v2",
            raw_hash: "hash-v2",
            raw_text_ref: "object://raw/v2",
            supersedes_version_id: "version-1",
            created_at: "2026-06-01T00:00:00Z",
          },
          {
            source_id: "source-1",
            version_id: "version-1",
            version_label: "v1",
            raw_hash: "hash-v1",
            raw_text_ref: "object://raw/v1",
            supersedes_version_id: null,
            created_at: "2026-05-31T00:00:00Z",
          },
        ]}
        sourceVersionsLoading={false}
        sourceVersionsError={null}
        sources={[]}
        sourceSearch=""
        sourceListLoading={false}
        sourceListError={null}
        sourceDeltas={[]}
        sourceDeltaSearch=""
        sourceDeltaStatus=""
        sourceDeltaKind=""
        sourceDeltaDetail={null}
        sourceDeltasNextCursor={null}
        sourceDeltaDetailLoading={false}
        sourceDeltaDetailError={null}
        loading={false}
        error={null}
        onSourceVersionRestore={onSourceVersionRestore}
        onClose={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "恢复正文版本 v1" }))

    expect(onSourceVersionRestore).toHaveBeenCalledWith("version-1")
  })

  it("lets the author compare an older SourceVersion and inspect line changes", () => {
    const onSourceVersionDiff = vi.fn()

    render(
      <ProjectPanel
        source={source}
        sourceVersions={[
          {
            source_id: "source-1",
            version_id: "version-2",
            version_label: "v2",
            raw_hash: "hash-v2",
            raw_text_ref: "object://raw/v2",
            supersedes_version_id: "version-1",
            created_at: "2026-06-01T00:00:00Z",
          },
          {
            source_id: "source-1",
            version_id: "version-1",
            version_label: "v1",
            raw_hash: "hash-v1",
            raw_text_ref: "object://raw/v1",
            supersedes_version_id: null,
            created_at: "2026-05-31T00:00:00Z",
          },
        ]}
        sourceVersionsLoading={false}
        sourceVersionsError={null}
        sourceVersionDiff={diff}
        sourceVersionDiffLoading={false}
        sourceVersionDiffError={null}
        sources={[]}
        sourceSearch=""
        sourceListLoading={false}
        sourceListError={null}
        sourceDeltas={[]}
        sourceDeltaSearch=""
        sourceDeltaStatus=""
        sourceDeltaKind=""
        sourceDeltaDetail={null}
        sourceDeltasNextCursor={null}
        sourceDeltaDetailLoading={false}
        sourceDeltaDetailError={null}
        loading={false}
        error={null}
        onSourceVersionDiff={onSourceVersionDiff}
        onClose={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "对比正文版本 v1" }))

    expect(onSourceVersionDiff).toHaveBeenCalledWith("version-1")
    expect(screen.getByText("版本对比")).toBeInTheDocument()
    expect(screen.getByText("v1 → v2")).toBeInTheDocument()
    expect(screen.getByText("+2 / -1")).toBeInTheDocument()
    expect(screen.getByText("第二行改")).toBeInTheDocument()
    expect(screen.queryByText("hash-v1")).toBeNull()
    expect(screen.queryByText("hash-v2")).toBeNull()
  })

  it("keeps raw project schema JSON behind the advanced editor", () => {
    const onStorySchemaOverrideTextChange = vi.fn()
    const onStorySchemaOverrideSave = vi.fn()
    const onStorySchemaGenreSelect = vi.fn()

    render(
      <ProjectPanel
        source={source}
        sourceVersions={[]}
        sourceVersionsLoading={false}
        sourceVersionsError={null}
        sources={[]}
        sourceSearch=""
        sourceListLoading={false}
        sourceListError={null}
        storySchema={storySchema}
        storySchemaGenrePacks={[storySchema.genre_schema_pack!]}
        storySchemaGenreStatus="类型规则已保存"
        onStorySchemaGenreSelect={onStorySchemaGenreSelect}
        storySchemaOverrideText={"规则名称：项目规则\n实体类型：无\n事件类型：无\n关系：无\n抽取提示：无\n风险规则：无"}
        storySchemaSaveStatus="规则已保存"
        onStorySchemaOverrideTextChange={onStorySchemaOverrideTextChange}
        onStorySchemaOverrideSave={onStorySchemaOverrideSave}
        sourceDeltas={[]}
        sourceDeltaSearch=""
        sourceDeltaStatus=""
        sourceDeltaKind=""
        sourceDeltaDetail={null}
        sourceDeltasNextCursor={null}
        sourceDeltaDetailLoading={false}
        sourceDeltaDetailError={null}
        loading={false}
        error={null}
        onClose={vi.fn()}
      />,
    )

    const schemaPanels = screen.getAllByTestId("project-story-schema")
    const schemaPanel = schemaPanels[schemaPanels.length - 1]
    const storySchemaPanel = within(schemaPanel)

    expect(schemaPanel).toBeInTheDocument()
    expect(storySchemaPanel.getByText("实体")).toBeInTheDocument()
    expect(storySchemaPanel.getByText("事件")).toBeInTheDocument()
    expect(storySchemaPanel.getByText("关系")).toBeInTheDocument()
    expect(storySchemaPanel.getByText("高级规则编辑")).toBeInTheDocument()
    expect(storySchemaPanel.queryByLabelText("高级规则草稿")).toBeNull()
    expect(storySchemaPanel.queryByText(/pack_name|relations|harbor-nine-overrides|mystery\.v1/)).toBeNull()

    fireEvent.click(storySchemaPanel.getByText("高级规则编辑"))
    fireEvent.change(storySchemaPanel.getByLabelText("类型规则包"), {
      target: { value: "" },
    })
    fireEvent.change(storySchemaPanel.getByLabelText("高级规则草稿"), {
      target: {
        value: "规则名称：项目规则\n实体类型：物件\n事件类型：无\n关系：守护\n抽取提示：无\n风险规则：无",
      },
    })
    fireEvent.click(storySchemaPanel.getByRole("button", { name: "保存规则" }))

    expect(onStorySchemaGenreSelect).toHaveBeenCalledWith(null)
    expect(onStorySchemaOverrideTextChange).toHaveBeenCalledWith(
      "规则名称：项目规则\n实体类型：物件\n事件类型：无\n关系：守护\n抽取提示：无\n风险规则：无",
    )
    expect(onStorySchemaOverrideSave).toHaveBeenCalled()
    expect(storySchemaPanel.getByText("类型规则已保存")).toBeInTheDocument()
    expect(storySchemaPanel.getByText("规则已保存")).toBeInTheDocument()
    expect(storySchemaPanel.queryByText(/pack_name|entity_types|relations|risk_rules|mystery\.v1/)).toBeNull()
  })

  it("lets the author inspect, upsert, and revoke project members", () => {
    const onProjectMemberUpsert = vi.fn()
    const onProjectMemberRevoke = vi.fn()

    render(
      <ProjectPanel
        source={source}
        sourceVersions={[]}
        sourceVersionsLoading={false}
        sourceVersionsError={null}
        sources={[]}
        sourceSearch=""
        sourceListLoading={false}
        sourceListError={null}
        projectMembers={[
          {
            id: "membership-owner",
            project_id: "project-1",
            actor_id: "actor-owner",
            role: "owner",
            status: "active",
            created_at: "2026-06-01T00:00:00Z",
          },
          {
            id: "membership-viewer",
            project_id: "project-1",
            actor_id: "actor-viewer",
            role: "viewer",
            status: "active",
            created_at: "2026-06-01T00:00:00Z",
          },
        ]}
        projectMemberOperationStatus="成员已更新。"
        onProjectMemberUpsert={onProjectMemberUpsert}
        onProjectMemberRevoke={onProjectMemberRevoke}
        sourceDeltas={[]}
        sourceDeltaSearch=""
        sourceDeltaStatus=""
        sourceDeltaKind=""
        sourceDeltaDetail={null}
        sourceDeltasNextCursor={null}
        sourceDeltaDetailLoading={false}
        sourceDeltaDetailError={null}
        loading={false}
        error={null}
        onClose={vi.fn()}
      />,
    )

    const memberPanels = screen.getAllByTestId("project-members")
    const membersPanel = within(memberPanels[memberPanels.length - 1])

    expect(membersPanel.getByText("所有者 1")).toBeInTheDocument()
    expect(membersPanel.getByText("读者 2")).toBeInTheDocument()

    fireEvent.change(membersPanel.getByLabelText("成员编号"), {
      target: { value: "actor-editor" },
    })
    fireEvent.change(membersPanel.getByLabelText("成员角色"), {
      target: { value: "editor" },
    })
    fireEvent.click(membersPanel.getByRole("button", { name: "添加或更新成员" }))
    fireEvent.click(membersPanel.getByRole("button", { name: "撤销成员 读者 2" }))

    expect(onProjectMemberUpsert).toHaveBeenCalledWith("actor-editor", "editor")
    expect(onProjectMemberRevoke).toHaveBeenCalledWith("actor-viewer")
    expect(membersPanel.getByText("成员已更新。")).toBeInTheDocument()
    expect(membersPanel.queryByText(/actor-owner|actor-viewer|[0-9a-f]{8}\.\.\./i)).toBeNull()
  })

  it("records project invitation intent and external proof through explicit callbacks", () => {
    const onProjectInvitationCreate = vi.fn()
    const onProjectInvitationProof = vi.fn()
    const invitation: ProjectInvitationResponse = {
      id: "invitation-1",
      project_id: "project-1",
      member_actor_id: "actor-invited",
      role: "editor",
      delivery_provider_ref: "ses://sextant-prod/invitations",
      delivery_target_ref: "ses://sextant-prod/recipient/actor-invited",
      token_issuer_ref: "auth0://sextant-prod/clients/web",
      delivery_proof_ref: null,
      token_proof_ref: null,
      status: "pending_external_delivery",
      delivery_status: "not_sent",
      token_status: "not_issued",
      delivered_at: null,
      token_issued_at: null,
      created_at: "2026-06-19T00:00:00Z",
    }

    render(
      <ProjectPanel
        source={source}
        sourceVersions={[]}
        sourceVersionsLoading={false}
        sourceVersionsError={null}
        sources={[]}
        sourceSearch=""
        sourceListLoading={false}
        sourceListError={null}
        sourceDeltas={[]}
        sourceDeltaSearch=""
        sourceDeltaStatus=""
        sourceDeltaKind=""
        sourceDeltaDetail={null}
        sourceDeltasNextCursor={null}
        sourceDeltaDetailLoading={false}
        sourceDeltaDetailError={null}
        projectInvitations={[invitation]}
        projectInvitationsLoading={false}
        projectInvitationsError={null}
        projectInvitationOperationStatus="邀请已记录。"
        loading={false}
        error={null}
        onProjectInvitationCreate={onProjectInvitationCreate}
        onProjectInvitationProof={onProjectInvitationProof}
        onClose={vi.fn()}
      />,
    )

    const membersPanel = screen.getByTestId("project-members")
    expect(within(membersPanel).getByText("邀请 · 编辑者")).toBeInTheDocument()
    expect(within(membersPanel).getByText("递送未记录 · Token 未签发")).toBeInTheDocument()

    fireEvent.change(within(membersPanel).getByLabelText("邀请对象编号"), {
      target: { value: "actor-new" },
    })
    fireEvent.change(within(membersPanel).getByLabelText("邀请对象角色"), {
      target: { value: "viewer" },
    })
    fireEvent.change(within(membersPanel).getByLabelText("邀请递送服务"), {
      target: { value: "ses://sextant-prod/invitations" },
    })
    fireEvent.change(within(membersPanel).getByLabelText("邀请递送目标"), {
      target: { value: "ses://sextant-prod/recipient/actor-new" },
    })
    fireEvent.change(within(membersPanel).getByLabelText("邀请 Token 签发"), {
      target: { value: "auth0://sextant-prod/clients/web" },
    })
    fireEvent.click(within(membersPanel).getByRole("button", { name: "记录邀请意图" }))

    fireEvent.change(within(membersPanel).getByLabelText("邀请递送证明"), {
      target: { value: "ses://sextant-prod/messages/new-delivery" },
    })
    fireEvent.change(within(membersPanel).getByLabelText("邀请 Token 证明"), {
      target: { value: "auth0://sextant-prod/tickets/new-token" },
    })
    fireEvent.click(within(membersPanel).getByRole("button", { name: "记录外部证明 邀请 1" }))

    expect(onProjectInvitationCreate).toHaveBeenCalledWith({
      memberActorId: "actor-new",
      role: "viewer",
      deliveryProviderRef: "ses://sextant-prod/invitations",
      deliveryTargetRef: "ses://sextant-prod/recipient/actor-new",
      tokenIssuerRef: "auth0://sextant-prod/clients/web",
    })
    expect(onProjectInvitationProof).toHaveBeenCalledWith("invitation-1", {
      deliveryProofRef: "ses://sextant-prod/messages/new-delivery",
      tokenProofRef: "auth0://sextant-prod/tickets/new-token",
    })
  })

  it("renders source deltas without raw storage refs or backend status tokens", () => {
    render(
      <ProjectPanel
        source={source}
        sourceVersions={[]}
        sourceVersionsLoading={false}
        sourceVersionsError={null}
        sources={[]}
        sourceSearch=""
        sourceListLoading={false}
        sourceListError={null}
        sourceDeltas={[
          {
            id: "d071f0e3-2b40-4332-a61e-b9679482ec01",
            source_id: "source-1",
            previous_version_id: "version-1",
            new_version_id: "version-2",
            accepted_fragment_id: "fragment-1",
            delta_kind: "replace",
            status: "memory_writeback_completed",
            range_start: 0,
            range_end: 12,
            base_hash: "hash-v1",
            source_type: "draft_manuscript",
            source_scope: "user_draft",
            provenance: {},
            submitted_text_ref: "object://local/submitted.txt",
            submitted_text_preview: "米拉停在西档案室门口。",
            job: null,
            created_at: "2026-06-11T08:00:00Z",
          },
        ]}
        sourceDeltaSearch=""
        sourceDeltaStatus=""
        sourceDeltaKind=""
        sourceDeltaDetail={{
          id: "d071f0e3-2b40-4332-a61e-b9679482ec01",
          source_id: "source-1",
          previous_version_id: "version-1",
          new_version_id: "version-2",
          accepted_fragment_id: "fragment-1",
          delta_kind: "replace",
          status: "memory_writeback_completed",
          range_start: 0,
          range_end: 12,
          base_hash: "hash-v1",
          source_type: "draft_manuscript",
          source_scope: "user_draft",
          provenance: {},
          submitted_text_ref: "object://local/submitted.txt",
          submitted_text: "米拉停在西档案室门口。",
          job: null,
        }}
        sourceDeltasNextCursor={null}
        sourceDeltaDetailLoading={false}
        sourceDeltaDetailError={null}
        loading={false}
        error={null}
        onClose={vi.fn()}
      />,
    )

    const sourceDeltas = screen.getByTestId("project-source-deltas")
    expect(within(sourceDeltas).getByText("正文变更")).toBeVisible()
    expect(within(sourceDeltas).getByText("替换 · 回写完成")).toBeVisible()
    expect(within(sourceDeltas).getByRole("button", { name: "打开正文变更 1" })).toBeVisible()
    expect(within(sourceDeltas).getByText("正文变更详情")).toBeVisible()
    expect(within(sourceDeltas).getByText("正文对象已保存")).toBeVisible()
    expect(within(sourceDeltas).queryByLabelText(/d071f0e3|打开正文变更 d071f0e3/)).toBeNull()
    expect(within(sourceDeltas).queryByText(/SourceDelta|memory_writeback_completed/)).toBeNull()
    expect(within(sourceDeltas).queryByText(/object:\/\/|hash-v1/)).toBeNull()
  })
})
