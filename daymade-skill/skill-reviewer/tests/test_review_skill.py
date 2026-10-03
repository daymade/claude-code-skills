import json
import subprocess
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
REVIEWER = SKILL_DIR / "scripts" / "review_skill.py"


def write_skill(tmp_path, frontmatter, body="# Test Skill\n"):
    skill_dir = tmp_path / "target-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n" + frontmatter + "\n---\n\n" + body,
        encoding="utf-8",
    )
    return skill_dir


def run_reviewer(skill_path=None, *extra_args):
    command = [sys.executable, str(REVIEWER)]
    if skill_path is not None:
        command.append(str(skill_path))
    command.extend(extra_args)
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def valid_frontmatter():
    return (
        "name: target-skill\n"
        "description: Reviews a target skill. Use when checking a skill before publishing."
    )


def test_invalid_yaml_is_an_error(tmp_path):
    skill_dir = write_skill(
        tmp_path,
        "name: target-skill\n"
        "description: [broken YAML",
    )

    result = run_reviewer(skill_dir, "--json")

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["summary"]["errors"] >= 1
    assert any("Invalid YAML" in issue["message"] for issue in report["issues"])


def test_unexpected_frontmatter_field_is_an_error(tmp_path):
    skill_dir = write_skill(
        tmp_path,
        valid_frontmatter() + "\nunexpected-field: value",
    )

    result = run_reviewer(skill_dir, "--json")

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert any("Unexpected key" in issue["message"] for issue in report["issues"])


def test_placeholders_are_not_reported_as_private_data(tmp_path):
    placeholder_path = "/Users/" + "username/project"
    body = """# Test Skill

```python
api_key = "<api-key>"
token = "your-api-key-here"
workspace = "{}"
```
""".format(placeholder_path)
    skill_dir = write_skill(tmp_path, valid_frontmatter(), body)

    result = run_reviewer(skill_dir, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert not any(issue["category"] == "privacy" for issue in report["issues"])


def test_real_looking_secret_is_reported(tmp_path):
    secret_value = "sk-" + ("A1b2C3d4" * 4)
    body = '# Test Skill\n\n```python\napi_key = "{}"\n```\n'.format(secret_value)
    skill_dir = write_skill(tmp_path, valid_frontmatter(), body)

    result = run_reviewer(skill_dir, "--json")

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert any(issue["category"] == "privacy" for issue in report["issues"])


def test_placeholder_word_inside_real_value_does_not_suppress_finding(tmp_path):
    secret_value = "latest" + "ProductionCredential42"
    body = (
        '# Test Skill\n\n```python\n'
        'api_key = "{}"\n'
        '```\n'
    ).format(secret_value)
    skill_dir = write_skill(tmp_path, valid_frontmatter(), body)

    result = run_reviewer(skill_dir, "--json")

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert any(issue["category"] == "privacy" for issue in report["issues"])


def test_placeholder_token_inside_real_value_does_not_suppress_finding(tmp_path):
    secret_values = [
        "prod-test-credential-A1b2C3d4E5f6",
        "prod-example-key-A1b2C3d4E5f6",
    ]
    body = '# Test Skill\n\n```python\npassword = "{}"\n```\n'.format(
        secret_values[0]
    )
    skill_dir = write_skill(tmp_path, valid_frontmatter(), body)

    result = run_reviewer(skill_dir, "--json")

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert any(issue["category"] == "privacy" for issue in report["issues"])

    (skill_dir / "SKILL.md").write_text(
        "---\n" + valid_frontmatter() + "\n---\n\n"
        + '# Test Skill\n\n```python\napi_key = "{}"\n```\n'.format(
            secret_values[1]
        ),
        encoding="utf-8",
    )
    result = run_reviewer(skill_dir, "--json")
    assert result.returncode == 2


def test_bare_except_is_found_when_typed_except_also_exists(tmp_path):
    skill_dir = write_skill(tmp_path, valid_frontmatter())
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "check.py").write_text(
        "#!/usr/bin/env python3\n"
        "try:\n"
        "    pass\n"
        "except:\n"
        "    pass\n\n"
        "try:\n"
        "    pass\n"
        "except Exception:\n"
        "    pass\n",
        encoding="utf-8",
    )

    result = run_reviewer(skill_dir, "--json")

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert any("bare 'except:'" in issue["message"] for issue in report["issues"])


