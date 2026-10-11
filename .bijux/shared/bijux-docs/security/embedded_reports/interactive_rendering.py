"""Reconstruct explicitly selected interactive reports from committed owner source."""
from pathlib import Path
from collections.abc import Mapping
import copy
import re

from .contract import AdmissionError, canonical, digest, json_data, read_owned, relative, source_inputs
from .html import Document, executable_scripts, report_class, report_recipe, validate_report
from .integration import verify_composition
from .planning import _descriptor_inputs, reviewed_providers
from .rendering import ReaderSource
from .resources import registration_data


def configured_owner(configuration, *, selected=None, passive=None):
    """The committed configuration selects authority; a retained receipt cannot."""
    extra = configuration.extra
    settings = extra.get('bijux', {}) if isinstance(extra, Mapping) else {}
    owner = settings.get('interactive_report_owner') if isinstance(settings, Mapping) else None
    if owner is not None:
        if (not isinstance(owner, str) or len(owner) > 1024 or not owner.endswith('.json')
            or any(character.isspace() for character in owner)):
            raise AdmissionError('interactive report owner requires a bounded JSON source path')
        relative(owner)
        if passive is not None:
            raise AdmissionError('passive and interactive report selections cannot be mixed')
    if selected is not None and (owner is None or selected != owner):
        raise AdmissionError('interactive report selector differs from committed configuration')
    return owner


