"""Source-owned passive reader navigation for exact frozen report routes."""

from html import escape
from html.parser import HTMLParser
from pathlib import Path
import json
import posixpath
import re
from urllib.parse import quote, urljoin, urlsplit
from .contract import AdmissionError, canonical, digest, json_data, read_owned, relative


BEGIN = "<!-- bijux-owned-reader-navigation -->"
END = "<!-- /bijux-owned-reader-navigation -->"


class MaterialTarget(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.configs = []
        self.active = None
        self.query_controls = 0
        self.feed(content)
        self.close()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "input" and values.get("data-md-component") == "search-query":
            self.query_controls += 1
        if tag == "script" and values.get("id") == "__config":
            if len(values) != len(attrs) or values.get("type") != "application/json":
                raise AdmissionError("reader target has ambiguous native configuration")
            self.active = []
            self.configs.append(self.active)

    def handle_data(self, content):
        if self.active is not None:
            self.active.append(content)

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = None


def _route(base, path):
    if path == "index.html":
        path = ""
    elif path.endswith("/index.html"):
        path = path[:-10]
    return base + path


def _target(site, base, path):
    relative(path)
    content = read_owned(site, path).decode()
    parsed = MaterialTarget(content)
    if len(parsed.configs) != 1 or parsed.query_controls != 1:
        raise AdmissionError(
            "reader documentation target requires one real native configuration"
        )
    config = json_data("".join(parsed.configs[0]))
    if not isinstance(config, dict):
        raise AdmissionError("reader target native configuration must be an object")
    worker = config.get("search")
    if not isinstance(worker, str) or not worker:
        raise AdmissionError(
            "reader documentation target lacks its native search worker"
        )
    target = urlsplit(urljoin(_route(base, path), worker))
    root = urlsplit(base)
    if (
        (target.scheme, target.netloc) != (root.scheme, root.netloc)
        or not target.path.startswith(root.path)
        or target.query
        or target.fragment
    ):
        raise AdmissionError("reader native search worker leaves its product")
    name = target.path[len(root.path) :]
    if not name.endswith(".js") or not read_owned(site, name):
        raise AdmissionError("reader native search worker is missing or empty")
    return digest(content.encode())


def purposes(repo, site, descriptor):
    """Derive only declared report purposes from their tracked finite JSON input."""
    pointer = descriptor.get("reader_purpose")
    if pointer is None:
        return {}
    if not isinstance(pointer, dict) or set(pointer) != {"path", "sha256"}:
        raise AdmissionError("reader purpose requires an exact source input identity")
    content = read_owned(repo, pointer["path"])
    if digest(content) != pointer["sha256"]:
        raise AdmissionError("reader purpose source identity differs")
    body = json_data(content)
    if (
        not isinstance(body, dict)
        or set(body) != {"schema", "readers"}
        or body["schema"] != 1
        or not isinstance(body["readers"], list)
        or not 1 <= len(body["readers"]) <= 512
    ):
        raise AdmissionError("reader purpose requires its finite schema")
    reports = {item["output"] for item in descriptor["reports"]}
    index = json_data(read_owned(site, "search/search_index.json").decode())
    entries = index.get("docs")
    if not isinstance(entries, list) or not entries:
        raise AdmissionError("reader search index is empty or invalid")
    corpus = " ".join(
        str(entry.get("title", "")) + " " + str(entry.get("text", ""))
        for entry in entries
        if isinstance(entry, dict)
    ).casefold()
    result = {}
    for reader in body["readers"]:
        keys = {"output", "title", "purpose", "return_route", "search_route", "query"}
        if (
            not isinstance(reader, dict)
            or set(reader) != keys
            or any(
                not isinstance(value, str)
                or value != value.strip()
                or not value
                or any(ord(c) < 32 for c in value)
                for value in reader.values()
            )
        ):
            raise AdmissionError(
                "reader purpose fields must be exact bounded plain text"
            )
        output = relative(reader["output"])
        if output not in reports or output in result:
            raise AdmissionError(
                "reader purpose selects an undeclared or duplicate report"
            )
        if (
            len(reader["title"]) > 160
            or not 10 <= len(reader["purpose"]) <= 500
            or re.fullmatch(r"[A-Za-z0-9]+(?: [A-Za-z0-9]+){0,7}", reader["query"])
            is None
        ):
            raise AdmissionError(
                "reader purpose title/query/description exceeds finite grammar"
            )
        if any(word.casefold() not in corpus for word in reader["query"].split()):
            raise AdmissionError("reader query has no documented corpus term")
        for key in ("return_route", "search_route"):
            if reader[key] in reports:
                raise AdmissionError("reader purpose must reach ordinary documentation")
            _target(site, descriptor["site_url"], reader[key])
        result[output] = dict(reader)
    return result


def _href(output, destination):
    directory = posixpath.dirname(output) or "."
    if destination == "index.html" or destination.endswith("/index.html"):
        return posixpath.relpath(posixpath.dirname(destination) or ".", directory) + "/"
    return posixpath.relpath(destination, directory)


def marker(output, reader):
    return (
        BEGIN
        + '<nav aria-label="Report documentation"><p>'
        + escape(reader["purpose"])
        + '</p><p><a target="_self" href="'
        + escape(_href(output, reader["return_route"]), quote=True)
        + '">Return to documentation</a> · <a target="_self" href="'
        + escape(
            _href(output, reader["search_route"])
            + "?q="
            + quote(reader["query"], safe=""),
            quote=True,
        )
        + '">Search documentation</a></p></nav>'
        + END
    )


def insert(content, output, reader):
    if reader is None:
        return content
    if content.count("<body>") != 1 or BEGIN in content or END in content:
        raise AdmissionError(
            "reader navigation requires an unambiguous source body boundary"
        )
    return content.replace("<body>", "<body>" + marker(output, reader), 1)


def restore(content, output, reader):
    owned = marker(output, reader)
    if content.count(owned) != 1:
        raise AdmissionError(
            "reader navigation differs from independently owned purpose"
        )
    return content.replace(owned, "", 1)


def sitemap(site, base, reader_routes, *, original=None):
    """Preserve ordinary sitemap entries and add only exact owned reader routes."""
    import base64
    import gzip
    from io import BytesIO
    import xml.etree.ElementTree as ET

    if not reader_routes:
        return None
    raw = read_owned(site, "sitemap.xml") if original is None else original.encode()
    if len(raw) > 16777216 or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise AdmissionError("reader sitemap must be bounded plain XML")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise AdmissionError("reader sitemap is invalid XML") from error
    namespace = root.tag[:-6] if root.tag.endswith("urlset") else None
    if namespace is None or namespace not in (
        "",
        "{http://www.sitemaps.org/schemas/sitemap/0.9}",
    ):
        raise AdmissionError("reader sitemap requires a URL set")
    entries = []
    for entry in root:
        if entry.tag != namespace + "url":
            raise AdmissionError("reader sitemap has an unknown entry")
        locations = [node.text or "" for node in entry if node.tag == namespace + "loc"]
        if len(locations) != 1:
            raise AdmissionError("reader sitemap has an ambiguous location")
        entries.append(locations[0])
    if len(entries) != len(set(entries)):
        raise AdmissionError("reader sitemap has duplicate routes")
    eligible = set()
    for page in sorted(Path(site).rglob("*.html")):
        if page.is_symlink() or not page.is_file() or page.stat().st_nlink != 1:
            raise AdmissionError(
                "reader sitemap route must be a regular owned document"
            )
        name = page.relative_to(site).as_posix()
        if name in reader_routes:
            eligible.add(base + name)
            continue
        document = HTMLParserDocument(page.read_text())
        if name == "404.html" or document.noindex:
            continue
        if len(document.canonicals) != 1:
            raise AdmissionError(
                "reader sitemap ordinary route has ambiguous canonical"
            )
        canonical_url = urljoin(_route(base, name), document.canonicals[0])
        if not document.redirect and canonical_url != _route(base, name):
            raise AdmissionError("reader sitemap ordinary canonical differs")
        if not canonical_url.startswith(base):
            raise AdmissionError("reader sitemap canonical leaves its product")
        eligible.add(canonical_url)
    additions = {base + name for name in reader_routes}
    if set(entries) - eligible or eligible - set(entries) - additions:
        raise AdmissionError(
            "reader sitemap ordinary or foreign route coverage differs"
        )
    for value in sorted(additions - set(entries)):
        entry = ET.SubElement(root, namespace + "url")
        ET.SubElement(entry, namespace + "loc").text = value
    # Stable URL order retains each ordinary entry's additional metadata.
    root[:] = sorted(
        root,
        key=lambda entry: next(
            node.text or "" for node in entry if node.tag == namespace + "loc"
        ),
    )
    output = ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"
    compressed = gzip.compress(output, mtime=0)
    old_compressed = Path(site) / "sitemap.xml.gz"
    old_gzip = read_owned(site, "sitemap.xml.gz") if old_compressed.exists() else None
    if original is None and old_gzip is not None:
        try:
            if (
                len(old_gzip) > 16777216
                or gzip.GzipFile(fileobj=BytesIO(old_gzip)).read(len(raw) + 1) != raw
            ):
                raise AdmissionError("reader sitemap gzip differs from plain sitemap")
        except (OSError, EOFError) as error:
            raise AdmissionError("reader sitemap gzip is invalid") from error
    return {
        "input_xml": raw.decode(),
        "input_sha256": digest(raw),
        "input_gzip_sha256": digest(old_gzip) if old_gzip is not None else None,
        "output_xml": output.decode(),
        "output_sha256": digest(output),
        "output_gzip": base64.b64encode(compressed).decode(),
        "output_gzip_sha256": digest(compressed),
    }


class HTMLParserDocument(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.canonicals = []
        self.noindex = False
        self.redirect = False
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "link" and "canonical" in (values.get("rel") or "").split():
            self.canonicals.append(values.get("href") or "")
        if tag == "meta":
            self.noindex |= (
                values.get("name", "").lower() == "robots"
                and "noindex" in values.get("content", "").lower()
            )
            self.redirect |= values.get("http-equiv", "").lower() == "refresh"


def sitemap_writes(plan, site):
    import base64

    index = plan.get("reader_index")
    writes = []
    if index is not None:
        if (
            digest(read_owned(site, "search/search_index.json"))
            != index["input_sha256"]
        ):
            raise AdmissionError("reader index changed after source preflight")
        writes.append(
            (Path(site) / "search/search_index.json", index["output_json"].encode())
        )
    record = plan.get("reader_sitemap")
    if record is None:
        return writes
    if digest(read_owned(site, "sitemap.xml")) != record["input_sha256"]:
        raise AdmissionError("reader sitemap changed after source preflight")
    compressed = Path(site) / "sitemap.xml.gz"
    if (
        digest(read_owned(site, "sitemap.xml.gz")) if compressed.exists() else None
    ) != record["input_gzip_sha256"]:
        raise AdmissionError("reader sitemap gzip changed after source preflight")
    return [
        *writes,
        (Path(site) / "sitemap.xml", record["output_xml"].encode()),
        (compressed, base64.b64decode(record["output_gzip"], validate=True)),
    ]


def verify_sitemap(plan, site):
    import base64

    record = plan.get("reader_sitemap")
    if record is None:
        return
    expected = sitemap(
        site,
        plan["site_url"],
        set(plan["reader_purposes"]),
        original=record["input_xml"],
    )
    for key in (
        "input_xml",
        "input_sha256",
        "output_xml",
        "output_sha256",
        "output_gzip",
        "output_gzip_sha256",
    ):
        if record[key] != expected[key]:
            raise AdmissionError(
                "reader sitemap differs from independently owned routes"
            )
    if read_owned(site, "sitemap.xml") != expected["output_xml"].encode() or read_owned(
        site, "sitemap.xml.gz"
    ) != base64.b64decode(expected["output_gzip"], validate=True):
        raise AdmissionError(
            "final reader sitemap differs from source-owned normalization"
        )


def search_index(site, readers, *, original=None):
    if not readers:
        return None
    raw = (
        read_owned(site, "search/search_index.json")
        if original is None
        else original.encode()
    )
    if len(raw) > 16777216:
        raise AdmissionError("reader search index exceeds its finite byte budget")
    body = json_data(raw)
    if not isinstance(body, dict) or not isinstance(body.get("docs"), list):
        raise AdmissionError("reader search index is invalid")
    if any(
        not isinstance(entry, dict)
        or not isinstance(entry.get("location"), str)
        or not isinstance(entry.get("title"), str)
        or not entry["title"]
        or not isinstance(entry.get("text"), str)
        for entry in body["docs"]
    ):
        raise AdmissionError("reader search entries require complete native metadata")
    if any(entry["location"].split("#", 1)[0] in readers for entry in body["docs"]):
        raise AdmissionError(
            "raw search index cannot predeclare source-owned reader entries"
        )
    body["docs"] += [
        {"location": name, "title": reader["title"], "text": reader["purpose"]}
        for name, reader in sorted(readers.items())
    ]
    output = canonical(body) + b"\n"
    return {
        "input_json": raw.decode(),
        "input_sha256": digest(raw),
        "output_json": output.decode(),
        "output_sha256": digest(output),
    }


def verify_search_index(plan, site):
    record = plan.get("reader_index")
    if record is None:
        return
    expected = search_index(
        site, plan["reader_purposes"], original=record["input_json"]
    )
    if (
        record != expected
        or read_owned(site, "search/search_index.json")
        != expected["output_json"].encode()
    ):
        raise AdmissionError(
            "final reader index differs from independently owned purpose"
        )
