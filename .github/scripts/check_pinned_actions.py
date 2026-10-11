#!/usr/bin/env python3
"""Admit immutable workflow job and step references through canonical YAML parsing."""
from __future__ import annotations

import re
import sys
import json
from pathlib import Path

from workflow_execution.yaml_io import parse_workflow

PINNED_PATTERN = re.compile(
    r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*@[0-9a-f]{40}"
)


def manifest_managed_paths(manifest_path: Path) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("workflow_inventory", {}).get("managed_workflows", [])
    paths: list[str] = []
    for entry in entries:
        source = entry.get("source")
        runtime = entry.get("consumer_runtime")
        if isinstance(source, str) and source and Path(source).exists():
            paths.append(source)
        if isinstance(runtime, str) and runtime and Path(runtime).exists():
            paths.append(runtime)
    return paths


def gather_workflow_files(raw_paths: list[str]) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    missing: list[str] = []
    seen: set[Path] = set()

    for raw_path in raw_paths:
        path = Path(raw_path)
        if not path.exists():
            missing.append(raw_path)
            continue
        if path.is_dir():
            recursive_matches = sorted(path.rglob("*.yml")) + sorted(path.rglob("*.yaml"))
            for item in recursive_matches:
                if not item.is_file():
                    continue
                resolved = item.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(item)
            continue

        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        files.append(path)

    return files, missing


def main() -> int:
    raw_args = sys.argv[1:]
    extra_paths: list[str] = []
    direct_paths: list[str] = []
    i = 0
    while i < len(raw_args):
        arg = raw_args[i]
        if arg == "--manifest-managed":
            if i + 1 >= len(raw_args):
                print("error: --manifest-managed requires <manifest-path>", file=sys.stderr)
                return 2
            extra_paths.extend(manifest_managed_paths(Path(raw_args[i + 1])))
            i += 2
            continue
        direct_paths.append(arg)
        i += 1

    if not direct_paths and not extra_paths:
        print("usage: check_pinned_actions.py [--manifest-managed <manifest.json>] <workflow-path> [<workflow-path> ...]", file=sys.stderr)
        return 2

    workflow_files, missing_paths = gather_workflow_files(direct_paths + extra_paths)
    violations: list[str] = []
    for missing in missing_paths:
        violations.append(f"missing path: {missing}")

    for path in workflow_files:
        try:
            document = parse_workflow(path.read_bytes(), str(path))
            for job_name, job in document["jobs"].items():
                if not isinstance(job, dict):
                    raise ValueError(f"job {job_name!r} must be a mapping")
                references = []
                if "uses" in job:
                    references.append((f"jobs.{job_name}.uses", job["uses"]))
                steps = job.get("steps", [])
                if not isinstance(steps, list):
                    raise ValueError(f"job {job_name!r} steps must be a sequence")
                for index, step in enumerate(steps):
                    if not isinstance(step, dict):
                        raise ValueError(f"job {job_name!r} step {index} must be a mapping")
                    if "uses" in step:
                        references.append((f"jobs.{job_name}.steps[{index}].uses", step["uses"]))
                for location, reference in references:
                    if not isinstance(reference, str) or not reference:
                        violations.append(f"{path}:{location}: action reference must be a nonempty string")
                    elif reference.startswith("./") or reference.startswith("docker://"):
                        continue
                    elif not PINNED_PATTERN.fullmatch(reference) or any(
                        part in {".", ".."} for part in reference.split("@", 1)[0].split("/")
                    ):
                        violations.append(f"{path}:{location}: unpinned action reference '{reference}'")
        except (OSError, ValueError, RuntimeError) as error:
            violations.append(f"{path}: {error}")

    if violations:
        print("Found unpinned action references:", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
