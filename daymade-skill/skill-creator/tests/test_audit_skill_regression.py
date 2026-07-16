import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.audit_skill_regression import (
    build_report,
    create_baseline_snapshot,
    create_regression_marker,
    main,
    requires_regression_review,
    tree_hash,
    validate_regression_marker,
    verify_review,
)


def _make_skill(root: Path, body: str, description: str = "Audits a fixture workflow.") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(
        "---\n"
        "name: fixture-skill\n"
        f"description: {description}\n"
        "---\n\n"
        "# Fixture Skill\n\n"
        f"{body.strip()}\n",
        encoding="utf-8",
    )
    return root


def _write_review(path: Path, report: dict) -> Path:
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


def _candidate_texts(report: dict) -> list[str]:
    return [candidate["text"] for candidate in report["candidates"]]


def test_exact_guidance_move_is_auto_preserved(tmp_path):
    before = _make_skill(
        tmp_path / "before",
        "- Verify the signed-in unauthorized branch with a genuinely role-less account.",
    )
    after = _make_skill(
        tmp_path / "after",
        "See references/authorization.md for the authorization contract.",
    )
    (after / "references").mkdir()
    (after / "references" / "authorization.md").write_text(
        "# Authorization\n\n"
        "- Verify the signed-in unauthorized branch with a genuinely role-less account.\n",
        encoding="utf-8",
    )

    report = build_report(before, after)

    assert not any("role-less" in text for text in _candidate_texts(report))
    assert any(
        item.get("kind") == "guidance" and "role-less" in item.get("text", "")
        for item in report["auto_preserved"]
    )


def test_paraphrase_stays_unclassified_for_semantic_review(tmp_path):
    before = _make_skill(
        tmp_path / "before",
        "- A signed-in user with no role, tenant, membership, or permission must see a plain no-access state.",
    )
    after = _make_skill(
        tmp_path / "after",
        "- Check the permission-denied branch.",
    )

    report = build_report(before, after)

    candidate = next(item for item in report["candidates"] if "no role" in item["text"])
    assert candidate["disposition"] == "unclassified"


def test_markdown_review_keeps_each_contract_bullet_independent(tmp_path):
    before = _make_skill(
        tmp_path / "before",
        "\n".join(f"- Preserve runtime contract {index} with its recovery path." for index in range(30)),
    )
    after = _make_skill(tmp_path / "after", "- Inspect the current workflow.")

    report = build_report(before, after)
    guidance = [item for item in report["candidates"] if item["kind"] == "guidance"]

    assert len(guidance) == 30
    assert any("runtime contract 0" in item["text"] for item in guidance)
    assert any("runtime contract 29" in item["text"] for item in guidance)


def test_removing_one_clause_still_surfaces_the_changed_section(tmp_path):
    before = _make_skill(
        tmp_path / "before",
        "- Keep the normal path.\n- Verify a signed-in role-less account sees no privileged shell.",
    )
    after = _make_skill(tmp_path / "after", "- Keep the normal path.")

    report = build_report(before, after)

    assert any("role-less" in item["text"] for item in report["candidates"])


def test_known_visual_contract_deletions_all_surface(tmp_path):
    before = _make_skill(
        tmp_path / "before",
        "\n".join([
            "- Test HTML slides at the exact intended projection size.",
            "- Verify a signed-in role-less user sees no privileged shell.",
            "- Charts must show units, source, time range, empty state, and error state.",
            "- Provider model runtime labels must match the selected path.",
        ]),
    )
    after = _make_skill(tmp_path / "after", "- Inspect the rendered page.")

    report = build_report(before, after)
    texts = "\n".join(_candidate_texts(report))

    assert "projection size" in texts
    assert "role-less" in texts
    assert "units, source, time range" in texts
    assert "Provider model runtime" in texts


