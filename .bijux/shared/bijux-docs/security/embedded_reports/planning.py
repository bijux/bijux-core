"""Source-owned route plans, with composition before a single outer CSP write."""

from pathlib import Path
from html import escape
from urllib.parse import urlsplit
import copy
import re

from .contract import (
    AdmissionError,
    bundle_identity,
    canonical,
    digest,
    json_data,
    read_owned,
    relative,
    site_url,
    source_inputs,
)
from .html import (
    Document,
    csp_hash,
    executable_scripts,
    parent_iframe,
    reviewed_recipe,
    validate_report,
)
from .resources import registration_data


def _report_capability(report, bodies):
    return {
        "script_hashes": [csp_hash(s["body"]) for s in bodies],
        "script_sources": ["'self'"],
        "frame_uris": [],
        "image_sources": ["'self'", "data:", *sorted(report["providers"])],
        "connect_sources": ["'self'"],
        "style_sources": ["'self'", "'unsafe-inline'"],
        "worker_sources": ["'none'"],
        "object_sources": ["'none'"],
    }


def _descriptor_inputs(descriptor):
    inputs = [descriptor["config"], *descriptor["producer_inputs"]]
    for report in descriptor["reports"]:
        inputs.append(report["source"])
        inputs.extend(
            {"path": r["source"], "sha256": r["sha256"]}
            for r in report["resources"].values()
        )
    inputs.extend(parent["source"] for parent in descriptor["parents"])
    unique = {}
    for item in inputs:
        if item["path"] in unique and unique[item["path"]] != item:
            raise AdmissionError("contradictory source ownership")
        unique[item["path"]] = item
    return list(unique.values())


def _config(repo, descriptor, build):
    config = descriptor["config"]
    content = read_owned(repo, config["path"])
    if digest(content) != config["sha256"] or build.get("config") != config:
        raise AdmissionError("actual build/source config identity differs")
    if build.get("resolved_config_sha256") != descriptor["resolved_config_sha256"]:
        raise AdmissionError("effective configuration identity differs")
    if build.get("site_url") != descriptor["site_url"] or build.get("schema") != 1:
        raise AdmissionError("build URL/schema identity differs")
    if build.get("scope") not in (
        "actual-mkdocs-renderer",
        "source-projection-compatibility",
    ):
        raise AdmissionError("unrecognized build evidence scope")
    if (
        build.get("scope") == "source-projection-compatibility"
        and build.get("verification_only") is not True
    ):
        raise AdmissionError("projection cannot claim a qualified render")
    if build.get("state") not in ("prepared", "complete"):
        raise AdmissionError("build receipt state differs")


