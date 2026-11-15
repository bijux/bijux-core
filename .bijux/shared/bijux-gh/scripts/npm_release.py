#!/usr/bin/env python3
"""Inspect an accepted workflow's npm archives and publish only those frozen bytes."""
from __future__ import annotations

import argparse
import base64
import hashlib
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import runpy
import subprocess
import tarfile

REGISTRY = 'https://registry.npmjs.org'
MAX_UNCOMPRESSED = 512*1024*1024
VERSION = re.compile(r'(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?')
NAME = re.compile(r'(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run(command):
    return subprocess.run(command, text=True, capture_output=True, check=True, timeout=120).stdout


def api(path):
    return json.loads(run(['gh', 'api', '--header', 'X-GitHub-Api-Version: 2022-11-28', path]))


def configuration(root, repository):
    manifest = json.loads((root/'.github/standards/repo-config.manifest.json').read_text())
    entries = [r for r in manifest['repositories'] if 'bijux/'+r['name'] == repository]
    require(len(entries) == 1, 'Expected one canonical repository declaration')
    entry = entries[0]
    require('release-npm' in entry.get('workflow_allowlist', []), 'npm is not an applicable capability')
    values = {value['key']: value['value'] for value in entry['release_env']}
    require(values.get('BIJUX_NPM_ENABLED') is True, 'npm publication is disabled in accepted configuration')
    packages = values.get('BIJUX_NPM_PACKAGES_JSON')
    version = values.get('BIJUX_NPM_RELEASE_VERSION')
    require(isinstance(version, str) and VERSION.fullmatch(version), 'Invalid repository release version')
    require(isinstance(packages, list) and packages and len(packages) <= 50, 'Expected a bounded nonempty package set')
    names = set()
    for package in packages:
        require(isinstance(package, dict) and set(package) == {'name','version','directory'}, 'Invalid npm package declaration')
        name, version, directory = package['name'], package['version'], package['directory']
        require(isinstance(name, str) and NAME.fullmatch(name) and name not in names, 'Invalid or duplicate package identity')
        require(isinstance(version, str) and VERSION.fullmatch(version), 'Invalid immutable npm version')
        require(isinstance(directory, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]*', directory), 'Invalid package directory')
        names.add(name)
    return values, packages


def validate_run(value, repository, commit, workflow, run_id=None):
    require(type(workflow.get('id')) is int and workflow['id'] > 0 and
            workflow.get('path') == '.github/workflows/package-candidate.yml' and
            type(value.get('id')) is int and value['id'] > 0 and
            (run_id is None or value['id'] == run_id) and value.get('repository', {}).get('full_name') == repository and
            value.get('head_repository', {}).get('full_name') == repository and
            value.get('head_sha') == commit and value.get('head_branch') == 'main' and
            value.get('event') == 'workflow_dispatch' and value.get('status') == 'completed' and
            value.get('conclusion') == 'success' and value.get('workflow_id') == workflow.get('id'),
            'Candidate must be a successful same-repository manual workflow at exact accepted main')


def validate_archive(path, expected, repository):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 128*1024*1024, 'Invalid bounded package archive')
    data = path.read_bytes()
    integrity = 'sha512-'+base64.b64encode(hashlib.sha512(data).digest()).decode()
    with gzip.GzipFile(fileobj=io.BytesIO(data), mode='rb') as source:
        raw = source.read(MAX_UNCOMPRESSED+1)
    require(len(raw) <= MAX_UNCOMPRESSED, 'Package archive exceeds decompression budget')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        seen, metadata = set(), None
        for member in archive:
            name = PurePosixPath(member.name)
            require(len(seen) < 10000 and not name.is_absolute() and name.parts and name.parts[0] == 'package' and
                    str(name) == member.name and '..' not in name.parts and '\\' not in member.name and '\0' not in member.name and
                    member.name not in seen and member.isfile(), 'Package entries must be distinct confined regular files')
            seen.add(member.name)
            if member.name == 'package/package.json':
                require(member.size <= 128*1024, 'Package metadata exceeds inspection budget')
                metadata = archive.extractfile(member).read()
        require(metadata is not None, 'Package metadata missing')
        package = json.loads(metadata)
    require(package.get('name') == expected['name'] and package.get('version') == expected['version'] and
            package.get('private') is not True, 'Archive identity differs from the declared release')
    require(package.get('publishConfig', {}).get('access') == 'public' and
            package.get('publishConfig', {}).get('registry', REGISTRY).rstrip('/') == REGISTRY and
            package.get('publishConfig', {}).get('provenance') is not False,
            'Expected explicit public npm registry metadata')
    require(package.get('repository') == {'type':'git','url':'git+https://github.com/'+repository+'.git',
                                         'directory':'packages/'+expected['directory']}, 'Archive repository provenance differs')
    for field in ['dependencies','optionalDependencies','peerDependencies','devDependencies']:
        values = package.get(field, {})
        require(isinstance(values, dict) and all(isinstance(v,str) and not re.match(r'^(?:workspace|file|link):',v) for v in values.values()),
                'Unpublishable package dependency')
    return {'name':package['name'],'version':package['version'],'directory':expected['directory'],
            'archive':str(path.resolve()),'sha256':hashlib.sha256(data).hexdigest(),'integrity':integrity,
            'dependencies':package.get('dependencies',{})}


def inspect_archives(root, destination, packages, repository, commit):
    require((destination/'reports/candidate-commit.txt').read_text().strip() == commit, 'Candidate source receipt differs')
    tree = run(['git','rev-parse','HEAD^{tree}']).strip()
    require((destination/'reports/candidate-tree.txt').read_text().strip() == tree, 'Candidate tree receipt differs')
    require((destination/'reports/package-lock.sha256').read_text().split()[0] == hashlib.sha256((root/'package-lock.json').read_bytes()).hexdigest(),
            'Candidate lock receipt differs')
    records = json.loads((destination/'packages/manifest.json').read_text())
    require(isinstance(records,list) and [p.get('name') for p in records] == [p['name'] for p in packages],
            'Candidate package order or set differs')
    expected_versions = {p['name']:p['version'] for p in packages}
    inspected, published = [], set()
    for record, expected in zip(records,packages):
        filename = PurePosixPath(record['archive']).name
        require(re.fullmatch(r'[a-zA-Z0-9._-]+\.tgz', filename), 'Invalid archive filename')
        actual = validate_archive(destination/'packages'/filename, expected, repository)
        require(actual['sha256'] == record.get('sha256') and actual['integrity'] == record.get('integrity') and
                actual['dependencies'] == record.get('dependencies'), 'Candidate archive digest or dependencies differ')
        for name, version in actual['dependencies'].items():
            if name in expected_versions:
                require(name in published and version == expected_versions[name], 'Packages must precede exact dependent versions')
        actual['archive']=str(Path(actual['archive']).relative_to(root))
        inspected.append(actual)
        published.add(actual['name'])
    return inspected


def prepare(root, repository, commit, tag, run_id):
    require(re.fullmatch(r'[0-9a-f]{40}', commit) and str(run_id).isdigit() and int(run_id)>0, 'Expected immutable source and numeric workflow run')
    values, packages = configuration(root, repository)
    require(tag == 'v'+values['BIJUX_NPM_RELEASE_VERSION'], 'Release tag differs from accepted package cohort')
    require(run(['git','rev-parse','HEAD']).strip() == commit, 'Checkout differs from accepted publication source')
    prefix = 'repos/'+repository
    workflow = api(prefix+'/actions/workflows/package-candidate.yml')
    candidate = api(prefix+'/actions/runs/'+str(run_id))
    validate_run(candidate,repository,commit,workflow,int(run_id))
    destination = root/'artifacts/publication/npm-candidate'
    destination.mkdir(parents=True,exist_ok=False)
    artifact_name = 'unpublished-package-candidate-'+commit
    run(['gh','run','download',str(run_id),'--repo',repository,'--name',artifact_name,'--dir',str(destination)])
    inspected = inspect_archives(root,destination,packages,repository,commit)
    receipt = {'repository':repository,'commit':commit,'tag':tag,'candidate_run':int(run_id),'artifact':artifact_name,
               'packages':inspected,'registry':REGISTRY,'remote_writes':False}
    target = root/'artifacts/publication/npm-plan.json'
    target.write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def registry_integrity(name, version):
    result = subprocess.run(['npm','view',name+'@'+version,'dist.integrity','--json','--registry',REGISTRY],
                            text=True,capture_output=True,timeout=120)
    if result.returncode == 0:
        value = json.loads(result.stdout)
        require(isinstance(value,str) and value.startswith('sha512-'), 'Registry omitted immutable integrity')
        return value
    try:
        code = json.loads(result.stdout)['error']['code']
    except (ValueError,KeyError,TypeError):
        raise ValueError('Registry lookup failed without a structured missing-version response') from None
    require(code == 'E404', 'Registry lookup failed; authentication/network errors are not missing releases')
    return None


def publish(root, repository, commit, tag):
    values, packages = configuration(root,repository)
    require(tag == 'v'+values['BIJUX_NPM_RELEASE_VERSION'], 'Publisher tag differs from accepted release version')
    path = root/'artifacts/publication/npm-plan.json'
    plan = json.loads(path.read_text())
    require((plan.get('repository'),plan.get('commit'),plan.get('tag'),plan.get('registry')) ==
            (repository,commit,tag,REGISTRY), 'Frozen publication plan differs from request')
    require(run(['git','rev-parse','HEAD']).strip() == commit, 'Publisher source differs')
    actual = inspect_archives(root,root/'artifacts/publication/npm-candidate',packages,repository,commit)
    require(actual == plan['packages'], 'Package bytes changed after inspection')
    # Re-admit remote source/check/tag identity after candidate download and before writes.
    admission = runpy.run_path(str(root/'.bijux/shared/bijux-gh/scripts/publication_admission.py'))
    admission['admit'](dict(os.environ))
    receipt = {**plan,'packages':[],'remote_writes':False,'complete':False}
    target = root/'artifacts/publication/npm-receipt.json'
    target.write_text(json.dumps(receipt,indent=2)+'\n')
    for package in actual:
        entry = {**package,'state':'checking-registry'}
        receipt['packages'].append(entry)
        target.write_text(json.dumps(receipt,indent=2)+'\n')
        current = registry_integrity(package['name'],package['version'])
        if current is not None:
            require(current == package['integrity'], 'Existing immutable version contains different bytes')
            state = 'already-present-identical'
        else:
            admission['admit'](dict(os.environ))
            entry['state']='publication-attempted'
            receipt['remote_writes']=None
            target.write_text(json.dumps(receipt,indent=2)+'\n')
            run(['npm','publish',package['archive'],'--access','public','--registry',REGISTRY,'--ignore-scripts'])
            receipt['remote_writes'] = True
            state = 'published'
            entry['state']='published-awaiting-verification'
            target.write_text(json.dumps(receipt,indent=2)+'\n')
        require(registry_integrity(package['name'],package['version']) == package['integrity'], 'Published integrity does not match the inspected archive')
        entry['state']=state
        target.write_text(json.dumps(receipt,indent=2)+'\n')
    receipt['complete'] = True
    target.write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['prepare','publish'])
    parser.add_argument('--candidate-run')
    args=parser.parse_args()
    root=Path.cwd()
    environment=dict(os.environ)
    repository=environment['PUBLICATION_REPOSITORY']
    commit=environment['PUBLICATION_COMMIT']
    tag=environment['PUBLICATION_TAG']
    result=(prepare(root,repository,commit,tag,args.candidate_run) if args.operation=='prepare'
            else publish(root,repository,commit,tag))
    print('npm '+args.operation+' completed for '+repository+' at '+commit)
