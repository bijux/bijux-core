"""Retire exact shared logo references without serializing authored YAML."""
from __future__ import annotations

import json
from pathlib import Path
import re

from .ordered_assets import field_bounds, scalar


def logo_policy(baseline: dict) -> tuple[str, tuple[str, ...]]:
    theme = baseline.get('theme')
    target = theme.get('logo') if isinstance(theme, dict) else None
    retired = baseline.get('retired_theme_logos', [])
    if not isinstance(target, str) or not target or not isinstance(retired, list):
        raise RuntimeError('Canonical theme logo policy must name a literal target and exact retired paths')
    def exact_path(value: object) -> bool:
        return (isinstance(value, str) and value.startswith('assets/')
                and not any(char in value for char in '\n\r\x00?#*[]\\')
                and all(part not in ('', '.', '..') for part in value.split('/')))
    if (not exact_path(target) or not all(exact_path(value) for value in retired)
            or len(set(retired)) != len(retired) or target in retired):
        raise RuntimeError('Canonical retired_theme_logos must contain unique exact asset paths distinct from the target')
    return target, tuple(retired)


def project_theme_logo(content: str, baseline: dict, source: Path) -> str:
    """Replace only an admitted retired literal; never create a logo override.

    The shared default is rendered from the baseline elsewhere. Absent branding
    continues to inherit; custom icons, logos, and dynamic logo values remain
    authored. Merge/flow theme structures require review before projection.
    """
    target, retired = logo_policy(baseline)
    lines = content.splitlines(keepends=True)
    if any(re.match(r'^ *\t', line) for line in lines):
        raise RuntimeError(f'{source}: tabs in YAML indentation require author review')
    bounds = field_bounds(lines, 'theme', source)
    if bounds is None:
        return content
    start, end = bounds
    if not re.fullmatch(r'theme\s*:\s*(?:#.*)?', lines[start].rstrip('\r\n')):
        raise RuntimeError(f'{source}: theme: use an ordinary block mapping before branding projection')
    children = lines[start + 1:end]
    meaningful = [line for line in children if line.strip() and not line.lstrip().startswith('#')]
    if not meaningful:
        return content
    if any('\t' in line[:len(line) - len(line.lstrip())] for line in meaningful):
        raise RuntimeError(f'{source}: theme: tabs in mapping indentation require author review')
    indent = min(len(line) - len(line.lstrip(' ')) for line in meaningful)
    if not indent or any(line[indent:].startswith('-') for line in meaningful if len(line) - len(line.lstrip(' ')) == indent):
        raise RuntimeError(f'{source}: theme: expected a block mapping')
    projected = [line[indent:] if line.startswith(' ' * indent) else line for line in children]
    logo_bounds = field_bounds(projected, 'logo', source)
    if logo_bounds is None:
        return content
    logo_start, logo_end = logo_bounds
    line = children[logo_start]
    match = re.match(r'(?P<prefix> +logo\s*:\s*)(?P<value>[^\r\n]*)(?P<newline>\r\n|\n|\r)?$', line)
    if not match or not re.match(r'^ +logo\s*:(?:\s|$)', line):
        raise RuntimeError(f'{source}: theme.logo: malformed mapping separator')
    raw = match.group('value')
    # Dynamic and multiline custom branding is outside this exact retirement.
    if not raw or raw.startswith(('#', '!', '&', '*', '|', '>', '{', '[')):
        return content
    plain = re.split(r'\s+#', raw, maxsplit=1)[0].strip()
    if plain.lower() in {'null', '~'}:
        return content
    value = scalar(raw, source, 'theme.logo')
    if value not in retired:
        return content
    if any(part.strip() and not part.lstrip().startswith('#') for part in projected[logo_start + 1:logo_end]):
        raise RuntimeError(f'{source}: theme.logo: literal logo cannot have nested content')
    if raw.startswith('"'):
        _, finish = json.JSONDecoder().raw_decode(raw)
        replacement = json.dumps(target, ensure_ascii=False)
    elif raw.startswith("'"):
        finish = re.match(r"'((?:[^']|'')*)'", raw).end()
        replacement = "'" + target.replace("'", "''") + "'"
    else:
        finish = len(value)
        replacement = target
    position = start + 1 + logo_start
    lines[position] = match.group('prefix') + replacement + raw[finish:] + (match.group('newline') or '')
    return ''.join(lines)
