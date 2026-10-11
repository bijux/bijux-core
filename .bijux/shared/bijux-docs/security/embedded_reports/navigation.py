"""Preserve full-document navigation across source-owned CSP partitions."""

from html import escape
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit, unquote
from .contract import AdmissionError, canonical, digest


def partitions(records):
    return {
        record["path"]: digest(canonical(record["capability"])) for record in records
    }


def metadata(path, base, ownership):
    routes = [path, *ownership]
    if any(
        not isinstance(route, str)
        or not route.endswith(".html")
        or route.startswith("/")
        or re.search(r"[\x00-\x20\x7f%?#\\]", route)
        or any(part in {"", ".", ".."} for part in route.split("/"))
        for route in routes
    ):
        raise AdmissionError(
            "Capability metadata requires unambiguous public HTML routes"
        )
    if any(
        not re.fullmatch(r"[a-f0-9]{64}", partition) for partition in ownership.values()
    ):
        raise AdmissionError(
            "Capability metadata requires source-derived partition digests"
        )
    table = sorted([[route, partition] for route, partition in ownership.items()])
    if len(table) > 2048:
        raise AdmissionError("Capability metadata route budget exceeded")
    return {
        "schema": 1,
        "site_url": base,
        "document_route": path,
        "document_partition": ownership.get(path, "ordinary"),
        "route_partitions": table,
        "table_sha256": digest(canonical(table)),
    }


def meta_marker(payload):
    return (
        '\n<meta name="bijux-csp-navigation" content="'
        + escape(canonical(payload).decode(), quote=True)
        + '">'
    )


def normalize(content, path, base, ownership):
    current = ownership.get(path, "ordinary")
    lines = [0]
    for index, char in enumerate(content):
        if char == "\n":
            lines.append(index + 1)
    changes = []
    preexisting = []
    root = urlsplit(base)

    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "meta" and dict(attrs).get("name") == "bijux-csp-navigation":
                preexisting.append(True)
            if tag != "a":
                return
            values = dict(attrs)
            if len(values) != len(attrs):
                raise AdmissionError(
                    "Ambiguous anchor attributes at CSP partition boundary"
                )
            href = values.get("href")
            if not href or values.get("target"):
                return
            target = urlsplit(urljoin(base + path, href))
            if (target.scheme, target.netloc) != (
                root.scheme,
                root.netloc,
            ) or not target.path.startswith(root.path):
                return
            name = unquote(target.path[len(root.path) :])
            if "\\" in name or any(part in {".", ".."} for part in name.split("/")):
                raise AdmissionError("Ambiguous capability navigation route")
            name = name + "index.html" if not name or name.endswith("/") else name
            destination = ownership.get(name, "ordinary")
            if current == destination:
                return
            start = lines[self.getpos()[0] - 1] + self.getpos()[1]
            original = self.get_starttag_text()
            # Material 9.7.7 handle() excludes any truthy target. _self keeps
            # native same-window, keyboard, history and no-script navigation.
            if "target" in values:
                raise AdmissionError(
                    "Empty target attribute must be reviewed before normalization"
                )
            replacement = original[:-1] + ' target="_self">'
            changes.append(
                {
                    "offset": start,
                    "original": original,
                    "replacement": replacement,
                    "destination": name,
                    "source_partition": current,
                    "destination_partition": destination,
                }
            )

    parser = Links(convert_charrefs=True)
    parser.feed(content)
    if preexisting:
        raise AdmissionError("Source cannot predeclare owned CSP navigation metadata")
    result = content
    for change in reversed(changes):
        start = change["offset"]
        result = (
            result[:start]
            + change["replacement"]
            + result[start + len(change["original"]) :]
        )
    payload = None
    if 'id="__config"' in content:
        payload = metadata(path, base, ownership)
        charset = re.search(
            r'<meta\s+charset=["\']?utf-8["\']?\s*/?>', result, flags=re.I
        )
        if not charset:
            raise AdmissionError(
                "Capability metadata requires the actual UTF-8 head boundary"
            )
        if len(canonical(payload)) > 262144:
            raise AdmissionError("Capability metadata byte budget exceeded")
        result = (
            result[: charset.end()] + meta_marker(payload) + result[charset.end() :]
        )
    return {
        "metadata": payload,
        "path": path,
        "input_sha256": digest(content.encode()),
        "normalized_sha256": digest(result.encode()),
        "changes": changes,
        "normalized_html": result,
    }


def restore(content, record, base, ownership):
    if digest(content.encode()) != record["normalized_sha256"]:
        raise AdmissionError("Normalized capability anchor output differs")
    result = content
    if record.get("metadata") is not None:
        expected = metadata(record["path"], base, ownership)
        marker = meta_marker(expected)
        if record["metadata"] != expected or result.count(marker) != 1:
            raise AdmissionError(
                "Capability navigation metadata differs from verified source partitions"
            )
        result = result.replace(marker, "", 1)
    shift = sum(len(c["replacement"]) - len(c["original"]) for c in record["changes"])
    for change in reversed(record["changes"]):
        shift -= len(change["replacement"]) - len(change["original"])
        start = change["offset"] + shift
        if result[start : start + len(change["replacement"])] != change["replacement"]:
            raise AdmissionError("Capability link position/content differs")
        result = (
            result[:start]
            + change["original"]
            + result[start + len(change["replacement"]) :]
        )
    expected = normalize(result, record["path"], base, ownership)
    if {
        k: v for k, v in expected.items() if k != "normalized_html"
    } != record or digest(result.encode()) != record["input_sha256"]:
        raise AdmissionError(
            "Capability link normalization lacks exact route-derived attribution"
        )
    return result
