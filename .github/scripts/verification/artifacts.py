"""Bind candidate and compilation archives to immutable input identities."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tarfile

from .planning import encoded


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))


def source_files(root: Path, *, paths: list[str] | None = None) -> dict[str, str]:
    files = {}
    def retain(path):
        relative = path.relative_to(root)
        if relative.parts[0] in {'.git', 'artifacts', 'target'} or '__pycache__' in relative.parts:
            return
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Candidate source alias escapes its owner: ' + str(relative))
            files[relative.as_posix()] = 'symlink:' + os.readlink(path)
        elif path.is_dir():
            visit(path)
        elif path.is_file():
            files[relative.as_posix()] = file_digest(path)
    def visit(directory):
        for path in sorted(directory.iterdir()):
            retain(path)
    if paths is None:
        visit(root)
    else:
        for relative in paths:
            retain(root / relative)
    return files


def verify_sources(root: Path, expected: dict[str, str]) -> None:
    for relative, digest in expected.items():
        path = root / relative
        if digest.startswith('symlink:'):
            if (not path.is_symlink() or 'symlink:' + os.readlink(path) != digest
                    or not path.resolve().is_relative_to(root.resolve())):
                raise ValueError('Prepared candidate alias changed: ' + relative)
            continue
        parents = [parent for parent in path.parents if parent != root and parent.is_relative_to(root)]
        if (path.is_symlink() or any(parent.is_symlink() for parent in parents)
                or not path.is_file() or file_digest(path) != digest):
            raise ValueError('Prepared candidate input changed: ' + relative)


def selected_files(root: Path, include: list[str] | None = None):
    for owned in ([root / name for name in include] if include else [root]):
        if not owned.exists():
            continue
        for path in sorted(owned.rglob('*')):
            if 'incremental' not in path.relative_to(root).parts and (path.is_symlink() or not path.is_dir()):
                yield path


def entry_digest(path: Path) -> str:
    return 'symlink:' + os.readlink(path) if path.is_symlink() else file_digest(path)


def snapshot(root: Path, *, include: list[str] | None = None) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): entry_digest(path) for path in selected_files(root, include)}


def pack(root: Path, output: Path, *, baseline: dict[str, str] | None = None,
         include: list[str] | None = None) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w:gz', compresslevel=1) as archive:
        for path in selected_files(root, include):
            relative = path.relative_to(root)
            if baseline is not None and relative.as_posix() in baseline and entry_digest(path) == baseline[relative.as_posix()]:
                continue
            archive.add(path, arcname=relative.as_posix(), recursive=False)
    return file_digest(output)


def unpack(archive: Path, destination: Path, expected: str) -> None:
    if not expected or file_digest(archive) != expected:
        raise ValueError('Archive digest does not match its producer: ' + archive.name)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, 'r:gz') as stream:
        stream.extractall(destination, filter='data')


def verify_receipts(plan: dict, identity: dict, records: list[dict]) -> dict:
    expected = {check['id'] for check in plan['checks']}
    observed = [record['check'] for record in records]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError('Acceptance requires exactly one result from every planned verification')
    for record in records:
        if record.get('identity') != identity or record.get('status') != 'passed':
            raise ValueError('Failed, stale or unrelated verification result: ' + record['check'])
        if not 0 <= record.get('elapsed_seconds', -1) < plan['policy']['maximum_seconds']:
            raise ValueError('Verification exceeded its five-minute budget: ' + record['check'])
    return {'schema': 1, 'status': 'passed', 'identity': identity, 'checks': len(records),
            'cargo_targets': len(plan['inventory']),
            'maximum_verification_seconds': max(record['elapsed_seconds'] for record in records),
            'above_target': [record['check'] for record in records
                             if record['elapsed_seconds'] >= plan['policy']['target_seconds']]}