def test_runtime_contract_only_in_evals_is_still_candidate(tmp_path):
    before = _make_skill(
        tmp_path / "before",
        "- Test HTML slides at the exact intended projection size.",
    )
    after = _make_skill(tmp_path / "after", "- Inspect the rendered page.")
    (after / "evals").mkdir()
    (after / "evals" / "evals.json").write_text(
        json.dumps({
            "evals": [{
                "id": 1,
                "name": "projection",
                "prompt": "Test HTML slides at the exact intended projection size.",
                "expectations": [],
            }]
        }),
        encoding="utf-8",
    )

    report = build_report(before, after)
    candidate = next(item for item in report["candidates"] if "projection size" in item["text"])

    assert candidate["scope"] == "runtime"
    assert candidate["only_outside_runtime"] is True


def test_explicit_user_removal_can_be_classified(tmp_path):
    before = _make_skill(tmp_path / "before", "- Keep the legacy export mode available.")
    after = _make_skill(tmp_path / "after", "- Use the current export mode.")
    report = build_report(before, after)
    candidate = next(item for item in report["candidates"] if "legacy export" in item["text"])
    candidate.update({
        "disposition": "removed_by_explicit_user_request",
        "reason": "The user explicitly retired this legacy mode.",
        "user_approval": "Remove the legacy export mode.",
    })
    review = _write_review(tmp_path / "review.json", report)

    ok, errors = verify_review(before, after, review)

    assert ok, errors


def test_review_becomes_stale_when_after_changes(tmp_path):
    before = _make_skill(tmp_path / "before", "- Keep the legacy export mode available.")
    after = _make_skill(tmp_path / "after", "- Use the current export mode.")
    report = build_report(before, after)
    for candidate in report["candidates"]:
        candidate.update({
            "disposition": "removed_by_explicit_user_request",
            "reason": "Fixture intentionally changes the mode.",
            "user_approval": "Retire every old fixture capability.",
        })
    review = _write_review(tmp_path / "review.json", report)
    (after / "SKILL.md").write_text(
        (after / "SKILL.md").read_text(encoding="utf-8") + "\nChanged after review.\n",
        encoding="utf-8",
    )

    ok, errors = verify_review(before, after, review)

    assert not ok
    assert any("after skill changed" in error for error in errors)


def test_preserved_disposition_requires_real_file_and_line_evidence(tmp_path):
    before = _make_skill(tmp_path / "before", "- Keep the legacy export mode available.")
    after = _make_skill(tmp_path / "after", "- Use the current export mode.")
    report = build_report(before, after)
    candidate = next(item for item in report["candidates"] if "legacy export" in item["text"])
    candidate.update({
        "disposition": "preserved_or_moved",
        "reason": "Claimed move.",
        "evidence": [{"path": "references/missing.md", "line": 1}],
    })
    review = _write_review(tmp_path / "review.json", report)

    ok, errors = verify_review(before, after, review)

    assert not ok
    assert any("target does not exist" in error for error in errors)


def test_preserved_evidence_requires_a_quote_near_the_cited_line(tmp_path):
    before = _make_skill(tmp_path / "before", "- Keep the legacy export mode available.")
    after = _make_skill(tmp_path / "after", "- Use the current export mode.")
    report = build_report(before, after)
    candidate = next(item for item in report["candidates"] if "legacy export" in item["text"])
    candidate.update({
        "disposition": "preserved_or_moved",
        "reason": "The current mode owns the migrated behavior.",
        "evidence": [{"path": "SKILL.md", "line": 7, "contains": "text that is not there"}],
    })
    review = _write_review(tmp_path / "review.json", report)

    ok, errors = verify_review(before, after, review)

    assert not ok
    assert any("contains was not found" in error for error in errors)


def test_preserved_evidence_must_relate_to_the_old_candidate(tmp_path):
    before = _make_skill(tmp_path / "before", "- Keep offline recovery available.")
    after = _make_skill(tmp_path / "after", "- Use the online workflow.")
    report = build_report(before, after)
    candidate = next(item for item in report["candidates"] if "offline recovery" in item["text"])
    candidate.update({
        "disposition": "preserved_or_moved",
        "reason": "Claimed preservation.",
        "evidence": [{"path": "SKILL.md", "line": 2, "contains": "name: fixture-skill"}],
    })
    review = _write_review(tmp_path / "review.json", report)

    ok, errors = verify_review(before, after, review)

    assert not ok
    assert any("no meaningful lexical relationship" in error for error in errors)


