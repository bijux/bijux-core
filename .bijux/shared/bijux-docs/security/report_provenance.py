"""Independently admit the finite Pollenomics public receipt projection."""
from __future__ import annotations

import hashlib
import builtins
import __future__
import inspect
import json
from pathlib import Path
import re

MANIFEST = 'configs/docs/publication/report-provenance.json'
MANIFEST_SHA256 = 'cbe708fc7b95f330d555dd4071e3caaf83fca720fca494fb6db4a51130aad91b'
REPORT_PATHS = ('report/publication-replay/landclim-example-reexecution/report.json', 'report/method-certification/linux-r-oracle/report.json', 'report/pollen-reconstruction/tibetanus-point-age-sensitivity/execution/native-capture.json', 'report/pollen-reconstruction/tibetanus-point-age-sensitivity/execution/source-cell-encoding-refusal.json', 'report/pollen-reconstruction/tibetanus-point-age-sensitivity/execution/source-census-status-refusal.json', 'report/pollen-reconstruction/nordic-static-basin-scenarios/verification/source-census-terminal.json', 'report/pollen-reconstruction/nordic-static-basin-scenarios/verification/independent-physical-terminal.json', 'report/pollen-reconstruction/nordic-static-basin-scenarios/verification/independent-scalar-terminal.json', 'report/pollen-reconstruction/nordic-static-basin-scenarios/verification/publication-metadata/acquisition-terminal.json', 'report/pollen-reconstruction/nordic-static-basin-scenarios/verification/publication-metadata/qualification-terminal.json', 'report/pollen-reconstruction/nordic-static-basin-scenarios/verification/native-terminal.json', 'report/pollen-reconstruction/nordic-static-basin-scenarios/verification/source-census.json', 'report/pollen-reconstruction/nordic-static-basin-scenarios/verification/primary-policy-native-terminal.json')
NOTE_KEY = '_public_provenance'
INTERNAL_PREFIXES = ('/Users/', '/home/', '/private/', '/tmp/')
SEMANTICS = ('Only the declared path strings are portable display values. They are not executed argv '
             'or physical acquisition authority. The immutable source receipt owns those original facts.')
