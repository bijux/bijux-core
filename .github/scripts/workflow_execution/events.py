"""Structural automatic event restrictions preserving shared workflow jobs."""
from __future__ import annotations

import copy
from .schema import WorkflowExecutionPolicy, require_closed_object

_SUPPORTED_EVENTS = frozenset({
    "push", "pull_request", "pull_request_target", "pull_request_review",
    "merge_group", "workflow_dispatch", "workflow_call",
})


def requires_event_projection(policy: WorkflowExecutionPolicy | None) -> bool:
    return policy is not None and (policy.get("automatic_runs") == "repository-policy-only" or policy.get("main_verification") == "accepted-pull-request")


def normalize_workflow_events(workflow_id: str, document: dict, *, allow_auxiliary: bool = False) -> dict:
    if not isinstance(document, dict) or not isinstance(document.get("jobs"), dict):
        raise ValueError(f"{workflow_id} must be a workflow object with jobs")
    events = document.get("on")
    if isinstance(events, str):
        events = {events: None}
    elif isinstance(events, list):
        if any(not isinstance(event, str) for event in events) or len(set(events)) != len(events):
            raise ValueError(f"{workflow_id} has ambiguous event sequence")
        events = dict.fromkeys(events)
    if not isinstance(events, dict) or not events or any(not isinstance(event, str) for event in events):
        raise ValueError(f"{workflow_id} requires a nonempty structural event declaration")
    supported = _SUPPORTED_EVENTS | ({"schedule", "workflow_run"} if allow_auxiliary else set())
    if set(events) - supported:
        raise ValueError(f"{workflow_id} has unsupported automatic workflow events")
    if any(value is not None and not isinstance(value, dict)
           and not (allow_auxiliary and event == "schedule" and isinstance(value, list)
                    and all(isinstance(entry, dict) and set(entry) == {"cron"}
                            and isinstance(entry["cron"], str) for entry in value))
           for event, value in events.items()):
        raise ValueError(f"{workflow_id} event configuration must be an object or null")
    return copy.deepcopy(events)


def project_automatic_events(
    workflow_id: str, document: dict, policy: WorkflowExecutionPolicy | None,
) -> dict:
    """Restrict explicit consumer automatic runs without altering shared check ownership."""
    projected = copy.deepcopy(document)
    if not requires_event_projection(policy):
        return projected
    events = normalize_workflow_events(workflow_id, document, allow_auxiliary=policy.get("main_verification") == "accepted-pull-request")
    if policy.get("main_verification") == "accepted-pull-request":
        # Verification belongs to the admitted human PR; publication and bookkeeping
        # keep their separately owned entrypoints. No push is a substitute for a PR.
        events.pop("push", None)
        if not events:
            raise ValueError(f"{workflow_id} would lose every verification entrypoint")
        projected["on"] = events
        return projected
    if workflow_id == "bijux-std" and not {"pull_request", "merge_group", "workflow_dispatch"}.issubset(events):
        raise ValueError("standard runtime must retain PR, merge_group and manual qualification")
    events = copy.deepcopy(events)
    push = events.get("push")
    if "push" in events:
        if push is not None:
            push = require_closed_object(push, {"branches", "branches-ignore", "tags", "tags-ignore", "paths", "paths-ignore"}, f"{workflow_id}.push")
            for key, values in push.items():
                if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                    raise ValueError(f"{workflow_id}.push.{key} must be an array of patterns")
            for key in ["branches", "tags", "paths"]:
                if key in push and key + "-ignore" in push:
                    raise ValueError(f"{workflow_id}.push has conflicting {key} filters")
        if workflow_id != "github-policy":
            del events["push"]
    if workflow_id == "github-policy":
        if not isinstance(push, dict) or "main" not in push.get("branches", []):
            raise ValueError("repository policy source must admit explicit main push")
        push = copy.deepcopy(push)
        push["branches"] = ["main"]
        push.pop("tags", None)
        push.pop("tags-ignore", None)
        events["push"] = push
    if not events:
        raise ValueError(f"{workflow_id} policy would leave no workflow entrypoint")
    projected["on"] = events
    return projected
