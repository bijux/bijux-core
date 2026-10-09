"""Select source-owned renderer profiles and reject unmanaged import surfaces."""
from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import importlib.util
import io
import marshal
import re
import types
import json
import os
from pathlib import Path
import platform
import sys
import sysconfig


class ProfileError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ProfileError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def aggregate(records):
    return digest(json.dumps(records, sort_keys=True, separators=(",", ":")).encode())


def source_link_identity(path: Path, root: Path, *, stdlib=False):
    """Use the same typed source ownership for inventory and executable caches."""
    require(stdlib, "Renderer profile: installed runtime symlink forbidden: " + str(path))
    base = Path(sys.base_prefix).resolve()
    target = path.resolve()
    if target.is_relative_to(base):
        return {'base_interpreter_link': target.relative_to(base).as_posix()}
    require(path.name in {'sitecustomize.py', 'usercustomize.py'} and path.parent == root,
            'Renderer profile: external runtime link requires a typed startup adapter: ' + str(path))
    return {'external_startup_target': str(target)}


def validate_bytecode(path: Path, *, root: Path | None = None, stdlib=False):
    require('__pycache__' in path.parts and not path.is_symlink(), "Renderer profile: sourceless/unowned bytecode forbidden")
    try:
        source=Path(importlib.util.source_from_cache(str(path)))
    except ValueError as error:
        raise ProfileError('Renderer profile: unsupported bytecode cache path') from error
    require(source.is_file(), 'Renderer profile: bytecode source missing: ' + str(source) + ' for cache ' + str(path))
    if source.is_symlink():
        require(root is not None and source.is_relative_to(root),
                'Renderer profile: bytecode source link requires owned stdlib context: ' + str(source) + ' for cache ' + str(path))
        source_link_identity(source, root, stdlib=stdlib)
    payload=path.read_bytes()
    require(len(payload)>=16 and len(payload)<=32*1024*1024 and payload[:4]==importlib.util.MAGIC_NUMBER,
            'Renderer profile: bytecode format differs from actual interpreter')
    require(int.from_bytes(payload[4:8],'little') in {0,1,3},'Renderer profile: unsupported bytecode flags')
    stream=io.BytesIO(payload[16:])
    try:
        actual=marshal.load(stream)
    except (EOFError, ValueError, TypeError) as error:
        raise ProfileError("Renderer profile: malformed executable cache") from error
    require(isinstance(actual,types.CodeType) and stream.read()==b'', 'Renderer profile: bytecode payload is not one code object')
    match=re.search(r'\.opt-([12])\.pyc$',path.name)
    expected=compile(source.read_bytes(),str(source),'exec',dont_inherit=True,optimize=int(match[1]) if match else 0)
    def normalized(code):
        return code.replace(co_filename='{source}',co_consts=tuple(normalized(value) if isinstance(value,types.CodeType) else value for value in code.co_consts))
    require(normalized(actual)==normalized(expected),
            'Renderer profile: cached executable bytecode differs from owned source: '+str(path))


def physical_files(root: Path, *, stdlib=False):
    require(root.is_dir() and not root.is_symlink(), "Renderer profile: regular runtime root required")
    records=[]
    for directory, directories, names in os.walk(root, followlinks=False):
        current=Path(directory)
        directories[:]=[name for name in directories if not (stdlib and name=='site-packages')]
        for name in directories:
            require(not (current/name).is_symlink(), "Renderer profile: runtime directory symlink forbidden")
        for name in names:
            path=current/name
            if path.suffix=='.pyc':
                validate_bytecode(path, root=root, stdlib=stdlib)
                continue
            if (current.name.endswith('.dist-info') and name in {'RECORD','INSTALLER','direct_url.json','REQUESTED'}):
                continue
            require(path.is_file(), "Renderer profile: regular installed source required: "+str(path))
            record={'path':path.relative_to(root).as_posix(),'sha256':digest(path.read_bytes())}
            if path.is_symlink():
                record.update(source_link_identity(path, root, stdlib=stdlib))
            records.append(record)
    return sorted(records,key=lambda item:item['path'])


