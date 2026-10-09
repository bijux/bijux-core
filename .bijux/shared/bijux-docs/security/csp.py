#!/usr/bin/env python3
"""Apply early static CSP only after admitting every executable inline script."""
from __future__ import annotations

import argparse
import base64
import hashlib
from html import escape
from html.parser import HTMLParser
import importlib.metadata
import importlib.util
import json
from pathlib import Path
from types import ModuleType
import re
import subprocess
import sys
from urllib.parse import urlsplit

MATERIAL_VERSION = "9.7.7"
SCRIPT = re.compile(r"<script(?:\s[^>]*)?>(.*?)</script>", re.DOTALL)
SCOPE = re.compile(r'var __md_scope = new URL\(("(?:[^"\\]|\\.)*"), location\);')


class PolicyError(ValueError):
    """An artifact cannot receive the admitted executable policy."""


def hash_source(source: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(source.encode()).digest()).decode() + "'"


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.inline = []
        self.current = None
        self.existing = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta" and values.get("http-equiv", "").lower() == "content-security-policy":
            self.existing = True
        if tag == "script":
            if len(values) != len(attrs):
                raise PolicyError("Duplicate script attributes are not admitted")
            kind = values.get("type", "").lower()
            if kind not in {"", "text/javascript", "application/javascript", "module", "application/json", "application/ld+json"}:
                raise PolicyError("Unreviewed script type")
            self.current = (values, [])

    def handle_data(self, data):
        if self.current:
            self.current[1].append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.current:
            attrs, body = self.current
            self.current = None
            if not attrs.get("src") and attrs.get("type", "").lower() not in {"application/json", "application/ld+json"}:
                self.inline.append("".join(body))


def admitted_scripts(shared: Path, material_templates: Path) -> tuple[set[str], str]:
    """Trust exact canonical override bytes and static admitted dependency snippets."""
    from jinja2 import Environment
    env = Environment()
    allowed = set()
    base_template = (shared / "partials/javascripts/base.html").read_text()
    rendered = env.from_string(base_template).render(config={"extra": {}}, base_url=".")
    base = SCRIPT.findall(rendered)
    if len(base) != 1 or not SCOPE.search(base[0]):
        raise PolicyError("Canonical preference bootstrap has an unreviewed shape")
    normalized = SCOPE.sub("var __md_scope = BIJUX_REVIEWED_SCOPE;", base[0])
    palette = env.from_string((shared / "partials/javascripts/palette.html").read_text()).render()
    allowed.update(SCRIPT.findall(palette))
    for path in sorted((material_templates / "partials/javascripts").rglob("*.html")):
        for body in SCRIPT.findall(path.read_text()):
            if "{{" not in body and "{%" not in body:
                allowed.add(body)
    return allowed, normalized


