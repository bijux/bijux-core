"""Refuse incomplete native inventories, changed case selection and failed inputs."""
from pathlib import Path
import copy
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / '.github/scripts'))
from native_testing import execution
from native_testing.planning import catalogue, case_totals, plan, validate


class NativeProofTests(unittest.TestCase):
    def setUp(self):
        self.policy = {'schema': 1, 'target_seconds': 180, 'maximum_seconds': 300,
                       'targets_per_partition': 6, 'isolated_tests': [], 'serial_test_targets': []}
        self.metadata = {'workspace_members': ['foundation', 'consumer'], 'packages': [
            {'id': name, 'name': name, 'targets': [
                {'name': name, 'kind': ['lib'], 'test': True},
                {'name': 'contract', 'kind': ['test'], 'test': True},
                {'name': 'measurement', 'kind': ['bench'], 'test': False},
            ]} for name in ['foundation', 'consumer']]}
        self.value = plan(self.metadata, self.policy, 'not test(/^slow__/)')

    def test_binary_only_workspace_members_contribute_their_dev_dependency_features(self):
        self.metadata['workspace_members'].append('runner')
        self.metadata['packages'].append({'id':'runner','name':'runner','targets':[
            {'name':'engine','kind':['bin'],'test':True}]})
        value=plan(self.metadata,self.policy,'not test(/^slow__/)')
        self.assertIn('--lib',value['warm_selectors'])
        self.assertIn('--bin',value['warm_selectors'])
        self.assertIn('engine',value['warm_selectors'])
        value['warm_selectors']=['--lib']
        with self.assertRaisesRegex(ValueError,'dependency graph'):validate(value)

    def test_complete_native_surface_excludes_the_unselected_benchmark(self):
        self.assertEqual(len(self.value['inventory']), 4)
        self.assertEqual(sum(len(c['targets']) for c in self.value['checks']), 4)
        self.assertEqual(sum(c['kind']=='python' for c in self.value['checks']), 1)

    def test_missing_and_duplicate_native_targets_are_rejected(self):
        for duplicate in [False, True]:
            value = copy.deepcopy(self.value);check = next(c for c in value['checks'] if c['targets'])
            if duplicate:check['targets'].append(check['targets'][0])
            else:check['targets'].pop()
            with self.subTest(duplicate=duplicate), self.assertRaisesRegex(ValueError, 'exactly one'):
                validate(value)

    def test_python_coverage_cannot_be_removed(self):
        self.value['checks'] = [c for c in self.value['checks'] if c['kind']!='python']
        with self.assertRaisesRegex(ValueError, 'Python coverage'):validate(self.value)

    def test_colliding_selectors_remain_in_one_worker(self):
        owners = {}
        for check in self.value['checks']:
            for target in check['targets']:owners.setdefault(tuple(target['selector']), set()).add(check['id'])
        self.assertTrue(all(len(ids)==1 for ids in owners.values()))

    def test_nextest_flags_retain_the_canonical_locked_workspace_and_filter(self):
        check = next(c for c in self.value['checks'] if c['targets'])
        arguments = execution.rust_arguments(check, self.value)
        self.assertIn('--workspace', arguments);self.assertIn('--all-features', arguments);self.assertIn('--locked', arguments)
        self.assertEqual(arguments[arguments.index('--profile')+1], 'ci')
        self.assertEqual(arguments[arguments.index('-E')+1], self.value['nextest_filter'])
        self.assertNotIn('--no-tests', arguments)
        for target in check['targets']:
            for flag in target['selector']:self.assertIn(flag, arguments)

    def test_inventory_and_execution_reuse_the_same_compiled_binary_metadata(self):
        check = next(c for c in self.value['checks'] if c['targets'])
        listing = execution.rust_arguments(check, self.value, listing=True, reuse=True)
        running = execution.rust_arguments(check, self.value, reuse=True)
        for arguments in [listing, running]:
            self.assertEqual(arguments[arguments.index('--cargo-metadata')+1], str(execution.OUT/'cargo-metadata.json'))
            self.assertEqual(arguments[arguments.index('--binaries-metadata')+1], str(execution.OUT/'binaries-metadata.json'))
            self.assertEqual(arguments[arguments.index('-E')+1], self.value['nextest_filter'])
            self.assertEqual(arguments[arguments.index('--profile')+1], 'ci')
            self.assertNotIn('--workspace', arguments)
            self.assertNotIn('--target-dir', arguments)
        self.assertIn('--workspace', execution.rust_arguments(check, self.value, listing=True))

    def test_unknown_case_profile_is_rejected(self):
        self.value['nextest_profile']='default'
        with self.assertRaisesRegex(ValueError, 'canonical'):validate(self.value)

    def suite(self, target, cases):
        return {'package-name': target['package'], 'binary-name': target['target'],
                'binary-id': target['package']+'::'+target['target'],
                'kind': target['selector'][0].removeprefix('--'), 'testcases': cases}

    def test_compiled_case_catalogue_accounts_for_the_existing_filter_and_ignored_cases(self):
        check = next(c for c in self.value['checks'] if c['targets'])
        suites = {str(i): self.suite(target, {
            'ordinary': {'ignored': False, 'filter-match': {'status':'matches'}},
            'slow__excluded': {'ignored': False, 'filter-match': {'status':'mismatch'}},
            'ignored': {'ignored': True, 'filter-match': {'status':'matches'}},
        }) for i,target in enumerate(check['targets'])}
        result=catalogue(check, {'rust-suites':suites})
        self.assertEqual(result['compiled_targets'], len(check['targets']))
        self.assertEqual(len(result['selected_cases']), len(check['targets']))
        self.assertEqual(len(result['excluded_cases']), 2*len(check['targets']))

    def test_empty_binary_is_still_a_required_compilation_proof(self):
        check = next(c for c in self.value['checks'] if c['targets'])
        suites = {str(i):self.suite(target,{}) for i,target in enumerate(check['targets'])}
        result=catalogue(check, {'rust-suites':suites})
        self.assertEqual(result['selected_cases'], [])
        with self.assertRaisesRegex(ValueError, 'nonempty'):case_totals([result])

    def test_missing_and_foreign_compiled_binaries_are_rejected(self):
        check = next(c for c in self.value['checks'] if c['targets'])
        with self.assertRaisesRegex(ValueError, 'assigned Cargo'):catalogue(check, {'rust-suites':{}})

    def test_duplicate_case_execution_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unique'):
            case_totals([{'selected_cases':['foundation::ordinary']}, {'selected_cases':['foundation::ordinary']}])

    def test_failed_or_missing_native_producers_cannot_accept(self):
        for results in [[], ['success']*5, ['success']*5+['failure']]:
            with self.subTest(results=results), patch.object(execution,'load',return_value=({},self.value)), \
                 patch.dict(execution.os.environ, {'NATIVE_JOB_RESULTS':json.dumps(results)}):
                with self.assertRaisesRegex(ValueError, 'Every native producer'):execution.accept()

    def test_python_worker_uses_the_full_canonical_coverage_entrypoint(self):
        arguments=execution.python_arguments()
        self.assertEqual(arguments[:2], ['make','test-py'])
        self.assertFalse(any('PYTEST_ADDOPTS' in value or 'PYTEST_MARKER_EXPR' in value for value in arguments))
        self.assertTrue(any(value.startswith('TEST_ARTIFACTS_DIR=') for value in arguments))
