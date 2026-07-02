import { describe, expect, it, vi } from "vitest"
import { SextantApiClient, SextantApiError } from "../src/generated/sextant-api"

describe("SextantApiClient", () => {
  it("sends request and idempotency headers for ActionRequest writes", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ action_request_id: "ar-1", status: "submitted" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          action_request_id: "ar-1",
          status: "succeeded",
          context_pack_id: "context-1",
          draft_candidate_ids: ["candidate-1"],
          risk_finding_ids: [],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: "candidate-1",
          action_request_id: "ar-1",
          mode: "rewrite_span",
          text: "米拉停在门口。",
          status: "offered_to_author",
          target_source_id: "source-1",
          target_version_id: "version-1",
          target_scene_id: null,
          affected_range: { start: 0, end: 12 },
          base_hash: "hash-v1",
          memory_refs: [],
          evidence_refs: [],
          agent_review_findings: [],
        }),
      })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const response = await client.submitActionRequest(
      "project-1",
      {
        trigger: "selection",
        action_type: "rewrite_span",
        target: { kind: "selected_text" },
        expected_output: "draft_candidate",
        actor_intent: "改写这里",
      },
      { actorId: "actor-1", requestId: "req-1", idempotencyKey: "idem-1" },
    )
    const runResponse = await client.runActionRequest(
      "project-1",
      "ar-1",
      { current_text_window: "米拉停在门口。" },
      { actorId: "actor-1", requestId: "req-run", idempotencyKey: "idem-run" },
    )
    const candidate = await client.getCandidate(
      "project-1",
      "candidate-1",
      { actorId: "actor-1" },
    )

    expect(response.status).toBe("submitted")
    expect(runResponse.draft_candidate_ids).toEqual(["candidate-1"])
    expect(candidate.text).toBe("米拉停在门口。")
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://api.test/api/projects/project-1/action-requests",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-Request-Id": "req-1",
          "X-Actor-Id": "actor-1",
          "Idempotency-Key": "idem-1",
        }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://api.test/api/projects/project-1/action-requests/ar-1/run",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-Request-Id": "req-run",
          "X-Actor-Id": "actor-1",
          "Idempotency-Key": "idem-run",
        }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://api.test/api/projects/project-1/candidates/candidate-1",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          "X-Actor-Id": "actor-1",
        }),
      }),
    )
  })

  it("sends dedicated agent wrapper requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        action_request_id: "ar-wrapper",
        status: "succeeded",
        output_type: "draft_candidates",
        context_pack_id: "context-1",
        draft_candidate_ids: ["candidate-1"],
        risk_finding_ids: [],
        beat_candidate_ids: [],
      }),
    })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const body = {
      trigger: "toolbar",
      target: { kind: "selected_text" },
      actor_intent: "继续这一段",
      current_text_window: "米拉停在门口。",
    }
    const headers = { actorId: "actor-1", requestId: "req-agent", idempotencyKey: "idem-agent" }

    await client.suggestNextBeat("project-1", body, headers)
    await client.draftNextPassage("project-1", body, headers)
    await client.rewriteCurrentPage("project-1", body, headers)
    await client.checkRisk("project-1", body, headers)

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://api.test/api/projects/project-1/agent/suggest-next-beat",
      expect.objectContaining({ method: "POST" }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://api.test/api/projects/project-1/agent/draft-next-passage",
      expect.objectContaining({ method: "POST" }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://api.test/api/projects/project-1/agent/rewrite-current-page",
      expect.objectContaining({ method: "POST" }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "http://api.test/api/projects/project-1/agent/check-risk",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-Actor-Id": "actor-1",
          "X-Request-Id": "req-agent",
          "Idempotency-Key": "idem-agent",
        }),
      }),
    )
  })

  it("reads ActionRequest detail with read headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        action_request_id: "ar-1",
        project_id: "project-1",
        source_id: "source-1",
        source_version_id: "version-1",
        scene_id: null,
        chapter_id: null,
        pov_character_id: null,
        actor_intent: "改写这里",
        trigger: "selection",
        action_type: "rewrite_span",
        target: { kind: "selected_text" },
        constraints: { tone: "克制" },
        expected_output: "draft_candidate",
        status: "submitted",
        created_by: "actor-1",
      }),
    })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const actionRequest = await client.getActionRequest(
      "project-1",
      "ar-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
    )

    expect(actionRequest.action_type).toBe("rewrite_span")
    expect(actionRequest.constraints).toEqual({ tone: "克制" })
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/api/projects/project-1/action-requests/ar-1",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Authorization: "Bearer jwt-token",
          "X-Actor-Id": "actor-1",
        }),
      }),
    )
  })

  it("posts candidate explain requests with read headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "candidate-1",
        action_request_id: "ar-1",
        mode: "rewrite_span",
        text: "米拉停在门口。",
        status: "offered_to_author",
        context_pack_id: null,
        target_source_id: "source-1",
        target_version_id: "version-1",
        target_scene_id: null,
        affected_range: { start: 0, end: 12 },
        base_hash: "hash-v1",
        memory_refs: [],
        evidence_refs: [],
        override_reason: null,
        agent_review_findings: [],
      }),
    })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const candidate = await client.explainCandidate(
      "project-1",
      "candidate-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
    )

    expect(candidate.id).toBe("candidate-1")
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/api/projects/project-1/candidates/candidate-1/explain",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer jwt-token",
          "X-Actor-Id": "actor-1",
        }),
      }),
    )
  })

  it("throws structured API errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({
          error: {
            code: "stale_source_version",
            message: "Target source version has changed.",
            details: {},
          },
        }),
      }),
    )

    const client = new SextantApiClient()

    await expect(
      client.acceptCandidate(
        "project-1",
        "candidate-1",
        {
          accepted_text_ref: "object://accepted/one",
          accepted_text: null,
          accept_mode: "partial",
          target_source_id: "source-1",
          target_version_id: "version-1",
          insert_or_replace_range: { start: 0, end: 12 },
          source_type: "draft_manuscript",
          source_scope: "user_draft",
          author_edited: true,
        },
        { actorId: "actor-1", requestId: "req-1", idempotencyKey: "idem-1" },
      ),
    ).rejects.toMatchObject<SextantApiError>({
      code: "stale_source_version",
      status: 409,
    })
  })

  it("sends authenticated formal review operations", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        review_item_id: "review-1",
        status: "resolved",
        resolution: "accepted_as_change",
        side_effects: { graph_projection: "mark_stale" },
      }),
    })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const response = await client.resolveReviewItem(
      "project-1",
      "review-1",
      {
        resolution: "accepted_as_change",
        author_note: "确认是新变化",
        replacement_refs: [{ type: "source_delta", id: "delta-1" }],
      },
      { actorId: "actor-1", requestId: "req-review", idempotencyKey: "idem-review" },
    )

    expect(response.side_effects.graph_projection).toBe("mark_stale")
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/api/projects/project-1/review-items/review-1/resolve",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-Actor-Id": "actor-1",
          "X-Request-Id": "req-review",
          "Idempotency-Key": "idem-review",
        }),
      }),
    )
  })

  it("loads project scene options with source and version filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
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
    })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const scenes = await client.listScenes(
      "project-1",
      { actorId: "actor-1" },
      { source_id: "source-1", version_id: "version-1", limit: 10 },
    )

    expect(scenes.items[0]?.position_label).toBe("Chapter 1 / Scene 1")
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/api/projects/project-1/scenes?source_id=source-1&version_id=version-1&limit=10",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({ "X-Actor-Id": "actor-1" }),
      }),
    )
  })

  it("sends memory answer and context pack requests with evidence headers", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          question: "米拉拥有什么？",
          answer: "Mira owns lantern map",
          answer_type: "canon",
          confidence: 0.92,
          source_span_refs: [{ type: "source_span", id: "span-1" }],
          affected_entities: [
            { type: "character", id: "mira", name: "Mira" },
            { type: "object", id: "lantern-map", name: "Lantern Map" },
          ],
          caveats: [],
          unknowns: [],
          related_review_items: [],
          safe_to_use_in_current_pov: true,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          context_pack_id: "context-1",
          schema_version: "writing-context-pack.v1",
          current_position: {},
          canonical_context: { facts: [] },
          pov_constraint: { forbidden_knowledge: [] },
          active_characters: [],
          character_agency_state: {},
          recent_events: [],
          character_knowledge: [],
          object_location_state: [],
          open_threads: [],
          risk_context: { facts: [] },
          style_memory: {},
          evidence_refs: [],
        }),
      })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const answer = await client.answerMemory(
      "project-1",
      {
        question: "米拉拥有什么？",
        subject_ref: { type: "character", id: "mira" },
        predicate: "owns",
      },
      { actorId: "actor-1", requestId: "req-answer", idempotencyKey: "idem-answer" },
    )
    const context = await client.buildContextPack(
      "project-1",
      {
        mode: "draft_next_passage",
        current_text_window: "米拉停在门口。",
      },
      { actorId: "actor-1", requestId: "req-context", idempotencyKey: "idem-context" },
    )

    expect(answer.answer_type).toBe("canon")
    expect(context.schema_version).toBe("writing-context-pack.v1")
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://api.test/api/projects/project-1/memory/answer",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Actor-Id": "actor-1",
          "X-Request-Id": "req-answer",
          "Idempotency-Key": "idem-answer",
        }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://api.test/api/projects/project-1/context-packs/build",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Actor-Id": "actor-1",
          "X-Request-Id": "req-context",
          "Idempotency-Key": "idem-context",
        }),
      }),
    )
  })

  it("reads ContextPackReadiness from the generated client", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
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
    })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const readiness = await client.listContextPackReadiness(
      "project-1",
      { actorId: "actor-1" },
      { status: "pending", reason: "memory_dependency_changed", limit: 20 },
    )

    expect(readiness.items[0].id).toBe("readiness-1")
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/api/projects/project-1/context-pack-readiness?status=pending&reason=memory_dependency_changed&limit=20",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({ "X-Actor-Id": "actor-1" }),
      }),
    )
  })

  it("reads source, job, writeback preview, and review queue with read headers", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          source_id: "source-1",
          version_id: "version-1",
          title: "Ch.03 西档案室",
          source_type: "draft_manuscript",
          source_scope: "user_draft",
          version_label: "v1",
          raw_hash: "hash-v1",
          text: "第一段。\n第二段。",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
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
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
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
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          source_delta_id: "delta-1",
          source_delta_status: "memory_writeback_completed",
          source_delta: {},
          job: null,
          source_spans: [{ id: "span-1" }],
          evidence_log_entries: [{ id: "evidence-1" }],
          fact_assertions: [{ id: "fact-1" }],
          review_items: [],
          memory_pages: [],
          graph_edges: [],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [] }),
      })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const source = await client.getSourceVersion(
      "project-1",
      "source-1",
      "version-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
    )
    const versions = await client.listSourceVersions(
      "project-1",
      "source-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
      { limit: 12 },
    )
    const job = await client.getJob("project-1", "job-1", { actorId: "actor-1" })
    const preview = await client.getMemoryWritebackPreview(
      "project-1",
      "delta-1",
      { actorId: "actor-1" },
    )
    const reviews = await client.listReviewItems(
      "project-1",
      { actorId: "actor-1" },
      "open",
    )

    expect(source.text).toBe("第一段。\n第二段。")
    expect(versions.items[0].version_label).toBe("v2")
    expect(job.status).toBe("succeeded")
    expect(preview.source_spans).toHaveLength(1)
    expect(reviews.items).toEqual([])
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://api.test/api/projects/project-1/sources/source-1/versions?limit=12",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Authorization: "Bearer jwt-token",
          "X-Actor-Id": "actor-1",
        }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "http://api.test/api/projects/project-1/review-items?status=open",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({ "X-Actor-Id": "actor-1" }),
      }),
    )
  })

  it("reads source version diff with read headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
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
    })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const diff = await client.getSourceVersionDiff(
      "project-1",
      "source-1",
      "version-1",
      "version-2",
      { actorId: "actor-1", bearerToken: "jwt-token" },
    )

    expect(diff.summary.changed).toBe(true)
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/api/projects/project-1/sources/source-1/versions/version-1/diff/version-2",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Authorization: "Bearer jwt-token",
          "X-Actor-Id": "actor-1",
        }),
      }),
    )
  })

  it("sends source and candidate lifecycle write requests", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          source_id: "source-1",
          version_id: "version-1",
          source_delta_id: "delta-import",
          memory_writeback_job_id: "job-import",
          raw_hash: "hash-v1",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          source_id: "source-1",
          version_id: "version-2",
          raw_hash: "hash-v2",
          supersedes_version_id: "version-1",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          source_id: "source-1",
          restored_from_version_id: "version-1",
          source_delta_id: "delta-restore",
          new_version_id: "version-3",
          memory_writeback_job_id: "job-restore",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          source_delta_id: "delta-1",
          new_version_id: "version-4",
          memory_writeback_job_id: "job-1",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          candidate_id: "candidate-1",
          status: "offered_to_author",
          replacement_candidate_id: null,
          override_reason: "作者确认。",
        }),
      })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const headers = { actorId: "actor-1", requestId: "req-write", idempotencyKey: "idem-write" }
    const bearerHeaders = {
      actorId: "actor-1",
      requestId: "req-write",
      idempotencyKey: "idem-write",
      bearerToken: "jwt-token",
    }
    const source = await client.createSource(
      "project-1",
      {
        title: "作者笔记",
        source_type: "author_notes",
        source_scope: "author_note",
        ownership_status: "owned",
        text: "Mira 讨厌冷钥匙。",
      },
      bearerHeaders,
    )
    const version = await client.createSourceVersion(
      "project-1",
      "source-1",
      {
        text: "Mira 讨厌冷钥匙，但会拿起来。",
        version_label: "v2",
        supersedes_version_id: "version-1",
      },
      headers,
    )
    const restored = await client.restoreSourceVersion(
      "project-1",
      "source-1",
      "version-1",
      { author_note: "回滚到第一版。" },
      headers,
    )
    const delta = await client.createSourceDelta(
      "project-1",
      "source-1",
      "version-2",
      {
        delta_kind: "replace",
        range_start: 0,
        range_end: 12,
        base_hash: "hash-v2",
        submitted_text: "Mira 拿起钥匙。",
        source_type: "draft_manuscript",
        source_scope: "user_draft",
      },
      headers,
    )
    const override = await client.overrideCandidateBlock(
      "project-1",
      "candidate-1",
      { override_reason: "作者确认。" },
      headers,
    )

    expect(source.version_id).toBe("version-1")
    expect(source.source_delta_id).toBe("delta-import")
    expect(source.memory_writeback_job_id).toBe("job-import")
    expect(version.supersedes_version_id).toBe("version-1")
    expect(restored.source_delta_id).toBe("delta-restore")
    expect(restored.new_version_id).toBe("version-3")
    expect(delta.memory_writeback_job_id).toBe("job-1")
    expect(override.status).toBe("offered_to_author")
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://api.test/api/projects/project-1/sources",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer jwt-token",
          "X-Actor-Id": "actor-1",
          "X-Request-Id": "req-write",
          "Idempotency-Key": "idem-write",
        }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://api.test/api/projects/project-1/sources/source-1/versions/version-1/restore",
      expect.objectContaining({ method: "POST" }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "http://api.test/api/projects/project-1/sources/source-1/versions/version-2/source-deltas",
      expect.objectContaining({ method: "POST" }),
    )
  })

  it("reads source delta/review/context details and writes preview decisions", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "delta-1",
              source_id: "source-1",
              previous_version_id: "version-1",
              new_version_id: "version-2",
              accepted_fragment_id: null,
              delta_kind: "insert",
              status: "memory_writeback_completed",
              range_start: 0,
              range_end: 0,
              base_hash: "hash-v1",
              source_type: "draft_manuscript",
              source_scope: "user_draft",
              provenance: {},
              submitted_text_ref: "object://local/delta-1",
              submitted_text_preview: "FACT: character:mira",
              job: null,
            },
          ],
          next_cursor: "cursor-2",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: "delta-1",
          source_id: "source-1",
          previous_version_id: "version-1",
          new_version_id: "version-2",
          accepted_fragment_id: null,
          delta_kind: "insert",
          status: "memory_writeback_completed",
          range_start: 0,
          range_end: 0,
          base_hash: "hash-v1",
          source_type: "draft_manuscript",
          source_scope: "user_draft",
          provenance: {},
          submitted_text_ref: "object://local/delta-1",
          submitted_text: "FACT: character:mira | owns | object:lantern-map | low",
          job: null,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
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
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              context_pack_id: "context-1",
              schema_version: "writing-context-pack.v1",
              mode: "draft_next_passage",
              current_position: {},
              evidence_refs: [],
            },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          context_pack_id: "context-1",
          schema_version: "writing-context-pack.v1",
          current_position: {},
          canonical_context: {},
          pov_constraint: {},
          active_characters: [],
          character_agency_state: {},
          recent_events: [],
          character_knowledge: [],
          object_location_state: [],
          open_threads: [],
          risk_context: {},
          style_memory: {},
          evidence_refs: [],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          decision_id: "decision-1",
          source_delta_id: "delta-1",
          item_ref: { type: "fact_assertion", id: "fact-1" },
          decision: "correct",
          status: "recorded",
          side_effects: { fact_assertion_status: "disputed" },
        }),
      })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const deltas = await client.listSourceDeltas(
      "project-1",
      { actorId: "actor-1" },
      {
        sourceId: "source-1",
        status: "memory_writeback_completed",
        cursor: "cursor-1",
        limit: 10,
      },
    )
    const delta = await client.getSourceDelta("project-1", "delta-1", { actorId: "actor-1" })
    const review = await client.getReviewItem("project-1", "review-1", { actorId: "actor-1" })
    const contexts = await client.listContextPacks("project-1", { actorId: "actor-1" }, 5)
    const context = await client.getContextPack("project-1", "context-1", { actorId: "actor-1" })
    const decision = await client.decideMemoryWritebackPreview(
      "project-1",
      "delta-1",
      {
        item_ref: { type: "fact_assertion", id: "fact-1" },
        decision: "correct",
        correction: { predicate: "carries" },
        replacement_refs: [{ type: "source_delta", id: "delta-2" }],
      },
      { actorId: "actor-1", requestId: "req-decision", idempotencyKey: "idem-decision" },
    )

    expect(deltas.items[0].id).toBe("delta-1")
    expect(deltas.next_cursor).toBe("cursor-2")
    expect(delta.submitted_text).toContain("lantern-map")
    expect(review.summary).toContain("Mira")
    expect(contexts.items[0].context_pack_id).toBe("context-1")
    expect(context.schema_version).toBe("writing-context-pack.v1")
    expect(decision.status).toBe("recorded")
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://api.test/api/projects/project-1/source-deltas?source_id=source-1&status=memory_writeback_completed&cursor=cursor-1&limit=10",
      expect.objectContaining({ method: "GET" }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      "http://api.test/api/projects/project-1/source-deltas/delta-1/memory-writeback-preview/decisions",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-Actor-Id": "actor-1",
          "X-Request-Id": "req-decision",
          "Idempotency-Key": "idem-decision",
        }),
        body: JSON.stringify({
          item_ref: { type: "fact_assertion", id: "fact-1" },
          decision: "correct",
          correction: { predicate: "carries" },
          replacement_refs: [{ type: "source_delta", id: "delta-2" }],
        }),
      }),
    )
  })

  it("reads MemoryPage list and detail with evidence refs", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "page-1",
              page_type: "character",
              target_ref: { type: "character", id: "mira" },
              title: "Mira",
              canon_status: "current",
              memory_depth: "standard",
              source_refs: [{ type: "source_span", id: "span-1" }],
              open_thread_count: 1,
              contradiction_count: 0,
            },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: "page-1",
          page_type: "character",
          target_ref: { type: "character", id: "mira" },
          title: "Mira",
          current_canon: { facts: [{ predicate: "owns", object: "lantern-map" }] },
          appearance_log: [{ source_span_id: "span-1" }],
          event_log: [],
          relationships: [],
          knowledge_state: [],
          open_threads: [{ id: "thread-1", summary: "Who gave Mira the map?" }],
          contradictions: [],
          source_refs: [{ type: "source_span", id: "span-1" }],
          canon_status: "current",
          memory_depth: "standard",
        }),
      })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const pages = await client.listMemoryPages(
      "project-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
      { pageType: "character", canonStatus: "current", limit: 20 },
    )
    const detail = await client.getMemoryPage(
      "project-1",
      "page-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
    )

    expect(pages.items[0].source_refs[0].id).toBe("span-1")
    expect(detail.current_canon.facts).toEqual([{ predicate: "owns", object: "lantern-map" }])
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://api.test/api/projects/project-1/memory/pages?page_type=character&canon_status=current&limit=20",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Authorization: "Bearer jwt-token",
          "X-Actor-Id": "actor-1",
        }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://api.test/api/projects/project-1/memory/pages/page-1",
      expect.objectContaining({ method: "GET" }),
    )
  })

  it("manages project members with read and idempotent write headers", async () => {
    const member = {
      id: "membership-1",
      project_id: "project-1",
      actor_id: "member-1",
      role: "editor",
      status: "active",
      created_at: "2026-06-11T00:00:00Z",
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [member] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ member, status: "updated" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ member: { ...member, status: "revoked" }, status: "revoked" }),
      })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const members = await client.listProjectMembers(
      "project-1",
      { actorId: "actor-1", bearerToken: "jwt-token" },
    )
    const upserted = await client.upsertProjectMember(
      "project-1",
      "member-1",
      { role: "editor" },
      { actorId: "actor-1", requestId: "req-upsert", idempotencyKey: "idem-upsert" },
    )
    const revoked = await client.revokeProjectMember(
      "project-1",
      "member-1",
      { actorId: "actor-1", requestId: "req-revoke", idempotencyKey: "idem-revoke" },
    )

    expect(members.items[0].actor_id).toBe("member-1")
    expect(upserted.status).toBe("updated")
    expect(revoked.member.status).toBe("revoked")
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://api.test/api/projects/project-1/members",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Authorization: "Bearer jwt-token",
          "X-Actor-Id": "actor-1",
        }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://api.test/api/projects/project-1/members/member-1",
      expect.objectContaining({
        method: "PUT",
        headers: expect.objectContaining({
          "X-Actor-Id": "actor-1",
          "X-Request-Id": "req-upsert",
          "Idempotency-Key": "idem-upsert",
        }),
        body: JSON.stringify({ role: "editor" }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://api.test/api/projects/project-1/members/member-1/revoke",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-Actor-Id": "actor-1",
          "X-Request-Id": "req-revoke",
          "Idempotency-Key": "idem-revoke",
        }),
      }),
    )
  })

  it("records project invitation intent and external proof with generated client methods", async () => {
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
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [invitation] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => invitation,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ...invitation,
          status: "external_delivery_recorded",
          delivery_status: "sent",
          token_status: "issued",
          delivery_proof_ref: "ses://sextant-prod/messages/invitation-1",
          token_proof_ref: "auth0://sextant-prod/tickets/invitation-1",
          delivered_at: "2026-06-19T00:01:00Z",
          token_issued_at: "2026-06-19T00:01:00Z",
        }),
      })
    vi.stubGlobal("fetch", fetchMock)

    const client = new SextantApiClient("http://api.test")
    const invitations = await client.listProjectInvitations("project-1", {
      actorId: "actor-1",
      bearerToken: "jwt-token",
    })
    const created = await client.createProjectInvitation(
      "project-1",
      {
        member_actor_id: "member-1",
        role: "editor",
        delivery_provider_ref: "ses://sextant-prod/invitations",
        delivery_target_ref: "ses://sextant-prod/recipient/member-1",
        token_issuer_ref: "auth0://sextant-prod/clients/web",
      },
      { actorId: "actor-1", requestId: "req-invite", idempotencyKey: "idem-invite" },
    )
    const proof = await client.recordProjectInvitationExternalProof(
      "project-1",
      "invitation-1",
      {
        delivery_proof_ref: "ses://sextant-prod/messages/invitation-1",
        token_proof_ref: "auth0://sextant-prod/tickets/invitation-1",
      },
      { actorId: "actor-1", requestId: "req-proof", idempotencyKey: "idem-proof" },
    )

    expect(invitations.items[0].id).toBe("invitation-1")
    expect(created.status).toBe("pending_external_delivery")
    expect(proof.delivery_status).toBe("sent")
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://api.test/api/projects/project-1/invitations",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Authorization: "Bearer jwt-token",
          "X-Actor-Id": "actor-1",
        }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://api.test/api/projects/project-1/invitations",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-Actor-Id": "actor-1",
          "X-Request-Id": "req-invite",
          "Idempotency-Key": "idem-invite",
        }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://api.test/api/projects/project-1/invitations/invitation-1/external-proof",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-Actor-Id": "actor-1",
          "X-Request-Id": "req-proof",
          "Idempotency-Key": "idem-proof",
        }),
      }),
    )
  })
})
