"""Reviewed catalogue derivation from captured committed original sources."""
from __future__ import annotations

import builtins
import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path
import sys
import types

RECIPE = 'masterclass-catalogue'
OWNER = 'mkdocs.yml'
CONFIGURATION = 'artifacts/mkdocs.root.yml'
GENERATOR = {
    'scripts/catalogue/__init__.py': 'f71b4484e0bfbef60b2d0f2edab0931df44286fe85a472de97ddc6988e5bafd5',
    'scripts/catalogue/files.py': 'a15bca4b54bcdaaab17a8f84f00ec81749ce8f3a53275a38aa7a32d5d4e7958a',
    'scripts/catalogue/links.py': '5baf4684642fdf40ba1a8a10a3215576a839598416058284fd060b3f13842d2a',
    'scripts/catalogue/source_plan.py': 'c113463e8c3c44a3970a083fd13867b44a6584e5a06724f6d833a7cc981f31cc',
    'scripts/docs_nav.py': 'c0afae8d877459b517a10c1642a8bf20cd633622231b9721515710251087a76c',
    'scripts/render_root_mkdocs.py': '05ce8d0ca82b005b91a92d167aecadd21f366a78c899b38d66e3c89ba674f11d',
    'scripts/sync_series_docs.py': '65f43a155a0a64ab492d9a2fa7bbfdfce0c44663f4f9ad04a8ce96a0c4834d06',
}
MODULES = {'scripts.catalogue.links': 'scripts/catalogue/links.py',
           'scripts.docs_nav': 'scripts/docs_nav.py',
           'scripts.catalogue.source_plan': 'scripts/catalogue/source_plan.py'}
IMPORTS = {'__future__', 'collections.abc', 'dataclasses', 'hashlib', 'pathlib',
           'typing', 'yaml', 're', 'html', 'html.parser', 'urllib.parse', 'functools'}


class RecipeError(ValueError):
    """A catalogue derivation has no reviewed committed source authority."""


def require(value, message):
    if not value:
        raise RecipeError('Catalogue recipe: ' + message)


