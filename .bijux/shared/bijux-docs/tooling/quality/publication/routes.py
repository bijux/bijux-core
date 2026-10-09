"""Build a deterministic route inventory and resolve links against its artifact."""
from __future__ import annotations
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import quote, unquote, urljoin, urlsplit
import xml.etree.ElementTree as ET
from validate_production_url import development_host


class Document(HTMLParser):
    def __init__(self, path: Path, url: str):
        super().__init__(convert_charrefs=True)
        self.path, self.url = path, url
        self.ids: list[str] = []
        self.references: list[tuple[str, str]] = []
        self.canonicals: list[str] = []
        self.noindex = False
        self.redirect = False
        self.config = ''
        self._config = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get('id'):
            self.ids.append(values['id'])
        if tag == 'a' and values.get('name') and values.get('name') != values.get('id'):
            self.ids.append(values['name'])
        if tag == 'link' and 'canonical' in (values.get('rel') or '').split():
            self.canonicals.append(values.get('href') or '')
        elif tag in {'a', 'area', 'link'} and values.get('href'):
            self.references.append(('link' if tag in {'a','area'} else 'asset', values['href']))
        for key in ('src', 'poster', 'action', 'formaction'):
            if values.get(key):
                self.references.append(('asset', values[key]))
        if tag == 'meta':
            self.noindex |= values.get('name','').lower() == 'robots' and 'noindex' in values.get('content','').lower()
            self.redirect |= values.get('http-equiv','').lower() == 'refresh'
        if tag == 'script' and values.get('id') == '__config':
            self._config = True

    def handle_endtag(self, tag):
        if tag == 'script':
            self._config = False

    def handle_data(self, data):
        if self._config:
            self.config += data


def route_url(site_url: str, relative: str) -> str:
    if relative == 'index.html':
        relative = ''
    elif relative.endswith('/index.html'):
        relative = relative[:-len('index.html')]
    return urljoin(site_url, quote(relative,safe="/"))


def inventory(site: Path, site_url: str) -> dict[Path, Document]:
    result = {}
    for path in sorted(site.rglob('*.html')):
        if path.is_symlink():
            raise ValueError(f'Symlink route is not admitted: {path.relative_to(site)}')
        doc = Document(path, route_url(site_url, path.relative_to(site).as_posix()))
        doc.feed(path.read_text(encoding='utf-8'))
        result[path.resolve()] = doc
    if not result or (site/'index.html').resolve() not in result:
        raise ValueError('Selected artifact must contain at least its root index.html')
    return result


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


def validate(site: Path, site_url: str, docs: dict[Path, Document], network_urls: list[str],
             exceptions: list[dict] | None = None,
             observations: list[dict] | None = None) -> list[str]:
    errors = []
    exceptions = exceptions or []
    observations = observations if observations is not None else []
    canonical_routes = set()
    for path, doc in docs.items():
        label = path.relative_to(site).as_posix()
        duplicate = [key for key, count in Counter(doc.ids).items() if count > 1]
        if duplicate:
            errors.append(f'{label}: duplicate document IDs: {", ".join(sorted(duplicate))}')
        if path.name != '404.html':
            # Redirect producers may identify their destination relative to this route.
            canonical = urljoin(doc.url, doc.canonicals[0]) if len(doc.canonicals) == 1 else None
            if len(doc.canonicals) != 1 or (not doc.redirect and doc.canonicals[0] != doc.url):
                errors.append(f'{label}: canonical must identify this production route ({doc.url})')
            elif not doc.noindex:
                canonical_routes.add(canonical)
            if doc.redirect and doc.canonicals:
                target, _ = resolve(site,site_url,doc.url,doc.canonicals[0])
                if target not in docs or canonical != docs[target].url:
                    errors.append(f'{label}: redirect canonical does not reach a built route')
        for kind, value in doc.references:
            failure = validate_reference(value,doc.url,kind,label,exceptions,observations)
            if failure:
                errors.append(f'{label}: {failure}')
                continue
            if is_network_boundary(site_url,urljoin(doc.url,value),network_urls):
                continue
            try:
                target, fragment = resolve(site,site_url,doc.url,value)
            except ValueError as exc:
                errors.append(f'{label}: {exc}')
                continue
            if target is None:
                continue
            if not target.is_file():
                errors.append(f'{label}: missing {kind} destination {value}')
            elif kind == 'link' and fragment and target in docs and fragment not in docs[target].ids:
                errors.append(f'{label}: missing anchor {value}')
    for path in sorted(site.rglob('*.css')):
        css = path.read_text(encoding='utf-8')
        values = re.findall(r'url\(\s*[\'"]?([^\'"\)\s]+)',css)
        values += re.findall(r'@import\s+[\'"]([^\'"]+)',css)
        for value in values:
            failure = validate_reference(value,urljoin(site_url,path.relative_to(site).as_posix()),'asset',path.relative_to(site).as_posix(),exceptions,observations)
            if failure:
                errors.append(f'{path.relative_to(site)}: {failure}')
                continue
            target, _ = resolve(site,site_url,urljoin(site_url,path.relative_to(site).as_posix()),value)
            if target is not None and not target.is_file():
                errors.append(f'{path.relative_to(site)}: missing CSS asset {value}')
    sitemap = site/'sitemap.xml'
    if not sitemap.is_file():
        errors.append('Selected artifact is missing sitemap.xml')
    else:
        try:
            urls = [node.text or '' for node in ET.parse(sitemap).iter() if node.tag.rsplit('}',1)[-1] == 'loc']
            if len(urls) != len(set(urls)):
                errors.append('sitemap.xml: duplicate route entries')
            unknown = set(urls)-canonical_routes
            missing = canonical_routes-set(urls)
            if unknown:
                errors.append('sitemap.xml: noncanonical/nonproduction/excluded routes: '+', '.join(sorted(unknown)))
            if missing:
                errors.append('sitemap.xml: missing eligible canonical routes: '+', '.join(sorted(missing)))
        except ET.ParseError:
            errors.append('sitemap.xml: invalid XML')
    compressed = site/'sitemap.xml.gz'
    if compressed.exists():
        import gzip
        from io import BytesIO
        try:
            plain = sitemap.read_bytes()
            if compressed.is_symlink() or gzip.GzipFile(fileobj=BytesIO(compressed.read_bytes())).read(len(plain)+1) != plain:
                errors.append('sitemap.xml.gz: content differs from the plain sitemap')
        except (OSError,EOFError):
            errors.append('sitemap.xml.gz: invalid compressed sitemap')
    return errors


def records(site: Path, docs: dict[Path, Document]) -> list[dict]:
    return [dict(path=path.relative_to(site).as_posix(), url=doc.url,
                 canonical=doc.canonicals, noindex=doc.noindex, redirect=doc.redirect,
                 anchors=len(set(doc.ids)), references=len(doc.references))
            for path,doc in docs.items()]
