import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_project_skill_roots.py"
ROUTER_MARKER = "# Compatibility router — no business rules live here"


def skill_text(name: str, body: str = "# Rules\n\nUse the canonical rules.\n") -> str:
    return (
        "---\n"
        f"name: {name}\n"
        "description: Test fixture Skill.\n"
        "---\n\n"
        f"{body}"
    )


def router_text(name: str, canonical_skill_file: str) -> str:
    return skill_text(
        name,
        (
            f"{ROUTER_MARKER}\n\n"
            f"The single source of truth is `{canonical_skill_file}`.\n\n"
            f"1. Read `{canonical_skill_file}` completely.\n"
            "2. Follow it without copying business rules into this file.\n\n"
            "If the canonical file is missing or unreadable, fail visibly.\n"
        ),
    )


class ProjectSkillRootsAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tinkle_skill_roots_")
        self.project = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_skill(
        self,
        root: str,
        directory_name: str,
        name: str,
        body: str = "# Rules\n\nUse the canonical rules.\n",
    ) -> Path:
        bundle = self.project / root / directory_name
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / "SKILL.md").write_text(skill_text(name, body), encoding="utf-8")
        return bundle

    def run_audit(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.project), "--json"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            self.fail(
                f"audit did not emit JSON (exit={completed.returncode}): "
                f"stdout={completed.stdout!r} stderr={completed.stderr!r}; {exc}"
            )
        return completed, payload

    def finding(self, payload, name):
        return next(item for item in payload["findings"] if item["name"] == name)

    def test_refuses_silent_empty_audit_when_neither_root_exists(self):
        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["result"], "invalid")
        self.assertIn("neither .claude/skills nor .agents/skills exists", payload["errors"][0]["message"])

    def test_present_but_empty_roots_are_invalid_not_clean(self):
        (self.project / ".claude/skills").mkdir(parents=True)
        (self.project / ".agents/skills").mkdir(parents=True)

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["result"], "invalid")
        self.assertIn("contain no auditable SKILL.md bundles", payload["errors"][0]["message"])

    def test_single_root_skill_is_informational_and_clean(self):
        self.write_skill(".claude/skills", "alpha", "alpha")

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["result"], "clean")
        self.assertEqual(self.finding(payload, "alpha")["status"], "single_root")
        self.assertEqual(payload["roots"]["missing"], [".agents/skills"])

    def test_identical_same_name_copies_are_reported_but_do_not_fail(self):
        self.write_skill(".claude/skills", "alpha-source", "alpha")
        self.write_skill(".agents/skills", "alpha-copy", "alpha")

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["result"], "clean")
        finding = self.finding(payload, "alpha")
        self.assertEqual(finding["status"], "identical_copy")
        self.assertEqual(len(set(finding["bundle_sha256"].values())), 1)

    def test_router_marker_quoted_in_full_skill_prose_is_not_a_router(self):
        body = (
            "# Rules\n\n"
            "This full skill documents the phrase "
            "`# Compatibility router — no business rules live here` without being a router.\n"
        )
        self.write_skill(".claude/skills", "alpha-source", "alpha", body)
        self.write_skill(".agents/skills", "alpha-copy", "alpha", body)

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(self.finding(payload, "alpha")["status"], "identical_copy")

    def test_divergent_same_name_full_copies_fail_with_both_hashes(self):
        self.write_skill(".claude/skills", "alpha", "alpha", "# Rules\n\nLeft.\n")
        self.write_skill(".agents/skills", "alpha", "alpha", "# Rules\n\nRight.\n")

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["result"], "drift")
        finding = self.finding(payload, "alpha")
        self.assertEqual(finding["status"], "drift")
        self.assertEqual(len(set(finding["bundle_sha256"].values())), 2)

    def test_explicit_canonical_router_contract_passes(self):
        self.write_skill(".claude/skills", "alpha", "alpha", "# Canonical\n\nAll rules.\n")
        router_bundle = self.project / ".agents/skills/alpha"
        router_bundle.mkdir(parents=True)
        (router_bundle / "SKILL.md").write_text(
            router_text("alpha", ".claude/skills/alpha/SKILL.md"), encoding="utf-8"
        )

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 0)
        finding = self.finding(payload, "alpha")
        self.assertEqual(finding["status"], "canonical_router")
        self.assertEqual(finding["canonical"], ".claude/skills/alpha")
        self.assertEqual(finding["router"], ".agents/skills/alpha")

    def test_router_paths_support_directory_names_independent_of_frontmatter_name(self):
        self.write_skill(
            ".claude/skills", "alpha source", "alpha", "# Canonical\n\nAll rules.\n"
        )
        router_bundle = self.project / ".agents/skills/alpha 路由"
        router_bundle.mkdir(parents=True)
        (router_bundle / "SKILL.md").write_text(
            router_text("alpha", ".claude/skills/alpha source/SKILL.md"),
            encoding="utf-8",
        )

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 0)
        finding = self.finding(payload, "alpha")
        self.assertEqual(finding["status"], "canonical_router")
        self.assertEqual(finding["canonical"], ".claude/skills/alpha source")
        self.assertEqual(finding["router"], ".agents/skills/alpha 路由")

    def test_router_marker_with_extra_business_file_is_invalid(self):
        self.write_skill(".claude/skills", "alpha", "alpha")
        router_bundle = self.project / ".agents/skills/alpha"
        router_bundle.mkdir(parents=True)
        (router_bundle / "SKILL.md").write_text(
            router_text("alpha", ".claude/skills/alpha/SKILL.md"), encoding="utf-8"
        )
        (router_bundle / "rules.md").write_text("copied rule", encoding="utf-8")

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["result"], "invalid")
        self.assertEqual(self.finding(payload, "alpha")["status"], "invalid")
        self.assertIn("may contain only SKILL.md", payload["errors"][0]["message"])

    def test_router_marker_pointing_to_another_skill_is_invalid(self):
        self.write_skill(".claude/skills", "alpha", "alpha")
        router_bundle = self.project / ".agents/skills/alpha"
        router_bundle.mkdir(parents=True)
        (router_bundle / "SKILL.md").write_text(
            router_text("alpha", ".claude/skills/beta/SKILL.md"), encoding="utf-8"
        )

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 2)
        self.assertIn("must reference exactly its paired canonical file", payload["errors"][0]["message"])

    def test_two_routers_cannot_form_a_cycle(self):
        left_bundle = self.project / ".claude/skills/alpha"
        right_bundle = self.project / ".agents/skills/alpha"
        left_bundle.mkdir(parents=True)
        right_bundle.mkdir(parents=True)
        (left_bundle / "SKILL.md").write_text(
            router_text("alpha", ".agents/skills/alpha/SKILL.md"), encoding="utf-8"
        )
        (right_bundle / "SKILL.md").write_text(
            router_text("alpha", ".claude/skills/alpha/SKILL.md"), encoding="utf-8"
        )

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 2)
        self.assertIn("neither is a canonical source", payload["errors"][0]["message"])

    def test_duplicate_frontmatter_name_within_one_root_is_invalid(self):
        self.write_skill(".claude/skills", "alpha-one", "alpha")
        self.write_skill(".claude/skills", "alpha-two", "alpha")

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 2)
        self.assertIn("duplicate frontmatter name", payload["errors"][0]["message"])

    def test_malformed_frontmatter_name_is_invalid_not_silently_skipped(self):
        bundle = self.project / ".claude/skills/alpha"
        bundle.mkdir(parents=True)
        (bundle / "SKILL.md").write_text(
            "---\ndescription: Missing name.\n---\n\n# Alpha\n", encoding="utf-8"
        )

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["result"], "invalid")
        self.assertIn("expected exactly one", payload["errors"][0]["message"])

    def test_local_status_files_do_not_create_false_drift(self):
        left = self.write_skill(".claude/skills", "alpha", "alpha")
        right = self.write_skill(".agents/skills", "alpha", "alpha")
        (left / ".security-scan-passed").write_text("left", encoding="utf-8")
        (right / ".skill-regression-reviewed").write_text("right", encoding="utf-8")

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(self.finding(payload, "alpha")["status"], "identical_copy")

    @unittest.skipIf(os.name == "nt", "executable bits are not portable on Windows")
    def test_executable_bit_difference_is_real_drift(self):
        left = self.write_skill(".claude/skills", "alpha", "alpha")
        right = self.write_skill(".agents/skills", "alpha", "alpha")
        (left / "scripts").mkdir()
        (right / "scripts").mkdir()
        left_script = left / "scripts/run.py"
        right_script = right / "scripts/run.py"
        left_script.write_text("print('ok')\n", encoding="utf-8")
        right_script.write_text("print('ok')\n", encoding="utf-8")
        left_script.chmod(0o755)
        right_script.chmod(0o644)

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(self.finding(payload, "alpha")["status"], "drift")

    @unittest.skipIf(os.name == "nt", "symlink creation requires privileges on Windows")
    def test_symlinked_second_root_reports_shared_target(self):
        canonical = self.write_skill(".claude/skills", "alpha", "alpha")
        agent_root = self.project / ".agents/skills"
        agent_root.mkdir(parents=True)
        (agent_root / "alpha").symlink_to(canonical, target_is_directory=True)

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(self.finding(payload, "alpha")["status"], "shared_target")

    @unittest.skipIf(os.name == "nt", "symlink creation requires privileges on Windows")
    def test_shared_skill_file_without_extra_material_reports_shared_target(self):
        canonical = self.write_skill(".claude/skills", "alpha", "alpha")
        agent_bundle = self.project / ".agents/skills/alpha"
        agent_bundle.mkdir(parents=True)
        (agent_bundle / "SKILL.md").symlink_to(canonical / "SKILL.md")

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(self.finding(payload, "alpha")["status"], "shared_target")

    @unittest.skipIf(os.name == "nt", "symlink creation requires privileges on Windows")
    def test_shared_skill_file_with_extra_business_file_is_drift(self):
        canonical = self.write_skill(".claude/skills", "alpha", "alpha")
        agent_bundle = self.project / ".agents/skills/alpha"
        agent_bundle.mkdir(parents=True)
        (agent_bundle / "SKILL.md").symlink_to(canonical / "SKILL.md")
        (agent_bundle / "rules.md").write_text("hidden rule\n", encoding="utf-8")

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["result"], "drift")
        self.assertEqual(self.finding(payload, "alpha")["status"], "drift")

    @unittest.skipIf(os.name == "nt", "symlink creation requires privileges on Windows")
    def test_shared_router_target_is_invalid(self):
        router = self.project / ".claude/skills/alpha"
        router.mkdir(parents=True)
        (router / "SKILL.md").write_text(
            router_text("alpha", ".agents/skills/alpha/SKILL.md"), encoding="utf-8"
        )
        agent_root = self.project / ".agents/skills"
        agent_root.mkdir(parents=True)
        (agent_root / "alpha").symlink_to(router, target_is_directory=True)

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["result"], "invalid")
        self.assertIn("shared target cannot itself be a compatibility router", payload["errors"][0]["message"])

    @unittest.skipIf(os.name == "nt", "symlink creation requires privileges on Windows")
    def test_identical_broken_nested_symlinks_are_invalid(self):
        left = self.write_skill(".claude/skills", "alpha", "alpha")
        right = self.write_skill(".agents/skills", "alpha", "alpha")
        (left / "missing.md").symlink_to("not-there.md")
        (right / "missing.md").symlink_to("not-there.md")

        completed, payload = self.run_audit()

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["result"], "invalid")
        self.assertEqual(self.finding(payload, "alpha")["status"], "invalid")
        self.assertIn("broken bundle symlink", payload["errors"][0]["message"])

    def test_human_output_names_result_and_each_status(self):
        self.write_skill(".claude/skills", "alpha", "alpha")
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.project)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Result: CLEAN", completed.stdout)
        self.assertIn("- single_root: alpha", completed.stdout)


if __name__ == "__main__":
    unittest.main()
