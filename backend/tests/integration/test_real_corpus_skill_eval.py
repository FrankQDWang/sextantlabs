from __future__ import annotations

import json
from pathlib import Path

import pytest
from sextant.infra.real_corpus_skill_eval import (
    load_real_corpus_eval_spec,
    run_real_corpus_memory_boundary_eval,
)


def test_real_corpus_eval_spec_rejects_embedded_slice_text(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "corpus_path": "sample.txt",
                "cases": [
                    {
                        "case_id": "bad-case",
                        "line_start": 1,
                        "line_end": 2,
                        "text": "forbidden embedded text",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must not embed corpus text"):
        load_real_corpus_eval_spec(spec_path)


def test_real_corpus_memory_boundary_eval_runs_without_committed_corpus_text(
    tmp_path: Path,
) -> None:
    corpus_path = tmp_path / "sample.txt"
    corpus_path.write_text(
        "第一章\n普通叙事，没有结构化 FACT 指令。\n第二章\n仍然只是正文。",
        encoding="utf-8",
    )
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "corpus_path": str(corpus_path),
                "cases": [
                    {
                        "case_id": "slice-1",
                        "chapter_label": "第一章",
                        "line_start": 1,
                        "line_end": 2,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_real_corpus_memory_boundary_eval(spec_path)

    assert result["summary"]["case_count"] == 1
    assert result["summary"]["passed"] == 1
    assert result["cases"][0]["fact_count"] == 0
    assert result["cases"][0]["thread_update_count"] == 0
    assert result["cases"][0]["memory_page_count"] == 0
