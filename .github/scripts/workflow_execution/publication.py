"""Manual publication API selection and local reusable caller admission."""
from __future__ import annotations

import copy
from .events import normalize_workflow_events
from .schema import PUBLICATION_ENTRYPOINTS, WorkflowExecutionPolicy
from .refs import project_publication_refs


def manual_publication_entrypoints(policy: WorkflowExecutionPolicy | None) -> set[str]:
    if policy is None:
        return set()
    return {identity for identity, definition in policy.get("publication_entrypoints", {}).items()
            if definition["mode"] == "manual-only"}


def requires_publication_projection(policy: WorkflowExecutionPolicy | None) -> bool:
    return bool(manual_publication_entrypoints(policy)) or (policy is not None and policy.get("publication_entrypoints") == {})


def project_publication_entrypoints(workflow_id: str, document: dict, policy: WorkflowExecutionPolicy | None) -> dict:
    projected = copy.deepcopy(document)
    if workflow_id not in manual_publication_entrypoints(policy):
        return projected
    events = normalize_workflow_events(workflow_id, document)
    if "workflow_dispatch" not in events or set(events) - {"workflow_dispatch", "workflow_call"}:
        raise ValueError(f"{workflow_id} must expose its canonical dispatch/call publication API")
    # Dispatch input/help/default identity and every job remain source-owned.
    events.pop("workflow_call", None)
    projected["on"] = events
    controlled = (policy or {}).get("publication_entrypoints", {}).get(workflow_id, {}).get("controller") == "iac"
    if not controlled or "publication_admission" not in projected.get("jobs", {}):
        projected = project_publication_refs(workflow_id, projected, policy)
    return project_controller(workflow_id, projected) if controlled else projected


def validate_publication_calls(documents: dict[str, dict], policy: WorkflowExecutionPolicy | None) -> None:
    manual = manual_publication_entrypoints(policy)
    no_publishers = policy is not None and policy.get("publication_entrypoints") == {}
    if not manual and not no_publishers:
        return
    forbidden_entrypoints = PUBLICATION_ENTRYPOINTS if no_publishers else manual
    forbidden = {f"./.github/workflows/{identity}.yml" for identity in forbidden_entrypoints}
    for path, document in documents.items():
        jobs = document.get("jobs")
        if not isinstance(jobs, dict):
            raise ValueError(f"{path} caller jobs must be an object")
        for identity, job in jobs.items():
            if not isinstance(job, dict):
                raise ValueError(f"{path} caller job {identity} must be an object")
            target = job.get("uses")
            if "uses" in job and (not isinstance(target, str) or not target.strip()):
                raise ValueError(f"{path} caller job {identity} uses must be a workflow reference")
            if isinstance(target, str):
                reference = target.strip().split("@", 1)[0]
                if reference in forbidden or reference.rsplit("/", 1)[-1] in {name + ".yml" for name in forbidden_entrypoints}:
                    raise ValueError(f"{path} job {identity} calls manual-only publication entrypoint {target}")
            controlled = no_publishers or any(entry.get("controller") == "iac" for entry in (policy or {}).get("publication_entrypoints", {}).values())
            basename = path.rsplit("/", 1)[-1]
            if controlled and external_publisher(job) and basename not in {name + ".yml" for name in manual}:
                raise ValueError(f"{path} contains a renamed publisher outside canonical manual entrypoints")


def controller_admission_job(workflow_id: str) -> dict:
    return {
        "name": "publication / admission", "runs-on": "ubuntu-latest",
        "permissions": {"contents": "read", "checks": "read"},
        "steps": [
            {"name": "Checkout immutable workflow input", "uses": "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
             "with": {"ref": "${{ github.sha }}", "persist-credentials": False}},
            {"name": "Authorize authenticated exact-commit publication", "env": {
                "GH_TOKEN": "${{ github.token }}", "PUBLICATION_REPOSITORY": "${{ github.repository }}",
                "PUBLICATION_EVENT": "${{ github.event_name }}", "PUBLICATION_REF": "${{ github.ref }}",
                "PUBLICATION_ACTOR": "${{ github.actor }}", "PUBLICATION_ACTOR_ID": "${{ github.actor_id }}",
                "PUBLICATION_TRIGGERING_ACTOR": "${{ github.triggering_actor }}",
                "PUBLICATION_CONTROLLER_ACTOR_ID": "${{ vars.BIJUX_PUBLICATION_ACTOR_ID }}",
                "PUBLICATION_COMMIT": "${{ inputs.accepted_commit }}", "PUBLICATION_RUN_SHA": "${{ github.sha }}",
                "PUBLICATION_WORKFLOW": workflow_id, "PUBLICATION_TAG": "${{ inputs.release_tag || '' }}",
                "PYTHONPYCACHEPREFIX": "${{ github.workspace }}/artifacts/python/pycache",
            }, "run": "python3 .bijux/shared/bijux-gh/scripts/publication_admission.py"},
        ],
    }


def project_controller(workflow_id: str, document: dict) -> dict:
    projected = copy.deepcopy(document)
    admission = controller_admission_job(workflow_id)
    jobs = projected.get("jobs", {})
    if "publication_admission" in jobs:
        if jobs["publication_admission"] != admission:
            raise ValueError("publication admission differs from its canonical definition")
        return projected
    dispatch = projected["on"].get("workflow_dispatch") or {}
    if not isinstance(dispatch, dict):
        raise ValueError("controller publication dispatch must be an object")
    inputs = dispatch.setdefault("inputs", {})
    inputs["accepted_commit"] = {"description": "Immutable accepted main commit selected by bijux-iac", "type": "string", "required": True}
    if workflow_id != "deploy-docs":
        if "release_tag" not in inputs:
            raise ValueError("controller releases require the canonical release_tag input")
        inputs["release_tag"]["required"] = True
    projected["on"]["workflow_dispatch"] = dispatch
    for name, job in jobs.items():
        if not isinstance(job, dict):
            raise ValueError(f"{name}: malformed publisher job")
        needs = job.get("needs", [])
        needs = [needs] if isinstance(needs, str) else needs
        if not isinstance(needs, list) or "publication_admission" in needs:
            raise ValueError(f"{name}: ambiguous publication admission dependency")
        job["needs"] = ["publication_admission", *needs]
        condition = job.get("if", "success()")
        if not isinstance(condition, str):
            raise ValueError(f"{name}: malformed publication condition")
        expression = condition.strip()
        if expression.startswith("${{") and expression.endswith("}}"):
            expression = expression[3:-2].strip()
        job["if"] = "${{ needs.publication_admission.result == 'success' && (" + expression + ") }}"
    projected["jobs"] = {"publication_admission": admission, **jobs}
    return projected


def external_publisher(job: dict) -> bool:
    import re
    for step in job.get("steps", []):
        if not isinstance(step, dict):
            raise ValueError("publisher steps must be objects")
        action = step.get("uses", "").split("@", 1)[0]
        if action in {"actions/deploy-pages", "pypa/gh-action-pypi-publish", "softprops/action-gh-release"}:
            return True
        if action == "docker/build-push-action" and step.get("with", {}).get("push") not in {None, False, "false"}:
            return True
        for line in str(step.get("run", "")).splitlines():
            if line.lstrip().startswith("#") or "--dry-run" in line:
                continue
            if re.search(r"(?:^|[;&\s])(?:cargo\s+publish|uv\s+publish|twine\s+upload|docker\s+push|gh\s+release\s+(?:create|upload))\b", line):
                return True
    return False
