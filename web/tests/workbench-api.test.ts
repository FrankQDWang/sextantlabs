import { describe, expect, it, vi } from "vitest"
import {
  acceptCandidateText,
  answerWorkbenchMemory,
  archiveWorkbenchSource,
  buildWorkbenchContextPack,
  cancelWorkbenchJob,
  decideWorkbenchWritebackItem,
  explainWorkbenchCandidate,
  createWorkbenchSource,
  createWorkbenchProjectInvitation,
  formatContextRefLabel,
  listWorkbenchProjectInvitations,
  loadLatestAcceptedText,
  loadWorkbenchMemoryPageDetail,
  loadWorkbenchMemoryPages,
  loadWorkbenchEntities,
  loadWorkbenchProjectMembers,
  loadReviewItemDetail,
  loadWorkbenchContextPack,
  loadWorkbenchContextPackReadiness,
  loadWorkbenchGraphProjectionEdges,
  loadWorkbenchStorySchema,
  loadWorkbenchStorySchemaPacks,
  loadWorkbenchSource,
  loadWorkbenchSourceVersionDiff,
  loadWorkbenchSourceDeltaDetail,
  loadWorkbenchSourceDeltaPage,
  loadWorkbenchSourceDeltas,
  loadWorkbenchSourceVersions,
  loadWorkbenchSources,
  loadWorkbenchReviewItems,
  loadWorkbenchSceneOptions,
  operateWorkbenchMemoryPageThread,
  operateWorkbenchReviewItem,
  overrideWorkbenchCandidateBlock,
  readWorkbenchWritebackState,
  readWorkbenchAuthConfig,
  readWorkbenchApiConfig,
  rejectWorkbenchCandidate,
  recordWorkbenchProjectInvitationExternalProof,
  requestContinuationCandidate,
  requestNextDirection,
  requestRiskCheck,
  requestRewriteCandidate,
  revokeWorkbenchProjectMember,
  retryWorkbenchJob,
  restoreWorkbenchSourceVersion,
  reviseWorkbenchCandidate,
  saveWorkbenchSourceEdit,
  selectWorkbenchStorySchemaGenrePack,
  toDrawerBeatCandidates,
  toDrawerCandidate,
  toDrawerRiskCandidates,
  upsertWorkbenchProjectMember,
  upsertWorkbenchStorySchemaOverride,
  workbenchErrorMessage,
  signInWorkbenchWithPassword,
} from "../lib/workbench-api"
import { SextantApiError, type CandidateDetailResponse } from "../src/generated/sextant-api"

const candidate: CandidateDetailResponse = {
  id: "candidate-1",
  action_request_id: "ar-1",
  mode: "rewrite_span",
  text: "米拉停在门口。她没有说出尚未确认的事。",
  status: "offered_to_author",
  override_reason: null,
  context_pack_id: "context-1",
  target_source_id: "source-1",
  target_version_id: "version-1",
  target_scene_id: null,
  affected_range: { start: 4, end: 16 },
  base_hash: "hash-v1",
  memory_refs: [],
  evidence_refs: [{ type: "source_span", id: "span-1" }],
  agent_review_findings: [],
}

