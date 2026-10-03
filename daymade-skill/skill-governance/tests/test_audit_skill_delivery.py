import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

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


@pytest.mark.parametrize('field', ['schema_version', 'user_outcome', 'scope', 'source_repo', 'skill_name'])
@pytest.mark.parametrize('value', ['missing', 'empty'])
def test_missing_and_empty_required_fields_fail(tmp_path, field, value):
    skill, path, contract = fixture(tmp_path)
    if value == 'missing':
        del contract[field]
    else:
        contract[field] = ''
    path.write_text(json.dumps(contract))
    assert module.audit_delivery(skill, path)['status'] == 'invalid'


def test_correct_registered_source_and_link_do_not_claim_current_loading(tmp_path):
    skill, path, _ = fixture(tmp_path)
    report = module.audit_delivery(skill, path)
    assert report['static_status'] == 'valid', report
    assert report['status'] == 'unknown'
    assert report['runtime']['status'] == 'unknown'
    assert report['user_requirement_match']['status'] == 'unknown'


def test_runnable_skill_in_wrong_repo_fails_delivery(tmp_path):
    skill, path, _ = fixture(tmp_path)
    other = tmp_path / 'pkm'
    other.mkdir()
    subprocess.run(['git', '-C', str(other), 'init', '-q'], check=True)
    misplaced = other / skill.name
    misplaced.mkdir()
    (misplaced / 'SKILL.md').write_text((skill / 'SKILL.md').read_text())
    (misplaced / 'run.py').write_text("print('working')\n")
    runtime = subprocess.run([sys.executable, str(misplaced / 'run.py')], capture_output=True, text=True, check=True)
    assert runtime.stdout.strip() == 'working'
    installed = tmp_path / 'wrong-install'
    installed.symlink_to(misplaced, target_is_directory=True)
    contract = json.loads(path.read_text())
    contract['installed_path'] = str(installed)
    path.write_text(json.dumps(contract))
    report = module.audit_delivery(misplaced, path)
    assert report['status'] == 'invalid', report


def test_install_path_omission_is_unknown_not_invalid_contract(tmp_path):
    skill, path, contract = fixture(tmp_path)
    del contract['installed_path']
    path.write_text(json.dumps(contract))
    report = module.audit_delivery(skill, path)
    assert report['status'] == 'unknown', report
    assert report['runtime']['status'] == 'unknown'


@pytest.mark.parametrize('value', ['', None])
def test_explicit_empty_install_path_is_invalid(tmp_path, value):
    skill, path, contract = fixture(tmp_path)
    contract['installed_path'] = value
    path.write_text(json.dumps(contract))
    assert module.audit_delivery(skill, path)['status'] == 'invalid'


def test_malformed_contract_cli_is_json_finding(tmp_path):
    path = tmp_path / 'contract.json'
    path.write_text('null')
    completed = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path), '--delivery-contract', str(path), '--json'], capture_output=True, text=True)
    assert completed.returncode == 2
    assert json.loads(completed.stdout)['status'] == 'invalid'


def test_source_audit_unavailable_is_unknown_not_pass(tmp_path, monkeypatch):
    skill, path, _ = fixture(tmp_path)
    def unavailable(*args, **kwargs):
        raise OSError('Source audit deliberately unavailable')
    monkeypatch.setattr(module.subprocess, 'run', unavailable)
    report = module.audit_delivery(skill, path)
    assert report['status'] == 'unknown'
    assert report['runtime']['status'] == 'unknown'


def test_author_supplied_runtime_green_is_not_current_host_evidence(tmp_path):
    skill, path, contract = fixture(tmp_path)
    contract['runtime'] = {'status': 'valid', 'currently_loaded': True}
    path.write_text(json.dumps(contract))
    report = module.audit_delivery(skill, path)
    assert report['runtime']['status'] == 'unknown'
    assert report['status'] == 'unknown'


def test_requested_identity_mismatch_fails_without_losing_layer_details(tmp_path):
    skill, path, contract = fixture(tmp_path)
    contract['skill_name'] = 'different-skill'
    path.write_text(json.dumps(contract))
    report = module.audit_delivery(skill, path)
    assert report['status'] == 'invalid'
    assert report['checks']['identity']['status'] == 'invalid'
    assert report['checks']['source']['status'] == 'valid'
    assert report['checks']['installation']['status'] == 'valid'


def test_project_contract_uses_project_roots_without_marketplace(tmp_path):
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
    assert report['static_status'] == 'valid', report
    assert report['checks']['registration']['status'] == 'valid'
    assert report['status'] == 'unknown'
