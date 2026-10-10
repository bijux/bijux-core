#!/usr/bin/env python3
"""Project the shared docs surface and admitted Python docs Make profiles."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

OWNERSHIP = '.bijux/docs-projection.json'
# Reviewed destinations from the accepted copier, rather than wildcard ownership.
# Root main.html and newly introduced partials/assets are deliberately absent.
LEGACY = frozenset([
    *('docs/overrides/partials/' + name for name in ('header.html', 'footer.html',
      'footer-profile-links.html', 'nav.html', 'nav-item.html', 'bijux-nav.html')),
    *('docs/assets/styles/' + name for name in ('00-tokens.css', '01-theme.css',
      '02-layout.css', '03-header.css', '04-nav.css', '05-content.css',
      '06-components.css', '07-utilities.css', '08-responsive.css', 'extra.css')),
    *('docs/assets/javascripts/shell/' + name for name in ('bootstrap.js',
      'detail-tabs.js', 'nav-reveal.js', 'nav-state.js', 'theme-persistence.js',
      'viewport-profile.js')),
    'docs/assets/javascripts/navigation-sync.js', 'docs/assets/javascripts/mermaid-init.js',
    'docs/assets/bijux_icon.png', 'docs/assets/bijux_logo_hq.png',
    'docs/assets/site-icons/favicon.ico', 'docs/assets/site-icons/apple-touch-icon.png',
    'docs/assets/site-icons/apple-touch-icon-precomposed.png',
    'makes/bijux-py/root/docs.mk', 'makes/bijux-py/ci/docs.mk',
])


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_destination(source: str) -> str:
    """Validate an ownership entry against the projector's declared namespace."""
    relative = Path(source)
    if relative.is_absolute() or '..' in relative.parts or relative.as_posix() != source:
        raise RuntimeError('Unsafe projection ownership source: ' + source)
    if source.startswith('bijux-docs/partials/') and source.endswith('.html'):
        part = source.removeprefix('bijux-docs/partials/')
        return 'docs/overrides/main.html' if part == 'main.html' else 'docs/overrides/partials/' + part
    if source.startswith('bijux-docs/assets/'):
        return 'docs/assets/' + source.removeprefix('bijux-docs/assets/')
    if source.startswith('bijux-docs/styles/') and relative.suffix == '.css' and len(relative.parts) == 3:
        return 'docs/assets/styles/' + relative.name
    if source.startswith('bijux-docs/scripts/') and relative.suffix == '.js' and len(relative.parts) == 3:
        if relative.name == 'nav-sync.js': return 'docs/assets/javascripts/navigation-sync.js'
        if relative.name == 'mermaid-init.js': return 'docs/assets/javascripts/mermaid-init.js'
        if relative.name == 'external-links.js': return 'docs/assets/javascripts/external-links.js'
        return 'docs/assets/javascripts/shell/' + relative.name
    if source in ('bijux-makes-py/root/docs.mk', 'bijux-makes-py/ci/docs.mk'):
        return 'makes/bijux-py/' + source.removeprefix('bijux-makes-py/')
    raise RuntimeError('Unmanaged projection ownership source: ' + source)


def destination_shape(repo: Path, destination: Path) -> None:
    relative = destination.relative_to(repo).as_posix()
    for parent in (destination, *destination.parents):
        if parent == repo: break
        if parent.is_symlink():
            raise RuntimeError('Preserve symlinked projection destination: ' + relative)
    if destination.exists() and not destination.is_file():
        raise RuntimeError('Projection destination is not a regular file: ' + relative)
    for parent in destination.parents:
        if parent == repo: break
        if parent.exists() and not parent.is_dir():
            raise RuntimeError('Projection destination parent is not a directory: ' + relative)


def tracked(repo: Path, destination: Path) -> bool:
    result = subprocess.run(['git', '-C', str(repo), 'ls-files', '--error-unmatch',
                             '--', destination.relative_to(repo).as_posix()], capture_output=True)
    return result.returncode == 0


