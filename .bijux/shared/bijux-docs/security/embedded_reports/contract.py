"""Finite ownership, path and data contracts; output cannot grant itself trust."""

from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urljoin
import hashlib
import json
import math
import os
import re
import subprocess


class AdmissionError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def relative(value):
    if not isinstance(value, str) or not value or value != str(PurePosixPath(value)):
        raise AdmissionError("noncanonical owned path")
    if value.startswith("/") or any(p in ("", ".", "..") for p in value.split("/")):
        raise AdmissionError("owned path escapes its root")
    if "\\" in value or "%" in value or any(ord(c) < 32 for c in value):
        raise AdmissionError("ambiguous owned path")
    return value


def public_route(base, path):
    """Identify terminal index documents by their public directory route."""
    path = relative(path)
    if path == "index.html":
        path = ""
    elif path.endswith("/index.html"):
        path = path[:-10]
    return site_url(base) + path


def read_owned(root, name):
    name = relative(name)
    root = Path(root).resolve()
    current = root
    for component in name.split("/"):
        current = current / component
        if current.is_symlink():
            raise AdmissionError("symlink in owned input: " + name)
    if not current.is_file() or not current.resolve().is_relative_to(root):
        raise AdmissionError("missing regular owned input: " + name)
    return current.read_bytes()