def environment_snapshot():
    roots=sorted({Path(sysconfig.get_path(name)).resolve() for name in ('purelib','platlib')})
    require(all(root.is_relative_to(Path(sys.prefix).resolve()) for root in roots), "Renderer profile: isolated environment required")
    packages=[]
    for distribution in sorted(metadata.distributions(),key=lambda item:item.metadata['Name'].lower()):
        base=Path(distribution.locate_file('')).resolve()
        require(base in roots, "Renderer profile: distribution outside owned environment")
        listed=distribution.files
        require(listed is not None, "Renderer profile: installed distribution inventory missing")
        records=[]
        for name in listed:
            if '..' in name.parts:
                require(name.parts[:4]==('..','..','..','bin') and len(name.parts)==5,
                        "Renderer profile: unknown distribution path escape")
                continue
            if name.suffix=='.pyc' or (name.parent.name.endswith('.dist-info') and name.name in {'RECORD','INSTALLER','direct_url.json','REQUESTED'}):
                continue
            path=Path(distribution.locate_file(name))
            require(not name.is_absolute() and path.is_file() and not path.is_symlink(), "Renderer profile: installed dependency source missing or escaped")
            records.append({'path':name.as_posix(),'sha256':digest(path.read_bytes())})
        records=sorted(records,key=lambda item:item['path'])
        packages.append({'name':distribution.metadata['Name'],'version':distribution.version,
                         'files_count':len(records),'files_sha256':aggregate(records),'files':records})
    physical=[]
    startup=[]
    for root in roots:
        actual=physical_files(root)
        listed={item['path'] for package in packages for item in package['files']}
        require({item['path'] for item in actual}==listed,
                "Renderer profile: unlisted installed source/data/.pth or missing distribution input")
        physical.append({'root':'site-packages','files_count':len(actual),'files_sha256':aggregate(actual)})
        for record in actual:
            if record['path'].endswith('.pth'):
                data=(root/record['path']).read_bytes()
                startup.append({'path':record['path'],'sha256':digest(data),'source':data.decode('utf-8')})
    standard_root=Path(sysconfig.get_path('stdlib')).resolve()
    stdlib=physical_files(standard_root,stdlib=True)
    for record in stdlib:
        if record['path'] in {'sitecustomize.py','usercustomize.py'}:
            path=standard_root/record['path']
            startup.append({'path':'stdlib/'+record['path'],'sha256':record['sha256'],
                            'source':path.read_text(),'resolved_target':str(path.resolve())})
    return {'platform':{'system':platform.system(),'machine':platform.machine(),'python':platform.python_version(),
                        'implementation':sys.implementation.name,'cache_tag':sys.implementation.cache_tag},
            'executable_sha256':digest(Path(sys.executable).resolve().read_bytes()),
            'stdlib':{'files_count':len(stdlib),'files_sha256':aggregate(stdlib)},
            'physical_roots':physical,'startup_inputs':sorted(startup,key=lambda item:item['path']),'packages':[{k:v for k,v in package.items() if k!='files'} for package in packages]}


def origins(root: Path, shared: Path, *, publication: bool, external_startup_sources=()):
    installed={Path(sysconfig.get_path(name)).resolve() for name in ('purelib','platlib')}
    stdlib=Path(sysconfig.get_path('stdlib')).resolve()
    source_roots={root.resolve(),shared.resolve()}
    allowed=installed|source_roots|{stdlib}
    external_paths={Path(value).resolve() for value in external_startup_sources}
    for entry in sys.path:
        path=Path(entry or os.getcwd()).resolve()
        if not path.exists() and path.suffix=='.zip' and path.parent==stdlib.parent:
            continue
        require(any(path.is_relative_to(value) for value in allowed) or not publication,
                "Renderer profile: unsupported producer import root")
    for name,module in list(sys.modules.items()):
        file=getattr(module,'__file__',None)
        if not file or (not publication and name=='__main__'):
            continue
        path=Path(file).resolve()
        require(any(path.is_relative_to(value) for value in allowed) or not publication
                or (name=='sitecustomize' and path in external_paths),
                "Renderer profile: loaded module outside reviewed runtime/source roots")
    owners=metadata.packages_distributions()
    for name,module in list(sys.modules.items()):
        file=getattr(module,'__file__',None)
        if not file:continue
        path=Path(file).resolve();top=name.split('.')[0]
        # Requests source exposes these historical namespace aliases to the same
        # admitted dependency objects. Other alias/shadow names stay closed.
        if name.startswith('requests.packages.'):
            canonical=name.removeprefix('requests.packages.')
            actual_name=getattr(module,'__name__',None)
            expected_names={canonical}
            if canonical.split('.')[0]=='chardet':expected_names.add(canonical.replace('chardet','charset_normalizer',1))
            require(canonical.split('.')[0] in {'urllib3','idna','chardet','charset_normalizer'} and actual_name in expected_names,
                    'Renderer profile: unknown requests dependency alias')
            top=actual_name.split('.')[0]
        if top in sys.stdlib_module_names:
            require(path.is_relative_to(stdlib),'Renderer profile: standard library import is shadowed')
        candidates=owners.get(top,[])
        if candidates:
            members={Path(metadata.distribution(owner).locate_file(item)).resolve()
                     for owner in candidates for item in metadata.distribution(owner).files or [] if '..' not in item.parts}
            require(path in members,'Renderer profile: installed producer namespace is shadowed: '+name+' at '+str(path))
    for name,distribution in [('mkdocs','mkdocs'),('material','mkdocs-material'),('jinja2','Jinja2'),('yaml','PyYAML')]:
        module=__import__(name)
        file=Path(module.__file__).resolve()
        base=Path(metadata.distribution(distribution).locate_file('')).resolve()
        require(base in installed and file.is_relative_to(base), "Renderer profile: loaded producer package is shadowed")
        members={Path(metadata.distribution(distribution).locate_file(item)).resolve()
                 for item in metadata.distribution(distribution).files or [] if '..' not in item.parts}
        require(file in members, "Renderer profile: loaded producer source absent installed inventory")


