"""Derive and verify managed governance bytes without mutating a product checkout."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .canonical_sources import capture_sources, owning_scripts, read_owned, validate_source_snapshots
from .schema import validate_manifest
from .events import requires_event_projection
from .publication import requires_publication_projection
from .dependency_prs import requires_dependency_projection
from .source_loading import MODULE_ORDER


def requires_parser(source_root: Path, repository: str) -> bool:
    manifest = json.loads(read_owned(source_root, ".github/standards/repo-config.manifest.json"))
    policy = validate_manifest(manifest, [repository])[repository]
    return any(predicate(policy) for predicate in (requires_event_projection, requires_publication_projection, requires_dependency_projection))


def expected_projection(source_root: Path, target: Path, repository: str) -> tuple[dict[str, bytes | None], set[str]]:
    sync, renderer = owning_scripts(source_root)
    manifest = json.loads(read_owned(source_root, ".github/standards/repo-config.manifest.json"))
    validate_manifest(manifest, [repository])
    repo = sync.find_repo_config(manifest, repository)
    sync.resolve_repository_checkout = lambda name: target
    # This invokes structural preparation and authored-call admission, never a writer.
    runtime = sync.prepare_runtime_workflows(repo, manifest)
    prepared = {destination: runtime.get(destination, read_owned(source_root, source))
                for source, destination in sync.BASE_FILE_MAPPINGS
                if destination != ".github/bijux-std-shared.sha256"
                and not destination.startswith(".github/standards/workflow-sources/")}
    # Verify the executable package closure even if a copy mapping accidentally omits a dependency.
    for name in (*MODULE_ORDER, "__init__"):
        relative = f".github/scripts/workflow_execution/{name}.py"
        prepared[relative] = read_owned(source_root, relative)
    prepared[".github/scripts/check_workflow_projection.py"] = read_owned(
        source_root, ".github/scripts/check_workflow_projection.py"
    )
    allowed = set(repo.get("workflow_allowlist", []))
    absent = set(sync.LEGACY_MANAGED_RUNTIME_PATHS) | set(sync.LEGACY_MANAGED_SHARED_PATHS)
    for entry in sync.inventory_entries(manifest):
        raw = read_owned(source_root, entry["source"])
        # The canonical writer retains a raw mirror for every inventory entry in every repository.
        prepared[".bijux/" + entry["source"]] = raw
        if repository == "bijux-std":
            prepared[entry["source"]] = raw
        if entry["id"] in allowed:
            prepared[entry["consumer_runtime"]] = runtime.get(entry["consumer_runtime"], raw)
        else:
            absent.add(entry["consumer_runtime"])
    absent -= set(prepared)
    prepared.update(renderer.prepare_repo_files(repository, manifest))
    prepared.update(capture_sources(source_root))
    return prepared, absent


def verify_projection(source_root: Path, target: Path, repository: str) -> dict:
    """Compare source-derived bytes; local checksum rebinding cannot make a match."""
    source_root, target = source_root.resolve(), target.resolve()
    validate_source_snapshots(source_root)
    expected, absent = expected_projection(source_root, target, repository)
    failures = []
    verified = {}
    for relative, body in sorted(expected.items()):
        path = target / relative
        if body is None:
            if path.is_file() and b"SSOT NOTICE" in read_owned(target, relative)[:250]:
                failures.append(f"unexpected generated wrapper: {relative}")
            continue
        try:
            actual = read_owned(target, relative)
        except (ValueError, OSError) as error:
            failures.append(f"unreadable managed projection {relative}: {error}")
            continue
        if actual != body:
            failures.append(f"noncanonical managed projection: {relative}")
        verified[relative] = hashlib.sha256(body).hexdigest()
    for relative in sorted(absent):
        path = target / relative
        if path.exists() or path.is_symlink():
            failures.append(f"disabled managed destination is present: {relative}")
    # Re-read the finite source graph after comparison to refuse concurrent source changes.
    current, current_absent = expected_projection(source_root, target, repository)
    if current != expected or current_absent != absent:
        failures.append("canonical source changed during workflow verification")
    if failures:
        raise ValueError("\n".join(failures))
    return {"repository": repository, "verified_files": verified, "absent_paths": sorted(absent), "mutated_product": False}