def test_regression_marker_is_content_bound_and_ignores_itself(tmp_path):
    before = _make_skill(tmp_path / "before", "- Keep the legacy export mode available.")
    after = _make_skill(tmp_path / "after", "- Use the current export mode.")
    report = build_report(before, after)
    for candidate in report["candidates"]:
        candidate.update({
            "disposition": "removed_by_explicit_user_request",
            "reason": "Fixture intentionally changes the mode.",
            "user_approval": "Retire every old fixture capability.",
        })
    review = _write_review(tmp_path / "review.json", report)

    marker = create_regression_marker(after, review)
    first = marker.read_text(encoding="utf-8")
    assert validate_regression_marker(after)[0] is True

    marker.write_text(first + "Reviewer note: still current\n", encoding="utf-8")
    assert validate_regression_marker(after)[0] is True

    marker.write_text(first.replace("Schema version: 3", "Schema version: 1"), encoding="utf-8")
    valid, reason = validate_regression_marker(after)
    assert valid is False
    assert "obsolete schema" in reason

    marker.write_text(
        first.replace("Attestation digest: ", "Attestation digest: 0", 1),
        encoding="utf-8",
    )
    valid, reason = validate_regression_marker(after)
    assert valid is False
    assert "malformed" in reason or "digest is invalid" in reason

    marker.write_text(first, encoding="utf-8")

    (after / "SKILL.md").write_text(
        (after / "SKILL.md").read_text(encoding="utf-8") + "\nNew runtime behavior.\n",
        encoding="utf-8",
    )
    valid, reason = validate_regression_marker(after)
    assert valid is False
    assert "changed since" in reason


def test_trigger_eval_and_expected_output_removals_surface(tmp_path):
    before = _make_skill(tmp_path / "before", "- Inspect the rendered workflow.")
    after = _make_skill(tmp_path / "after", "- Inspect the rendered workflow.")
    (before / "evals").mkdir()
    (before / "evals" / "trigger-evals.json").write_text(
        json.dumps([
            {"query": "Audit this existing landing page.", "should_trigger": True},
        ]),
        encoding="utf-8",
    )
    (before / "evals" / "evals.json").write_text(
        json.dumps({
            "evals": [{
                "id": 1,
                "prompt": "Audit the page.",
                "expected_output": "A blocked result when no rendered page is available.",
                "expected_behavior": ["Does not invent browser evidence"],
            }]
        }),
        encoding="utf-8",
    )

    report = build_report(before, after)
    kinds = {item["kind"] for item in report["candidates"]}
    texts = "\n".join(_candidate_texts(report))

    assert "trigger_expectation" in kinds
    assert "should_trigger=true" in texts
    assert "A blocked result" in texts
    assert "Does not invent browser evidence" in texts


def test_command_and_environment_interface_removals_surface(tmp_path):
    before = _make_skill(
        tmp_path / "before",
        "Use the supported command:\n\n```bash\nFLOW_MODE=strict uv run python -m scripts.audit --format json\n```",
    )
    after = _make_skill(tmp_path / "after", "Use the supported audit flow.")

    report = build_report(before, after)
    pairs = {(item["kind"], item["text"]) for item in report["candidates"]}

    assert ("command", "FLOW_MODE=strict uv run python -m scripts.audit --format json") in pairs
    assert ("env_var", "FLOW_MODE") in pairs
    assert ("cli_flag", "--format") in pairs


def test_same_path_runtime_script_body_change_surfaces(tmp_path):
    before = _make_skill(tmp_path / "before", "Run scripts/export.py for exports.")
    after = _make_skill(tmp_path / "after", "Run scripts/export.py for exports.")
    for skill, body in (
        (before, "def export(kind):\n    if kind == 'json': return '{}'\n    return 'csv'\n"),
        (after, "def export(kind):\n    return 'csv'\n"),
    ):
        (skill / "scripts").mkdir()
        (skill / "scripts" / "export.py").write_text(body, encoding="utf-8")

    report = build_report(before, after)

    assert any(
        item["kind"] == "runtime_file_changed" and "scripts/export.py" in item["text"]
        for item in report["candidates"]
    )


