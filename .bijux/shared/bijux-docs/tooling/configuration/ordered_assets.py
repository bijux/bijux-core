"""Project admitted configuration lists without serializing authored YAML.

Only block sequences of strings or block mappings are admitted. Exotic YAML
representations require an explicit author migration; no guessed conversion is
allowed to change execution order or attribute ownership.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class Entry:
    name: str
    raw: str
    mapping: bool = False


def scalar(value: str, source: Path, field: str) -> str:
    value = value.strip()
    fail = lambda: RuntimeError(f"{source}: {field}: expected a literal string; use a reviewed block-list representation")
    if value.startswith('"'):
        try:
            result, end = json.JSONDecoder().raw_decode(value)
        except ValueError as exc:
            raise fail() from exc
        if not isinstance(result, str) or (value[end:].strip() and not value[end:].lstrip().startswith('#')):
            raise fail()
    elif value.startswith("'"):
        match = re.fullmatch(r"'((?:[^']|'')*)'\s*(?:#.*)?", value)
        if not match:
            raise fail()
        result = match.group(1).replace("''", "'")
    else:
        result = re.split(r'\s+#', value, maxsplit=1)[0].strip()
        if not result or result[0] in '!&*[{|>?:' or ': ' in result or result.lower() in {'null', '~', 'true', 'false', 'yes', 'no', 'on', 'off'} or re.fullmatch(r'[-+]?\d+(?:\.\d+)?', result):
            raise fail()
    if not result or '\n' in result or '\r' in result or '\x00' in result:
        raise fail()
    return result


def field_bounds(lines: list[str], field: str, source: Path) -> tuple[int, int] | None:
    if any(re.match(r'^(?:<<|[\"\']<<[\"\'])\s*:', line) or line.startswith('? ') for line in lines):
        raise RuntimeError(f'{source}: top-level YAML merge/explicit keys require author review before canonical projection')
    starts = [i for i, line in enumerate(lines) if re.match(rf'^{field}\s*:', line)]
    if any(re.match(rf'^[\"\']{field}[\"\']\s*:', line) for line in lines):
        raise RuntimeError(f'{source}: {field}: use an unquoted top-level field name')
    if len(starts) > 1:
        raise RuntimeError(f'{source}: duplicate {field} keys')
    if not starts:
        return None
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() and not lines[i].startswith((' ', '#', '-'))), len(lines))
    return start, end


def entries(lines: list[str], start: int, end: int, source: Path, field: str) -> tuple[str, list[Entry], int]:
    header = lines[start]
    if not re.match(rf'^{field}\s*:(?:\s|$)', header):
        raise RuntimeError(f'{source}: {field}: mapping separator must be followed by whitespace')
    tail = header.split(':', 1)[1].strip()
    if tail and not tail.startswith('#') and not re.fullmatch(r'\[\]\s*(?:#.*)?', tail):
        raise RuntimeError(f'{source}: {field}: expected a block list or []; scalar, alias, and flow lists require explicit migration')
    positions = [i for i in range(start + 1, end) if re.match(r'^ *-\s+', lines[i])]
    if not positions:
        if any(line.strip() and not line.lstrip().startswith('#') for line in lines[start + 1:end]):
            raise RuntimeError(f'{source}: {field}: malformed block list')
        return ''.join(lines[start + 1:end]), [], 2
    indent = len(lines[positions[0]]) - len(lines[positions[0]].lstrip(' '))
    positions = [i for i in positions if len(lines[i]) - len(lines[i].lstrip(' ')) == indent]
    prefix = ''.join(lines[start + 1:positions[0]])
    if any(line.strip() and not line.lstrip().startswith('#') for line in lines[start + 1:positions[0]]):
        raise RuntimeError(f'{source}: {field}: malformed block list prefix')
    result = []
    for index, position in enumerate(positions):
        last = positions[index + 1] if index + 1 < len(positions) else end
        chunk = lines[position:last]
        value = re.sub(r'^ *-\s+', '', chunk[0]).rstrip('\r\n')
        mapping = False
        if field == 'plugins' and re.fullmatch(r'[A-Za-z0-9_.-]+:\s*(?:#.*)?', value):
            name = value.split(':', 1)[0]
            mapping = True
        elif field == 'extra_javascript' and re.match(r'^path\s*:', value):
            name = scalar(value.split(':', 1)[1], source, field)
            mapping = True
        else:
            name = scalar(value, source, field)
        for continuation in chunk[1:]:
            if not continuation.strip() or continuation.lstrip().startswith('#'):
                continue
            depth = len(continuation) - len(continuation.lstrip(' '))
            if not mapping or depth <= indent:
                raise RuntimeError(f'{source}: {field}: unsupported list item shape for {name}')
            if field == 'extra_javascript' and re.match(r'^\s+path\s*:', continuation):
                raise RuntimeError(f'{source}: {field}: duplicate path in script mapping')
        result.append(Entry(name, ''.join(chunk), mapping))
    if re.fullmatch(r'\[\]\s*(?:#.*)?', tail):
        raise RuntimeError(f'{source}: {field}: [] cannot also contain block items')
    return prefix, result, indent


def ordered_list(content: str, field: str, required: list[str], source: Path, *, create: bool, retired: tuple[str, ...] = (), prior_javascript: Callable[[], tuple[str, ...] | None] | None = None) -> str:
    """Insert missing owned entries; retain every authored item and relative order.

    A missing entry is inserted immediately before its next present owned peer,
    or immediately after its preceding peer. Conflicting existing owned order
    and attribute-bearing owned scripts demand explicit author review.
    """
    if not isinstance(required, list) or not required or not all(isinstance(item, str) and item for item in required) or len(set(required)) != len(required):
        raise RuntimeError(f'Canonical {field} policy must contain unique nonempty strings')
    if set(required).intersection(retired):
        raise RuntimeError(f'Canonical {field} policy cannot require a retired asset')
    lines = content.splitlines(keepends=True)
    bounds = field_bounds(lines, field, source)
    if bounds is None:
        if not create:
            return content
        if content and not content.endswith('\n'):
            content += '\n'
        return content + field + ':\n' + ''.join(f'  - {item}\n' for item in required)
    start, end = bounds
    prefix, values, indent = entries(lines, start, end, source, field)
    names = [entry.name for entry in values]
    owned = [name for name in names if name in required]
    if len(set(owned)) != len(owned):
        raise RuntimeError(f'{source}: {field}: duplicate canonical entry')
    if owned != [name for name in required if name in owned]:
        if field == 'extra_javascript' and prior_javascript is not None:
            previous = prior_javascript()
            if previous is not None:
                plain = ''.join('  - ' + name + '\n' for name in previous)
                body = ''.join(lines[start + 1:end])
                trailing = body[len(plain):] if body.startswith(plain) else None
                # Only the complete literal prior default is managed adoption.
                # Comments, custom entries and attribute-bearing scripts retain author ownership.
                if (lines[start] == 'extra_javascript:\n' and names == list(previous)
                        and trailing is not None and not trailing.strip('\n')
                        and not any(entry.mapping for entry in values)):
                    replacement = lines[start] + ''.join('  - ' + name + '\n' for name in required) + trailing
                    return ''.join(lines[:start]) + replacement + ''.join(lines[end:])
        raise RuntimeError(f'{source}: {field}: canonical order conflicts with existing entries; review authored execution order')
    for entry in values:
        if entry.name in (*required, *retired) and field == 'extra_javascript' and entry.mapping:
            meaningful = [line for line in entry.raw.splitlines()[1:] if line.strip() and not line.lstrip().startswith('#')]
            if meaningful:
                raise RuntimeError(f'{source}: {field}: canonical script {entry.name} has authored attributes; review compatibility before adoption')
    values = [Entry('', ''.join(entry.raw.splitlines(keepends=True)[1:])) if entry.name in retired else entry for entry in values]
    if not owned:
        values = [*(Entry(name, ' ' * indent + '- ' + name + '\n') for name in required), *values]
    for index, name in enumerate(required):
        if any(entry.name == name for entry in values):
            continue
        after = next((other for other in required[index + 1:] if any(entry.name == other for entry in values)), None)
        before = next((other for other in reversed(required[:index]) if any(entry.name == other for entry in values)), None)
        position = next(i for i, entry in enumerate(values) if entry.name == after) if after else next(i for i, entry in enumerate(values) if entry.name == before) + 1 if before else len(values)
        values.insert(position, Entry(name, ' ' * indent + '- ' + name + '\n'))
    header = lines[start]
    if re.fullmatch(r'\[\]\s*(?:#.*)?', header.split(':', 1)[1].strip()):
        header = re.sub(r'\[\]', '', header)
    rendered = [entry.raw if entry.raw.endswith('\n') or i == len(values) - 1 else entry.raw + '\n' for i, entry in enumerate(values)]
    replacement = header + prefix + ''.join(rendered)
    if replacement and not replacement.endswith('\n') and end < len(lines):
        replacement += '\n'
    return ''.join(lines[:start]) + replacement + ''.join(lines[end:])


def project_required_lists(content: str, baseline: dict, source: Path, *, shared: bool, prior_javascript: Callable[[], tuple[str, ...] | None] | None = None) -> str:
    if not shared:
        lines = content.splitlines(keepends=True)
        bounds = field_bounds(lines, 'INHERIT', source)
        if bounds is None or scalar(lines[bounds[0]].split(':', 1)[1], source, 'INHERIT') != 'mkdocs.shared.yml':
            raise RuntimeError(f'{source}: INHERIT must name mkdocs.shared.yml; alternate inheritance needs an explicit supported source contract')
    policy = baseline.get('retired_extra_javascript', [])
    if not isinstance(policy, list) or not all(isinstance(item, str) for item in policy) or len(set(policy)) != len(policy):
        raise RuntimeError('Canonical retired_extra_javascript policy must contain unique exact paths')
    for field in ('extra_css', 'extra_javascript', 'plugins'):
        required = baseline['required_plugins'] if field == 'plugins' else baseline[field]
        content = ordered_list(content, field, required, source, create=shared, retired=tuple(policy) if field == 'extra_javascript' else (), prior_javascript=prior_javascript if shared else None)
    return content


def validate_effective_assets(config: dict, baseline: dict, source: str) -> None:
    for field in ('extra_css', 'extra_javascript'):
        values = config.get(field)
        if not isinstance(values, list):
            raise RuntimeError(f'{source}: {field}: expected a list')
        names = []
        for value in values:
            if isinstance(value, str):
                names.append(value)
            elif field == 'extra_javascript' and isinstance(value, dict) and isinstance(value.get('path'), str):
                if value['path'] in baseline[field] and set(value) != {'path'}:
                    raise RuntimeError(f'{source}: {field}: canonical script attributes are not admitted')
                names.append(value['path'])
            else:
                raise RuntimeError(f'{source}: {field}: unsupported asset representation')
        required = baseline[field]
        if [name for name in names if name in required] != required:
            raise RuntimeError(f'{source}: {field}: required assets must occur exactly once in canonical order')
        if field == 'extra_javascript' and set(names).intersection(baseline.get('retired_extra_javascript', [])):
            raise RuntimeError(f'{source}: {field}: retired canonical script is still configured')
