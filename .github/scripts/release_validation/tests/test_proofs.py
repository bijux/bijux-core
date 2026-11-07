"""Reject incomplete, stale, modified or over-budget release evidence."""
from pathlib import Path
import copy
import io
import json
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / '.github/scripts'))
from verification.artifacts import file_digest, pack, snapshot, unpack, verify_receipts, verify_sources, source_files
from release_validation import execution
from release_validation.execution import commands
from unittest.mock import patch
from release_validation.planning import PUBLIC_DAG, plan, validate


class ReleaseProofTests(unittest.TestCase):
    def setUp(self):
        self.policy = {'schema': 1, 'target_seconds': 180, 'maximum_seconds': 300,
                       'targets_per_partition': 6, 'isolated_tests': []}
        self.metadata = {'workspace_members': list(PUBLIC_DAG), 'packages': [
            {'id': name, 'name': name, 'targets': [
                {'kind': ['lib'], 'name': name.replace('-', '_')},
                {'kind': ['test'], 'name': 'contract'},
                {'kind': ['custom-build'], 'name': 'build-script-build'},
            ]} for name in PUBLIC_DAG]}
        self.prepared = plan(self.metadata, self.policy)
        self.identity = {'source_sha': 'a' * 40, 'candidate_sha256': 'b' * 64}
        self.records = [{'check': check['id'], 'identity': self.identity, 'status': 'passed',
                         'elapsed_seconds': 3.0} for check in self.prepared['checks']]

    def directory(self):
        output = ROOT / 'artifacts/release-validation-parallelism/tests'
        output.mkdir(parents=True, exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=output)
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def test_every_workspace_target_has_one_owner(self):
        self.assertEqual(len(self.prepared['inventory']), 10)
        self.assertEqual(sum(len(check['targets']) for check in self.prepared['checks']), 10)

    def test_missing_target_cannot_be_accepted(self):
        damaged = copy.deepcopy(self.prepared)
        next(check for check in damaged['checks'] if check['kind'] == 'tests')['targets'].pop()
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            validate(damaged)

    def test_duplicate_target_cannot_be_accepted(self):
        damaged = copy.deepcopy(self.prepared)
        group = next(check for check in damaged['checks'] if check['kind'] == 'tests')
        group['targets'].append(group['targets'][0])
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            validate(damaged)

    def test_missing_package_proof_family_cannot_be_accepted(self):
        for kind in ('lint', 'docs', 'doctests', 'publish', 'format', 'package-contents', 'smoke', 'python-installation'):
            damaged = copy.deepcopy(self.prepared)
            damaged['checks'].remove(next(check for check in damaged['checks'] if check['kind'] == kind))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validate(damaged)

    def test_colliding_workspace_selectors_cannot_be_split_between_workers(self):
        damaged = copy.deepcopy(self.prepared)
        check = next(check for check in damaged['checks'] if any(target['selector'] == ['--lib'] for target in check['targets']))
        duplicate = copy.deepcopy(check);duplicate['id'] += '/other'
        duplicate['targets'] = check['targets'][1:];check['targets'] = check['targets'][:1]
        damaged['checks'].append(duplicate)
        with self.assertRaisesRegex(ValueError, 'selector'):
            validate(damaged)

    def test_unreviewed_target_kind_refuses_planning(self):
        self.metadata['packages'][0]['targets'].append({'kind': ['foreign'], 'name': 'unknown'})
        with self.assertRaisesRegex(ValueError, 'Unreviewed'):
            plan(self.metadata, self.policy)

    def test_heavy_target_is_isolated_and_remaining_targets_are_bounded(self):
        self.policy['isolated_tests'] = ['bijux-dag-core/slow_calendar']
        self.metadata['packages'][0]['targets'].extend(
            [{'kind': ['test'], 'name': 'slow_calendar'}] +
            [{'kind': ['test'], 'name': f'contract_{index}'} for index in range(8)])
        result = plan(self.metadata, self.policy)
        groups = [check for check in result['checks'] if check['kind'] == 'tests']
        owner = next(check for check in groups if any(target['target'] == 'slow_calendar' for target in check['targets']))
        self.assertEqual(len(owner['targets']), 1)
        self.assertTrue(all(len(check['targets']) <= 6 for check in groups))

    def test_complete_current_results_are_accepted(self):
        result = verify_receipts(self.prepared, self.identity, self.records)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['cargo_targets'], 10)

    def test_missing_duplicate_and_foreign_results_are_rejected(self):
        for records in (self.records[:-1], self.records + self.records[:1],
                        self.records + [{'check': 'foreign', 'identity': self.identity, 'status': 'passed'}]):
            with self.subTest(records=len(records)), self.assertRaises(ValueError):
                verify_receipts(self.prepared, self.identity, records)

    def test_failed_stale_and_over_budget_results_are_rejected(self):
        for values in ({'status': 'failed'}, {'identity': {'source_sha': 'c' * 40}},
                       {'elapsed_seconds': 300}, {'elapsed_seconds': -1}):
            damaged = copy.deepcopy(self.records)
            damaged[0].update(values)
            with self.subTest(values=values), self.assertRaises(ValueError):
                verify_receipts(self.prepared, self.identity, damaged)

    def test_target_budget_is_visible_without_relaxing_maximum(self):
        self.records[0]['elapsed_seconds'] = 181
        result = verify_receipts(self.prepared, self.identity, self.records)
        self.assertEqual(result['above_target'], [self.records[0]['check']])

    def test_modified_archive_is_rejected_before_extraction(self):
        root = self.directory();source = root / 'source';source.mkdir();(source / 'owned').write_text('original')
        archive = root / 'source.tar.gz';digest = pack(source, archive);archive.write_bytes(archive.read_bytes() + b'tampered')
        with self.assertRaisesRegex(ValueError, 'digest'):
            unpack(archive, root / 'destination', digest)
        self.assertFalse((root / 'destination').exists())

    def test_cache_layers_reconstruct_changed_and_new_outputs(self):
        root = self.directory();source = root / 'source';source.mkdir();(source / 'library').write_text('library')
        first = root / 'libraries.tar.gz';a = pack(source, first);baseline = snapshot(source)
        (source / 'binary').write_text('binary');(source / 'library').write_text('rebuilt')
        second = root / 'binaries.tar.gz';b = pack(source, second, baseline=baseline)
        destination = root / 'restored';unpack(first, destination, a);unpack(second, destination, b)
        self.assertEqual(snapshot(destination), snapshot(source))

    def test_unchanged_libraries_are_not_duplicated_in_binary_layer(self):
        root = self.directory();source = root / 'source';source.mkdir();(source / 'library').write_text('library')
        baseline = snapshot(source);(source / 'binary').write_text('binary');archive = root / 'binaries.tar.gz'
        pack(source, archive, baseline=baseline)
        with tarfile.open(archive) as stream:self.assertEqual(stream.getnames(), ['binary'])

    def test_archive_path_traversal_cannot_escape_its_destination(self):
        root = self.directory();archive = root / 'malicious.tar.gz'
        with tarfile.open(archive, 'w:gz') as stream:
            item = tarfile.TarInfo('../escape');item.size = 4
            stream.addfile(item, io.BytesIO(b'data'))
        with self.assertRaises(tarfile.FilterError):
            unpack(archive, root / 'destination', file_digest(archive))
        self.assertFalse((root / 'escape').exists())

    def test_parent_source_alias_cannot_replace_a_declared_input(self):
        root = self.directory();source = root / 'source';source.mkdir()
        (source / 'owned').write_text('owned');identity = source_files(source)
        original = source / 'owned';original.unlink()
        external = root / 'external';external.write_text('owned');original.symlink_to(external)
        with self.assertRaises(ValueError):verify_sources(source, identity)

    def test_registry_transfer_excludes_credentials_and_unrelated_outputs(self):
        root = self.directory();(root / 'cargo-home/registry').mkdir(parents=True)
        (root / 'cargo-home/registry/public').write_text('registry')
        (root / 'cargo-home/credentials.toml').write_text('credential')
        (root / 'target').mkdir();(root / 'target/library').write_text('compiled')
        (root / 'unrelated').write_text('unrelated');archive = root / 'cache.tar.gz'
        pack(root, archive, include=['target', 'cargo-home/registry'])
        with tarfile.open(archive) as stream:
            self.assertEqual(set(stream.getnames()), {'target/library', 'cargo-home/registry/public'})

    def test_internal_directory_alias_survives_candidate_transfer(self):
        root = self.directory();source = root / 'source';source.mkdir()
        (source / 'owned').mkdir();(source / 'owned/input').write_text('owned')
        (source / 'alias').symlink_to('owned', target_is_directory=True)
        identity = source_files(source);archive = root / 'candidate.tar.gz'
        value = pack(source, archive);destination = root / 'restored'
        unpack(archive, destination, value);verify_sources(destination, identity)
        self.assertTrue((destination / 'alias').is_symlink())

    def test_source_mutation_is_rejected(self):
        root = self.directory();(root / 'Cargo.lock').write_text('locked');identity = source_files(root)
        (root / 'Cargo.lock').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            verify_sources(root, identity)

    def test_source_alias_cannot_escape_its_owner(self):
        root = self.directory();source = root / 'source';source.mkdir()
        (root / 'external').write_text('external');(source / 'alias').symlink_to(root / 'external')
        with self.assertRaisesRegex(ValueError, 'alias'):
            source_files(source)

    def test_committed_internal_aliases_retain_their_exact_identity(self):
        root = self.directory();(root / 'owned').write_text('owned');(root / 'LICENSE').symlink_to('owned')
        identity = source_files(root);verify_sources(root, identity)
        (root / 'LICENSE').unlink();(root / 'LICENSE').write_text('owned')
        with self.assertRaises(ValueError):verify_sources(root, identity)

    def test_test_commands_preserve_feature_surface_and_select_every_owned_target(self):
        check = next(check for check in self.prepared['checks'] if check['kind'] == 'tests')
        arguments = commands(check)[0]
        self.assertIn('--workspace', arguments);self.assertIn('--all-features', arguments);self.assertIn('--locked', arguments)
        self.assertLessEqual(arguments.count('--lib'), 1)
        for target in check['targets']:
            for flag in target['selector']:self.assertIn(flag, arguments)

    def test_timing_suite_keeps_every_test_with_serial_resource_isolation(self):
        self.policy['serial_test_targets'] = ['bijux-dag-core/contract']
        result = plan(self.metadata, self.policy)
        selected = [check for check in result['checks'] if check.get('test_threads') == 1]
        self.assertEqual(len(selected), 1)
        arguments = commands(selected[0])[0]
        self.assertEqual(arguments[-2:], ['--', '--test-threads=1'])
        self.assertNotIn('--skip', arguments)
        self.assertIn('--all-features', arguments)
        selected[0].pop('test_threads')
        with self.assertRaisesRegex(ValueError, 'resource isolation'):
            validate(result)

    def test_unknown_timing_suite_refuses_planning(self):
        self.policy['serial_test_targets'] = ['bijux-cli/missing']
        with self.assertRaisesRegex(ValueError, 'Serial test policy'):
            plan(self.metadata, self.policy)

    def test_nested_fixture_builds_reuse_authenticated_compilation_outputs(self):
        root = self.directory();workspace = root / 'workspace';workspace.mkdir()
        cache = root / 'producer';(cache / 'target').mkdir(parents=True)
        (cache / 'target/compiled').write_text('compiled')
        archive = root / 'libraries.tar.gz';identity = pack(cache, archive)
        with patch.object(execution, 'OUT', root), patch.object(execution, 'WORKSPACE', workspace), \
             patch.object(execution, 'TARGET', root / 'target'), \
             patch.dict(execution.os.environ, {'RELEASE_LIBRARIES_SHA256': identity}):
            execution.restore({'files': {}}, libraries=True, binaries=False)
            self.assertEqual((workspace / 'artifacts/target/compiled').read_text(), 'compiled')
            self.assertEqual((workspace / 'artifacts/target').resolve(), root / 'target')

    def test_nested_fixture_cache_cannot_replace_an_unrelated_directory(self):
        root = self.directory();workspace = root / 'workspace';(workspace / 'artifacts/target').mkdir(parents=True)
        cache = root / 'producer';(cache / 'target').mkdir(parents=True)
        archive = root / 'libraries.tar.gz';identity = pack(cache, archive)
        with patch.object(execution, 'OUT', root), patch.object(execution, 'WORKSPACE', workspace), \
             patch.object(execution, 'TARGET', root / 'target'), \
             patch.dict(execution.os.environ, {'RELEASE_LIBRARIES_SHA256': identity}):
            with self.assertRaisesRegex(ValueError, 'Nested Cargo'):
                execution.restore({'files': {}}, libraries=True, binaries=False)
        self.assertTrue((workspace / 'artifacts/target').is_dir())

    def test_terminal_acceptance_rejects_failed_or_missing_producers(self):
        root = self.directory()
        environment = {'RELEASE_LIBRARIES_SECONDS': '2', 'RELEASE_BINARIES_SECONDS': '3'}
        for results in ([], ['success'] * 3, ['success', 'failure', 'success', 'success']):
            environment['RELEASE_JOB_RESULTS'] = json.dumps(results)
            with self.subTest(results=results), \
                 patch.object(execution, 'load', return_value=({'identity': self.identity}, self.prepared)), \
                 patch.object(execution, 'OUT', root), patch.dict(execution.os.environ, environment):
                with self.assertRaisesRegex(ValueError, 'Every producer'):
                    execution.accept()
            self.assertFalse((root / 'acceptance.json').exists())

    def test_publication_commands_always_remain_locked_dry_runs(self):
        for check in self.prepared['checks']:
            if check['kind'] == 'publish':
                arguments = commands(check)[0]
                self.assertIn('--dry-run', arguments);self.assertIn('--locked', arguments)


if __name__ == '__main__':
    unittest.main()
