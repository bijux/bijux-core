"""Select source-owned renderer profiles and reject unmanaged import surfaces."""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib.metadata as metadata
import importlib.util
import io
import marshal
import re
import struct
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


def cache_code_equal(actual, expected, *, search_limit=100000):
    """Bind executable values and non-reflexive constant reference graphs."""
    # Compilation produces the graph that the cache writer serializes. Re-read
    # that graph through the same interpreter to account for marshal interning.
    expected = marshal.loads(marshal.dumps(expected))
    steps = 0
    nonreflexive = {}
    visiting = set()

    def has_nan(value):
        # Equal reflexive constants can be interned differently by independent
        # compilation and marshal reads. NaNs and their containing objects need
        # reference bijections: collapsing them changes equality/set semantics.
        identity = id(value)
        if identity in nonreflexive:
            return nonreflexive[identity]
        if identity in visiting:
            raise ProfileError('Renderer profile: cyclic executable constant graph')
        visiting.add(identity)
        kind = type(value)
        if kind in {float, complex}:
            result = value != value
        elif kind is types.CodeType:
            result = has_nan(value.co_consts)
        elif kind in {tuple, frozenset}:
            result = any(has_nan(item) for item in value)
        elif kind is slice:
            result = any(has_nan(item) for item in (value.start, value.stop, value.step))
        else:
            scalar(value)
            result = False
        visiting.remove(identity)
        nonreflexive[identity] = result
        return result

    def scalar(value):
        kind = type(value)
        if kind is float:
            return (kind, struct.pack('>d', value))
        if kind is complex:
            return (kind, struct.pack('>dd', value.real, value.imag))
        if kind in {type(None), type(Ellipsis), bool, int, str, bytes}:
            return (kind, value)
        raise ProfileError('Renderer profile: unsupported executable constant type')

    def shape(value):
        kind = type(value)
        if kind is types.CodeType:
            return (kind, value.co_code, value.co_name, len(value.co_consts))
        if kind in {tuple, frozenset}:
            return (kind, len(value))
        if kind is slice:
            return (kind,)
        return scalar(value)

    def metadata(left, right):
        if type(left) is not type(right):
            return False
        if type(left) is tuple:
            return len(left) == len(right) and all(metadata(a, b) for a, b in zip(left, right))
        return scalar(left) == scalar(right)

    def reflexive_key(value):
        kind = type(value)
        if kind is types.CodeType:
            return (kind, tuple((name, reflexive_key(getattr(value, name)))
                                for name in dir(value)
                                if name.startswith('co_') and name != 'co_filename'
                                and not callable(getattr(value, name))))
        if kind is tuple:
            return (kind, tuple(reflexive_key(item) for item in value))
        if kind is frozenset:
            return (kind, frozenset(Counter(reflexive_key(item) for item in value).items()))
        if kind is slice:
            return (kind, reflexive_key(value.start), reflexive_key(value.stop), reflexive_key(value.step))
        return scalar(value)

    def match_pairs(pairs, unordered, forward, reverse):
        nonlocal steps
        while pairs:
            steps += 1
            if steps > search_limit:
                raise ProfileError('Renderer profile: executable constant graph comparison budget exceeded')
            left, right = pairs.pop()
            if type(left) is not type(right):
                return False
            left_id, right_id = id(left), id(right)
            if has_nan(left) != has_nan(right):
                return False
            if has_nan(left):
                if left_id in forward:
                    if forward[left_id] != right_id:
                        return False
                    continue
                if right_id in reverse:
                    return False
                forward[left_id], reverse[right_id] = right_id, left_id
            kind = type(left)
            if kind is types.CodeType:
                fields = tuple(name for name in dir(left) if name.startswith('co_') and not callable(getattr(left, name)))
                if fields != tuple(name for name in dir(right) if name.startswith('co_') and not callable(getattr(right, name))):
                    return False
                for name in fields:
                    if name == 'co_filename':
                        continue
                    if name == 'co_consts':
                        pairs.append((left.co_consts, right.co_consts))
                    elif not metadata(getattr(left, name), getattr(right, name)):
                        return False
            elif kind is tuple:
                if len(left) != len(right):
                    return False
                pairs.extend(zip(left, right))
            elif kind is slice:
                pairs.extend(((left.start, right.start), (left.stop, right.stop), (left.step, right.step)))
            elif kind is frozenset:
                if len(left) != len(right):
                    return False
                if has_nan(left):
                    unordered.append((tuple(left), tuple(right)))
                elif reflexive_key(left) != reflexive_key(right):
                    return False
            elif scalar(left) != scalar(right):
                return False
        return True

    def branches(left_items, right_items, pending, forward, reverse):
        left, rest = left_items[0], left_items[1:]
        left_shape = shape(left)
        for index, right in enumerate(right_items):
            if shape(right) == left_shape:
                yield ([(left, right)], pending + [(rest, right_items[:index] + right_items[index + 1:])],
                       forward.copy(), reverse.copy())

    # Explicit search frames preserve global alias backtracking without adding
    # a Python call frame for every member of a legitimate large constant set.
    alternatives = [iter([([(actual, expected)], [], {}, {})])]
    while alternatives:
        try:
            pairs, unordered, forward, reverse = next(alternatives[-1])
        except StopIteration:
            alternatives.pop()
            continue
        if not match_pairs(pairs, unordered, forward, reverse):
            continue
        while unordered and not unordered[-1][0]:
            unordered.pop()
        if not unordered:
            return True
        left_items, right_items = unordered.pop()
        alternatives.append(branches(left_items, right_items, unordered, forward, reverse))
    return False


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
    require(cache_code_equal(actual, expected),
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
    # Resolve each immutable distribution inventory once during this origin check.
    # A later capture creates a fresh index and retains full physical validation.
    distribution_members = {}

    def distribution_identity(owner):
        if owner not in distribution_members:
            distribution = metadata.distribution(owner)
            members = {
                Path(distribution.locate_file(item)).resolve()
                for item in distribution.files or [] if '..' not in item.parts
            }
            distribution_members[owner] = (distribution, members)
        return distribution_members[owner]

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
            members = set().union(*(distribution_identity(owner)[1] for owner in candidates))
            require(path in members,'Renderer profile: installed producer namespace is shadowed: '+name+' at '+str(path))
    for name,distribution in [('mkdocs','mkdocs'),('material','mkdocs-material'),('jinja2','Jinja2'),('yaml','PyYAML')]:
        module=__import__(name)
        file=Path(module.__file__).resolve()
        owner, members = distribution_identity(distribution)
        base=Path(owner.locate_file('')).resolve()
        require(base in installed and file.is_relative_to(base), "Renderer profile: loaded producer package is shadowed")
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
