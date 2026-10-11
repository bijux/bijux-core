#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


API_VERSION = "2022-11-28"
WAITING_EXTERNAL_EXIT_CODE = 75


@dataclass(frozen=True)
class RequiredWorkflow:
    identifier: str
    fail_on_non_success: bool = True
    allowed_events: tuple[str, ...] = ()


def _event_payload() -> dict:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise RuntimeError("GITHUB_EVENT_PATH is required")
    return json.loads(Path(event_path).read_text(encoding="utf-8"))


def _api_get_json(path: str) -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repository:
        raise RuntimeError("GITHUB_TOKEN and GITHUB_REPOSITORY are required")

    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
        },
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def _current_head_sha(event: dict) -> str:
    pull_request = event.get("pull_request")
    if isinstance(pull_request, dict):
        head = pull_request.get("head")
        if isinstance(head, dict):
            sha = head.get("sha")
            if isinstance(sha, str) and sha:
                return sha

    merge_group = event.get("merge_group")
    if isinstance(merge_group, dict):
        sha = merge_group.get("head_sha")
        if isinstance(sha, str) and sha:
            return sha

    sha = os.environ.get("GITHUB_SHA")
    if not sha:
        raise RuntimeError("Unable to resolve GITHUB_SHA")
    return sha


def _required_workflows(event_name: str) -> list[RequiredWorkflow]:
    override = os.environ.get("BIJUX_REQUIRED_WORKFLOWS", "").strip()
    if override:
        identifiers = [
            identifier.strip()
            for identifier in override.split(",")
            if identifier.strip()
        ]
        return [RequiredWorkflow(identifier) for identifier in identifiers]

    if event_name in {"workflow_call", "workflow_dispatch"}:
        return []
    if event_name in {"pull_request", "pull_request_target", "pull_request_review"}:
        return [
            RequiredWorkflow(
                ".github/workflows/bijux-std.yml",
                allowed_events=("pull_request",),
            ),
            # Approval failures should stop downstream work immediately.
            # A later label or review update creates a new event and a new run.
            RequiredWorkflow(
                ".github/workflows/pr-approval-policy.yml",
                allowed_events=("pull_request_target", "pull_request_review"),
            ),
        ]
    if event_name in {"merge_group", "push"}:
        return [
            RequiredWorkflow(
                ".github/workflows/bijux-std.yml",
                allowed_events=(event_name,),
            )
        ]
    return []


def _list_workflow_runs(head_sha: str) -> list[dict]:
    query = urllib.parse.urlencode({"head_sha": head_sha, "per_page": 100})
    payload = _api_get_json(f"/actions/runs?{query}")
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        return []
    return runs


def _run_matches_event(run: dict, workflow: RequiredWorkflow) -> bool:
    if not workflow.allowed_events:
        return True
    event_name = run.get("event")
    return isinstance(event_name, str) and event_name in workflow.allowed_events


def _run_matches_identifier(run: dict, workflow: RequiredWorkflow) -> bool:
    if workflow.identifier.startswith(".github/workflows/"):
        return run.get("path") == workflow.identifier
    return run.get("name") == workflow.identifier


def _run_has_materialized_jobs(run: dict, jobs_cache: dict[int, bool]) -> bool:
    run_id = run.get("id")
    if not isinstance(run_id, int):
        return False
    cached = jobs_cache.get(run_id)
    if cached is not None:
        return cached

    payload = _api_get_json(f"/actions/runs/{run_id}/jobs?per_page=1")
    total_count = payload.get("total_count")
    jobs = payload.get("jobs")
    has_jobs = bool(total_count) if isinstance(total_count, int) else bool(jobs)
    jobs_cache[run_id] = has_jobs
    return has_jobs


def _latest_run_for_identifier(
    runs: list[dict],
    workflow: RequiredWorkflow,
    jobs_cache: dict[int, bool],
) -> dict | None:
    matching = [
        run
        for run in runs
        if isinstance(run, dict)
        and _run_matches_identifier(run, workflow)
        and _run_matches_event(run, workflow)
        and _run_has_materialized_jobs(run, jobs_cache)
    ]
    if not matching:
        return None

    def sort_key(run: dict) -> tuple[str, int]:
        created_at = str(run.get("created_at") or "")
        run_number = int(run.get("run_number") or 0)
        return (created_at, run_number)

    return max(matching, key=sort_key)


def _run_state_text(run: dict | None) -> str:
    if run is None:
        return "missing"
    status = run.get("status") or "unknown"
    conclusion = run.get("conclusion") or "pending"
    return f"{status}/{conclusion}"


def _all_prerequisites_ready(
    required: list[RequiredWorkflow],
    runs: list[dict],
) -> tuple[bool, list[str]]:
    states: list[str] = []
    jobs_cache: dict[int, bool] = {}
    for workflow in required:
        run = _latest_run_for_identifier(runs, workflow, jobs_cache)
        states.append(f"{workflow.identifier}={_run_state_text(run)}")
        if run is None:
            return (False, states)
        status = run.get("status")
        conclusion = run.get("conclusion")
        if status != "completed":
            return (False, states)
        if conclusion != "success":
            if workflow.fail_on_non_success:
                raise RuntimeError(
                    f"Required workflow '{workflow.identifier}' completed with conclusion "
                    f"'{conclusion}'."
                )
            return (False, states)
    return (True, states)


def main() -> None:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    required = _required_workflows(event_name)
    if not required:
        print(f"No workflow prerequisites required for event '{event_name}'.")
        return

    event = _event_payload()
    head_sha = _current_head_sha(event)
    runs = _list_workflow_runs(head_sha)
    ready, states = _all_prerequisites_ready(required, runs)
    print(f"Workflow prerequisites for {head_sha}: {', '.join(states)}")
    if ready:
        print("All prerequisite workflows completed successfully.")
        return
    print(
        "Workflow prerequisites are waiting_external; invoke this observation again "
        "after the next workflow event."
    )
    raise SystemExit(WAITING_EXTERNAL_EXIT_CODE)


if __name__ == "__main__":
    main()
