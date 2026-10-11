"""Early managed-job admission for explicitly selected dependency pull requests."""
from __future__ import annotations

import copy
from .events import normalize_workflow_events
from .schema import WorkflowExecutionPolicy


PR_EVENTS = frozenset({"pull_request", "pull_request_target", "pull_request_review"})
DEPENDENCY_PR_EXCLUSION = (
    "(github.event_name != 'pull_request' && github.event_name != 'pull_request_target' && "
    "github.event_name != 'pull_request_review') || "
    "github.event.pull_request.user.login != 'dependabot[bot]'"
)


def requires_dependency_projection(policy: WorkflowExecutionPolicy | None) -> bool:
    return policy is not None and policy.get("dependency_pull_requests") == "skip-managed-jobs"


def _validate_expression_boundary(expression: str, label: str) -> None:
    """Validate grouping/quoting boundaries without interpreting source-owned expressions."""
    if not expression or "${{" in expression or "}}" in expression or "\0" in expression:
        raise ValueError(f"{label} has an empty or ambiguous job expression")
    depth, quoted, index = 0, False, 0
    while index < len(expression):
        character = expression[index]
        if character == "'":
            if quoted and index + 1 < len(expression) and expression[index + 1] == "'":
                index += 2
                continue
            quoted = not quoted
        elif not quoted:
            if character in "{}":
                raise ValueError(f"{label} has ambiguous expression delimiters")
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth < 0:
                    raise ValueError(f"{label} has unbalanced job expression grouping")
        index += 1
    if depth or quoted:
        raise ValueError(f"{label} has unbalanced job expression grouping or quoting")


def _compose_condition(job: dict, label: str) -> str:
    if "if" not in job:
        return "${{ " + DEPENDENCY_PR_EXCLUSION + " }}"
    existing = job["if"]
    if not isinstance(existing, str) or not existing.strip():
        raise ValueError(f"{label} job if must be a nonempty source-owned expression")
    expression = existing.strip()
    if expression.startswith("${{") and expression.endswith("}}"):
        expression = expression[3:-2].strip()
    _validate_expression_boundary(expression, label)
    if expression == DEPENDENCY_PR_EXCLUSION:
        return "${{ " + expression + " }}"
    prefix = "(" + DEPENDENCY_PR_EXCLUSION + ") && ("
    if expression.startswith(prefix) and expression.endswith(")"):
        # A trailing disjunction cannot masquerade as the complete projected grouping.
        _validate_expression_boundary(expression[len(prefix):-1], label)
        return "${{ " + expression + " }}"
    return "${{ (" + DEPENDENCY_PR_EXCLUSION + ") && (" + expression + ") }}"


def project_dependency_pull_requests(
    workflow_id: str, document: dict, policy: WorkflowExecutionPolicy | None,
) -> dict:
    projected = copy.deepcopy(document)
    if not requires_dependency_projection(policy):
        return projected
    events = normalize_workflow_events(workflow_id, document)
    if not PR_EVENTS.intersection(events):
        return projected
    jobs = projected["jobs"]
    if not jobs or any(not isinstance(name, str) or not isinstance(job, dict) for name, job in jobs.items()):
        raise ValueError(f"{workflow_id} requires distinct source-owned PR job objects")
    conditions = {name: _compose_condition(job, f"{workflow_id}/{name}") for name, job in jobs.items()}
    for name, condition in conditions.items():
        jobs[name]["if"] = condition
    return projected
