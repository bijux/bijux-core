#!/usr/bin/env python3
"""Account for committed, projected and served shared payloads without network inference."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import zlib

ORIGIN = 'https://github.com/bijux/bijux-std.git'
PREFERRED_LOGO = 'assets/bijux_logo.png'
COMPATIBILITY_LOGO = 'assets/bijux_logo_hq.png'
PREFERRED_LOGO_LIMIT = 32 * 1024


def byte_quantity(value: int | None, basis: str) -> dict:
    """An observed zero is a value; an unobserved quantity is never zero."""
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError('Byte quantities require a nonnegative integer or unknown')
    return {'value': value, 'unit': 'bytes', 'availability': 'unobserved' if value is None else 'observed', 'basis': basis}


def fingerprint(data: bytes) -> dict:
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def relative_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Owned paths require a nonempty relative POSIX spelling')
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(part in ('.', '..') for part in path.parts):
        raise ValueError('Owned paths must be canonical and remain inside their root')
    return path


def regular_file(root: Path, value: str) -> Path:
    path = root
    for part in relative_path(value).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f'Owned file cannot use a symlink: {value}')
    if not path.is_file():
        raise ValueError(f'Missing owned file: {value}')
    return path


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=False)
    if result.returncode:
        raise ValueError('Committed standard source is unavailable: ' + result.stderr.decode(errors='replace').strip())
    return result.stdout


def source_identity(root: Path, sha: str) -> dict:
    if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Select an exact full standard commit SHA')
    if Path(_git(root, 'rev-parse', '--show-toplevel').decode().strip()).resolve() != root:
        raise ValueError('Standard root must identify its repository root')
    origin = _git(root, 'remote', 'get-url', 'origin').decode().strip()
    if origin not in (ORIGIN, 'git@github.com:bijux/bijux-std.git'):
        raise ValueError('Standard source must retain the Bijux GitHub origin')
    actual = _git(root, 'rev-parse', sha + '^{commit}').decode().strip()
    if actual != sha:
        raise ValueError('Standard source commit differs from the exact selection')
    return {'origin': ORIGIN, 'sha': sha, 'tree': _git(root, 'rev-parse', sha + '^{tree}').decode().strip(),
            'authority': 'selected committed Git objects; remote acceptance is a separate obligation'}


def committed_file(root: Path, sha: str, name: str) -> bytes:
    relative_path(name)
    return _git(root, 'show', sha + ':shared/bijux-docs/' + name)


def unique_json(data: bytes) -> dict:
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError(f'Duplicate evidence field: {key}')
            value[key] = item
        return value
    value = json.loads(data, object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError('Evidence requires a JSON object')
    return value


def png_dimensions(data: bytes) -> list[int]:
    if (len(data) < 33 or data[:8] != b'\x89PNG\r\n\x1a\n' or
            struct.unpack('>I', data[8:12])[0] != 13 or data[12:16] != b'IHDR' or
            zlib.crc32(data[12:29]) != struct.unpack('>I', data[29:33])[0]):
        raise ValueError('Preferred logo requires a valid PNG IHDR')
    return list(struct.unpack('>II', data[16:24]))


def qualify(repo: Path, site: Path, standard: Path, sha: str) -> dict:
    repo, site, standard = repo.resolve(), site.resolve(), standard.resolve()
    if not site.is_relative_to(repo / 'artifacts') or not site.is_dir():
        raise ValueError('Select an existing owning artifacts/ served directory')
    identity = source_identity(standard, sha)
    projection_path = regular_file(repo, '.bijux/docs-projection.json')
    projection_bytes = projection_path.read_bytes()
    projection = unique_json(projection_bytes)
    expected_source = {'mode': 'accepted-github', 'origin': ORIGIN, 'sha': sha}
    if type(projection.get('schema')) is not int or projection['schema'] != 1 or projection.get('source') != expected_source:
        raise ValueError('Projection selects stale or different accepted standard source')
    files = projection.get('files')
    if not isinstance(files, dict):
        raise ValueError('Projection requires an owned file mapping')
    baseline = unique_json(committed_file(standard, sha, 'config/mkdocs-baseline.json'))
    theme, diagram = baseline.get('theme'), baseline.get('diagram')
    if not isinstance(theme, dict) or theme.get('logo') != PREFERRED_LOGO:
        raise ValueError('Committed baseline does not select the reviewed preferred logo')
    if not isinstance(diagram, dict):
        raise ValueError('Committed baseline requires owned diagram configuration')
    vendor = diagram.get('vendor')
    relative_path(vendor)
    if not vendor.startswith('assets/javascripts/vendor/'):
        raise ValueError('Committed diagram library must be an owned vendor asset')
    provenance_bytes = committed_file(standard, sha, 'tooling/diagrams/provenance.json')
    provenance = unique_json(provenance_bytes)
    vendor_records = [item for item in provenance.get('output', []) if isinstance(item, dict) and item.get('name') == PurePosixPath(vendor).name]
    if len(vendor_records) != 1:
        raise ValueError('Committed diagram provenance must identify the exact vendor output')
    licenses = [('assets/javascripts/vendor/THIRD-PARTY-LICENSES.txt', 'retained-diagram-licenses'),
                (vendor + '.LEGAL.txt', 'retained-diagram-legal-notices')]
    selected = [(PREFERRED_LOGO, 'preferred-brand'), (COMPATIBILITY_LOGO, 'retained-brand-compatibility'),
                (vendor, 'optional-diagram-library'), *licenses]
    payloads = []
    for name, role in selected:
        data = committed_file(standard, sha, name)
        expected = fingerprint(data)
        source_name = 'bijux-docs/' + name
        destinations = [(path, entry) for path, entry in files.items() if isinstance(entry, dict) and entry.get('source') == source_name]
        if len(destinations) != 1:
            raise ValueError(f'Projection must identify one owned destination for {name}')
        destination, entry = destinations[0]
        if entry != {'source': source_name, 'sha256': expected['sha256']}:
            raise ValueError(f'Projection digest differs from committed source: {name}')
        projected = regular_file(repo, destination).read_bytes()
        served = regular_file(site, name).read_bytes()
        if projected != data:
            raise ValueError(f'Projected bytes differ from committed source: {name}')
        if served != data:
            raise ValueError(f'Served bytes differ from committed source: {name}')
        item = {'asset': name, 'role': role, 'source': expected, 'projected': {'path': destination, **fingerprint(projected)},
                'served': {'path': name, **fingerprint(served)}, 'quantities': {
                    'raw_file_bytes': byte_quantity(len(served), 'local served file'),
                    'decoded_body_bytes': byte_quantity(None, 'requires an actual response observation'),
                    'encoded_body_bytes': byte_quantity(None, 'requires an actual encoded response observation'),
                    'transfer_bytes_including_headers': byte_quantity(None, 'requires an actual transfer observation')},
                'cache': 'unobserved', 'content_encoding': 'unobserved'}
        if name == PREFERRED_LOGO:
            dimensions = png_dimensions(data)
            if dimensions != [128, 128]:
                raise ValueError('Preferred logo intrinsic dimensions differ from the reviewed 128x128 source')
            if len(data) > PREFERRED_LOGO_LIMIT:
                raise ValueError('Preferred logo exceeds the existing 32 KiB body ceiling')
            item.update(intrinsic_pixels=dimensions, preferred_body_ceiling_bytes=PREFERRED_LOGO_LIMIT,
                        budget_scope='matching raw PNG representation; actual delivered response remains separately observed')
        if name == vendor:
            vendor_record = vendor_records[0]
            if type(vendor_record.get('bytes')) is not int or vendor_record['bytes'] != len(data) or vendor_record.get('sha256') != expected['sha256']:
                raise ValueError('Committed diagram provenance differs from its actual output')
            actual_sri = 'sha384-' + base64.b64encode(hashlib.sha384(data).digest()).decode()
            if vendor_record.get('integrity') != actual_sri:
                raise ValueError('Committed diagram integrity differs from its actual output')
            item.update(provenance=fingerprint(provenance_bytes), integrity=actual_sri)
        if name == licenses[0][0] and provenance.get('license_sha256') != expected['sha256']:
            raise ValueError('Committed diagram license provenance differs from its actual source')
        if name == licenses[1][0]:
            legal = [entry for entry in provenance.get('output', []) if isinstance(entry, dict) and entry.get('name') == PurePosixPath(name).name]
            if len(legal) != 1 or type(legal[0].get('bytes')) is not int or legal[0]['bytes'] != len(data) or legal[0].get('sha256') != expected['sha256']:
                raise ValueError('Committed diagram legal-notice provenance differs from its actual source')
        payloads.append(item)
    return {'schema': 1, 'scope': 'owned committed/projected/served static payload accounting', 'result': 'pass',
            'verification_only': True, 'standard': identity, 'projection': fingerprint(projection_bytes),
            'site_dir': site.relative_to(repo).as_posix(), 'payloads': payloads,
            'limits': ['No cold/warm/cache/compression/wire/lab/field measurement.',
                       'No physical sharpness, custom-logo or fallback rendering qualification.',
                       'No consumer adoption, publication, live delivery or remote acceptance certification.']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument('--site-dir', type=Path, required=True)
    parser.add_argument('--standard-root', type=Path, required=True)
    parser.add_argument('--standard-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    site, output = (repo / args.site_dir).resolve(), (repo / args.output).resolve()
    if not output.is_relative_to(repo / 'artifacts') or output.is_relative_to(site):
        parser.error('Write an owning artifacts/ report outside the served directory')
    try:
        report = qualify(repo, site, args.standard_root, args.standard_sha)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report = {'schema': 1, 'scope': 'owned committed/projected/served static payload accounting',
                  'result': 'fail', 'verification_only': True, 'errors': [str(exc)]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(f'{report["result"].upper()}: owned payload accounting; report {output}')
    return 0 if report['result'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