def source_context() -> dict:
    """The shell authority supplies verified provenance; local runs stay explicit."""
    mode = os.environ.get('BIJUX_DOCS_SOURCE_MODE')
    if mode == 'local-verification' and (os.environ.get('BIJUX_STD_LOCAL_VERIFY') == '1' or os.environ.get('BIJUX_STD_ALLOW_LOCAL_SOURCE') == '1'):
        return {'mode': mode, 'sha': None, 'origin': None}
    if mode == 'accepted-github':
        sha = os.environ.get('BIJUX_DOCS_SOURCE_SHA', '')
        origin = os.environ.get('BIJUX_DOCS_SOURCE_ORIGIN', '')
        authority = os.environ.get('BIJUX_STD_ROOT', '')
        if not re.fullmatch('[a-f0-9]{40}', sha) or origin not in ('https://github.com/bijux/bijux-std.git', 'git@github.com:bijux/bijux-std.git') or not authority:
            raise RuntimeError('Projection requires verified accepted source provenance')
        return {'mode': mode, 'sha': sha, 'origin': origin, 'authority': authority}
    raise RuntimeError('Run projection through the verified docs authority; explicit local verification is separate')


def published_bytes(context: dict, sha: str, source: str) -> bytes:
    if not re.fullmatch('[a-f0-9]{40}', sha):
        raise RuntimeError('Accepted projection provenance requires an exact full SHA')
    root = context['authority']
    origin = subprocess.run(['git', '-C', root, 'remote', 'get-url', 'origin'], capture_output=True, text=True)
    if origin.returncode or origin.stdout.strip() != context['origin'] or context['origin'] not in ('https://github.com/bijux/bijux-std.git', 'git@github.com:bijux/bijux-std.git'):
        raise RuntimeError('Projection authority origin differs from verified GitHub source; fetch refused')
    result = subprocess.run(['git', '-C', context['authority'], 'show', sha + ':shared/' + source], capture_output=True)
    if result.returncode:
        exists = subprocess.run(['git', '-C', root, 'cat-file', '-e', sha + '^{commit}'], capture_output=True)
        if not exists.returncode:
            raise RuntimeError('Prior accepted projection source lacks recorded path: ' + source)
        head = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(['git', '-C', root, 'status', '--porcelain', '--untracked-files=all'], capture_output=True, text=True, check=True)
        if status.stdout:
            raise RuntimeError('Preserve modified authority inputs before prior-source fetch')
        fetched = subprocess.run(['git', '-C', root, 'fetch', '--quiet', '--depth', '1', 'origin', sha], capture_output=True)
        if fetched.returncode:
            raise RuntimeError('Prior accepted projection source unavailable; fetch exact SHA ' + sha + ' failed before consumer mutation')
        actual = subprocess.run(['git', '-C', root, 'rev-parse', 'FETCH_HEAD^{commit}'], capture_output=True, text=True, check=True).stdout.strip()
        after = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
        if actual != sha or after != head:
            raise RuntimeError('Prior-source fetch changed HEAD or returned an unexpected object; consumer mutation refused')
        result = subprocess.run(['git', '-C', root, 'show', sha + ':shared/' + source], capture_output=True)
        if result.returncode:
            raise RuntimeError('Fetched accepted projection source lacks recorded path: ' + source)
    return result.stdout


def committed_prior_pin(repository: Path, context: dict, git) -> str | None:
    """Select prior ownership only from a regular committed consumer pin."""
    root = repository.resolve()
    pin_relative = '.github/standards/bijux-std.sha'
    pin = root / pin_relative
    if git(root, 'rev-parse', '--show-toplevel') != str(root):
        raise RuntimeError('Prior asset authority: explicit consumer repository root is required')
    if any(path.is_symlink() for path in (pin, pin.parent, pin.parent.parent)) or not pin.is_file():
        raise RuntimeError('Prior asset authority: regular working standard pin is required')
    if pin.read_text().strip() != context['sha']:
        raise RuntimeError('Prior asset authority: working standard pin differs from accepted source')
    committed = git(root, 'ls-tree', 'HEAD', '--', pin_relative)
    if not re.fullmatch(r'100644 blob [a-f0-9]{40}\t' + re.escape(pin_relative), committed):
        raise RuntimeError('Prior asset authority: committed regular standard pin is required')
    previous = git(root, 'show', 'HEAD:' + pin_relative)
    if not re.fullmatch(r'[a-f0-9]{40}', previous):
        raise RuntimeError('Prior asset authority: committed exact previous standard pin is required')
    return previous if previous != context['sha'] else None


