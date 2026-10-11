"""Validate stylesheet and SVG resource graphs against their public artifact."""
from __future__ import annotations
from pathlib import Path
from urllib.parse import urljoin
from . import style_references, svg_references
from .documents import Document
from .destinations import route_url, resolve, is_network_boundary, validate_reference


def collect_svg_resources(site: Path, site_url: str) -> tuple[dict, list, list[str]]:
    errors = []
    svg_ids = {}
    svg_assets = []
    for path in sorted(path for path in site.rglob('*') if path.is_file() and path.suffix.lower() == '.svg'):
        label = path.relative_to(site).as_posix()
        try:
            ids, references = svg_references.read(path)
            svg_ids[path.resolve()] = ids
            svg_assets.extend((route_url(site_url,label),label,item) for item in references)
        except ValueError as exc:
            errors.append(f'{label}: {exc}')
    return svg_ids, svg_assets, errors


def validate_resources(site: Path, site_url: str, docs: dict[Path, Document],
                       network_urls: list[str], exceptions: list[dict],
                       observations: list[dict], svg_ids: dict, svg_assets: list) -> list[str]:
    errors = []
    for current, label, reference in svg_assets:
        failure = validate_reference(reference.url,current,reference.kind,label,exceptions,observations)
        if failure:
            errors.append(f'{label}: SVG resource: {failure}')
            continue
        if is_network_boundary(site_url,urljoin(current,reference.url),network_urls):
            continue
        try:
            target, fragment = resolve(site,site_url,current,reference.url)
        except ValueError as exc:
            errors.append(f'{label}: SVG resource: {exc}')
            continue
        if target is None:
            continue
        if not target.is_file():
            errors.append(f'{label}: missing SVG {reference.kind} destination {reference.url}')
        elif fragment and reference.fragment_id:
            ids = svg_ids.get(target, docs[target].svg_ids if target in docs else None)
            if ids is None:
                errors.append(f'{label}: SVG fragment requires an owned SVG destination {reference.url}')
            elif fragment not in ids:
                errors.append(f'{label}: missing SVG fragment {reference.url}')
    for path in sorted(site.rglob('*.css')):
        css = path.read_text(encoding='utf-8')
        label = path.relative_to(site).as_posix()
        current = urljoin(site_url,label)
        try:
            references = style_references.references(css)
        except ValueError as exc:
            errors.append(f'{label}: CSS resource syntax: {exc}')
            continue
        for reference in references:
            value = reference.url
            location = f'{label}:{reference.line}:{reference.column}'
            failure = validate_reference(value,current,'asset',label,exceptions,observations)
            if failure:
                errors.append(f'{location}: {failure}')
                continue
            try:
                target, _ = resolve(site,site_url,current,value)
            except ValueError as exc:
                errors.append(f'{location}: {exc}')
                continue
            if target is not None and not target.is_file():
                errors.append(f'{location}: missing CSS asset {value}')
    return errors