def test_file_fingerprint_alone_cannot_claim_changed_runtime_behavior_is_preserved(tmp_path):
    before = _make_skill(tmp_path / "before", "Run scripts/export.py for exports.")
    after = _make_skill(tmp_path / "after", "Run scripts/export.py for exports.")
    for skill, body in (
        (before, "def export(kind):\n    return kind\n"),
        (after, "def export(kind):\n    return 'csv'\n"),
    ):
        (skill / "scripts").mkdir()
        (skill / "scripts" / "export.py").write_text(body, encoding="utf-8")
    report = build_report(before, after)
    candidate = next(item for item in report["candidates"] if item["kind"] == "runtime_file_changed")
    from scripts.audit_skill_regression import _file_fingerprint
    candidate.update({
        "disposition": "preserved_or_moved",
        "reason": "The changed script is claimed to preserve all prior export behavior.",
        "evidence": [{
            "path": "scripts/export.py",
            "sha256": _file_fingerprint(after / "scripts" / "export.py"),
        }],
    })
    for other in report["candidates"]:
        if other is candidate:
            continue
        other.update({
            "disposition": "removed_by_explicit_user_request",
            "reason": "The fixture explicitly retires this old implementation detail.",
            "user_approval": "Retire the old fixture implementation detail.",
        })
    review = _write_review(tmp_path / "review.json", report)

    ok, errors = verify_review(before, after, review)

    assert not ok
    assert any("fingerprint proves identity, not behavior" in error for error in errors)


def test_contract_moved_to_orphan_reference_is_not_auto_preserved(tmp_path):
    contract = "Verify the signed-in unauthorized branch with a genuinely role-less account."
    before = _make_skill(tmp_path / "before", f"- {contract}")
    after = _make_skill(tmp_path / "after", "Inspect the rendered authorization state.")
    (after / "references").mkdir()
    (after / "references" / "orphan.md").write_text(f"# Orphan\n\n- {contract}\n", encoding="utf-8")

    report = build_report(before, after)

    candidate = next(item for item in report["candidates"] if "role-less" in item["text"])
    assert candidate["scope"] == "runtime"
    assert candidate["only_outside_runtime"] is True


def test_runtime_reachability_follows_imported_python_dependencies(tmp_path):
    before = _make_skill(tmp_path / "before", "Run scripts/entry.py for the workflow.")
    after = _make_skill(tmp_path / "after", "Run scripts/entry.py for the workflow.")
    for skill in (before, after):
        (skill / "scripts").mkdir()
        (skill / "scripts" / "entry.py").write_text(
            "from scripts.runtime_policy import POLICY\nprint(POLICY)\n",
            encoding="utf-8",
        )
    (before / "scripts" / "runtime_policy.py").write_text("POLICY = 'strict'\n", encoding="utf-8")
    (after / "scripts" / "runtime_policy.py").write_text("POLICY = 'updated'\n", encoding="utf-8")

    report = build_report(before, after)

    changed = next(
        item for item in report["candidates"]
        if item["kind"].endswith("file_changed") and "runtime_policy.py" in item["text"]
    )
    assert changed["scope"] == "runtime"


def test_runtime_file_moved_to_tests_is_not_auto_preserved(tmp_path):
    before = _make_skill(tmp_path / "before", "Run scripts/runner.sh for the workflow.")
    after = _make_skill(tmp_path / "after", "Run the workflow.")
    (before / "scripts").mkdir()
    (before / "scripts" / "runner.sh").write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    (after / "tests").mkdir()
    (after / "tests" / "runner.sh").write_text("#!/bin/sh\necho ok\n", encoding="utf-8")

    report = build_report(before, after)

    candidate = next(item for item in report["candidates"] if item["kind"] == "runtime_file")
    assert candidate["only_outside_runtime"] is True
    assert candidate["observed_destinations"] == ["tests/runner.sh"]


def test_nested_dist_file_is_hashed_because_it_would_ship(tmp_path):
    skill = _make_skill(tmp_path / "skill", "Use the bundled runtime asset.")
    target = skill / "assets" / "dist" / "runtime.js"
    target.parent.mkdir(parents=True)
    target.write_text("export const mode = 'one';\n", encoding="utf-8")
    first = tree_hash(skill)

    target.write_text("export const mode = 'two';\n", encoding="utf-8")

    assert tree_hash(skill) != first


