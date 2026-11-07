"""Assign complete Cargo target inventories to bounded verification workers."""
from __future__ import annotations
import hashlib
import json

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


def test_partitions(targets: list[dict], policy: dict) -> list[dict]:
    size = policy["targets_per_partition"]
    checks = []
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
    return checks
