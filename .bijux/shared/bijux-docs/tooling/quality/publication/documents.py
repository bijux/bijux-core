"""Parse built HTML into publication-owned anchors and resource references."""
from __future__ import annotations
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import math
import re
from . import style_references, svg_references


def responsive_candidates(value: str) -> list[str]:
    """Collect conforming candidates without splitting commas inside URLs."""
    whitespace = ' \t\n\f\r'
    result = []
    descriptors = set()
    mode = None
    position = 0
    while position < len(value):
        while position < len(value) and value[position] in whitespace:
            position += 1
        if position == len(value):
            break
        if value[position] == ',':
            raise ValueError('empty candidate')
        start = position
        # URL tokens end at ASCII whitespace. Internal commas belong to the URL.
        while position < len(value) and value[position] not in whitespace:
            position += 1
        url = value[start:position]
        descriptor = ''
        if url.endswith(','):
            url = url[:-1]
            if url.endswith(','):
                raise ValueError('repeated candidate separator')
        else:
            start = position
            while position < len(value) and value[position] != ',':
                position += 1
            descriptor = value[start:position].strip(whitespace)
            if position < len(value):
                position += 1
        if not url:
            raise ValueError('missing candidate URL')
        if not descriptor:
            kind, number = 'x', 1.0
        elif re.fullmatch(r'[0-9]+w',descriptor):
            kind, number = 'w', int(descriptor[:-1])
        elif re.fullmatch(r'(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?x',descriptor):
            kind, number = 'x', float(descriptor[:-1])
        else:
            raise ValueError('unsupported or ambiguous descriptor')
        if number <= 0 or (kind == 'x' and not math.isfinite(number)):
            raise ValueError('nonpositive or nonfinite descriptor')
        if (mode is not None and kind != mode) or number in descriptors:
            raise ValueError('mixed or duplicate descriptors')
        mode = kind
        descriptors.add(number)
        result.append(url)
    return result


class Document(HTMLParser):
    def __init__(self, path: Path, url: str):
        super().__init__(convert_charrefs=True)
        self.path, self.url = path, url
        self.ids: list[str] = []
        self.references: list[tuple[str, str]] = []
        self.canonicals: list[str] = []
        self.noindex = False
        self.redirect = False
        self.refreshes: list[str | None] = []
        self.base_hrefs: list[str | None] = []
        self.responsive_errors: list[str] = []
        self.svg_errors: list[str] = []
        self.svg_references: list[svg_references.Reference] = []
        self.svg_ids: list[str] = []
        self._svg_depth = 0
        self._svg_foreign = False
        self._svg_scopes = []
        self._svg_style = False
        self._svg_style_data = ''
        self.config = ''
        self._config = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'svg':
            self._svg_scopes.append((tag, self._svg_foreign))
            self._svg_foreign = False
            self._svg_depth += 1
        svg_context = self._svg_depth and not self._svg_foreign
        if svg_context:
            if values.get('id'):
                self.svg_ids.append(values['id'])
            try:
                self.svg_references.extend(svg_references.attributes(tag, attrs))
            except ValueError as exc:
                self.svg_errors.append(str(exc))
            if tag == 'style':
                self._svg_style = True
                self._svg_style_data = ''
            if tag == 'foreignobject':
                self._svg_scopes.append((tag, self._svg_foreign))
                self._svg_foreign = True
        if tag == 'base':
            self.base_hrefs.extend(value for key,value in attrs if key == 'href')
        if values.get('id'):
            self.ids.append(values['id'])
        if tag == 'a' and values.get('name') and values.get('name') != values.get('id'):
            self.ids.append(values['name'])
        if tag == 'link' and 'canonical' in (values.get('rel') or '').split():
            self.canonicals.append(values.get('href') or '')
        elif tag in {'a', 'area', 'link'} and values.get('href') and not (svg_context and tag == 'a'):
            self.references.append(('link' if tag in {'a','area'} else 'asset', values['href']))
        for key in ('src', 'poster', 'action', 'formaction'):
            if values.get(key):
                self.references.append(('asset', values[key]))
        attribute = 'srcset' if tag in {'img','source'} else 'imagesrcset' if tag == 'link' else None
        alternatives = [value or '' for key,value in attrs if key == attribute]
        if alternatives:
            try:
                if len(alternatives) != 1:
                    raise ValueError('duplicate attribute')
                self.references.extend(('asset',url) for url in responsive_candidates(alternatives[0]))
            except ValueError as exc:
                self.responsive_errors.append(f'invalid responsive asset candidates ({attribute}): {exc}')
        if tag == 'meta':
            self.noindex |= values.get('name','').lower() == 'robots' and 'noindex' in values.get('content','').lower()
            if any(key == 'http-equiv' and (value or '').strip().lower() == 'refresh' for key,value in attrs):
                self.redirect = True
                # Ambiguous duplicate attributes cannot select browser authority.
                counts = Counter(key for key,_ in attrs)
                self.refreshes.append(values.get('content') if counts['http-equiv'] == counts['content'] == 1 else None)
        if tag == 'script' and values.get('id') == '__config':
            self._config = True

    def handle_endtag(self, tag):
        if tag == 'style' and self._svg_style:
            try:
                self.svg_references.extend(svg_references.Reference('asset', item.url, True)
                    for item in style_references.references(self._svg_style_data))
            except ValueError as exc:
                self.svg_errors.append(str(exc))
            self._svg_style = False
        if tag == 'svg' and self._svg_depth:
            self._svg_depth -= 1
        if tag in {'svg','foreignobject'} and self._svg_scopes and self._svg_scopes[-1][0] == tag:
            _, self._svg_foreign = self._svg_scopes.pop()
        if tag == 'script':
            self._config = False

    def handle_data(self, data):
        if self._svg_style:
            self._svg_style_data += data
        if self._config:
            self.config += data