def test_tree_hash_binds_executable_mode(tmp_path):
    skill = _make_skill(tmp_path / "skill", "Run scripts/runner.sh.")
    target = skill / "scripts" / "runner.sh"
    target.parent.mkdir()
    target.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    os.chmod(target, 0o644)
    first = tree_hash(skill)

    os.chmod(target, 0o755)

    assert tree_hash(skill) != first


def test_runtime_candidate_cannot_be_blanket_not_reusable(tmp_path):
    before = _make_skill(tmp_path / "before", "- Keep offline recovery available.")
    after = _make_skill(tmp_path / "after", "- Use the online workflow.")
    report = build_report(before, after)
    for candidate in report["candidates"]:
        candidate.update({"disposition": "not_reusable", "reason": "Not reusable."})
    review = _write_review(tmp_path / "review.json", report)

    ok, errors = verify_review(before, after, review)

    assert not ok
    assert any("runtime capability cannot be retired" in error for error in errors)


def test_runtime_boundary_requires_user_approval_and_current_evidence(tmp_path):
    before = _make_skill(tmp_path / "before", "- Keep offline recovery available.")
    after = _make_skill(tmp_path / "after", "- Use the online workflow.")
    report = build_report(before, after)
    for candidate in report["candidates"]:
        candidate.update({
            "disposition": "intentional_boundary",
            "reason": "The old recovery capability is claimed to belong to another skill.",
            "destination": "recovery-skill",
        })
    review = _write_review(tmp_path / "review.json", report)

    ok, errors = verify_review(before, after, review)

    assert not ok
    assert any("requires traceable user_approval" in error for error in errors)
    assert any("requires at least one evidence entry" in error for error in errors)


def test_existing_clean_git_skill_without_marker_still_requires_review(tmp_path):
    repo = tmp_path / "repo"
    skill = _make_skill(repo / "skill", "- Keep offline recovery available.")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "user@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "skill"], check=True)
    tree = subprocess.run(
        ["git", "-C", str(repo), "write-tree"], check=True, capture_output=True, text=True
    ).stdout.strip()
    commit = subprocess.run(
        ["git", "-C", str(repo), "commit-tree", tree, "-m", "baseline"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "symbolic-ref", "HEAD", "refs/heads/master"], check=True)
    subprocess.run(["git", "-C", str(repo), "update-ref", "refs/heads/master", commit], check=True)

    required, reason = requires_regression_review(skill)

    assert required is True
    assert "requires the completed regression review" in reason


def test_non_git_skill_is_unknown_unless_explicitly_new(tmp_path):
    skill = _make_skill(tmp_path / "skill", "- Keep offline recovery available.")

    assert requires_regression_review(skill)[0] is True
    assert requires_regression_review(skill, new_skill=True)[0] is False


def test_create_marker_rejects_unverified_review(tmp_path):
    after = _make_skill(tmp_path / "after", "- Use the online workflow.")
    review = _write_review(tmp_path / "review.json", {})

    with pytest.raises(ValueError, match="before.path"):
        create_regression_marker(after, review)


def test_truncated_forged_marker_is_rejected(tmp_path):
    skill = _make_skill(tmp_path / "skill", "- Keep offline recovery available.")
    (skill / ".skill-regression-reviewed").write_text(
        f"Skill regression review passed\nSchema version: 3\nAfter tree hash: {tree_hash(skill)}\n",
        encoding="utf-8",
    )

    valid, reason = validate_regression_marker(skill)

    assert valid is False
    assert "malformed" in reason