def site_url(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise AdmissionError("production site URL must be HTTPS without credentials")
    if (
        parsed.query
        or parsed.fragment
        or not parsed.path.endswith("/")
        or "%" in parsed.path
    ):
        raise AdmissionError("production site URL must have a canonical base path")
    if any(p in (".", "..") for p in parsed.path.split("/")):
        raise AdmissionError("production URL contains path traversal")
    return value


def data_url(value, base):
    if not isinstance(value, str) or not value or value != value.strip():
        raise AdmissionError("invalid data URL")
    if "\\" in value or any(ord(c) < 32 for c in value):
        raise AdmissionError("ambiguous data URL")
    parsed = urlsplit(value)
    if parsed.scheme:
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise AdmissionError("unsafe data URL protocol or authority")
        return value
    if value.startswith("//") or "%" in value:
        raise AdmissionError("ambiguous relative data URL")
    target = urlsplit(urljoin(base, value))
    root = urlsplit(base)
    # The caller supplies the product base, not an individual report directory.
    if target.netloc != root.netloc or not target.path.startswith(root.path):
        raise AdmissionError("relative data URL leaves its product")
    return value


def inspect_data(value, product_base, report_path, depth=0):
    if depth > 80:
        raise AdmissionError("data nesting budget exceeded")
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                isinstance(item, str)
                and item
                and (
                    key in ("url", "href", "method_doi", "dataset_doi")
                    or key.endswith("_url")
                )
            ):
                if (
                    item != item.strip()
                    or "\\" in item
                    or any(ord(c) < 32 for c in item)
                ):
                    raise AdmissionError("ambiguous dataset URL")
                if urlsplit(item).scheme:
                    data_url(item, product_base)
                else:
                    resolved = urljoin(urljoin(product_base, report_path), item)
                    parsed = urlsplit(resolved)
                    root = urlsplit(product_base)
                    if parsed.netloc != root.netloc or not parsed.path.startswith(
                        root.path
                    ):
                        raise AdmissionError("relative data URL leaves its product")
                    data_url(resolved, product_base)
            inspect_data(item, product_base, report_path, depth + 1)
    elif isinstance(value, list):
        for item in value:
            inspect_data(item, product_base, report_path, depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise AdmissionError("nonfinite JSON data")


def json_data(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise AdmissionError("duplicate JSON member")
            result[key] = item
        return result

    try:
        return json.loads(
            value,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                AdmissionError("nonfinite JSON")
            ),
        )
    except (ValueError, UnicodeError, RecursionError) as error:
        raise AdmissionError("invalid bounded JSON: " + str(error)) from error


def retained_templates(descriptor):
    """Limit historical Git authority to explicit interactive recipe templates."""
    if descriptor is None:
        return {}
    producers = descriptor["producer_inputs"]
    templates = {
        report["recipe"]["template"]
        for report in descriptor["reports"]
        if report.get("report_class") == "interactive"
    }
    ordinary = {descriptor["config"]["path"]}
    if descriptor.get("reader_purpose") is not None:
        ordinary.add(descriptor["reader_purpose"]["path"])
    for report in descriptor["reports"]:
        ordinary.add(report["source"]["path"])
        ordinary.update(row["source"] for row in report["resources"].values())
        ordinary.update(
            row["path"] for row in report.get("recipe", {}).get("expansions", [])
            if row.get("path") is not None
        )
    ordinary.update(row["source"]["path"] for row in descriptor["parents"])
    retained = {}
    for pointer in producers:
        if "storage" not in pointer:
            continue
        name = relative(pointer["path"])
        if sum(row["path"] == name for row in producers) != 1:
            raise AdmissionError("duplicate producer source authority for retained template")
        if (set(pointer) != {"path", "sha256", "storage"}
            or name not in templates or name in ordinary):
            raise AdmissionError("retained template requires sole recipe-only producer authority")
        storage = pointer["storage"]
        if (not isinstance(storage, dict)
            or set(storage) != {"role", "commit", "blob", "bytes"}
            or storage["role"] != "retained-template"
            or type(storage["bytes"]) is not int
            or not 1 <= storage["bytes"] <= 2 * 1024**2
            or not isinstance(pointer["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", pointer["sha256"]) is None
            or any(not isinstance(storage[key], str)
                   or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", storage[key]) is None
                   for key in ("commit", "blob"))):
            raise AdmissionError("retained template requires exact bounded Git identity")
        retained[name] = pointer
    return retained


def _retained_template(repo, source_sha, pointer):
    """Read one reachable ordinary historical blob, never a filesystem fallback."""
    if (not isinstance(source_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", source_sha) is None):
        raise AdmissionError("retained template requires selected source commit")
    repo = Path(repo)
    environment = {
        "PATH": os.defpath, "LANG": "C", "LC_ALL": "C",
        "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }

    def git(*arguments):
        try:
            return subprocess.run(
                ["git", "--no-replace-objects", "--no-optional-locks", "-C", str(repo), *arguments],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=10, env=environment,
            ).stdout
        except (OSError, subprocess.SubprocessError) as error:
            raise AdmissionError("retained template Git custody differs") from error

    git_dir = Path(git("rev-parse", "--absolute-git-dir").decode().strip())
    if (git_dir / "info/grafts").exists():
        raise AdmissionError("retained template refuses grafted history")
    storage = pointer["storage"]
    for revision in (source_sha, storage["commit"]):
        if git("cat-file", "-t", revision) != b"commit\n":
            raise AdmissionError("retained template revision must be a commit")
    git("merge-base", "--is-ancestor", storage["commit"], source_sha)
    entries = git("ls-tree", "-rz", storage["commit"], "--", pointer["path"]).split(b"\0")
    expected = pointer["path"].encode()
    if len(entries) != 2 or entries[-1] != b"":
        raise AdmissionError("retained template historical path differs")
    metadata, _, name = entries[0].partition(b"\t")
    if name != expected or metadata.decode().split() not in [
        ["100644", "blob", storage["blob"]], ["100755", "blob", storage["blob"]]
    ]:
        raise AdmissionError("retained template must be the declared ordinary blob")
    if git("cat-file", "-s", storage["blob"]) != str(storage["bytes"]).encode() + b"\n":
        raise AdmissionError("retained template byte count differs")
    content = git("cat-file", "blob", storage["blob"])
    algorithm = "sha256" if len(storage["blob"]) == 64 else "sha1"
    actual_blob = hashlib.new(
        algorithm, b"blob " + str(len(content)).encode() + b"\0" + content
    ).hexdigest()
    if (len(content) != storage["bytes"] or digest(content) != pointer["sha256"]
        or actual_blob != storage["blob"]):
        raise AdmissionError("retained template bytes differ from declared identity")
    return content


def recipe_template(repo, name, *, source_sha=None, descriptor=None):
    """Select declared historical storage explicitly; ordinary recipes stay physical."""
    retained = retained_templates(descriptor)
    if name in retained:
        return _retained_template(repo, source_sha, retained[name])
    return read_owned(repo, name)


def source_inputs(repo, source_sha, inputs, *, descriptor=None):
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", source_sha):
        raise AdmissionError("source identity must be an exact commit")
    command = ["git", "-C", str(repo), "ls-tree", "-rz", source_sha]
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout
    objects = {}
    for entry in result.split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, kind, object_id = metadata.decode().split()
        objects[name.decode()] = (mode, kind, object_id)
    algorithm = "sha256" if len(source_sha) == 64 else "sha1"
    checked = []
    retained = retained_templates(descriptor)
    for item in inputs:
        name = relative(item["path"])
        if "storage" in item:
            if (name not in retained or item["storage"] != retained[name]["storage"]
                or item["sha256"] != retained[name]["sha256"]):
                raise AdmissionError("retained input is not an owned interactive template")
            content = _retained_template(repo, source_sha, retained[name])
            checked.append({"path": name, "sha256": digest(content),
                            "git_blob": retained[name]["storage"]["blob"],
                            "storage": dict(retained[name]["storage"])})
            continue
        if name in retained:
            raise AdmissionError("retained template storage authority was omitted")
        content = read_owned(repo, name)
        if digest(content) != item["sha256"]:
            raise AdmissionError("reviewed source fingerprint differs: " + name)
        blob = hashlib.new(
            algorithm, b"blob " + str(len(content)).encode() + b"\0" + content
        ).hexdigest()
        actual = objects.get(name)
        if (
            actual is None
            or actual[0] not in ("100644", "100755")
            or actual[1:] != ("blob", blob)
        ):
            raise AdmissionError(
                "source is untracked or differs from selected commit: " + name
            )
        checked.append({"path": name, "sha256": digest(content), "git_blob": blob})
    return sorted(checked, key=lambda item: item["path"])


def bundle_identity(site):
    items = []
    for path in sorted(Path(site).rglob("*")):
        if path.is_symlink():
            raise AdmissionError("bundle contains symlink")
        if path.is_file():
            if path.stat().st_nlink != 1:
                raise AdmissionError("bundle contains hardlinked input")
            name = relative(path.relative_to(site).as_posix())
            data = path.read_bytes()
            items.append({"path": name, "bytes": len(data), "sha256": digest(data)})
    return items, digest(canonical(items))
