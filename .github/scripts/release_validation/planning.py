"""Partition the complete Cargo target inventory without dropping a proof surface."""
from __future__ import annotations

import hashlib
import json

PUBLIC_DAG = (
    'bijux-dag-core', 'bijux-dag-artifacts', 'bijux-dag-runtime',
    'bijux-dag-app', 'bijux-dag-cli',
)


def encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def digest(value: object) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def selector(target: dict) -> list[str] | None:
    kinds = target['kind']
    if kinds == ['custom-build']:
        return None
    for kind in ('bin', 'test', 'bench', 'example'):
        if kinds == [kind]:
            return ['--' + kind, target['name']]
    if kinds and all(kind in {'lib', 'rlib', 'cdylib', 'dylib', 'staticlib', 'proc-macro'} for kind in kinds):
        return ['--lib']
    raise ValueError('Unreviewed Cargo target kind: ' + repr(kinds))


def inventory(metadata: dict) -> list[dict]:
    members = set(metadata['workspace_members'])
    result = []
    for package in sorted(metadata['packages'], key=lambda item: item['name']):
        if package['id'] not in members:
            continue
        for target in sorted(package['targets'], key=lambda item: (item['kind'], item['name'])):
            flags = selector(target)
            if flags is not None:
                result.append({'package': package['name'], 'target': target['name'], 'selector': flags})
    keys = [(item['package'], tuple(item['selector'])) for item in result]
    if not result or len(keys) != len(set(keys)):
        raise ValueError('Cargo inventory is empty or contains duplicate targets')
    return result


def plan(metadata: dict, policy: dict) -> dict:
    if policy.get('schema') != 1 or policy.get('target_seconds') != 180 or policy.get('maximum_seconds') != 300:
        raise ValueError('Release verification requires reviewed three/five minute budgets')
    size = policy.get('targets_per_partition')
    if not isinstance(size, int) or not 1 <= size <= 16:
        raise ValueError('Release target partition size is not bounded')
    targets = inventory(metadata)
    known = {item['package'] + '/' + item['target'] for item in targets}
    if not set(policy['isolated_tests']) <= known:
        raise ValueError('Isolated test policy references a missing Cargo target')
    packages = sorted({item['package'] for item in targets})
    checks = [{'id': 'format', 'kind': 'format', 'compiled': False, 'package': '', 'targets': []}]
    for package in packages:
        for kind in ('lint', 'docs'):
            checks.append({'id': kind + '/' + package, 'kind': kind, 'package': package, 'compiled': True, 'targets': []})
        owned = [item for item in targets if item['package'] == package]
        ordinary = []
        groups = []
        for item in owned:
            if package + '/' + item['target'] in policy['isolated_tests']:
                groups.append([item])
            else:
                ordinary.append(item)
        groups.extend(ordinary[index:index + size] for index in range(0, len(ordinary), size))
        for group in groups:
            identity = digest(group)[:12]
            checks.append({'id': 'tests/' + package + '/' + identity, 'kind': 'tests', 'package': package,
                           'compiled': True, 'targets': group})
    for package in PUBLIC_DAG:
        if package not in packages:
            raise ValueError('Public DAG crate is missing from the workspace: ' + package)
        checks.append({'id': 'publish/' + package, 'kind': 'publish', 'package': package, 'compiled': True, 'targets': []})
    checks.extend([
        {'id': 'package-contents', 'kind': 'package-contents', 'package': '', 'compiled': False, 'targets': []},
        {'id': 'smoke', 'kind': 'smoke', 'package': 'bijux-dag-cli', 'compiled': True, 'targets': []},
        {'id': 'python-installation', 'kind': 'python-installation', 'package': 'bijux-cli-python', 'compiled': True, 'targets': []},
    ])
    result = {'schema': 1, 'inventory': targets, 'checks': checks, 'policy': policy}
    validate(result)
    return result


def validate(value: dict) -> None:
    checks = value['checks']
    identities = [check['id'] for check in checks]
    if len(identities) != len(set(identities)):
        raise ValueError('Duplicate verification partition')
    expected = sorted(encoded(target) for target in value['inventory'])
    observed = sorted(encoded(target) for check in checks if check['kind'] == 'tests' for target in check['targets'])
    if not expected or observed != expected:
        raise ValueError('Partition plan must cover every Cargo target exactly once')
    packages = {target['package'] for target in value['inventory']}
    for kind in ('lint', 'docs'):
        if sorted(check['package'] for check in checks if check['kind'] == kind) != sorted(packages):
            raise ValueError('Incomplete package verification family: ' + kind)
    if sorted(check['package'] for check in checks if check['kind'] == 'publish') != sorted(PUBLIC_DAG):
        raise ValueError('Incomplete publication verification family')
    for kind in ('format', 'package-contents', 'smoke', 'python-installation'):
        if sum(check['kind'] == kind for check in checks) != 1:
            raise ValueError('Missing or duplicated verification: ' + kind)