DISTRO_STARTUP_SHA256 = '43d81125d92376b1a69d53a71126a041cc9a18d8080e92dea0a2ae23be138b1e'


def external_startup_review(profile, actual):
    """Allow only the reviewed conditional distro hook with no active importer."""
    records=[item for item in actual.get('startup_inputs',[]) if item['path'].startswith('stdlib/')
             and not Path(item['resolved_target']).is_relative_to(Path(sys.base_prefix).resolve())]
    review=profile.get('external_startup_review',{})
    require(set(review)=={item['path'] for item in records},
            'Renderer profile: external startup sources require exact source-owned review')
    for item in records:
        admitted=review[item['path']]
        require(item['path']=='stdlib/sitecustomize.py' and item['sha256']==DISTRO_STARTUP_SHA256
                and admitted.get('sha256')==item['sha256'] and admitted.get('resolved_target')==item['resolved_target']
                and admitted.get('recipe')=='distro-apport-import-unavailable'
                and len(admitted.get('purpose','').strip())>=10,
                'Renderer profile: external startup recipe differs from reviewed exact source')
        module=sys.modules.get('sitecustomize')
        require(module is not None and Path(getattr(module,'__file__','')).resolve()==Path(item['resolved_target'])
                and getattr(module,'apport_python_hook',None) is None
                and 'apport_python_hook' not in sys.modules and sys.excepthook is sys.__excepthook__
                and type(sys.excepthook) is types.BuiltinFunctionType
                and sys.excepthook.__self__ is sys and sys.excepthook.__name__=='excepthook',
                'Renderer profile: external startup imports/callbacks are not qualified by source-only review')
    return tuple(item['resolved_target'] for item in records)


def select(shared: Path, root: Path, *, publication=False):
    path=shared/'security/renderer-producer-admission.json'
    require(path.is_file() and not path.is_symlink(), "Renderer profile: source-owned admission table required")
    captured=path.read_bytes();table=json.loads(captured)
    require(table.get('schema')==2 and isinstance(table.get('profiles'),list) and len(table['profiles'])<=32, "Renderer profile: bounded reviewed profile table required")
    require(all(isinstance(profile.get('id'),str) and profile['id'] for profile in table['profiles']) and len({profile['id'] for profile in table['profiles']})==len(table['profiles']), 'Renderer profile: unique profile identities required')
    actual=environment_snapshot()
    matches=[profile for profile in table['profiles'] if profile.get('environment')==actual]
    require(len(matches)==1, "Renderer profile: unsupported environment; retain actual hosted fingerprints and review a source-owned profile")
    profile=matches[0]
    reviewed_startup=external_startup_review(profile,actual)
    require(profile.get('usage') in {'verification-only','publication'}, "Renderer profile: explicit usage required")
    require(not publication or profile['usage']=='publication', "Renderer profile: observed local or pending Linux profile is not approved for publication")
    if publication:
        review=profile.get('startup_review',{})
        require(set(review)=={item['path'] for item in actual['startup_inputs']}, 'Renderer profile: every startup path needs source-owned review')
        require(all(review[item['path']].get('sha256')==item['sha256'] and len(review[item['path']].get('purpose','').strip())>=10 for item in actual['startup_inputs']), 'Renderer profile: startup behavior differs from reviewed exact source')
    origins(root,shared,publication=publication,external_startup_sources=reviewed_startup)
    require(captured==path.read_bytes(), "Renderer profile: admission source changed during selection")
    return {'profile_id':profile['id'],'usage':profile['usage'],'environment':actual,'table_sha256':digest(captured)}


def unchanged(shared: Path, root: Path, selected: dict, *, publication=False):
    require(select(shared,root,publication=publication)==selected, "Renderer profile: runtime/profile changed after reconstruction")
