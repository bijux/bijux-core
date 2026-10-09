#!/usr/bin/env python3
"""Admit one public documentation bundle and verify its retained identity."""
from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
from html.parser import HTMLParser
from html import escape
import json
import importlib.util
from pathlib import Path
import re
import sys
from urllib.parse import quote, unquote, urlsplit
from xml.etree import ElementTree

sys.dont_write_bytecode = True

POLICY = Path(__file__).with_name("policy.json")
SHA = re.compile(r"^[0-9a-f]{40}$")
VERSION_REF = re.compile(r"^refs/tags/v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
PRIVATE_MARKERS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b"),
    re.compile(rb"\bAKIA[A-Z0-9]{16}\b"),
)


class AdmissionError(ValueError):
    """A publication input is outside the admitted static website contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionError(message)


def single_line(value: str, name: str) -> str:
    require(not any(ord(c) < 32 or ord(c) == 127 for c in value), f"{name}: control characters forbidden")
    return value


def validate_url(url: str, expected: str | None = None) -> str:
    single_line(url, "site URL")
    parsed = urlsplit(url)
    require(parsed.scheme == "https" and bool(parsed.hostname), "site URL: absolute HTTPS required")
    require(parsed.username is None and parsed.password is None and parsed.port is None,
            "site URL: credentials and explicit ports forbidden")
    require(not parsed.query and not parsed.fragment, "site URL: query and fragment forbidden")
    require(url.endswith("/") and not re.search(r"[%\\\s]", url), "site URL: plain trailing-slash URL required")
    require(not any(part in {".", ".."} for part in parsed.path.split("/")), "site URL: dot segments forbidden")
    if expected:
        require(url == expected, "site URL: does not match repository production identity")
    return url


def site_directory(repo_root: Path, value: str, *, exists: bool = False) -> Path:
    single_line(value, "site directory")
    require(bool(re.fullmatch(r"artifacts/[A-Za-z0-9._/-]+", value)),
            "site directory: relative artifacts/ descendant required")
    parts = Path(value).parts
    require(all(p not in {".", ".."} for p in parts) and "//" not in value,
            "site directory: normalized path required")
    root = repo_root.resolve()
    current = root
    for part in parts:
        current /= part
        require(not current.is_symlink(), "site directory: symlink path forbidden")
    candidate = current.resolve()
    require(candidate.is_relative_to(root / "artifacts") and candidate != root / "artifacts",
            "site directory: escapes artifact boundary")
    if exists:
        require(candidate.is_dir() and (candidate / "index.html").is_file(),
                "site directory: exact configured output with index.html required")
    return candidate


def validate_config(*, repository: str, event: str, ref: str, default_branch: str,
                    site_url: str, site_dir: str, verify_command: str, repo_root: Path) -> dict:
    for name, value in (("repository", repository), ("event", event), ("ref", ref),
                        ("default branch", default_branch), ("verify command", verify_command)):
        single_line(value, name)
    require(bool(re.fullmatch(r"bijux/[A-Za-z0-9._-]+", repository)), "repository: Bijux owner/name required")
    require(event in {"push", "release", "workflow_dispatch", "workflow_call"},
            "publication event: untrusted or unsupported trigger")
    require(bool(default_branch), "default branch: required")
    require(ref == f"refs/heads/{default_branch}" or bool(VERSION_REF.fullmatch(ref)),
            "publication ref: default branch or version tag required")
    name = repository.split("/", 1)[1]
    expected = "https://bijux.io/" if name == "bijux.github.io" else f"https://bijux.io/{name}/"
    validate_url(site_url, expected)
    site_directory(repo_root, site_dir)
    require(bool(verify_command.strip()), "verification command: required before publication")
    return {"site_url": site_url, "site_dir": site_dir, "repository": repository,
            "ref": ref, "event": event, "default_branch": default_branch}


class DocumentPolicy(HTMLParser):
    """Inspect executable/URL attributes without treating code text as HTML."""

    def __init__(self, *, owned_report: bool = False, owned_parent: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.failures: list[str] = []
        self.canonicals: list[str] = []
        self.csp: list[str] = []
        self.head_open = False
        self.active_seen = False
        self.csp_early = False
        self.owned_report = owned_report
        self.owned_parent = owned_parent

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if len(values) != len(attrs):
            self.failures.append("duplicate HTML attributes")
        if tag == "head":
            self.head_open = True
        if tag == "iframe" and not self.owned_parent:
            self.failures.append("iframe requires an exact source-owned parent capability")
        if tag in {"script", "style", "img", "iframe", "object", "embed", "source", "video", "audio"} or (
                tag == "link" and set((values.get("rel") or "").split()) & {
                    "stylesheet", "preload", "modulepreload", "prefetch", "preconnect", "dns-prefetch", "icon"}) or (
                tag == "base" or tag == "meta" and (values.get("http-equiv") or "").lower() == "refresh"):
            self.active_seen = True
        for name, value in attrs:
            if value is None:
                continue
            if name.startswith("on"):
                self.failures.append("inline event handler")
            if name in {"href", "src", "action", "formaction", "xlink:href"}:
                normalized = re.sub(r"[\x00-\x20\x7f]", "", unquote(value)).lower()
                scheme = urlsplit(normalized).scheme
                if scheme in {"javascript", "vbscript"}:
                    self.failures.append("executable URL scheme")
                empty_owned_icon = self.owned_report and tag == "link" and values.get("rel") == "icon" and value == "data:,"
                if scheme == "data" and tag not in {"img", "source"} and not empty_owned_icon:
                    self.failures.append("unadmitted data URL")
                if normalized.startswith("http://") and tag in {"script", "img", "iframe", "link", "source", "video", "audio"}:
                    self.failures.append("insecure active resource")
        if tag == "link" and "canonical" in (values.get("rel") or "").split():
            self.canonicals.append(values.get("href") or "")
        if tag == "meta" and (values.get("http-equiv") or "").lower() == "content-security-policy":
            self.csp.append(values.get("content") or "")
            self.csp_early = self.head_open and not self.active_seen

    def handle_endtag(self, tag: str) -> None:
        if tag == "head":
            self.head_open = False


def load_policy(path: Path = POLICY) -> dict:
    policy = json.loads(path.read_text(encoding="utf-8"))
    require(policy.get("schema") == 1, "publication policy: unsupported schema")
    require(isinstance(policy.get("allowed_extensions"), list), "publication policy: extensions required")
    for exception in policy.get("public_exceptions", []):
        require(isinstance(exception.get("pattern"), str) and bool(exception.get("purpose")),
                "publication exception: pattern and public purpose required")
        pattern = exception["pattern"]
        require(not pattern.startswith("/") and ".." not in Path(pattern).parts,
                "publication exception: confined path pattern required")
    return policy


def public_bundle_identity(site: Path) -> tuple[list[dict], str]:
    """Hash regular public files identically for admission and scoped verification."""
    require(site.is_dir(), "public bundle: selected directory is missing")
    files = []
    for path in sorted(site.rglob("*")):
        require(not path.is_symlink(), "public bundle: symlink identity is forbidden")
        if path.is_dir():
            continue
        require(path.is_file(), "public bundle: nonregular file identity is forbidden")
        relative = path.relative_to(site).as_posix()
        single_line(relative, "public path")
        content = path.read_bytes()
        files.append({"path": relative, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return files, digest


def static_svg(content: bytes, maximum_bytes: int) -> None:
    """Admit a vector image that stays passive when opened as a document."""
    require(len(content) <= maximum_bytes, "SVG size budget")
    try:
        source = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AdmissionError("SVG UTF-8 encoding required") from None
    require("\x00" not in source, "SVG UTF-8 encoding required")
    require(not re.search(r"<!ENTITY|<\?xml-stylesheet\b", source, re.IGNORECASE), "SVG entity or stylesheet declaration")
    try:
        root = ElementTree.fromstring(source)
    except ElementTree.ParseError:
        raise AdmissionError("invalid SVG XML") from None
    local = lambda name: name.rsplit("}", 1)[-1].lower()
    require(local(root.tag) == "svg", "invalid SVG root")
    denied = {"script", "foreignobject", "iframe", "object", "embed", "html", "body", "canvas",
              "audio", "video", "link", "animate", "animatemotion", "animatetransform", "set", "discard"}
    passive_metadata = {
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#": {"rdf", "description", "seq", "bag", "alt", "li", "type", "value"},
        "http://purl.org/dc/elements/1.1/": {"title", "creator", "date", "description", "format", "identifier",
                                             "source", "rights", "subject", "publisher", "contributor", "language",
                                             "type", "relation", "coverage"},
        "http://creativecommons.org/ns#": {"work", "agent", "license", "permits", "requires", "prohibits", "attributionname",
                                            "attributionurl", "morepermissions", "jurisdiction", "deprecatedon", "legalcode"},
        "http://www.inkscape.org/namespaces/inkscape": {"clipboard"},
    }
    metadata_nodes = {child for element in root.iter()
                      if element.tag in {"metadata", "{http://www.w3.org/2000/svg}metadata"}
                      for child in element.iter()}

    def css(value: str) -> None:
        value = re.sub(r"\\\r?\n", "", value)
        value = re.sub(r"\\([0-9a-fA-F]{1,6})\s?|\\(.)",
                       lambda match: chr(min(int(match[1], 16), 0x10ffff)) if match[1] else match[2], value)
        value = re.sub(r"/\*.*?\*/", "", value, flags=re.DOTALL)
        require(not re.search(r"@import\b", value, re.IGNORECASE), "SVG external stylesheet")
        for match in re.finditer(r"url\s*\((.*?)\)", value, re.IGNORECASE | re.DOTALL):
            target = match[1].strip().strip("'\"")
            require(bool(re.fullmatch(r"#[A-Za-z0-9_.:-]+", target)), "SVG external CSS resource")

    for element in root.iter():
        tag = local(element.tag)
        namespace = element.tag[1:].split("}", 1)[0] if element.tag.startswith("{") else ""
        require(namespace in {"", "http://www.w3.org/2000/svg"}
                or element in metadata_nodes and tag in passive_metadata.get(namespace, set()),
                "SVG foreign document namespace")
        require(tag not in denied, "SVG active document content")
        if tag == "style":
            css("".join(element.itertext()))
        for key, value in element.attrib.items():
            attribute = local(key)
            require(not attribute.startswith("on") and attribute != "srcdoc", "SVG executable attribute")
            require(attribute != "base", "SVG resource base override")
            css(value)
            if attribute not in {"href", "src"}:
                continue
            normalized = re.sub(r"[\x00-\x20\x7f]", "", unquote(value))
            require("\\" not in normalized, "SVG ambiguous resource URL")
            parsed = urlsplit(normalized)
            require(parsed.scheme.lower() not in {"javascript", "vbscript"}, "SVG executable URL")
            if tag == "a":
                require(parsed.scheme.lower() in {"", "https"} and not (parsed.netloc and not parsed.scheme), "SVG unsafe navigation URL")
            elif parsed.scheme.lower() == "data":
                match = re.fullmatch(r"data:image/(png|jpeg|gif|webp);base64,(.*)", normalized, re.IGNORECASE)
                require(tag in {"image", "feimage"} and match is not None, "SVG unadmitted embedded resource")
                try:
                    data = base64.b64decode(match[2], validate=True)
                except ValueError:
                    raise AdmissionError("SVG invalid raster data") from None
                signatures = {"png": data.startswith(b"\x89PNG\r\n\x1a\n"), "jpeg": data.startswith(b"\xff\xd8\xff"),
                              "gif": data.startswith((b"GIF87a", b"GIF89a")),
                              "webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP"}
                require(signatures[match[1].lower()], "SVG mismatched raster data")
            else:
                require(not parsed.scheme and not parsed.netloc, "SVG external resource")


def bundle_manifest(repo_root: Path, site_dir: str, site_url: str, source_sha: str,
                    policy: dict, standard_sha: str | None = None, *, embedded_report_routes: set[str] | None = None,
                    embedded_parent_routes: set[str] | None = None) -> dict:
    validate_url(site_url)
    require(bool(SHA.fullmatch(source_sha)), "source identity: full lowercase commit SHA required")
    if standard_sha is not None:
        require(bool(SHA.fullmatch(standard_sha)), "standard identity: full lowercase SHA required")
    site = site_directory(repo_root, site_dir, exists=True)
    files: list[dict] = []
    failures: list[dict] = []
    for path in sorted(site.rglob("*")):
        relative = path.relative_to(site).as_posix()
        single_line(relative, "public path")
        if path.is_symlink():
            failures.append({"path": relative, "code": "symlink"})
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            failures.append({"path": relative, "code": "nonregular-file"})
            continue
        denied = any(part.startswith(".") or part in policy["forbidden_names"] for part in path.relative_to(site).parts)
        exception = any(fnmatch.fnmatchcase(relative, item["pattern"]) for item in policy.get("public_exceptions", []))
        # Exceptions admit public downloads/maps, never private dotfiles, keys or secrets.
        if denied or path.name.startswith("id_rsa") or path.name.startswith("id_ed25519"):
            failures.append({"path": relative, "code": "private-file"})
        elif (path.suffix.lower() not in policy["allowed_extensions"] or path.suffix.lower() == ".map") and not exception:
            failures.append({"path": relative, "code": "unadmitted-extension"})
        content = path.read_bytes()
        if any(marker.search(content) for marker in PRIVATE_MARKERS):
            failures.append({"path": relative, "code": "private-material"})
        if path.suffix.lower() == ".html":
            try:
                parser = DocumentPolicy(owned_report=relative in (embedded_report_routes or set()), owned_parent=relative in (embedded_parent_routes or set()))
                parser.feed(content.decode("utf-8"))
                for failure in sorted(set(parser.failures)):
                    failures.append({"path": relative, "code": failure})
                if path.name != "404.html":
                    if len(parser.canonicals) != 1 or not parser.canonicals[0].startswith(site_url):
                        failures.append({"path": relative, "code": "production-canonical"})
                    elif urlsplit(parser.canonicals[0]).query or urlsplit(parser.canonicals[0]).fragment:
                        failures.append({"path": relative, "code": "production-canonical"})
            except (UnicodeError, ValueError):
                failures.append({"path": relative, "code": "invalid-html-encoding"})
        elif path.suffix.lower() == ".svg":
            try:
                static_svg(content, policy["maximum_svg_bytes"])
            except (AdmissionError, UnicodeError, ValueError):
                failures.append({"path": relative, "code": "unadmitted-svg-content"})
        files.append({"path": relative, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    if failures:
        # Only paths and classifications are emitted; never print matching private bytes.
        raise AdmissionError(json.dumps({"publication_rejected": failures}, sort_keys=True))
    require(bool(files), "public bundle: no files")
    total = sum(f["bytes"] for f in files)
    require(total <= policy["maximum_bytes"], "public bundle: exceeds admitted size budget")
    require(len(files) <= policy["maximum_files"], "public bundle: exceeds admitted file budget")
    identity_files, identity = public_bundle_identity(site)
    require(identity_files == files, "public bundle: changed during admission")
    return {"schema": 1, "repository_source_sha": source_sha, "standard_sha": standard_sha,
            "site_url": site_url, "site_dir": site_dir, "bundle_sha256": identity,
            "bytes": total, "file_count": len(files), "files": files,
            "policy_sha256": hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()}


def identity_module():
    spec = importlib.util.spec_from_file_location("bijux_docs_build_identity", Path(__file__).with_name("build_identity.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def applied_csp(policy: str, admitted_hashes: set[str], capability: dict | None = None) -> set[str]:
    expected = {"default-src": ["'self'"], "base-uri": ["'self'"], "object-src": ["'none'"],
                "form-action": ["'self'"], "script-src-attr": ["'none'"],
                "style-src": ["'self'", "'unsafe-inline'"], "font-src": ["'self'"],
                "connect-src": ["'self'"], "worker-src": ["'self'", "blob:"],
                "img-src": ["'self'", "data:", "https://img.shields.io", "https://raw.githubusercontent.com"],
                "media-src": ["'self'"], "frame-src": ["'none'"], "manifest-src": ["'self'"]}
    if capability is not None:
        expected["frame-src"] = capability["frame_uris"] or ["'none'"]
        if "script_hashes" in capability:
            expected.update({"base-uri": ["'none'"], "form-action": ["'none'"],
                             "worker-src": capability["worker_sources"],
                             "connect-src": capability["connect_sources"],
                             "img-src": capability["image_sources"],
                             "style-src": capability["style_sources"]})
    if capability is not None and capability.get("script_sources") == ["'none'"]:
        expected.update({name: ["'none'"] for name in
                         ("default-src", "font-src", "media-src", "manifest-src")})
    directives = {}
    for section in policy.split(";"):
        tokens = section.strip().split()
        if not tokens:
            continue
        require(tokens[0] not in directives, "CSP receipt: duplicate directive")
        directives[tokens[0]] = tokens[1:]
    script = directives.pop("script-src", [])
    require(directives == expected, "CSP receipt: policy differs from admitted static capabilities")
    if capability is not None and capability.get("script_sources") == ["'none'"]:
        require(script == ["'none'"] and capability.get("script_hashes") == [],
                "CSP receipt: non-executable reader gained script authority")
        return set()
    require(script and script[0] == "'self'", "CSP receipt: script policy missing")
    hashes = set(script[1:])
    require(all(re.fullmatch(r"'sha256-[A-Za-z0-9+/]{43}='", value) and value in admitted_hashes for value in hashes),
            "CSP receipt: unadmitted executable hash or source")
    return hashes


def embedded_module():
    import sys
    name = "bijux_publication_embedded"
    path = Path(__file__).with_name("embedded_reports")
    spec = importlib.util.spec_from_file_location(name, path / "__init__.py", submodule_search_locations=[str(path)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return importlib.import_module(name + ".integration")


def verify_embedded_candidate(repo_root: Path, site_dir: str, site_url: str, source_sha: str,
                              policy: dict, csp: dict, completed_build: dict, *, canonical_root: Path | None = None) -> dict:
    """Exercise source-owned local composition without claiming accepted publication."""
    site = site_directory(repo_root, site_dir, exists=True)
    admitted = embedded_module().verify_composition(site, csp, completed_build)
    result = bundle_manifest(repo_root, site_dir, site_url, source_sha, policy,
                             embedded_report_routes=admitted["report_routes"],
                             embedded_parent_routes=set(admitted["capabilities"]) - admitted["report_routes"])
    require(csp.get("pages") == sum(e["path"].endswith(".html") for e in result["files"]),
            "Candidate CSP: incomplete HTML coverage")
    owned_hashes = {"'" + h + "'" for cap in admitted["capabilities"].values() for h in cap.get("script_hashes", [])}
    used = set()
    executable = executable_admission(canonical_root or Path(__file__).resolve().parents[1], csp)
    for item in result["files"]:
        if not item["path"].endswith(".html"):
            continue
        parsed = DocumentPolicy(owned_report=item["path"] in admitted["report_routes"], owned_parent=item["path"] in admitted["capabilities"] and item["path"] not in admitted["report_routes"])
        parsed.feed((site / item["path"]).read_text())
        require(len(parsed.csp) == 1 and parsed.csp_early, "Candidate CSP: missing or late policy")
        capability = admitted["capabilities"].get(item["path"])
        executable((site / item["path"]).read_text(), item["path"], capability, csp)
        hashes = applied_csp(parsed.csp[0], set(csp.get("script_hashes", [])), capability)
        require(hashes.intersection(owned_hashes) == ({"'" + h + "'" for h in capability.get("script_hashes", [])} if capability else set()),
                "Candidate CSP: report script hash is admitted on another route")
        used.update(hashes)
    require(used == set(csp.get("script_hashes", [])), "Candidate CSP: script coverage differs")
    return result | {"verification_only": True, "scope": "source-owned local embedded composition; no publication acceptance", "embedded": admitted["receipt"]}


def executable_admission(canonical: Path, csp: dict):
    """Recompute exact source-derived executable admission, independent of receipt hashes."""
    import importlib.metadata
    import material
    spec = importlib.util.spec_from_file_location("bijux_publication_exact_csp", Path(__file__).with_name("csp.py"))
    processor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(processor)
    require(importlib.metadata.version("mkdocs-material") == processor.MATERIAL_VERSION,
            "CSP receipt: actual admitted dependency version differs")
    templates = Path(material.__file__).parent / "templates"
    observed = processor.policy_inputs(canonical, templates)
    require(all(csp["policy_inputs"].get(key) == value for key, value in observed.items()),
            "CSP receipt: actual source/dependency executable inputs differ")
    require(csp.get("processor_sha256") == hashlib.sha256(Path(processor.__file__).read_bytes()).hexdigest(),
            "CSP receipt: executable processor differs")
    allowed, base = processor.admitted_scripts(canonical, templates)
    def validate(html, path, capability, report):
        parsed = DocumentPolicy(owned_report=bool(capability and "script_hashes" in capability),
                                owned_parent=bool(capability and "script_hashes" not in capability))
        parsed.feed(html)
        require(len(parsed.csp) == 1 and not parsed.failures, "CSP receipt: unsafe or missing effective HTML policy")
        injected = '\n<meta http-equiv="Content-Security-Policy" content="' + parsed.csp[0] + '">'
        require(html.count(injected) == 1, "CSP receipt: exact early insertion is required")
        original = html.replace(injected, "", 1)
        page_allowed = allowed
        if capability and "script_hashes" in capability:
            # The embedded source verifier already proved these exact bodies;
            # reparse only this declared source-owned route, never ordinary HTML.
            page_parser = processor.Scripts()
            page_parser.feed(original)
            page_allowed = set(page_parser.inline)
            require({processor.hash_source(body) for body in page_allowed} == {"'" + h + "'" for h in capability["script_hashes"]},
                    "CSP receipt: source-owned report bodies differ")
        for record in report.get("redirects", {}).get("records", []):
            if record["path"] == path:
                redirect = importlib.util.spec_from_file_location("bijux_publication_exact_redirect", Path(__file__).with_name("redirects.py"))
                normalizer = importlib.util.module_from_spec(redirect)
                redirect.loader.exec_module(normalizer)
                script = normalizer.SCRIPT.format(target=json.dumps(record["target"], ensure_ascii=True))
                page_allowed = page_allowed | {script}
        updated, _ = processor.qualify_html(original, page_allowed, base, capability,
                                          owned_report=bool(capability and "script_hashes" in capability))
        require(updated == html, "CSP receipt: final policy differs from independently admitted executable source")
    return validate


def qualified_redirects(canonical: Path, build: dict, csp: dict, site: Path, site_url: str) -> dict:
    """Reconstruct each admitted redirect from actual renderer map and trusted source."""
    inputs = csp["policy_inputs"].get("redirects")
    report = csp.get("redirects")
    require(isinstance(inputs, dict) and isinstance(report, dict), "Redirect receipt: explicit scope required")
    spec = importlib.util.spec_from_file_location("bijux_admitted_redirects", canonical / "security/redirects.py")
    processor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(processor)
    require(inputs.get("processor_sha256") == hashlib.sha256((canonical / "security/redirects.py").read_bytes()).hexdigest()
            and inputs.get("resolved_config_sha256") == build["resolved_config_sha256"],
            "Redirect receipt: accepted processor or actual configuration differs")
    require(report.get("schema") == 1 and report.get("policy") == "exact-declared-redirects"
            and report.get("site_url") == site_url and report.get("applied") is True,
            "Redirect receipt: normalized publication scope required")
    records = report.get("records")
    require(isinstance(records, list), "Redirect receipt: records required")
    plugin = build["renderer"].get("plugins", {}).get("redirects")
    if plugin is None:
        require(inputs.get("plugin") is None and inputs.get("redirect_map_sha256") is None and not records,
                "Redirect receipt: undeclared plugin or routes")
        return {}
    expected_plugin = {"distribution": "mkdocs-redirects", "version": processor.PLUGIN_VERSION,
                       "module": "mkdocs_redirects/plugin.py", "module_sha256": processor.PLUGIN_MODULE_SHA256,
                       "template_sha256": processor.PLUGIN_TEMPLATE_SHA256}
    require(inputs.get("plugin") == expected_plugin
            and plugin.get("module") == "mkdocs_redirects.plugin"
            and plugin.get("distributions", {}).get("mkdocs-redirects") == processor.PLUGIN_VERSION
            and plugin.get("source", {}).get("sha256") == processor.PLUGIN_MODULE_SHA256,
            "Redirect receipt: actual reviewed plugin identity differs")
    mapping = plugin.get("redirect_maps")
    require(isinstance(mapping, dict) and len(mapping) <= 10000
            and inputs.get("redirect_map_sha256") == plugin.get("redirect_map_sha256") == identity_module().json_digest(mapping),
            "Redirect receipt: actual declared map differs")
    routes = plugin.get("routes", [])
    require(isinstance(routes, list) and len(routes) == len(mapping) == len(records),
            "Redirect receipt: incomplete declared route coverage")
    configured = {}
    declared_sources = set()
    for route in routes:
        processor.path_parameter(route["source"])
        processor.path_parameter(route["declared_target"].partition("#")[0])
        require(mapping.get(route["source"]) == route["declared_target"] and route["path"] not in configured,
                "Redirect receipt: renderer route differs from declared source")
        require(route["source"] not in declared_sources, "Redirect receipt: duplicate declared source")
        declared_sources.add(route["source"])
        identity_module().regular(site, route["path"])
        configured[route["path"]] = route
    require(declared_sources == set(mapping), "Redirect receipt: missing actual declared source")
    admitted = {}
    for record in records:
        path = record.get("path")
        require(path in configured and path not in admitted, "Redirect receipt: undeclared or duplicate emitted route")
        route = configured[path]
        require(record.get("source") == route["source"] and record.get("declared_target") == route["declared_target"],
                "Redirect receipt: source parameters differ")
        seen = set()
        current = route
        fragment = ""
        while True:
            require(current["path"] not in seen, "Redirect receipt: cyclic declared routes")
            seen.add(current["path"])
            fragment = fragment or current["declared_target"].partition("#")[2]
            if current["destination"] not in configured:
                break
            current = configured[current["destination"]]
        destination = current["destination"]
        identity_module().regular(site, destination)
        url = current["url"]
        require(not urlsplit(url).scheme and not urlsplit(url).netloc and not url.startswith("/")
                and "\\" not in unquote(url) and not any(part in {".", ".."} for part in unquote(url).split("/")),
                "Redirect receipt: target escaped product base")
        canonical_url = site_url + quote(unquote(url), safe="/-._~")
        target = canonical_url + ("#" + quote(unquote(fragment), safe="-._~:") if fragment else "")
        require(record.get("destination") == destination and record.get("canonical") == canonical_url and record.get("target") == target,
                "Redirect receipt: final target differs from actual declared chain")
        terminal = processor.Destination()
        terminal.feed((site / destination).read_text())
        require(not terminal.redirect and (not fragment or unquote(fragment) in terminal.ids),
                "Redirect receipt: terminal route or fragment is unavailable")
        script = processor.SCRIPT.format(target=json.dumps(target, ensure_ascii=True))
        script_digest = hashlib.sha256(script.encode()).digest()
        csp_hash = "'sha256-" + base64.b64encode(script_digest).decode() + "'"
        expected_html = processor.TEMPLATE.format(canonical=escape(canonical_url, quote=True), target=escape(target, quote=True), script=script)
        require(record.get("script_sha256") == script_digest.hex() and record.get("csp_hash") == csp_hash
                and record.get("normalized_sha256") == hashlib.sha256(expected_html.encode()).hexdigest()
                and bool(re.fullmatch(r"[0-9a-f]{64}", record.get("input_sha256", ""))),
                "Redirect receipt: normalized template or script identity differs")
        document = (site / path).read_text()
        parsed = DocumentPolicy()
        parsed.feed(document)
        require(len(parsed.csp) == 1, "Redirect receipt: effective CSP missing")
        injected = '\n<meta http-equiv="Content-Security-Policy" content="' + parsed.csp[0] + '">'
        require(document.count(injected) == 1 and document.replace(injected, "", 1) == expected_html,
                "Redirect receipt: final page differs from exact admitted template")
        admitted[path] = csp_hash
    return admitted


def qualified_manifest(repo_root: Path, site_dir: str, site_url: str, source_sha: str,
                       policy: dict, source_identity: str, build_identity: str,
                       verification_report: str, csp_report: str) -> dict:
    """Bind honest source/build/mechanical policy evidence to the exact upload bytes."""
    identity = identity_module()
    root = repo_root.resolve()
    selected = site_directory(root, site_dir, exists=True)
    records = {}
    for name, value in (("source", source_identity), ("build", build_identity),
                        ("verification", verification_report), ("csp", csp_report)):
        path = identity.artifact(root, value)
        require(path.is_file(), f"{name} qualification receipt: missing")
        require(not path.is_relative_to(selected), "qualification receipt: keep evidence outside public bundle")
        content = path.read_bytes()
        records[name] = {"path": value, "sha256": hashlib.sha256(content).hexdigest(), "receipt": json.loads(content)}
    source = records["source"]["receipt"]
    identity.verify_source(root, source)
    require(source["repository_source"]["sha"] == source_sha, "source identity: receipt differs from selected source")
    require(source["site_url"] == site_url and source["site_dir"] == site_dir,
            "source identity: receipt selects another public artifact")
    embedded = None
    if records["csp"]["receipt"].get("embedded") is not None:
        embedded_module()
        readers = importlib.import_module("bijux_publication_embedded.publication")
        try:
            embedded = readers.verify_readers(selected, records["csp"]["receipt"],
                                              records["build"]["receipt"], repository=root,
                                              identity=identity, checkpoint=source)
        except (ValueError, KeyError, OSError) as error:
            raise AdmissionError(
                "Embedded publication: independently reconstructed producer capability admission is required: " + str(error)
            ) from error
        require(embedded["site_url"] == site_url, "Embedded publication: source-owned site identity differs")
    result = bundle_manifest(root, site_dir, site_url, source_sha, policy, source["standard"]["sha"],
                             embedded_report_routes=embedded["report_routes"] if embedded else None,
                             embedded_parent_routes=(set(embedded["capabilities"]) - embedded["report_routes"]) if embedded else None)
    for name in ("build", "verification", "csp"):
        receipt = records[name]["receipt"]
        require(receipt.get("schema") == 1, f"{name} receipt: unsupported schema")
        require(receipt.get("site_url") == site_url and receipt.get("site_dir") == site_dir,
                f"{name} receipt: wrong public artifact")
        require(receipt.get("bundle_sha256") == result["bundle_sha256"], f"{name} receipt: stale or unqualified bundle")
    build = records["build"]["receipt"]
    require(build.get("state") == "complete" and build.get("verification_only") is False,
            "build receipt: completed publication renderer identity required")
    require(build.get("source_checkpoint") == source and build.get("source_checkpoint_sha256") == identity.json_digest(source),
            "build receipt: another source checkpoint")
    require(build.get("processor_sha256") == hashlib.sha256(Path(__file__).with_name("build_identity.py").read_bytes()).hexdigest(),
            "build receipt: identity processor differs from accepted source")
    require(build.get("derivation") == source.get("derivation"),
            "source identity: build derivation differs from owner checkpoint")
    if source.get("derivation"):
        require(build.get("effective_config") == source["derivation"]["configuration"],
                "source identity: exact reconstructed configuration required")
    else:
        require("effective_config" not in build, "source identity: unreviewed derived configuration")
    config = build["config"]
    require(hashlib.sha256(identity.regular(root, config["path"]).read_bytes()).hexdigest() == config["sha256"],
            "build receipt: actual renderer configuration changed")
    require(bool(re.fullmatch(r"[0-9a-f]{64}", build.get("resolved_config_sha256", ""))),
            "build receipt: resolved renderer configuration identity missing")
    require(isinstance(build.get("renderer_inputs"), list) and build["renderer_inputs"],
            "build receipt: actual renderer source input identity missing")
    for inputs in build["renderer_inputs"]:
        path = Path(inputs["path"])
        require(not path.is_absolute() and ".." not in path.parts and str(path) == inputs["path"],
                "build receipt: normalized renderer input path required")
        require(identity.tree_identity(root / path) == inputs["sha256"],
                "build receipt: actual renderer source inputs changed")
    packages = build["renderer"]["packages"]
    require(all(isinstance(packages.get(name), str) and packages[name] for name in
                ("mkdocs", "mkdocs-material", "Jinja2", "PyYAML", "Markdown", "Pygments", "pymdown-extensions")),
            "build receipt: actual MkDocs renderer package identity missing")
    verification = records["verification"]["receipt"]
    require(verification.get("passed") is True and verification.get("verification_only") is False,
            "verification receipt: passed publication-scope mechanical checks required")
    require(set(verification.get("scope", [])) == {"PUBLIC-ROUTES", "SEARCH-DELIVERY", "PRODUCTION-URLS"},
            "verification receipt: required route/search/public URL scope missing")
    checks = verification.get("checks", [])
    require({check.get("id") for check in checks} == {"PUBLIC-ROUTES", "SEARCH-DELIVERY", "PRODUCTION-URLS"}
            and len(checks) == 3 and all(check.get("passed") is True and not check.get("errors") for check in checks),
            "verification receipt: skipped, failed or missing mechanical checks")
    source_checks = verification.get("source_checks", {})
    require(source_checks.get("before") is True and source_checks.get("after") is True
            and source_checks.get("mode") == "exact_fetched"
            and source_checks.get("standard_sha") == source["standard"]["sha"]
            and source_checks.get("origin") == source["standard"]["origin"],
            "verification receipt: another or unverified standard authority")
    if verification.get("development_link_policy"):
        path = identity.regular(root, verification["development_link_policy"])
        identity.git(root, "ls-files", "--error-unmatch", verification["development_link_policy"])
        require(hashlib.sha256(path.read_bytes()).hexdigest() == verification.get("development_link_policy_sha256"),
                "verification receipt: reviewed development-link policy changed")
    else:
        require(verification.get("development_link_policy_sha256") is None,
                "verification receipt: development-link policy source missing")
    csp = records["csp"]["receipt"]
    require(csp.get("policy") == "early-meta-hashes" and csp.get("material") == packages["mkdocs-material"],
            "CSP receipt: actual admitted renderer policy identity required")
    canonical = root / source["shared_root"]
    require(csp.get("processor_sha256") == hashlib.sha256((canonical / "security/csp.py").read_bytes()).hexdigest(),
            "CSP receipt: policy processor differs from accepted source")
    policy_inputs = csp["policy_inputs"]
    expected_canonical = [{"path": name, "sha256": hashlib.sha256(identity.regular(canonical, name).read_bytes()).hexdigest()}
                          for name in ("partials/javascripts/base.html", "partials/javascripts/palette.html")]
    require(policy_inputs.get("canonical") == expected_canonical, "CSP receipt: canonical policy inputs differ from accepted source")
    require(policy_inputs.get("material_templates") and policy_inputs["material_templates"] == build["renderer"].get("material_templates"),
            "CSP receipt: policy template inputs differ from actual renderer")
    redirect_hashes = qualified_redirects(canonical, build, csp, selected, site_url)
    require(build.get("config") == source.get("config") and source.get("config") is not None,
            "source identity: build config must equal owner-selected checkpoint")
    html = [entry for entry in result["files"] if entry["path"].endswith(".html")]
    require(csp.get("pages") == len(html), "CSP receipt: incomplete public HTML coverage")
    used_hashes = set()
    for entry in html:
        capability = embedded["capabilities"].get(entry["path"]) if embedded else None
        parsed = DocumentPolicy(owned_report=bool(embedded and entry["path"] in embedded["report_routes"]),
                                owned_parent=bool(capability and "script_hashes" not in capability))
        parsed.feed((selected / entry["path"]).read_text())
        require(len(parsed.csp) == 1 and parsed.csp_early, "CSP receipt: missing or late effective policy")
        page_hashes = applied_csp(parsed.csp[0], set(csp.get("script_hashes", [])), capability)
        require(page_hashes.intersection(redirect_hashes.values()) == ({redirect_hashes[entry["path"]]} if entry["path"] in redirect_hashes else set()),
                "Redirect receipt: executable hash admitted on another route")
        used_hashes.update(page_hashes)
    require(used_hashes == set(csp.get("script_hashes", [])), "CSP receipt: executable policy coverage differs")
    producer_spec = importlib.util.spec_from_file_location("bijux_publication_producer", identity.regular(canonical, "security/producer_authority.py"))
    producer = importlib.util.module_from_spec(producer_spec)
    producer_spec.loader.exec_module(producer)
    producer_evidence = producer.verify_publication(root, selected, canonical, build, csp, source)
    identity.verify_source(root, source)
    return result | {"schema": 2, "qualification": records, "producer_authority": producer_evidence,
                     "scope": "clean accepted source, actual renderer, route/search/public URLs and applied CSP",
                     "limitations": ["Configured verifier and repository commands are trusted author code, not a sandbox for a malicious maintainer.",
                                     "Browser/accessibility/manual/hosting/live publication gates remain separate evidence."]}


def verify_manifest(repo_root: Path, manifest: dict, policy: dict) -> dict:
    if manifest.get("schema") == 2:
        # Serialized qualification/profile fields are assertions to verify again,
        # never executable or producer authority merely because bytes still match.
        records = manifest.get("qualification")
        require(isinstance(records, dict) and set(records) == {"source", "build", "verification", "csp"},
                "public bundle: complete source-owned qualification records required")
        current = qualified_manifest(repo_root, manifest["site_dir"], manifest["site_url"],
                                     manifest["repository_source_sha"], policy,
                                     *(records[name]["path"] for name in ("source", "build", "verification", "csp")))
    else:
        current = bundle_manifest(repo_root, manifest["site_dir"], manifest["site_url"],
                                  manifest["repository_source_sha"], policy, manifest.get("standard_sha"))
    require(current == manifest, "public bundle: changed after qualification or policy identity differs")
    return current



def verify_retained_bytes(repo_root: Path, manifest: dict, policy: dict) -> dict:
    """Compare an explicitly selected historical bundle without granting authority.

    An offline recovery operator must independently trust the retained manifest.
    Its serialized source/profile/CSP declarations are not verified or returned.
    """
    require(manifest.get("schema") in {1, 2}, "retained bytes: supported inventory required")
    site = site_directory(repo_root, manifest["site_dir"], exists=True)
    files, digest = public_bundle_identity(site)
    total = sum(item["bytes"] for item in files)
    require(files == manifest.get("files") and digest == manifest.get("bundle_sha256")
            and len(files) == manifest.get("file_count") and total == manifest.get("bytes"),
            "retained bytes: physical inventory differs from selected historical manifest")
    policy_digest = hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()
    require(policy_digest == manifest.get("policy_sha256"), "retained bytes: policy identity differs")
    require(total <= policy["maximum_bytes"] and len(files) <= policy["maximum_files"],
            "retained bytes: current inventory budget exceeded")
    return {"schema": 1, "scope": "retained-public-bytes-only", "verification_only": True,
            "publication_approval": False, "qualified_source_verified": False,
            "site_dir": manifest["site_dir"], "bundle_sha256": digest,
            "file_count": len(files), "bytes": total, "policy_sha256": policy_digest}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    config = commands.add_parser("config")
    for name in ("repository", "event", "ref", "default-branch", "site-url", "site-dir", "verify-command"):
        config.add_argument("--" + name, required=True)
    manifest = commands.add_parser("admit")
    for name in ("site-dir", "site-url", "source-sha"):
        manifest.add_argument("--" + name, required=True)
    manifest.add_argument("--standard-sha")
    for name in ("source-identity", "build-identity", "verification-report", "csp-report"):
        manifest.add_argument("--" + name, required=True)
    manifest.add_argument("--policy", type=Path, default=POLICY)
    manifest.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--policy", type=Path, default=POLICY)
    mode = verify.add_mutually_exclusive_group()
    mode.add_argument("--require-qualified", action="store_true")
    mode.add_argument("--bytes-only", action="store_true",
                      help="Compare selected retained bytes offline; grants no source, runtime or publication authority")
    args = parser.parse_args()
    try:
        if args.command == "config":
            result = validate_config(repository=args.repository, event=args.event, ref=args.ref,
                                     default_branch=args.default_branch, site_url=args.site_url,
                                     site_dir=args.site_dir, verify_command=args.verify_command,
                                     repo_root=args.repo_root)
        elif args.command == "admit":
            root = args.repo_root.resolve()
            relative = args.output.relative_to(root).as_posix() if args.output.is_absolute() else args.output.as_posix()
            output = identity_module().artifact(root, relative)
            require(not output.is_relative_to(site_directory(args.repo_root, args.site_dir)),
                    "manifest: keep identity outside uploaded bundle")
            result = qualified_manifest(args.repo_root, args.site_dir, args.site_url, args.source_sha,
                                        load_policy(args.policy), args.source_identity, args.build_identity,
                                        args.verification_report, args.csp_report)
            if args.standard_sha:
                require(args.standard_sha == result["standard_sha"], "standard identity: supplied value differs from actual accepted pin")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        else:
            retained = json.loads(args.manifest.read_text())
            if args.bytes_only:
                result = verify_retained_bytes(args.repo_root, retained, load_policy(args.policy))
            else:
                if args.require_qualified:
                    require(retained.get("schema") == 2, "publication: qualified identity manifest required")
                result = verify_manifest(args.repo_root, retained, load_policy(args.policy))
        summary = {k: v for k, v in result.items() if k not in {"files", "qualification"}}
        if "qualification" in result:
            summary["qualification_receipts"] = {key: {"path": value["path"], "sha256": value["sha256"]}
                                                  for key, value in result["qualification"].items()}
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (AdmissionError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"documentation publication rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
