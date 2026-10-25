"""Read-only, offline demonstration of the seven saved synthetic CLI cases.

Run: python3 -B demo.py
Exit 0 means expected accepted/rejected cases, repeatability and input checks pass.
It does not mean every synthetic response is valid.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
CASES = [
    ('geojson', 'geojson-valid.json', 0, []),
    ('arcgis', 'arcgis-valid.json', 0, []),
    ('geojson', 'geojson-null-geometry.json', 1, ['geometry.null']),
    ('geojson', 'geojson-projected-coordinates.json', 1, ['coordinate.bounds']),
    ('geojson', 'geojson-axis-swap-undetectable.json', 0, []),
    ('arcgis', 'arcgis-wrong-crs.json', 1, ['crs.mismatch']),
    ('arcgis', 'arcgis-truncated.json', 1, ['response.truncated']),
]


def snapshot():
    result = {}
    for path in sorted((ROOT / 'fixtures').iterdir()):
        if path.is_file():
            info = path.stat()
            result[path.name] = {
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'size': info.st_size, 'mtime_ns': info.st_mtime_ns,
                'mode': stat.S_IMODE(info.st_mode),
            }
    return result


def main():
    before = snapshot()
    cases = []
    for kind, name, expected_exit, expected_codes in CASES:
        command = [sys.executable, '-B', str(ROOT / 'qa.py'), kind,
                   str(ROOT / 'fixtures' / name)]
        runs = [subprocess.run(
            command, cwd=ROOT, text=True, capture_output=True, timeout=10,
            env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE='1'))
            for seed in ['1', '98765']]
        first, second = runs
        try:
            data = json.loads(first.stdout)
            codes = [issue['code'] for issue in data['issues']]
            contract_met = (first.returncode == expected_exit
                            and data['valid'] is (expected_exit == 0)
                            and codes == expected_codes and first.stderr == '')
        except (ValueError, KeyError, TypeError):
            codes, contract_met = [], False
        identical = ((first.returncode, first.stdout, first.stderr)
                     == (second.returncode, second.stdout, second.stderr))
        cases.append({
            'fixture': name, 'format': kind,
            'expected_exit': expected_exit, 'actual_exit': first.returncode,
            'issue_codes': codes, 'expected_result_observed': contract_met,
            'outputs_identical_across_seeds': identical,
            'stdout_sha256': hashlib.sha256(first.stdout.encode()).hexdigest(),
        })
    unchanged = before == snapshot()
    passed = unchanged and all(row['expected_result_observed']
                               and row['outputs_identical_across_seeds'] for row in cases)
    print(json.dumps({
        'synthetic_only': True, 'cases': cases,
        'inputs_unchanged': unchanged,
        'input_sha256': {name: info['sha256'] for name, info in before.items()},
        'all_checks_passed': passed,
    }, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
