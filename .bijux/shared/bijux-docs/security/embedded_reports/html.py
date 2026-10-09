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
        if tag == "script":
            if self.current is not None:
                raise AdmissionError("nested script")
            self.current = {"attrs": attrs, "body": ""}
            self.scripts.append(self.current)

    def handle_data(self, value):
        if self.current is not None:
            self.current["body"] += value

    def handle_endtag(self, tag):
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


def validate_report(source, report, product_base):
    doc = Document(source)
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
