"""Execute bounded release checks and authenticate complete partition evidence."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import sys
import tomllib

from .artifacts import file_digest, pack, source_files, unpack, verify_receipts, verify_sources, write_json, snapshot
from .planning import PUBLIC_DAG, digest, plan, validate

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'artifacts/release-validation'
WORKSPACE = OUT / 'workspace'
TARGET = OUT / 'target'
STARTED = time.monotonic()


def command(arguments: list[str], *, cwd: Path = WORKSPACE, capture: bool = False) -> str:
    remaining = 240 - (time.monotonic() - STARTED)
    if remaining <= 0:
        raise TimeoutError('Release verification exhausted its bounded command budget')
    environment = dict(os.environ, CARGO_TARGET_DIR=str(TARGET), CARGO_BUILD_JOBS='4',
                       CARGO_INCREMENTAL='0', CARGO_HOME=str(OUT / 'cargo-home'), PYTHONDONTWRITEBYTECODE='1',
                       PYTHONPYCACHEPREFIX=str(OUT / 'python-cache'),
                       BIJUX_DAG_BIN=str(TARGET / 'debug/bijux-dag'),
                       TMPDIR=str(OUT / 'tmp'), TMP=str(OUT / 'tmp'), TEMP=str(OUT / 'tmp'))
    (OUT / 'tmp').mkdir(parents=True, exist_ok=True)
    environment['BIJUX_DAG_BUILD_GIT_SHA'] = subprocess.check_output(
        ['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, text=True).strip()
    print('Executing:', ' '.join(arguments), flush=True)
    result = subprocess.run(arguments, cwd=cwd, env=environment, text=True, check=True,
                            stdout=subprocess.PIPE if capture else None, timeout=remaining)
    return result.stdout if capture else ''


def output(name: str, value: str) -> None:
    if '\n' in value or '\r' in value:
        raise ValueError('Workflow output must occupy one line')
    if os.environ.get('GITHUB_OUTPUT'):
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
            stream.write(name + '=' + value + '\n')


def prepare() -> None:
    if WORKSPACE.exists():
        raise ValueError('Preserve the existing candidate workspace; select an isolated run')
    version = tomllib.loads((ROOT / 'Cargo.toml').read_text())['workspace']['package']['version']
    command(['python3', '.github/scripts/prepare_release_tree.py', '--workspace-root', str(ROOT),
             '--output-dir', str(WORKSPACE), '--version', version], cwd=ROOT)
    config = WORKSPACE / '.cargo/config.toml'
    with config.open('a') as stream:
        stream.write('\n[patch.crates-io]\n')
        for package in PUBLIC_DAG:
            stream.write(package + ' = { path = "crates/' + package + '" }\n')
    boundary = json.loads((WORKSPACE / 'contracts/foundation/workspace_package_boundary.v1.json').read_text())
    public = {item['crate'] for item in boundary['packages']
              if item['product_family'] == 'bijux-dag' and item['release_status'] == 'public'}
    if public != set(PUBLIC_DAG):
        raise ValueError('Release planner must reconcile the governed public package boundary')
    metadata = json.loads(command(['cargo', 'metadata', '--locked', '--no-deps', '--all-features',
                                   '--format-version', '1'], capture=True))
    policy = json.loads((WORKSPACE / 'configs/rust/release-verification.json').read_text())
    prepared = plan(metadata, policy)
    write_json(OUT / 'plan.json', prepared)
    archive_hash = pack(WORKSPACE, OUT / 'candidate.tar.gz')
    identity = {'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'candidate_sha256': archive_hash, 'plan_sha256': file_digest(OUT / 'plan.json'),
                'lock_sha256': file_digest(WORKSPACE / 'Cargo.lock'),
                'rustc': command(['rustc', '--version', '--verbose'], capture=True).strip(),
                'python': sys.version.split()[0]}
    write_json(OUT / 'candidate.json', {'schema': 1, 'identity': identity, 'files': source_files(WORKSPACE)})
    output('candidate_sha256', archive_hash)
    output('manifest_sha256', file_digest(OUT / 'candidate.json'))
    output('plan_sha256', identity['plan_sha256'])
    output('matrix', json.dumps({'include': prepared['checks']}, separators=(',', ':')))
    print('Prepared', len(prepared['inventory']), 'Cargo targets in', len(prepared['checks']), 'checks')


def load() -> tuple[dict, dict]:
    if file_digest(OUT / 'candidate.json') != os.environ['RELEASE_MANIFEST_SHA256']:
        raise ValueError('Candidate manifest differs from its producer')
    manifest = json.loads((OUT / 'candidate.json').read_text())
    identity = manifest['identity']
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if identity['source_sha'] != head or identity['candidate_sha256'] != os.environ['RELEASE_CANDIDATE_SHA256']:
        raise ValueError('Candidate belongs to a different workflow commit')
    if identity['plan_sha256'] != os.environ['RELEASE_PLAN_SHA256'] or file_digest(OUT / 'plan.json') != identity['plan_sha256']:
        raise ValueError('Verification plan differs from its producer')
    prepared = json.loads((OUT / 'plan.json').read_text())
    validate(prepared)
    if (identity['rustc'] != command(['rustc', '--version', '--verbose'], cwd=ROOT, capture=True).strip()
            or identity['python'] != sys.version.split()[0]):
        raise ValueError('Release workers must use one exact Rust compiler')
    return manifest, prepared


def restore(manifest: dict, *, libraries: bool, binaries: bool) -> None:
    if not WORKSPACE.exists():
        unpack(OUT / 'candidate.tar.gz', WORKSPACE, manifest['identity']['candidate_sha256'])
    if libraries:
        unpack(OUT / 'libraries.tar.gz', OUT, os.environ['RELEASE_LIBRARIES_SHA256'])
    if binaries:
        unpack(OUT / 'binaries.tar.gz', OUT, os.environ['RELEASE_BINARIES_SHA256'])
    verify_sources(WORKSPACE, manifest['files'])


def warm(check: str) -> None:
    manifest, _ = load()
    restore(manifest, libraries=check == 'binaries', binaries=False)
    cache_roots = ['target', 'cargo-home/registry']
    baseline = snapshot(OUT, include=cache_roots) if check == 'binaries' else None
    if check == 'libraries':
        command(['cargo', 'test', '--workspace', '--lib', '--all-features', '--locked', '--no-run'])
    else:
        command(['cargo', 'build', '--workspace', '--bins', '--all-features', '--locked'])
    verify_sources(WORKSPACE, manifest['files'])
    archive_hash = pack(OUT, OUT / (check + '.tar.gz'), baseline=baseline, include=cache_roots)
    elapsed = time.monotonic() - STARTED
    if elapsed >= 240:
        raise TimeoutError('Compilation preparation exceeded its bounded execution budget')
    output(check + '_sha256', archive_hash)
    output('elapsed_seconds', str(round(elapsed, 3)))


def commands(check: dict) -> list[list[str]]:
    package = check['package']
    kind = check['kind']
    if kind == 'format':
        return [['cargo', 'fmt', '--all', '--', '--check']]
    if kind == 'lint':
        return [['cargo', 'clippy', '-p', package, '--all-targets', '--all-features', '--locked', '--', '-D', 'warnings']]
    if kind == 'docs':
        return [['cargo', 'doc', '-p', package, '--all-features', '--no-deps', '--locked']]
    if kind == 'tests':
        arguments = ['cargo', 'test', '-p', package, '--all-features', '--locked']
        for target in check['targets']:
            arguments.extend(target['selector'])
        return [arguments]
    if kind == 'publish':
        return [['cargo', 'publish', '-p', package, '--dry-run', '--locked']]
    if kind == 'package-contents':
        return [['cargo', 'package', '-p', package, '--list'] for package in PUBLIC_DAG]
    if kind == 'smoke':
        return [['cargo', 'test', '-p', package, '--test', 'smoke_pipeline', '--locked', '--', '--nocapture']]
    if kind == 'python-installation':
        return [['make', 'install', 'VENV=' + str(OUT / 'python-environment'),
                 'PYTHON_INSTALL_ARTIFACTS_DIR=' + str(OUT / 'python-installation')]]
    raise ValueError('Unknown release verification family: ' + kind)


def verify(check_id: str) -> None:
    manifest, prepared = load()
    matches = [check for check in prepared['checks'] if check['id'] == check_id]
    if len(matches) != 1:
        raise ValueError('Worker must name exactly one planned verification')
    check = matches[0]
    receipt = {'schema': 1, 'identity': manifest['identity'], 'check': check_id, 'status': 'failed'}
    path = OUT / 'results' / (digest(check_id) + '.json')
    try:
        restore(manifest, libraries=check['compiled'], binaries=check['compiled'])
        receipt['commands'] = commands(check)
        for arguments in receipt['commands']:
            command(arguments)
        verify_sources(WORKSPACE, manifest['files'])
        receipt['status'] = 'passed'
    except Exception as error:
        receipt['error'] = str(error)
        raise
    finally:
        receipt['elapsed_seconds'] = round(time.monotonic() - STARTED, 3)
        write_json(path, receipt)


def accept() -> None:
    manifest, prepared = load()
    if any(result != 'success' for result in json.loads(os.environ['RELEASE_JOB_RESULTS'])):
        raise ValueError('Every producer and verification matrix must finish successfully')
    for name in ('RELEASE_LIBRARIES_SECONDS', 'RELEASE_BINARIES_SECONDS'):
        if not 0 <= float(os.environ[name]) < prepared['policy']['maximum_seconds']:
            raise ValueError('Compilation producer exceeded its five-minute budget')
    records = [json.loads(path.read_text()) for path in (OUT / 'results').glob('*.json')]
    result = verify_receipts(prepared, manifest['identity'], records)
    write_json(OUT / 'acceptance.json', result)
    print(json.dumps(result, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.check == 'prepare':
        prepare()
    elif args.check == 'candidate':
        manifest, _ = load()
        restore(manifest, libraries=False, binaries=False)
    elif args.check in {'libraries', 'binaries'}:
        warm(args.check)
    elif args.check == 'accept':
        accept()
    else:
        verify(args.check)
    return 0
