"""Resolve a committed consumer baseline from exact accepted GitHub source."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from scripts.project_bijux_docs import published_bytes, source_context

PIN = '.github/standards/bijux-std.sha'
BASELINE = 'bijux-docs/config/mkdocs-baseline.json'
LEGACY_PIN = '44e9153959f98bfc27444d6b740144146ed17a77'
CORE_LEGACY_PIN = '10f073dba1d3a9617c8847d72d2bf62bdf7e996d'
LEGACY_PINS = frozenset({LEGACY_PIN, CORE_LEGACY_PIN})
LEGACY_REGISTRY = 'bijux-docs/config/legacy-mkdocs-baselines.json'
LEGACY_SOURCE_PATHS = frozenset({
    'bijux-docs/CONTRACT.md',
    'bijux-docs/scripts/README.md',
    'bijux-docs/tooling/scripts/sync_bijux_docs.sh',
    'bijux-docs/tooling/scripts/verify_bijux_docs_source_of_truth.sh',
    'bijux-docs/scripts/mermaid-init.js',
    'bijux-docs/scripts/theme-persistence.js',
    'bijux-docs/scripts/viewport-profile.js',
    'bijux-docs/scripts/nav-state.js',
    'bijux-docs/scripts/detail-tabs.js',
    'bijux-docs/scripts/nav-reveal.js',
    'bijux-docs/scripts/bootstrap.js',
    'bijux-docs/scripts/nav-sync.js',
})
SHA = re.compile(r'[a-f0-9]{40}\Z')


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(['git', '-C', str(root), *arguments], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Prior asset authority: required Git source is unavailable: ' + ' '.join(arguments))
    return result.stdout.strip()


def authority(context: dict) -> Path:
    root = Path(context['authority']).resolve()
    if (git(root, 'rev-parse', '--show-toplevel') != str(root)
            or git(root, 'remote', 'get-url', 'origin') != context['origin']
            or git(root, 'rev-parse', 'HEAD') != context['sha']
            or git(root, 'status', '--porcelain', '--untracked-files=all')):
        raise RuntimeError('Prior asset authority: exact clean accepted GitHub checkout is required')
    return root



def reviewed_legacy_javascript(context: dict, previous: str, shared: Path) -> bytes:
    """Admit only an explicit upstream review, bound to its predecessor bytes.

    The legacy source predates the baseline file. Its scripts prove destination
    ownership, while the accepted registry separately declares the reviewed
    plain-list migration; consumers cannot infer or supply that declaration.
    """
    data = published_bytes(context, context['sha'], LEGACY_REGISTRY)
    local = shared / 'config/legacy-mkdocs-baselines.json'
    if local.is_symlink() or not local.is_file() or local.read_bytes() != data:
        raise RuntimeError('Prior asset authority: legacy registry differs from accepted Git source')
    try:
        registry = json.loads(data)
        if set(registry) != {'schema', 'baselines'} or type(registry['schema']) is not int or registry['schema'] != 1:
            raise ValueError('registry schema')
        if not isinstance(registry['baselines'], dict) or set(registry['baselines']) != LEGACY_PINS:
            raise ValueError('reviewed predecessor')
        record = registry['baselines'][previous]
        if set(record) != {'extra_javascript', 'source_evidence', 'review'} or not isinstance(record['review'], str) or not record['review'].strip():
            raise ValueError('reviewed record')
        evidence = record['source_evidence']
        if not isinstance(evidence, dict) or set(evidence) != LEGACY_SOURCE_PATHS:
            raise ValueError('source evidence')
        for source, expected in evidence.items():
            if (not isinstance(source, str) or not source.startswith('bijux-docs/')
                    or any(part in ('', '.', '..') for part in source.split('/'))
                    or not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected)):
                raise ValueError('source evidence shape')
            actual = published_bytes(context, previous, source)
            if hashlib.sha256(actual).hexdigest() != expected:
                raise RuntimeError('Prior asset authority: legacy source evidence differs: ' + source)
        return json.dumps({'extra_javascript': record['extra_javascript']}).encode()
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise RuntimeError('Prior asset authority: invalid reviewed legacy baseline') from error


def prior_javascript(repository: Path, shared: Path) -> tuple[str, ...] | None:
    """Never infer prior ownership from local overrides or untracked receipts.

    The normal/current list path does not call this function. The caller supplies
    no predecessor override: the consumer's committed pin selects the prior tree.
    """
    if os.environ.get('BIJUX_DOCS_SOURCE_MODE') != 'accepted-github':
        return None
    context = source_context()
    root = repository.resolve()
    if git(root, 'rev-parse', '--show-toplevel') != str(root):
        raise RuntimeError('Prior asset authority: explicit consumer repository root is required')
    pin = root / PIN
    if any(path.is_symlink() for path in (pin, pin.parent, pin.parent.parent)) or not pin.is_file():
        raise RuntimeError('Prior asset authority: regular working standard pin is required')
    if pin.read_text().strip() != context['sha']:
        raise RuntimeError('Prior asset authority: working standard pin differs from accepted source')
    committed = git(root, 'ls-tree', 'HEAD', '--', PIN)
    if not re.fullmatch(r'100644 blob [a-f0-9]{40}\t' + re.escape(PIN), committed):
        raise RuntimeError('Prior asset authority: committed regular standard pin is required')
    previous = git(root, 'show', 'HEAD:' + PIN)
    if not SHA.fullmatch(previous):
        raise RuntimeError('Prior asset authority: committed exact previous standard pin is required')
    if previous == context['sha']:
        return None
    authority(context)
    current = published_bytes(context, context['sha'], BASELINE)
    if hashlib.sha256((shared / 'config/mkdocs-baseline.json').read_bytes()).digest() != hashlib.sha256(current).digest():
        raise RuntimeError('Prior asset authority: current baseline differs from accepted Git source')
    data = (reviewed_legacy_javascript(context, previous, shared) if previous in LEGACY_PINS
            else published_bytes(context, previous, BASELINE))
    authority(context)
    try:
        baseline = json.loads(data)
        names = baseline['extra_javascript']
        if (not isinstance(names, list) or not names
                or not all(isinstance(name, str) and name and not any(ord(char) < 32 for char in name) for name in names)
                or len(names) != len(set(names))):
            raise ValueError('invalid script list')
    except (ValueError, KeyError, TypeError) as error:
        raise RuntimeError('Prior asset authority: invalid previous accepted script baseline') from error
    return tuple(names)
