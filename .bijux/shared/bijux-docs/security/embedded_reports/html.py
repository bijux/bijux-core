"""Reviewed renderer recipes and explicit HTML resource boundaries."""

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
import base64
import math
import re

from .contract import AdmissionError, digest, inspect_data, json_data, read_owned


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.scripts = []
        self.tags = []
        self.current = None
        self.styles = []
        self.current_style = None
        self.feed(source)
        self.close()
        if self.current is not None:
            raise AdmissionError("unclosed script")

    def handle_starttag(self, tag, attrs):
        names = [name for name, _ in attrs]
        if len(set(names)) != len(names):
            raise AdmissionError("duplicate HTML attribute")
        attrs = dict(attrs)
        if any(name.lower().startswith("on") for name in attrs):
            raise AdmissionError("event handler attribute")
        self.tags.append((tag, attrs))
        if tag == "style":
            if self.current_style is not None:
                raise AdmissionError("nested style")
            self.current_style = []
            self.styles.append(self.current_style)
        if tag == "script":
            if self.current is not None:
                raise AdmissionError("nested script")
            self.current = {"attrs": attrs, "body": ""}
            self.scripts.append(self.current)

    def handle_data(self, value):
        if self.current_style is not None:
            self.current_style.append(value)
        if self.current is not None:
            self.current["body"] += value

    def handle_endtag(self, tag):
        if tag == "style":
            self.current_style = None
        if tag == "script":
            self.current = None


def executable_scripts(document):
    return [
        script
        for script in document.scripts
        if not script["attrs"].get("src")
        and script["attrs"].get("type", "")
        not in ("application/json", "application/ld+json")
    ]


def csp_hash(body):
    return "sha256-" + base64.b64encode(bytes.fromhex(digest(body.encode()))).decode()


def reviewed_recipe(repo, body, recipe, product_base, report_path):
    template = Document(read_owned(repo, recipe["template"]).decode())
    scripts = executable_scripts(template)
    if len(scripts) != 1:
        raise AdmissionError("renderer template must have one executable body")
    pattern = scripts[0]["body"]
    for expansion in recipe["expansions"]:
        token = expansion["token"]
        if pattern.count(token) != 1:
            raise AdmissionError("reviewed expansion must occupy one slot")
        content = (
            read_owned(repo, expansion["path"]).decode()
            if expansion.get("path")
            else ""
        )
        pattern = pattern.replace(token, content)
    slots = recipe["slots"]
    if any(not re.fullmatch(r"__[A-Z][A-Z0-9_]+__", token) for token in slots):
        raise AdmissionError("invalid recipe token")
    parts = re.split("(" + "|".join(re.escape(token) for token in slots) + ")", pattern)
    tokens = []
    expressions = []
    for part in parts:
        if part in slots:
            tokens.append(part)
            expressions.append("(.*?)")
        else:
            expressions.append(re.escape(part))
    match = re.fullmatch("".join(expressions), body, re.S)
    if match is None:
        raise AdmissionError("executable body differs from reviewed renderer recipe")
    values = {}
    for token, value in zip(tokens, match.groups()):
        if token in values and values[token] != value:
            raise AdmissionError("inconsistent repeated renderer slot")
        values[token] = value
        policy = slots[token]
        if policy["kind"] == "literal":
            if value not in policy["values"]:
                raise AdmissionError("unreviewed executable expression")
        elif policy["kind"] == "number":
            if not re.fullmatch(r"\d+(?:\.\d+)?", value) or not math.isfinite(
                float(value)
            ):
                raise AdmissionError("unreviewed numeric expression")
            if not 0 <= float(value) <= policy["maximum"]:
                raise AdmissionError("renderer number exceeds budget")
        elif policy["kind"] == "json":
            if any(c in value for c in "<>&\u2028\u2029"):
                raise AdmissionError("script JSON is not safely serialized")
            parsed = json_data(value)
            inspect_data(parsed, product_base, report_path)
        else:
            raise AdmissionError("unknown recipe slot grammar")
    return {
        "recipe_sha256": digest(read_owned(repo, recipe["template"])),
        "parameters_sha256": digest(str(sorted(values.items())).encode()),
        "slot_count": len(tokens),
    }


def report_class(report):
    kind = report.get("report_class", "interactive")
    if kind not in ("interactive", "static-reader"):
        raise AdmissionError("unknown reviewed report class")
    return kind


