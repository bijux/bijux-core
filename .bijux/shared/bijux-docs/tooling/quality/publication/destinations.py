"""Bind public references to production origins and selected artifact boundaries."""
from __future__ import annotations
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit
from validate_production_url import development_host


def route_url(site_url: str, relative: str) -> str:
    if relative == 'index.html':
        relative = ''
    elif relative.endswith('/index.html'):
        relative = relative[:-len('index.html')]
    return urljoin(site_url, quote(relative,safe="/"))


def resolve(site: Path, site_url: str, current: str, value: str) -> tuple[Path | None, str]:
    url = urlsplit(urljoin(current, value))
    base = urlsplit(site_url)
    if url.scheme not in {'http','https'} or url.netloc != base.netloc:
        return None, ''
    if not url.path.startswith(base.path):
        return None, ''
    relative = unquote(url.path[len(base.path):])
    target = (site/relative).resolve()
    if not target.is_relative_to(site.resolve()):
        raise ValueError('Local reference escapes the selected artifact')
    if target.is_dir() or url.path.endswith('/'):
        target /= 'index.html'
    return target, unquote(url.fragment)


def is_network_boundary(site_url: str, target: str, network_urls: list[str]) -> bool:
    absolute = urljoin(site_url, target)
    # Another product's publication is outside this artifact, even on the same origin.
    return any(root != site_url and absolute.startswith(root) and len(urlsplit(root).path) > len(urlsplit(site_url).path)
               for root in network_urls)


def validate_reference(value: str, current: str, kind: str, label: str,
                       exceptions: list[dict], observations: list[dict]) -> str | None:
    if any(c in value for c in ('{', '}', '\\')) or any(ord(c) < 32 for c in value):
        return 'malformed/unrendered public URL ' + value
    try:
        parsed = urlsplit(urljoin(current, value))
        hostname = parsed.hostname or ''
        if parsed.scheme not in {'http', 'https'}:
            return None
        if not hostname or parsed.username is not None or parsed.password is not None:
            return 'public URL cannot contain credentials or a missing hostname'
        if '%' in hostname:
            return 'malformed public URL hostname ' + value
        _ = parsed.port
        if development_host(hostname):
            allowed = kind == 'link' and next((item for item in exceptions
                       if item['route'] == label and item['url'] == value), None)
            observations.append(dict(route=label,url=value,kind=kind,
                                     classification='development-origin',exempted=bool(allowed),
                                     purpose=allowed['purpose'] if allowed else None))
            if not allowed:
                return 'development/private host in public ' + kind + ' URL ' + value
        elif kind == 'asset' and parsed.scheme == 'http':
            return 'insecure active resource URL ' + value
    except ValueError:
        return 'malformed public URL ' + value
    return None
