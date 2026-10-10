#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


WAITING_EXTERNAL_EXIT_CODE = 75


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def parse_github_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def github_get_json(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def format_run(run: dict[str, Any]) -> str:
    run_id = run.get("id", "unknown")
    created_at = run.get("created_at", "unknown")
    status = run.get("status", "unknown")
    conclusion = run.get("conclusion") or "pending"
    html_url = run.get("html_url", "")
    return (
        f"run_id={run_id} created_at={created_at} "
        f"status={status} conclusion={conclusion} {html_url}"
    ).strip()


def latest_ci_run(
    runs: list[dict[str, Any]],
    target_ref_name: str,
) -> dict[str, Any] | None:
    candidates = [
        run
        for run in runs
        if run.get("name") == "CI"
        and run.get("event") == "push"
    ]
    if not candidates:
        return None

    if target_ref_name:
        ref_matched = [run for run in candidates if run.get("head_branch") == target_ref_name]
        if ref_matched:
            candidates = ref_matched

    candidates.sort(key=lambda run: parse_github_time(run["created_at"]), reverse=True)
    return candidates[0]


def main() -> int:
    token = require_env("GITHUB_TOKEN")
    repository = require_env("GITHUB_REPOSITORY")
    target_sha = require_env("TARGET_SHA")
    target_ref_name = os.environ.get("TARGET_REF_NAME", "").strip()

    api_root = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    workflow_file = os.environ.get("GH_RELEASE_CI_WORKFLOW_FILE", "ci.yml")

    url = (
        f"{api_root}/repos/{repository}/actions/workflows/"
        f"{urllib.parse.quote(workflow_file, safe='')}/runs"
        f"?event=push&head_sha={urllib.parse.quote(target_sha, safe='')}&per_page=20"
    )

    print(
        "Observing CI workflow before release publish:",
        f"workflow={workflow_file}",
        f"sha={target_sha}",
        sep=" ",
    )
    payload = github_get_json(url, token)
    runs = payload.get("workflow_runs", [])
    run = latest_ci_run(runs, target_ref_name)
    if run is None:
        print(
            "CI run is waiting_external; invoke this observation again after the next "
            "workflow event.",
            file=sys.stderr,
        )
        return WAITING_EXTERNAL_EXIT_CODE

    print(f"Observed CI run: {format_run(run)}")
    status = run.get("status")
    conclusion = run.get("conclusion")
    if status != "completed":
        print(
            "CI run is waiting_external; invoke this observation again after the next "
            "workflow event.",
            file=sys.stderr,
        )
        return WAITING_EXTERNAL_EXIT_CODE
    if conclusion == "success":
        print("CI gate passed; release workflow may continue.")
        return 0
    print(f"CI gate failed with conclusion={conclusion}; stopping release publish.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