def retired_readme_matches(repo: Path, source: Path, destination: Path, shared: Path, context: dict) -> bool:
    if source.is_file() and destination.read_bytes() == source.read_bytes():
        return True
    if context['mode'] != 'accepted-github':
        return False

    def git(root, *arguments):
        result = subprocess.run(['git', '-C', str(root), *arguments], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('Prior asset authority: required Git source is unavailable')
        return result.stdout.strip()

    previous = committed_prior_pin(repo, context, git)
    if previous is None:
        return False
    relative = source.relative_to(shared.parent).as_posix()
    return destination.read_bytes() == published_bytes(context, previous, relative)


def ownership_plan(repo: Path, shared: Path, files: list, context: dict,
                   input_bytes: dict | None = None) -> tuple[dict, bytes, list[Path]]:
    """An ownership record proves prior generated bytes; it cannot adopt author files."""
    metadata = repo / OWNERSHIP
    destination_shape(repo, metadata)
    prior = {}
    if metadata.exists():
        try:
            record = json.loads(metadata.read_text())
            if set(record) != {'schema', 'source', 'files'} or type(record['schema']) is not int or record['schema'] != 1 or not isinstance(record['files'], dict):
                raise ValueError('shape')
            provenance = record['source']
            if set(provenance) != {'mode', 'sha', 'origin'} or provenance['mode'] not in ('local-verification', 'accepted-github'):
                raise ValueError('provenance')
            if provenance['mode'] == 'accepted-github':
                if not re.fullmatch('[a-f0-9]{40}', provenance['sha']) or provenance['origin'] not in ('https://github.com/bijux/bijux-std.git', 'git@github.com:bijux/bijux-std.git'):
                    raise ValueError('accepted provenance')
            elif provenance['sha'] is not None or provenance['origin'] is not None:
                raise ValueError('local provenance')
            if context['mode'] == 'accepted-github' and provenance['mode'] != 'accepted-github':
                raise RuntimeError('Local projection ownership cannot silently become accepted rollout; review an explicit migration')
            for destination, entry in record['files'].items():
                if set(entry) != {'source', 'sha256'} or not isinstance(entry['source'], str) or not re.fullmatch('[a-f0-9]{64}', entry['sha256']):
                    raise ValueError('entry')
                if source_destination(entry['source']) != destination:
                    raise ValueError('destination mapping')
                if context['mode'] == 'accepted-github' and digest(published_bytes(context, provenance['sha'], entry['source'])) != entry['sha256']:
                    raise RuntimeError('Projection ownership record differs from actual prior accepted source: ' + destination)
            prior = record['files']
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise RuntimeError('Invalid projection ownership record; preserve it for review: ' + OWNERSHIP) from exc
    planned = {}
    for source, destination in files:
        relative = destination.relative_to(repo).as_posix()
        source_relative = source.relative_to(shared.parent).as_posix()
        if source_destination(source_relative) != relative or relative in planned:
            raise RuntimeError('Ambiguous canonical projection destination: ' + relative)
        value = digest(input_bytes[source] if input_bytes is not None else source.read_bytes())
        if context['mode'] == 'accepted-github' and value != digest(published_bytes(context, context['sha'], source_relative)):
            raise RuntimeError('Canonical projection input differs from verified accepted source: ' + source_relative)
        planned[relative] = {'source': source_relative, 'sha256': value}
        destination_shape(repo, destination)
        if destination.exists():
            if relative in prior:
                if digest(destination.read_bytes()) != prior[relative]['sha256']:
                    raise RuntimeError('Preserve authored changes to previously generated destination: ' + relative)
            else:
                if not tracked(repo, destination):
                    raise RuntimeError('Preserve untracked generated destination input: ' + relative)
                if relative not in LEGACY:
                    raise RuntimeError('Preserve consumer-owned extension at newly projected destination; explicit authored extension migration required: ' + relative)
    retired = []
    for relative, entry in prior.items():
        if relative not in planned:
            destination = repo / relative
            destination_shape(repo, destination)
            if destination.exists() and digest(destination.read_bytes()) != entry['sha256']:
                raise RuntimeError('Preserve authored changes before generated retirement: ' + relative)
            retired.append(destination)
    desired = {'schema': 1, 'source': {key: context[key] for key in ('mode', 'sha', 'origin')}, 'files': planned}
    return prior, (json.dumps(desired, indent=2, sort_keys=True) + '\n').encode(), retired


def projection(repo: Path, shared: Path) -> list[tuple[Path, Path]]:
    files = []
    baseline_path = shared / 'config/mkdocs-baseline.json'
    if baseline_path.exists():
        diagram = json.loads(baseline_path.read_text()).get('diagram')
        if diagram:
            vendor = shared / 'assets' / Path(diagram['vendor']).relative_to('assets')
            if not vendor.is_file() or hashlib.sha256(vendor.read_bytes()).hexdigest() != diagram['sha256']:
                raise RuntimeError('Missing or altered pinned diagram vendor; projection aborted before mutation')
    required = ('header.html', 'footer.html', 'footer-profile-links.html', 'nav.html', 'nav-item.html', 'bijux-nav.html')
    for part in required:
        if not (shared / 'partials' / part).is_file():
            raise RuntimeError('Missing canonical partial: ' + part)
    for path in sorted((shared / 'partials').rglob('*.html')):
        relative = path.relative_to(shared/'partials')
        destination = repo/'docs/overrides/main.html' if relative.as_posix() == 'main.html' else repo/'docs/overrides/partials'/relative
        files.append((path,destination))
    for path in sorted((shared / 'styles').iterdir()):
        if path.is_file() and path.suffix == '.css':
            files.append((path, repo / 'docs/assets/styles' / path.name))
    for path in sorted((shared / 'scripts').iterdir()):
        if path.is_file() and path.suffix == '.js' and path.name not in {'nav-sync.js', 'mermaid-init.js', 'external-links.js'}:
            files.append((path, repo / 'docs/assets/javascripts/shell' / path.name))
    files.extend((shared / 'scripts' / src, repo / 'docs/assets/javascripts' / dst) for src, dst in (
        ('nav-sync.js', 'navigation-sync.js'), ('mermaid-init.js', 'mermaid-init.js'),
        ('external-links.js', 'external-links.js')))
    for path in sorted((shared / 'assets').rglob('*')):
        if path.is_file():
            files.append((path, repo / 'docs/assets' / path.relative_to(shared / 'assets')))
    # Existing Python profiles declare applicability; unrelated Make files are product-owned.
    for name in ('root/docs.mk', 'ci/docs.mk'):
        dst = repo / 'makes/bijux-py' / name
        if dst.exists():
            files.append((shared.parent / 'bijux-makes-py' / name, dst))
    missing = [str(src) for src, _ in files if not src.is_file()]
    if missing:
        raise RuntimeError('Missing canonical projection inputs: ' + ', '.join(missing))
    return files


def assert_destinations_pristine(repo: Path, destinations: list[Path]) -> None:
    """Only committed generated bytes may be replaced; pending user work is preserved."""
    probe = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--show-toplevel'],
                           capture_output=True, text=True)
    if probe.returncode:
        return
    if Path(probe.stdout.strip()).resolve() != repo.resolve():
        raise RuntimeError('Projection repository must be its own Git root')
    for destination in destinations:
        relative = str(destination.relative_to(repo))
        for parent in (destination, *destination.parents):
            if parent == repo:
                break
            if parent.is_symlink():
                raise RuntimeError('Preserve symlinked projection destination: ' + relative)
        for arguments in (['diff', '--quiet', '--', relative],
                          ['diff', '--cached', '--quiet', '--', relative]):
            if subprocess.run(['git', '-C', str(repo), *arguments], capture_output=True).returncode:
                raise RuntimeError('Preserve local generated destination changes: ' + relative)
        # Query index ownership directly: ignored files are still consumer work.
        if destination.exists() and not tracked(repo, destination):
            raise RuntimeError('Preserve untracked generated destination input: ' + relative)


