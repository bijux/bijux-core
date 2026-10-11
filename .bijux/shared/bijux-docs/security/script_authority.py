"""Reconstruct ordinary inline executable authority from reviewed source bytes."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from types import ModuleType


class AuthorityError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuthorityError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(root: Path, name: str) -> Path:
    path = root
    for part in Path(name).parts:
        require(part not in {"", ".", ".."}, "Script authority: ambiguous source path")
        path /= part
        require(not path.is_symlink(), "Script authority: source symlink")
    require(path.is_file(), "Script authority: missing reviewed source")
    return path


def source_bytes(shared):
    names = ["security/script_authority.py", "security/csp.py", "security/policy.json",
             "security/material-script-admission.json", "partials/javascripts/base.html",
             "partials/javascripts/palette.html"]
    return {name: regular(shared, name).read_bytes() for name in names}


def reconstruction(shared: Path, renderer: dict, csp_report: dict):
    source = source_bytes(shared)
    policy = ModuleType("bijux_source_script_policy")
    policy.__file__ = str(shared / "security/csp.py")
    # Execute captured trusted processor bytes, not a receipt-supplied path or
    # a file reopened after its fingerprint was captured.
    exec(compile(source["security/csp.py"], policy.__file__, "exec"), policy.__dict__)
    require(csp_report.get("processor_sha256") == digest(source["security/csp.py"]),
            "Script authority: processor differs from reviewed source")
    admission = json.loads(source["security/material-script-admission.json"])
    require(admission.get("schema") == 1 and admission.get("distribution") == "mkdocs-material"
            and admission.get("version") == policy.MATERIAL_VERSION == renderer.get("packages", {}).get("mkdocs-material"),
            "Script authority: actual renderer differs from dependency admission")
    templates = admission.get("templates")
    require(isinstance(templates, list) and 0 < len(templates) <= 64,
            "Script authority: bounded reviewed dependency templates required")
    seen = set()
    allowed = set()
    expected = []
    for record in templates:
        name = record.get("path")
        require(isinstance(name, str) and re.fullmatch(r"partials/javascripts/[A-Za-z0-9_/-]+\.html", name)
                and ".." not in name.split("/") and name not in seen
                and re.fullmatch(r"[a-f0-9]{64}", record.get("sha256", "")),
                "Script authority: invalid reviewed dependency input")
        seen.add(name)
        bodies = record.get("static_script_bodies")
        require(isinstance(bodies, list) and all(isinstance(body, str) and "{{" not in body and "{%" not in body for body in bodies),
                "Script authority: dynamic dependency body lacks source-derived admission")
        allowed.update(bodies)
        expected.append({"path": name, "sha256": record["sha256"]})
    expected.sort(key=lambda record: record["path"])
    require(renderer.get("material_templates") == expected
            and csp_report.get("policy_inputs", {}).get("material_templates") == expected,
            "Script authority: actual dependency fingerprint differs from canonical admission")
    canonical = [{"path": name, "sha256": digest(source[name])}
                 for name in ("partials/javascripts/base.html", "partials/javascripts/palette.html")]
    require(csp_report.get("policy_inputs", {}).get("canonical") == canonical,
            "Script authority: canonical template fingerprint differs")
    token = "{{ (config.extra.scope | d(base_url)) | tojson }}"
    bases = policy.SCRIPT.findall(source["partials/javascripts/base.html"].decode())
    require(len(bases) == 1 and bases[0].count(token) == 1,
            "Script authority: canonical preference template shape requires review")
    scope = "var __md_scope = new URL(" + token + ", location);"
    require(bases[0].count(scope) == 1,
            "Script authority: canonical preference scope shape requires review")
    normalized = bases[0].replace(scope, "var __md_scope = BIJUX_REVIEWED_SCOPE;")
    require("{{" not in normalized and "{%" not in normalized,
            "Script authority: unreviewed preference template expression")
    palette = policy.SCRIPT.findall(source["partials/javascripts/palette.html"].decode())
    require(palette and all("{{" not in body and "{%" not in body for body in palette),
            "Script authority: canonical palette requires static source admission")
    allowed.update(palette)
    return source, policy, allowed, normalized


class InlineAttributes(HTMLParser):
    """Keep executable interpretation aligned with the reviewed classic snippets."""
    def handle_starttag(self, tag, attrs):
        if tag != "script":
            return
        values = dict(attrs)
        require(len(values) == len(attrs), "Script authority: duplicate script attributes")
        if values.get("src") or values.get("type", "").lower() in {"application/json", "application/ld+json"}:
            return
        require(set(values) <= {"type"} and values.get("type", "").lower() in {"", "text/javascript", "application/javascript"},
                "Script authority: executable attributes differ from reviewed classic snippets")


def verify_ordinary(site: Path, shared: Path, renderer: dict, csp_report: dict, redirect_hashes: dict | None = None, *, verified_readers=None) -> dict:
    """Redirect exclusions must come from independent declared-template verification."""
    redirect_hashes = redirect_hashes or {}
    source, policy, allowed, normalized = reconstruction(shared, renderer, csp_report)
    capabilities, reports = {}, set()
    interactive_reports = None
    if verified_readers is not None:
        import importlib
        adapter = importlib.import_module(policy.embedded_module().__package__ + '.rendering')
        interactive = importlib.import_module(policy.embedded_module().__package__ + '.interactive_rendering')
        require(type(verified_readers) in {adapter.VerifiedReaders, interactive.VerifiedInteractiveReports}, 'Script authority: reports require an independently rederived in-process scope')
        if type(verified_readers) is interactive.VerifiedInteractiveReports:
            interactive_reports = verified_readers
        verified_readers.unchanged(site, csp_report)
        capabilities, reports = verified_readers.capabilities, verified_readers.reports
    originals = {page.relative_to(site).as_posix(): page.read_bytes() for page in sorted(site.rglob("*.html"))}
    require(originals, "Script authority: no HTML")
    require(set(redirect_hashes) <= set(originals), "Script authority: undeclared redirect exclusion")
    report = []
    used = set(redirect_hashes.values())
    for name, data in originals.items():
        if name in reports and (interactive_reports is None or interactive_reports.classes[name] == 'static-reader'):
            report.append({"path": name, "class": "source-owned-static-reader", "inline_hashes": []})
            continue
        if name in redirect_hashes:
            continue
        content = data.decode()
        policies = []
        class Meta(HTMLParser):
            def handle_starttag(self, tag, attrs):
                values = dict(attrs)
                require(len(values) == len(attrs), "Script authority: duplicate HTML attributes")
                if tag == "meta" and values.get("http-equiv", "").lower() == "content-security-policy":
                    policies.append(values.get("content", ""))
        Meta(convert_charrefs=True).feed(content)
        require(len(policies) == 1, "Script authority: one actual CSP required")
        insertion = '\n<meta http-equiv="Content-Security-Policy" content="' + policies[0] + '">'
        require(content.count(insertion) == 1, "Script authority: exact policy insertion required")
        raw = content.replace(insertion, "", 1)
        InlineAttributes().feed(raw)
        scripts = policy.Scripts()
        scripts.feed(raw)
        require(scripts.current is None, "Script authority: unterminated script")
        owned_interactive = interactive_reports is not None and name in reports
        page_allowed = set(interactive_reports.bodies[name]) if owned_interactive else allowed
        rebuilt, hashes = policy.qualify_html(raw, page_allowed, normalized, capabilities.get(name), owned_report=owned_interactive)
        require(rebuilt == content, "Script authority: final policy differs from independently admitted script bodies")
        used.update(hashes)
        page = {"path": name, "inline_hashes": hashes}
        if owned_interactive:
            page['class'] = 'source-owned-interactive-report'
        report.append(page)
    require(sorted(used) == csp_report.get("script_hashes"),
            "Script authority: receipt hashes differ from independently reconstructed bodies")
    require(source == source_bytes(shared), "Script authority: policy/source fingerprint changed during reconstruction")
    require(originals == {page.relative_to(site).as_posix(): page.read_bytes() for page in sorted(site.rglob("*.html"))},
            "Script authority: final HTML changed during reconstruction")
    return {"schema": 1, "scope": "ordinary-source-derived-inline-executables",
            "sources": [{"path": name, "sha256": digest(data)} for name, data in sorted(source.items())],
            "material": policy.MATERIAL_VERSION, "pages": report,
            "redirect_exclusions": sorted(redirect_hashes), "script_hashes": sorted(used),
            "limitations": ["Same-origin external executable asset provenance remains a separate producer/source mapping obligation.",
                            "Source-owned embedded report classes require independent typed adapters, not ordinary receipt exceptions."]}
