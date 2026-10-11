"""Early managed-job admission for explicitly selected dependency pull requests."""
from __future__ import annotations

import copy
from .events import normalize_workflow_events
from .schema import WorkflowExecutionPolicy


DEPENDENCY_PROPOSAL_MATCH = (
    "github.event.pull_request.user.login == 'dependabot[bot]' || "
    "(github.event.pull_request.user.login == 'github-actions[bot]' && "
    "github.event.pull_request.head.ref == 'automation/dependency-lock-refresh')"
)
UNVERIFIED_JOB_PREFIX = "${{ (" + DEPENDENCY_PROPOSAL_MATCH + ") && 'unverified dependency / ' || '' }}"

PR_EVENTS = frozenset({"pull_request", "pull_request_target", "pull_request_review"})
DEPENDENCY_PR_EXCLUSION = (
    "(github.event_name != 'pull_request' && github.event_name != 'pull_request_target' && "
    "github.event_name != 'pull_request_review') || "
    "(github.event.pull_request.user.login != 'dependabot[bot]' && "
    "(github.event.pull_request.user.login != 'github-actions[bot]' || "
    "github.event.pull_request.head.ref != 'automation/dependency-lock-refresh'))"
)


def requires_dependency_projection(policy: WorkflowExecutionPolicy | None) -> bool:
    return policy is not None and policy.get("dependency_pull_requests") in {"skip-managed-jobs", "notification-only"}


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


def _guaranteed_predicates(condition: str) -> set[str]:
    """Find mandatory atomic clauses without treating quoted text as an event guard."""
    expression = condition.strip()
    if expression.startswith("${{") and expression.endswith("}}"):
        expression = expression[3:-2].strip()
    _validate_expression_boundary(expression, "owned workflow_run")

    def splits(text: str, operator: str) -> list[str]:
        depth, quoted, index, start = 0, False, 0, 0
        parts = []
        while index < len(text):
            character = text[index]
            if character == "'":
                if quoted and index + 1 < len(text) and text[index + 1] == "'":
                    index += 2
                    continue
                quoted = not quoted
            elif not quoted:
                if character == "(":
                    depth += 1
                elif character == ")":
                    depth -= 1
                elif depth == 0 and text[index:index + 2] == operator:
                    parts.append(text[start:index].strip())
                    index += 2
                    start = index
                    continue
            index += 1
        return parts + [text[start:].strip()]

    def clauses(text: str) -> set[str]:
        # A complete outer group has no top-level suffix; wrapping validation
        # distinguishes it from a group followed by an escape disjunction.
        while text.startswith("(") and text.endswith(")"):
            try:
                _validate_expression_boundary(text[1:-1], "owned workflow_run")
            except ValueError:
                break
            text = text[1:-1].strip()
        alternatives = splits(text, "||")
        if len(alternatives) > 1:
            return set.intersection(*(clauses(part) for part in alternatives))
        conjunction = splits(text, "&&")
        if len(conjunction) > 1:
            return set.union(*(clauses(part) for part in conjunction))
        return {text}

    return clauses(expression)


def project_dependency_pull_requests(
    workflow_id: str, document: dict, policy: WorkflowExecutionPolicy | None,
) -> dict:
    projected = copy.deepcopy(document)
    if not requires_dependency_projection(policy):
        return projected
    events = normalize_workflow_events(workflow_id, document, allow_auxiliary=policy.get("dependency_pull_requests") == "notification-only")
    if workflow_id == "dependency-notice":
        notice = projected["jobs"].get("notice", {})
        if (set(projected["jobs"]) != {"notice"}
                or not isinstance(notice, dict)
                or set(notice) != {"name", "if", "runs-on", "timeout-minutes", "steps"}
                or notice.get("name") != "dependency / owner review notice"
                or notice.get("if") != "${{ " + DEPENDENCY_PROPOSAL_MATCH + " }}"
                or notice.get("runs-on") != "ubuntu-latest" or type(notice.get("timeout-minutes")) is not int
                or notice["timeout-minutes"] != 1 or not isinstance(notice.get("steps"), list) or len(notice["steps"]) != 1
                or not isinstance(notice["steps"][0], dict)
                or set(notice["steps"][0]) != {"name", "shell", "env", "run"}
                or notice["steps"][0].get("shell") != "bash"
                or projected.get("permissions") != {"contents": "read"}):
            raise ValueError("dependency notice requires one distinct read-only bot notice job")
        return projected
    if not PR_EVENTS.intersection(events):
        return projected
    jobs = projected["jobs"]
    if not jobs or any(not isinstance(name, str) or not isinstance(job, dict) for name, job in jobs.items()):
        raise ValueError(f"{workflow_id} requires distinct source-owned PR job objects")
    conditions = {name: _compose_condition(job, f"{workflow_id}/{name}") for name, job in jobs.items()}
    for name, condition in conditions.items():
        jobs[name]["if"] = condition
        if policy.get("dependency_pull_requests") == "notification-only":
            existing_name = jobs[name].get("name", name)
            if not isinstance(existing_name, str) or not existing_name.strip():
                raise ValueError(f"{workflow_id}/{name} requires a distinct source-owned job name")
            if not existing_name.startswith(UNVERIFIED_JOB_PREFIX):
                jobs[name]["name"] = UNVERIFIED_JOB_PREFIX + existing_name
    return projected


def validate_owned_execution(documents: dict[str, dict], policy: WorkflowExecutionPolicy | None) -> None:
    """Admit owned PR guards and event scope without creating a path-based bypass."""
    if policy is None or policy.get("dependency_pull_requests") != "notification-only":
        return
    for relative, document in documents.items():
        if not isinstance(relative, str) or not relative.endswith((".yml", ".yaml")):
            raise ValueError("owned workflow path must identify a YAML workflow")
        identity = relative.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        events = normalize_workflow_events(identity, document, allow_auxiliary=True)
        if policy.get("main_verification") == "accepted-pull-request" and "push" in events:
            raise ValueError(f"owned workflow retains duplicate push verification: {relative}")
        if "workflow_run" in events:
            entry = events["workflow_run"]
            if not isinstance(entry, dict) or entry != {"workflows": ["deploy-docs"], "types": ["completed"], "branches": ["main"]}:
                raise ValueError(f"owned workflow_run requires bounded manual docs followthrough: {relative}")
            for job in document["jobs"].values():
                condition = job.get("if", "")
                if not isinstance(condition, str):
                    raise ValueError(f"owned workflow_run job requires a source-owned condition: {relative}")
                predicates = _guaranteed_predicates(condition)
                required = {"github.event_name == 'workflow_run'", "github.event.workflow_run.conclusion == 'success'", "github.event.workflow_run.head_branch == 'main'"}
                if "github.event_name != 'workflow_run'" not in predicates and not required.issubset(predicates):
                    raise ValueError(f"owned workflow_run job lacks successful-main admission: {relative}")
        projected = project_dependency_pull_requests(identity, document, policy)
        if document != projected:
            raise ValueError(f"owned dependency job admission is missing: {relative}")
