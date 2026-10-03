import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/audit_skill_delivery.py'
spec = importlib.util.spec_from_file_location('delivery_audit', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(tmp_path):
    repo = tmp_path / 'source'
    repo.mkdir()
    subprocess.run(['git', '-C', str(repo), 'init', '-q'], check=True)
    skill = repo / 'target-skill'
    skill.mkdir()
    (skill / 'SKILL.md').write_text('---\nname: target-skill\ndescription: Reviews a target skill. Use when checking delivery ownership.\n---\n\n# Test\n\nInspect the requested source.\n')
    manifest = repo / '.claude-plugin/marketplace.json'
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({'name': 'test-market', 'plugins': [{'name': 'target-skill', 'source': './target-skill'}]}))
    installed = tmp_path / 'installed'
    installed.symlink_to(skill, target_is_directory=True)
    contract = {'schema_version': 1, 'user_outcome': 'Deliver target-skill from this source', 'scope': 'marketplace', 'source_repo': str(repo), 'skill_name': 'target-skill', 'installed_path': str(installed)}
    path = tmp_path / 'contract.json'
    path.write_text(json.dumps(contract))
    return skill, path, contract


class SkillDeliveryAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='skill-delivery-audit-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_missing_and_empty_required_fields_fail(self):
        for field in ('schema_version', 'user_outcome', 'scope', 'source_repo', 'skill_name'):
            for value in ('missing', 'empty'):
                with self.subTest(field=field, value=value):
                    tmp_path = self.root / (field + '-' + value)
                    tmp_path.mkdir()
                    skill, path, contract = fixture(tmp_path)
                    if value == 'missing':
                        del contract[field]
                    else:
                        contract[field] = ''
                    path.write_text(json.dumps(contract))
                    self.assertEqual(module.audit_delivery(skill, path)['status'], 'invalid')

    def test_correct_registered_source_and_link_do_not_claim_current_loading(self):
        tmp_path = self.root
        skill, path, _ = fixture(tmp_path)
        report = module.audit_delivery(skill, path)
        self.assertEqual(report['static_status'], 'valid', report)
        self.assertEqual(report['status'], 'unknown')
        self.assertEqual(report['runtime']['status'], 'unknown')
        self.assertEqual(report['user_requirement_match']['status'], 'unknown')

    def test_runnable_skill_in_wrong_repo_fails_delivery(self):
        tmp_path = self.root
        skill, path, _ = fixture(tmp_path)
        other = tmp_path / 'pkm'
        other.mkdir()
        subprocess.run(['git', '-C', str(other), 'init', '-q'], check=True)
        misplaced = other / skill.name
        misplaced.mkdir()
        (misplaced / 'SKILL.md').write_text((skill / 'SKILL.md').read_text())
        (misplaced / 'run.py').write_text("print('working')\n")
        runtime = subprocess.run([sys.executable, str(misplaced / 'run.py')], capture_output=True, text=True, check=True)
        self.assertEqual(runtime.stdout.strip(), 'working')
        installed = tmp_path / 'wrong-install'
        installed.symlink_to(misplaced, target_is_directory=True)
        contract = json.loads(path.read_text())
        contract['installed_path'] = str(installed)
        path.write_text(json.dumps(contract))
        report = module.audit_delivery(misplaced, path)
        self.assertEqual(report['status'], 'invalid', report)

    def test_install_path_omission_is_unknown_not_invalid_contract(self):
        tmp_path = self.root
        skill, path, contract = fixture(tmp_path)
        del contract['installed_path']
        path.write_text(json.dumps(contract))
        report = module.audit_delivery(skill, path)
        self.assertEqual(report['status'], 'unknown', report)
        self.assertEqual(report['runtime']['status'], 'unknown')

    def test_explicit_empty_install_path_is_invalid(self):
        for index, value in enumerate(('', None)):
            with self.subTest(value=value):
                tmp_path = self.root / str(index)
                tmp_path.mkdir()
                skill, path, contract = fixture(tmp_path)
                contract['installed_path'] = value
                path.write_text(json.dumps(contract))
                self.assertEqual(module.audit_delivery(skill, path)['status'], 'invalid')

    def test_malformed_contract_cli_is_json_finding(self):
        tmp_path = self.root
        path = tmp_path / 'contract.json'
        path.write_text('null')
        completed = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path), '--delivery-contract', str(path), '--json'], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)['status'], 'invalid')

    def test_source_audit_unavailable_is_unknown_not_pass(self):
        tmp_path = self.root
        skill, path, _ = fixture(tmp_path)
        with mock.patch.object(module.subprocess, 'run', side_effect=OSError('Source audit deliberately unavailable')):
            report = module.audit_delivery(skill, path)
        self.assertEqual(report['status'], 'unknown')
        self.assertEqual(report['runtime']['status'], 'unknown')

    def test_author_supplied_runtime_green_is_not_current_host_evidence(self):
        tmp_path = self.root
        skill, path, contract = fixture(tmp_path)
        contract['runtime'] = {'status': 'valid', 'currently_loaded': True}
        path.write_text(json.dumps(contract))
        report = module.audit_delivery(skill, path)
        self.assertEqual(report['runtime']['status'], 'unknown')
        self.assertEqual(report['status'], 'unknown')

    def test_requested_identity_mismatch_fails_without_losing_layer_details(self):
        tmp_path = self.root
        skill, path, contract = fixture(tmp_path)
        contract['skill_name'] = 'different-skill'
        path.write_text(json.dumps(contract))
        report = module.audit_delivery(skill, path)
        self.assertEqual(report['status'], 'invalid')
        self.assertEqual(report['checks']['identity']['status'], 'invalid')
        self.assertEqual(report['checks']['source']['status'], 'valid')
        self.assertEqual(report['checks']['installation']['status'], 'valid')

    def test_project_contract_uses_project_roots_without_marketplace(self):
        tmp_path = self.root
        project = tmp_path / 'project'
        project.mkdir()
        subprocess.run(['git', '-C', str(project), 'init', '-q'], check=True)
        skill = project / '.agents/skills/target-skill'
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text('---\nname: target-skill\ndescription: Checks project delivery. Use when auditing a project skill.\n---\n\n# Project\n')
        installed = tmp_path / 'installed'
        installed.symlink_to(skill, target_is_directory=True)
        contract = tmp_path / 'contract.json'
        contract.write_text(json.dumps({'schema_version': 1, 'user_outcome': 'Keep this project skill available', 'scope': 'project', 'source_repo': str(project), 'skill_name': 'target-skill', 'installed_path': str(installed)}))
        report = module.audit_delivery(skill, contract)
        self.assertEqual(report['static_status'], 'valid', report)
        self.assertEqual(report['checks']['registration']['status'], 'valid')
        self.assertEqual(report['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
