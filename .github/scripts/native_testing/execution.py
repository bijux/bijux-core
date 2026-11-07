"""Run bounded native compilation, Nextest partitions and Python coverage."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from verification.artifacts import file_digest, pack, snapshot, source_files, unpack, verify_receipts, verify_sources, write_json
from verification.planning import digest
from .planning import catalogue, case_totals, plan, validate

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'artifacts/native-tests'
TARGET = OUT / 'target'
STARTED = time.monotonic()


def command(arguments: list[str], *, capture=False) -> str:
    remaining = 240 - (time.monotonic() - STARTED)
    if remaining <= 0:
        raise TimeoutError('Native verification exhausted its bounded command budget')
    temporary = OUT / 'tmp';temporary.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, CARGO_TARGET_DIR=str(TARGET), CARGO_HOME=str(OUT / 'cargo-home'),
                       CARGO_BUILD_JOBS='4', CARGO_INCREMENTAL='0', PYTHONDONTWRITEBYTECODE='1',
                       RS_TARGET_DIR=str(TARGET), RS_CARGO_HOME=str(OUT / 'cargo-home'),
                       RS_TMP_DIR=str(temporary), RS_NEXTEST_CACHE_DIR=str(OUT / 'nextest-cache'),
                       RS_NEXTEST_CONFIG_HOME=str(OUT / 'nextest-config'),
                       PYTHONPYCACHEPREFIX=str(OUT / 'python-cache'),
                       BIJUX_DAG_BIN=str(TARGET / 'debug/bijux-dag'),
                       BIJUX_DEV_CLI_BIN=str(TARGET / 'debug/bijux-dev-cli'),
                       NEXTEST_CACHE_DIR=str(OUT / 'nextest-cache'),
                       XDG_CONFIG_HOME=str(OUT / 'nextest-config'),
                       TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))
    if arguments[:2] != ['make', 'test-py']:
        environment['NEXTEST_PROFILE_FAST'] = 'ci'
    environment['BIJUX_DAG_BUILD_GIT_SHA'] = subprocess.check_output(
        ['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, text=True).strip()
    print('Executing:', ' '.join(arguments), flush=True)
    result = subprocess.run(arguments, cwd=ROOT, env=environment, text=True, check=True,
                            stdout=subprocess.PIPE if capture else None, timeout=remaining)
    return result.stdout if capture else ''


def output(name, value):
    if '\n' in value or '\r' in value:
        raise ValueError('Workflow output must occupy one line')
    if os.environ.get('GITHUB_OUTPUT'):
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:stream.write(name + '=' + value + '\n')


def filter_expression():
    return command(['make', '-s', '--no-print-directory', 'gh-test-filter'], capture=True).strip()


def prepare():
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('Native verification must inventory a clean committed checkout')
    metadata = json.loads(command(['cargo', 'metadata', '--locked', '--no-deps',
                                   '--all-features', '--format-version', '1'], capture=True))
    policy = json.loads((ROOT / 'configs/rust/native-testing.json').read_text())
    prepared = plan(metadata, policy, filter_expression())
    write_json(OUT / 'plan.json', prepared)
    identity = {'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'lock_sha256': file_digest(ROOT / 'Cargo.lock'), 'plan_sha256': file_digest(OUT / 'plan.json'),
                'rustc': command(['rustc', '--version', '--verbose'], capture=True).strip(),
                'python': sys.version.split()[0]}
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT, text=True).split('\0')
    write_json(OUT / 'manifest.json', {'schema': 1, 'identity': identity,
                                       'files': source_files(ROOT, paths=[path for path in tracked if path])})
    output('manifest_sha256', file_digest(OUT / 'manifest.json'))
    output('plan_sha256', identity['plan_sha256'])
    output('matrix', json.dumps({'include': [check for check in prepared['checks'] if check['kind'] == 'tests']}, separators=(',', ':')))
    print('Prepared', len(prepared['inventory']), 'native Cargo targets and full Python coverage')


def load():
    if file_digest(OUT / 'manifest.json') != os.environ['NATIVE_MANIFEST_SHA256']:
        raise ValueError('Native manifest differs from its producer')
    manifest = json.loads((OUT / 'manifest.json').read_text());identity = manifest['identity']
    if (identity['source_sha'] != subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
            or identity['lock_sha256'] != file_digest(ROOT / 'Cargo.lock')
            or identity['plan_sha256'] != os.environ['NATIVE_PLAN_SHA256']
            or identity['plan_sha256'] != file_digest(OUT / 'plan.json')
            or identity['rustc'] != command(['rustc', '--version', '--verbose'], capture=True).strip()
            or identity['python'] != sys.version.split()[0]):
        raise ValueError('Native workers must authenticate one commit, lock, plan and compiler')
    prepared = json.loads((OUT / 'plan.json').read_text());validate(prepared)
    if filter_expression() != prepared['nextest_filter']:
        raise ValueError('Native worker changed the canonical Nextest selection')
    return manifest, prepared


def restore(manifest, layers):
    for layer in layers:
        unpack(OUT / (layer + '.tar.gz'), OUT, os.environ['NATIVE_' + layer.upper() + '_SHA256'])
    verify_sources(ROOT, manifest['files'])
    if layers:
        for relative in ['artifacts/target', 'artifacts/rust/target']:
            path = ROOT / relative;path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() and not path.is_symlink():
                path.symlink_to(os.path.relpath(TARGET, path.parent), target_is_directory=True)
            if not path.is_symlink() or path.resolve() != TARGET.resolve():
                raise ValueError('Nested native builds cannot replace unrelated artifact directories')


def compile_inputs(kind):
    manifest, prepared = load();restore(manifest, [] if kind == 'libraries' else ['libraries'])
    included = ['target', 'cargo-home/registry']
    baseline = snapshot(OUT, include=included) if kind != 'libraries' else None
    if kind == 'libraries':
        arguments = ['cargo', 'test', '--workspace', '--all-features', '--locked', '--no-run', *prepared['warm_selectors']]
    elif kind == 'binaries':
        arguments = ['cargo', 'build', '--workspace', '--bins', '--all-features', '--locked']
    else:
        arguments = ['cargo', 'build', '--locked', '-p', 'bijux-dev', '--bin', 'bijux-dev-cli',
                     '-p', 'bijux-dag-cli', '--bin', 'bijux-dag', '-p', 'bijux-cli', '--bin', 'bijux']
    command(arguments);verify_sources(ROOT, manifest['files'])
    archive_hash = pack(OUT, OUT / (kind + '.tar.gz'), baseline=baseline, include=included)
    elapsed = time.monotonic() - STARTED
    if elapsed >= 240:raise TimeoutError('Native compilation exceeded its bounded execution budget')
    output('sha256', archive_hash);output('elapsed_seconds', str(round(elapsed, 3)))


def rust_arguments(check, prepared, *, listing=False):
    arguments = ['cargo', 'nextest', 'list' if listing else 'run', '--workspace', '--all-features',
                 '--locked', '--config-file', 'configs/rust/nextest.toml', '--profile', prepared['nextest_profile'],
                 '--target-dir', str(TARGET), '-E', prepared['nextest_filter']]
    for flags in dict.fromkeys(tuple(target['selector']) for target in check['targets']):arguments.extend(flags)
    if listing:arguments.extend(['--message-format', 'json'])
    else:arguments.extend(['--status-level', 'all', '--final-status-level', 'all'])
    return arguments


def python_arguments():
    return ['make', 'test-py', 'VENV=' + str(OUT / 'python-environment'),
            'PYTHON_INSTALL_ARTIFACTS_DIR=' + str(OUT / 'python-installation'),
            'PYTHON_BYTECODE_DIR=' + str(OUT / 'python-cache'),
            'TEST_ARTIFACTS_DIR=' + str(OUT / 'python-test'),
            'PY_RUNTIME_BIN=' + str(TARGET / 'debug/bijux'),
            'PY_DAG_RUNTIME_BIN=' + str(TARGET / 'debug/bijux-dag')]


def verify(check_id):
    manifest, prepared = load();matches = [check for check in prepared['checks'] if check['id'] == check_id]
    if len(matches) != 1:raise ValueError('Native worker must own exactly one planned check')
    check = matches[0];record = {'schema': 1, 'identity': manifest['identity'], 'check': check_id, 'status': 'failed'}
    try:
        layers = ['libraries', 'tools'] if check['kind'] == 'python' else ['libraries', 'binaries', 'tools']
        restore(manifest, layers)
        if check['kind'] == 'tests':
            version = command(['cargo', 'nextest', '--version'], capture=True).split()
            if version[:2] != ['cargo-nextest', prepared['nextest_version']]:raise ValueError('Native test executor version differs')
            listed = json.loads(command(rust_arguments(check, prepared, listing=True), capture=True))
            record.update(catalogue(check, listed));arguments = rust_arguments(check, prepared)
            if not record['selected_cases']:
                arguments.extend(['--no-tests', 'pass'])
            record['commands'] = [arguments];command(arguments)
        else:
            arguments = python_arguments();record['commands'] = [arguments];command(arguments)
            suites = ET.parse(OUT / 'python-test/junit.xml').getroot()
            rows = [suites] if suites.tag == 'testsuite' else list(suites.iter('testsuite'))
            count = sum(int(row.get('tests', '0')) for row in rows)
            if count <= 0 or any(int(row.get('failures', '0')) or int(row.get('errors', '0')) for row in rows):
                raise ValueError('Python verification requires nonempty passing JUnit evidence')
            record['python_cases'] = count
        verify_sources(ROOT, manifest['files']);record['status'] = 'passed'
    except Exception as error:
        record['error'] = str(error);raise
    finally:
        record['elapsed_seconds'] = round(time.monotonic() - STARTED, 3)
        write_json(OUT / 'results' / (digest(check_id) + '.json'), record)


def accept():
    manifest, prepared = load();results = json.loads(os.environ['NATIVE_JOB_RESULTS'])
    if len(results) != 6 or any(result != 'success' for result in results):
        raise ValueError('Every native producer, Rust matrix and Python worker must pass')
    for kind in ['LIBRARIES', 'BINARIES', 'TOOLS']:
        if not 0 <= float(os.environ['NATIVE_' + kind + '_SECONDS']) < 300:
            raise ValueError('Native compilation producer exceeded the five-minute budget')
    records = [json.loads(path.read_text()) for path in (OUT / 'results').glob('*.json')]
    result = verify_receipts(prepared, manifest['identity'], records);result.update(case_totals(records))
    python = next(record for record in records if record['check'] == 'python')
    if python.get('python_cases', 0) <= 0:raise ValueError('Passing Python coverage evidence is required')
    result['python_cases'] = python['python_cases'];write_json(OUT / 'acceptance.json', result)
    print(json.dumps(result, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--check', required=True)
    check = parser.parse_args().check;OUT.mkdir(parents=True, exist_ok=True)
    if check == 'prepare':prepare()
    elif check in ['libraries', 'binaries', 'tools']:compile_inputs(check)
    elif check == 'accept':accept()
    else:verify(check)
    return 0
