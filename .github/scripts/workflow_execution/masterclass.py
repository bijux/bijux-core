"""Bounded dependency-notice promotion preserving Masterclass's accepted runtime."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from .canonical_sources import owning_scripts, read_owned
from .dependency_prs import project_dependency_pull_requests, validate_owned_execution
from .source_loading import MODULE_ORDER
from .yaml_io import parse_workflow

REPOSITORY = 'bijux-masterclass'
AUTHORITY_PATH = '.github/standards/dependency-notification-source.json'
BASELINE_SHA = '1ad55aafdb44e2d47890632653e7d9c312cc7968'
POLICY = {'schema': 1, 'dependency_pull_requests': 'notification-only',
          'dependency_merge': 'owner-consolidation', 'main_verification': 'existing-events'}


def read_authority(target: Path) -> dict:
    authority = json.loads(read_owned(target, AUTHORITY_PATH))
    if (not isinstance(authority, dict) or set(authority) != {'schema', 'repository', 'baseline_sha', 'execution_policy_sha'}
            or type(authority['schema']) is not int or authority['schema'] != 1
            or authority['repository'] != REPOSITORY or authority['baseline_sha'] != BASELINE_SHA
            or not isinstance(authority['execution_policy_sha'], str)
            or not re.fullmatch(r'[0-9a-f]{40}', authority['execution_policy_sha'])):
        raise ValueError('Masterclass dependency authority requires its fixed baseline and exact policy source')
    if read_owned(target, '.github/standards/bijux-std.sha').decode().strip() != BASELINE_SHA:
        raise ValueError('Masterclass dependency promotion must preserve the accepted runtime source pin')
    return authority


def accepted_baseline(source_root: Path, target: Path) -> Path:
    """Independently fetch the one supported baseline inside this product's artifacts."""
    cache = target / 'artifacts/masterclass-runtime-source'
    if (target / 'artifacts').is_symlink() or cache.is_symlink():
        raise ValueError('Masterclass baseline cache must be owned by this checkout')
    if not cache.exists():
        cache.mkdir(parents=True)
        subprocess.run(['git', '-C', str(cache), 'init', '--quiet'], check=True)
        subprocess.run(['git', '-C', str(cache), 'remote', 'add', 'origin', 'https://github.com/bijux/bijux-std.git'], check=True)
        subprocess.run(['git', '-C', str(cache), 'fetch', '--quiet', '--depth', '1', 'origin', BASELINE_SHA], check=True)
        subprocess.run(['git', '-C', str(cache), 'checkout', '--quiet', '--detach', BASELINE_SHA], check=True)
    from .source_authority import git, OFFICIAL_ORIGINS
    if (Path(git(cache, 'rev-parse', '--show-toplevel')).resolve() != cache.resolve()
            or git(cache, 'rev-parse', 'HEAD') != BASELINE_SHA
            or git(cache, 'remote', 'get-url', 'origin') not in OFFICIAL_ORIGINS
            or git(cache, 'status', '--porcelain', '--untracked-files=all')):
        raise ValueError('Masterclass baseline cache is not clean exact official source')
    _, renderer = owning_scripts(cache)
    renderer.WORKFLOW_EXECUTION.admit_source(cache, target, REPOSITORY, BASELINE_SHA)
    return cache


