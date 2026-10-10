#!/usr/bin/env python3
"""Check canonical governance projection using explicit independently admitted source."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
LOADER_PATH = ROOT / ".github/scripts/workflow_execution/source_loading.py"
LOADER_SOURCE = LOADER_PATH.read_bytes()
LOADER = ModuleType("bijux_workflow_projection_loader")
LOADER.__file__ = str(LOADER_PATH)
exec(compile(LOADER_SOURCE, str(LOADER_PATH), "exec"), LOADER.__dict__)
POLICY = LOADER.load_package(LOADER_SOURCE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--candidate", action="store_true")
    parser.add_argument("--requires-parser", action="store_true")
    args = parser.parse_args()
    authority = POLICY.admit_source(ROOT, args.target, args.repo, args.source_sha, candidate=args.candidate)
    POLICY.validate_source_snapshots(ROOT)
    if args.requires_parser:
        print("true" if POLICY.requires_parser(ROOT, args.repo) else "false")
        return
    result = POLICY.verify_projection(ROOT, args.target, args.repo)
    final_authority = POLICY.admit_source(ROOT, args.target, args.repo, args.source_sha, candidate=args.candidate)
    if final_authority != authority:
        raise ValueError("workflow source authority changed during verification")
    result["source_authority"] = authority
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