def plan_embedded_reports(
    repo_root,
    site,
    descriptor_path,
    build_receipt,
    *,
    source_sha,
    publication_checkpoint=None,
):
    repo_root, site, descriptor_path = (
        Path(repo_root),
        Path(site),
        Path(descriptor_path),
    )
    if (
        descriptor_path.is_symlink()
        or not descriptor_path.is_file()
        or descriptor_path.stat().st_nlink != 1
        or descriptor_path.stat().st_size > 2097152
    ):
        raise AdmissionError("descriptor must be one bounded regular source input")
    descriptor_bytes = descriptor_path.read_bytes()
    descriptor = json_data(descriptor_bytes)
    if descriptor.get("schema") != "owned-embedded-reports.v1":
        raise AdmissionError("unknown embedded report contract")
    # A local file or self-declared boolean is not an accepted publication checkpoint.
    # Publication authority belongs to the independent source checkpoint verifier.
    if (
        publication_checkpoint is not None
        or build_receipt.get("verification_only") is not True
    ):
        raise AdmissionError(
            "mechanical planning requires verification-only scope and independent publication authority"
        )
    product_base = site_url(descriptor["site_url"])
    _config(repo_root, descriptor, build_receipt)
    mappings = {}
    checked_inputs = source_inputs(
        repo_root, source_sha, _descriptor_inputs(descriptor)
    )
    _, initial_bundle = bundle_identity(site)
    if (
        build_receipt.get("bundle_sha256") is not None
        and build_receipt["bundle_sha256"] != initial_bundle
    ):
        raise AdmissionError("build receipt is for a different artifact")
    records, seen_routes = [], set()
    for report in descriptor["reports"]:
        output = relative(report["output"])
        if output in seen_routes:
            raise AdmissionError("duplicate report route")
        seen_routes.add(output)
        original = read_owned(site, output)
        if (
            len(original) > 524288
            or len(report["resources"]) > 512
            or sum(r["bytes"] for r in report["resources"].values()) > 134217728
        ):
            raise AdmissionError(
                "static report class exceeds reviewed document/resource budget"
            )
        source = read_owned(repo_root, report["source"]["path"])
        if source != original:
            raise AdmissionError("emitted report differs from reviewed tracked source")
        document = validate_report(original.decode(), report, product_base)
        bodies = executable_scripts(document)
        if len(bodies) != 1:
            raise AdmissionError(
                "reviewed report class requires exactly one executable body"
            )
        producer_paths = {item["path"] for item in descriptor["producer_inputs"]}
        recipe_paths = {
            report["recipe"]["template"],
            *[
                item["path"]
                for item in report["recipe"]["expansions"]
                if item.get("path")
            ],
        }
        if not recipe_paths <= producer_paths:
            raise AdmissionError(
                "renderer recipe lacks tracked producer fingerprint closure"
            )
        recipe = reviewed_recipe(
            repo_root, bodies[0]["body"], report["recipe"], product_base, output
        )
        providers = report["providers"]
        if set(providers) != set(report["reviewed_provider_origins"]):
            raise AdmissionError("provider origin is not owner-reviewed")
        observed_providers = set()
        for call in report["provider_calls"]:
            callee = call["callee"]
            if not re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", callee):
                raise AdmissionError("invalid reviewed provider call")
            matches = list(re.finditer(re.escape(callee) + r"\s*\(", bodies[0]["body"]))
            for match in matches:
                literal = re.match(
                    r"\s*(['\"])(https://[^'\"]+)\1", bodies[0]["body"][match.end() :]
                )
                if literal is None:
                    raise AdmissionError(
                        "provider URL is not a reviewed static literal"
                    )
                target = urlsplit(literal.group(2))
                observed_providers.add(target.scheme + "://" + target.netloc)
        if observed_providers != set(providers):
            raise AdmissionError(
                "declared providers differ from actual reviewed executable calls"
            )
        for origin, policy in providers.items():
            url = urlsplit(origin)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.path
                or url.query
                or url.fragment
                or url.username
                or url.password
            ):
                raise AdmissionError("provider must be an exact HTTPS origin")
            if (
                not policy.get("purpose")
                or not policy.get("activation")
                or not policy.get("attribution")
                or not policy.get("terms")
            ):
                raise AdmissionError(
                    "provider privacy/attribution contract is incomplete"
                )
            if origin not in bodies[0]["body"]:
                raise AdmissionError(
                    "declared provider is not in reviewed executable source"
                )
        resource_records = []
        chunks = 0
        for resource_output, resource in sorted(report["resources"].items()):
            relative(resource_output)
            content = read_owned(site, resource_output)
            if (
                digest(content) != resource["sha256"]
                or len(content) != resource["bytes"]
                or content != read_owned(repo_root, resource["source"])
            ):
                raise AdmissionError(
                    "report resource identity differs: " + resource_output
                )
            record = {
                "path": resource_output,
                "sha256": digest(content),
                "bytes": len(content),
                "kind": resource["kind"],
            }
            if resource["kind"] == "data-registration":
                record["data"] = registration_data(
                    content, resource["registration"], product_base, output
                )
                chunks += 1
            elif resource["kind"] not in ("reviewed-script", "reviewed-style", "image"):
                raise AdmissionError("unreviewed resource kind")
            resource_records.append(record)
        # Unknown sibling executable files in this owned resource class cannot hide
        # outside its finite manifest while script-src self is enabled.
        root = Path(output).parent
        observed = {
            p.relative_to(site).as_posix()
            for p in (site / root).rglob("*")
            if p.is_file() and p.suffix.lower() in (".js", ".css")
        }
        if any(p not in report["resources"] for p in observed):
            raise AdmissionError("undeclared executable/style resource in report tree")
        bootstrap = [
            s
            for s in document.scripts
            if s["attrs"].get("id") == report["bootstrap_id"]
        ]
        if (
            len(bootstrap) != 1
            or bootstrap[0]["attrs"].get("type") != "application/json"
        ):
            raise AdmissionError("owned bootstrap is absent")
        data = json_data(bootstrap[0]["body"])
        if digest(canonical(data)) != report["bootstrap_sha256"]:
            raise AdmissionError("bootstrap manifest differs")
        canonical_url = product_base + output
        if any(
            tag == "link" and attrs.get("rel") == "canonical"
            for tag, attrs in document.tags
        ):
            raise AdmissionError("raw report must not predeclare a canonical URL")
        marker = (
            '<link rel="canonical" href="' + escape(canonical_url, quote=True) + '">'
        )
        if original.decode().count("<head>") != 1:
            raise AdmissionError("report head boundary is ambiguous")
        normalized = original.decode().replace("<head>", "<head>" + marker, 1)
        capability = _report_capability(report, bodies)
        records.append(
            {
                "kind": "owned-report",
                "path": output,
                "source": report["source"],
                "canonical": canonical_url,
                "input_sha256": digest(original),
                "normalized_sha256": digest(normalized.encode()),
                "normalized_html": normalized,
                "admitted_scripts": [s["body"] for s in bodies],
                "resources": resource_records,
                "recipe": recipe,
                "chunk_count": chunks,
                "capability": capability,
                "capability_sha256": digest(canonical(capability)),
                "providers": providers,
            }
        )
        mappings[output] = canonical_url
    for parent in descriptor["parents"]:
        output = relative(parent["output"])
        if output in seen_routes:
            raise AdmissionError("duplicate capability route")
        seen_routes.add(output)
        original = read_owned(site, output)
        frames = [mappings[name] for name in parent["reports"] if name in mappings]
        if len(frames) != len(parent["reports"]):
            raise AdmissionError("parent references undeclared report")
        parent_iframe(
            read_owned(repo_root, parent["source"]["path"]).decode(),
            output,
            frames,
            product_base,
        )
        parent_iframe(original.decode(), output, frames, product_base)
        if digest(original) != parent["built_html_sha256"]:
            raise AdmissionError(
                "parent output identity differs from reviewed build input"
            )
        # Ordinary shell script and image policy remains with the outer CSP planner.
        records.append(
            {
                "kind": "owned-parent-frame",
                "path": output,
                "source": parent["source"],
                "input_sha256": digest(original),
                "normalized_sha256": digest(original),
                "normalized_html": original.decode(),
                "admitted_scripts": [],
                "capability": {"frame_uris": frames},
                "capability_sha256": digest(canonical({"frame_uris": frames})),
            }
        )
    from .navigation import partitions, normalize

    ownership = partitions(records)
    by_route = {record["path"]: record for record in records}
    navigation = []
    for page in sorted(site.rglob("*.html")):
        name = page.relative_to(site).as_posix()
        content = (
            by_route[name]["normalized_html"] if name in by_route else page.read_text()
        )
        if name in by_route or 'id="__config"' in content:
            navigation.append(normalize(content, name, product_base, ownership))
    for entry in navigation:
        if entry["path"] in by_route:
            by_route[entry["path"]]["normalized_html"] = entry["normalized_html"]
            by_route[entry["path"]]["normalized_sha256"] = entry["normalized_sha256"]
    records.sort(key=lambda record: record["path"])
    return {
        "schema": 1,
        "scope": "source-owned-embedded-report-plan",
        "verification_only": True,
        "site": str(site.resolve()),
        "repo": str(repo_root.resolve()),
        "descriptor_path": str(descriptor_path.resolve()),
        "descriptor_sha256": digest(descriptor_bytes),
        "source_sha": source_sha,
        "source_inputs": checked_inputs,
        "build_receipt": build_receipt,
        "build_receipt_sha256": digest(canonical(build_receipt)),
        "resolved_config_sha256": build_receipt["resolved_config_sha256"],
        "site_url": product_base,
        "initial_bundle_sha256": initial_bundle,
        "records": records,
        "navigation": navigation,
        "limitations": [
            "Mechanical admission alone does not grant publication authority.",
            "No browser, scientific, live hosting, license, provider-terms or publication acceptance is inferred.",
            "Outer CSP must preflight ordinary, redirect and embedded-report pages together before any write.",
        ],
    }


