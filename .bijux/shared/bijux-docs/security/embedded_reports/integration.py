"""Bind dry source plans to a complete outer CSP transaction and final artifact."""

from pathlib import Path
import copy
from html import escape

from .contract import (
    AdmissionError,
    bundle_identity,
    canonical,
    digest,
    json_data,
    read_owned,
    source_inputs,
)
from .html import (
    Document,
    executable_scripts,
    parent_iframe,
    reviewed_recipe,
    validate_report,
)
from .planning import plan_embedded_reports, final_receipt, _report_capability
from .resources import registration_data


def processor_inputs():
    root = Path(__file__).resolve().parent
    return [
        {
            "path": "security/embedded_reports/" + p.name,
            "sha256": digest(p.read_bytes()),
        }
        for p in sorted(root.glob("*.py"))
    ]


def validate_plan(plan, site):
    if (
        plan.get("schema") != 1
        or plan.get("scope") != "source-owned-embedded-report-plan"
        or plan.get("verification_only") is not True
    ):
        raise AdmissionError("unqualified or unsupported embedded plan")
    if Path(plan["site"]).resolve() != Path(site).resolve():
        raise AdmissionError("embedded plan selects a different artifact")
    if bundle_identity(Path(site))[1] != plan["initial_bundle_sha256"]:
        raise AdmissionError("embedded artifact changed after source planning")
    expected = plan_embedded_reports(
        Path(plan["repo"]),
        Path(site),
        Path(plan["descriptor_path"]),
        plan["build_receipt"],
        source_sha=plan["source_sha"],
    )
    if canonical(expected) != canonical(plan):
        raise AdmissionError(
            "embedded plan differs from independently rederived source admission"
        )
    return expected


def inputs(plan):
    return {
        "schema": 1,
        "processors": processor_inputs(),
        "descriptor_sha256": plan["descriptor_sha256"],
        "source_sha": plan["source_sha"],
        "source_inputs_sha256": digest(canonical(plan["source_inputs"])),
        "resolved_config_sha256": plan["resolved_config_sha256"],
        "build_receipt_sha256": plan["build_receipt_sha256"],
        "initial_bundle_sha256": plan["initial_bundle_sha256"],
        "navigation_sha256": digest(
            canonical(
                [
                    {k: v for k, v in entry.items() if k != "normalized_html"}
                    for entry in plan["navigation"]
                ]
            )
        ),
    }


def report(plan):
    result = copy.deepcopy(plan)
    result["scope"] = "source-owned-embedded-csp"
    result["applied"] = True
    for entry in result["navigation"]:
        entry.pop("normalized_html")
    for record in result["records"]:
        record.pop("normalized_html")
        record.pop("admitted_scripts")
    return result


def _policy(content):
    document = Document(content)
    policies = [
        a["content"]
        for tag, a in document.tags
        if tag == "meta"
        and a.get("http-equiv", "").lower() == "content-security-policy"
    ]
    if len(policies) != 1:
        raise AdmissionError("owned route must have one effective CSP")
    return policies[0]


