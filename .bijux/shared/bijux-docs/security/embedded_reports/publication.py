"""Derive finite reader composition scope before trusted producer publication.

This adapter grants no renderer or publication authority. The actual producer
must still rebuild source outputs under its independently admitted environment.
"""
from pathlib import Path

from .contract import AdmissionError, digest, json_data, read_owned, source_inputs
from .html import report_class
from .integration import verify_composition


def verify_readers(site, csp, completed_build, *, repository, identity, checkpoint):
    """Reconstruct only source-owned zero-executable readers and useful discovery."""
    retained = csp.get("embedded")
    if not isinstance(retained, dict) or identity is None or checkpoint is None:
        raise AdmissionError(
            "independently reconstructed producer capability admission requires source-owned reader evidence"
        )
    if completed_build.get("state") != "complete":
        raise AdmissionError("reader publication requires the completed actual renderer")
    repo = Path(repository).resolve()
    descriptor_path = Path(retained.get("descriptor_path", ""))
    if not descriptor_path.is_absolute() or not descriptor_path.is_relative_to(repo):
        raise AdmissionError("reader publication descriptor must belong to its exact repository")
    name = descriptor_path.relative_to(repo).as_posix()
    content = read_owned(repo, name)
    if len(content) > 2097152 or descriptor_path.stat().st_nlink != 1:
        raise AdmissionError("reader publication descriptor must be bounded and singly owned")
    descriptor = json_data(content)
    fields = {"schema", "site_url", "config", "resolved_config_sha256",
              "producer_inputs", "reports", "parents", "reader_purpose"}
    if not isinstance(descriptor, dict) or set(descriptor) != fields:
        raise AdmissionError("reader publication requires exact source-owned descriptor fields")
    if descriptor["schema"] != "owned-embedded-reports.v1":
        raise AdmissionError("reader publication requires supported source-owned descriptor schema")
    reports = descriptor["reports"]
    if not isinstance(reports, list) or not 1 <= len(reports) <= 512:
        raise AdmissionError("reader publication requires bounded exact report ownership")
    if descriptor["producer_inputs"] or any(
        not isinstance(report, dict) or report_class(report) != "static-reader"
        for report in reports
    ):
        raise AdmissionError("interactive producer/resource/provider admission remains separate")
    source_inputs(repo, retained["source_sha"], [{"path": name, "sha256": digest(content)}])
    admitted = verify_composition(
        Path(site), csp, completed_build, publication=True,
        identity=identity, checkpoint=checkpoint, repository=repo,
    )
    owned = admitted["report_routes"]
    if set(admitted["reader_purposes"]) != owned:
        raise AdmissionError("reader publication requires exact return/search purpose for every report")
    for name in owned:
        capability = admitted["capabilities"][name]
        if capability.get("script_sources") != ["'none'"] or capability.get("script_hashes"):
            raise AdmissionError("reader publication cannot grant executable authority")
    identity.verify_source(repo, checkpoint)
    return admitted
