#!/usr/bin/env python3
"""Reproduce admitted Material with owned index and worker recovery boundaries."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess

OWNED = Path(__file__).resolve().parent
SHARED = OWNED.parents[1]
REPLACEMENT = 'zi=document.forms.namedItem("search")?window.bijuxSearchIndex.observe(ks,Z):tt'
WORKER_REPLACEMENT = 'function Ei(e,t){let r=window.bijuxSearchWorker.channel(e,T);'
FRAGMENT_SCROLL_BOUNDARY = 'function gn(e){let t=x("a",{href:e});t.addEventListener("click",r=>r.stopPropagation()),t.click()}'
FRAGMENT_SCROLL_REPLACEMENT = 'function gn(e){__bijuxScrollCurrentFragment(e)}'

GLOBAL_CHARACTER_SHORTCUTS = ',r.pipe(g(({mode:c})=>c==="global")).subscribe(c=>{switch(c.type){case"f":case"s":case"/":i.focus(),i.select(),c.claim();break}});'


def without_global_character_shortcuts(source: str) -> str:
    """Retain focused native keyboard behavior without character-only global actions."""
    if source.count(GLOBAL_CHARACTER_SHORTCUTS) != 1:
        raise ValueError('Native character-only search shortcut boundary must occur exactly once')
    return source.replace(GLOBAL_CHARACTER_SHORTCUTS, ';')


NODE_PARSER_VERSION = 'v24.21.0'
JAVASCRIPT_SYNTAX = ('const fs=require("node:fs"),vm=require("node:vm");'
                     'try{new vm.Script(fs.readFileSync(0,"utf8"),{filename:"bijux-material-runtime.js"})}'
                     'catch(error){console.error(error.name+": "+error.message);process.exitCode=1}')


def validate_generated_javascript(source: bytes) -> None:
    """Parse the complete emitted classic script before changing any owned output."""
    try:
        version = subprocess.run(['node', '--version'], capture_output=True, check=True, timeout=10)
        if version.stdout.decode().strip() != NODE_PARSER_VERSION:
            raise ValueError('Generated Material runtime requires the admitted Node.js ' + NODE_PARSER_VERSION + ' parser')
        parsed = subprocess.run(['node', '-e', JAVASCRIPT_SYNTAX], input=source,
                                capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError('Generated Material runtime parser is unavailable; output was not changed') from error
    if parsed.returncode:
        raise ValueError('Generated Material runtime rejected by admitted JavaScript parser: '
                         + parsed.stderr.decode(errors='replace').strip()[:1000])


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compile_runtime(templates: Path, installed_version: str) -> tuple[str, bytes, dict, bytes]:
    admitted = json.loads((OWNED / 'admission.json').read_text())
    if installed_version != admitted['version']:
        raise ValueError('Unsupported Material version; review admission before compiling')
    upstream = (templates / admitted['bundle']).read_bytes()
    base = (templates / 'base.html').read_bytes()
    source_map = (templates / (admitted['bundle'] + '.map')).read_bytes()
    worker = (templates / admitted['worker']).read_bytes()
    for name, data in [('bundle', upstream), ('base_template', base), ('upstream_map', source_map), ('worker', worker)]:
        if sha256(data) != admitted[name + '_sha256']:
            raise ValueError('Material ' + name + ' differs from admitted bytes')
    license_bytes = (OWNED / 'UPSTREAM-LICENSE.txt').read_bytes()
    if sha256(license_bytes) != admitted['license_sha256']:
        raise ValueError('Upstream license differs from admission')
    original = upstream.decode()
    needle = admitted['needle']
    if original.count(needle) != 1:
        raise ValueError('Search-index boundary must occur exactly once')
    worker_needle = admitted['worker_boundary']
    if original.count(worker_needle) != 1:
        raise ValueError('Search-worker boundary must occur exactly once')
    adapter = (OWNED / 'search-index-adapter.js').read_bytes()
    worker_adapter = (OWNED / 'search-worker-adapter.js').read_bytes()
    # The original map describes upstream offsets. Never claim it maps modified bytes.
    modified = without_global_character_shortcuts(original).replace(needle, REPLACEMENT).replace(worker_needle, WORKER_REPLACEMENT)
    renderer_needle = 'href:`${s}`,class:"md-search-result__link",tabIndex:-1'
    renderer_replacement = 'href:`${s}`,target:__bijuxSearchCapabilityTarget(s),class:"md-search-result__link",tabIndex:-1'
    opening = '"use strict";(()=>{'
    if original.count(renderer_needle) != 1 or original.count(opening) != 1 or '__bijuxSearchCapabilityTarget' in original:
        raise ValueError('Native search renderer boundary differs from admitted unique context')
    resize_needle = 'new ResizeObserver(e=>e.forEach(t=>cn.next(t)))'
    resize_replacement = '__bijuxElementResizeObserver(t=>cn.next(t))'
    if original.count(resize_needle) != 1 or '__bijuxElementResizeObserver' in original:
        raise ValueError('Native resize delivery differs from admitted unique context')
    if original.count(FRAGMENT_SCROLL_BOUNDARY) != 1 or '__bijuxScrollCurrentFragment' in original:
        raise ValueError('Native fragment restoration boundary must occur exactly once')
    fragment_scroll = (OWNED / 'fragment-restoration.js').read_bytes()
    modified = modified.replace(FRAGMENT_SCROLL_BOUNDARY, FRAGMENT_SCROLL_REPLACEMENT)
    resize = (OWNED / 'element-resize-delivery.js').read_bytes()
    modified = modified.replace(resize_needle, resize_replacement)
    navigation = (OWNED / 'search-capability-boundary.js').read_bytes()
    modified = modified.replace(renderer_needle, renderer_replacement).replace(opening, opening + navigation.decode() + resize.decode() + fragment_scroll.decode())
    modified, maps = re.subn(r'(?m)^//# sourceMappingURL=.*(?:\n|$)', '', modified)
    if maps != 1:
        raise ValueError('Expected exactly one upstream source-map annotation')
    runtime = b'/*\n' + license_bytes + b'\n*/\n' + adapter + b'\n' + worker_adapter + b'\n' + modified.encode()
    digest = sha256(runtime)
    asset = 'assets/javascripts/material-search.' + digest + '.js'
    provenance = {
        'schema': 1, 'upstream_version': installed_version,
        'upstream_bundle': admitted['bundle'], 'upstream_sha256': admitted['bundle_sha256'],
        'upstream_base_template_sha256': admitted['base_template_sha256'],
        'upstream_map_sha256': admitted['upstream_map_sha256'],
        'upstream_license_sha256': admitted['license_sha256'],
        'adapter_sha256': sha256(adapter), 'owned_source': 'tooling/material/search-index-adapter.js',
        'worker_adapter_sha256': sha256(worker_adapter), 'worker_owned_source': 'tooling/material/search-worker-adapter.js',
        'upstream_worker': admitted['worker'], 'upstream_worker_sha256': admitted['worker_sha256'],
        'boundary': {'original': needle, 'replacement': REPLACEMENT, 'occurrences': 1},
        'worker_boundary': {'original': worker_needle, 'replacement': WORKER_REPLACEMENT, 'occurrences': 1},
        'global_character_shortcuts': {'original': GLOBAL_CHARACTER_SHORTCUTS, 'replacement': ';', 'occurrences': 1, 'disabled_keys': ['/', 'f', 's'], 'retained': 'Focused native query/result keyboard subscriptions and browser modifier defaults.'},
        'fragment_restoration_owned_source': 'tooling/material/fragment-restoration.js',
        'fragment_restoration_sha256': sha256(fragment_scroll),
        'fragment_restoration_boundary': {'original': FRAGMENT_SCROLL_BOUNDARY, 'replacement': FRAGMENT_SCROLL_REPLACEMENT, 'occurrences': 1, 'behavior': 'Scroll only the fragment of the current native history entry; do not queue a redundant native anchor navigation.'},
        'element_resize_owned_source': 'tooling/material/element-resize-delivery.js',
        'element_resize_sha256': sha256(resize),
        'element_resize_boundary': {'original': resize_needle, 'replacement': resize_replacement, 'occurrences': 1, 'helper_scope': 'admitted native IIFE; no global observer or error interception'},
        'search_capability_owned_source': 'tooling/material/search-capability-boundary.js',
        'search_capability_sha256': sha256(navigation),
        'search_capability_renderer': {'original': renderer_needle, 'replacement': renderer_replacement, 'occurrences': 1, 'helper_scope': 'unique admitted native runtime IIFE'},
        'output_asset': asset, 'output_sha256': digest,
        'syntax_validation': {'parser': 'Node.js vm.Script', 'required_version': NODE_PARSER_VERSION, 'scope': 'Complete generated classic-script bytes after all transformations; syntax-only validation before emission.'},
        'source_map': 'Upstream map applies only to unmodified upstream bundle; compatibility output has no map annotation.',
        'transport': 'Owned same-origin HTTP index XHR starts only on actual search focus/input/open or a native query/highlight deep link; direct cancel/retry, 45-second nonrenewable total deadline, 8-second no-progress stall bound, 80MiB browser-reported progress-byte limit, 40Mi UTF-16 response/source-character limit and 50,000-document candidate limit. Worker operation deadlines remain separately fixed at 8 seconds.',
        'limits': ['Index-ready means fetched/admitted index, not worker-ready.', 'File-protocol search is outside admitted HTTP website qualification.', 'Largest actual consumer search corpus and CPU measurements remain required before scale claims.'],
        'activity_state': {'searching_stage': 'worker-searching', 'ready_after': 'actual latest native RESULT has been delivered to subscribers', 'pending': 'remain searching while queued or in-flight work exists'},
        'template_extension': {'block': 'extrahead', 'include': 'partials/site-head.html', 'owner': 'consumer', 'optional': True, 'managed_default': False},
        'query_scheduling': {'in_flight_limit': 1, 'pending_limit': 1, 'settle_ms': 150, 'operation_deadline_ms': 8000, 'obsolete_results': 'discard when a newer native query is pending'},
        'behavior': 'Native worker algorithm, SETUP/options, query/results, ranking, highlighting and rendering retained. Owned index Observable catches failure before native subscribers; owned native-Subject worker channel contains resource/protocol failures, bounds each actual setup/query operation to 8 seconds without renewal on queued edits, coalesces intermediate input behind a 150ms settle window with one native query in flight and one replaceable pending query, discards superseded results before native rendering, announces searching while work is pending and readiness only after the latest native result reaches subscribers, directly terminates retired workers, and replays cached native SETUP/query on retry without index refetch.',
    }
    template = ('{# Native config/layout remain inherited; this reviewed block replaces only the admitted runtime. #}\n'
                '{% extends "base.html" %}\n'
                '{% block extrahead %}\n  {{ super() }}\n'
                '  {% include "partials/site-head.html" ignore missing %}\n{% endblock %}\n'
                '{% block scripts %}\n'
                '  <script src="{{ \'' + asset + '\' | url }}"></script>\n'
                '  {% for script in config.extra_javascript %}\n    {{ script | script_tag }}\n  {% endfor %}\n'
                '{% endblock %}\n').encode()
    return asset, runtime, provenance, template


def generate(shared: Path, templates: Path, installed_version: str, check: bool = False) -> dict:
    asset, runtime, provenance, template = compile_runtime(templates, installed_version)
    if not check:
        validate_generated_javascript(runtime)
    expected = {
        shared / asset: runtime,
        shared / 'tooling/material/runtime-provenance.json': (json.dumps(provenance, indent=2) + '\n').encode(),
        shared / 'partials/main.html': template,
    }
    stale = sorted((shared / 'assets/javascripts').glob('material-search.*.js'))
    stale = [path for path in stale if path != shared / asset]
    if stale:
        raise ValueError('Preserve previous owned runtime assets; retire them explicitly after review: ' + ', '.join(map(str, stale)))
    if check:
        if any(not path.is_file() or path.read_bytes() != data for path, data in expected.items()):
            raise ValueError('Generated Material compatibility output differs from exact admitted source')
    else:
        for path, data in expected.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shared-root', type=Path, default=SHARED)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    distribution = importlib.metadata.distribution('mkdocs-material')
    templates = Path(distribution.locate_file('material/templates'))
    result = generate(args.shared_root.resolve(), templates, distribution.version, args.check)
    print(json.dumps({'asset': result['output_asset'], 'sha256': result['output_sha256'], 'mode': 'check' if args.check else 'write'}))


if __name__ == '__main__':
    main()
