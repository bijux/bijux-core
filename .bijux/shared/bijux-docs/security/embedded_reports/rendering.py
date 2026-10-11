"""Compose explicitly committed passive readers in both source renderer outputs."""
from pathlib import Path
import copy
import importlib
import subprocess

from .contract import AdmissionError, digest, json_data, read_owned, source_inputs
from .html import report_class, validate_report
from .integration import plan_embedded_reports, verify_composition
from .planning import _descriptor_inputs


class ReaderSource:
    """In-process committed owner selection; no receipt can construct this scope."""
    def __init__(self, repository, descriptor_name, config, config_digest, resolved_digest, site_url):
        self.repository = Path(repository).resolve()
        self.descriptor_name = descriptor_name
        self.config = {"path": config, "sha256": config_digest}
        self.resolved_digest, self.site_url = resolved_digest, site_url
        command = subprocess.run(["git", "-C", str(self.repository), "rev-parse", "HEAD"], capture_output=True, text=True)
        if command.returncode:
            raise AdmissionError("reader renderer requires actual committed owner source")
        self.source_sha = command.stdout.strip()
        self.descriptor_bytes = read_owned(self.repository, descriptor_name)
        self.descriptor = self._descriptor()

    def _descriptor(self):
        selected = Path(self.descriptor_name)
        if selected.is_absolute() or '..' in selected.parts or selected.as_posix() != self.descriptor_name:
            raise AdmissionError("reader renderer requires a confined owner descriptor")
        content = read_owned(self.repository, self.descriptor_name)
        path = self.repository / self.descriptor_name
        if content != self.descriptor_bytes or len(content) > 2097152 or path.stat().st_nlink != 1:
            raise AdmissionError("reader renderer owner source changed or exceeds ownership boundary")
        source_inputs(self.repository, self.source_sha, [{"path": self.descriptor_name, "sha256": digest(content)}])
        descriptor = json_data(content)
        keys = {"schema", "site_url", "config", "resolved_config_sha256", "producer_inputs", "reports", "parents", "reader_purpose"}
        if not isinstance(descriptor, dict) or set(descriptor) != keys or descriptor["schema"] != "owned-embedded-reports.v1":
            raise AdmissionError("reader renderer requires exact supported descriptor fields")
        if descriptor['site_url'] != self.site_url or descriptor['config'] != self.config or descriptor['resolved_config_sha256'] != self.resolved_digest:
            raise AdmissionError("reader renderer descriptor differs from actual selected configuration")
        reports = descriptor['reports']
        if not isinstance(reports, list) or not 1 <= len(reports) <= 512 or descriptor['producer_inputs'] or any(not isinstance(r, dict) or report_class(r) != 'static-reader' for r in reports):
            raise AdmissionError("reader renderer supports only finite zero-executable source-owned reports")
        source_inputs(self.repository, self.source_sha, _descriptor_inputs(descriptor))
        for report in reports:
            original = read_owned(self.repository, report['source']['path'])
            validate_report(original.decode(), report, self.site_url)
        return descriptor

    def compose(self, site, receipt, policy, shared, templates, redirects):
        self._descriptor()
        # Planning is a mechanical source operation. It never converts the actual
        # renderer checkpoint or a profile into publication authority.
        beginning = {k: v for k, v in receipt.items() if k not in {'bundle_sha256', 'limitations'}}
        beginning.update(state='prepared', verification_only=True)
        plan = plan_embedded_reports(self.repository, site, self.repository / self.descriptor_name, beginning, source_sha=self.source_sha)
        owned = {item['output'] for item in self.descriptor['reports']}
        if set(plan['reader_purposes']) != owned:
            raise AdmissionError('reader renderer requires exact useful discovery for every report')
        return policy.apply(site, shared, templates, redirects, plan)

    def _verify(self, site, csp, receipt, *, identity=None, checkpoint=None, publication=False):
        self._descriptor()
        retained = csp.get('embedded')
        if not isinstance(retained, dict) or retained.get('descriptor_path') != str(self.repository / self.descriptor_name) or retained.get('source_sha') != self.source_sha:
            raise AdmissionError('reader renderer receipt cannot select a different committed owner')
        if publication:
            adapter = importlib.import_module(__package__ + '.publication')
            admitted = adapter.verify_readers(site, csp, receipt, repository=self.repository, identity=identity, checkpoint=checkpoint)
        else:
            if receipt.get('verification_only') is not True:
                raise AdmissionError('reader renderer local scope cannot claim qualified publication')
            admitted = verify_composition(site, csp, receipt)
        return admitted

    def verify(self, site, csp, receipt, **scope):
        return VerifiedReaders(self, Path(site), csp, receipt, scope)


class VerifiedReaders:
    """Typed rederived composition bound to current source, bytes and policy."""
    def __init__(self, source, site, csp, receipt, scope):
        if type(source) is not ReaderSource:
            raise AdmissionError("reader renderer requires independently prepared in-process source")
        admitted = source._verify(site, csp, receipt, **scope)
        self.source, self.site = source, site
        self.scope = dict(scope)
        self.csp, self.receipt = copy.deepcopy(csp), copy.deepcopy(receipt)
        self.capabilities = copy.deepcopy(admitted['capabilities'])
        self.reports = set(admitted['report_routes'])
        self.html = {p.relative_to(site).as_posix(): p.read_bytes() for p in site.rglob('*.html')}
        if set(admitted['reader_purposes']) != self.reports or any(self.capabilities[name].get('script_sources') != ["'none'"] or self.capabilities[name].get('script_hashes') for name in self.reports):
            raise AdmissionError('reader renderer cannot admit an executable report')

    def unchanged(self, site, csp):
        admitted = self.source._verify(site, csp, self.receipt, **self.scope)
        if self.capabilities != admitted["capabilities"] or self.reports != admitted["report_routes"]:
            raise AdmissionError("reader renderer rederived capability changed")
        if Path(site) != self.site or csp != self.csp or self.html != {p.relative_to(site).as_posix(): p.read_bytes() for p in site.rglob('*.html')}:
            raise AdmissionError('reader renderer composition changed after independent verification')