def expected_masterclass(source_root: Path, baseline: Path, target: Path, policy_sha: str) -> tuple[dict, set]:
    """Compose only the owned governance boundary; every runtime byte keeps its baseline."""
    _, baseline_renderer = owning_scripts(baseline)
    original, absent = baseline_renderer.WORKFLOW_EXECUTION.verification.expected_projection(baseline, target, REPOSITORY)
    prepared = copy.deepcopy(original)
    _, renderer = owning_scripts(source_root)
    manifest = json.loads(read_owned(baseline, '.github/standards/repo-config.manifest.json'))
    entry = next(repo for repo in manifest['repositories'] if repo['name'] == REPOSITORY)
    entry.setdefault('workflow_execution_policy', {}).update(POLICY)
    if 'dependency-notice' not in entry['workflow_allowlist']:
        entry['workflow_allowlist'].append('dependency-notice')
    notice_inventory = {'id': 'dependency-notice', 'source': 'shared/bijux-gh/workflows/dependency-notice.yml',
                        'consumer_runtime': '.github/workflows/dependency-notice.yml'}
    manifest['workflow_inventory']['managed_workflows'].append(notice_inventory)
    prepared['.github/standards/repo-config.manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    prepared['.github/standards/workflow-inventory.json'] = (json.dumps(manifest['workflow_inventory'], indent=2) + '\n').encode()
    # Source-owned loader/checker files understand the explicitly bounded composition.
    for name in (*MODULE_ORDER, '__init__'):
        relative = f'.github/scripts/workflow_execution/{name}.py'
        prepared[relative] = read_owned(source_root, relative)
    prepared['.github/scripts/check_workflow_projection.py'] = read_owned(source_root, '.github/scripts/check_workflow_projection.py')
    for relative, body in tuple(prepared.items()):
        if not relative.startswith('.github/workflows/') or body is None:
            continue
        identity = relative.rsplit('/', 1)[-1].removesuffix('.yml')
        if identity == 'automerge-pr':
            prepared[relative] = read_owned(source_root, '.github/workflows/automerge-pr.yml')
            continue
        document = parse_workflow(body, identity)
        projected = project_dependency_pull_requests(identity, document, POLICY)
        if identity == 'github-policy':
            step = next(item for item in projected['jobs']['policy']['steps']
                        if item.get('name') == 'Select canonical workflow verification source')
            original_pin = 'source_sha="$(cat .github/standards/bijux-std.sha)"'
            replacement = 'source_sha="$(python3 -c \'import json; print(json.load(open(".github/standards/dependency-notification-source.json"))["execution_policy_sha"])\')"'
            if step['run'].count(original_pin) != 1:
                raise ValueError('Masterclass baseline governance source selector is not the supported contract')
            step['run'] = step['run'].replace(original_pin, replacement)
        if projected != document:
            prepared[relative] = renderer.render_yaml_document(projected, preserve_scalar_types=True).encode()
    prepared[notice_inventory['consumer_runtime']] = renderer.render_yaml_document(
        parse_workflow(read_owned(source_root, notice_inventory['source']), 'dependency-notice'),
        preserve_scalar_types=True,
    ).encode()
    authority = {'schema': 1, 'repository': REPOSITORY, 'baseline_sha': BASELINE_SHA, 'execution_policy_sha': policy_sha}
    prepared[AUTHORITY_PATH] = (json.dumps(authority, indent=2, sort_keys=True) + '\n').encode()
    snapshots = '.github/standards/workflow-sources/'
    for identity in ['bijux-std', 'automerge-pr']:
        prepared[snapshots + identity + '.yml'] = prepared[f'.github/workflows/{identity}.yml']
    record = {'schema': 2, 'authority': authority, 'inputs': {
        path: hashlib.sha256(body).hexdigest() for path, body in sorted(prepared.items())
        if body is not None and not path.startswith(snapshots)
    }}
    prepared[snapshots + 'source-manifest.json'] = (json.dumps(record, indent=2, sort_keys=True) + '\n').encode()
    return prepared, absent - set(prepared)


def verify_masterclass(source_root: Path, target: Path) -> dict:
    authority = read_authority(target)
    baseline = accepted_baseline(source_root, target)
    expected, absent = expected_masterclass(source_root, baseline, target, authority['execution_policy_sha'])
    failures, verified = [], {}
    checksum_rows = [line.split() for line in read_owned(target, '.github/bijux-std-shared.sha256').decode().splitlines()]
    for relative in [AUTHORITY_PATH, '.github/scripts/workflow_execution/masterclass.py', '.github/workflows/dependency-notice.yml']:
        bindings = [row[0] for row in checksum_rows if len(row) == 2 and row[1] == relative]
        if bindings != [hashlib.sha256(expected[relative]).hexdigest()]:
            failures.append('missing or rebound Masterclass execution checksum: ' + relative)
    for relative, body in sorted(expected.items()):
        if body is None:
            if (target / relative).exists() and b'SSOT NOTICE' in read_owned(target, relative)[:250]:
                failures.append('unexpected generated wrapper: ' + relative)
            continue
        if read_owned(target, relative) != body:
            failures.append('noncanonical bounded Masterclass projection: ' + relative)
        verified[relative] = hashlib.sha256(body).hexdigest()
    for relative in sorted(absent):
        if (target / relative).exists() or (target / relative).is_symlink():
            failures.append('disabled managed destination is present: ' + relative)
    owned = {str(path.relative_to(target)): parse_workflow(path.read_bytes(), path.name)
             for path in (target / '.github/workflows').glob('*.yml')
             if str(path.relative_to(target)) not in expected}
    validate_owned_execution(owned, POLICY)
    current, current_absent = expected_masterclass(source_root, baseline, target, authority['execution_policy_sha'])
    if current != expected or current_absent != absent or read_authority(target) != authority:
        failures.append('Masterclass source authority changed during verification')
    if failures:
        raise ValueError('\n'.join(failures))
    return {'repository': REPOSITORY, 'verified_files': verified, 'absent_paths': sorted(absent),
            'mutated_product': False, 'execution_authorities': authority}


def promote_masterclass(source_root: Path, target: Path, policy_sha: str) -> dict:
    """Promote the accepted bot policy without advancing the accepted product baseline."""
    source_root, target = source_root.resolve(), target.resolve()
    if target.name != REPOSITORY or source_root == target or not source_root.is_relative_to(target / 'artifacts'):
        raise ValueError('Masterclass policy source must use its owning artifact cache')
    from .source_authority import git, OFFICIAL_ORIGINS
    if (source_root != Path(__file__).resolve().parents[3]
            or Path(git(source_root, 'rev-parse', '--show-toplevel')).resolve() != source_root
            or not re.fullmatch(r'[0-9a-f]{40}', policy_sha) or git(source_root, 'rev-parse', 'HEAD') != policy_sha
            or git(source_root, 'remote', 'get-url', 'origin') not in OFFICIAL_ORIGINS
            or git(source_root, 'status', '--porcelain', '--untracked-files=all')):
        raise ValueError('Masterclass policy promotion requires clean exact official GitHub source')
    environment = os.environ.copy()
    environment.pop('BIJUX_STD_ALLOW_LOCAL_SOURCE', None)
    environment['BIJUX_STD_GIT_URL'] = git(source_root, 'remote', 'get-url', 'origin')
    subprocess.run(['bash', str(source_root / 'shared/bijux-checks/scripts/verify-accepted-source.sh'),
                    str(source_root), policy_sha], check=True, env=environment)
    if read_owned(target, '.github/standards/bijux-std.sha').decode().strip() != BASELINE_SHA:
        raise ValueError('Masterclass runtime baseline is not the supported accepted source')
    baseline = accepted_baseline(source_root, target)
    _, baseline_renderer = owning_scripts(baseline)
    baseline_expected, baseline_absent = baseline_renderer.WORKFLOW_EXECUTION.verification.expected_projection(baseline, target, REPOSITORY)
    expected, absent = expected_masterclass(source_root, baseline, target, policy_sha)
    if (target / AUTHORITY_PATH).exists():
        verify_masterclass(source_root, target)
        return {'repository': REPOSITORY, 'changed_paths': [], 'authorities': read_authority(target)}
    for relative, body in baseline_expected.items():
        if body is not None and read_owned(target, relative) != body:
            raise ValueError('Masterclass baseline drift before bounded promotion: ' + relative)
    for relative in baseline_absent:
        if (target / relative).exists() or (target / relative).is_symlink():
            raise ValueError('Masterclass disabled baseline workflow is present: ' + relative)
    changed = []
    for relative, body in expected.items():
        if body is None:
            continue
        path = target / relative
        if path.exists() and read_owned(target, relative) == body:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        # read_owned rejects any existing path alias before mutation.
        if path.exists() or path.is_symlink():
            read_owned(target, relative)
        path.write_bytes(body)
        changed.append(relative)
    for relative in absent:
        if (target / relative).exists():
            raise ValueError('Masterclass promotion cannot delete an authored path: ' + relative)
    sync, _ = owning_scripts(source_root)
    sync.refresh_shared_checksums(target)
    checksum = target / '.github/bijux-std-shared.sha256'
    rows = [line.split() for line in checksum.read_text().splitlines()]
    if not any(len(row) == 2 and row[1] == AUTHORITY_PATH for row in rows):
        with checksum.open('a') as output:
            output.write(hashlib.sha256(expected[AUTHORITY_PATH]).hexdigest() + '  ' + AUTHORITY_PATH + '\n')
    sync.verify_shared_checksums(target)
    proof = verify_masterclass(source_root, target)
    return {'repository': REPOSITORY, 'changed_paths': sorted(changed), 'authorities': proof['execution_authorities']}