describe("workbench API adapter", () => {
  it("formats context refs with author-readable labels instead of raw UUIDs", () => {
    expect(
      formatContextRefLabel({
        type: "character",
        id: "bff4cfc2-1c42-46a6-8c33-4d1ab05d8e5a",
        label: "Mira",
      }),
    ).toBe("Mira")

    expect(
      formatContextRefLabel({
        type: "object",
        id: "lantern-map",
      }),
    ).toBe("lantern-map")

    expect(
      formatContextRefLabel({
        type: "character",
        id: "bff4cfc2-1c42-46a6-8c33-4d1ab05d8e5a",
      }),
    ).toBe("character")
  })

  it("requires real backend identifiers before enabling API mode", () => {
    expect(readWorkbenchApiConfig({ VITE_SEXTANT_API_BASE_URL: "http://api.test" })).toBeNull()

    expect(
      readWorkbenchApiConfig({
        VITE_SEXTANT_API_BASE_URL: "http://api.test",
        VITE_SEXTANT_PROJECT_ID: "project-1",
        VITE_SEXTANT_ACTOR_ID: "actor-1",
        VITE_SEXTANT_BEARER_TOKEN: "jwt-token",
        VITE_SEXTANT_SOURCE_ID: "source-1",
        VITE_SEXTANT_SOURCE_VERSION_ID: "version-1",
        VITE_SEXTANT_SCENE_ID: "scene-1",
        VITE_SEXTANT_POV_CHARACTER_ID: "mira-1",
      }),
    ).toEqual({
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      bearerToken: "jwt-token",
      sourceId: "source-1",
      sourceVersionId: "version-1",
      sceneId: "scene-1",
      povCharacterId: "mira-1",
    })
  })

  it("reads Supabase Auth public runtime config separately from static bearer tokens", () => {
    expect(
      readWorkbenchAuthConfig({
        VITE_SEXTANT_SUPABASE_URL: "https://auth.test/",
        VITE_SEXTANT_SUPABASE_PUBLISHABLE_KEY: "publishable-key",
      }),
    ).toEqual({
      supabaseUrl: "https://auth.test",
      publishableKey: "publishable-key",
    })

    expect(readWorkbenchAuthConfig({ VITE_SEXTANT_SUPABASE_URL: "https://auth.test" })).toBeNull()
  })

  it("exchanges author credentials for a runtime Supabase access token", async () => {
    const fetcher = vi.fn().mockResolvedValue(
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

    const session = await signInWorkbenchWithPassword(
      { supabaseUrl: "https://auth.test/", publishableKey: "publishable-key" },
      { email: "author@example.com", password: "secret-password" },
      fetcher,
    )

    expect(fetcher).toHaveBeenCalledWith(
      "https://auth.test/auth/v1/token?grant_type=password",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          apikey: "publishable-key",
        },
        body: JSON.stringify({
          email: "author@example.com",
          password: "secret-password",
        }),
      },
    )
    expect(session.accessToken).toBe("runtime-jwt")
    expect(session.refreshToken).toBe("refresh-token")
    expect(session.expiresAt).toBeGreaterThan(Math.floor(Date.now() / 1000))
  })

  it("creates ActionRequest, runs it, and reads candidate detail", async () => {
    const client = {
      submitActionRequest: vi.fn().mockResolvedValue({
        action_request_id: "ar-1",
        status: "submitted",
      }),
      runActionRequest: vi.fn().mockResolvedValue({
        action_request_id: "ar-1",
        status: "succeeded",
        context_pack_id: "context-1",
        draft_candidate_ids: ["candidate-1"],
        risk_finding_ids: [],
      }),
      getCandidate: vi.fn().mockResolvedValue(candidate),
    }

    const detail = await requestRewriteCandidate(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        bearerToken: "jwt-token",
        sourceId: "source-1",
        sourceVersionId: "version-1",
      },
      {
        text: "钥匙是冷的",
        range: { start: 4, end: 16 },
        actorIntent: "改写得更克制",
        currentTextWindow: "Mira 把钥匙放在两人之间。钥匙是冷的。",
      },
      () => "fixed-id",
    )

    expect(detail).toBe(candidate)
    expect(client.submitActionRequest).toHaveBeenCalledWith(
      "project-1",
      expect.objectContaining({
        action_type: "rewrite_span",
        source_id: "source-1",
        source_version_id: "version-1",
        target: {
          kind: "selected_text",
          source_id: "source-1",
          source_version_id: "version-1",
          range: { start: 4, end: 16 },
          selected_text: "钥匙是冷的",
        },
      }),
      {
        actorId: "actor-1",
        bearerToken: "jwt-token",
        requestId: "req-fixed-id",
        idempotencyKey: "idem-fixed-id",
      },
    )
    expect(client.runActionRequest).toHaveBeenCalledWith(
      "project-1",
      "ar-1",
      { current_text_window: "Mira 把钥匙放在两人之间。钥匙是冷的。" },
      {
        actorId: "actor-1",
        bearerToken: "jwt-token",
        requestId: "req-fixed-id",
        idempotencyKey: "idem-fixed-id",
      },
    )
    expect(client.getCandidate).toHaveBeenCalledWith(
      "project-1",
      "candidate-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
    )
  })

  it("creates an Ask continuation ActionRequest without provider test hooks", async () => {
    const client = {
      submitActionRequest: vi.fn().mockResolvedValue({
        action_request_id: "ar-2",
        status: "submitted",
      }),
      runActionRequest: vi.fn().mockResolvedValue({
        action_request_id: "ar-2",
        status: "succeeded",
        context_pack_id: "context-1",
        draft_candidate_ids: ["candidate-1"],
        risk_finding_ids: [],
      }),
      getCandidate: vi.fn().mockResolvedValue(candidate),
    }

    const detail = await requestContinuationCandidate(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
      },
      {
        actorIntent: "试写有争议版本",
        currentTextWindow: "Mira 把钥匙放在两人之间。",
        insertOffset: 12,
      },
      () => "ask-id",
    )

    expect(detail).toBe(candidate)
    expect(client.submitActionRequest).toHaveBeenCalledWith(
      "project-1",
      expect.objectContaining({
        trigger: "natural_language",
        action_type: "continue_small_passage",
        actor_intent: "试写有争议版本",
        target: {
          kind: "current_position",
          source_id: "source-1",
          source_version_id: "version-1",
          range: { start: 12, end: 12 },
        },
        constraints: {
          ui_surface: "workbench.ask_palette",
        },
      }),
      { actorId: "actor-1", requestId: "req-ask-id", idempotencyKey: "idem-ask-id" },
    )
  })

  it("accepts browser text through the backend object-store path", async () => {
    const client = {
      acceptCandidate: vi.fn().mockResolvedValue({
        accepted_fragment_id: "fragment-1",
        source_delta_id: "delta-1",
        new_version_id: "version-2",
        memory_writeback_job_id: "job-1",
      }),
    }

    const result = await acceptCandidateText(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
      },
      candidate,
      "米拉停在门口。",
      () => "accept-id",
    )

    expect(result.memory_writeback_job_id).toBe("job-1")
    expect(client.acceptCandidate).toHaveBeenCalledWith(
      "project-1",
      "candidate-1",
      {
        accepted_text: "米拉停在门口。",
        accepted_text_ref: null,
        accept_mode: "partial",
        target_source_id: "source-1",
        target_version_id: "version-1",
        insert_or_replace_range: { start: 4, end: 16 },
        base_hash: "hash-v1",
        source_type: "draft_manuscript",
        source_scope: "user_draft",
        author_edited: true,
      },
      { actorId: "actor-1", requestId: "req-accept-id", idempotencyKey: "idem-accept-id" },
    )
  })

  it("loads source text and writeback state through read APIs", async () => {
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      bearerToken: "jwt-token",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }
    const sourceClient = {
      getSourceVersion: vi.fn().mockResolvedValue({
        source_id: "source-1",
        version_id: "version-1",
        title: "Ch.03 西档案室",
        source_type: "draft_manuscript",
        source_scope: "user_draft",
        version_label: "v1",
        raw_hash: "hash-v1",
        text: "第一段。\n第二段。",
      }),
      listSourceVersions: vi.fn().mockResolvedValue({
        items: [
          {
            source_id: "source-1",
            version_id: "version-2",
            version_label: "v2",
            raw_hash: "hash-v2",
            raw_text_ref: "object://source/v2",
            supersedes_version_id: "version-1",
            created_at: "2026-06-01T00:00:00Z",
          },
          {
            source_id: "source-1",
            version_id: "version-1",
            version_label: "v1",
            raw_hash: "hash-v1",
            raw_text_ref: "object://source/v1",
            supersedes_version_id: null,
            created_at: "2026-05-31T00:00:00Z",
          },
        ],
      }),
    }
    const writebackClient = {
      getJob: vi.fn().mockResolvedValue({
        id: "job-1",
        job_type: "run_memory_writeback",
        status: "succeeded",
        attempt_count: 1,
        run_after: null,
        locked_by: "worker-1",
        locked_at: null,
        last_error: null,
        payload: { source_delta_id: "delta-1" },
      }),
      getMemoryWritebackPreview: vi.fn().mockResolvedValue({
        source_delta_id: "delta-1",
        source_delta_status: "memory_writeback_completed",
        source_delta: {},
        job: null,
        source_spans: [{ id: "span-1" }],
        evidence_log_entries: [{ id: "evidence-1" }],
        fact_assertions: [{ id: "fact-1", fact_status: "canon" }],
        review_items: [],
        memory_pages: [{ id: "page-1", title: "mira" }],
        graph_edges: [{ id: "edge-1" }],
      }),
      listReviewItems: vi.fn().mockResolvedValue({ items: [] }),
    }

    const source = await loadWorkbenchSource(sourceClient, config)
    const versions = await loadWorkbenchSourceVersions(sourceClient, config)
    const state = await readWorkbenchWritebackState(writebackClient, config, {
      accepted_fragment_id: "fragment-1",
      source_delta_id: "delta-1",
      new_version_id: "version-2",
      memory_writeback_job_id: "job-1",
    })

    expect(source.text).toBe("第一段。\n第二段。")
    expect(versions.map((version) => version.version_label)).toEqual(["v2", "v1"])
    expect(state.preview.source_spans).toHaveLength(1)
    expect(sourceClient.getSourceVersion).toHaveBeenCalledWith(
      "project-1",
      "source-1",
      "version-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
    )
    expect(sourceClient.listSourceVersions).toHaveBeenCalledWith(
      "project-1",
      "source-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
      { limit: 12 },
    )
    expect(writebackClient.getMemoryWritebackPreview).toHaveBeenCalledWith(
      "project-1",
      "delta-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
    )
  })

  it("restores a source version through the backend restore API", async () => {
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      bearerToken: "jwt-token",
      sourceId: "source-1",
      sourceVersionId: "version-2",
    }
    const client = {
      restoreSourceVersion: vi.fn().mockResolvedValue({
        source_id: "source-1",
        restored_from_version_id: "version-1",
        source_delta_id: "delta-restore",
        new_version_id: "version-3",
        memory_writeback_job_id: "job-restore",
      }),
    }

    const restored = await restoreWorkbenchSourceVersion(
      client,
      config,
      "version-1",
      () => "restore-id",
    )

    expect(restored.new_version_id).toBe("version-3")
    expect(client.restoreSourceVersion).toHaveBeenCalledWith(
      "project-1",
      "source-1",
      "version-1",
      { author_note: "作者从正文版本历史恢复此版本。" },
      {
        actorId: "actor-1",
        requestId: "req-restore-id",
        idempotencyKey: "idem-restore-id",
        bearerToken: "jwt-token",
      },
    )
  })

  it("loads source version diff through the backend diff API", async () => {
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      bearerToken: "jwt-token",
      sourceId: "source-1",
      sourceVersionId: "version-2",
    }
    const client = {
      getSourceVersionDiff: vi.fn().mockResolvedValue({
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
            lines: [{ kind: "insert", old_line: null, new_line: 4, text: "新增行" }],
          },
        ],
      }),
    }

    const diff = await loadWorkbenchSourceVersionDiff(
      client,
      config,
      "version-1",
      "version-2",
    )

    expect(diff.summary).toEqual({ insertions: 2, deletions: 1, changed: true })
    expect(client.getSourceVersionDiff).toHaveBeenCalledWith(
      "project-1",
      "source-1",
      "version-1",
      "version-2",
      { actorId: "actor-1", bearerToken: "jwt-token" },
    )
  })

  it("saves a source edit as a minimal backend SourceDelta", async () => {
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      bearerToken: "jwt-token",
      sourceId: "source-1",
      sourceVersionId: "version-2",
    }
    const source = {
      source_id: "source-1",
      version_id: "version-2",
      title: "Ch.03 西档案室",
      source_type: "draft_manuscript",
      source_scope: "user_draft",
      version_label: "v2",
      raw_hash: "hash-v2",
      text: "第一行\n第二行\n第三行",
    }
    const client = {
      createSourceDelta: vi.fn().mockResolvedValue({
        source_delta_id: "delta-edit",
        new_version_id: "version-3",
        memory_writeback_job_id: "job-edit",
      }),
    }

    const saved = await saveWorkbenchSourceEdit(
      client,
      config,
      source,
      "第一行\n第二行改\n第三行",
      () => "edit-id",
    )

    expect(saved.new_version_id).toBe("version-3")
    expect(client.createSourceDelta).toHaveBeenCalledWith(
      "project-1",
      "source-1",
      "version-2",
      {
        delta_kind: "insert",
        range_start: 7,
        range_end: 7,
        base_hash: "hash-v2",
        submitted_text: "改",
        source_type: "draft_manuscript",
        source_scope: "user_draft",
        provenance: {
          source_edit_surface: "workbench_editor",
          previous_version_id: "version-2",
        },
      },
      {
        actorId: "actor-1",
        requestId: "req-edit-id",
        idempotencyKey: "idem-edit-id",
        bearerToken: "jwt-token",
      },
    )
  })

  it("lists and creates sources through backend source APIs", async () => {
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }
    const client = {
      listSources: vi.fn().mockResolvedValue({
        items: [
          {
            source_id: "source-1",
            title: "西档案室",
            source_type: "draft_manuscript",
            source_scope: "user_draft",
            ownership_status: "owned",
            latest_version_id: "version-1",
            latest_version_label: "v1",
            latest_raw_hash: "hash-v1",
            version_count: 1,
          },
        ],
      }),
      createSource: vi.fn().mockResolvedValue({
        source_id: "source-2",
        version_id: "version-2",
        source_delta_id: "delta-2",
        memory_writeback_job_id: "job-2",
        raw_hash: "hash-v2",
      }),
      archiveSource: vi.fn().mockResolvedValue({
        source_id: "source-2",
        status: "archived",
        archived_at: "2026-06-01T00:00:00Z",
        archived_by: "actor-1",
      }),
    }

    const sources = await loadWorkbenchSources(client, config, "西档案")
    const created = await createWorkbenchSource(
      client,
      config,
      {
        title: "角色备忘",
        sourceType: "author_notes",
        sourceScope: "author_note",
        text: "Mira 不确定钥匙来源。",
      },
      () => "source-id",
    )
    const archived = await archiveWorkbenchSource(
      client,
      config,
      created.source_id,
      () => "archive-id",
    )

    expect(sources[0].title).toBe("西档案室")
    expect(created.source_id).toBe("source-2")
    expect(created.source_delta_id).toBe("delta-2")
    expect(created.memory_writeback_job_id).toBe("job-2")
    expect(archived.status).toBe("archived")
    expect(client.listSources).toHaveBeenCalledWith(
      "project-1",
      { actorId: "actor-1" },
      { query: "西档案", limit: 20 },
    )
    expect(client.createSource).toHaveBeenCalledWith(
      "project-1",
      {
        title: "角色备忘",
        source_type: "author_notes",
        source_scope: "author_note",
        ownership_status: "owned",
        text: "Mira 不确定钥匙来源。",
        version_label: "v1",
      },
      { actorId: "actor-1", requestId: "req-source-id", idempotencyKey: "idem-source-id" },
    )
    expect(client.archiveSource).toHaveBeenCalledWith(
      "project-1",
      "source-2",
      { author_note: "作者将材料从当前项目列表归档；证据和版本仍保留。" },
      { actorId: "actor-1", requestId: "req-archive-id", idempotencyKey: "idem-archive-id" },
    )
  })

  it("reads latest accepted text from SourceDelta so refresh is backend-backed", async () => {
    const client = {
      listSourceDeltas: vi.fn().mockResolvedValue({
        items: [
          {
            id: "delta-1",
            source_id: "source-1",
            previous_version_id: "version-1",
            new_version_id: "version-2",
            accepted_fragment_id: "fragment-1",
            delta_kind: "replace",
            status: "memory_writeback_completed",
            range_start: 10,
            range_end: 10,
            base_hash: "hash-v1",
            source_type: "draft_manuscript",
            source_scope: "user_draft",
            provenance: {},
            submitted_text_ref: "objects/delta-1.txt",
            submitted_text_preview: "米拉停在西档案室门口。",
            job: null,
          },
        ],
        next_cursor: null,
      }),
    }

    const text = await loadLatestAcceptedText(client, {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    })

    expect(text).toBe("米拉停在西档案室门口。")
    expect(client.listSourceDeltas).toHaveBeenCalledWith(
      "project-1",
      { actorId: "actor-1" },
      { sourceId: "source-1", limit: 10 },
    )
  })

  it("passes SourceDelta search and filter options to the backend", async () => {
    const client = {
      listSourceDeltas: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    }

    await loadWorkbenchSourceDeltas(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
      },
      {
        query: "灯图",
        status: "memory_writeback_completed",
        deltaKind: "replace",
        sourceVersionId: "version-2",
      },
    )

    expect(client.listSourceDeltas).toHaveBeenCalledWith(
      "project-1",
      { actorId: "actor-1" },
      {
        sourceId: "source-1",
        sourceVersionId: "version-2",
        query: "灯图",
        status: "memory_writeback_completed",
        deltaKind: "replace",
        limit: 10,
      },
    )
  })

  it("passes SourceDelta cursor and returns page metadata", async () => {
    const client = {
      listSourceDeltas: vi.fn().mockResolvedValue({
        items: [],
        next_cursor: "cursor-2",
      }),
    }

    const page = await loadWorkbenchSourceDeltaPage(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
      },
      { query: "灯图", cursor: "cursor-1" },
    )

    expect(page.next_cursor).toBe("cursor-2")
    expect(client.listSourceDeltas).toHaveBeenCalledWith(
      "project-1",
      { actorId: "actor-1" },
      {
        sourceId: "source-1",
        query: "灯图",
        cursor: "cursor-1",
        limit: 10,
      },
    )
  })

  it("retries transient SourceDelta read fetch failures", async () => {
    const listClient = {
      listSourceDeltas: vi.fn()
        .mockRejectedValueOnce(new TypeError("Failed to fetch"))
        .mockResolvedValueOnce({
          items: [],
          next_cursor: null,
        }),
    }
    const detailClient = {
      getSourceDelta: vi.fn()
        .mockRejectedValueOnce(new TypeError("Failed to fetch"))
        .mockResolvedValueOnce({
          id: "delta-1",
          source_id: "source-1",
          previous_version_id: "version-1",
          new_version_id: "version-2",
          accepted_fragment_id: "fragment-1",
          delta_kind: "replace",
          status: "memory_writeback_completed",
          range_start: 10,
          range_end: 10,
          base_hash: "hash-v1",
          source_type: "draft_manuscript",
          source_scope: "user_draft",
          provenance: {},
          submitted_text_ref: "objects/delta-1.txt",
          submitted_text: "米拉停在西档案室门口。",
          job: null,
        }),
    }
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }

    const page = await loadWorkbenchSourceDeltaPage(listClient, config)
    const detail = await loadWorkbenchSourceDeltaDetail(detailClient, config, "delta-1")

    expect(page.next_cursor).toBeNull()
    expect(detail.submitted_text).toBe("米拉停在西档案室门口。")
    expect(listClient.listSourceDeltas).toHaveBeenCalledTimes(2)
    expect(detailClient.getSourceDelta).toHaveBeenCalledTimes(2)
  })

  it("loads SourceDelta detail through the backend", async () => {
    const client = {
      getSourceDelta: vi.fn().mockResolvedValue({
        id: "delta-1",
        source_id: "source-1",
        previous_version_id: "version-1",
        new_version_id: "version-2",
        accepted_fragment_id: "fragment-1",
        delta_kind: "replace",
        status: "memory_writeback_completed",
        range_start: 10,
        range_end: 10,
        base_hash: "hash-v1",
        source_type: "draft_manuscript",
        source_scope: "user_draft",
        provenance: {},
        submitted_text_ref: "objects/delta-1.txt",
        submitted_text: "米拉停在西档案室门口。",
        job: null,
      }),
    }

    const detail = await loadWorkbenchSourceDeltaDetail(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
      },
      "delta-1",
    )

    expect(detail.submitted_text).toBe("米拉停在西档案室门口。")
    expect(client.getSourceDelta).toHaveBeenCalledWith(
      "project-1",
      "delta-1",
      { actorId: "actor-1" },
    )
  })

  it("sends job control operations through write headers", async () => {
    const client = {
      cancelJob: vi.fn().mockResolvedValue({ status: "cancelled" }),
      retryJob: vi.fn().mockResolvedValue({ status: "queued" }),
    }
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }

    await cancelWorkbenchJob(client, config, "job-1", "暂停这次回写", () => "cancel-job-id")
    await retryWorkbenchJob(client, config, "job-1", "立即重试", () => "retry-job-id")

    expect(client.cancelJob).toHaveBeenCalledWith(
      "project-1",
      "job-1",
      { author_note: "暂停这次回写" },
      { actorId: "actor-1", requestId: "req-cancel-job-id", idempotencyKey: "idem-cancel-job-id" },
    )
    expect(client.retryJob).toHaveBeenCalledWith(
      "project-1",
      "job-1",
      { author_note: "立即重试" },
      { actorId: "actor-1", requestId: "req-retry-job-id", idempotencyKey: "idem-retry-job-id" },
    )
  })

  it("persists writeback item decisions through the backend", async () => {
    const client = {
      decideMemoryWritebackPreview: vi.fn().mockResolvedValue({
        decision_id: "decision-1",
        source_delta_id: "delta-1",
        item_ref: { type: "fact_assertion", id: "fact-1" },
        decision: "correct",
        status: "recorded",
        side_effects: { fact_assertion_status: "disputed" },
      }),
    }

    const result = await decideWorkbenchWritebackItem(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
      },
      {
        accepted_fragment_id: "fragment-1",
        source_delta_id: "delta-1",
        new_version_id: "version-2",
        memory_writeback_job_id: "job-1",
      },
      {
        itemRef: { type: "fact_assertion", id: "fact-1" },
        decision: "correct",
        authorNote: "关系需要改。",
        correction: { predicate: "carries" },
        replacementRefs: [{ type: "source_delta", id: "delta-2" }],
      },
      () => "decision-id",
    )

    expect(result.status).toBe("recorded")
    expect(client.decideMemoryWritebackPreview).toHaveBeenCalledWith(
      "project-1",
      "delta-1",
      {
        item_ref: { type: "fact_assertion", id: "fact-1" },
        decision: "correct",
        author_note: "关系需要改。",
        correction: { predicate: "carries" },
        replacement_refs: [{ type: "source_delta", id: "delta-2" }],
      },
      { actorId: "actor-1", requestId: "req-decision-id", idempotencyKey: "idem-decision-id" },
    )
  })

  it("loads review item detail through the backend", async () => {
    const client = {
      getReviewItem: vi.fn().mockResolvedValue({
        id: "review-1",
        review_type: "knowledge_conflict",
        severity: "medium",
        status: "open",
        summary: "Mira may know too much.",
        affected_refs: {},
        new_evidence: {},
        existing_evidence: {},
        suggested_actions: [],
        default_action: "ask_author",
        resolution: null,
        side_effects: {},
      }),
    }

    const detail = await loadReviewItemDetail(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
      },
      "review-1",
    )

    expect(detail.summary).toContain("Mira")
    expect(client.getReviewItem).toHaveBeenCalledWith(
      "project-1",
      "review-1",
      { actorId: "actor-1" },
    )
  })

  it("loads the initial backend review queue instead of demo ids", async () => {
    const client = {
      listReviewItems: vi.fn().mockResolvedValue({
        items: [
          {
            id: "review-1",
            review_type: "knowledge_conflict",
            severity: "medium",
            status: "open",
            summary: "Mira may know too much.",
            affected_refs: {},
            new_evidence: {},
            existing_evidence: {},
            suggested_actions: [],
            default_action: "ask_author",
            resolution: null,
            side_effects: {},
          },
        ],
      }),
    }

    const items = await loadWorkbenchReviewItems(client, {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    })

    expect(items).toHaveLength(1)
    expect(client.listReviewItems).toHaveBeenCalledWith(
      "project-1",
      { actorId: "actor-1" },
      "open",
    )
  })

  it("loads canonical entities from the backend for alias correction", async () => {
    const client = {
      listEntities: vi.fn().mockResolvedValue({
        items: [
          {
            id: "entity-1",
            entity_type: "character",
            display_name: "Mira",
            canonical_status: "provisional",
            cast_tier: "unknown",
            first_seen_scene_id: null,
          },
        ],
      }),
    }

    const entities = await loadWorkbenchEntities(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
      },
      { query: "mir", entityType: "character", limit: 10 },
    )

    expect(entities.items[0]?.display_name).toBe("Mira")
    expect(client.listEntities).toHaveBeenCalledWith(
      "project-1",
      { actorId: "actor-1" },
      { q: "mir", entity_type: "character", limit: 10 },
    )
  })

  it("loads scene options from the backend for alias boundary correction", async () => {
    const client = {
      listScenes: vi.fn().mockResolvedValue({
        items: [
          {
            id: "scene-1",
            source_id: "source-1",
            version_id: "version-1",
            chapter_id: "chapter-1",
            chapter_index: 0,
            chapter_title: "The Harbor",
            scene_index: 0,
            position_label: "Chapter 1 / Scene 1",
            story_time: "Night 1",
            scene_summary: "Mira enters the harbor.",
            pov_character_id: null,
            pov_mode: null,
          },
        ],
      }),
    }

    const scenes = await loadWorkbenchSceneOptions(client, {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    })

    expect(scenes.items[0]?.position_label).toBe("Chapter 1 / Scene 1")
    expect(client.listScenes).toHaveBeenCalledWith(
      "project-1",
      { actorId: "actor-1" },
      { source_id: "source-1", version_id: "version-1", limit: 100 },
    )
  })

  it("loads candidate context pack detail through the backend", async () => {
    const client = {
      getContextPack: vi.fn().mockResolvedValue({
        context_pack_id: "context-1",
        schema_version: "writing-context-pack.v1",
        current_position: { mode: "continue_small_passage" },
        canonical_context: { facts: [] },
        pov_constraint: { forbidden_knowledge: [] },
        active_characters: [],
        character_agency_state: {},
        recent_events: [],
        character_knowledge: [],
        object_location_state: [],
        open_threads: [],
        risk_context: { facts: [], review_items: [] },
        style_memory: {},
        evidence_refs: [],
      }),
    }

    const contextPack = await loadWorkbenchContextPack(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
      },
      "context-1",
    )

    expect(contextPack.current_position.mode).toBe("continue_small_passage")
    expect(client.getContextPack).toHaveBeenCalledWith(
      "project-1",
      "context-1",
      { actorId: "actor-1" },
    )
  })

  it("loads ContextPackReadiness through the backend", async () => {
    const client = {
      listContextPackReadiness: vi.fn().mockResolvedValue({
        items: [
          {
            id: "readiness-1",
            source_span_id: "span-1",
            source_delta_id: "delta-1",
            status: "pending",
            reason: "memory_dependency_changed",
            affected_refs: [{ type: "fact_assertion", id: "fact-1" }],
            evidence_refs: [{ type: "source_span", id: "span-1" }],
          },
        ],
      }),
    }

    const readiness = await loadWorkbenchContextPackReadiness(client, {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    })

    expect(readiness.items[0].status).toBe("pending")
    expect(client.listContextPackReadiness).toHaveBeenCalledWith(
      "project-1",
      { actorId: "actor-1" },
      { status: "pending", limit: 20 },
    )
  })

  it("builds a backend scene context pack for API-mode scene card state", async () => {
    const client = {
      getContextPack: vi.fn(),
      buildContextPack: vi.fn().mockResolvedValue({
        context_pack_id: "context-1",
        schema_version: "writing-context-pack.v1",
        current_position: { mode: "review" },
        canonical_context: { facts: [] },
        pov_constraint: {},
        active_characters: [],
        character_agency_state: {},
        recent_events: [],
        character_knowledge: [],
        object_location_state: [],
        open_threads: [],
        risk_context: { facts: [], review_items: [] },
        style_memory: {},
        evidence_refs: [],
      }),
    }

    const contextPack = await buildWorkbenchContextPack(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
        sceneId: "scene-1",
        povCharacterId: "mira-1",
      },
      { mode: "review", currentTextWindow: "正文" },
      () => "scene-id",
    )

    expect(contextPack.current_position.mode).toBe("review")
    expect(client.buildContextPack).toHaveBeenCalledWith(
      "project-1",
      {
        current_source_id: "source-1",
        current_version_id: "version-1",
        current_scene_id: "scene-1",
        current_pov_character_id: "mira-1",
        mode: "review",
        current_text_window: "正文",
      },
      { actorId: "actor-1", requestId: "req-scene-id", idempotencyKey: "idem-scene-id" },
    )
  })

  it("answers Ask evidence questions without seed-story subject inference", async () => {
    const client = {
      submitActionRequest: vi.fn().mockResolvedValue({
        action_request_id: "action-memory-1",
        status: "submitted",
      }),
      runActionRequest: vi.fn().mockResolvedValue({
        action_request_id: "action-memory-1",
        status: "succeeded",
        output_type: "memory_answer",
        context_pack_id: null,
        draft_candidate_ids: [],
        risk_finding_ids: [],
        beat_candidate_ids: [],
        memory_answer: {
          question: "Mira 现在知道钥匙的来源吗？",
          answer: "No SourceSpan-backed memory evidence matches this question.",
          answer_type: "unknown",
          confidence: 0,
          source_span_refs: [],
          affected_entities: [],
          caveats: ["no_matching_evidence"],
          unknowns: ["no_matching_evidence"],
          related_review_items: [],
          safe_to_use_in_current_pov: false,
        },
      }),
    }

    const answer = await answerWorkbenchMemory(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
        sceneId: "scene-1",
        povCharacterId: "mira-1",
      },
      "Mira 现在知道钥匙的来源吗？",
      () => "answer-id",
    )

    expect(answer.answer_type).toBe("unknown")
    expect(client.submitActionRequest).toHaveBeenCalledWith(
      "project-1",
      {
        trigger: "natural_language",
        action_type: "ask_memory",
        target: null,
        constraints: {
          ui_surface: "workbench.ask_palette",
          question: "Mira 现在知道钥匙的来源吗？",
        },
        expected_output: "memory_answer",
        actor_intent: "Mira 现在知道钥匙的来源吗？",
        source_id: "source-1",
        source_version_id: "version-1",
        scene_id: "scene-1",
        pov_character_id: "mira-1",
      },
      { actorId: "actor-1", requestId: "req-answer-id", idempotencyKey: "idem-answer-id" },
    )
    expect(client.runActionRequest).toHaveBeenCalledWith(
      "project-1",
      "action-memory-1",
      { current_text_window: "" },
      { actorId: "actor-1", requestId: "req-answer-id", idempotencyKey: "idem-answer-id" },
    )
  })

  it("sends explicit author-selected Ask memory targets through ActionRequest constraints", async () => {
    const client = {
      submitActionRequest: vi.fn().mockResolvedValue({
        action_request_id: "action-memory-1",
        status: "submitted",
      }),
      runActionRequest: vi.fn().mockResolvedValue({
        action_request_id: "action-memory-1",
        status: "succeeded",
        output_type: "memory_answer",
        context_pack_id: null,
        draft_candidate_ids: [],
        risk_finding_ids: [],
        beat_candidate_ids: [],
        memory_answer: {
          question: "她拥有什么？",
          answer: "Mira owns the lantern map.",
          answer_type: "canon",
          confidence: 0.9,
          source_span_refs: [{ type: "source_span", id: "span-1" }],
          affected_entities: [{ type: "character", id: "entity-1", label: "Mira" }],
          caveats: [],
          unknowns: [],
          related_review_items: [],
          safe_to_use_in_current_pov: true,
        },
      }),
    }

    await answerWorkbenchMemory(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
        sceneId: "scene-1",
        povCharacterId: "mira-1",
      },
      "她拥有什么？",
      {
        subjectRef: { type: "character", id: "entity-1", label: "Mira" },
        predicate: "owns",
      },
      () => "answer-target-id",
    )

    expect(client.submitActionRequest).toHaveBeenCalledWith(
      "project-1",
      expect.objectContaining({
        action_type: "ask_memory",
        constraints: {
          ui_surface: "workbench.ask_palette",
          question: "她拥有什么？",
          subject_ref: { type: "character", id: "entity-1", label: "Mira" },
          predicate: "owns",
        },
      }),
      { actorId: "actor-1", requestId: "req-answer-target-id", idempotencyKey: "idem-answer-target-id" },
    )
  })

  it("retries transient Ask ActionRequest submit fetch failures with the same idempotency headers", async () => {
    const client = {
      submitActionRequest: vi.fn()
        .mockRejectedValueOnce(new TypeError("Failed to fetch"))
        .mockResolvedValueOnce({
          action_request_id: "action-memory-1",
          status: "submitted",
        }),
      runActionRequest: vi.fn().mockResolvedValue({
        action_request_id: "action-memory-1",
        status: "succeeded",
        output_type: "memory_answer",
        context_pack_id: null,
        draft_candidate_ids: [],
        risk_finding_ids: [],
        beat_candidate_ids: [],
        memory_answer: {
          question: "Mira 现在知道钥匙的来源吗？",
          answer: "No SourceSpan-backed memory evidence matches this question.",
          answer_type: "unknown",
          confidence: 0,
          source_span_refs: [],
          affected_entities: [],
          caveats: ["no_matching_evidence"],
          unknowns: ["no_matching_evidence"],
          related_review_items: [],
          safe_to_use_in_current_pov: false,
        },
      }),
    }

    const answer = await answerWorkbenchMemory(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
      },
      "Mira 现在知道钥匙的来源吗？",
      () => "answer-id",
    )

    expect(answer.answer_type).toBe("unknown")
    expect(client.submitActionRequest).toHaveBeenCalledTimes(2)
    expect(client.submitActionRequest).toHaveBeenNthCalledWith(
      2,
      "project-1",
      expect.any(Object),
      { actorId: "actor-1", requestId: "req-answer-id", idempotencyKey: "idem-answer-id" },
    )
  })

  it("retries transient Ask ActionRequest run fetch failures with the same idempotency headers", async () => {
    const client = {
      submitActionRequest: vi.fn().mockResolvedValue({
        action_request_id: "action-memory-1",
        status: "submitted",
      }),
      runActionRequest: vi.fn()
        .mockRejectedValueOnce(new TypeError("Failed to fetch"))
        .mockResolvedValueOnce({
          action_request_id: "action-memory-1",
          status: "succeeded",
          output_type: "memory_answer",
          context_pack_id: null,
          draft_candidate_ids: [],
          risk_finding_ids: [],
          beat_candidate_ids: [],
          memory_answer: {
            question: "Mira 现在知道钥匙的来源吗？",
            answer: "No SourceSpan-backed memory evidence matches this question.",
            answer_type: "unknown",
            confidence: 0,
            source_span_refs: [],
            affected_entities: [],
            caveats: ["no_matching_evidence"],
            unknowns: ["no_matching_evidence"],
            related_review_items: [],
            safe_to_use_in_current_pov: false,
          },
        }),
    }

    const answer = await answerWorkbenchMemory(
      client,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
      },
      "Mira 现在知道钥匙的来源吗？",
      () => "answer-id",
    )

    expect(answer.answer_type).toBe("unknown")
    expect(client.runActionRequest).toHaveBeenCalledTimes(2)
    expect(client.runActionRequest).toHaveBeenNthCalledWith(
      2,
      "project-1",
      "action-memory-1",
      { current_text_window: "" },
      { actorId: "actor-1", requestId: "req-answer-id", idempotencyKey: "idem-answer-id" },
    )
  })

  it("checks selected risk through ActionRequest risk output", async () => {
    const client = {
      submitActionRequest: vi.fn().mockResolvedValue({
        action_request_id: "action-risk-1",
        status: "submitted",
      }),
      runActionRequest: vi.fn().mockResolvedValue({
        action_request_id: "action-risk-1",
        status: "succeeded",
        output_type: "risk_findings",
        context_pack_id: null,
        draft_candidate_ids: [],
        risk_finding_ids: ["risk-1"],
        beat_candidate_ids: [],
        risk_findings: [
          {
            id: "risk-1",
            risk_level: "high",
            risk_type: "canon_risk",
            summary: "把风险事实写成 canon。",
            memory_refs: { source_span_id: "span-1" },
            storytelling_refs: { source: "check_risk_action" },
            suggested_revision: "改成怀疑。",
            can_offer_to_author: false,
            maps_to_review_type_if_accepted: "canon_conflict",
            draft_local_only: true,
          },
        ],
      }),
    }
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }

    const findings = await requestRiskCheck(
      client,
      config,
      {
        actorIntent: "这里有没有写得太实的暗示？",
        currentTextWindow: "risk-context 已经坐实了秘密。",
        range: { start: 0, end: 18 },
      },
      () => "risk-id",
    )
    const drawerCandidates = toDrawerRiskCandidates(findings)

    expect(drawerCandidates[0].risk?.level).toBe("high")
    expect(drawerCandidates[0].sentences).toEqual([])
    expect(client.submitActionRequest).toHaveBeenCalledWith(
      "project-1",
      {
        trigger: "natural_language",
        action_type: "check_risk",
        target: {
          kind: "selected_text",
          source_id: "source-1",
          source_version_id: "version-1",
          range: { start: 0, end: 18 },
          selected_text: "risk-context 已经坐实了秘密。",
        },
        constraints: { ui_surface: "workbench.ask_palette" },
        expected_output: "risk_findings",
        actor_intent: "这里有没有写得太实的暗示？",
        source_id: "source-1",
        source_version_id: "version-1",
      },
      { actorId: "actor-1", requestId: "req-risk-id", idempotencyKey: "idem-risk-id" },
    )
    expect(client.runActionRequest).toHaveBeenCalledWith(
      "project-1",
      "action-risk-1",
      { current_text_window: "risk-context 已经坐实了秘密。" },
      { actorId: "actor-1", requestId: "req-risk-id", idempotencyKey: "idem-risk-id" },
    )
  })

  it("requests next direction through ActionRequest BeatCandidate output", async () => {
    const client = {
      submitActionRequest: vi.fn().mockResolvedValue({
        action_request_id: "action-beat-1",
        status: "submitted",
      }),
      runActionRequest: vi.fn().mockResolvedValue({
        action_request_id: "action-beat-1",
        status: "succeeded",
        output_type: "beat_candidates",
        context_pack_id: "context-1",
        draft_candidate_ids: [],
        risk_finding_ids: [],
        beat_candidate_ids: ["beat-1"],
        beat_candidates: [
          {
            id: "beat-1",
            summary: "Mira 先确认眼前阻力，不揭开秘密。",
            driver_character: "Mira",
            agency_rationale: "保持当前可观察压力。",
            storytelling_rationale: "先制造选择压力。",
            cast_decision: { policy: "reuse_current_cast" },
            tension: "信息被压住。",
            memory_refs: [{ type: "source_span", id: "span-1" }],
            evidence_refs: [{ type: "source_span", id: "span-1" }],
            agent_review_findings: [],
          },
        ],
      }),
    }
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }

    const beats = await requestNextDirection(
      client,
      config,
      {
        actorIntent: "下面可以发生什么？",
        currentTextWindow: "Mira 停在门口。",
        insertOffset: 12,
      },
      () => "beat-id",
    )
    const drawerCandidates = toDrawerBeatCandidates(beats)

    expect(drawerCandidates[0].direction).toContain("眼前阻力")
    expect(drawerCandidates[0].sentences).toEqual([])
    expect(client.submitActionRequest).toHaveBeenCalledWith(
      "project-1",
      {
        trigger: "natural_language",
        action_type: "suggest_next_direction",
        target: {
          kind: "cursor_position",
          source_id: "source-1",
          source_version_id: "version-1",
          range: { start: 12, end: 12 },
        },
        constraints: { ui_surface: "workbench.ask_palette" },
        expected_output: "beat_candidates",
        actor_intent: "下面可以发生什么？",
        source_id: "source-1",
        source_version_id: "version-1",
      },
      { actorId: "actor-1", requestId: "req-beat-id", idempotencyKey: "idem-beat-id" },
    )
  })

  it("loads MemoryPage list and detail through backend read APIs", async () => {
    const client = {
      listMemoryPages: vi.fn().mockResolvedValue({
        items: [
          {
            id: "page-1",
            page_type: "character",
            target_ref: { type: "character", id: "mira" },
            title: "Mira",
            canon_status: "stale",
            memory_depth: "standard",
            source_refs: [{ type: "source_span", id: "span-1" }],
            open_thread_count: 1,
            contradiction_count: 1,
          },
        ],
      }),
      getMemoryPage: vi.fn().mockResolvedValue({
        id: "page-1",
        page_type: "character",
        target_ref: { type: "character", id: "mira" },
        title: "Mira",
        current_canon: { facts: [{ predicate: "owns", object: "lantern-map" }] },
        appearance_log: [],
        event_log: [],
        relationships: [],
        knowledge_state: [],
        open_threads: [{ id: "thread-1" }],
        contradictions: [{ source_delta_id: "delta-1" }],
        source_refs: [{ type: "source_span", id: "span-1" }],
        canon_status: "stale",
        memory_depth: "standard",
      }),
    }
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      bearerToken: "jwt-token",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }

    const pages = await loadWorkbenchMemoryPages(client, config, {
      pageType: "character",
      canonStatus: "stale",
    })
    const detail = await loadWorkbenchMemoryPageDetail(client, config, "page-1")

    expect(pages[0].title).toBe("Mira")
    expect(detail.source_refs[0].id).toBe("span-1")
    expect(client.listMemoryPages).toHaveBeenCalledWith(
      "project-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
      { pageType: "character", canonStatus: "stale", limit: 20 },
    )
    expect(client.getMemoryPage).toHaveBeenCalledWith(
      "project-1",
      "page-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
    )
  })

  it("operates MemoryPage open threads through backend write APIs", async () => {
    const client = {
      operateMemoryPageOpenThread: vi.fn().mockResolvedValue({
        memory_page_id: "page-1",
        thread_id: "thread-1",
        status: "resolved",
        update_type: "pays_off",
        memory_page: {
          id: "page-1",
          page_type: "character",
          target_ref: { type: "character", id: "mira" },
          title: "Mira",
          current_canon: { facts: [] },
          appearance_log: [],
          event_log: [],
          relationships: [],
          knowledge_state: [],
          open_threads: [{ id: "thread-1", status: "resolved" }],
          contradictions: [],
          source_refs: [{ type: "source_span", id: "span-1" }],
          canon_status: "current",
          memory_depth: "scene",
        },
        side_effects: { memory_pages: "thread_update_applied" },
      }),
    }
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      bearerToken: "jwt-token",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }

    const result = await operateWorkbenchMemoryPageThread(
      client,
      config,
      "page-1",
      {
        threadId: "thread-1",
        updateType: "pays_off",
        authorNote: "已在正文中回收。",
        summary: "地图来源已由档案室揭示。",
      },
      () => "thread-op-id",
    )

    expect(result.status).toBe("resolved")
    expect(client.operateMemoryPageOpenThread).toHaveBeenCalledWith(
      "project-1",
      "page-1",
      "thread-1",
      {
        update_type: "pays_off",
        author_note: "已在正文中回收。",
        summary: "地图来源已由档案室揭示。",
      },
      {
        actorId: "actor-1",
        bearerToken: "jwt-token",
        requestId: "req-thread-op-id",
        idempotencyKey: "idem-thread-op-id",
      },
    )
  })

  it("retries transient MemoryPage read fetch failures", async () => {
    const client = {
      listMemoryPages: vi.fn()
        .mockRejectedValueOnce(new TypeError("Failed to fetch"))
        .mockResolvedValueOnce({
          items: [
            {
              id: "page-1",
              page_type: "character",
              target_ref: { type: "character", id: "mira" },
              title: "Mira",
              canon_status: "current",
              memory_depth: "standard",
              source_refs: [{ type: "source_span", id: "span-1" }],
              open_thread_count: 0,
              contradiction_count: 0,
            },
          ],
        }),
      getMemoryPage: vi.fn()
        .mockRejectedValueOnce(new TypeError("Failed to fetch"))
        .mockResolvedValueOnce({
          id: "page-1",
          page_type: "character",
          target_ref: { type: "character", id: "mira" },
          title: "Mira",
          current_canon: { facts: [{ predicate: "owns", object: "lantern-map" }] },
          appearance_log: [],
          event_log: [],
          relationships: [],
          knowledge_state: [],
          open_threads: [],
          contradictions: [],
          source_refs: [{ type: "source_span", id: "span-1" }],
          canon_status: "current",
          memory_depth: "standard",
        }),
    }
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }

    const pages = await loadWorkbenchMemoryPages(client, config)
    const detail = await loadWorkbenchMemoryPageDetail(client, config, "page-1")

    expect(pages[0].title).toBe("Mira")
    expect(detail.current_canon.facts[0].predicate).toBe("owns")
    expect(client.listMemoryPages).toHaveBeenCalledTimes(2)
    expect(client.getMemoryPage).toHaveBeenCalledTimes(2)
  })

  it("loads GraphProjection edges through the backend read API", async () => {
    const client = {
      listGraphProjectionEdges: vi.fn().mockResolvedValue({
        items: [
          {
            id: "edge-1",
            run_id: "run-1",
            source_ref: { type: "fact_assertion", id: "fact-1" },
            subject_ref: { type: "character", id: "mira", label: "Mira" },
            relation: "located_in",
            target_ref: { type: "location", id: "west-archive", label: "West Archive" },
            edge_status: "disputed",
            evidence_refs: [{ type: "source_span", id: "span-1" }],
            created_at: "2026-06-04T00:00:00Z",
          },
        ],
      }),
    }
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      bearerToken: "jwt-token",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }

    const edges = await loadWorkbenchGraphProjectionEdges(client, config, {
      query: "archive",
      edgeStatus: "disputed",
    })

    expect(edges[0].relation).toBe("located_in")
    expect(client.listGraphProjectionEdges).toHaveBeenCalledWith(
      "project-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
      { q: "archive", relation: undefined, edgeStatus: "disputed", limit: 30 },
    )
  })

  it("loads and writes Project Story Schema overrides through generated APIs", async () => {
    const client = {
      getProjectStorySchema: vi.fn().mockResolvedValue({
        project_id: "project-1",
        binding_id: null,
        base_schema_pack_id: null,
        genre_schema_pack_id: null,
        genre_schema_pack: null,
        project_override_pack_id: null,
        project_override_pack: null,
        effective_schema: { relations: ["owns"] },
      }),
      listStorySchemaPacks: vi.fn().mockResolvedValue({
        items: [
          {
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
        ],
      }),
      selectProjectStorySchemaGenrePack: vi.fn().mockResolvedValue({
        project_id: "project-1",
        binding_id: "binding-genre-1",
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
        project_override_pack_id: null,
        project_override_pack: null,
        effective_schema: { relations: ["owns", "points_to"] },
      }),
      upsertProjectStorySchemaOverride: vi.fn().mockResolvedValue({
        project_id: "project-1",
        binding_id: "binding-1",
        base_schema_pack_id: "base-pack-1",
        genre_schema_pack_id: null,
        genre_schema_pack: null,
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
          relations: [
            { name: "guards", subject_types: ["character"], object_types: ["artifact"] },
          ],
          extraction_hints: {},
          risk_rules: {},
        },
        effective_schema: { relations: ["guards"] },
      }),
    }
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      bearerToken: "jwt-token",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }

    const schema = await loadWorkbenchStorySchema(client, config)
    const packs = await loadWorkbenchStorySchemaPacks(client, config)
    const selected = await selectWorkbenchStorySchemaGenrePack(
      client,
      config,
      "genre-pack-1",
      () => "genre-request-id",
    )
    const updated = await upsertWorkbenchStorySchemaOverride(
      client,
      config,
      {
        packName: "harbor-nine-overrides",
        entityTypes: [{ name: "artifact", subtype_of: "object" }],
        relations: [
          { name: "guards", subject_types: ["character"], object_types: ["artifact"] },
        ],
      },
      () => "schema-request-id",
    )

    expect(schema.effective_schema.relations).toEqual(["owns"])
    expect(packs[0].pack_name).toBe("mystery")
    expect(selected.genre_schema_pack_id).toBe("genre-pack-1")
    expect(updated.project_override_pack_id).toBe("override-pack-1")
    expect(client.getProjectStorySchema).toHaveBeenCalledWith(
      "project-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
    )
    expect(client.listStorySchemaPacks).toHaveBeenCalledWith(
      "project-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
      { packType: "genre" },
    )
    expect(client.selectProjectStorySchemaGenrePack).toHaveBeenCalledWith(
      "project-1",
      { genre_schema_pack_id: "genre-pack-1" },
      {
        actorId: "actor-1",
        requestId: "req-genre-request-id",
        idempotencyKey: "idem-genre-request-id",
        bearerToken: "jwt-token",
      },
    )
    expect(client.upsertProjectStorySchemaOverride).toHaveBeenCalledWith(
      "project-1",
      {
        pack_name: "harbor-nine-overrides",
        entity_types: [{ name: "artifact", subtype_of: "object" }],
        event_types: [],
        relations: [
          { name: "guards", subject_types: ["character"], object_types: ["artifact"] },
        ],
        extraction_hints: {},
        risk_rules: {},
      },
      {
        actorId: "actor-1",
        requestId: "req-schema-request-id",
        idempotencyKey: "idem-schema-request-id",
        bearerToken: "jwt-token",
      },
    )
  })

  it("sends formal review operations through the backend", async () => {
    const client = {
      resolveReviewItem: vi.fn().mockResolvedValue({
        review_item_id: "review-1",
        status: "resolved",
        resolution: "accepted_as_change",
        side_effects: {},
      }),
      dismissReviewItem: vi.fn().mockResolvedValue({
        review_item_id: "review-1",
        status: "dismissed",
        resolution: null,
        side_effects: {},
      }),
      reopenReviewItem: vi.fn().mockResolvedValue({
        review_item_id: "review-1",
        status: "open",
        resolution: null,
        side_effects: {},
      }),
    }
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }

    await operateWorkbenchReviewItem(
      client,
      config,
      "review-1",
      {
        operation: "resolve",
        resolution: "mark_intentional",
        authorNote: "作者确认新文本替代旧设定。",
        replacementRefs: [{ type: "source_delta", id: "delta-2" }],
        correction: { alias_record_id: "alias-1", target_entity_id: "entity-2" },
      },
      () => "review-id",
    )
    await operateWorkbenchReviewItem(
      client,
      config,
      "review-1",
      { operation: "dismiss" },
      () => "dismiss-id",
    )
    await operateWorkbenchReviewItem(
      client,
      config,
      "review-1",
      { operation: "reopen" },
      () => "reopen-id",
    )

    expect(client.resolveReviewItem).toHaveBeenCalledWith(
      "project-1",
      "review-1",
      {
        resolution: "mark_intentional",
        author_note: "作者确认新文本替代旧设定。",
        replacement_refs: [{ type: "source_delta", id: "delta-2" }],
        correction: { alias_record_id: "alias-1", target_entity_id: "entity-2" },
      },
      { actorId: "actor-1", requestId: "req-review-id", idempotencyKey: "idem-review-id" },
    )
    expect(client.dismissReviewItem).toHaveBeenCalledWith(
      "project-1",
      "review-1",
      { author_note: "作者暂不处理此复核。" },
      { actorId: "actor-1", requestId: "req-dismiss-id", idempotencyKey: "idem-dismiss-id" },
    )
    expect(client.reopenReviewItem).toHaveBeenCalledWith(
      "project-1",
      "review-1",
      { author_note: "作者重新打开此复核。" },
      { actorId: "actor-1", requestId: "req-reopen-id", idempotencyKey: "idem-reopen-id" },
    )
  })

  it("sends candidate explain, reject, revise, and override operations through the backend", async () => {
    const client = {
      submitActionRequest: vi.fn()
        .mockResolvedValueOnce({
          action_request_id: "action-explain-1",
          status: "submitted",
        })
        .mockResolvedValueOnce({
          action_request_id: "action-revise-1",
          status: "submitted",
        }),
      runActionRequest: vi.fn()
        .mockResolvedValueOnce({
          action_request_id: "action-explain-1",
          status: "succeeded",
          output_type: "candidate_explanation",
          context_pack_id: null,
          draft_candidate_ids: [],
          risk_finding_ids: [],
          beat_candidate_ids: [],
          candidate_explanation: {
            candidate_id: "candidate-1",
            why_this: "候选保留悬念。",
            used_memory_refs: [],
            respected_constraints: [],
            avoided_claims: [],
            risks: [],
          },
        })
        .mockResolvedValueOnce({
          action_request_id: "action-revise-1",
          status: "succeeded",
          output_type: "draft_candidates",
          context_pack_id: "context-2",
          draft_candidate_ids: ["candidate-2"],
          risk_finding_ids: [],
          beat_candidate_ids: [],
        }),
      rejectCandidate: vi.fn().mockResolvedValue({
        candidate_id: "candidate-1",
        status: "archived",
        replacement_candidate_id: null,
        override_reason: null,
      }),
      overrideCandidateBlock: vi.fn(),
      getCandidate: vi.fn()
        .mockResolvedValueOnce(candidate)
        .mockResolvedValueOnce({ ...candidate, id: "candidate-2" }),
    }
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }

    const explanation = await explainWorkbenchCandidate(
      client,
      config,
      "candidate-1",
      () => "explain-id",
    )
    await rejectWorkbenchCandidate(client, config, "candidate-1", () => "reject-id")
    const replacement = await reviseWorkbenchCandidate(
      client,
      config,
      "candidate-1",
      "米拉停在门口。",
      () => "revise-id",
    )

    expect(explanation.id).toBe("candidate-1")
    expect(client.submitActionRequest).toHaveBeenCalledWith(
      "project-1",
      {
        trigger: "candidate_action",
        action_type: "explain_candidate",
        target: { kind: "candidate", candidate_id: "candidate-1" },
        constraints: { ui_surface: "workbench.candidate_drawer" },
        expected_output: "candidate_explanation",
        actor_intent: "为什么这个候选合理？",
        source_id: "source-1",
        source_version_id: "version-1",
      },
      { actorId: "actor-1", requestId: "req-explain-id", idempotencyKey: "idem-explain-id" },
    )
    expect(client.runActionRequest).toHaveBeenCalledWith(
      "project-1",
      "action-explain-1",
      { current_text_window: "" },
      { actorId: "actor-1", requestId: "req-explain-id", idempotencyKey: "idem-explain-id" },
    )
    expect(client.getCandidate).toHaveBeenNthCalledWith(
      1,
      "project-1",
      "candidate-1",
      { actorId: "actor-1" },
    )
    expect(replacement.id).toBe("candidate-2")
    expect(client.submitActionRequest).toHaveBeenNthCalledWith(
      2,
      "project-1",
      {
        trigger: "candidate_action",
        action_type: "revise_candidate",
        target: { kind: "candidate", candidate_id: "candidate-1" },
        constraints: { ui_surface: "workbench.candidate_drawer" },
        expected_output: "draft_candidate",
        actor_intent: "按作者选择的修订文本重写候选。",
        source_id: "source-1",
        source_version_id: "version-1",
      },
      { actorId: "actor-1", requestId: "req-revise-id", idempotencyKey: "idem-revise-id" },
    )
    expect(client.runActionRequest).toHaveBeenNthCalledWith(
      2,
      "project-1",
      "action-revise-1",
      { current_text_window: "米拉停在门口。" },
      { actorId: "actor-1", requestId: "req-revise-id", idempotencyKey: "idem-revise-id" },
    )
    expect(client.rejectCandidate).toHaveBeenCalledWith(
      "project-1",
      "candidate-1",
      { author_note: "作者退回这个候选。" },
      { actorId: "actor-1", requestId: "req-reject-id", idempotencyKey: "idem-reject-id" },
    )
    expect(client.getCandidate).toHaveBeenCalledWith(
      "project-1",
      "candidate-2",
      { actorId: "actor-1" },
    )

    client.getCandidate.mockResolvedValueOnce({
      ...candidate,
      status: "offered_to_author",
      override_reason: "作者确认这是有意越界。",
    })
    const overridden = await overrideWorkbenchCandidateBlock(
      client,
      config,
      "candidate-1",
      "作者确认这是有意越界。",
      () => "override-id",
    )
    expect(overridden.override_reason).toBe("作者确认这是有意越界。")
    expect(client.overrideCandidateBlock).toHaveBeenCalledWith(
      "project-1",
      "candidate-1",
      { override_reason: "作者确认这是有意越界。" },
      { actorId: "actor-1", requestId: "req-override-id", idempotencyKey: "idem-override-id" },
    )
  })

  it("keeps blocked/high-risk candidates out of accept until override exists", async () => {
    await expect(
      acceptCandidateText(
        { acceptCandidate: vi.fn() },
        {
          apiBaseUrl: "http://api.test",
          projectId: "project-1",
          actorId: "actor-1",
          sourceId: "source-1",
          sourceVersionId: "version-1",
        },
        {
          ...candidate,
          status: "blocked",
          override_reason: null,
          agent_review_findings: [
            {
              id: "risk-1",
              risk_level: "high",
              risk_type: "canon_risk",
              summary: "把风险事实写成 canon。",
              memory_refs: {},
              storytelling_refs: {},
              suggested_revision: null,
              can_offer_to_author: false,
              maps_to_review_type_if_accepted: "canon_conflict",
              draft_local_only: true,
            },
          ],
        },
        "米拉停在门口。",
      ),
    ).rejects.toThrow("Blocked candidate requires override")

    const acceptClient = {
      acceptCandidate: vi.fn().mockResolvedValue({
        accepted_fragment_id: "fragment-1",
        source_delta_id: "delta-1",
        new_version_id: "version-2",
        memory_writeback_job_id: "job-1",
      }),
    }
    await acceptCandidateText(
      acceptClient,
      {
        apiBaseUrl: "http://api.test",
        projectId: "project-1",
        actorId: "actor-1",
        sourceId: "source-1",
        sourceVersionId: "version-1",
      },
      {
        ...candidate,
        status: "offered_to_author",
        override_reason: "作者确认这是有意越界。",
        agent_review_findings: [
          {
            id: "risk-1",
            risk_level: "high",
            risk_type: "canon_risk",
            summary: "把风险事实写成 canon。",
            memory_refs: {},
            storytelling_refs: {},
            suggested_revision: null,
            can_offer_to_author: false,
            maps_to_review_type_if_accepted: "canon_conflict",
            draft_local_only: true,
          },
        ],
      },
      "米拉停在门口。",
      () => "accept-after-override",
    )
    expect(acceptClient.acceptCandidate).toHaveBeenCalled()
  })

  it("loads and mutates project members through generated client methods", async () => {
    const member = {
      id: "membership-1",
      project_id: "project-1",
      actor_id: "member-1",
      role: "editor",
      status: "active",
      created_at: "2026-06-11T00:00:00Z",
    }
    const client = {
      listProjectMembers: vi.fn().mockResolvedValue({ items: [member] }),
      upsertProjectMember: vi.fn().mockResolvedValue({ member, status: "updated" }),
      revokeProjectMember: vi
        .fn()
        .mockResolvedValue({ member: { ...member, status: "revoked" }, status: "revoked" }),
    }
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      bearerToken: "jwt-token",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }

    const members = await loadWorkbenchProjectMembers(client, config)
    const upserted = await upsertWorkbenchProjectMember(
      client,
      config,
      "member-1",
      "editor",
      () => "member-upsert",
    )
    const revoked = await revokeWorkbenchProjectMember(
      client,
      config,
      "member-1",
      () => "member-revoke",
    )

    expect(members).toEqual([member])
    expect(upserted.status).toBe("updated")
    expect(revoked.member.status).toBe("revoked")
    expect(client.listProjectMembers).toHaveBeenCalledWith(
      "project-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
    )
    expect(client.upsertProjectMember).toHaveBeenCalledWith(
      "project-1",
      "member-1",
      { role: "editor" },
      {
        actorId: "actor-1",
        bearerToken: "jwt-token",
        requestId: "req-member-upsert",
        idempotencyKey: "idem-member-upsert",
      },
    )
    expect(client.revokeProjectMember).toHaveBeenCalledWith(
      "project-1",
      "member-1",
      {
        actorId: "actor-1",
        bearerToken: "jwt-token",
        requestId: "req-member-revoke",
        idempotencyKey: "idem-member-revoke",
      },
    )
  })

  it("loads and records project invitations through generated client methods", async () => {
    const invitation = {
      id: "invitation-1",
      project_id: "project-1",
      member_actor_id: "member-1",
      role: "editor",
      delivery_provider_ref: "ses://sextant-prod/invitations",
      delivery_target_ref: "ses://sextant-prod/recipient/member-1",
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
    const client = {
      listProjectInvitations: vi.fn().mockResolvedValue({ items: [invitation] }),
      createProjectInvitation: vi.fn().mockResolvedValue(invitation),
      recordProjectInvitationExternalProof: vi.fn().mockResolvedValue({
        ...invitation,
        delivery_status: "sent",
        token_status: "issued",
        delivery_proof_ref: "ses://sextant-prod/messages/invitation-1",
        token_proof_ref: "auth0://sextant-prod/tickets/invitation-1",
      }),
    }
    const config = {
      apiBaseUrl: "http://api.test",
      projectId: "project-1",
      actorId: "actor-1",
      bearerToken: "jwt-token",
      sourceId: "source-1",
      sourceVersionId: "version-1",
    }

    const invitations = await listWorkbenchProjectInvitations(client, config)
    const created = await createWorkbenchProjectInvitation(
      client,
      config,
      {
        memberActorId: "member-1",
        role: "editor",
        deliveryProviderRef: "ses://sextant-prod/invitations",
        deliveryTargetRef: "ses://sextant-prod/recipient/member-1",
        tokenIssuerRef: "auth0://sextant-prod/clients/web",
      },
      () => "invitation-create",
    )
    const proof = await recordWorkbenchProjectInvitationExternalProof(
      client,
      config,
      "invitation-1",
      {
        deliveryProofRef: "ses://sextant-prod/messages/invitation-1",
        tokenProofRef: "auth0://sextant-prod/tickets/invitation-1",
      },
      () => "invitation-proof",
    )

    expect(invitations).toEqual([invitation])
    expect(created.status).toBe("pending_external_delivery")
    expect(proof.delivery_status).toBe("sent")
    expect(client.listProjectInvitations).toHaveBeenCalledWith("project-1", {
      actorId: "actor-1",
      bearerToken: "jwt-token",
    })
    expect(client.createProjectInvitation).toHaveBeenCalledWith(
      "project-1",
      {
        member_actor_id: "member-1",
        role: "editor",
        delivery_provider_ref: "ses://sextant-prod/invitations",
        delivery_target_ref: "ses://sextant-prod/recipient/member-1",
        token_issuer_ref: "auth0://sextant-prod/clients/web",
      },
      {
        actorId: "actor-1",
        bearerToken: "jwt-token",
        requestId: "req-invitation-create",
        idempotencyKey: "idem-invitation-create",
      },
    )
    expect(client.recordProjectInvitationExternalProof).toHaveBeenCalledWith(
      "project-1",
      "invitation-1",
      {
        delivery_proof_ref: "ses://sextant-prod/messages/invitation-1",
        token_proof_ref: "auth0://sextant-prod/tickets/invitation-1",
      },
      {
        actorId: "actor-1",
        bearerToken: "jwt-token",
        requestId: "req-invitation-proof",
        idempotencyKey: "idem-invitation-proof",
      },
    )
  })

  it("maps stale SourceVersion errors to a rebase-oriented workbench message", () => {
    const error = new SextantApiError(409, {
      error: {
        code: "stale_source_version",
        message: "Target source version has changed.",
        details: { latest_version_id: "version-2" },
      },
    })

    expect(workbenchErrorMessage(error)).toContain("正文版本已更新")
    expect(workbenchErrorMessage(error)).toContain("重新生成候选")
    expect(workbenchErrorMessage(error)).not.toContain("Target source version")
  })

  it("maps backend candidate detail into the existing drawer view model", () => {
    const drawerCandidate = toDrawerCandidate(candidate)

    expect(drawerCandidate.sentences).toHaveLength(2)
    expect(drawerCandidate.usedMemory).toEqual(["span-1"])
    expect(drawerCandidate.risk).toBeNull()
  })

  it("maps candidate evidence refs without exposing raw UUID-only labels", () => {
    const drawerCandidate = toDrawerCandidate({
      ...candidate,
      evidence_refs: [
        {
          type: "source_span",
          id: "c2476d16-feff-4d1b-a03e-ea3c5299158b",
        },
      ],
    })

    expect(drawerCandidate.usedMemory).toEqual(["source_span:c2476d16"])
  })
})
