from __future__ import annotations

import json
import re
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "backend" / "scripts" / "generate_api_artifacts.py"
SPEC = spec_from_file_location("generate_api_artifacts", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
generate_api_artifacts = module_from_spec(SPEC)
sys.modules["generate_api_artifacts"] = generate_api_artifacts
SPEC.loader.exec_module(generate_api_artifacts)


def test_generated_api_artifacts_are_current() -> None:
    artifacts = generate_api_artifacts.build_artifacts()

    assert generate_api_artifacts.OPENAPI_PATH.read_text(encoding="utf-8") == artifacts.openapi_json
    assert generate_api_artifacts.CLIENT_PATH.read_text(encoding="utf-8") == artifacts.client_ts


def test_documented_api_routes_exist_in_openapi() -> None:
    artifacts = generate_api_artifacts.build_artifacts()
    openapi = json.loads(artifacts.openapi_json)
    implemented_routes = {
        (method.upper(), path)
        for path, operations in openapi["paths"].items()
        for method in operations
    }
    documented_routes = _documented_api_routes()

    assert documented_routes - implemented_routes == set()


def test_generated_typescript_client_exposes_project_invitation_routes() -> None:
    artifacts = generate_api_artifacts.build_artifacts()

    assert "ProjectInvitationCreateBody" in artifacts.client_ts
    assert "ProjectInvitationExternalProofBody" in artifacts.client_ts
    assert "ProjectInvitationListResponse" in artifacts.client_ts
    assert "async listProjectInvitations(" in artifacts.client_ts
    assert "async createProjectInvitation(" in artifacts.client_ts
    assert "async recordProjectInvitationExternalProof(" in artifacts.client_ts


def test_generated_typescript_client_exposes_memory_page_thread_operation() -> None:
    artifacts = generate_api_artifacts.build_artifacts()

    assert "MemoryPageThreadOperationBody" in artifacts.client_ts
    assert "MemoryPageThreadOperationResponse" in artifacts.client_ts
    assert "async operateMemoryPageOpenThread(" in artifacts.client_ts


def _documented_api_routes() -> set[tuple[str, str]]:
    contract = (ROOT / "implementation" / "08-api-contracts.md").read_text(encoding="utf-8")
    return {
        (method, path)
        for method, path in re.findall(r"^(GET|POST|PUT|DELETE)\s+(/api/\S+)", contract, re.M)
    }
