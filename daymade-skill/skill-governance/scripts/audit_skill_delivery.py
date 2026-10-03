#!/usr/bin/env python3
"""Read-only delivery-contract adapter; source ownership stays with skill-creator.

Exit 1: delivery unknown (including static-only success); 2: invalid.
A static pass never proves current host loading or the user's intent.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys


REQUIRED_STRINGS = ('user_outcome', 'scope', 'source_repo', 'skill_name')


def audit_delivery(skill_path, contract_path):
    report = {
        'status': 'unknown', 'checks': {},
        'runtime': {'status': 'unknown', 'message': 'Current host loading was not probed; use a fresh host audit.'},
        'user_requirement_match': {'status': 'unknown', 'message': 'Compare this contract with the original user request independently.'},
    }
    try:
        contract = json.loads(Path(contract_path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report.update(status='invalid', checks={'contract': {'status': 'invalid', 'detail': f'Cannot read delivery contract: {exc}'}})
        return report
    errors = []
    if not isinstance(contract, dict):
        errors.append('Delivery contract must be a JSON object')
    else:
        if type(contract.get('schema_version')) is not int or contract['schema_version'] != 1:
            errors.append('schema_version must be integer 1')
        for field in REQUIRED_STRINGS:
            if not isinstance(contract.get(field), str) or not contract[field].strip():
                errors.append(f'{field} must be a non-empty string')
        if contract.get('scope') not in ('marketplace', 'project'):
            errors.append('scope must be marketplace or project')
        for field in ('installed_path', 'inventory'):
            if field in contract and (not isinstance(contract[field], str) or not contract[field].strip()):
                errors.append(f'{field}, when supplied, must be a non-empty path string')
    if errors:
        report.update(status='invalid', checks={'contract': {'status': 'invalid', 'detail': errors}})
        return report
    core = Path(__file__).resolve().parents[2] / 'skill-creator/scripts/source_contract.py'
    command = [sys.executable, str(core), 'audit', str(skill_path), '--repo', contract['source_repo'], '--scope', contract['scope']]
    if 'installed_path' in contract:
        command.extend(['--install-path', contract['installed_path']])
    if 'inventory' in contract:
        command.extend(['--inventory', contract['inventory']])
    try:
        if not core.is_file():
            raise ValueError(f'Source audit entry point not found: {core}')
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        source = json.loads(result.stdout)
        if not isinstance(source, dict) or source.get('status') not in ('valid', 'invalid', 'unknown'):
            raise ValueError('Source audit returned no recognized status')
        if result.returncode not in (0, 1, 2):
            raise ValueError(f'Source audit could not complete (exit {result.returncode})')
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        report['checks']['source_evidence'] = {'status': 'unknown', 'detail': f'Source audit unavailable: {exc}'}
        return report
    report['source_audit'] = source
    report['checks'] = dict(source.get('checks', {}))
    report['static_status'] = source['status']
    # The core owns source/frontmatter identity; compare requested identity too.
    observed_name = source.get('skill_name')
    if observed_name is not None and observed_name != contract['skill_name']:
        report['checks']['identity'] = {'status': 'invalid', 'detail': 'Requested skill_name differs from audited identity'}
        report['static_status'] = 'invalid'
    report['status'] = 'invalid' if report['static_status'] == 'invalid' else 'unknown'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skill_path')
    parser.add_argument('--delivery-contract', required=True)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    report = audit_delivery(args.skill_path, args.delivery_contract)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Delivery review: {report['status']}; static: {report.get('static_status', 'unknown')}; runtime: unknown")
        for layer, check in report['checks'].items():
            print(f"{layer}: {json.dumps(check, ensure_ascii=False)}")
    return {'valid': 0, 'unknown': 1, 'invalid': 2}[report['status']]


if __name__ == '__main__':
    sys.exit(main())