def report_recipe(repo, document, report, product_base, output):
    if report_class(report) == "static-reader":
        return {"class": "static-reader", "source_sha256": report["source"]["sha256"]}
    return reviewed_recipe(
        repo, executable_scripts(document)[0]["body"], report["recipe"], product_base, output
    )


# This class admits passive notices, not arbitrary CSS or browser resources.
_STATIC_LENGTH = r"(?:0|(?:[0-9]+(?:\.[0-9]+)?)(?:px|rem|em|vh|vw|%))"
_STATIC_NUMBER = r"(?:[0-9]+(?:\.[0-9]+)?)"
_STATIC_COLOR = r"(?:white|black|transparent|\#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?|rgba?\([0-9., ]+\))"
_STATIC_SELECTOR = r"(?:[a-zA-Z][a-zA-Z0-9-]*|[.#][a-zA-Z_][a-zA-Z0-9_-]*)"
_STATIC_VALUES = {
    **{name: _STATIC_LENGTH for name in ("margin-top", "max-width", "min-height", "font-size", "border-radius")},
    **{name: _STATIC_LENGTH + r"(?:\s+" + _STATIC_LENGTH + r"){0,3}" for name in ("margin", "padding")},
    **{name: _STATIC_COLOR for name in ("color", "background", "background-color")},
    "line-height": _STATIC_NUMBER + r"|" + _STATIC_LENGTH,
    "display": r"block|inline|inline-block|grid|flex|none",
    "place-items": r"center|start|end|stretch",
    "font-family": r"(?:ui-sans-serif|system-ui|sans-serif|serif|monospace|ui-monospace)(?:\s*,\s*(?:ui-sans-serif|system-ui|sans-serif|serif|monospace|ui-monospace))*",
    "border": _STATIC_LENGTH + r"\s+(?:solid|dashed|dotted)\s+" + _STATIC_COLOR,
    "box-shadow": _STATIC_LENGTH + r"\s+" + _STATIC_LENGTH + r"\s+" + _STATIC_LENGTH + r"\s+" + _STATIC_COLOR,
}


def static_reader_css(content, *, declarations=False):
    """Admit only finite notice layout/color declarations with no fetch grammar."""
    if any(token in content for token in ("@", "\\", "/*", "*/")):
        raise AdmissionError("static reader CSS is outside its finite grammar")
    if declarations:
        chunks = [content]
    else:
        chunks = []
        remaining = content.strip()
        while remaining:
            match = re.match(r"([^{}]+)\{([^{}]*)\}", remaining)
            if match is None:
                raise AdmissionError("static reader CSS rule is outside its finite grammar")
            selectors = match[1].strip().split(",")
            if any(re.fullmatch(_STATIC_SELECTOR, selector.strip()) is None for selector in selectors):
                raise AdmissionError("static reader CSS selector is outside its finite grammar")
            chunks.append(match[2])
            remaining = remaining[match.end():].strip()
    for chunk in chunks:
        for declaration in chunk.split(";"):
            if not declaration.strip():
                continue
            if declaration.count(":") != 1:
                raise AdmissionError("static reader CSS declaration is outside its finite grammar")
            name, value = (part.strip() for part in declaration.split(":", 1))
            pattern = _STATIC_VALUES.get(name)
            if pattern is None or re.fullmatch(pattern, value) is None:
                raise AdmissionError("static reader CSS property/value is outside its finite grammar")
            for color in re.findall(r"rgba?\([0-9., ]+\)", value):
                components = [component.strip() for component in color[color.index("(")+1:-1].split(",")]
                expected = 4 if color.startswith("rgba") else 3
                if (len(components) != expected
                    or any(re.fullmatch(r"[0-9]{1,3}", c) is None or not 0 <= int(c) <= 255 for c in components[:3])
                    or (expected == 4 and (re.fullmatch(r"(?:0(?:\.[0-9]+)?|1(?:\.0+)?)", components[3]) is None))):
                    raise AdmissionError("static reader CSS color is outside its finite grammar")


