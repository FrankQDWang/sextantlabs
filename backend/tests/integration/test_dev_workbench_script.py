from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import UUID


def test_dev_workbench_prepare_only_migrates_seeds_and_writes_api_env(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    state_dir = tmp_path / "dev-workbench"
    env = {
        **os.environ,
        "SEXTANT_DEV_STATE_DIR": str(state_dir),
        "SEXTANT_DEV_PYTHON": sys.executable,
        "SEXTANT_DEV_API_PORT": "19081",
        "SEXTANT_DEV_WEB_PORT": "19082",
        "SEXTANT_DEV_SEED_FIXED_IDS": "1",
        "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", str(tmp_path / "uv-cache")),
    }

    result = subprocess.run(
        ["bash", "scripts/dev-workbench.sh", "--prepare-only"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "Sextant dev workbench prepared" in result.stdout
    assert "worker healthcheck: pass" in result.stdout

    vite_env = state_dir / "workbench.vite.env"
    assert vite_env.exists()
    env_text = vite_env.read_text(encoding="utf-8")
    assert "VITE_SEXTANT_API_BASE_URL=http://127.0.0.1:19081" in env_text
    assert "VITE_SEXTANT_PROJECT_ID=00000000-0000-4000-8000-000000000001" in env_text
    assert "VITE_SEXTANT_ACTOR_ID=00000000-0000-4000-8000-000000000002" in env_text
    assert "VITE_SEXTANT_SOURCE_ID=00000000-0000-4000-8000-000000000003" in env_text
    assert "VITE_SEXTANT_SOURCE_VERSION_ID=00000000-0000-4000-8000-000000000004" in env_text
    assert "VITE_SEXTANT_SCENE_ID=00000000-0000-4000-8000-000000000012" in env_text
    assert "VITE_SEXTANT_POV_CHARACTER_ID=00000000-0000-4000-8000-00000000000c" in env_text

    database_path = state_dir / "workbench.db"
    assert database_path.exists()
    with sqlite3.connect(database_path) as connection:
        chapter_count = connection.execute("select count(*) from story_chapters").fetchone()[0]
        scenes = connection.execute("select id, pov_character_id from story_scenes").fetchall()
        scene_span_ids = [
            _uuid_text(row[0])
            for row in connection.execute(
                "select scene_id from source_spans where scene_id is not null"
            ).fetchall()
        ]
    assert chapter_count == 1
    assert [(_uuid_text(row[0]), _uuid_text(row[1])) for row in scenes] == [
        (
            "00000000-0000-4000-8000-000000000012",
            "00000000-0000-4000-8000-00000000000c",
        )
    ]
    assert scene_span_ids.count("00000000-0000-4000-8000-000000000012") >= 2


def test_dev_workbench_prepare_only_is_repeatable_with_default_seed_mode(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    state_dir = tmp_path / "dev-workbench-repeatable"
    env = {
        **os.environ,
        "SEXTANT_DEV_STATE_DIR": str(state_dir),
        "SEXTANT_DEV_PYTHON": sys.executable,
        "SEXTANT_DEV_API_PORT": "19091",
        "SEXTANT_DEV_WEB_PORT": "19092",
        "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", str(tmp_path / "uv-cache")),
    }

    first = subprocess.run(
        ["bash", "scripts/dev-workbench.sh", "--prepare-only"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    second = subprocess.run(
        ["bash", "scripts/dev-workbench.sh", "--prepare-only"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "Sextant dev workbench prepared" in second.stdout

    vite_env = state_dir / "workbench.vite.env"
    assert vite_env.exists()
    env_text = vite_env.read_text(encoding="utf-8")
    assert "VITE_SEXTANT_API_BASE_URL=http://127.0.0.1:19091" in env_text
    assert "VITE_SEXTANT_PROJECT_ID=" in env_text
    assert "VITE_SEXTANT_SOURCE_ID=" in env_text
    assert "VITE_SEXTANT_SOURCE_VERSION_ID=" in env_text


def _uuid_text(value: str) -> str:
    return str(UUID(value))
