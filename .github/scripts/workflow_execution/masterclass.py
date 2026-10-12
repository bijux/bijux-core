"""Promote governance and documentation while preserving the program runtime."""
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
ACTION_PIN_SOURCES = {
    'actions/upload-artifact': 'shared/bijux-gh/workflows/release-artifacts.yml',
    'actions/download-artifact': 'shared/bijux-gh/workflows/release-ghcr.yml',
    'actions/setup-node': 'shared/bijux-gh/workflows/deploy-docs.yml',
}


def action_pins(source_root: Path) -> dict[str, str]:
    """Read only the three admitted action identities from canonical templates."""
    def references(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'uses' and isinstance(child, str):
                    yield child
                else:
                    yield from references(child)
        elif isinstance(value, list):
            for child in value:
                yield from references(child)
    pins = {}
    for action, relative in ACTION_PIN_SOURCES.items():
        document = parse_workflow(read_owned(source_root, relative), relative)
        values = {ref for ref in references(document) if ref.partition('@')[0] == action}
        if len(values) != 1 or not re.fullmatch(re.escape(action) + r'@[0-9a-f]{40}', next(iter(values), '')):
            raise ValueError('Masterclass action promotion requires one canonical immutable reference: ' + action)
        pins[action] = values.pop()
    return pins


def project_action_pins(document: dict, pins: dict[str, str]) -> dict:
    """Replace finite action references without altering workflow behavior."""
    prepared = copy.deepcopy(document)
    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'uses' and isinstance(child, str) and child.partition('@')[0] in pins:
                    value[key] = pins[child.partition('@')[0]]
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(prepared)
    return prepared


def accepted_policy(source_root: Path, target: Path, policy_sha: str) -> Path:
    """Fetch the previous authority before admitting its existing projection."""
    from .source_authority import git, OFFICIAL_ORIGINS
    cache_root = target / 'artifacts/masterclass-policy-source'
    cache = cache_root / policy_sha
    if (target / 'artifacts').is_symlink() or cache_root.is_symlink() or cache.is_symlink():
        raise ValueError('Masterclass policy cache must be owned by this checkout')
    if not cache.exists():
        cache.mkdir(parents=True)
        subprocess.run(['git', '-C', str(cache), 'init', '--quiet'], check=True)
        subprocess.run(['git', '-C', str(cache), 'remote', 'add', 'origin', 'https://github.com/bijux/bijux-std.git'], check=True)
        subprocess.run(['git', '-C', str(cache), 'fetch', '--quiet', '--depth', '1', 'origin', policy_sha], check=True)
        subprocess.run(['git', '-C', str(cache), 'checkout', '--quiet', '--detach', policy_sha], check=True)
    if (Path(git(cache, 'rev-parse', '--show-toplevel')).resolve() != cache.resolve()
            or git(cache, 'rev-parse', 'HEAD') != policy_sha
            or git(cache, 'remote', 'get-url', 'origin') not in OFFICIAL_ORIGINS
            or git(cache, 'status', '--porcelain', '--untracked-files=all')):
        raise ValueError('Masterclass previous policy is not clean exact official source')
    environment = os.environ.copy()
    environment.pop('BIJUX_STD_ALLOW_LOCAL_SOURCE', None)
    environment['BIJUX_STD_GIT_URL'] = git(cache, 'remote', 'get-url', 'origin')
    subprocess.run(['bash', str(source_root / 'shared/bijux-checks/scripts/verify-accepted-source.sh'),
                    str(cache), policy_sha], check=True, env=environment)
    return cache


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


GITHUB_SOURCE = 'shared/bijux-gh'
GITHUB_DESTINATION = '.bijux/shared/bijux-gh/'
DOCS_PIN_PATH = '.github/standards/bijux-docs.sha'
DOCS_DESTINATION = '.bijux/shared/bijux-docs/'


def baseline_github_tree(baseline: Path) -> dict[str, bytes]:
    """Own the complete retained GitHub tree, including non-workflow inputs."""
    directory = baseline / GITHUB_SOURCE
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Masterclass GitHub baseline requires its regular source directory')
    prepared = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError('Masterclass GitHub baseline cannot contain path aliases')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError('Masterclass GitHub baseline requires regular files')
        relative = path.relative_to(baseline).as_posix()
        prepared['.bijux/' + relative] = read_owned(baseline, relative)
    return prepared


def verify_github_tree(target: Path, expected: dict[str, bytes]) -> None:
    """Reject uncovered GitHub paths before a projection can replace any bytes."""
    wanted = {path: body for path, body in expected.items() if path.startswith(GITHUB_DESTINATION)}
    directory = target / GITHUB_DESTINATION
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Masterclass GitHub projection requires its regular source directory')
    actual = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError('Masterclass GitHub projection cannot contain path aliases')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError('Masterclass GitHub projection requires regular files')
        relative = path.relative_to(target).as_posix()
        actual[relative] = read_owned(target, relative)
    if actual != wanted:
        differences = sorted(path for path in set(actual) | set(wanted) if actual.get(path) != wanted.get(path))
        raise ValueError('noncanonical complete Masterclass GitHub projection: ' + ', '.join(differences))


def documentation_authority(source_root: Path, target: Path, policy_sha: str) -> tuple[Path, str]:
    """Resolve documentation from its independently accepted exact source pin."""
    sha = read_owned(target, DOCS_PIN_PATH).decode().strip()
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Masterclass documentation requires a full lowercase source SHA')
    if sha == policy_sha:
        return source_root, sha
    from .source_authority import git
    git(target, 'ls-files', '--error-unmatch', DOCS_PIN_PATH)
    return accepted_policy(source_root, target, sha), sha


def verify_documentation_tree(target: Path, expected: dict[str, bytes]) -> None:
    """Reject uncovered documentation bytes under the retained exact authority."""
    wanted = {path: body for path, body in expected.items() if path.startswith(DOCS_DESTINATION)}
    directory = target / DOCS_DESTINATION
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Masterclass documentation requires its regular source directory')
    actual = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError('Masterclass documentation cannot contain path aliases')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError('Masterclass documentation requires regular files')
        relative = path.relative_to(target).as_posix()
        actual[relative] = read_owned(target, relative)
    if actual != wanted:
        raise ValueError('noncanonical complete Masterclass documentation projection')


def expected_masterclass(source_root: Path, baseline: Path, target: Path, policy_sha: str,
                         *, documentation_root: Path | None = None,
                         documentation_sha: str | None = None) -> tuple[dict, set]:
    """Advance only governance and docs; complementary programs keep their baseline."""
    _, baseline_renderer = owning_scripts(baseline)
    original, absent = baseline_renderer.WORKFLOW_EXECUTION.verification.expected_projection(baseline, target, REPOSITORY)
    prepared = copy.deepcopy(original)
    prepared.update(baseline_github_tree(baseline))
    _, renderer = owning_scripts(source_root)
    manifest = json.loads(read_owned(baseline, '.github/standards/repo-config.manifest.json'))
    current_manifest = json.loads(read_owned(source_root, '.github/standards/repo-config.manifest.json'))
    current_entries = {repo['name']: repo for repo in current_manifest['repositories']}
    for repo in manifest['repositories']:
        current = current_entries[repo['name']]
        repo.setdefault('workflow_execution_policy', {}).setdefault('publication_entrypoints', {})['deploy-docs'] = copy.deepcopy(
            current['workflow_execution_policy']['publication_entrypoints']['deploy-docs'])
        repo['workflow_allowlist'] = sorted(set(repo['workflow_allowlist']) | {'deploy-docs'})
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
    pins = action_pins(source_root)
    for relative, body in tuple(prepared.items()):
        if not relative.startswith('.github/workflows/') or body is None:
            continue
        identity = relative.rsplit('/', 1)[-1].removesuffix('.yml')
        if identity == 'deploy-docs':
            continue
        if identity == 'automerge-pr':
            prepared[relative] = read_owned(source_root, '.github/workflows/automerge-pr.yml')
            continue
        document = parse_workflow(body, identity)
        projected = project_action_pins(project_dependency_pull_requests(identity, document, POLICY), pins)
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
    current_projection, _ = renderer.WORKFLOW_EXECUTION.verification.expected_projection(source_root, target, REPOSITORY)
    for relative in ('.github/workflows/deploy-docs.yml', '.bijux/shared/bijux-gh/workflows/deploy-docs.yml',
                     '.bijux/shared/bijux-gh/scripts/publication_admission.py'):
        prepared[relative] = current_projection[relative]
    if (documentation_root is None) != (documentation_sha is None):
        raise ValueError('Masterclass documentation source requires a complete authority pair')
    documentation_root = source_root if documentation_root is None else documentation_root
    documentation_sha = policy_sha if documentation_sha is None else documentation_sha
    if not re.fullmatch(r'[0-9a-f]{40}', documentation_sha):
        raise ValueError('Masterclass documentation requires a full lowercase source SHA')
    docs_root = documentation_root / 'shared/bijux-docs'
    if docs_root.is_symlink() or not docs_root.is_dir():
        raise ValueError('Masterclass documentation requires its regular source directory')
    for path in sorted(docs_root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Masterclass documentation source cannot contain path aliases')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError('Masterclass documentation source requires regular files')
        relative = path.relative_to(documentation_root).as_posix()
        prepared['.bijux/' + relative] = read_owned(documentation_root, relative)
    prepared[DOCS_PIN_PATH] = (documentation_sha + '\n').encode()
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
    docs_root, docs_sha = documentation_authority(source_root, target, authority['execution_policy_sha'])
    expected, absent = expected_masterclass(source_root, baseline, target, authority['execution_policy_sha'],
                                           documentation_root=docs_root, documentation_sha=docs_sha)
    verify_github_tree(target, expected)
    verify_documentation_tree(target, expected)
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
    final_docs_root, final_docs_sha = documentation_authority(source_root, target, authority['execution_policy_sha'])
    current, current_absent = expected_masterclass(source_root, baseline, target, authority['execution_policy_sha'],
                                                 documentation_root=final_docs_root, documentation_sha=final_docs_sha)
    if (final_docs_root, final_docs_sha) != (docs_root, docs_sha):
        failures.append('Masterclass documentation authority changed during verification')
    if current != expected or current_absent != absent or read_authority(target) != authority:
        failures.append('Masterclass source authority changed during verification')
    if failures:
        raise ValueError('\n'.join(failures))
    return {'repository': REPOSITORY, 'verified_files': verified, 'absent_paths': sorted(absent),
            'mutated_product': False, 'execution_authorities': authority}


def admit_previous_projection(source_root: Path, target: Path) -> Path:
    """Require the old marker and every managed byte to match its own authority."""
    authority = read_authority(target)
    previous = accepted_policy(source_root, target, authority["execution_policy_sha"])
    _, previous_renderer = owning_scripts(previous)
    previous_renderer.WORKFLOW_EXECUTION.masterclass.verify_masterclass(previous, target)
    return previous


def promote_masterclass(source_root: Path, target: Path, policy_sha: str, *, keep_documentation: bool = False) -> dict:
    """Promote accepted governance and docs without advancing the program baseline."""
    if type(keep_documentation) is not bool:
        raise ValueError('Masterclass documentation preservation must be explicit boolean selection')
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
    previous = None
    if (target / AUTHORITY_PATH).exists():
        authority = read_authority(target)
        if (authority['execution_policy_sha'] == policy_sha
                and (keep_documentation or read_owned(target, DOCS_PIN_PATH).decode().strip() == policy_sha)):
            verify_masterclass(source_root, target)
            return {'repository': REPOSITORY, 'changed_paths': [], 'authorities': authority}
        previous = admit_previous_projection(source_root, target)
    docs_root, docs_sha = (documentation_authority(source_root, target, policy_sha)
                           if keep_documentation else (source_root, policy_sha))
    expected, absent = expected_masterclass(source_root, baseline, target, policy_sha,
                                           documentation_root=docs_root, documentation_sha=docs_sha)
    github_preimage = baseline_github_tree(baseline)
    if previous is None:
        previous_expected = baseline_expected
    else:
        _, previous_renderer = owning_scripts(previous)
        if read_owned(target, DOCS_PIN_PATH).decode().strip() == authority['execution_policy_sha']:
            previous_expected, _ = previous_renderer.WORKFLOW_EXECUTION.masterclass.expected_masterclass(
                previous, baseline, target, authority['execution_policy_sha'])
        else:
            previous_docs_root, previous_docs_sha = documentation_authority(previous, target, authority['execution_policy_sha'])
            previous_expected, _ = previous_renderer.WORKFLOW_EXECUTION.masterclass.expected_masterclass(
                previous, baseline, target, authority['execution_policy_sha'],
                documentation_root=previous_docs_root, documentation_sha=previous_docs_sha)
    github_preimage.update({path: body for path, body in previous_expected.items()
                           if path.startswith(GITHUB_DESTINATION) and body is not None})
    verify_github_tree(target, github_preimage)
    for relative, body in (() if previous is not None else baseline_expected.items()):
        if body is not None and read_owned(target, relative) != body:
            raise ValueError('Masterclass baseline drift before bounded promotion: ' + relative)
    for relative in (() if previous is not None else baseline_absent):
        if (target / relative).exists() or (target / relative).is_symlink():
            raise ValueError('Masterclass disabled baseline workflow is present: ' + relative)
    if keep_documentation:
        verify_documentation_tree(target, expected)
        if read_owned(target, DOCS_PIN_PATH).decode().strip() != docs_sha:
            raise ValueError('Masterclass retained documentation pin changed before promotion')
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
    covered = {row[1] for row in rows if len(row) == 2}
    with checksum.open('a') as output:
        for relative, body in sorted(expected.items()):
            if body is not None and relative not in covered:
                output.write(hashlib.sha256(body).hexdigest() + '  ' + relative + '\n')
    sync.verify_shared_checksums(target)
    proof = verify_masterclass(source_root, target)
    return {'repository': REPOSITORY, 'changed_paths': sorted(changed), 'authorities': proof['execution_authorities']}