def validate_static_reader(document, report):
    expected = {"report_class", "output", "source", "resources", "reviewed_scripts",
                "providers", "reviewed_provider_origins", "provider_calls"}
    if set(report) != expected:
        raise AdmissionError("static reader requires its exact non-executable descriptor")
    if (document.scripts or report["resources"] != {} or report["providers"] != {}
        or report["reviewed_scripts"] != [] or report["reviewed_provider_origins"] != []
        or report["provider_calls"] != []):
        raise AdmissionError("static reader cannot own scripts, resources, bootstrap or providers")
    passive = {"html", "head", "meta", "title", "style", "body", "main", "section", "article",
               "header", "footer", "nav", "aside", "div", "span", "h1", "h2", "h3", "h4", "h5", "h6",
               "p", "a", "br", "hr", "ul", "ol", "li", "dl", "dt", "dd", "strong", "em", "small",
               "code", "pre", "blockquote", "table", "thead", "tbody", "tr", "th", "td", "caption", "link"}
    global_attributes = {"class", "id", "lang", "dir", "title", "role", "aria-label", "aria-labelledby", "style"}
    for tag, attrs in document.tags:
        if tag not in passive:
            raise AdmissionError("static reader has an unsupported active/resource element")
        permitted = global_attributes | ({"href", "target", "rel"} if tag == "a" else set())
        if tag == "meta":
            if attrs == {"charset": "utf-8"}:
                continue
            if attrs == {"name": "viewport", "content": "width=device-width, initial-scale=1"}:
                continue
            raise AdmissionError("static reader has unsupported metadata")
        if tag == "link":
            if attrs == {"rel": "icon", "href": "data:,"}:
                continue
            raise AdmissionError("static reader cannot load a linked resource")
        if set(attrs) - permitted:
            raise AdmissionError("static reader has an unsupported attribute")
        if "style" in attrs:
            static_reader_css(attrs["style"], declarations=True)
        if tag == "a":
            href = attrs.get("href", "")
            if (any(ord(c) < 32 for c in href) or urlsplit(href).scheme not in ("", "http", "https", "mailto", "tel")
                or attrs.get("target", "_self") not in ("_self", "_blank")
                or set(attrs.get("rel", "").split()) - {"noopener", "noreferrer"}):
                raise AdmissionError("static reader has an unsupported navigation attribute")
    if document.current_style is not None:
        raise AdmissionError("static reader has an unclosed style element")
    for style in document.styles:
        static_reader_css("".join(style))


def validate_report(source, report, product_base):
    doc = Document(source)
    if report_class(report) == "static-reader":
        validate_static_reader(doc, report)
    local = set(report["resources"])
    for tag, attrs in doc.tags:
        if tag in ("base", "iframe", "object", "embed", "form"):
            raise AdmissionError("unreviewed active HTML element")
        if tag == "meta" and attrs.get("http-equiv"):
            raise AdmissionError("source must not own CSP or refresh")
        if tag in ("script", "link", "img", "video", "audio", "source"):
            value = attrs.get("src", attrs.get("href"))
            if not value:
                continue
            if tag == "link" and attrs.get("rel") == "icon" and value == "data:,":
                continue
            target = urlsplit(urljoin(product_base + report["output"], value))
            base = urlsplit(product_base)
            path = (
                target.path[len(base.path) :]
                if target.path.startswith(base.path)
                else ""
            )
            if (
                target.netloc != base.netloc
                or target.query
                or target.fragment
                or path not in local
            ):
                raise AdmissionError("unowned report resource: " + value)
        if tag == "script" and attrs.get("type", "") not in ("", "application/json"):
            raise AdmissionError("unreviewed script kind")
    bodies = executable_scripts(doc)
    if [digest(s["body"].encode()) for s in bodies] != report["reviewed_scripts"]:
        raise AdmissionError("executable source is not the owner-reviewed body")
    return doc


def parent_iframe(source, output, expected, product_base):
    doc = Document(source)
    frames = [attrs for tag, attrs in doc.tags if tag == "iframe"]
    found = []
    for attrs in frames:
        if set(attrs) - {"src", "title", "class", "loading", "width", "height"}:
            raise AdmissionError("unreviewed iframe attribute or capability")
        target = urljoin(product_base + output, attrs.get("src", ""))
        if target not in expected:
            raise AdmissionError("foreign or undeclared parent iframe")
        found.append(target)
    if sorted(found) != sorted(expected):
        raise AdmissionError("declared iframe is missing or duplicated")
    return found
