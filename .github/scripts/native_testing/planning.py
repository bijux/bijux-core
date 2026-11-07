"""Preserve the canonical native test inventory and Nextest case selection."""
from collections import Counter
from verification.planning import encoded, inventory, test_partitions


def plan(metadata: dict, policy: dict, expression: str) -> dict:
    if (policy.get('schema') != 1 or policy.get('target_seconds') != 180
            or policy.get('maximum_seconds') != 300
            or not 1 <= policy.get('targets_per_partition', 0) <= 16):
        raise ValueError('Native testing requires reviewed bounded worker budgets')
    selected = dict(metadata, packages=[dict(package, targets=[target for target in package['targets']
                                                              if target.get('test', False)])
                                        for package in metadata['packages']])
    targets = inventory(selected)
    selectors = [('--lib',)] if any(target['selector'] == ['--lib'] for target in targets) else []
    for owner in sorted({target['package'] for target in targets}):
        owned = [target for target in targets if target['package'] == owner]
        if not any(target['selector'] == ['--lib'] for target in owned):
            selectors.append(tuple(owned[0]['selector']))
    warm_selectors = [flag for selector in dict.fromkeys(selectors) for flag in selector]
    checks = test_partitions(targets, policy)
    checks.append({'id': 'python', 'kind': 'python', 'package': 'bijux-cli-python', 'targets': []})
    value = {'schema': 1, 'inventory': targets, 'checks': checks, 'policy': policy,
             'warm_selectors': warm_selectors, 'nextest_filter': expression, 'nextest_profile': 'ci', 'nextest_version': '0.9.100'}
    validate(value)
    return value


def validate(value: dict) -> None:
    checks = value['checks']
    if len({check['id'] for check in checks}) != len(checks):
        raise ValueError('Duplicate native verification owner')
    expected = Counter(encoded(target) for target in value['inventory'])
    observed = Counter(encoded(target) for check in checks if check['kind'] == 'tests' for target in check['targets'])
    if not expected or expected != observed:
        raise ValueError('Every native Cargo target needs exactly one complete owner')
    selectors = {}
    for check in checks:
        for target in check['targets']:
            selectors.setdefault(tuple(target['selector']), set()).add(check['id'])
    if any(len(owners) != 1 for owners in selectors.values()):
        raise ValueError('Colliding workspace selectors cannot have separate native workers')
    if sum(check['kind'] == 'python' for check in checks) != 1:
        raise ValueError('Python coverage and parity verification is required exactly once')
    if any(check['kind'] not in {'tests', 'python'} for check in checks):
        raise ValueError('Unreviewed native test family')
    warm = value['warm_selectors']
    for owner in {target['package'] for target in value['inventory']}:
        owned = [target for target in value['inventory'] if target['package'] == owner]
        if not any(all(flag in warm for flag in target['selector']) for target in owned):
            raise ValueError('Every workspace package must contribute its native test dependency graph')
    if not value['nextest_filter'] or value['nextest_profile'] != 'ci' or value['nextest_version'] != '0.9.100':
        raise ValueError('The canonical native test executor and filter must be retained')


def catalogue(check: dict, value: dict) -> dict:
    expected = {(target['package'], target['target'], target['selector'][0].removeprefix('--'))
                for target in check['targets']}
    observed = set()
    selected = []
    excluded = []
    for suite in value['rust-suites'].values():
        key = (suite['package-name'], suite['binary-name'], suite['kind'])
        if key in observed:
            raise ValueError('Duplicate compiled native test binary')
        observed.add(key)
        for name, case in suite['testcases'].items():
            identity = suite['binary-id'] + '::' + name
            if case['filter-match']['status'] == 'matches' and not case['ignored']:
                selected.append(identity)
            else:
                excluded.append(identity)
    if observed != expected:
        raise ValueError('Compiled Nextest catalogue differs from the assigned Cargo targets')
    return {'selected_cases': selected, 'excluded_cases': excluded, 'compiled_targets': len(observed)}


def case_totals(records: list[dict]) -> dict:
    selected = [case for record in records for case in record.get('selected_cases', [])]
    excluded = [case for record in records for case in record.get('excluded_cases', [])]
    if not selected or len(set(selected + excluded)) != len(selected + excluded):
        raise ValueError('Native case coverage must be nonempty and have unique ownership')
    return {'rust_cases': len(selected), 'excluded_rust_cases': len(excluded)}
