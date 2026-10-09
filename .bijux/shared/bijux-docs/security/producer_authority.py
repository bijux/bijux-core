"""Reproduce executable and search outputs from source, never receipt hash authority."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
from types import ModuleType
from urllib.parse import urljoin, urlsplit, unquote


class ProducerError(ValueError):
    pass


def require(value, message):
    if not value:
        raise ProducerError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def module(path):
    require(path.is_file() and not path.is_symlink(), 'Producer: reviewed module missing or symlinked')
    captured = path.read_bytes()
    result = ModuleType('bijux_captured_' + path.stem)
    result.__file__ = str(path)
    exec(compile(captured, str(path), 'exec'), result.__dict__)
    require(path.read_bytes() == captured, 'Producer: source changed during module capture')
    return result


def repository_files(root):
    """Bind physical publication inputs to the complete current committed Git tree.

    Git status can hide local bytes through index flags. Capture verifies every
    tracked blob and mode independently, without spawning Git for each file.
    Actual renderer inputs are additionally checked by build_identity.source_inputs.
    """
    def git(*args):
        command = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
        require(command.returncode == 0, 'Producer: repository source operation failed')
        return command.stdout

    require(Path(git('rev-parse', '--show-toplevel').strip()).resolve() == root.resolve(),
            'Producer: exact repository root required')
    require(not git('status', '--porcelain', '--untracked-files=all').strip(),
            'Producer: tracked or untracked publication source is dirty')
    head = git('rev-parse', 'HEAD').strip()
    object_format = git('rev-parse', '--show-object-format').strip()
    require(object_format in {'sha1', 'sha256'}, 'Producer: supported Git object format required')
    committed = {}
    for record in git('ls-tree', '-rz', '--full-tree', head).split('\0'):
        if not record:
            continue
        metadata, name = record.split('\t', 1)
        mode, kind, blob = metadata.split()
        require(mode in {'100644', '100755'} and kind == 'blob',
                'Producer: symlink tracked source or nonregular committed source forbidden')
        require(name not in committed, 'Producer: duplicate committed source path')
        committed[name] = (mode, blob)

    indexed = {}
    for record in git('ls-files', '--stage', '-z').split('\0'):
        if not record:
            continue
        metadata, name = record.split('\t', 1)
        mode, blob, stage = metadata.split()
        require(stage == '0' and name not in indexed, 'Producer: unmerged or duplicate indexed source')
        indexed[name] = (mode, blob)
    require(bool(committed) and indexed == committed,
            'Producer: indexed source paths, modes or blobs differ from committed source')

    result = {}
    for name, (mode, blob) in sorted(committed.items()):
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts,
                'Producer: confined tracked source required')
        path = root
        for part in relative.parts:
            path = path / part
            require(not path.is_symlink(), 'Producer: symlink tracked source forbidden')
        require(path.is_file(), 'Producer: regular tracked source required')
        captured = path.read_bytes()
        header = ('blob ' + str(len(captured)) + '\0').encode()
        actual_blob = hashlib.new(object_format, header + captured).hexdigest()
        actual_mode = '100755' if path.stat().st_mode & 0o100 else '100644'
        require(actual_blob == blob and actual_mode == mode,
                'Producer: physical tracked source blob or mode differs from committed source: ' + name)
        result[name] = captured
    require(git('rev-parse', 'HEAD').strip() == head,
            'Producer: committed source changed during capture')
    require(not git('status', '--porcelain', '--untracked-files=all').strip(),
            'Producer: tracked or untracked publication source changed during capture')
    return result


def files(root, *, source=False, publication_source=False):
    require(root.is_dir() and not root.is_symlink(), 'Producer: regular tree required')
    if publication_source:
        require(source, 'Producer: publication source selection requires source capture')
        return repository_files(root)
    result={}
    for directory, directories, names in os.walk(root, followlinks=False):
        current=Path(directory)
        if source:
            # Prune generated trees before traversal, rather than walking every
            # old bundle/browser/toolchain just to discard its files afterward.
            directories[:]=[name for name in directories if name!='__pycache__'
                           and not (current==root and name in {'.git','artifacts'})]
        for name in directories:
            require(not (current/name).is_symlink(), 'Producer: symlink input/output forbidden')
        for name in names:
            path=current/name
            if source and (path.suffix=='.pyc' or (current==root and name=='.git')):
                continue
            require(not path.is_symlink() and path.is_file(), 'Producer: symlink or nonregular input/output forbidden')
            result[path.relative_to(root).as_posix()]=path.read_bytes()
    return dict(sorted(result.items()))


def fingerprints(values):
    return [{'path': name, 'sha256': digest(data)} for name, data in sorted(values.items())]


def profiles(shared):
    return module(shared/'security/renderer_profiles.py')


def dependencies(shared, root, *, publication=False):
    return profiles(shared).select(shared,root,publication=publication)


def require_committed_hook_inputs(capabilities, inputs, *, publication):
    """Bind publication callback source and assets to verified committed bytes."""
    if not publication:
        return

    def bind(path, expected):
        require(isinstance(path, str) and path in inputs,
                'Producer: publication hook input is not committed source: ' + str(path))
        require(expected == digest(inputs[path]),
                'Producer: publication hook input digest differs from committed source: ' + path)

    for hook in capabilities['hooks']:
        bind(hook['source'], hook['source_sha256'])
        for item in hook['inputs']:
            bind(item['path'], item['sha256'])


class PreparedProducer:
    """In-process reconstruction result; a deserialized receipt is never this authority."""
    def __init__(self, root, config, shared, templates, output, inputs, shared_inputs, reference, native, deps, config_sha, capabilities, redirect_hashes, publication_scope):
        self.root, self.config, self.shared, self.templates, self.output = root, config, shared, templates, output
        self.inputs, self.shared_inputs, self.reference = inputs, shared_inputs, reference
        self.native, self.deps, self.config_sha = native, deps, config_sha
        self.capabilities, self.redirect_hashes, self.publication_scope = capabilities, redirect_hashes, publication_scope
        self.source_recipe, self.derivation = None, None

    def unchanged(self):
        require(self.inputs == files(self.root, source=True, publication_source=self.publication_scope or bool(self.source_recipe)), 'Producer: owner source/config changed after reconstruction')
        require(self.shared_inputs == files(self.shared, source=True), 'Producer: standard authority changed after reconstruction')
        require(self.reference == files(self.output), 'Producer: independent reference changed after reconstruction')
        profiles(self.shared).unchanged(self.shared,self.root,self.deps,publication=self.publication_scope)
        from mkdocs.config import load_config
        catalogue = None
        if self.source_recipe:
            catalogue = module(self.shared/'security/catalogue_recipe.py').derive(
                self.root, self.shared, self.source_recipe, inputs=self.inputs, expected=self.derivation)
            configuration = catalogue.configuration(self.selected_site)
        else:
            configuration=load_config(config_file=str(self.root/self.config),site_dir=str(self.selected_site))
        actual=module(self.shared/'security/producer_capabilities.py').preflight(
            configuration,self.root,publication=self.publication_scope,catalogue=catalogue)
        require_committed_hook_inputs(actual, self.inputs, publication=self.publication_scope or catalogue is not None)
        require(actual==self.capabilities,'Producer: callback/source/history changed after reconstruction')


def render(configuration, *, catalogue=False):
    """Use native public lifecycle for source-backed catalogue event ownership."""
    from mkdocs.commands.build import build
    if not catalogue:
        return build(configuration)
    configuration.plugins.on_startup(command='build', dirty=False)
    try:
        return build(configuration)
    finally:
        configuration.plugins.on_shutdown()


def prepare(root: Path, config_name: str, shared: Path, templates: Path, output: Path, site_dir: Path,
            *, publication_scope=False, source_recipe=None, reader_owner=None):
    """Run only under the trusted renderer, with owner-selected config and frozen source.

    Production callers must independently verify the clean source checkpoint before
    selecting this config, and again after verification. This function also supports
    explicitly verification-only source fixtures; it does not create accepted source.
    """
    require(not Path(config_name).is_absolute() and '..' not in Path(config_name).parts, 'Producer: owner config path required')
    require(site_dir.is_relative_to(root/'artifacts') and output != site_dir, 'Producer: separate selected and independent artifact directories required')
    boundary=module(shared/'security/publication.py')
    require(boundary.site_directory(root,site_dir.relative_to(root).as_posix())==site_dir,'Producer: selected artifact must be confined')
    require(boundary.site_directory(root,output.relative_to(root).as_posix())==output and not output.exists(), 'Producer: fresh independent root artifacts output required')
    require(not output.is_relative_to(site_dir) and not site_dir.is_relative_to(output),'Producer: selected/reference artifacts overlap')
    inputs, shared_inputs = files(root, source=True, publication_source=publication_scope or bool(source_recipe)), files(shared, source=True)
    if not source_recipe:
        require(config_name in inputs, 'Producer: config absent from owner source')
    deps = dependencies(shared,root,publication=publication_scope)
    require(not (source_recipe and reader_owner is not None), "Producer: passive readers require a tracked MkDocs config; catalogue recipe composition remains separate")
    catalogue = None
    if source_recipe:
        catalogue = module(shared/'security/catalogue_recipe.py').derive(root, shared, source_recipe, inputs=inputs)
        require(config_name == catalogue.record['configuration']['path'], 'Producer: exact reconstructed configuration selection required')
    compiler = module(shared/'tooling/material/build_runtime.py')
    asset, runtime, provenance, template = compiler.compile_runtime(templates, importlib.metadata.version('mkdocs-material'))
    require(shared_inputs.get(asset) == runtime, 'Producer: compiled runtime differs from owned compiler/adapters')
    require(shared_inputs.get('partials/main.html') == template, 'Producer: owned native head/runtime template differs')
    require(json.loads(shared_inputs['tooling/material/runtime-provenance.json']) == provenance, 'Producer: runtime provenance differs from reconstruction')
    from mkdocs.config import load_config
    from mkdocs.commands.build import build
    configuration = (catalogue.configuration(site_dir) if catalogue else
                     load_config(config_file=str(root/config_name), site_dir=str(site_dir)))
    identity = module(shared/'security/build_identity.py')
    config_sha = identity.configuration_identity(configuration, root)
    require(Path(configuration.docs_dir).is_relative_to(root), 'Producer: docs source outside owner root')
    capabilities=module(shared/'security/producer_capabilities.py')
    capability_inputs=capabilities.preflight(configuration,root,publication=publication_scope,catalogue=catalogue)
    require_committed_hook_inputs(capability_inputs, inputs, publication=publication_scope or catalogue is not None)
    reader_source = None
    reader_receipt = None
    if reader_owner is not None:
        csp = module(shared/'security/csp.py')
        embedded = csp.embedded_module()
        adapter = importlib.import_module(embedded.__package__ + '.rendering')
        reader_source = adapter.ReaderSource(root, reader_owner, config_name, digest(inputs[config_name]), config_sha, configuration.site_url)
        reader_receipt = {'schema': 1, 'scope': 'source-projection-compatibility', 'state': 'prepared',
                          'verification_only': True, 'site_url': configuration.site_url,
                          'config': {'path': config_name, 'sha256': digest(inputs[config_name])},
                          'resolved_config_sha256': config_sha, 'renderer': identity.renderer(configuration),
                          'site_dir': output.relative_to(root).as_posix(),
                          'selected_site_dir': site_dir.relative_to(root).as_posix()}
    configuration.site_dir = str(output)
    render(configuration, catalogue=catalogue is not None)
    capabilities.verify_outputs(output,capability_inputs)
    redirects=module(shared/'security/redirects.py')
    plan=redirects.normalize_redirects(configuration,output,configuration.site_url,write=False,source_root=root if catalogue else None)
    csp=module(shared/'security/csp.py')
    if reader_source is None:
        csp.apply(output,shared,templates,plan)
    else:
        reference_csp = reader_source.compose(output, reader_receipt, csp, shared, templates, plan)
        completed_reference = reader_receipt | {'state': 'complete', 'bundle_sha256': boundary.public_bundle_identity(output)[1]}
        reader_source.verify(output, reference_csp, completed_reference)
    redirect_hashes={item['path']:item['csp_hash'] for item in plan['records']}
    reference = files(output)
    require(reference.get(asset) == runtime, 'Producer: rendered native runtime differs')
    worker = provenance['upstream_worker']
    require(reference.get(worker) == (templates/worker).read_bytes(), 'Producer: rendered worker differs from admitted native bytes')
    index = reference.get('search/search_index.json')
    require(index is not None, 'Producer: native index output missing')
    parsed = json.loads(index)
    require(isinstance(parsed.get('docs'), list), 'Producer: actual native index shape differs')
    prepared = PreparedProducer(root, config_name, shared, templates, output, inputs, shared_inputs, reference,
                                {'asset': asset, 'sha256': digest(runtime), 'worker': worker,
                                 'worker_sha256': digest(reference[worker]), 'index_sha256': digest(index),
                                 'index_bytes': len(index), 'index_documents': len(parsed['docs'])}, deps, config_sha, capability_inputs, redirect_hashes, publication_scope)
    prepared.reader_source=reader_source
    prepared.selected_site=site_dir
    prepared.source_recipe=source_recipe
    prepared.derivation=catalogue.record if catalogue else None
    prepared.unchanged()
    return prepared


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.external, self.configs, self.current, self.data = [], [], None, []
    def handle_starttag(self, tag, attrs):
        if tag != 'script': return
        values = dict(attrs)
        require(len(values) == len(attrs), 'Producer: duplicate script attribute')
        if 'src' in values:
            require(bool(values['src']), 'Producer: empty src changes script interpretation')
            require(values.get('type', '').lower() in {'', 'text/javascript', 'application/javascript'}, 'Producer: external interpretation needs reviewed adapter')
            require(set(values) <= {'src','type','defer','async','integrity','crossorigin'}, 'Producer: unreviewed external script attribute')
            self.external.append(values['src'])
        if values.get('id') == '__config':
            require(values.get('type') == 'application/json', 'Producer: native config must stay inert JSON')
            self.current, self.data = True, []
    def handle_data(self, data):
        if self.current: self.data.append(data)
    def handle_endtag(self, tag):
        if tag == 'script' and self.current:
            self.configs.append(json.loads(''.join(self.data)))
            self.current = None


def local_resource(value, page_url, site_url):
    require(isinstance(value, str) and value and '\\' not in value and not re.search('%(?:2f|5c|2e)', value, re.I), 'Producer: ambiguous executable URL')
    url = urlsplit(urljoin(page_url, value));base=urlsplit(site_url)
    require((url.scheme,url.netloc)==(base.scheme,base.netloc) and not url.query and not url.fragment, 'Producer: executable URL outside production source origin')
    require(url.path.startswith(base.path), 'Producer: executable URL outside configured mount')
    path=unquote(url.path[len(base.path):])
    require(path and '..' not in path.split('/') and not path.startswith('/'), 'Producer: executable path escapes mount')
    return path


def native_resources(native: dict, page_url: str, site_url: str) -> tuple[str, str]:
    require(isinstance(native.get('base'), str), 'Producer: native base must be a URL string')
    # Material's worker is page-relative; the index belongs to the native base.
    # Applying the base to both ascends twice on deep product routes.
    base = urljoin(page_url, native['base'] + '/')
    worker = local_resource(native.get('search'), page_url, site_url)
    index = local_resource('search/search_index.json', base, site_url)
    return worker, index


def verify(site: Path, prepared: PreparedProducer, renderer: dict, csp_report: dict, site_url: str, *, completed_build=None, checkpoint=None):
    require(type(prepared) is PreparedProducer, 'Producer: reconstruct authority in trusted renderer; serialized inventory is insufficient')
    prepared.unchanged()
    originals = files(site)
    # Bind every served executable, including dynamically loaded worker/stems/diagrams,
    # rather than only script tags observed on a selected initial page.
    executable = lambda values: {n:b for n,b in values.items() if Path(n).suffix.lower() in {'.js','.mjs','.cjs','.wasm'}}
    expected, actual = executable(prepared.reference), executable(originals)
    require(actual == expected, 'Producer: served executable set/bytes differs from independent source build')
    require(originals.get('search/search_index.json') == prepared.reference['search/search_index.json'], 'Producer: search index differs from independent native producer')
    inline = module(prepared.shared/'security/script_authority.py')
    capabilities=module(prepared.shared/'security/producer_capabilities.py')
    capabilities.verify_outputs(site,prepared.capabilities)
    boundary=module(prepared.shared/'security/publication.py')
    hashes=boundary.qualified_redirects(prepared.shared,{'renderer':renderer,'resolved_config_sha256':prepared.config_sha},csp_report,site,site_url)
    require(hashes==prepared.redirect_hashes,'Producer: declared redirects differ from independent source reconstruction')
    verified_readers = None
    reader_source = getattr(prepared, 'reader_source', None)
    require(bool(reader_source) == bool(csp_report.get('embedded')), 'Producer: reader receipt requires an explicit actual source-owned renderer selection')
    if reader_source is not None:
        require(isinstance(completed_build, dict) and completed_build.get('renderer') == renderer, 'Producer: readers require the actual completed renderer receipt')
        identity = module(prepared.shared/'security/build_identity.py')
        verified_readers = reader_source.verify(site, csp_report, completed_build, identity=identity, checkpoint=checkpoint, publication=prepared.publication_scope)
    inline_report = inline.verify_ordinary(site, prepared.shared, renderer, csp_report, hashes, verified_readers=verified_readers)
    require(set(originals)==set(prepared.reference),'Producer: complete public resource set differs from independent source build')
    for name,value in originals.items():
        expected_value=prepared.reference[name]
        if name=='sitemap.xml.gz':
            # MkDocs gzip stamps only header mtime; all other gzip bytes remain exact.
            require(value[:4]+value[8:]==expected_value[:4]+expected_value[8:],'Producer: sitemap gzip content differs')
        else:
            require(value==expected_value,'Producer: public resource bytes differ from independent source build: '+name)
    pages = []
    html_names = {n for n in originals if n.endswith('.html')}
    require(html_names == {n for n in prepared.reference if n.endswith('.html')}, 'Producer: HTML route set differs from owner build')
    for name in sorted(html_names):
        if name in hashes:
            pages.append({'path':name,'class':'declared-redirect','script_hash':hashes[name]})
            continue
        if verified_readers is not None and name in verified_readers.reports:
            pages.append({'path': name, 'class': 'source-owned-static-reader', 'executables': [], 'search_route': csp_report['embedded']['reader_purposes'][name]['search_route']})
            continue
        actual_page, source_page = References(), References()
        actual_page.feed(originals[name].decode());source_page.feed(prepared.reference[name].decode())
        require(actual_page.external == source_page.external and actual_page.configs == source_page.configs,
                'Producer: native config/executable references differ from actual owner renderer')
        require(len(actual_page.configs) == 1, 'Producer: single actual native config required')
        page_url = urljoin(site_url, name)
        paths = [local_resource(value,page_url,site_url) for value in actual_page.external]
        require(all(p in expected for p in paths), 'Producer: script reference absent from independent source output')
        native = actual_page.configs[0]
        worker, index = native_resources(native, page_url, site_url)
        require(worker == prepared.native['worker'], 'Producer: native worker URL differs from reviewed worker')
        require(index == 'search/search_index.json', 'Producer: native search index URL escapes root/mount')
        pages.append({'path':name,'executables':paths,'worker':worker,'index':index})
    prepared.unchanged()
    require(originals == files(site), 'Producer: output changed during authority verification')
    return {'schema':1,'scope':'independent-source-renderer-public-resources-and-typed-capabilities',
            'verification_only':True,'native':prepared.native,'pages':pages,'inline':inline_report,
            'served_executables':fingerprints(expected),'owner_inputs':fingerprints(prepared.inputs),
            'standard_inputs':fingerprints(prepared.shared_inputs),'dependency_admission_sha256':digest(prepared.shared_inputs['security/renderer-producer-admission.json']),
            'resolved_config_sha256':prepared.config_sha,'capabilities':prepared.capabilities,'renderer_profile':prepared.deps,
            'limits':['Accepted source checkpoint, owner-selected config and trusted DOCS_PYTHON invocation remain mandatory at publication.',
                      'Reviewed native search, autorefs, redirects, revision dates and source asset/icon callbacks; other producer classes require typed adapters.',
                      'No browser/live/header/privacy/security sandbox qualification is asserted.']}


def verify_publication(root: Path, site: Path, shared: Path, build_receipt: dict, csp_receipt: dict, checkpoint: dict):
    """Called from qualified_manifest under the owned DOCS_PYTHON environment."""
    import tempfile
    identity = module(shared/'security/build_identity.py')
    identity.verify_source(root, checkpoint)
    require(build_receipt.get('config') == checkpoint.get('config'), 'Producer: build receipt cannot select owner config')
    require(checkpoint.get('config') is not None, 'Producer: owner config source checkpoint required')
    require(build_receipt.get('derivation') == checkpoint.get('derivation'), 'Producer: source/build derivation differs')
    from mkdocs.config import load_config
    import material
    record = checkpoint.get('derivation')
    source_recipe = record.get('recipe') if record else None
    catalogue = module(shared/'security/catalogue_recipe.py').derive(root, shared, source_recipe, expected=record) if record else None
    configuration = (catalogue.configuration(site) if catalogue else
                     load_config(config_file=str(root/checkpoint['config']['path']), site_dir=str(site)))
    require(configuration.site_url == checkpoint['site_url'], 'Producer: actual config site URL differs')
    require(identity.renderer(configuration,catalogue) == build_receipt['renderer'], 'Producer: publication must use actual trusted renderer environment, never receipt executable')
    parent = root/'artifacts/website-security/producer-reconstruction';parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as scratch:
        prepared = prepare(root, record['configuration']['path'] if record else checkpoint['config']['path'], shared, Path(material.__file__).parent/'templates', Path(scratch)/'site', site, publication_scope=True, source_recipe=source_recipe,
                           reader_owner=Path(csp_receipt["embedded"]["descriptor_path"]).relative_to(root).as_posix() if csp_receipt.get("embedded") else None)
        require(prepared.config_sha == build_receipt['resolved_config_sha256'], 'Producer: resolved config differs from independent actual renderer')
        report = verify(site, prepared, build_receipt['renderer'], csp_receipt, checkpoint['site_url'], completed_build=build_receipt, checkpoint=checkpoint)
        identity.verify_source(root, checkpoint)
        return report | {'verification_only':False}
