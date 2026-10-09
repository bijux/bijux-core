"""Verify native Material search index, worker delivery and same-site destinations."""
from __future__ import annotations
import json
from pathlib import Path
from .routes import Document, resolve


def validate(site: Path, site_url: str, docs: dict[Path, Document], *, verified_readers: dict | None = None) -> tuple[list[str], int]:
    errors = []
    index = site/'search/search_index.json'
    if not index.is_file():
        return ['Search index is absent from the selected production artifact'],0
    try:
        body = json.loads(index.read_text(encoding='utf-8'))
        entries = body['docs']
        if not isinstance(entries,list) or not entries:
            raise ValueError('Search corpus is empty or not a list')
    except (OSError,UnicodeError,json.JSONDecodeError,KeyError,TypeError,ValueError) as exc:
        return [f'Search index is invalid: {type(exc).__name__}'],0
    for number, entry in enumerate(entries):
        if not isinstance(entry,dict) or not isinstance(entry.get('location'),str) or not isinstance(entry.get('title'),str) or not entry.get('title') or not isinstance(entry.get('text'),str):
            errors.append(f'Search entry {number}: incomplete location/title/text contract')
            continue
        target, fragment = resolve(site,site_url,site_url,entry['location'])
        if target is None or target not in docs:
            errors.append(f'Search entry {number}: destination escapes this product or is not a built HTML route')
        elif fragment and fragment not in docs[target].ids:
            errors.append(f'Search entry {number}: destination anchor is missing')
        elif docs[target].noindex:
            # Public search eligibility is independently configurable; external noindex need not exclude native search.
            pass
    worker_targets = set()
    verified_readers = verified_readers or {}
    for path,doc in docs.items():
        if path.name == '404.html' or doc.redirect:
            continue
        reader = verified_readers.get(path.relative_to(site).as_posix())
        if reader is not None:
            if doc.config:
                errors.append(f'{path.relative_to(site)}: standalone report cannot impersonate Material configuration')
            continue
        try:
            config = json.loads(doc.config)
        except (json.JSONDecodeError,TypeError):
            errors.append(f'{path.relative_to(site)}: native search configuration is absent or invalid')
            continue
        worker = config.get('search')
        if not isinstance(worker,str) or not worker:
            errors.append(f'{path.relative_to(site)}: native search worker is not configured')
            continue
        target,_ = resolve(site,site_url,doc.url,worker)
        if target is None or not target.is_file() or target.suffix != '.js' or target.stat().st_size == 0:
            errors.append(f'{path.relative_to(site)}: configured search worker is absent/empty/outside the artifact')
        else:
            worker_targets.add(target)
    if not worker_targets:
        errors.append('No delivered native search worker was qualified')
    return errors,len(entries)
