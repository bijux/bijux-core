"""Read explicit SVG resource references without admitting executable capabilities."""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.parsers import expat
from . import style_references


SVG = 'http://www.w3.org/2000/svg'
XLINK = 'http://www.w3.org/1999/xlink'
XML = 'http://www.w3.org/XML/1998/namespace'
RESOURCE_TAGS = {'image', 'use', 'script', 'feimage'}
PAINT_ATTRIBUTES = {'fill', 'stroke', 'filter', 'clip-path', 'mask',
                    'marker', 'marker-start', 'marker-mid', 'marker-end', 'cursor', 'style'}


@dataclass(frozen=True)
class Reference:
    kind: str
    url: str
    fragment_id: bool = False


def attributes(tag: str, attrs: list[tuple[str, str | None]]) -> list[Reference]:
    """Select one native href identity and literal SVG paint/style URLs."""
    values = [(('xlink:href' if name == '{'+XLINK+'}href' else
                'xml:base' if name == '{'+XML+'}base' else name), value)
              for name, value in attrs]
    if any(name == 'xml:base' and value for name, value in values):
        raise ValueError('unsupported SVG xml:base resource authority')
    result = []
    if tag in RESOURCE_TAGS or tag == 'a':
        hrefs = [(name, value) for name, value in values if name in {'href', 'xlink:href'}]
        if len({name for name, _ in hrefs}) != len(hrefs) or len({value for _, value in hrefs}) > 1:
            raise ValueError('ambiguous SVG resource href')
        if hrefs and hrefs[0][1]:
            result.append(Reference('link' if tag == 'a' else 'asset', hrefs[0][1], tag == 'use'))
    for name, value in values:
        if name in PAINT_ATTRIBUTES and value:
            result.extend(Reference('asset', item.url, True) for item in style_references.references(value))
    return result


def inspect_document_type(data: bytes) -> None:
    """Keep inert external SVG metadata while refusing DTD-defined authority."""
    parser = expat.ParserCreate()
    def doctype(name, system, public, internal):
        if name != 'svg' or internal:
            raise ValueError('SVG document types/entities with internal authority are outside resource inspection')
    def entity(*args):
        raise ValueError('SVG document types/entities are outside resource inspection')
    parser.StartDoctypeDeclHandler = doctype
    parser.EntityDeclHandler = entity
    parser.ExternalEntityRefHandler = entity
    # External PUBLIC/SYSTEM identifiers are metadata, never fetched or expanded.
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.Parse(data, True)


def read(path: Path) -> tuple[list[str], list[Reference]]:
    """Inspect one finite public SVG asset; XML comments/CDATA are ordinary data."""
    data = path.read_bytes()
    try:
        inspect_document_type(data)
        root = ET.fromstring(data)
    except (ET.ParseError, expat.ExpatError) as exc:
        raise ValueError('invalid SVG XML: '+str(exc)) from exc
    if root.tag not in {'svg', '{'+SVG+'}svg'}:
        raise ValueError('public SVG asset requires an SVG root')
    ids, references = [], []
    for element in root.iter():
        # Namespaced SVG and unqualified authored SVG have the same owned fields.
        if not isinstance(element.tag, str) or (element.tag.startswith('{') and not element.tag.startswith('{'+SVG+'}')):
            continue
        tag = element.tag.rsplit('}', 1)[-1].lower()
        if element.get('id'):
            ids.append(element.get('id'))
        references.extend(attributes(tag, list(element.attrib.items())))
        if tag == 'style':
            references.extend(Reference('asset', item.url, True) for item in
                              style_references.references(''.join(element.itertext())))
    duplicates = sorted(name for name, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError('duplicate SVG IDs: '+', '.join(duplicates))
    return ids, references
