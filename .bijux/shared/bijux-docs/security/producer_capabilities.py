"""Admit reviewed source asset callbacks and actual revision-history inputs."""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import marshal
from pathlib import Path
import subprocess
import types
import sysconfig
import sys

HOOKS = {
    '4f04c4736adc9b9ff801bb2e2214e4bb622b8858aac16a9f6ae88b49ff2f7e84':'root-icons',
    'bda022ee3efa9393f03cda2d49684ba186d67714a362f4225890b8d4b15583d5':'source-assets-and-root-icons',
}
ICONS=('favicon.ico','apple-touch-icon.png','apple-touch-icon-precomposed.png')
PLUGINS={'material/search','autorefs','redirects','git-revision-date-localized','material/social'}


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


def hooks(configuration,root,*,publication=False):
    records=[]
    for hook in configuration.hooks.values():
        require(isinstance(hook,types.ModuleType),'Producer capability: source-owned hook module required')
        path=Path(hook.__file__).absolute();source=regular(root,path);recipe=HOOKS.get(digest(source))
        require(recipe is not None,'Producer capability: hook needs a reviewed source recipe')
        if publication:
            git(root,'ls-files','--error-unmatch',path.relative_to(root).as_posix())
        require(tuple(hook.ROOT_ICON_FILENAMES)==ICONS,'Producer capability: loaded icon contract changed')
        # Recompile rather than trust a file hash attached to a replaced callback.
        expected=compile(source,str(path),'exec',dont_inherit=True)
        declared={node.name for node in ast.parse(source).body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
        functions={item.co_name:item for item in expected.co_consts if isinstance(item,types.CodeType) and item.co_name in declared}
        require(set(functions)==declared,'Producer capability: declared callback compilation differs')
        require({name for name,value in vars(hook).items() if name.startswith('on_') and callable(value)}=={name for name in declared if name.startswith('on_')},'Producer capability: undeclared hook callback')
        for name,code in functions.items():
            actual=getattr(hook,name,None)
            require(inspect.isfunction(actual) and actual.__code__==code,
                    'Producer capability: loaded callback differs from reviewed source')
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
        records.append({'source':path.relative_to(root).as_posix(),'source_sha256':digest(source),
                        'recipe':recipe,'inputs':sorted(inputs,key=lambda item:item['path']),'outputs':outputs})
    return records


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
        for document in documents.documentation_pages():
            path=Path(document.abs_src_path).relative_to(root).as_posix()
            git(root,'ls-files','--error-unmatch',path)
            require(bool(git(root,'log','-1','--format=%H','HEAD','--',path)),
                    'Producer capability: missing source history cannot use build-time fallback for publication')
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
    social=configuration.plugins.get('material/social')
    if social is not None:
        require(social.config.get('enabled') is False,'Producer capability: active social generation requires its own reviewed producer')
    return {'hooks':hooks(configuration,root,publication=publication),'callbacks':callback_records(configuration,root,catalogue),
            'revision':revision_history(configuration,root,publication=publication,catalogue=catalogue)}


def verify_outputs(site,records):
    for record in records['hooks']:
        for name,expected in record['outputs'].items():
            require(digest(regular(site,site/name))==expected,'Producer capability: published source asset differs from reviewed projection')
