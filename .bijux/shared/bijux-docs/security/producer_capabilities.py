"""Admit reviewed source asset callbacks and actual revision-history inputs."""
from __future__ import annotations

import ast
import csv
import hashlib
import importlib.metadata
import inspect
import json
import marshal
from pathlib import Path
import subprocess
import types
import sysconfig
import sys
from urllib.parse import urlsplit

HOOKS = {
    'ca8006f2c2665aecc7f2566344f4ad926ea6a2279e7a7ff5d7ae35bbee256c93':'core-contract-assets',
    '4f04c4736adc9b9ff801bb2e2214e4bb622b8858aac16a9f6ae88b49ff2f7e84':'root-icons',
    'bda022ee3efa9393f03cda2d49684ba186d67714a362f4225890b8d4b15583d5':'source-assets-and-root-icons',
    '3162000c64180ca575be718c03ecdfe90bc0f53240eb4101947356c863848906':'scientific-pdf-downloads',
    'f714e9c71a7213f573007baf2f54aab1f5ec3375b7481bb48b64f2d06923a88b':'root-icons-and-custom-domain',
}
ICONS=('favicon.ico','apple-touch-icon.png','apple-touch-icon-precomposed.png')
PLUGINS={'material/search','autorefs','redirects','git-revision-date-localized','material/social','material/tags','minify','glightbox'}
EXTENSION_PLUGINS = {
    'minify': ('mkdocs-minify-plugin', '0.8.0', 'mkdocs_minify_plugin'),
    'glightbox': ('mkdocs-glightbox', '0.5.2', 'mkdocs_glightbox'),
}
PDF_VERIFIER = 'reports/exports/papers/verify.py'
PDF_VERIFIER_SHA256 = {
    '87a4e621c498572cbc6060b7be2b3ce0b296523245bddc0878bd6bcb5986e758',
    'b6c60e27d9b53de7900017121c0d98b9bee4342aee252875cdbcda66a3f8c9a2',
}


class CapabilityError(ValueError):
    pass


def require(condition,message):
    if not condition:
        raise CapabilityError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(root,path):
    require(path.is_relative_to(root) and path.is_file(), 'Producer capability: source must belong to owner repository')
    for item in (path,*path.parents):
        require(not item.is_symlink(),'Producer capability: source symlink forbidden')
        if item==root:break
    return path.read_bytes()


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()