def test_invalid_utf8_is_a_structured_operational_error(tmp_path):
    skill_dir = tmp_path / "target-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_bytes(
        b"---\nname: target-skill\ndescription: Invalid UTF-8 fixture\n---\n\xff"
    )

    result = run_reviewer(skill_dir, "--json")

    assert result.returncode == 3
    report = json.loads(result.stdout)
    assert report["status"] == "operational_error"
    assert "UTF-8" in report["error"]["message"]
    assert "Traceback" not in result.stderr


def test_missing_pyyaml_is_a_structured_operational_error():
    result = subprocess.run(
        [sys.executable, "-S", str(REVIEWER), str(SKILL_DIR), "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )

    assert result.returncode == 3
    report = json.loads(result.stdout)
    assert report["status"] == "operational_error"
    assert "PyYAML" in report["error"]["message"]
    assert "Traceback" not in result.stderr


def test_missing_arguments_use_operational_exit_code():
    result = run_reviewer()

    assert result.returncode == 3
    assert "usage:" in result.stderr.lower()


def test_missing_arguments_are_json_when_requested():
    result = run_reviewer(None, "--json")

    assert result.returncode == 3
    report = json.loads(result.stdout)
    assert report["status"] == "operational_error"
    assert report["error"]["category"] == "invocation"


def test_reviewer_accepts_its_own_bundle():
    result = run_reviewer(SKILL_DIR, "--json")

    assert result.returncode == 0, result.stdout + result.stderr


def test_quality_only_review_does_not_claim_delivery(tmp_path):
    skill = write_skill(tmp_path, valid_frontmatter())
    result = run_reviewer(skill, '--json')
    assert result.returncode == 0
    assert json.loads(result.stdout)['delivery_review']['status'] == 'not_requested'


def test_explicit_invalid_delivery_contract_blocks_healthy_quality(tmp_path):
    skill = write_skill(tmp_path, valid_frontmatter())
    contract = tmp_path / 'delivery.json'
    contract.write_text(json.dumps({'schema_version': 1}))
    result = run_reviewer(skill, '--delivery-contract', str(contract), '--json')
    report = json.loads(result.stdout)
    assert result.returncode == 2
    assert report['delivery_review']['status'] == 'invalid'
    assert any(issue['category'] == 'delivery' for issue in report['issues'])


def test_wrong_source_blocks_delivery_even_with_valid_structure_and_working_script(tmp_path):
    source_repo = tmp_path / 'expected-owner'
    source_repo.mkdir()
    subprocess.run(['git', '-C', str(source_repo), 'init', '-q'], check=True)
    other_repo = tmp_path / 'pkm'
    other_repo.mkdir()
    subprocess.run(['git', '-C', str(other_repo), 'init', '-q'], check=True)
    skill = write_skill(other_repo, valid_frontmatter())
    scripts = skill / 'scripts'
    scripts.mkdir()
    script = scripts / 'run.py'
    script.write_text("#!/usr/bin/env python3\nprint('working')\n")
    assert subprocess.run([sys.executable, str(script)], capture_output=True, text=True, check=True).stdout.strip() == 'working'
    installed = tmp_path / 'installed'
    installed.symlink_to(skill, target_is_directory=True)
    contract = tmp_path / 'delivery.json'
    contract.write_text(json.dumps({
        'schema_version': 1, 'user_outcome': 'Deliver from expected-owner',
        'scope': 'marketplace', 'source_repo': str(source_repo),
        'skill_name': 'target-skill', 'installed_path': str(installed),
    }))
    quality_only = run_reviewer(skill, '--json')
    assert quality_only.returncode == 0, quality_only.stdout + quality_only.stderr
    result = run_reviewer(skill, '--delivery-contract', str(contract), '--json')
    report = json.loads(result.stdout)
    assert result.returncode == 2, report
    assert report['delivery_review']['status'] == 'invalid'
    assert report['delivery_review']['runtime']['status'] == 'unknown'


def test_legacy_run_review_api_keeps_two_item_return(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('reviewer_legacy_api', REVIEWER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    skill = write_skill(tmp_path, valid_frontmatter())
    issues, name = module.run_review(skill)
    assert name == 'target-skill'
    assert not any(issue[0] in ('error', 'warning') for issue in issues)