def prepare(repo: Path, shared: Path, protect: bool = True,
            include_config: bool = False, context: dict | None = None) -> tuple[list[tuple[Path, Path]], list[Path], list[str]]:
    """Validate every input, retirement and affected destination before any write."""
    files = projection(repo, shared)
    context = context or {'mode': 'local-verification', 'sha': None, 'origin': None}
    destination_shape(repo, repo / OWNERSHIP)
    for _, destination in files:
        destination_shape(repo, destination)
    retired = [(shared / 'styles/README.md', repo / 'docs/assets/styles/README.md'),
               (shared / 'scripts/README.md', repo / 'docs/assets/javascripts/shell/README.md')]
    for source, destination in retired:
        destination_shape(repo, destination)
        if destination.exists() and not retired_readme_matches(repo, source, destination, shared, context):
            raise RuntimeError('Preserve modified author documentation before retiring generated website copy: ' + str(destination))
    retired_paths = [dst for _, dst in retired if dst.exists()]
    affected = [dst for src, dst in files if not dst.is_file() or src.read_bytes() != dst.read_bytes()]
    if protect:
        if include_config:
            assert_destinations_pristine(repo, [repo / name for name in ('mkdocs.shared.yml', 'mkdocs.yml')])
        assert_destinations_pristine(repo, [*affected, *retired_paths])
    prior, desired, managed_retired = ownership_plan(repo, shared, files, context)
    retired_paths = sorted(set([*retired_paths, *managed_retired]))
    metadata = repo / OWNERSHIP
    metadata_differs = not metadata.is_file() or metadata.read_bytes() != desired
    if protect and (affected or retired_paths or metadata_differs):
        # A previously generated but pending record is not committed ownership.
        assert_destinations_pristine(repo, [metadata, *managed_retired])
    drift = [str(dst.relative_to(repo)) for src, dst in files if not dst.is_file() or src.read_bytes() != dst.read_bytes()]
    drift.extend(str(dst.relative_to(repo)) for dst in retired_paths if dst.exists())
    if metadata_differs:
        drift.append(OWNERSHIP)
    return files, retired_paths, drift


