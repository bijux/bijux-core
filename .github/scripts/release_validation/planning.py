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
    if not set(policy.get('serial_test_targets', [])) <= known:
        raise ValueError('Serial test policy references a missing Cargo target')
    if not set(policy['isolated_tests']) <= known:
        raise ValueError('Isolated test policy references a missing Cargo target')
    packages = sorted({item['package'] for item in targets})
    checks = [{'id': kind, 'kind': kind, 'compiled': kind != 'format', 'package': '', 'targets': []}
              for kind in ('format', 'lint', 'docs', 'doctests')]
    atomic = {}
    for target in targets:
        atomic.setdefault(tuple(target['selector']), []).append(target)
    ordinary = {}
    groups = []
    for members in atomic.values():
        if len(members) > size:
            raise ValueError('An indivisible Cargo selector exceeds the target partition bound')
        owners = {member['package'] for member in members}
        owner = next(iter(owners)) if len(owners) == 1 else 'workspace'
        if any(member['package'] + '/' + member['target'] in policy['isolated_tests'] for member in members):
            groups.append((owner, members))
        else:
            ordinary.setdefault(owner, []).append(members)
    for owner, batches in sorted(ordinary.items()):
        current = []
        for members in batches:
            if len(current) + len(members) > size:
                groups.append((owner, current));current = []
            current.extend(members)
        if current:
            groups.append((owner, current))
    for owner, group in groups:
        identity = digest(group)[:12]
        checks.append({'id': 'tests/' + owner + '/' + identity, 'kind': 'tests', 'package': owner,
                       'compiled': True, 'targets': group})
    for check in checks:
        if any(target['package'] + '/' + target['target'] in policy.get('serial_test_targets', [])
               for target in check['targets']):
            check['test_threads'] = 1
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
    selector_owners = {}
    for check in checks:
        if check['kind'] == 'tests':
            serial = any(target['package'] + '/' + target['target'] in value['policy'].get('serial_test_targets', [])
                         for target in check['targets'])
            if check.get('test_threads') != (1 if serial else None):
                raise ValueError('Verification must retain governed test resource isolation')
            for target in check['targets']:
                selector_owners.setdefault(tuple(target['selector']), set()).add(check['id'])
    if any(len(owners) != 1 for owners in selector_owners.values()):
        raise ValueError('A workspace-wide Cargo selector must have exactly one worker')
    for kind in ('lint', 'docs', 'doctests'):
        if sum(check['kind'] == kind for check in checks) != 1:
            raise ValueError('Incomplete workspace verification family: ' + kind)
    if sorted(check['package'] for check in checks if check['kind'] == 'publish') != sorted(PUBLIC_DAG):
        raise ValueError('Incomplete publication verification family')
    for kind in ('format', 'package-contents', 'smoke', 'python-installation'):
        if sum(check['kind'] == kind for check in checks) != 1:
            raise ValueError('Missing or duplicated verification: ' + kind)