def apply_plan(plan):
    """Normalize an isolated tree after independently reconstructing its complete plan."""
    site = Path(plan["site"])
    if bundle_identity(site)[1] != plan["initial_bundle_sha256"]:
        raise AdmissionError("bundle changed after full preflight")
    if digest(Path(plan["descriptor_path"]).read_bytes()) != plan["descriptor_sha256"]:
        raise AdmissionError("descriptor changed after full preflight")
    source_inputs(Path(plan["repo"]), plan["source_sha"], plan["source_inputs"])
    expected = plan_embedded_reports(
        Path(plan["repo"]),
        site,
        Path(plan["descriptor_path"]),
        plan["build_receipt"],
        source_sha=plan["source_sha"],
    )
    if canonical(expected) != canonical(plan):
        raise AdmissionError(
            "plan differs from independently rederived source contract"
        )
    pending = []
    for record in plan["records"]:
        original = read_owned(site, record["path"])
        if (
            digest(original) != record["input_sha256"]
            or digest(record["normalized_html"].encode()) != record["normalized_sha256"]
        ):
            raise AdmissionError("planned source or normalized HTML changed")
        if digest(canonical(record["capability"])) != record["capability_sha256"]:
            raise AdmissionError("planned capability changed")
        pending.append((site / record["path"], record["normalized_html"].encode()))
    # Preflight is all-or-nothing. Multi-file IO itself is not filesystem-atomic;
    # callers retain the immutable original build and publish only a complete receipt.
    for path, value in pending:
        path.write_bytes(value)