def require_native_history_environment():
    """The selected source root owns Git storage, worktree and graft authority."""
    for name in ('GIT_GRAFT_FILE', 'GIT_DIR', 'GIT_COMMON_DIR', 'GIT_WORK_TREE'):
        require(name not in os.environ, 'native history environment override forbidden: ' + name)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def json_digest(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def shared_module(path):
    require(path.is_file() and not path.is_symlink(), 'regular shared helper required')
    source = path.read_bytes()
    name = 'bijux_catalogue_' + path.stem
    require(name not in sys.modules, 'cached shared helper forbidden')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    try:
        exec(compile(source, str(path), 'exec'), module.__dict__)
        require(path.read_bytes() == source, 'shared helper changed during capture')
        return module
    finally:
        # Callback source identity remains inspectable through __file__; there
        # is no global cache authority that a later candidate can inherit.
        sys.modules.pop(name, None)


def captured_generator(root, originals):
    """Compile only the exact reviewed source set with fixed dependency routing."""
    require(all(name in originals and digest(originals[name]) == expected
                for name, expected in GENERATOR.items()), 'generator source differs from reviewed recipe')
    modules = {}
    registered = []

    def importer(name, globals=None, locals=None, fromlist=(), level=0):
        require(level == 0, 'relative generator import forbidden')
        if name in MODULES:
            require(bool(fromlist), 'reviewed generator import must name its symbols')
            return load(name)
        require(name in IMPORTS, 'unreviewed generator dependency: ' + name)
        return builtins.__import__(name, globals, locals, fromlist, level)

    def load(public):
        if public in modules:
            return modules[public]
        path = MODULES[public]
        private = 'bijux_catalogue_recipe_' + digest((str(root) + ':' + path).encode())
        require(private not in sys.modules, 'cached generator module forbidden')
        module = types.ModuleType(private)
        module.__file__ = str(root / path)
        module.__dict__['__builtins__'] = dict(vars(builtins), __import__=importer)
        modules[public] = module
        sys.modules[private] = module
        registered.append(private)
        exec(compile(originals[path], str(root / path), 'exec'), module.__dict__)
        return module

    try:
        return load('scripts.catalogue.source_plan')
    finally:
        for name in registered:
            sys.modules.pop(name, None)


class CatalogueDerivation:
    """In-memory source authority created only through the reviewed constructor."""

    def __init__(self, root, shared, inputs, plan, environment, helper):
        self.root, self.shared = root, shared
        self.inputs, self.plan, self.environment = inputs, plan, environment
        self.helper = helper
        self.sources = helper.CatalogueSources(root, inputs, [
            helper.OriginalDocument(item.source, item.destination.removeprefix('docs/'), item.content)
            for item in plan.documents])
        self.plugin = None
        def git(*arguments):
            require_native_history_environment()
            result = subprocess.run(['git', '-C', str(root), *arguments], capture_output=True, text=True)
            require(result.returncode == 0, 'native source history operation failed')
            return result.stdout.strip()
        require(not os.environ.get('GIT_REPLACE_REF_BASE'), 'alternate native replacement namespace forbidden')
        require(git('rev-parse', '--is-shallow-repository') == 'false', 'complete native original history required')
        require(not git('for-each-ref', '--format=%(refname)', 'refs/replace'), 'replacement source history forbidden')
        common = Path(git('rev-parse', '--git-common-dir'))
        if not common.is_absolute():
            common = root / common
        require(not (common / 'info/grafts').exists(), 'grafted source history forbidden')
        history = git('log', '--format=%H:%at:%ct:%P', 'HEAD', '--', 'programs')
        require(bool(history), 'native original course history required')
        self.map = [{'route': item.destination.removeprefix('docs/'), 'source': item.source,
                     'source_sha256': digest(inputs[item.source]), 'content_sha256': digest(item.content)}
                    for item in plan.documents]
        self.record = {'schema': 1, 'recipe': RECIPE,
                       'owner': {'path': OWNER, 'sha256': digest(inputs[OWNER])},
                       'configuration': {'path': CONFIGURATION, 'sha256': digest(plan.configuration.content)},
                       'generator': dict(GENERATOR), 'environment': dict(environment),
                       'source_inputs_sha256': json_digest(dict(plan.source_hashes)),
                       'documents': len(self.map), 'document_map_sha256': json_digest(self.map),
                       'native_history_sha256': digest(history.encode())}

    def configuration(self, site_dir):
        from mkdocs.config import load_config
        self.verify_outputs()
        configuration = load_config(config_file=str(self.root / CONFIGURATION), site_dir=str(site_dir))
        require(configuration.docs_dir == str(self.root / 'docs'), 'derived docs root differs')
        require('bijux/catalogue-sources' not in configuration.plugins, 'foreign catalogue plugin declared')
        self.plugin = self.helper.CatalogueSourcePlugin(self.sources)
        configuration.plugins['bijux/catalogue-sources'] = self.plugin
        return configuration

    def verify_outputs(self):
        from_path = self.root / CONFIGURATION
        for path in [from_path, *from_path.parents]:
            require(not path.is_symlink(), 'derived configuration symlink forbidden')
            if path == self.root:
                break
        require(from_path.is_file() and from_path.stat().st_nlink == 1,
                'regular unlinked derived configuration required')
        require(from_path.read_bytes() == self.plan.configuration.content,
                'configuration differs from independently reconstructed owner')
        expected = {name: data for name, data in self.inputs.items() if name.startswith('docs/')}
        for document in self.plan.documents:
            require(document.destination not in expected, 'derived document overwrites committed input')
            expected[document.destination] = document.content
        actual = {}
        directory = self.root / 'docs'
        require(directory.is_dir() and not directory.is_symlink(), 'regular docs root required')
        for path in directory.rglob('*'):
            require(not path.is_symlink(), 'derived docs symlink forbidden')
            if path.is_dir():
                continue
            require(path.is_file() and path.stat().st_nlink == 1, 'regular unlinked derived docs required')
            if path.suffix == '.pyc':
                source = Path(importlib.util.source_from_cache(str(path)))
                name = source.relative_to(self.root).as_posix()
                require(name == 'docs/hooks/publish_site_assets.py' and name in self.inputs
                        and source.read_bytes() == self.inputs[name],
                        'cache must belong to the captured publication hook')
                shared_module(self.shared / 'security/renderer_profiles.py').validate_bytecode(path)
                continue
            actual[path.relative_to(self.root).as_posix()] = path.read_bytes()
        require(actual == expected, 'docs contain changed, missing or extra bytes outside committed reconstruction')

    def input_records(self, configuration):
        self.verify_outputs()
        directories = [Path(configuration.docs_dir)]
        custom = configuration.theme.get('custom_dir')
        if custom:
            directories.append(Path(custom))
        records = []
        for directory in sorted(set(directories)):
            require(directory.is_relative_to(self.root), 'renderer input outside source owner')
            values = {path.relative_to(self.root).as_posix(): path.read_bytes()
                      for path in directory.rglob('*') if path.is_file()}
            if directory != self.root / 'docs':
                require(values == {name: data for name, data in self.inputs.items()
                                   if name.startswith(directory.relative_to(self.root).as_posix() + '/')},
                        'custom renderer input differs from committed source')
            records.append({'path': directory.relative_to(self.root).as_posix(),
                            'sha256': json_digest({'files': [{'path': Path(name).relative_to(directory.relative_to(self.root)).as_posix(),
                                                               'sha256': digest(data)} for name, data in sorted(values.items())]})})
        return records


def derive(root, shared, recipe, *, inputs=None, expected=None):
    require(recipe == RECIPE, 'unknown recipe')
    root, shared = Path(root).absolute(), Path(shared).absolute()
    require_native_history_environment()
    producer = shared_module(shared / 'security/producer_authority.py')
    captured = producer.repository_files(root)
    if inputs is not None:
        require(inputs == captured, 'caller input differs from committed source capture')
    originals = {name: data for name, data in captured.items()
                 if name in {OWNER, 'mkdocs.shared.yml', *GENERATOR}
                 or name.startswith('programs/') and (name.endswith('.md') or name.endswith('/mkdocs.yml'))}
    import yaml
    def env_names(node):
        if getattr(node, 'tag', None) == '!ENV':
            value = node.value[0].value if isinstance(node, yaml.SequenceNode) and node.value else node.value
            require(value == 'SITE_URL', 'unreviewed configuration ENV input')
        if isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                env_names(key)
                env_names(value)
        elif isinstance(node, yaml.SequenceNode):
            for value in node.value:
                env_names(value)
    for name, content in originals.items():
        if name.endswith('.yml'):
            env_names(yaml.compose(content.decode('utf-8')))
    shared_node = yaml.compose(originals['mkdocs.shared.yml'].decode('utf-8'))
    require(isinstance(shared_node, yaml.MappingNode)
            and all(key.value != 'INHERIT' for key, _ in shared_node.value),
            'shared configuration cannot inherit uncaptured configuration')
    environment = {'SITE_URL': os.environ.get('SITE_URL')}
    module = captured_generator(root, originals)
    plan = module.build_plan(originals, environment={} if environment['SITE_URL'] is None else environment)
    require(plan.configuration.owner == OWNER and plan.configuration.destination == CONFIGURATION,
            'reviewed configuration ownership differs')
    require(set(dict(plan.source_hashes)) == set(originals), 'generator source map differs')
    require(dict(plan.source_hashes) == {name: digest(data) for name, data in originals.items()}, 'generator source digest differs')
    require(plan.configuration.environment == (() if environment['SITE_URL'] is None else (('SITE_URL', environment['SITE_URL']),)),
            'unreviewed ENV input in catalogue configuration')
    helper = shared_module(shared / 'security/catalogue_sources.py')
    result = CatalogueDerivation(root, shared, captured, plan, environment, helper)
    result.verify_outputs()
    require(expected is None or result.record == expected, 'record differs from actual committed reconstruction')
    require(captured == producer.repository_files(root), 'source changed during reconstruction')
    return result