def apply(repo: Path, shared: Path, check: bool = False, context: dict | None = None) -> list[str]:
    context = context or {'mode': 'local-verification', 'sha': None, 'origin': None}
    files, retired, drift = prepare(repo, shared, protect=not check, context=context)
    if check:
        if drift:
            raise RuntimeError('Generated docs projection differs: ' + ', '.join(drift))
    else:
        # Read every copy payload and metadata before the first destination write.
        payloads = {src: src.read_bytes() for src, _ in files}
        _, desired, _ = ownership_plan(repo, shared, files, context, input_bytes=payloads)
        for dst in retired:
            if dst.exists():
                dst.unlink()
        for src, dst in files:
            data = payloads[src]
            if dst.is_file() and data == dst.read_bytes():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
        metadata = repo / OWNERSHIP
        if not metadata.is_file() or metadata.read_bytes() != desired:
            metadata.parent.mkdir(parents=True, exist_ok=True)
            metadata.write_bytes(desired)
    return drift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository', type=Path)
    parser.add_argument('shared_docs', type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--include-config', action='store_true')
    args = parser.parse_args()
    try:
        if args.preflight:
            _, _, changed = prepare(args.repository.resolve(), args.shared_docs.resolve(), include_config=args.include_config, context=source_context())
        else:
            changed = apply(args.repository.resolve(), args.shared_docs.resolve(), args.check, context=source_context())
    except (RuntimeError, OSError) as exc:
        parser.exit(1, f'ERROR: {exc}\n')
    status = "preflight verified" if args.preflight else "verified" if args.check else "written"
    print(f'Canonical docs projection {status}: {len(changed)} changed paths')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