def verify_composition(
    site,
    csp_report,
    completed_build,
    *,
    publication=False,
    identity=None,
    checkpoint=None,
    repository=None,
):
    retained = csp_report.get("embedded")
    expected_inputs = csp_report.get("policy_inputs", {}).get("embedded")
    if (
        retained is None
        or expected_inputs is None
        or retained.get("scope") != "source-owned-embedded-csp"
        or retained.get("applied") is not True
    ):
        raise AdmissionError("typed source-owned embedded receipt is required")
    if expected_inputs.get("processors") != processor_inputs():
        raise AdmissionError(
            "embedded admission processors differ from reviewed source"
        )
    if Path(retained["site"]).resolve() != Path(site).resolve():
        raise AdmissionError("embedded receipt selects another artifact")
    repo = Path(retained["repo"])
    descriptor_path = Path(retained["descriptor_path"])
    if (
        descriptor_path.is_symlink()
        or digest(descriptor_path.read_bytes()) != retained["descriptor_sha256"]
    ):
        raise AdmissionError("embedded owner descriptor changed")
    if publication:
        # Call the standard's independent source verifier, not a boolean contained
        # in descriptor or a report. Every selected producer/input is a commit blob.
        if (
            repository is None
            or repo.resolve() != Path(repository).resolve()
            or not descriptor_path.resolve().is_relative_to(repo.resolve())
        ):
            raise AdmissionError(
                "publication descriptor must be tracked inside the selected source repository"
            )
        relative = descriptor_path.resolve().relative_to(repo.resolve()).as_posix()
        source_inputs(
            repo,
            retained["source_sha"],
            [{"path": relative, "sha256": retained["descriptor_sha256"]}],
        )
        if identity is None or checkpoint is None:
            raise AdmissionError(
                "independently accepted source and producer/input checkpoint required"
            )
        identity.verify_source(repo, checkpoint)
        if (
            checkpoint["repository_source"]["sha"] != retained["source_sha"]
            or completed_build.get("source_checkpoint") != checkpoint
            or completed_build.get("verification_only") is not False
            or completed_build.get("scope") != "actual-mkdocs-renderer"
        ):
            raise AdmissionError(
                "embedded publication lacks actual accepted source/render checkpoint"
            )
        beginning = {
            key: value
            for key, value in completed_build.items()
            if key not in {"bundle_sha256", "limitations"}
        }
        beginning.update(state="prepared", verification_only=True)
        if beginning != retained["build_receipt"]:
            raise AdmissionError(
                "embedded preflight uses another actual renderer/source checkpoint"
            )
    if retained.get("verification_only") is not True or (
        not publication and completed_build.get("verification_only") is not True
    ):
        raise AdmissionError(
            "candidate embedded receipts cannot claim publication qualification"
        )
    descriptor = json_data(descriptor_path.read_bytes())
    plan = copy.deepcopy(retained)
    plan["scope"] = "source-owned-embedded-report-plan"
    plan.pop("applied")
    originals = {item["output"]: item for item in descriptor["reports"]}
    policies = []
    from .navigation import partitions, normalize, restore

    ownership = partitions(plan["records"])
    navigation = {entry["path"]: entry for entry in plan["navigation"]}
    for record in plan["records"]:
        content = read_owned(Path(site), record["path"]).decode()
        policy = _policy(content)
        policies.append({"path": record["path"], "policy": policy})
        if record["kind"] == "owned-report":
            owner = originals[record["path"]]
            source = read_owned(repo, owner["source"]["path"]).decode()
            unlinked = source.replace(
                "<head>",
                '<head><link rel="canonical" href="'
                + escape(retained["site_url"] + record["path"], quote=True)
                + '">',
                1,
            )
            link_plan = normalize(
                unlinked, record["path"], retained["site_url"], ownership
            )
            if {
                k: v for k, v in link_plan.items() if k != "normalized_html"
            } != navigation[record["path"]]:
                raise AdmissionError("Report navigation attribution differs")
            record["normalized_html"] = link_plan["normalized_html"]
            record["admitted_scripts"] = [
                s["body"] for s in executable_scripts(Document(source))
            ]
            validated = validate_report(source, owner, retained["site_url"])
            expected_recipe = reviewed_recipe(
                repo,
                executable_scripts(validated)[0]["body"],
                owner["recipe"],
                retained["site_url"],
                record["path"],
            )
            expected_resources = []
            for name, resource in sorted(owner["resources"].items()):
                content_bytes = read_owned(repo, resource["source"])
                entry = {
                    "path": name,
                    "sha256": digest(content_bytes),
                    "bytes": len(content_bytes),
                    "kind": resource["kind"],
                }
                if resource["kind"] == "data-registration":
                    entry["data"] = registration_data(
                        content_bytes,
                        resource["registration"],
                        retained["site_url"],
                        record["path"],
                    )
                expected_resources.append(entry)
            if (
                record["source"] != owner["source"]
                or record["input_sha256"] != digest(source.encode())
                or record["normalized_sha256"]
                != digest(record["normalized_html"].encode())
                or record["canonical"] != retained["site_url"] + record["path"]
                or record["recipe"] != expected_recipe
                or record["resources"] != expected_resources
                or record["providers"] != owner["providers"]
                or record["chunk_count"]
                != sum(r["kind"] == "data-registration" for r in expected_resources)
                or record["capability"]
                != _report_capability(owner, executable_scripts(validated))
            ):
                raise AdmissionError(
                    "embedded report receipt differs from independently reviewed source/recipe/data/resource attribution"
                )
        else:
            injected = (
                '\n<meta http-equiv="Content-Security-Policy" content="' + policy + '">'
            )
            if content.count(injected) != 1:
                raise AdmissionError("parent CSP is not the exact outer insertion")
            record["normalized_html"] = content.replace(injected, "", 1)
            original_parent = restore(
                record["normalized_html"],
                navigation[record["path"]],
                retained["site_url"],
                ownership,
            )
            record["admitted_scripts"] = []
            parents = {p["output"]: p for p in descriptor["parents"]}
            owner = parents.get(record["path"])
            if (
                owner is None
                or record["source"] != owner["source"]
                or record["input_sha256"] != owner["built_html_sha256"]
                or digest(original_parent.encode()) != owner["built_html_sha256"]
                or record["normalized_sha256"]
                != digest(record["normalized_html"].encode())
            ):
                raise AdmissionError(
                    "embedded parent receipt source/output attribution differs"
                )
            frames = [retained["site_url"] + name for name in owner["reports"]]
            parent_iframe(
                read_owned(repo, owner["source"]["path"]).decode(),
                record["path"],
                frames,
                retained["site_url"],
            )
            parent_iframe(
                record["normalized_html"], record["path"], frames, retained["site_url"]
            )
        if digest(canonical(record["capability"])) != record["capability_sha256"]:
            raise AdmissionError("embedded capability digest differs")
    actual_html = {
        page.relative_to(site).as_posix(): page for page in Path(site).rglob("*.html")
    }
    eligible = {
        name
        for name, page in actual_html.items()
        if name in ownership or 'id="__config"' in page.read_text()
    }
    if set(navigation) != eligible:
        raise AdmissionError("Capability navigation coverage differs")
    for name in sorted(navigation):
        page = actual_html[name]
        content = page.read_text()
        policy = _policy(content)
        injected = (
            '\n<meta http-equiv="Content-Security-Policy" content="' + policy + '">'
        )
        if content.count(injected) != 1:
            raise AdmissionError(
                "Capability navigation requires exact outer CSP insertion"
            )
        normalized = content.replace(injected, "", 1)
        restore(normalized, navigation[name], retained["site_url"], ownership)
        navigation[name]["normalized_html"] = normalized
    if inputs(plan) != expected_inputs:
        raise AdmissionError(
            "embedded receipt source/config/processor attribution differs"
        )
    # The pure verifier does not grant authority. Its candidate view is used only
    # after the independent source verifier above; the actual final renderer
    # receipt remains bound separately and is never rewritten by this adapter.
    mechanical_build = (
        completed_build
        if not publication
        else completed_build | {"verification_only": True}
    )
    receipt = final_receipt(plan, mechanical_build, policies)
    if publication:
        identity.verify_source(repo, checkpoint)
        receipt.update(
            verification_only=False,
            source_checkpoint_sha256=digest(canonical(checkpoint)),
            actual_build_receipt_sha256=digest(canonical(completed_build)),
        )
    return {
        "receipt": receipt,
        "capabilities": {r["path"]: r["capability"] for r in plan["records"]},
        "report_routes": {
            r["path"] for r in plan["records"] if r["kind"] == "owned-report"
        },
    }