def test_git_ref_baseline_is_resolved_and_verified_against_git_tree(tmp_path):
    repo = tmp_path / "repo"
    skill = _make_skill(repo / "skill", "- Keep offline recovery available.")
    before = tmp_path / "before"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "add", "skill"], check=True)
    tree = subprocess.run(
        ["git", "-C", str(repo), "write-tree"], check=True, capture_output=True, text=True
    ).stdout.strip()
    commit = subprocess.run(
        ["git", "-C", str(repo), "commit-tree", tree, "-m", "baseline"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
    subprocess.run(["git", "-C", str(repo), "update-ref", "refs/heads/main", commit], check=True)
    create_baseline_snapshot(skill, before)
    (skill / "SKILL.md").write_text(
        (skill / "SKILL.md").read_text(encoding="utf-8").replace(
            "Keep offline recovery available", "Use the online workflow"
        ),
        encoding="utf-8",
    )

    report = build_report(before, skill, baseline_origin="git-ref:HEAD")

    assert report["before"]["provenance"]["origin"] == f"git-ref:{commit}"
    assert report["before"]["provenance"]["resolved_commit"] == commit
    assert any("offline recovery" in item["text"] for item in report["candidates"])


def test_git_ref_baseline_rejects_a_copy_made_after_editing(tmp_path):
    repo = tmp_path / "repo"
    skill = _make_skill(repo / "skill", "- Keep offline recovery available.")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "add", "skill"], check=True)
    tree = subprocess.run(
        ["git", "-C", str(repo), "write-tree"], check=True, capture_output=True, text=True
    ).stdout.strip()
    commit = subprocess.run(
        ["git", "-C", str(repo), "commit-tree", tree, "-m", "baseline"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
    subprocess.run(["git", "-C", str(repo), "update-ref", "refs/heads/main", commit], check=True)
    (skill / "SKILL.md").write_text(
        (skill / "SKILL.md").read_text(encoding="utf-8").replace(
            "Keep offline recovery available", "Use the online workflow"
        ),
        encoding="utf-8",
    )
    copied_after_edit = tmp_path / "copied-after-edit"
    create_baseline_snapshot(skill, copied_after_edit)

    with pytest.raises(ValueError, match="does not match HEAD"):
        build_report(copied_after_edit, skill, baseline_origin="git-ref:HEAD")


def test_pre_edit_snapshot_requires_tool_created_provenance(tmp_path):
    skill = _make_skill(tmp_path / "skill", "- Keep offline recovery available.")
    raw_copy = _make_skill(tmp_path / "raw-copy", "- Keep offline recovery available.")

    with pytest.raises(ValueError, match="provenance manifest"):
        build_report(raw_copy, skill, baseline_origin="pre-edit-snapshot")

    verified_copy = tmp_path / "verified-copy"
    manifest_path = create_baseline_snapshot(skill, verified_copy)
    assert str(skill.resolve()) not in manifest_path.read_text(encoding="utf-8")
    (skill / "SKILL.md").write_text(
        (skill / "SKILL.md").read_text(encoding="utf-8").replace(
            "Keep offline recovery available", "Use the online workflow"
        ),
        encoding="utf-8",
    )
    report = build_report(verified_copy, skill, baseline_origin="pre-edit-snapshot")
    assert report["before"]["provenance"]["origin"] == "pre-edit-snapshot"


def test_compare_cli_rejects_identical_current_to_current_baseline(tmp_path, capsys):
    skill = _make_skill(tmp_path / "skill", "- Keep offline recovery available.")
    before = tmp_path / "before"
    create_baseline_snapshot(skill, before)

    exit_code = main([
        "compare",
        "--before", str(before),
        "--after", str(skill),
        "--output", str(tmp_path / "review.json"),
        "--baseline-origin", "pre-edit-snapshot",
    ])

    assert exit_code == 2
    assert "before and after are identical" in capsys.readouterr().err


def test_valid_marker_is_informational_and_cannot_bypass_packaging_review(tmp_path):
    repo = tmp_path / "repo"
    skill = _make_skill(repo / "skill", "- Keep offline recovery available.")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "add", "skill"], check=True)
    tree = subprocess.run(
        ["git", "-C", str(repo), "write-tree"], check=True, capture_output=True, text=True
    ).stdout.strip()
    commit = subprocess.run(
        ["git", "-C", str(repo), "commit-tree", tree, "-m", "baseline"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
    subprocess.run(["git", "-C", str(repo), "update-ref", "refs/heads/main", commit], check=True)
    before = tmp_path / "before"
    create_baseline_snapshot(skill, before)
    (skill / "SKILL.md").write_text(
        (skill / "SKILL.md").read_text(encoding="utf-8").replace(
            "Keep offline recovery available", "Use the online workflow"
        ),
        encoding="utf-8",
    )
    report = build_report(before, skill, baseline_origin="git-ref:HEAD")
    for candidate in report["candidates"]:
        candidate.update({
            "disposition": "removed_by_explicit_user_request",
            "reason": "Fixture explicitly retires the old mode.",
            "user_approval": "Retire the old offline recovery fixture.",
        })
    review = _write_review(tmp_path / "review.json", report)
    create_regression_marker(skill, review)

    required, reason = requires_regression_review(skill)

    assert required is True
    assert "informational only" in reason


def test_classify_fills_dispositions_and_verify_passes(tmp_path):
    before = _make_skill(
        tmp_path / "before",
        "- Verify the signed-in unauthorized branch with a genuinely role-less account.",
    )
    after = _make_skill(
        tmp_path / "after",
        "- Reworded: verify the signed-in unauthorized branch using a genuinely role-less account.",
    )
    report = build_report(before, after)
    assert report["candidates"], "fixture must produce at least one candidate"
    review_path = _write_review(tmp_path / "review.json", report)
    map_path = tmp_path / "map.json"
    map_path.write_text(
        json.dumps(
            {
                "0": {
                    "destination": "SKILL.md",
                    "needle": "verify the signed-in unauthorized branch using a genuinely role-less account",
                    "reason": "guidance sentence reworded in place; the unauthorized-branch check survives in SKILL.md",
                }
            }
        ),
        encoding="utf-8",
    )
    from scripts.audit_skill_regression import classify_review

    classified, unclassified = classify_review(review_path, after, map_path, "tester")

    assert classified == 1
    assert unclassified == []
    ok, errors = verify_review(before, after, review_path)
    assert ok, errors


def test_classify_fail_fast_writes_nothing_on_bad_map(tmp_path):
    before = _make_skill(
        tmp_path / "before",
        "- Verify the signed-in unauthorized branch with a genuinely role-less account.",
    )
    after = _make_skill(
        tmp_path / "after",
        "- Completely different replacement guidance for the fixture skill body.",
    )
    report = build_report(before, after)
    assert report["candidates"]
    review_path = _write_review(tmp_path / "review.json", report)
    original = review_path.read_text(encoding="utf-8")
    map_path = tmp_path / "map.json"
    map_path.write_text(
        json.dumps(
            {
                "0": {
                    "destination": "SKILL.md",
                    "needle": "this quote exists nowhere in the destination file",
                    "reason": "long enough reason but the needle cannot be located anywhere",
                },
                "99": {
                    "destination": "SKILL.md",
                    "needle": "irrelevant",
                    "reason": "long enough reason for a key that matches no candidate",
                },
            }
        ),
        encoding="utf-8",
    )
    from scripts.audit_skill_regression import classify_review

    with pytest.raises(ValueError) as excinfo:
        classify_review(review_path, after, map_path, "tester")

    message = str(excinfo.value)
    assert "needle not found" in message
    assert "matches no candidate" in message
    assert review_path.read_text(encoding="utf-8") == original


def test_classify_rejects_short_reason(tmp_path):
    before = _make_skill(
        tmp_path / "before",
        "- Verify the signed-in unauthorized branch with a genuinely role-less account.",
    )
    after = _make_skill(
        tmp_path / "after",
        "- Reworded: verify the signed-in unauthorized branch using a genuinely role-less account.",
    )
    report = build_report(before, after)
    review_path = _write_review(tmp_path / "review.json", report)
    map_path = tmp_path / "map.json"
    map_path.write_text(
        json.dumps(
            {
                "0": {
                    "destination": "SKILL.md",
                    "needle": "genuinely role-less account",
                    "reason": "too short",
                }
            }
        ),
        encoding="utf-8",
    )
    from scripts.audit_skill_regression import classify_review

    with pytest.raises(ValueError, match="reason needs >= 20"):
        classify_review(review_path, after, map_path, "tester")
