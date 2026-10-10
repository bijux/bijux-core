"""Build a deterministic route inventory and resolve links against its artifact."""
from __future__ import annotations
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin
from .documents import Document
from .destinations import route_url, resolve, is_network_boundary, validate_reference
from .redirects import redirect_destination, redirect_cycles
from .resources import collect_svg_resources, validate_resources
from .sitemaps import validate_sitemaps


def inventory(site: Path, site_url: str) -> dict[Path, Document]:
    result = {}
    for path in sorted(site.rglob('*.html')):
        if path.is_symlink():
            raise ValueError(f'Symlink route is not admitted: {path.relative_to(site)}')
        doc = Document(path, route_url(site_url, path.relative_to(site).as_posix()))
        doc.feed(path.read_text(encoding='utf-8'))
        result[path.resolve()] = doc
    if not result or (site/'index.html').resolve() not in result:
        raise ValueError('Selected artifact must contain at least its root index.html')
    return result


def validate(site: Path, site_url: str, docs: dict[Path, Document], network_urls: list[str],
             exceptions: list[dict] | None = None,
             observations: list[dict] | None = None) -> list[str]:
    errors = []
    exceptions = exceptions or []
    observations = observations if observations is not None else []
    canonical_routes = set()
    redirect_edges = {}
    svg_ids, svg_assets, resource_errors = collect_svg_resources(site, site_url)
    errors.extend(resource_errors)
    for path, doc in docs.items():
        label = path.relative_to(site).as_posix()
        errors.extend(f'{label}: {failure}' for failure in doc.responsive_errors)
        errors.extend(f'{label}: {failure}' for failure in doc.svg_errors)
        svg_assets.extend((doc.url,label,item) for item in doc.svg_references)
        duplicate = [key for key, count in Counter(doc.ids).items() if count > 1]
        if duplicate:
            errors.append(f'{label}: duplicate document IDs: {", ".join(sorted(duplicate))}')
        if path.name != '404.html':
            # Redirect producers may identify their destination relative to this route.
            canonical = urljoin(doc.url, doc.canonicals[0]) if len(doc.canonicals) == 1 else None
            if len(doc.canonicals) != 1 or (not doc.redirect and doc.canonicals[0] != doc.url):
                errors.append(f'{label}: canonical must identify this production route ({doc.url})')
            elif not doc.noindex:
                canonical_routes.add(canonical)
            if doc.redirect and doc.canonicals:
                target, _ = resolve(site,site_url,doc.url,doc.canonicals[0])
                if target not in docs or canonical != docs[target].url:
                    errors.append(f'{label}: redirect canonical does not reach a built route')
        if doc.redirect:
            target, failure = redirect_destination(site,site_url,doc,docs,label,observations)
            if target is not None:
                redirect_edges[path] = target
            if failure:
                errors.append(f'{label}: {failure}')
        for kind, value in doc.references:
            failure = validate_reference(value,doc.url,kind,label,exceptions,observations)
            if failure:
                errors.append(f'{label}: {failure}')
                continue
            if is_network_boundary(site_url,urljoin(doc.url,value),network_urls):
                continue
            try:
                target, fragment = resolve(site,site_url,doc.url,value)
            except ValueError as exc:
                errors.append(f'{label}: {exc}')
                continue
            if target is None:
                continue
            if not target.is_file():
                errors.append(f'{label}: missing {kind} destination {value}')
            elif kind == 'link' and fragment and target in docs and fragment not in docs[target].ids:
                errors.append(f'{label}: missing anchor {value}')
    errors.extend(redirect_cycles(site,redirect_edges))
    errors.extend(validate_resources(site, site_url, docs, network_urls,
                                     exceptions, observations, svg_ids, svg_assets))
    errors.extend(validate_sitemaps(site, canonical_routes))
    return errors


def records(site: Path, docs: dict[Path, Document]) -> list[dict]:
    return [dict(path=path.relative_to(site).as_posix(), url=doc.url,
                 canonical=doc.canonicals, noindex=doc.noindex, redirect=doc.redirect,
                 anchors=len(set(doc.ids)), references=len(doc.references)+len(doc.svg_references))
            for path,doc in docs.items()]
