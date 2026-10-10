#!/usr/bin/env python3
"""Account for source-bound serialized navigation without transport inference."""
from __future__ import annotations

import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit

import yaml

try:
    from . import payloads
except ImportError:
    import payloads

VOID = frozenset('area base br col embed hr img input link meta param source track wbr'.split())


class Regions(HTMLParser):
    """Convert parser character positions into exact UTF-8 source byte spans."""
    def __init__(self, raw: bytes):
        super().__init__(convert_charrefs=True)
        self.raw = raw
        self.text = raw.decode('utf-8')
        self.lines = self.text.split('\n')
        self.line_bytes, total = [], 0
        for line in self.lines:
            self.line_bytes.append(total)
            total += len(line.encode('utf-8')) + 1
        self.stack, self.regions, self.ids = [], {}, Counter()
        self.feed(self.text)
        self.close()
        if self.stack:
            raise ValueError('Unclosed HTML cannot provide exact region ownership')
        for name in ('header', 'primary-navigation'):
            if name not in self.regions:
                raise ValueError('Missing required navigation landmark: ' + name)
        if any(count > 1 for count in self.ids.values()):
            raise ValueError('Duplicate document ID makes navigation ownership ambiguous')

    def byte_offset(self):
        line, column = self.getpos()
        return self.line_bytes[line - 1] + len(self.lines[line - 1][:column].encode('utf-8'))

    def handle_starttag(self, tag, attrs):
        if len(dict(attrs)) != len(attrs):
            raise ValueError('Duplicate HTML attributes cannot identify exact regions')
        values = dict(attrs)
        if values.get('id'):
            self.ids[values['id']] += 1
        classes = (values.get('class') or '').split()
        role = None
        if tag == 'header' and values.get('data-md-component') == 'header': role = 'header'
        if tag == 'nav' and values.get('data-md-component') == 'tabs': role = 'tabs'
        if values.get('id') == 'bijux-navigation':
            if tag != 'nav' or values.get('data-bijux-nav-variant') != 'complete' or not values.get('aria-label'):
                raise ValueError('Primary navigation requires its exact complete named landmark')
            role = 'primary-navigation'
        if tag == 'nav' and 'md-nav--secondary' in classes: role = 'local-toc'
        if tag == 'footer' and 'md-footer' in classes: role = 'footer'
        contained_role = None
        if role == 'tabs' and any(frame['role'] == 'header' for frame in self.stack):
            # Canonical site tabs belong to their enclosing header's serialized bytes.
            contained_role, role = role, None
        if role:
            if role in self.regions or any(frame['role'] == role for frame in self.stack):
                raise ValueError('Duplicate navigation landmark: ' + role)
            if any(frame['role'] for frame in self.stack):
                raise ValueError('Nested owned navigation regions would double-count serialized bytes')
            if role in ('tabs', 'local-toc') and not values.get('aria-label'):
                raise ValueError('Navigation landmark requires a name: ' + role)
        if tag == 'a' and values.get('href'):
            for frame in reversed(self.stack):
                if frame['role']:
                    frame['links'].append(values['href'])
                    break
        if tag not in VOID:
            self.stack.append({'tag': tag, 'role': role, 'start': self.byte_offset(), 'links': [], 'contained_role': contained_role, 'contained_landmarks': []})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self._end(tag, self.byte_offset() + len(self.get_starttag_text().encode('utf-8')))

    def _end(self, tag, end):
        if not self.stack or self.stack[-1]['tag'] != tag:
            raise ValueError('Malformed nesting cannot provide exact region ownership: ' + tag)
        frame = self.stack.pop()
        if frame['contained_role']:
            owner = next(item for item in reversed(self.stack) if item['role'])
            owner['contained_landmarks'].append({'role': frame['contained_role'], 'start_byte': frame['start'],
                'end_byte': end, 'accounted_by': owner['role']})
        if frame['role']:
            start = frame['start']
            self.regions[frame['role']] = {'start_byte': start, 'end_byte': end,
                **payloads.fingerprint(self.raw[start:end]), 'links': frame['links'], 'contained_landmarks': frame['contained_landmarks']}

    def handle_endtag(self, tag):
        start = self.byte_offset()
        end = self.raw.find(b'>', start)
        if end < 0:
            raise ValueError('Unterminated closing tag')
        self._end(tag, end + 1)


