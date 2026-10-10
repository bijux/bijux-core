"""Reconcile plain and compressed sitemaps with eligible built canonical routes."""
from __future__ import annotations
from pathlib import Path
import xml.etree.ElementTree as ET


def validate_sitemaps(site: Path, canonical_routes: set[str]) -> list[str]:
    errors = []
    sitemap = site/'sitemap.xml'
    if not sitemap.is_file():
        errors.append('Selected artifact is missing sitemap.xml')
    else:
        try:
            urls = [node.text or '' for node in ET.parse(sitemap).iter() if node.tag.rsplit('}',1)[-1] == 'loc']
            if len(urls) != len(set(urls)):
                errors.append('sitemap.xml: duplicate route entries')
            unknown = set(urls)-canonical_routes
            missing = canonical_routes-set(urls)
            if unknown:
                errors.append('sitemap.xml: noncanonical/nonproduction/excluded routes: '+', '.join(sorted(unknown)))
            if missing:
                errors.append('sitemap.xml: missing eligible canonical routes: '+', '.join(sorted(missing)))
        except ET.ParseError:
            errors.append('sitemap.xml: invalid XML')
    compressed = site/'sitemap.xml.gz'
    if compressed.exists():
        import gzip
        from io import BytesIO
        try:
            plain = sitemap.read_bytes()
            if compressed.is_symlink() or gzip.GzipFile(fileobj=BytesIO(compressed.read_bytes())).read(len(plain)+1) != plain:
                errors.append('sitemap.xml.gz: content differs from the plain sitemap')
        except (OSError,EOFError):
            errors.append('sitemap.xml.gz: invalid compressed sitemap')
    return errors
