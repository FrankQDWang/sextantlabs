from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sextant.infra.real_corpus_skill_eval import (  # noqa: E402
    run_real_corpus_memory_boundary_eval,
)


def _default_spec_path() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "AGENTS.md").exists() and (parent / "PLAN.md").exists():
            return (
                parent
                / "evals"
                / "datasets"
                / "real_corpus_memory_boundary"
                / "fanren-chapter-slices.v1.json"
            )
    raise RuntimeError("Could not locate Sextant repository root.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run real-corpus memory-boundary eval against ignored local slices."
    )
    parser.add_argument(
        "--spec",
        type=Path,
        default=_default_spec_path(),
        help="Path to the real corpus eval spec JSON.",
    )
    args = parser.parse_args()
    result = run_real_corpus_memory_boundary_eval(args.spec)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