def config_data(raw: bytes) -> dict:
    class UniqueLoader(yaml.SafeLoader):
        pass
    def mapping(loader, node, deep=False):
        result = {}
        for key, value in node.value:
            name = loader.construct_object(key, deep=deep)
            if name in result:
                raise ValueError('Duplicate configuration field: ' + str(name))
            result[name] = loader.construct_object(value, deep=deep)
        return result
    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    # Material's configured function names are metadata here, never imported or invoked.
    def function_name(loader, suffix, node):
        if not suffix or not isinstance(node, yaml.ScalarNode):
            raise ValueError('Configured function name must remain inert scalar metadata')
        return {'configured_function_name': suffix, 'value': loader.construct_scalar(node)}
    UniqueLoader.add_multi_constructor('tag:yaml.org,2002:python/name:', function_name)
    value = yaml.load(raw, Loader=UniqueLoader)
    if not isinstance(value, dict):
        raise ValueError('Selected configuration requires an object')
    base = urlsplit(value.get('site_url', ''))
    if base.scheme not in ('http', 'https') or not base.netloc or base.username or base.password or base.query or base.fragment or not base.path.endswith('/'):
        raise ValueError('Configured site_url requires an exact HTTP(S) publication root')
    if type(value.get('use_directory_urls', True)) is not bool:
        raise ValueError('Directory route configuration must be boolean')
    return value


def route_url(base: str, name: str) -> str:
    if name == 'index.html': name = ''
    elif name.endswith('/index.html'): name = name[:-len('index.html')]
    return urljoin(base, quote(name, safe='/'))


def destination(base: str, current: str, href: str) -> tuple[str, str]:
    if '\\' in href or any(ord(c) < 32 for c in href):
        raise ValueError('Malformed navigation destination')
    target = urlsplit(urljoin(current, href))
    root = urlsplit(base)
    if target.scheme not in ('http', 'https'):
        raise ValueError('Navigation destination requires HTTP(S)')
    if target.username or target.password:
        raise ValueError('Navigation destination cannot contain credentials')
    if target.netloc != root.netloc or not target.path.startswith(root.path):
        return 'external', target.geturl()
    relative = unquote(target.path[len(root.path):])
    if '\\' in relative or any(part in ('.', '..') for part in relative.split('/')):
        raise ValueError('Navigation destination escapes the owned route root')
    name = relative + 'index.html' if not relative or relative.endswith('/') else relative
    payloads.relative_path(name)
    return 'internal', name


def authored_routes(config: dict) -> set[str]:
    result = set()
    def visit(value):
        if isinstance(value, dict):
            for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
        elif isinstance(value, str):
            if urlsplit(value).scheme or value.startswith('//'): return
            path = payloads.relative_path(value).as_posix()
            if not path.endswith('.md'):
                raise ValueError('Authored local navigation requires a Markdown source route')
            stem = path[:-3]
            if config.get('use_directory_urls', True):
                route = stem + '.html' if stem == 'index' or stem.endswith('/index') else stem + '/index.html'
            else: route = stem + '.html'
            result.add(route)
        else:
            raise ValueError('Authored navigation requires finite mappings, lists and destinations')
    if 'nav' not in config:
        raise ValueError('Selected configuration must declare authored navigation')
    visit(config['nav'])
    return result


