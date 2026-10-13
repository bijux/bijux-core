"""Retire exact unused package workflow copies without overwriting authored work."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

from .canonical_sources import read_owned
from .yaml_io import parse_workflow


ATLAS_PACKAGE_PREIMAGES = {
    '.github/workflows/reusable-ci-python-packages.yml':
        '563c9288dd53e424000b63655ac8992556b04f9cbd3879a1a096720a6cdaffe9',
    '.github/workflows/reusable-verify-python-packages.yml':
        '619bc3b8009f78850cea0c61342443a859a0700b31f6785dfb2a8ac54a56e37b',
}


def retired_paths(repository: str) -> set[str]:
    return set(ATLAS_PACKAGE_PREIMAGES) if repository == 'bijux-atlas' else set()


def _committed_preimage(root: Path, relative: str, expected: str) -> None:
    actual = read_owned(root, relative)
    if hashlib.sha256(actual).hexdigest() != expected:
        raise ValueError(f'retired package workflow differs from admitted preimage: {relative}')
    result = subprocess.run(['git', 'show', f'HEAD:{relative}'], cwd=root,
                            capture_output=True, check=False)
    if result.returncode or result.stdout != actual:
        raise ValueError(f'retired package workflow must be committed and unchanged: {relative}')
    staged = subprocess.run(['git', 'diff', '--cached', '--quiet', 'HEAD', '--', relative],
                            cwd=root, capture_output=True, check=False)
    if staged.returncode:
        raise ValueError(f'retired package workflow has staged changes: {relative}')


def plan_retirement(root: Path, repository: str) -> dict[str, str]:
    """Admit all preimages and remaining callers before any projection writes."""
    paths = retired_paths(repository)
    present = {relative: ATLAS_PACKAGE_PREIMAGES[relative] for relative in paths
               if (root / relative).exists() or (root / relative).is_symlink()}
    if not present:
        return {}
    for relative, expected in sorted(present.items()):
        _committed_preimage(root, relative, expected)
    for path in sorted((root / '.github/workflows').iterdir()):
        relative = path.relative_to(root).as_posix()
        if relative in paths or path.suffix not in {'.yml', '.yaml'}:
            continue
        document = parse_workflow(read_owned(root, relative), relative)
        for name, job in document['jobs'].items():
            if not isinstance(job, dict):
                raise ValueError(f'workflow job must be a mapping: {relative}/{name}')
            references = [job.get('uses')]
            steps = job.get('steps', [])
            if not isinstance(steps, list):
                raise ValueError(f'workflow steps must be a sequence: {relative}/{name}')
            for step in steps:
                if not isinstance(step, dict):
                    raise ValueError(f'workflow step must be a mapping: {relative}/{name}')
                references.append(step.get('uses'))
            for reference in references:
                if reference is None:
                    continue
                if not isinstance(reference, str):
                    raise ValueError(f'workflow reference must be a string: {relative}/{name}')
                if any(retired in reference.split('@', 1)[0] for retired in paths):
                    raise ValueError(f'retired package workflow still has a caller: {relative}/{name}')
    return dict(sorted(present.items()))


def apply_retirement(root: Path, repository: str, admitted: dict[str, str]) -> None:
    """Recheck exact files and callers; a changed preimage never authorizes deletion."""
    if plan_retirement(root, repository) != admitted:
        raise ValueError('retired package workflow inputs changed during projection')
    for relative in admitted:
        (root / relative).unlink()