def reviewed_hook_functions(hook, source, path):
    """Bind every helper and the registered callback to reviewed executable source."""
    expected=compile(source,str(path),'exec',dont_inherit=True)
    declared={node.name for node in ast.parse(source).body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
    functions={item.co_name:item for item in expected.co_consts if isinstance(item,types.CodeType) and item.co_name in declared}
    require(set(functions)==declared,'Producer capability: declared callback compilation differs')
    require({name for name,value in vars(hook).items() if name.startswith('on_') and callable(value)}=={name for name in declared if name.startswith('on_')},'Producer capability: undeclared hook callback')
    for name,code in functions.items():
        actual=getattr(hook,name,None)
        require(inspect.isfunction(actual) and actual.__code__==code and actual.__globals__ is vars(hook),
                'Producer capability: loaded callback differs from reviewed source')


def scientific_downloads(hook, root, path, source):
    """Preserve the reviewed finite PDF exports and all of their source inputs."""
    import runpy
    from pathlib import PurePosixPath
    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.structure.files import File, Files
    require(path == root/'configs/docs/science_downloads.py'
            and hook.ROOT == root and hook.MANIFEST == 'reports/exports/site-downloads.json'
            and hook.DECKS == ('big-picture','developer','scientific-evidence'),
            'Producer capability: scientific download owner or constants changed')
    require(hook.csv is csv and hook.hashlib is hashlib and hook.json is json
            and hook.Path is Path and hook.PurePosixPath is PurePosixPath and hook.runpy is runpy
            and hook.MkDocsConfig is MkDocsConfig and hook.File is File and hook.Files is Files,
            'Producer capability: scientific download dependency binding changed')
    require(digest(regular(root, root/PDF_VERIFIER)) in PDF_VERIFIER_SHA256,
            'Producer capability: scientific export verifier differs from reviewed source')
    # The original callback performs this same exact population and byte validation
    # before creating native MkDocs files; the admission independently freezes it.
    frozen=hook.download_bytes(root)
    require(isinstance(frozen,dict) and len(frozen)==12,
            'Producer capability: scientific download population differs')
    manifest=json.loads(regular(root,root/hook.MANIFEST))
    deck_lock=json.loads(regular(root,root/'presentation/source-lock.json'))
    paper_manifest=json.loads(regular(root,root/'reports/exports/papers/manifest.json'))
    names={hook.MANIFEST,PDF_VERIFIER,'presentation/source-lock.json',
           'reports/exports/papers/manifest.json','reports/exports/papers/visual-review.json',
           'reports/science/paper-accounts.csv',paper_manifest['inventory']}
    names.update(manifest['inputs'])
    names.update(deck_lock['sources'])
    names.update(paper_manifest['producer_sha256'])
    for row in manifest['files']:
        names.update((row['path'],row['canonical_source']))
    for row in paper_manifest['papers']:
        names.add(row['canonical_report'])
    inputs=[]
    for name in sorted(names):
        require(isinstance(name,str) and bool(name) and not PurePosixPath(name).is_absolute()
                and all(part not in {'','.','..'} for part in name.split('/')) and '\\' not in name,
                'Producer capability: canonical scientific source path required')
        inputs.append({'path':name,'sha256':digest(regular(root,root/name))})
    return {'source':path.relative_to(root).as_posix(),'source_sha256':digest(source),
            'recipe':'scientific-pdf-downloads','inputs':inputs,
            'outputs':{name:digest(value) for name,value in sorted(frozen.items())}}


CORE_CONTRACT_ASSETS = (
    'schemas/output-envelope-v1.schema.json',
    'schemas/error-envelope-v1.schema.json',
    'schemas/plugin-manifest-v2.schema.json',
    'official_product_namespace_registry.json',
    'product_mount_metadata_contract.json',
)


def core_contract_assets(hook, configuration, root, path, source, *, publication=False):
    """Bind Core's curated source links and five native contract copies."""
    import posixpath
    import re
    import shutil
    from urllib.parse import unquote, urlsplit, urlunsplit
    require(path == root/'docs/automation/publish_contract_assets.py'
            and tuple(hook.CONTRACT_ASSETS) == CORE_CONTRACT_ASSETS
            and Path(configuration.docs_dir).absolute() == root/'docs'
            and configuration['repo_url'] == 'https://github.com/bijux/bijux-core',
            'Producer capability: Core contract owner, source root or population changed')
    require(hook.posixpath is posixpath and hook.re is re and hook.shutil is shutil
            and hook.Path is Path and hook.unquote is unquote
            and hook.urlsplit is urlsplit and hook.urlunsplit is urlunsplit,
            'Producer capability: Core contract dependency binding changed')
    require(isinstance(hook.MARKDOWN_LINK, re.Pattern)
            and hook.MARKDOWN_LINK.pattern == r'(?<!!)(\[[^\]]+\]\()([^)]+)(\))'
            and hook.MARKDOWN_LINK.flags == re.UNICODE
            and isinstance(hook.HTML_LINK, re.Pattern)
            and hook.HTML_LINK.pattern == r"""(href\s*=\s*["'])([^"']+)(["'])"""
            and hook.HTML_LINK.flags == re.UNICODE | re.IGNORECASE,
            'Producer capability: Core source-link recognition changed')
    inputs, outputs = [], {}
    for name in CORE_CONTRACT_ASSETS:
        relative = 'contracts/' + name
        value = regular(root, root/relative)
        require(isinstance(json.loads(value), (dict, list)),
                'Producer capability: Core contract must retain JSON document identity')
        if publication:
            git(root, 'ls-files', '--error-unmatch', relative)
        inputs.append({'path': relative, 'sha256': digest(value)})
        outputs[relative] = digest(value)
    return {'source': path.relative_to(root).as_posix(), 'source_sha256': digest(source),
            'recipe': 'core-contract-assets', 'inputs': inputs, 'outputs': outputs}


def hooks(configuration,root,*,publication=False):
    records=[]
    for hook in configuration.hooks.values():
        require(isinstance(hook,types.ModuleType),'Producer capability: source-owned hook module required')
        path=Path(hook.__file__).absolute();source=regular(root,path);recipe=HOOKS.get(digest(source))
        require(recipe is not None,'Producer capability: hook needs a reviewed source recipe')
        if publication:
            git(root,'ls-files','--error-unmatch',path.relative_to(root).as_posix())
        reviewed_hook_functions(hook,source,path)
        if recipe=='core-contract-assets':
            records.append(core_contract_assets(hook,configuration,root,path,source,publication=publication))
            continue
        if recipe=='scientific-pdf-downloads':
            records.append(scientific_downloads(hook,root,path,source))
            continue
        require(tuple(hook.ROOT_ICON_FILENAMES)==ICONS,'Producer capability: loaded icon contract changed')
        docs=Path(configuration.docs_dir).absolute();assets=docs/'assets'
        if recipe=='source-assets-and-root-icons':
            require(hook.REPO_ROOT==root and hook.SHARED_ASSET_SOURCE_DIR==root/'docs/assets',
                    'Producer capability: loaded source asset root changed')
            if not assets.exists():assets=root/'docs/assets'
            require(hook._asset_source_dir(configuration)==assets,'Producer capability: selected asset source changed')
        require(assets.is_relative_to(root) and assets.is_dir() and not assets.is_symlink(),
                'Producer capability: owned asset source directory required')
        inputs=[]
        outputs={}
        if recipe=='source-assets-and-root-icons':
            for asset in sorted(assets.rglob('*')):
                require(not asset.is_symlink(),'Producer capability: recursive asset symlink forbidden')
                if asset.is_file():
                    value=regular(root,asset);relative=asset.relative_to(assets).as_posix()
                    inputs.append({'path':asset.relative_to(root).as_posix(),'sha256':digest(value)})
                    outputs['assets/'+relative]=digest(value)
        for icon in ICONS:
            value=regular(root,assets/'site-icons'/icon)
            inputs.append({'path':(assets/'site-icons'/icon).relative_to(root).as_posix(),'sha256':digest(value)})
            outputs[icon]=digest(value)
        if recipe=='root-icons-and-custom-domain':
            import shutil
            require(hook.REPO_ROOT==root and hook.Path is Path and hook.shutil is shutil,
                    'Producer capability: custom domain callback owner or dependency changed')
            value=regular(root,root/'CNAME')
            require(value==((urlsplit(configuration.site_url).hostname or '')+'\n').encode()
                    and len(value)<=254 and b'/' not in value and b':' not in value,
                    'Producer capability: custom domain differs from production URL')
            inputs.append({'path':'CNAME','sha256':digest(value)})
            outputs['CNAME']=digest(value)
        records.append({'source':path.relative_to(root).as_posix(),'source_sha256':digest(source),
                        'recipe':recipe,'inputs':sorted(inputs,key=lambda item:item['path']),'outputs':outputs})
    return records


def committed_document_history(root, paths, head):
    """Require exact indexed and committed owners for native revision pages.

    Every file in the selected committed tree has path history, including a
    shallow boundary commit. Checking that exact tree and index avoids one Git
    process per page without approximating path-limited merge simplification.
    Staged, generated, unmerged or symlinked pages cannot acquire publication
    history from unrelated reachable commits or build-date fallback.
    """
    indexed = {}
    for record in git(root, 'ls-files', '--stage', '-z').split('\0'):
        if not record:
            continue
        metadata, name = record.split('\t', 1)
        mode, blob, stage = metadata.split()
        require(stage == '0' and name not in indexed,
                'Producer capability: unmerged or duplicate indexed source')
        indexed[name] = (mode, blob)
    committed = {}
    for record in git(root, 'ls-tree', '-r', '-z', '--full-tree', head).split('\0'):
        if not record:
            continue
        metadata, name = record.split('\t', 1)
        mode, kind, blob = metadata.split()
        if kind == 'blob' and mode in {'100644', '100755'}:
            committed[name] = (mode, blob)
    for path in paths:
        require(path in committed and indexed.get(path) == committed[path],
                'Producer capability: exact committed documentation source required; '
                'missing source history cannot use build-time fallback for publication')


def revision_history(configuration,root,*,publication=False,catalogue=None):
    plugin=configuration.plugins.get('git-revision-date-localized')
    if plugin is None:return None
    import importlib.metadata as metadata
    require(metadata.version('mkdocs-git-revision-date-localized-plugin') in {'1.5.1','1.5.3','1.6.0'},
            'Producer capability: reviewed revision date plugin1.5.1,1.5.3 or1.6.0 required')
    require(type(plugin).__module__.startswith('mkdocs_git_revision_date_localized_plugin.'),
            'Producer capability: actual revision plugin source required')
    module=__import__(type(plugin).__module__,fromlist=[''])
    file=Path(module.__file__).resolve();distribution=metadata.distribution('mkdocs-git-revision-date-localized-plugin')
    require(file.is_relative_to(Path(distribution.locate_file('')).resolve()),'Producer capability: revision plugin import shadowed')
    head=git(root,'rev-parse','HEAD');history=git(root,'log','--format=%H:%ct:%P','HEAD','--',str(Path(configuration.docs_dir).relative_to(root)))
    require(bool(history),'Producer capability: actual source revision history required')
    if publication:
        from mkdocs.structure.files import get_files
        documents = get_files(configuration)
        if catalogue is not None:
            require(git(root,'rev-parse','--is-shallow-repository') == 'false',
                    'Producer capability: catalogue publication needs complete native original history')
            documents = catalogue.sources.files(documents, configuration)
        paths = [Path(document.abs_src_path).relative_to(root).as_posix()
                 for document in documents.documentation_pages()]
        committed_document_history(root, paths, head)
    return {'head':head,'history_sha256':digest(history.encode()),'plugin_source_sha256':digest(file.read_bytes()),
            'source_config':dict(plugin.config),'fallback_preserved':True,'publication_history_verified':publication}


def callback_records(configuration,root,catalogue=None):
    """Bind registered event callbacks, including the registry actually executed."""
    installed={Path(sysconfig.get_path(name)).resolve() for name in ('purelib','platlib')}
    hook_functions={value for module in configuration.hooks.values() for name,value in vars(module).items() if name.startswith('on_') and inspect.isfunction(value)}
    plugins=list(configuration.plugins.values());result=[];compiled={}
    def codes(code):
        yield code
        for child in code.co_consts:
            if isinstance(child,types.CodeType):yield from codes(child)
    for event,callbacks in sorted(configuration.plugins.events.items()):
        for index,callback in enumerate(callbacks):
            function=callback.__func__ if inspect.ismethod(callback) else callback
            require(inspect.isfunction(function),'Producer capability: registered event needs source-owned Python callback')
            require((inspect.ismethod(callback) and any(callback.__self__ is plugin for plugin in plugins)) or function in hook_functions,
                    'Producer capability: foreign registered callback owner')
            path=Path(inspect.getsourcefile(function) or '').absolute()
            require(path.is_file() and not path.is_symlink(),'Producer capability: callback source must be regular')
            owned_hook=function in hook_functions
            owned_catalogue = (catalogue is not None and inspect.ismethod(callback)
                               and callback.__self__ is catalogue.plugin
                               and configuration.plugins.get('bijux/catalogue-sources') is catalogue.plugin)
            require(owned_hook and path.is_relative_to(root)
                    or owned_catalogue and path == Path(catalogue.helper.__file__).absolute()
                    or not owned_hook and not owned_catalogue and any(path.is_relative_to(directory) for directory in installed),
                    'Producer capability: callback source outside reviewed roots')
            source=path.read_bytes()
            if path not in compiled:
                compiled[path]=list(codes(compile(source,str(path),'exec',dont_inherit=True,optimize=sys.flags.optimize)))
            require(any(code==function.__code__ for code in compiled[path]),'Producer capability: registered callback executable differs from source')
            result.append({'event':event,'index':index,'owner':function.__module__,'function':function.__qualname__,
                           'source':path.relative_to(root).as_posix() if owned_hook else path.relative_to(catalogue.shared).as_posix() if owned_catalogue else next(path.relative_to(directory).as_posix() for directory in installed if path.is_relative_to(directory)),
                           'source_sha256':digest(source),'class':'reviewed-hook' if owned_hook else 'reviewed-standard-catalogue' if owned_catalogue else 'installed-profile'})
    return result

def preflight(configuration,root,*,publication=False,catalogue=None):
    declared_hooks={name for name,plugin in configuration.plugins.items() if any(plugin is hook for hook in configuration.hooks.values())}
    declared_catalogue = set()
    if catalogue is not None:
        require(configuration.plugins.get('bijux/catalogue-sources') is catalogue.plugin,
                'Producer capability: exact producer-owned catalogue plugin required')
        declared_catalogue = {'bijux/catalogue-sources'}
    require(set(configuration.plugins)<=PLUGINS|declared_hooks|declared_catalogue,'Producer capability: plugin requires a reviewed adapter')
    for name,(distribution,version,module_name) in EXTENSION_PLUGINS.items():
        plugin=configuration.plugins.get(name)
        if plugin is None:continue
        require(importlib.metadata.version(distribution)==version,
                'Producer capability: extension plugin needs exact reviewed version: '+name)
        require(type(plugin).__module__.split('.')[0]==module_name,
                'Producer capability: extension plugin source owner differs: '+name)
    social=configuration.plugins.get('material/social')
    if social is not None:
        require(social.config.get('enabled') is False,'Producer capability: active social generation requires its own reviewed producer')
    return {'hooks':hooks(configuration,root,publication=publication),'callbacks':callback_records(configuration,root,catalogue),
            'revision':revision_history(configuration,root,publication=publication,catalogue=catalogue)}


def verify_outputs(site,records):
    for record in records['hooks']:
        for name,expected in record['outputs'].items():
            require(digest(regular(site,site/name))==expected,'Producer capability: published source asset differs from reviewed projection')
