"""Finite ownership, path and data contracts; output cannot grant itself trust."""

from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urljoin
import hashlib
import json
import math
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


def source_inputs(repo, source_sha, inputs):
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
    for item in inputs:
        name = relative(item["path"])
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
