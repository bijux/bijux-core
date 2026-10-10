"""Native MkDocs file protocol for an independently reconstructed catalogue.

This adapter is a renderer helper, not a publication admission receipt. Its
caller must first bind the reviewed recipe, committed capture and reconstruction.
"""
from __future__ import annotations

from typing import NamedTuple
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from mkdocs.plugins import BasePlugin, event_priority
from mkdocs.structure.files import File, Files, set_exclusions


class CatalogueSourceError(ValueError):
    """A public document has no verified original source identity."""


def confined(name):
    if (not isinstance(name, str) or not name or '\\' in name
            or any(ord(character) < 32 or ord(character) == 127 for character in name)
            or PurePosixPath(name).is_absolute()
            or any(part in {'', '.', '..'} for part in name.split('/'))):
        raise CatalogueSourceError('confined catalogue path required')
    return name


class OriginalDocument(NamedTuple):
    source: str
    route: str
    content: bytes


class CatalogueSources:
    """Bind public routes to verified originals without relabeling generated files."""

    def __init__(self, root, captured, documents):
        self.root = Path(root).resolve()
        self.captured = MappingProxyType(dict(captured))
        self.documents = tuple(documents)
        routes = {}
        for document in self.documents:
            source, route = confined(document.source), confined(document.route)
            if source not in self.captured or not isinstance(self.captured[source], bytes):
                raise CatalogueSourceError('catalogue original is outside committed capture')
            if not source.endswith('.md') or not route.endswith('.md'):
                raise CatalogueSourceError('catalogue document must retain Markdown identity')
            if not isinstance(document.content, bytes):
                raise CatalogueSourceError('reconstructed document bytes required')
            document.content.decode('utf-8', errors='strict')
            if route in routes:
                raise CatalogueSourceError('duplicate catalogue public route')
            routes[route] = document
        if not routes:
            raise CatalogueSourceError('nonempty catalogue required')
        self.routes = MappingProxyType(routes)

    def original_unchanged(self, source):
        path = self.root
        for component in source.split('/'):
            path /= component
            if path.is_symlink():
                raise CatalogueSourceError('catalogue original cannot use a symlink')
        if not path.is_file() or path.read_bytes() != self.captured[source]:
            raise CatalogueSourceError('catalogue original changed after capture')

    def unchanged(self):
        for source in {document.source for document in self.documents}:
            self.original_unchanged(source)

    def files(self, existing, configuration):
        self.unchanged()
        # Extra documentation cannot disappear merely because the catalogue
        # uses an explicit route map. Assets retain their native copy path.
        for item in existing.documentation_pages():
            if item.src_uri not in self.routes:
                raise CatalogueSourceError('unowned documentation outside reconstructed plan')
        files = [item for item in existing if not item.is_documentation_page()]
        for route, document in self.routes.items():
            item = File(route, str(self.root), configuration.site_dir,
                        configuration.use_directory_urls)
            item.abs_src_path = str(self.root / document.source)
            item.edit_uri = document.source
            files.append(item)
        set_exclusions(files, configuration)
        return Files(files)

    def read(self, page):
        document = self.routes.get(page.file.src_uri)
        if document is None:
            raise CatalogueSourceError('documentation route outside reconstructed plan')
        self.original_unchanged(document.source)
        if (page.file.abs_src_path != str(self.root / document.source)
                or page.file.generated_by is not None
                or page.file.edit_uri != document.source):
            raise CatalogueSourceError('native catalogue original identity was replaced')
        return document.content.decode('utf-8', errors='strict')


class CatalogueSourcePlugin(BasePlugin):
    """Reviewed public events preserve original Git history and projected content."""

    def __init__(self, sources):
        super().__init__()
        self.sources = sources

    @event_priority(100)
    def on_files(self, files, config):
        return self.sources.files(files, config)

    @event_priority(100)
    def on_page_read_source(self, page, config):
        return self.sources.read(page)
