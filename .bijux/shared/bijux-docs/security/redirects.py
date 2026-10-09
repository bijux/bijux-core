#!/usr/bin/env python3
"""Normalize only exact declared documentation redirects before CSP admission."""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
from html import escape
from html.parser import HTMLParser
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import posixpath
import re
import sys
from urllib.parse import quote, unquote, urlsplit

sys.dont_write_bytecode = True

PLUGIN_VERSION = "1.2.3"
PLUGIN_MODULE_SHA256 = "676e3e0cac7fc861593179092ec1386dbc581df5ededffc983305d4866ddf432"
PLUGIN_TEMPLATE_SHA256 = "65f7280ef6788775c0530bde48f906977c31f70aaa0a3c37ffa1cca02a4bc112"
SCRIPT = ('var target=new URL({target});'
          'var highlight=new URLSearchParams(window.location.search).get("h");'
          'if(highlight&&highlight.length<=4096)target.searchParams.set("h",highlight);'
          'if(!target.hash)target.hash=window.location.hash;'
          'window.location.replace(target.href);')
TEMPLATE = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Redirecting...</title>
<link rel="canonical" href="{canonical}">
<script>{script}</script>
<meta http-equiv="refresh" content="0; url={target}">
</head>
<body>You're being redirected to a <a href="{target}">new destination</a>.</body>
</html>
'''


class RedirectError(ValueError):
    """A generated redirect cannot inherit declared source admission."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RedirectError(message)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def identity_module():
    spec = importlib.util.spec_from_file_location("bijux_redirect_build_identity", Path(__file__).with_name("build_identity.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def path_parameter(value: str) -> str:
    require(isinstance(value, str) and bool(value), "Redirect: nonempty declared Markdown path required")
    require(not value.startswith("/") and all(part not in {"", ".", ".."} for part in value.split("/")),
            "Redirect: normalized relative Markdown path required")
    require(not any(ord(char) < 32 or ord(char) == 127 or char in '\\<>"\'%?#' or char in '\u2028\u2029' for char in value),
            "Redirect: ambiguous or executable path parameter")
    require(value.lower().endswith(".md"), "Redirect: declared Markdown route required")
    return value


def plugin_inputs(plugin) -> tuple[dict, str]:
    require(type(plugin).__module__ == "mkdocs_redirects.plugin", "Redirect: admitted plugin implementation required")
    distribution = importlib.metadata.distribution("mkdocs-redirects")
    require(distribution.version == PLUGIN_VERSION, "Redirect: reviewed mkdocs-redirects==1.2.3 required")
    module = Path(distribution.locate_file("mkdocs_redirects/plugin.py"))
    require(module.is_file() and not module.is_symlink(), "Redirect: regular plugin source required")
    source = module.read_bytes()
    require(digest(source) == PLUGIN_MODULE_SHA256, "Redirect: installed plugin source differs from reviewed bytes")
    loaded = Path(sys.modules[type(plugin).__module__].__file__).resolve()
    require(loaded == module.resolve(), "Redirect: loaded plugin source differs from installed distribution")
    constants = [node.value for node in ast.parse(source).body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "HTML_TEMPLATE" for target in node.targets)]
    require(len(constants) == 1, "Redirect: dependency template identity missing")
    template = ast.literal_eval(constants[0])
    require(isinstance(template, str) and digest(template.encode()) == PLUGIN_TEMPLATE_SHA256,
            "Redirect: dependency template differs from reviewed bytes")
    return {"distribution": "mkdocs-redirects", "version": distribution.version,
            "module": "mkdocs_redirects/plugin.py", "module_sha256": digest(source),
            "template_sha256": digest(template.encode())}, template


class Destination(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.redirect = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        self.redirect |= tag == "meta" and (values.get("http-equiv") or "").lower() == "refresh"


def normalize_redirects(configuration, site: Path, site_url: str, *, write: bool = True) -> dict:
    """Preflight declared producer bytes and final destinations, then normalize stubs."""
    identity = identity_module()
    require(site.is_dir() and not site.is_symlink(), "Redirect: regular built site directory required")
    require(configuration.site_url == site_url, "Redirect: actual configuration production URL differs")
    plugin = configuration.plugins.get("redirects")
    inputs = {"processor_sha256": digest(Path(__file__).read_bytes()),
              "resolved_config_sha256": identity.configuration_identity(configuration, Path(configuration.config_file_path).parent),
              "plugin": None, "redirect_map_sha256": None}
    if plugin is None:
        return {"schema": 1, "policy": "exact-declared-redirects", "site_url": site_url,
                "policy_inputs": inputs, "records": [], "applied": write}
    from mkdocs.structure.files import File, get_files
    plugin_identity, dependency_template = plugin_inputs(plugin)
    inputs["plugin"] = plugin_identity
    mapping = plugin.config.get("redirect_maps", {})
    require(isinstance(mapping, dict), "Redirect: declared map must be an object")
    require(len(mapping) <= 10000, "Redirect: declared route count exceeds admission budget")
    if mapping:
        identity.publication().validate_url(site_url)
    inputs["redirect_map_sha256"] = identity.json_digest(mapping)
    files = {file.src_uri: file for file in get_files(configuration).documentation_pages()}
    planned = {}
    for old, new in sorted(mapping.items()):
        old = path_parameter(old)
        require(isinstance(new, str), "Redirect: string target required")
        source, separator, fragment = new.partition("#")
        path_parameter(source)
        require(not fragment or not any(ord(char) < 32 or ord(char) == 127 or char in '\\<>"\'?#' or char in '\u2028\u2029' for char in fragment),
                "Redirect: ambiguous fragment parameter")
        require(source in files, "Redirect: declared target is not an actual documentation source")
        old_html = File(old, "", "", configuration.use_directory_urls).dest_uri
        require(old_html not in planned, "Redirect: colliding emitted source route")
        target_file = files[source]
        relative = posixpath.relpath(target_file.url, start=posixpath.dirname(old_html))
        if configuration.use_directory_urls:
            relative += "/"
        if separator:
            relative += "#" + fragment
        path = identity.regular(site, old_html)
        original = path.read_bytes()
        require(len(original) <= 65536, "Redirect: stub exceeds admission size budget")
        planned[old_html] = {"source": old, "declared_target": new, "destination": target_file.dest_uri,
                             "url": target_file.url, "fragment": fragment, "path": path,
                             "original": original, "expected": dependency_template.format(url=relative).encode()}

    resolved = {}

    def terminal(name: str) -> tuple[str, str, str]:
        seen = set()
        pending = []
        current = name
        while current in planned and current not in resolved:
            require(current not in seen, "Redirect: cycle or self-redirect")
            seen.add(current)
            pending.append(current)
            item = planned[current]
            current = item["destination"]
        destination, target_url, fragment = resolved.get(current, (current, planned[pending[-1]]["url"] if pending else "", ""))
        for source in reversed(pending):
            fragment = planned[source]["fragment"] or fragment
            resolved[source] = (destination, target_url, fragment)
        return resolved[name]

    records = []
    writes = []
    for old_html, item in planned.items():
        destination, target_url, fragment = terminal(old_html)
        target = identity.regular(site, destination)
        document = Destination()
        document.feed(target.read_text(encoding="utf-8"))
        require(not document.redirect, "Redirect: undeclared redirect destination")
        require(not fragment or unquote(fragment) in document.ids, "Redirect: fixed fragment does not exist at final destination")
        require(not urlsplit(target_url).scheme and not urlsplit(target_url).netloc and not target_url.startswith("/"),
                "Redirect: target escaped product base")
        absolute = site_url + quote(unquote(target_url), safe="/-._~")
        canonical = absolute
        if fragment:
            absolute += "#" + quote(unquote(fragment), safe="-._~:")
        script = SCRIPT.format(target=json.dumps(absolute, ensure_ascii=True))
        normalized = TEMPLATE.format(canonical=escape(canonical, quote=True), target=escape(absolute, quote=True), script=script).encode()
        require(item["original"] in {item["expected"], normalized}, "Redirect: output differs from exact declared dependency/shared template")
        records.append({"path": old_html, "source": item["source"], "declared_target": item["declared_target"],
                        "destination": destination, "target": absolute, "canonical": canonical,
                        "input_sha256": digest(item["original"]), "normalized_sha256": digest(normalized),
                        "normalized_html": normalized.decode("utf-8"),
                        "script": script, "script_sha256": digest(script.encode()),
                        "csp_hash": "'sha256-" + base64.b64encode(hashlib.sha256(script.encode()).digest()).decode() + "'"})
        writes.append((item["path"], item["original"], normalized))
    for path, original, _ in writes:
        require(path.read_bytes() == original, "Redirect: generated output changed during preflight")
    if write:
        for path, _, normalized in writes:
            path.write_bytes(normalized)
    return {"schema": 1, "policy": "exact-declared-redirects", "site_url": site_url,
            "policy_inputs": inputs, "records": records,
            "applied": write,
            "behavior": {"history": "replace", "configured_fragment_precedence": True,
                         "incoming_query": "h only, at most 4096 characters",
                         "no_javascript": "meta refresh and direct fallback; incoming query/hash preservation is not claimed"}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("config", "site-dir", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--site-url", default="")
    parser.add_argument("--check", action="store_true", help="Retain a fully preflighted plan without mutating public files")
    args = parser.parse_args()
    identity = identity_module()
    root = Path.cwd().resolve()
    try:
        from mkdocs.config import load_config
        configuration = load_config(str(identity.regular(root, args.config)), site_dir=str(root / args.site_dir))
        site = identity.publication().site_directory(root, args.site_dir, exists=True)
        output = identity.artifact(root, args.output)
        require(not output.is_relative_to(site), "Redirect: keep evidence outside published bundle")
        report = normalize_redirects(configuration, site, args.site_url or configuration.site_url, write=not args.check)
        report["site_dir"] = args.site_dir
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
    except (RedirectError, ValueError, OSError, TypeError, KeyError, ImportError) as error:
        parser.exit(1, f"Documentation redirect rejected: {error}\n")
    print(json.dumps({"policy": report["policy"], "routes": len(report["records"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
