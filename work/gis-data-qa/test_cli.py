"""Exercise the actual CLI's exits, deterministic output, and read-only inputs."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / 'fixtures'
# Literal expectations derived from the profile, not from validator helpers.
CASES = [
    ('geojson', 'geojson-valid.json', 0, []),
    ('arcgis', 'arcgis-valid.json', 0, []),
    ('geojson', 'geojson-null-geometry.json', 1, ['geometry.null']),
    ('geojson', 'geojson-projected-coordinates.json', 1, ['coordinate.bounds']),
    ('geojson', 'geojson-axis-swap-undetectable.json', 0, []),
    ('arcgis', 'arcgis-wrong-crs.json', 1, ['crs.mismatch']),
    ('arcgis', 'arcgis-truncated.json', 1, ['response.truncated']),
]


def fingerprint(path):
    info = path.stat()
    return (hashlib.sha256(path.read_bytes()).hexdigest(), info.st_size,
            info.st_mtime_ns, stat.S_IMODE(info.st_mode))


class CommandLineContract(unittest.TestCase):
    def invoke(self, kind, path, metadata=None, seed='1', cwd=None):
        command = [sys.executable, '-B', str(ROOT / 'qa.py'), kind, str(path)]
        if metadata is not None:
            command += ['--metadata', str(metadata)]
        return subprocess.run(command, cwd=cwd or ROOT, text=True, capture_output=True,
                              env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE='1'),
                              timeout=10)

    def assert_result(self, completed, exit_code, codes):
        self.assertEqual(completed.returncode, exit_code, completed.stderr)
        self.assertEqual(completed.stderr, '')
        data = json.loads(completed.stdout)
        self.assertIs(data['valid'], exit_code == 0)
        self.assertEqual([issue['code'] for issue in data['issues']], codes)

    def test_seven_saved_cases_have_expected_exits_and_identical_outputs_across_seeds(self):
        for kind, name, expected_exit, codes in CASES:
            with self.subTest(name=name):
                first = self.invoke(kind, FIXTURES / name, seed='1')
                second = self.invoke(kind, FIXTURES / name, seed='98765')
                self.assert_result(first, expected_exit, codes)
                self.assert_result(second, expected_exit, codes)
                self.assertEqual((first.stdout, first.stderr), (second.stdout, second.stderr))

    def test_multi_issue_output_is_stable_across_hash_seeds(self):
        # A set of missing fields must not make issue text/order nondeterministic.
        document = json.loads((FIXTURES / 'geojson-valid.json').read_text())
        document['features'][0]['properties'] = {'extra': 'unexpected'}
        document['features'][0]['geometry']['coordinates'] = [181, 91]
        with tempfile.TemporaryDirectory(prefix='gis-cli-') as temporary:
            path = Path(temporary) / 'multiple-issues.json'
            path.write_text(json.dumps(document))
            first = self.invoke('geojson', path, seed='1')
            second = self.invoke('geojson', path, seed='98765')
            self.assert_result(first, 1, ['schema.missing', 'schema.extra', 'schema.feature_id', 'coordinate.bounds'])
            self.assertEqual((first.returncode, first.stdout, first.stderr),
                             (second.returncode, second.stdout, second.stderr))

    def test_fixture_and_metadata_contents_modes_and_mtimes_do_not_change(self):
        paths = sorted(FIXTURES.glob('*.json'))
        before = {path: fingerprint(path) for path in paths}
        for kind, name, expected_exit, codes in CASES:
            self.assert_result(self.invoke(kind, FIXTURES / name), expected_exit, codes)
        self.assertEqual({path: fingerprint(path) for path in paths}, before)

    def test_missing_malformed_and_invalid_encoding_inputs_exit_two(self):
        with tempfile.TemporaryDirectory(prefix='gis-cli-') as temporary:
            folder = Path(temporary)
            missing = folder / 'does-not-exist.json'
            malformed = folder / 'malformed.json'
            malformed.write_text('{')
            invalid_utf8 = folder / 'invalid-utf8.json'
            invalid_utf8.write_bytes(b'\xff')
            for response in [missing, malformed, invalid_utf8]:
                with self.subTest(response=response.name):
                    self.assert_result(self.invoke('geojson', response), 2, ['input.read'])
            for metadata in [missing, malformed, invalid_utf8]:
                with self.subTest(metadata=metadata.name):
                    self.assert_result(self.invoke('geojson', FIXTURES / 'geojson-valid.json', metadata), 2, ['input.read'])
            self.assertEqual(malformed.read_bytes(), b'{')
            self.assertEqual(invalid_utf8.read_bytes(), b'\xff')
            self.assertFalse(missing.exists())

    def test_valid_json_with_contract_error_exits_one_and_default_metadata_works_from_other_cwd(self):
        with tempfile.TemporaryDirectory(prefix='gis-cli-') as temporary:
            folder = Path(temporary)
            metadata = json.loads((FIXTURES / 'service-metadata.json').read_text())
            metadata['spatialReference']['wkid'] = 3857
            path = folder / 'wrong-metadata.json'
            path.write_text(json.dumps(metadata))
            self.assert_result(self.invoke('geojson', FIXTURES / 'geojson-valid.json', path), 1, ['metadata.contract'])
            self.assert_result(self.invoke('geojson', FIXTURES / 'geojson-valid.json', cwd=folder), 0, [])

    def test_runnable_demonstration_reports_all_seven_expected_results(self):
        completed = subprocess.run([sys.executable, '-B', str(ROOT / 'demo.py')],
                                   cwd=ROOT, text=True, capture_output=True,
                                   env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, '')
        report = json.loads(completed.stdout)
        self.assertIs(report['all_checks_passed'], True)
        self.assertIs(report['inputs_unchanged'], True)
        self.assertEqual(len(report['cases']), 7)
        expected = {name: (exit_code, codes) for _, name, exit_code, codes in CASES}
        observed = {row['fixture']: (row['actual_exit'], row['issue_codes']) for row in report['cases']}
        self.assertEqual(observed, expected)
        self.assertTrue(all(row['outputs_identical_across_seeds'] for row in report['cases']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
