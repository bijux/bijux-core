#!/usr/bin/env python3
"""Keep website build output outside the repository's authored source tree."""
from __future__ import annotations

from pathlib import Path
import sys


def validate(root: Path) -> None:
    """Permit product assets while rejecting Material's compiled website output."""
    forbidden = (
        'overrides', '404.html', 'index.html', 'learning', 'platform',
        'projects', 'reading-paths', 'search', 'sitemap.xml', 'sitemap.xml.gz',
    )
    for relative in forbidden:
        path = root / relative
        if path.exists() or path.is_symlink():
            raise ValueError(f'generated root path must not exist: {relative}')
    # Scientific reference data and fixtures legitimately live in assets/.
    # Material's hashed runtime bundles identify generated website assets.
    for pattern in (
        'assets/javascripts/bundle.*.min.js',
        'assets/javascripts/workers/search.*.min.js',
        'assets/stylesheets/main.*.min.css',
        'assets/stylesheets/palette.*.min.css',
    ):
        for path in sorted(root.glob(pattern)):
            raise ValueError(f'generated website asset must not exist: {path.relative_to(root)}')


if __name__ == '__main__':
    try:
        validate(Path(sys.argv[1]).resolve())
    except ValueError as error:
        raise SystemExit(f'ERROR: {error}') from error
