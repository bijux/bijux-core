"""Reviewed documentation publication refs and pre-preparation event admission."""
from __future__ import annotations

import copy
import hashlib
from .schema import WorkflowExecutionPolicy


CANONICAL_EVENT_REF = "github.event_name != 'pull_request' && github.event_name != 'pull_request_target' && (github.ref == format('refs/heads/{0}', github.event.repository.default_branch) || startsWith(github.ref, 'refs/tags/v'))"
MAIN_EVENT_REF = "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"
GUARD_NAME = "Validate publication event and ref"
CANONICAL_GUARD_DIGEST = "3f82890af70c51874e72ed752ac1f1acdc3c2647a31968c90ddc914dede2c221"
CANONICAL_GUARD_ENV = {
    "PUBLICATION_EVENT": "${{ github.event_name }}",
    "PUBLICATION_REF": "${{ github.ref }}",
    "PUBLICATION_DEFAULT_BRANCH": "${{ github.event.repository.default_branch }}",
}
MAIN_GUARD = {
    "name": GUARD_NAME,
    "shell": "bash",
    "env": {"PUBLICATION_EVENT": "${{ github.event_name }}", "PUBLICATION_REF": "${{ github.ref }}"},
    "run": ('set -euo pipefail\n'
            'if [[ "$PUBLICATION_EVENT" != "workflow_dispatch" || "$PUBLICATION_REF" != "refs/heads/main" ]]; then\n'
            '  echo "Docs publication requires workflow_dispatch on refs/heads/main" >&2\n'
            '  exit 1\n'
            'fi\n'),
}


def _conditions(event_ref: str) -> dict[str, str]:
    return {"build": "${{ " + event_ref + " }}",
            "deploy": "${{ needs.build.outputs.site_available == 'true' && " + event_ref + " }}"}


def project_publication_refs(workflow_id: str, document: dict, policy: WorkflowExecutionPolicy | None) -> dict:
    projected = copy.deepcopy(document)
    if workflow_id != "deploy-docs" or policy is None:
        return projected
    selection = policy.get("publication_entrypoints", {}).get("deploy-docs", {})
    if selection.get("refs", "canonical") == "canonical":
        return projected
    if selection.get("refs") != "main-only" or selection.get("mode") != "manual-only":
        raise ValueError("main-only docs requires its typed manual-only selection")
    jobs = projected.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != {"build", "deploy"} or any(
        not isinstance(job, dict) for job in jobs.values()
    ):
        raise ValueError("main-only docs requires the reviewed build/deploy job ownership")
    if jobs["deploy"].get("needs") != "build":
        raise ValueError("main-only docs requires its source-owned build dependency")
    current = {name: job.get("if") for name, job in jobs.items()}
    canonical, restricted = _conditions(CANONICAL_EVENT_REF), _conditions(MAIN_EVENT_REF)
    if current != canonical and current != restricted:
        raise ValueError("main-only docs job predicates differ from the reviewed source")
    steps = jobs["build"].get("steps")
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise ValueError("main-only docs build steps must be source-owned objects")
    matches = [(index, step) for index, step in enumerate(steps) if step.get("name") == GUARD_NAME]
    if len(matches) != 1:
        raise ValueError("main-only docs requires one named publication event/ref guard")
    index, guard = matches[0]
    if current == restricted:
        if index != 0 or guard != MAIN_GUARD:
            raise ValueError("main-only docs projected guard is incomplete or changed")
        return projected
    if (index != 1 or steps[0].get("name") != "Checkout repository"
        or set(guard) != {"name", "shell", "env", "run"} or guard["shell"] != "bash"
        or guard["env"] != CANONICAL_GUARD_ENV or not isinstance(guard["run"], str)
        or hashlib.sha256(guard["run"].encode()).hexdigest() != CANONICAL_GUARD_DIGEST):
        raise ValueError("main-only docs canonical shell guard differs from the reviewed source")
    # Replace only qualified ref predicates and the guard; all publication bodies stay owned.
    for name, predicate in restricted.items():
        jobs[name]["if"] = predicate
    jobs["build"]["steps"] = [copy.deepcopy(MAIN_GUARD)] + [step for i, step in enumerate(steps) if i != index]
    return projected