def final_receipt(plan, final_build_receipt, final_policy_records):
    """Bind completed outer CSP policy, exact resources and final bundle identity."""
    from .navigation import partitions, normalize, restore

    ownership = partitions(plan["records"])
    navigation = {
        entry["path"]: {k: v for k, v in entry.items() if k != "normalized_html"}
        for entry in plan["navigation"]
    }
    site = Path(plan["site"])
    source_inputs(Path(plan["repo"]), plan["source_sha"], plan["source_inputs"])
    if digest(Path(plan["descriptor_path"]).read_bytes()) != plan["descriptor_sha256"]:
        raise AdmissionError("descriptor changed before final receipt")
    descriptor = json_data(Path(plan["descriptor_path"]).read_bytes())
    expected_inputs = source_inputs(
        Path(plan["repo"]), plan["source_sha"], _descriptor_inputs(descriptor)
    )
    if expected_inputs != plan["source_inputs"]:
        raise AdmissionError("plan source input closure differs")
    _config(Path(plan["repo"]), descriptor, plan["build_receipt"])
    source_reports = {r["output"]: r for r in descriptor["reports"]}
    source_parents = {r["output"]: r for r in descriptor["parents"]}
    if len(plan["records"]) != len(source_reports) + len(source_parents) or {
        r["path"] for r in plan["records"]
    } != set(source_reports) | set(source_parents):
        raise AdmissionError("plan route ownership differs")
    bundle = bundle_identity(site)[1]
    if (
        final_build_receipt.get("state") != "complete"
        or final_build_receipt.get("bundle_sha256") != bundle
        or final_build_receipt.get("resolved_config_sha256")
        != plan["resolved_config_sha256"]
        or final_build_receipt.get("site_url") != plan["site_url"]
    ):
        raise AdmissionError(
            "completed actual build does not bind final artifact/config"
        )
    if final_build_receipt.get("verification_only") is not True:
        raise AdmissionError(
            "mechanical receipt alone cannot claim production acceptance"
        )
    _config(Path(plan["repo"]), descriptor, final_build_receipt)
    policy_map = {item["path"]: item["policy"] for item in final_policy_records}
    if len(policy_map) != len(final_policy_records) or set(policy_map) != {
        r["path"] for r in plan["records"]
    }:
        raise AdmissionError("final policy route attribution differs")
    records = []
    for record in plan["records"]:
        content = read_owned(site, record["path"]).decode()
        document = Document(content)
        policies = [
            a.get("content")
            for tag, a in document.tags
            if tag == "meta"
            and a.get("http-equiv", "").lower() == "content-security-policy"
        ]
        if policies != [policy_map[record["path"]]]:
            raise AdmissionError("final route CSP attribution differs")
        metas = list(re.finditer(r"<meta\b[^>]*>", content, re.I))
        csp_metas = [m for m in metas if "content-security-policy" in m.group().lower()]
        if (
            len(csp_metas) != 1
            or content[: csp_metas[0].start()].lower().count("<head>") != 1
            or "</head>" in content[: csp_metas[0].start()].lower()
        ):
            raise AdmissionError("final CSP must occupy an early head boundary")
        begin = csp_metas[0].start()
        if begin and content[begin - 1] == "\n":
            begin -= 1
        without_csp = content[:begin] + content[csp_metas[0].end() :]
        if without_csp != record["normalized_html"]:
            raise AdmissionError(
                "final HTML changed outside the planned canonical/CSP transform"
            )
        policy = {}
        for raw in policies[0].split(";"):
            parts = raw.strip().split()
            if parts:
                if parts[0] in policy:
                    raise AdmissionError("duplicate CSP directive")
                policy[parts[0]] = parts[1:]
        capability = record["capability"]
        if record["kind"] == "owned-report":
            owned = source_reports.get(record["path"])
            if owned is None:
                raise AdmissionError("plan route kind differs")
            original = read_owned(Path(plan["repo"]), owned["source"]["path"]).decode()
            source_document = validate_report(original, owned, plan["site_url"])
            source_bodies = executable_scripts(source_document)
            expected_html = original.replace(
                "<head>",
                '<head><link rel="canonical" href="'
                + escape(plan["site_url"] + record["path"], quote=True)
                + '">',
                1,
            )
            expected_html = normalize(
                expected_html, record["path"], plan["site_url"], ownership
            )["normalized_html"]
            if (
                record["normalized_html"] != expected_html
                or capability != _report_capability(owned, source_bodies)
                or record["admitted_scripts"] != [s["body"] for s in source_bodies]
            ):
                raise AdmissionError(
                    "final plan differs from reviewed tracked renderer source"
                )
            expected = {
                "script-src": [
                    "'self'",
                    *["'" + h + "'" for h in capability["script_hashes"]],
                ],
                "script-src-attr": ["'none'"],
                "base-uri": ["'none'"],
                "form-action": ["'none'"],
                "frame-src": ["'none'"],
                "img-src": capability["image_sources"],
                "connect-src": capability["connect_sources"],
                "style-src": capability["style_sources"],
                "worker-src": capability["worker_sources"],
                "object-src": capability["object_sources"],
            }
            for directive, values in expected.items():
                if sorted(policy.get(directive, [])) != sorted(values):
                    raise AdmissionError("final report CSP exceeds reviewed capability")
            if [s["body"] for s in executable_scripts(document)] != record[
                "admitted_scripts"
            ]:
                raise AdmissionError("final report executable body differs")
            if [
                a.get("href")
                for tag, a in document.tags
                if tag == "link" and a.get("rel") == "canonical"
            ] != [record["canonical"]]:
                raise AdmissionError("final canonical differs")
            for resource in record["resources"]:
                if digest(read_owned(site, resource["path"])) != resource["sha256"]:
                    raise AdmissionError("final report resource differs")
        else:
            owned = source_parents.get(record["path"])
            expected_frames = (
                [plan["site_url"] + name for name in owned["reports"]] if owned else []
            )
            if (
                owned is None
                or capability != {"frame_uris": expected_frames}
                or digest(
                    restore(
                        record["normalized_html"],
                        navigation[record["path"]],
                        plan["site_url"],
                        ownership,
                    ).encode()
                )
                != owned["built_html_sha256"]
            ):
                raise AdmissionError("final parent plan ownership differs")
            if policy.get("frame-src") != capability["frame_uris"]:
                raise AdmissionError("final parent frame policy exceeds reviewed URI")
            parent_iframe(
                content, record["path"], capability["frame_uris"], plan["site_url"]
            )
        stripped = copy.deepcopy(record)
        stripped.pop("normalized_html")
        stripped.pop("admitted_scripts")
        stripped["final_html_sha256"] = digest(content.encode())
        stripped["final_policy_sha256"] = digest(policies[0].encode())
        records.append(stripped)
    return {
        "schema": 1,
        "scope": "source-owned-embedded-report-receipt",
        "verification_only": True,
        "bundle_sha256": bundle,
        "descriptor_sha256": plan["descriptor_sha256"],
        "source_sha": plan["source_sha"],
        "source_inputs_sha256": digest(canonical(plan["source_inputs"])),
        "resolved_config_sha256": plan["resolved_config_sha256"],
        "build_receipt_sha256": digest(canonical(final_build_receipt)),
        "records": records,
        "navigation": list(navigation.values()),
        "limitations": plan["limitations"],
    }