def qualify(repo: Path, site: Path, config_path: Path, manifest_path: Path, standard: Path, sha: str) -> dict:
    repo, standard = repo.resolve(), standard.resolve()
    for path in (site, config_path, manifest_path):
        if not path.absolute().is_relative_to(repo / 'artifacts') or not path.resolve().is_relative_to(repo / 'artifacts'):
            raise ValueError('Measurement inputs must remain in owning artifacts/')
    owned_site = repo
    for part in site.relative_to(repo).parts:
        owned_site = owned_site / part
        if owned_site.is_symlink():
            raise ValueError('Served directory cannot use a symlink')
    site = site.resolve()
    identity = payloads.source_identity(standard, sha)
    manifest_bytes = payloads.regular_file(repo, manifest_path.relative_to(repo).as_posix()).read_bytes()
    manifest = payloads.unique_json(manifest_bytes)
    if type(manifest.get('schema')) is not int or manifest['schema'] != 1 or manifest.get('source') != identity:
        raise ValueError('Manifest selects stale or different committed source')
    config_bytes = payloads.regular_file(repo, config_path.relative_to(repo).as_posix()).read_bytes()
    if manifest.get('configuration') != {'path': config_path.relative_to(repo).as_posix(), **payloads.fingerprint(config_bytes)}:
        raise ValueError('Configuration differs from source-bound inventory')
    config = config_data(config_bytes)
    expected_inputs = payloads._git(standard, 'ls-tree', '-r', '--name-only', sha, 'shared/bijux-docs/partials').decode().splitlines()
    expected_inputs = [name.removeprefix('shared/bijux-docs/') for name in expected_inputs if name.endswith('.html')]
    inputs = manifest.get('producer_inputs')
    if not isinstance(inputs, dict) or set(inputs) != set(expected_inputs):
        raise ValueError('Manifest must bind the complete shared template producer set')
    for name in expected_inputs:
        entry = inputs[name]
        data = payloads.committed_file(standard, sha, name)
        if not isinstance(entry, dict) or set(entry) != {'path', 'sha256', 'bytes'} or {key: entry[key] for key in ('sha256', 'bytes')} != payloads.fingerprint(data):
            raise ValueError('Producer input differs from selected committed template: ' + name)
        projected = repo / payloads.relative_path(entry['path'])
        if not projected.is_relative_to(repo / 'artifacts'):
            raise ValueError('Projected producer inputs must remain in owning artifacts/')
        if payloads.regular_file(repo, entry['path']).read_bytes() != data:
            raise ValueError('Projected template differs from selected committed producer: ' + name)
    if not isinstance(manifest.get('retained_generation'), dict) or not manifest['retained_generation'].get('scope'):
        raise ValueError('Retained generator/runtime scope must be explicit')
    if any(path.is_symlink() for path in site.rglob('*')):
        raise ValueError('Served inventory cannot hide routes behind a symlink')
    actual = {}
    for path in sorted(site.rglob('*.html')):
        name = path.relative_to(site).as_posix()
        actual[name] = payloads.fingerprint(payloads.regular_file(site, name).read_bytes())
    if not actual or 'index.html' not in actual or manifest.get('html_files') != actual:
        raise ValueError('Missing, additional or changed served HTML route inventory')
    configured = authored_routes(config)
    if not configured <= set(actual) - {'404.html'}:
        raise ValueError('Configured navigation reaches missing or404 routes')
    pages = []
    for name in actual:
        raw = payloads.regular_file(site, name).read_bytes()
        parsed = Regions(raw)
        coverage, external, references = set(), set(), []
        url = route_url(config['site_url'], name)
        for href in parsed.regions['primary-navigation']['links']:
            kind, target = destination(config['site_url'], url, href)
            references.append({'href': href, 'classification': kind, 'target': target})
            if kind == 'external': external.add(target)
            elif target not in actual or target == '404.html':
                raise ValueError('Primary navigation reaches missing or404 route: ' + target)
            else: coverage.add(target)
        if not configured <= coverage:
            raise ValueError('Complete primary navigation omits configured destinations: ' + name)
        region_total = sum(value['bytes'] for value in parsed.regions.values())
        if region_total > len(raw):
            raise ValueError('Serialized regions overlap the document byte inventory')
        pages.append({'path': name, 'url': url, 'classification': 'not-found' if name == '404.html' else 'normal',
            'raw_html': actual[name], 'regions': parsed.regions, 'raw_region_bytes': region_total,
            'remaining_html_bytes': len(raw) - region_total, 'primary_internal_targets': sorted(coverage),
            'primary_external_targets': sorted(external), 'normal_routes_outside_primary_navigation': sorted(set(actual) - {'404.html'} - coverage),
            'navigation_references': references})
    normal = [page for page in pages if page['classification'] == 'normal']
    return {'schema': 1, 'result': 'pass', 'scope': 'exact local serialized HTML regions and route graph only',
        'standard': identity, 'configuration': payloads.fingerprint(config_bytes), 'manifest': payloads.fingerprint(manifest_bytes),
        'retained_generation': manifest['retained_generation'], 'html_files': len(pages), 'normal_routes': len(normal),
        'not_found_routes': len(pages) - len(normal), 'configured_navigation_routes': sorted(configured),
        'normal_raw_html_bytes': sum(page['raw_html']['bytes'] for page in normal),
        'normal_raw_region_bytes': {role: sum(page['regions'].get(role, {}).get('bytes', 0) for page in normal)
            for role in ('header', 'tabs', 'primary-navigation', 'local-toc', 'footer')},
        'pages': pages, 'network_quantities': {name: payloads.byte_quantity(None, 'requires actual response/transport measurement')
            for name in ('encoded_body_bytes', 'transfer_bytes_including_headers')},
        'limits': ['Retained generator/runtime identity is historical; only selected template projection equality is qualified.',
                   'Raw repeated bytes do not establish wire, cache, CPU, timing or optimization savings.',
                   'No rendering, consumer adoption, deployment, manual or live qualification.',
                   'No reduction target or threshold is prescribed before measured comparisons.']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo-root', 'site-dir', 'config', 'manifest', 'standard-root', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--standard-sha', required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = (repo / args.output).absolute()
    site = (repo / args.site_dir).absolute()
    if not output.is_relative_to(repo / 'artifacts') or not output.resolve().is_relative_to(repo / 'artifacts') or output.resolve().is_relative_to(site.resolve()):
        parser.error('Write an owning artifacts/ report outside the served directory')
    if output.resolve() in {(repo / args.config).resolve(), (repo / args.manifest).resolve()}:
        parser.error('Output cannot replace selected source-bound measurement inputs')
    try:
        report = qualify(repo, site, (repo / args.config).absolute(), (repo / args.manifest).absolute(), args.standard_root, args.standard_sha)
    except (ValueError, OSError, UnicodeError, yaml.YAMLError) as exc:
        report = {'schema': 1, 'result': 'fail', 'scope': 'serialized navigation accounting', 'error': str(exc)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': report['result'], 'output': str(output)}))
    return 0 if report['result'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