def _input(pointer):
    if (not isinstance(pointer, dict) or set(pointer) != {'path', 'sha256'}
        or not isinstance(pointer['sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', pointer['sha256']) is None):
        raise AdmissionError('interactive ownership requires exact source input identities')
    relative(pointer['path'])


def _shape(descriptor):
    """Reject ambiguous nested authority before following any source pointers."""
    _input(descriptor['config'])
    _input(descriptor['reader_purpose'])
    for pointer in descriptor['producer_inputs']:
        _input(pointer)
    for report in descriptor['reports']:
        if not isinstance(report, dict):
            raise AdmissionError('interactive renderer requires typed report objects')
        _input(report.get('source'))
        relative(report.get('output'))
        resources = report.get('resources')
        if not isinstance(resources, dict) or len(resources) > 512:
            raise AdmissionError('interactive renderer requires finite typed resources')
        total = 0
        for name, resource in resources.items():
            relative(name)
            if not isinstance(resource, dict):
                raise AdmissionError('interactive renderer requires typed resource objects')
            _input({'path': resource.get('source'), 'sha256': resource.get('sha256')})
            size = resource.get('bytes')
            if type(size) is not int or size < 0:
                raise AdmissionError('interactive resource requires its exact nonnegative byte count')
            total += size
            kind = resource.get('kind')
            fields = {'source', 'sha256', 'bytes', 'kind'}
            if kind == 'data-registration':
                fields.add('registration')
                if not isinstance(resource.get('registration'), dict):
                    raise AdmissionError('interactive data resource requires its bounded registration recipe')
            elif kind not in {'reviewed-script', 'reviewed-style', 'image'}:
                raise AdmissionError('interactive resource kind is not reviewed')
            if set(resource) != fields:
                raise AdmissionError('interactive resource has unknown authority fields')
        if total > 134217728:
            raise AdmissionError('interactive resource closure exceeds its reviewed byte budget')
        if report.get('report_class') == 'interactive':
            recipe = report.get('recipe')
            if (not isinstance(recipe, dict) or set(recipe) != {'template', 'expansions', 'slots'}
                or not isinstance(recipe['expansions'], list) or len(recipe['expansions']) > 512
                or not isinstance(recipe['slots'], dict) or not 1 <= len(recipe['slots']) <= 512):
                raise AdmissionError('interactive renderer requires a finite source recipe')
            relative(recipe['template'])
            for expansion in recipe['expansions']:
                if (not isinstance(expansion, dict) or set(expansion) != {'token', 'path'}
                    or not isinstance(expansion['token'], str) or len(expansion['token']) > 128):
                    raise AdmissionError('interactive recipe expansion requires an exact source slot')
                if expansion['path'] is not None:
                    relative(expansion['path'])
            for slot in recipe['slots'].values():
                if not isinstance(slot, dict) or slot.get('kind') not in {'json', 'number', 'literal'}:
                    raise AdmissionError('interactive recipe requires a reviewed slot grammar')
                kind = slot['kind']
                fields = {'kind'} | ({'values'} if kind == 'literal' else {'maximum'} if kind == 'number' else set())
                if set(slot) != fields:
                    raise AdmissionError('interactive recipe slot has unknown authority fields')
                if kind == 'literal' and (not isinstance(slot['values'], list) or not 1 <= len(slot['values']) <= 512
                    or any(not isinstance(v, str) or len(v) > 65536 for v in slot['values'])):
                    raise AdmissionError('interactive literal slot exceeds its finite expression budget')
                if kind == 'number' and (type(slot['maximum']) not in {int, float} or not 0 <= slot['maximum'] <= 1e15):
                    raise AdmissionError('interactive numeric slot requires a finite bounded maximum')
            if (not isinstance(report.get('providers'), dict) or len(report['providers']) > 32
                or not isinstance(report.get('reviewed_provider_origins'), list)
                or not isinstance(report.get('provider_calls'), list) or len(report['provider_calls']) > 32):
                raise AdmissionError('interactive provider closure must be finite and explicit')
            if (any(not isinstance(origin, str) or not isinstance(policy, dict) for origin, policy in report['providers'].items())
                or any(not isinstance(origin, str) for origin in report['reviewed_provider_origins'])):
                raise AdmissionError('interactive provider requires typed owner decisions')
            if any(not isinstance(call, dict) or set(call) != {'callee'} or not isinstance(call['callee'], str)
                   for call in report['provider_calls']):
                raise AdmissionError('interactive provider calls require exact named reviewed callees')
    parents = descriptor['parents']
    if not isinstance(parents, list) or len(parents) > 512:
        raise AdmissionError('interactive parent closure must be finite')
    for parent in parents:
        if not isinstance(parent, dict) or set(parent) != {'output', 'source', 'reports', 'built_html_sha256'}:
            raise AdmissionError('interactive parent requires exact source ownership')
        _input(parent['source'])
        relative(parent['output'])
        if not isinstance(parent['reports'], list) or len(parent['reports']) > 512:
            raise AdmissionError('interactive parent report closure must be finite')
        for report in parent['reports']:
            relative(report)


class InteractiveReportSource(ReaderSource):
    """Separate executable capability; passive ReaderSource remains zero-script."""
    def __init__(self, repository, descriptor_name, config, config_digest, resolved_digest, site_url):
        from mkdocs.config import load_config
        configuration = load_config(config_file=str(Path(repository) / config))
        configured_owner(configuration, selected=descriptor_name)
        super().__init__(repository, descriptor_name, config, config_digest, resolved_digest, site_url)

    def _descriptor(self):
        from mkdocs.config import load_config
        configuration = load_config(config_file=str(self.repository / self.config['path']))
        configured_owner(configuration, selected=self.descriptor_name)
        relative(self.descriptor_name)
        content = read_owned(self.repository, self.descriptor_name)
        path = self.repository / self.descriptor_name
        if content != self.descriptor_bytes or len(content) > 2097152 or path.stat().st_nlink != 1:
            raise AdmissionError('interactive report owner source changed or exceeds ownership boundary')
        source_inputs(self.repository, self.source_sha, [{'path': self.descriptor_name, 'sha256': digest(content)}])
        descriptor = json_data(content)
        fields = {'schema', 'site_url', 'config', 'resolved_config_sha256', 'producer_inputs',
                  'reports', 'parents', 'reader_purpose'}
        if not isinstance(descriptor, dict) or set(descriptor) != fields or descriptor['schema'] != 'owned-embedded-reports.v1':
            raise AdmissionError('interactive report renderer requires exact supported descriptor fields')
        if descriptor['site_url'] != self.site_url or descriptor['config'] != self.config or descriptor['resolved_config_sha256'] != self.resolved_digest:
            raise AdmissionError('interactive report descriptor differs from actual selected configuration')
        reports, producers = descriptor['reports'], descriptor['producer_inputs']
        if (not isinstance(reports, list) or not 1 <= len(reports) <= 512
            or not isinstance(producers, list) or not 1 <= len(producers) <= 512
            or not any(isinstance(r, dict) and r.get('report_class') == 'interactive' for r in reports)):
            raise AdmissionError('interactive renderer requires finite explicitly classified reports and producers')
        _shape(descriptor)
        source_inputs(self.repository, self.source_sha, _descriptor_inputs(descriptor))
        producer_paths = {item['path'] for item in producers}
        for report in reports:
            if not isinstance(report, dict) or report.get('report_class') not in {'interactive', 'static-reader'}:
                raise AdmissionError('interactive renderer requires an explicit report class')
            source = read_owned(self.repository, report['source']['path'])
            if len(source) > 524288:
                raise AdmissionError('interactive report exceeds its reviewed document budget')
            document = validate_report(source.decode(), report, self.site_url)
            for resource in report['resources'].values():
                content = read_owned(self.repository, resource['source'])
                if len(content) != resource['bytes']:
                    raise AdmissionError('interactive resource differs from its reviewed byte count')
                if resource['kind'] == 'data-registration':
                    registration_data(content, resource['registration'], self.site_url, report['output'])
            if report_class(report) == 'static-reader':
                continue
            fields = {'report_class', 'output', 'source', 'resources', 'reviewed_scripts', 'bootstrap_id',
                      'bootstrap_sha256', 'recipe', 'providers', 'reviewed_provider_origins', 'provider_calls'}
            if set(report) != fields:
                raise AdmissionError('interactive renderer requires exact executable report fields')
            recipe = report['recipe']
            if not isinstance(recipe, dict) or set(recipe) != {'template', 'expansions', 'slots'}:
                raise AdmissionError('interactive renderer requires a finite source recipe')
            recipe_paths = {recipe['template'], *[item['path'] for item in recipe['expansions'] if item.get('path')]}
            if not recipe_paths <= producer_paths:
                raise AdmissionError('interactive recipe lacks committed producer closure')
            report_recipe(self.repository, document, report, self.site_url, report['output'])
            bodies = executable_scripts(document)
            reviewed_providers(report, bodies)
            bootstrap = [s for s in document.scripts if s['attrs'].get('id') == report['bootstrap_id']]
            if (len(bootstrap) != 1 or bootstrap[0]['attrs'].get('type') != 'application/json'
                or digest(canonical(json_data(bootstrap[0]['body']))) != report['bootstrap_sha256']):
                raise AdmissionError('interactive bootstrap differs from committed ownership')
        return descriptor

    def _verify(self, site, csp, receipt, *, identity=None, checkpoint=None, publication=False):
        self._descriptor()
        retained = csp.get('embedded')
        if (not isinstance(retained, dict) or retained.get('descriptor_path') != str(self.repository / self.descriptor_name)
            or retained.get('source_sha') != self.source_sha):
            raise AdmissionError('interactive report receipt cannot select another committed owner')
        if publication:
            if identity is None or checkpoint is None:
                raise AdmissionError('interactive publication requires independent source authority')
            identity.verify_source(self.repository, checkpoint)
            if checkpoint.get('config') != self.config or checkpoint['repository_source']['sha'] != self.source_sha:
                raise AdmissionError('interactive publication selects another source configuration')
        elif receipt.get('verification_only') is not True:
            raise AdmissionError('interactive local scope cannot claim qualified publication')
        return verify_composition(Path(site), csp, receipt, publication=publication,
                                  identity=identity, checkpoint=checkpoint, repository=self.repository)

    def verify(self, site, csp, receipt, **scope):
        return VerifiedInteractiveReports(self, Path(site), csp, receipt, scope)


class VerifiedInteractiveReports:
    """Exact in-process rederivation, never constructed from a serialized receipt."""
    def __init__(self, source, site, csp, receipt, scope):
        if type(source) is not InteractiveReportSource:
            raise AdmissionError('interactive renderer requires independently prepared in-process source')
        admitted = source._verify(site, csp, receipt, **scope)
        self.source, self.site, self.scope = source, site, dict(scope)
        self.csp, self.receipt = copy.deepcopy(csp), copy.deepcopy(receipt)
        self.capabilities = copy.deepcopy(admitted['capabilities'])
        self.reports = set(admitted['report_routes'])
        descriptor = source._descriptor()
        self.classes = {r['output']: report_class(r) for r in descriptor['reports']}
        self.bodies = {r['output']: [s['body'] for s in executable_scripts(Document(
            read_owned(source.repository, r['source']['path']).decode()))] for r in descriptor['reports']}
        self.html = {p.relative_to(site).as_posix(): p.read_bytes() for p in site.rglob('*.html')}
        if set(admitted['reader_purposes']) != self.reports or set(self.classes) != self.reports:
            raise AdmissionError('interactive renderer requires exact useful discovery for every report')

    def unchanged(self, site, csp):
        admitted = self.source._verify(site, csp, self.receipt, **self.scope)
        descriptor = self.source._descriptor()
        classes = {r['output']: report_class(r) for r in descriptor['reports']}
        bodies = {r['output']: [s['body'] for s in executable_scripts(Document(
            read_owned(self.source.repository, r['source']['path']).decode()))] for r in descriptor['reports']}
        if self.classes != classes or self.bodies != bodies:
            raise AdmissionError('interactive renderer class or executable source changed after verification')
        if self.capabilities != admitted['capabilities'] or self.reports != admitted['report_routes']:
            raise AdmissionError('interactive renderer rederived capability changed')
        if Path(site) != self.site or csp != self.csp or self.html != {p.relative_to(site).as_posix(): p.read_bytes() for p in site.rglob('*.html')}:
            raise AdmissionError('interactive composition changed after independent verification')


def verify_publication(site, csp, completed_build, *, repository, identity, checkpoint):
    """Independent publisher derives the selector from the actual committed config."""
    identity.verify_source(repository, checkpoint)
    from mkdocs.config import load_config
    config = checkpoint['config']
    configuration = load_config(config_file=str(Path(repository) / config['path']), site_dir=str(site))
    owner = configured_owner(configuration)
    if owner is None:
        raise AdmissionError('interactive publication requires an actual source configuration selector')
    source = InteractiveReportSource(repository, owner, config['path'], config['sha256'],
                                     identity.configuration_identity(configuration, Path(repository)), configuration.site_url)
    return source._verify(site, csp, completed_build, identity=identity, checkpoint=checkpoint, publication=True)
