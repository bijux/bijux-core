"""Resolve explicit refresh destinations and diagnose cycles in built routes."""
from __future__ import annotations
from pathlib import Path
import re
from .documents import Document
from .destinations import resolve, validate_reference


def refresh_destination(doc: Document) -> str:
    """Read one explicit refresh target without substituting its canonical URL."""
    failure = 'redirect refresh requires one unambiguous destination'
    if len(doc.refreshes) != 1 or not isinstance(doc.refreshes[0],str):
        raise ValueError(failure)
    match = re.fullmatch(r'\s*[0-9]+(?:\.[0-9]+)?\s*;\s*(?:url\s*=\s*)?(.*?)\s*',
                         doc.refreshes[0], re.IGNORECASE)
    if not match:
        raise ValueError(failure)
    destination = match[1]
    if destination.startswith(('"',"'")):
        if len(destination) < 2 or destination[-1] != destination[0]:
            raise ValueError(failure)
        destination = destination[1:-1].strip()
    if not destination:
        raise ValueError(failure)
    return destination


def redirect_destination(site: Path, site_url: str, doc: Document,
                         docs: dict[Path, Document], label: str,
                         observations: list[dict]) -> tuple[Path | None, str | None]:
    try:
        if any(doc.base_hrefs):
            return None, 'unsupported redirect base href for a public URL'
        value = refresh_destination(doc)
        # Automatic navigation cannot inherit an authored development-link exception.
        failure = validate_reference(value,doc.url,'asset',label,[],observations)
        if failure:
            return None, 'redirect refresh: ' + failure
        target, fragment = resolve(site,site_url,doc.url,value)
        if target not in docs:
            return None, 'redirect refresh must reach a built production route'
        if fragment and fragment not in docs[target].ids:
            return target, 'redirect refresh anchor is missing'
        if len(doc.canonicals) == 1:
            canonical, _ = resolve(site,site_url,doc.url,doc.canonicals[0])
            if target != canonical:
                return target, 'redirect refresh destination differs from canonical'
        return target, None
    except ValueError as exc:
        return None, str(exc)


def redirect_cycles(site: Path, edges: dict[Path, Path]) -> list[str]:
    """Traverse each built refresh edge once, including self and joined cycles."""
    errors = []
    finished = set()
    for source in edges:
        pending = {}
        current = source
        while current in edges and current not in finished:
            if current in pending:
                cycle = list(pending)[pending[current]:]
                errors.append('redirect refresh cycle: '+', '.join(sorted(p.relative_to(site).as_posix() for p in cycle)))
                break
            pending[current] = len(pending)
            current = edges[current]
        finished.update(pending)
    return errors