TOKEN = re.compile(r'\s+|"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"|'
                   r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null|[{}\[\]:,]')


def require(condition, message):
    if not condition:
        raise ValueError('Producer report provenance: ' + message)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def unique_pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('Producer report provenance: nonfinite JSON token')


def spans(text):
    """Tokenize independently of the consumer's JSONDecoder pointer walk."""
    document = json.loads(text, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    require(isinstance(document, dict) and bool(document) and NOTE_KEY not in document,
            'one unprojected report object required')
    tokens = []
    end = 0
    for match in TOKEN.finditer(text):
        require(match.start() == end, 'unrecognized JSON token')
        end = match.end()
        if not match.group().isspace():
            tokens.append((match.group(), match.start(), match.end()))
    require(end == len(text), 'trailing unrecognized JSON token')
    fields = {}

    def walk(index, pointer):
        token, begin, finish = tokens[index]
        if token == '{':
            index += 1
            if tokens[index][0] == '}':
                return index + 1
            while True:
                key = json.loads(tokens[index][0])
                require(isinstance(key, str) and tokens[index + 1][0] == ':', 'object key separator')
                index = walk(index + 2, pointer + '/' + key.replace('~', '~0').replace('/', '~1'))
                if tokens[index][0] == '}':
                    return index + 1
                require(tokens[index][0] == ',', 'object member separator')
                index += 1
        if token == '[':
            index += 1
            if tokens[index][0] == ']':
                return index + 1
            position = 0
            while True:
                index = walk(index, pointer + '/' + str(position))
                if tokens[index][0] == ']':
                    return index + 1
                require(tokens[index][0] == ',', 'array member separator')
                index += 1
                position += 1
        if token.startswith('"'):
            fields[pointer] = (json.loads(token), begin, finish)
        return index + 1

    require(walk(0, '') == len(tokens), 'trailing JSON tokens')
    return fields


def project(raw, row):
    require(digest(raw) == row['source_sha256'], 'physical raw receipt differs')
    text = raw.decode('utf-8')
    positions = spans(text)
    edits = []
    seen = set()
    for field in row['fields']:
        require(set(field) == {'pointer', 'value_sha256', 'kind', 'display'}, 'field schema differs')
        pointer = field['pointer']
        require(pointer not in seen and pointer in positions, 'unique declared string pointer required')
        seen.add(pointer)
        value, begin, end = positions[pointer]
        require(digest(value.encode()) == field['value_sha256'], 'physical path value differs')
        display = field['display']
        require(isinstance(display, str) and bool(display) and not display.startswith('/')
                and '\\' not in display and ':' not in display
                and all(ord(character) >= 32 for character in display)
                and all(part not in {'', '.', '..'} for part in display.split('/')), 'relative display required')
        require(field['kind'] in {'interpreter-display', 'repository-path-display',
                                 'artifact-path-display', 'retained-source-path-display'}, 'display semantics differ')
        edits.append((begin, end, json.dumps(display, ensure_ascii=False)))
    require(bool(edits), 'declared display fields required')
    for begin, end, replacement in sorted(edits, reverse=True):
        text = text[:begin] + replacement + text[end:]
    require(not any(prefix in value for value, _, _ in spans(text).values()
                    for prefix in INTERNAL_PREFIXES), 'unmapped internal path remains')
    note = {'schema': 1, 'source_receipt_sha256': row['source_sha256'],
            'display_fields': row['fields'], 'display_semantics': SEMANTICS}
    closing = len(text.rstrip()) - 1
    value = (text[:closing].rstrip() + ',\n  ' + json.dumps(NOTE_KEY) + ': '
             + json.dumps(note, ensure_ascii=False, sort_keys=True, allow_nan=False)
             + '\n}' + text[closing + 1:]).encode()
    require(digest(value) == row['public_sha256'], 'independent public bytes differ')
    return value


def admit(hook, configuration, root, path, source, regular):
    """Fresh source and independent bytes grant authority; callback output does not."""
    from pathlib import PurePosixPath
    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.structure.files import File, Files
    names = {'File', 'Files', 'INTERNAL_PREFIXES', 'MANIFEST', 'MANIFEST_SHA256',
             'MkDocsConfig', 'NOTE_KEY', 'Path', 'PurePosixPath', 'REPORT_PATHS', 'ROOT',
             '_digest', '_nonfinite', '_note', '_pairs', '_project_report', '_read',
             '_require', '_string_fields', 'annotations', 'hashlib', 'json',
             'on_files', 'projected_reports'}
    require({name for name in vars(hook) if not name.startswith('__')} == names,
            'undeclared loaded global binding')
    scope = hook.__builtins__ if isinstance(hook.__builtins__, dict) else vars(hook.__builtins__)
    require(set(scope) == set(vars(builtins))
            and all(scope[name] is value for name, value in vars(builtins).items())
            and hook.annotations is __future__.annotations, 'loaded builtin binding differs')
    require(all(value.__defaults__ is None and value.__kwdefaults__ is None
                and value.__closure__ is None for value in vars(hook).values()
                if inspect.isfunction(value)), 'loaded function state differs')
    require(path == root/'configs/docs/report_provenance.py' and hook.ROOT == root
            and Path(configuration.docs_dir).absolute() == root/'docs'
            and configuration.repo_url == 'https://github.com/bijux/bijux-pollenomics'
            and configuration.site_url == 'https://bijux.io/bijux-pollenomics/', 'owner or public mount differs')
    require(hook.MANIFEST == MANIFEST and hook.MANIFEST_SHA256 == MANIFEST_SHA256
            and hook.REPORT_PATHS == REPORT_PATHS and hook.NOTE_KEY == NOTE_KEY
            and hook.INTERNAL_PREFIXES == INTERNAL_PREFIXES, 'loaded constants differ')
    require(hook.hashlib is hashlib and hook.json is json and hook.Path is Path
            and hook.PurePosixPath is PurePosixPath and hook.MkDocsConfig is MkDocsConfig
            and hook.File is File and hook.Files is Files, 'loaded dependency binding differs')
    raw = regular(root, root/MANIFEST)
    require(digest(raw) == MANIFEST_SHA256, 'reviewed manifest differs')
    manifest = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    require(set(manifest) == {'schema', 'owner', 'reports'} and manifest['schema'] == 1
            and manifest['owner'] == 'bijux-pollenomics', 'manifest owner/schema differs')
    rows = manifest['reports']
    require(tuple(row['path'] for row in rows) == REPORT_PATHS and len(rows) == 13
            and sum(len(row['fields']) for row in rows) == 32, 'finite report population differs')
    inputs = [{'path': MANIFEST, 'sha256': digest(raw)}]
    outputs = {}
    for row in rows:
        require(set(row) == {'path', 'source_sha256', 'fields', 'public_sha256'}, 'report schema differs')
        relative = 'docs/' + row['path']
        original = regular(root, root/relative)
        value = project(original, row)
        inputs.append({'path': relative, 'sha256': digest(original)})
        outputs[row['path']] = digest(value)
    return {'source': path.relative_to(root).as_posix(), 'source_sha256': digest(source),
            'recipe': 'public-report-provenance', 'inputs': sorted(inputs, key=lambda item: item['path']),
            'outputs': outputs}