def policy_inputs(shared: Path, material_templates: Path) -> dict:
    def records(root: Path, paths: list[Path]) -> list[dict]:
        return [{"path": p.relative_to(root).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in sorted(paths)]
    return {"canonical": records(shared, [shared / "partials/javascripts/base.html", shared / "partials/javascripts/palette.html"]),
            "material_templates": records(material_templates, list((material_templates / "partials/javascripts").rglob("*.html")))}


def embedded_module():
    path = Path(__file__).with_name("embedded_reports").resolve()
    captured = {p.stem: (p, p.read_bytes()) for p in sorted(path.glob("*.py"))}
    if "processor_loading" not in captured:
        raise ValueError("Owned processors require captured loader source")
    source, content = captured["processor_loading"]
    loader = ModuleType("bijux_captured_processor_loading")
    loader.__file__ = str(source)
    exec(compile(content, str(source), "exec"), loader.__dict__)
    return loader.load_processors(path, captured, "bijux_owned_embedded_")


def qualify_html(html: str, allowed: set[str], normalized_base: str, capability: dict | None = None,
                 *, owned_report: bool = False) -> tuple[str, list[str]]:
    parser = Scripts()
    parser.feed(html)
    if parser.existing:
        raise PolicyError("An existing CSP requires explicit owner reconciliation; do not stack policies")
    hashes = set()
    for body in parser.inline:
        accepted = body in allowed
        match = SCOPE.search(body)
        if match:
            scope = json.loads(match[1])
            parsed = urlsplit(scope)
            if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or "\\" in scope:
                raise PolicyError("Preference scope must be a local URL path")
            accepted |= SCOPE.sub("var __md_scope = BIJUX_REVIEWED_SCOPE;", body) == normalized_base
        if not accepted:
            raise PolicyError("Executable inline script lacks exact canonical/dependency admission")
        hashes.add(hash_source(body))
    policy = "; ".join([
        # Firefox applies the default directive to native same-origin next-page prefetch.
        # Explicit fetch directives retain the narrower executable/resource boundaries.
        "default-src 'self'", "base-uri 'self'", "object-src 'none'", "form-action 'self'",
        "script-src 'self' " + " ".join(sorted(hashes)), "script-src-attr 'none'",
        "style-src 'self' 'unsafe-inline'", "font-src 'self'", "connect-src 'self'",
        "worker-src 'self' blob:", "img-src 'self' data: https://img.shields.io https://raw.githubusercontent.com",
        "media-src 'self'", "frame-src 'none'", "manifest-src 'self'",
    ])
    if capability is not None:
        directives = {part.split()[0]: part.split()[1:] for part in policy.split("; ")}
        if owned_report:
            directives.update({"base-uri": ["'none'"], "form-action": ["'none'"],
                               "worker-src": capability["worker_sources"],
                               "connect-src": capability["connect_sources"],
                               "img-src": capability["image_sources"],
                               "style-src": capability["style_sources"],
                               "script-src": [*capability["script_sources"], *sorted(hashes)]})
        if owned_report and capability["script_sources"] == ["'none'"]:
            directives.update({name: ["'none'"] for name in
                               ("default-src", "font-src", "media-src", "manifest-src")})
        directives["frame-src"] = capability["frame_uris"] or ["'none'"]
        policy = "; ".join(name + " " + " ".join(values) for name, values in directives.items())
    charset = re.search(r'<meta\s+charset=["\']?utf-8["\']?\s*/?>', html, flags=re.IGNORECASE)
    if not charset or "<script" in html[:charset.end()].lower():
        raise PolicyError("UTF-8 charset must precede executable scripts")
    meta = '\n<meta http-equiv="Content-Security-Policy" content="' + policy + '">'
    return html[:charset.end()] + meta + html[charset.end():], sorted(hashes)


def apply(site: Path, shared: Path, material_templates: Path, redirect_plan: dict | None = None,
          embedded_plan: dict | None = None) -> dict:
    allowed, base = admitted_scripts(shared, material_templates)
    static_inputs = policy_inputs(shared, material_templates)
    processor_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    # Admit every page before writing any; a late rejection preserves all original bytes.
    writes = []
    redirects = {}
    embedded = {}
    navigation = {}
    admission = None
    initial_bundle = None
    initial_embedded_inputs = None
    if embedded_plan is not None:
        admission = embedded_module()
        try:
            embedded_plan = admission.validate_plan(embedded_plan, site)
        except ValueError as error:
            raise PolicyError(str(error)) from error
        initial_embedded_inputs = admission.inputs(embedded_plan)
        navigation = {entry["path"]: entry for entry in embedded_plan["navigation"]}
        initial_bundle = admission.bundle_identity(site)[1]
        for record in embedded_plan["records"]:
            if record["path"] in embedded:
                raise PolicyError("Duplicate embedded capability route")
            embedded[record["path"]] = record
    if redirect_plan is not None:
        if redirect_plan.get("schema") != 1 or redirect_plan.get("policy") != "exact-declared-redirects" or redirect_plan.get("applied"):
            raise PolicyError("A preflighted, unapplied declared redirect plan is required")
        redirect_spec = importlib.util.spec_from_file_location("bijux_csp_plan_identity", Path(__file__).with_name("redirects.py"))
        normalizer = importlib.util.module_from_spec(redirect_spec)
        redirect_spec.loader.exec_module(normalizer)
        if redirect_plan["policy_inputs"]["processor_sha256"] != hashlib.sha256(Path(normalizer.__file__).read_bytes()).hexdigest():
            raise PolicyError("Redirect plan processor differs from canonical source")
        for record in redirect_plan["records"]:
            name = record["path"]
            if name in embedded:
                raise PolicyError("Redirect and embedded routes must have distinct owners")
            if name in redirects or not name.endswith(".html") or Path(name).is_absolute() or any(part in {".", ".."} for part in name.split("/")):
                raise PolicyError("Redirect route is duplicate or outside the selected artifact")
            expected_script = normalizer.SCRIPT.format(target=json.dumps(record["target"], ensure_ascii=True))
            expected_html = normalizer.TEMPLATE.format(canonical=escape(record["canonical"], quote=True), target=escape(record["target"], quote=True), script=expected_script)
            if record["script"] != expected_script or record["normalized_html"] != expected_html:
                raise PolicyError("Redirect plan differs from the canonical route template")
            if hashlib.sha256(record["normalized_html"].encode()).hexdigest() != record["normalized_sha256"] or hashlib.sha256(record["script"].encode()).hexdigest() != record["script_sha256"] or hash_source(record["script"]) != record["csp_hash"]:
                raise PolicyError("Redirect plan content differs from its admitted digests")
            redirects[name] = record
    observed_redirects = set()
    observed_embedded = set()
    publication_spec = importlib.util.spec_from_file_location("bijux_csp_html_boundary", Path(__file__).with_name("publication.py"))
    boundary = importlib.util.module_from_spec(publication_spec)
    publication_spec.loader.exec_module(boundary)
    for path in sorted(site.rglob("*.html")):
        if path.is_symlink():
            raise PolicyError("Symlink HTML is not admitted")
        original_bytes = path.read_bytes()
        original = original_bytes.decode("utf-8")
        name = path.relative_to(site).as_posix()
        record = redirects.get(name)
        owned = embedded.get(name)
        page_allowed = allowed
        if record:
            if hashlib.sha256(original_bytes).hexdigest() != record["input_sha256"]:
                raise PolicyError("Declared redirect changed after source preflight")
            original = record["normalized_html"]
            page_allowed = allowed | {record["script"]}
            observed_redirects.add(name)
        if owned:
            if hashlib.sha256(original_bytes).hexdigest() != owned["input_sha256"]:
                raise PolicyError("Embedded HTML changed after source preflight")
            original = owned["normalized_html"]
            if owned["kind"] == "owned-report":
                page_allowed = set(owned["admitted_scripts"])
            observed_embedded.add(name)
        if name in navigation:
            original = navigation[name]["normalized_html"]
        inspected = boundary.DocumentPolicy(owned_report=bool(owned and owned["kind"] == "owned-report"),
                                            owned_parent=bool(owned and owned["kind"] == "owned-parent-frame"))
        inspected.feed(original)
        if inspected.failures:
            raise PolicyError("Public HTML boundary rejects: " + ", ".join(sorted(set(inspected.failures))))
        updated, hashes = qualify_html(original, page_allowed, base,
                                       owned["capability"] if owned else None,
                                       owned_report=bool(owned and owned["kind"] == "owned-report"))
        writes.append((path, updated, hashes, original_bytes))
    if not writes:
        raise PolicyError("The selected artifact contains no HTML")
    if observed_redirects != set(redirects):
        raise PolicyError("Declared redirect is missing from the selected HTML artifact")
    if observed_embedded != set(embedded):
        raise PolicyError("Owned embedded route is missing from selected artifact")
    if any(path.read_bytes() != original for path, _, _, original in writes):
        raise PolicyError("Selected HTML changed during executable preflight")
    if admission is not None:
        if admission.bundle_identity(site)[1] != initial_bundle:
            raise PolicyError("Public resources changed during complete executable preflight")
        admission.validate_plan(embedded_plan, site)
        if admission.inputs(embedded_plan) != initial_embedded_inputs:
            raise PolicyError("Embedded processor/source/config inputs changed during preflight")
    if policy_inputs(shared, material_templates) != static_inputs or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != processor_sha256:
        raise PolicyError("Canonical/dependency executable policy inputs changed during preflight")
    additional_writes = []
    if admission is not None:
        from importlib import import_module
        additional_writes = import_module(admission.__package__ + ".reader").sitemap_writes(embedded_plan, site)
    for path, updated, _, _ in writes:
        path.write_text(updated)
    for path, content in additional_writes:
        path.write_bytes(content)
    report = {"schema": 1, "material": MATERIAL_VERSION, "pages": len(writes),
            "processor_sha256": processor_sha256, "policy_inputs": static_inputs,
            "policy": "early-meta-hashes", "script_hashes": sorted({h for _, _, hs, _ in writes for h in hs}),
            "limitations": ["Meta CSP cannot set frame-ancestors, HSTS or nosniff; hosting controls remain separate.",
                           "Inline styles remain required by admitted Material and diagram output; no unsafe-eval or inline handlers admitted."]}
    if redirect_plan is not None:
        report["redirects"] = {key: value for key, value in redirect_plan.items() if key not in {"records", "policy_inputs", "applied"}}
        report["redirects"]["applied"] = True
        report["redirects"]["records"] = [{key: value for key, value in record.items() if key not in {"normalized_html", "script"}} for record in redirect_plan["records"]]
    if admission is not None:
        report["embedded"] = admission.report(embedded_plan)
        report["policy_inputs"]["embedded"] = initial_embedded_inputs
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("mkdocs.yml"))
    parser.add_argument("--site-url")
    parser.add_argument("--embedded-owner", type=Path)
    parser.add_argument("--build-identity", type=Path)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    site, output = args.site_dir.resolve(), args.output.resolve()
    try:
        if not site.is_relative_to(root / "artifacts") or not output.is_relative_to(root / "artifacts") or output.is_relative_to(site):
            raise PolicyError("Select root artifacts/ output and an external report")
        if importlib.metadata.version("mkdocs-material") != MATERIAL_VERSION:
            raise PolicyError("Material version differs from the admitted policy toolchain")
        import material
        from mkdocs.config import load_config
        config = load_config(config_file=str(args.config), site_dir=str(site))
        site_url = config["site_url"]
        if args.site_url and args.site_url != site_url:
            raise PolicyError("Actual MkDocs configuration selects another production URL")
        spec = importlib.util.spec_from_file_location("bijux_csp_publication", Path(__file__).with_name("publication.py"))
        publication = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publication)
        publication.validate_url(site_url)
        shared = Path(__file__).resolve().parents[1]
        templates = Path(material.__file__).parent / "templates"
        inputs = policy_inputs(shared, templates)
        publication.public_bundle_identity(site)
        redirect_spec = importlib.util.spec_from_file_location("bijux_csp_redirects", Path(__file__).with_name("redirects.py"))
        redirects = importlib.util.module_from_spec(redirect_spec)
        redirect_spec.loader.exec_module(redirects)
        redirect_plan = redirects.normalize_redirects(config, site, site_url, write=False)
        embedded_plan = None
        if args.embedded_owner:
            if args.build_identity is None:
                raise PolicyError("An actual prepared builder receipt is required for embedded reports")
            build = json.loads(args.build_identity.read_text())
            if build.get("state") != "prepared" or build.get("scope") != "actual-mkdocs-renderer":
                raise PolicyError("Embedded CLI requires actual prepared renderer evidence")
            identity = publication.identity_module()
            checkpoint = build.get("source_checkpoint")
            if build.get("verification_only") is False:
                identity.verify_source(root, checkpoint)
                owner = args.embedded_owner.resolve()
                if not owner.is_relative_to(root):
                    raise PolicyError("Accepted embedded descriptor must belong to the selected source repository")
                identity.git(root, "ls-files", "--error-unmatch", owner.relative_to(root).as_posix())
                source_sha = checkpoint["repository_source"]["sha"]
            else:
                source_sha = identity.git(root, "rev-parse", "HEAD")
            # Source authority is independent from mechanical plan validation.
            # Keep the captured renderer/checkpoint unchanged; only the pure
            # planner view is candidate-scoped, and publication verifies authority.
            candidate_view = build | {"verification_only": True}
            embedded_plan = embedded_module().plan_embedded_reports(root, site, args.embedded_owner, candidate_view, source_sha=source_sha)
        report = apply(site, shared, templates, redirect_plan, embedded_plan)
        inputs.update(report.get("policy_inputs", {}))
        inputs["redirects"] = redirect_plan["policy_inputs"]
        if {key: value for key, value in inputs.items() if key not in {"redirects", "embedded"}} != policy_inputs(shared, templates):
            raise PolicyError("Policy inputs changed during artifact transformation")
        _, bundle_sha256 = publication.public_bundle_identity(site)
        report.update({"site_url": site_url, "site_dir": site.relative_to(root).as_posix(),
                       "bundle_sha256": bundle_sha256, "policy_inputs": inputs,
                       "processor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
    except (OSError, ValueError, importlib.metadata.PackageNotFoundError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(f"Applied early admitted CSP to {report['pages']} pages; {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
