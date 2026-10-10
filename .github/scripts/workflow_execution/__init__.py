"""Supported repository workflow execution policy interfaces."""
from .schema import PublicationEntrypoint, WorkflowExecutionPolicy, validate_inventory, validate_manifest, validate_policy
from .yaml_io import parse_workflow
from .events import project_automatic_events, requires_event_projection
from .refs import project_publication_refs
from .dependency_prs import project_dependency_pull_requests, requires_dependency_projection
from .publication import (
    manual_publication_entrypoints, project_publication_entrypoints,
    requires_publication_projection, validate_publication_calls,
)

from .canonical_sources import capture_sources, validate_source_snapshots
from .source_authority import admit_source
from .verification import requires_parser, verify_projection

__all__ = [
    "PublicationEntrypoint", "WorkflowExecutionPolicy", "validate_inventory", "validate_manifest", "validate_policy",
    "parse_workflow", "project_automatic_events", "requires_event_projection", "project_publication_refs",
    "manual_publication_entrypoints", "project_publication_entrypoints",
    "requires_publication_projection", "validate_publication_calls",
    "project_dependency_pull_requests", "requires_dependency_projection",
    "capture_sources", "validate_source_snapshots", "admit_source", "requires_parser", "verify_projection",
]
