#!/usr/bin/env python3
"""Run bounded static delivery smoke checks without collecting visitor telemetry."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
from http.client import HTTPConnection, HTTPSConnection, HTTPException
import importlib.util
import json
from pathlib import Path
import re
import sys
import subprocess
import time
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

MAX_BYTES = 8 * 1024 * 1024
HEADER_NAMES = ("content-security-policy", "strict-transport-security", "x-content-type-options",
                "x-frame-options", "referrer-policy", "permissions-policy", "cache-control", "etag")


def sibling_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRODUCTION_URL = sibling_module("bijux_monitor_production_url", Path(__file__).resolve().parents[1] / "tooling/quality/validate_production_url.py")


def relative_path(value: str, *, fragment: bool = False) -> tuple[str, str]:
    parsed = urlsplit(value)
    if (parsed.scheme or parsed.netloc or parsed.query or (parsed.fragment and not fragment)
            or re.search(r"%(?![0-9a-fA-F]{2})|%2f|%5c", parsed.path, re.IGNORECASE)):
        raise ValueError("monitor path: normalized relative product descendant required")
    path = unquote(parsed.path, errors="strict")
    if (path.startswith("/") or any(part in {".", ".."} for part in path.split("/"))
            or "//" in path or re.search(r"%[0-9a-fA-F]{2}", path)
            or any(ord(c) <= 32 or c == "\\" for c in path)):
        raise ValueError("monitor path: ambiguous or escaping path")
    anchor = unquote(parsed.fragment, errors="strict")
    if any(ord(c) < 32 for c in anchor):
        raise ValueError("monitor anchor: control characters forbidden")
    return quote(path, safe="/"), anchor


def public_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def validate_target(url: str, live: bool) -> None:
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("monitor target: credentials/query/fragment forbidden")
    if any(ord(c) <= 32 or c == "\\" for c in url):
        raise ValueError("monitor target: plain URL required")
    relative_path(parsed.path.lstrip("/"))
    if parsed.path.startswith("//"):
        raise ValueError("monitor target: ambiguous path")
    if live:
        if parsed.scheme != "https" or parsed.hostname != "bijux.io" or parsed.port is not None:
            raise ValueError("live monitor: only HTTPS bijux.io without explicit port admitted")
    elif parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("local monitor: loopback HTTP required; public targets require --live")


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonical: list[str] = []
        self.title = False
        self.title_text: list[str] = []
        self.navigation = 0
        self.csp: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "title":
            self.title = True
        if tag == "a" and values.get("href") and not values["href"].startswith("#"):
            self.navigation += 1
        if tag == "link" and "canonical" in (values.get("rel") or "").split():
            self.canonical.append(values.get("href") or "")
        if tag == "meta" and (values.get("http-equiv") or "").lower() == "content-security-policy":
            self.csp.append(values.get("content") or "")

    def handle_endtag(self, tag):
        if tag == "title":
            self.title = False

    def handle_data(self, data):
        if self.title:
            self.title_text.append(data)


def request(url: str, *, live: bool, timeout: float, expected_status: int = 200,
            product_root: str | None = None) -> tuple[dict, bytes]:
    validate_target(url, live)
    if not 0 < timeout <= 30:
        raise ValueError("monitor timeout: within 30 seconds required")
    if product_root is not None:
        validate_target(product_root, live)
        if not product_root.endswith("/"):
            raise ValueError("monitor product boundary: trailing slash required")
    boundary = urlsplit(product_root or urlunsplit((*urlsplit(url)[:2], "/", "", "")))
    started = time.monotonic()
    redirects, size = [], 0
    result = {"url": public_url(url), "expected_status": expected_status,
              "boundary_kind": "declared_product" if product_root else "standalone_origin"}
    def remaining():
        value = timeout - (time.monotonic() - started)
        if value <= 0:
            raise TimeoutError("monitor deadline exhausted")
        return value
    try:
        current = url
        for hop in range(4):
            validate_target(current, live)
            parsed = urlsplit(current)
            if ((parsed.scheme, parsed.netloc) != (boundary.scheme, boundary.netloc)
                    or not parsed.path.startswith(boundary.path)):
                raise ValueError("monitor redirect: outside declared product")
            connection = (HTTPSConnection if live else HTTPConnection)(parsed.hostname, parsed.port, timeout=remaining())
            try:
                # Direct connections deliberately do not inherit ambient HTTP proxy settings.
                connection.connect()
                transport = connection.sock
                transport.settimeout(remaining())
                connection.request("GET", parsed.path or "/", headers={"User-Agent": "bijux-docs-monitor/1", "Accept-Encoding": "identity"})
                transport.settimeout(remaining())
                response = connection.getresponse()
                declared_length = response.length
                chunks = []
                while True:
                    if response.isclosed():
                        break
                    transport.settimeout(remaining())
                    chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk); size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("monitor response: byte budget exceeded")
                remaining()
                body = b"".join(chunks)
                if declared_length is not None and len(body) != declared_length:
                    raise HTTPException("monitor response: truncated payload")
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    if not location or hop == 3:
                        raise ValueError("monitor redirect: missing destination or hop limit")
                    redirects.append({"url": public_url(current), "status": response.status})
                    current = urljoin(current, location)
                    continue
                encoding = response.getheader("Content-Encoding", "identity").lower()
                result.update(status=response.status, final_url=public_url(current),
                              headers={name: {"present": True, "sha256": hashlib.sha256(response.getheader(name).encode()).hexdigest()} for name in HEADER_NAMES if response.getheader(name)},
                              content_type=response.getheader("Content-Type", "").split(";", 1)[0].strip().lower(),
                              passed=response.status == expected_status and encoding == "identity",
                              body_sha256=hashlib.sha256(body).hexdigest(), body_bytes=len(body))
                return result, body
            finally:
                connection.close()
        raise ValueError("monitor redirect: hop limit")
    except (ValueError, HTTPException, OSError) as error:
        # Do not retain server-controlled messages or complete URLs with sensitive parameters.
        result.update(passed=False, error_type=type(error).__name__)
        return result, b""
    finally:
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        result["redirects"] = redirects
        result["received_bytes"] = size


def execution_source(repo: Path) -> dict:
    owner = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True)
    dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True)
    owns_source = owner.returncode == 0 and Path(owner.stdout.strip()).resolve() == repo
    return {"git_sha": head.stdout.strip() if owns_source and head.returncode == 0 else None,
            "working_tree_dirty": bool(dirty.stdout) if owns_source and dirty.returncode == 0 else None,
            "module_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "url_validator_sha256": hashlib.sha256(Path(PRODUCTION_URL.__file__).read_bytes()).hexdigest(),
            "publication_inputs": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                   for name in ("publication.py", "build_identity.py", "policy.json")},
            "classification": "executing local checkout and module bytes; not accepted publication identity"}


def smoke(root: str, *, canonical_root: str, deep_path: str = "", asset_path: str = "assets/stylesheets/main.css",
          query: str = "", live: bool = False, timeout: float = 10.0,
          manifest_path: Path | None = None, repo_root: Path | None = None) -> dict:
    validate_target(root, live)
    if not root.endswith("/"):
        raise ValueError("monitor root: trailing slash required")
    PRODUCTION_URL.validate(canonical_root)
    canonical = urlsplit(canonical_root)
    if canonical.hostname != "bijux.io" or urlsplit(root).path != canonical.path or (live and root != canonical_root):
        raise ValueError("canonical root: HTTPS bijux.io identity required")
    deep_path, _ = relative_path(deep_path)
    asset_path, _ = relative_path(asset_path)
    if not asset_path or not isinstance(query, str) or not query.strip():
        raise ValueError("monitor requires a declared asset and a known query")
    query = query.strip()
    if not 0 < timeout <= 30:
        raise ValueError("monitor timeout: within 30 seconds required")
    repo = (repo_root or Path.cwd()).resolve()
    source = execution_source(repo)
    manifest, expected_files, binding = None, {}, {"kind": "unverified_deployment", "claim": "HTTP observations do not identify an accepted deployment"}
    if manifest_path is not None:
        identity = sibling_module("bijux_monitor_identity", Path(__file__).with_name("build_identity.py"))
        selected = identity.artifact(repo, str(manifest_path))
        manifest = json.loads(selected.read_text(encoding="utf-8"))
        publication = identity.publication()
        (publication.verify_manifest if manifest.get("schema") == 1 else publication.verify_retained_bytes)(
            repo, manifest, publication.load_policy())
        if manifest["site_url"] != canonical_root:
            raise ValueError("monitor manifest: wrong public identity")
        expected_files = {item["path"]: item["sha256"] for item in manifest["files"]}
        binding = {"kind": "retained_artifact_sample", "manifest_sha256": hashlib.sha256(selected.read_bytes()).hexdigest(),
                   "repository_source_sha": manifest["repository_source_sha"], "standard_sha": manifest.get("standard_sha"),
                   "verification_mode": "mechanical-bundle" if manifest.get("schema") == 1 else "retained-public-bytes-only",
                   "verification_only": True, "publication_approval": False, "qualified_source_verified": False,
                   "claim": "Selected historical manifest must be independently trusted; matching sampled bytes do not establish full deployment or requalify accepted source"}
    checks, cache = [], {}
    def fetch(path, status=200):
        if path not in cache:
            result, body = request(urljoin(root, path), live=live, timeout=timeout, expected_status=status, product_root=root)
            if manifest is not None and status == 200 and result["passed"]:
                file = path + "index.html" if not path or path.endswith("/") else path
                expected = expected_files.get(unquote(file))
                result["expected_file_match"] = expected is not None and expected == result["body_sha256"]
                if not result["expected_file_match"]:
                    result.update(passed=False, error_type="sampled-artifact-mismatch")
            cache[path] = result, body
        result, body = cache[path]
        return dict(result), body
    def document(path):
        result, body = fetch(path)
        page = None
        if result["passed"]:
            try:
                page = Page(); page.feed(body.decode("utf-8"))
                if (result["content_type"] != "text/html" or page.canonical != [urljoin(canonical_root, path)]
                        or not "".join(page.title_text).strip() or not page.navigation):
                    result.update(passed=False, error_type="document-contract")
                result.update(meta_csp_count=len(page.csp), destination_count=page.navigation)
            except (UnicodeError, ValueError):
                result.update(passed=False, error_type="document-parse")
        return result, page
    for path in dict.fromkeys(["", deep_path]):
        result, _ = document(path)
        result["kind"] = "document"
        checks.append(result)
    result, body = fetch("search/search_index.json")
    result["kind"] = "search-corpus"
    if result["passed"]:
        try:
            docs = json.loads(body)["docs"]
            if (not isinstance(docs, list) or not docs or any(not isinstance(d, dict)
                    or not isinstance(d.get("location"), str) or not isinstance(d.get("title"), str)
                    or not d["title"] or not isinstance(d.get("text"), str) for d in docs)):
                raise ValueError("search corpus invalid")
            for doc in docs:
                relative_path(doc["location"], fragment=True)
            match = next((d for d in docs if query.casefold() in (d["title"] + " " + d["text"]).casefold()), None)
            if match is None:
                raise ValueError("known query absent")
            result["document_count"] = len(docs)
        except (KeyError, TypeError, UnicodeError, ValueError):
            result.update(passed=False, error_type="search-corpus-contract")
    checks.append(result)
    if result["passed"]:
        path, anchor = relative_path(match["location"], fragment=True)
        destination, page = document(path)
        if destination["passed"] and anchor and anchor not in page.ids:
            destination.update(passed=False, error_type="search-destination-anchor")
        destination["kind"] = "known-search-destination"
        checks.append(destination)
    result, body = fetch(asset_path)
    result["kind"] = "critical-asset"
    if result["passed"] and (not body or result["content_type"] == "text/html"
            or body.lstrip().lower().startswith((b"<!doctype html", b"<html", b"<head", b"<body"))):
        result.update(passed=False, error_type="asset-is-empty-or-html")
    expected_mime = {".css": {"text/css"}, ".js": {"text/javascript", "application/javascript"}}
    if (result["passed"] and Path(asset_path).suffix in expected_mime
            and result["content_type"] not in expected_mime[Path(asset_path).suffix]):
        result.update(passed=False, error_type="critical-asset-mime")
    checks.append(result)
    result, _ = fetch("bijux-monitor-missing-destination/", 404)
    result["kind"] = "missing-route"
    checks.append(result)
    if execution_source(repo) != source:
        raise ValueError("monitor execution source changed during observation")
    if manifest is not None:
        (publication.verify_manifest if manifest.get("schema") == 1 else publication.verify_retained_bytes)(
            repo, manifest, publication.load_policy())
        if hashlib.sha256(selected.read_bytes()).hexdigest() != binding["manifest_sha256"]:
            raise ValueError("retained manifest changed during observation")
    return {"schema": 2, "timestamp": datetime.now(timezone.utc).isoformat(), "root": public_url(root),
            "mode": "live-read-only" if live else "local-fixture", "passed": all(c["passed"] for c in checks),
            "source": source, "artifact_binding": binding,
            "request_budget": len(cache), "maximum_http_requests": (len(dict.fromkeys(["", deep_path])) + 4) * 4,
            "maximum_response_payload_bytes_per_chain": MAX_BYTES,
            "maximum_observation_payload_bytes": MAX_BYTES * (len(dict.fromkeys(["", deep_path])) + 4),
            "timeout_seconds": timeout, "checks": checks,
            "limitations": ["Static HTTP/search-corpus checks do not certify rendered menu, keyboard, browser search, accessibility or actual visitor availability.",
                            "Missing sampled response policies are capability evidence, not proof of compromise.",
                            "Deadlines are checked before transport phases and each body read; OS DNS/TLS/connect interruption is not an absolute wall-clock guarantee.",
                            "No scheduling, notification, deduplication, multi-region uptime or accepted live deployment claim is supplied."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--canonical-root", required=True)
    parser.add_argument("--deep-path", default="")
    parser.add_argument("--asset-path", required=True)
    parser.add_argument("--query", default="")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, help="Retained publication manifest under this repository's artifacts/")
    args = parser.parse_args()
    try:
        identity = sibling_module("bijux_monitor_output_identity", Path(__file__).with_name("build_identity.py"))
        output = identity.artifact(Path.cwd().resolve(), str(args.output))
        result = smoke(args.root, canonical_root=args.canonical_root, deep_path=args.deep_path,
                       asset_path=args.asset_path, query=args.query, timeout=args.timeout, live=args.live, manifest_path=args.manifest)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"passed": result["passed"], "request_budget": result["request_budget"], "output": str(args.output)}))
        return 0 if result["passed"] else 1
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        print(f"documentation monitor rejected: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
