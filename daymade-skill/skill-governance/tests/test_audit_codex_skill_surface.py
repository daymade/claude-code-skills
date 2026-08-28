import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "audit_codex_skill_surface.py"
)


def skill_text(name: str, description: str) -> str:
    return (
        "---\n"
        f"name: {name}\n"
        "description: >-\n"
        f"  {description}\n"
        "---\n\n"
        f"# {name}\n"
    )


class CodexSkillSurfaceAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="skill_surface_audit_")
        self.root = Path(self.temporary.name)
        self.skills_root = self.root / "skills"
        self.skills_root.mkdir()
        self.config = self.root / "config.toml"
        self.config.write_text("", encoding="utf-8")
        self.manifest = self.root / "activation.json"
        self.manifest.write_text(
            json.dumps({"schema_version": 1, "active_skills": []}),
            encoding="utf-8",
        )
        self.inventory = self.root / "skills.json"
        self.skill_metadata: dict[Path, tuple[str, str]] = {}

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_skill(
        self,
        directory: str,
        name: str,
        description: str,
        *,
        content: str | None = None,
    ) -> Path:
        bundle = self.skills_root / directory
        bundle.mkdir(parents=True)
        skill_file = bundle / "SKILL.md"
        skill_file.write_text(
            content if content is not None else skill_text(name, description),
            encoding="utf-8",
        )
        self.skill_metadata[skill_file.resolve()] = (name, description)
        return skill_file

    def inventory_item(
        self,
        skill_file: Path,
        *,
        name: str | None = None,
        description: str | None = None,
        enabled: bool = True,
        scope: str = "user",
    ) -> dict:
        source_name, source_description = self.skill_metadata[skill_file.resolve()]
        return {
            "name": name or source_name,
            "description": description or source_description,
            "path": str(skill_file.resolve()),
            "enabled": enabled,
            "scope": scope,
        }

    def write_inventory(
        self,
        skills: list[dict],
        *,
        errors: list[dict] | None = None,
    ) -> None:
        self.inventory.write_text(
            json.dumps(
                {
                    "data": [
                        {
                            "cwd": str(self.root),
                            "skills": skills,
                            "errors": errors or [],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    def write_prompt(
        self,
        entries: list[tuple[str, str, Path]],
        *,
        extra_inventory: list[dict] | None = None,
        inventory_errors: list[dict] | None = None,
    ) -> Path:
        lines = [
            "<skills_instructions>",
            "## Skills",
            "### Skill roots",
            f"- `r0` = `{self.skills_root}`",
            "### Available skills",
        ]
        inventory: list[dict] = []
        for display_name, description, skill_file in entries:
            locator = f"r0/{skill_file.relative_to(self.skills_root).as_posix()}"
            lines.append(f"- {display_name}: {description} (file: {locator})")
            inventory.append(self.inventory_item(skill_file))
        inventory.extend(extra_inventory or [])
        inventory = list({item["path"]: item for item in inventory}.values())
        self.write_inventory(inventory, errors=inventory_errors)
        lines.append("</skills_instructions>")
        prompt = self.root / "prompt.json"
        prompt.write_text(
            json.dumps([{"content": [{"text": "\n".join(lines)}]}]),
            encoding="utf-8",
        )
        return prompt

    def run_audit(
        self,
        prompt: Path,
        *extra: str,
        activation_manifest: Path | None = None,
        manifest_equals: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        manifest = self.manifest if activation_manifest is None else activation_manifest
        args = [
            sys.executable,
            str(SCRIPT),
            "--prompt-json",
            str(prompt),
            "--skills-json",
            str(self.inventory),
            "--config",
            str(self.config),
        ]
        if manifest_equals:
            args.append(f"--activation-manifest={manifest}")
        else:
            args.extend(["--activation-manifest", str(manifest)])
        args.extend(
            [
                "--agents-root",
                str(self.skills_root),
                "--cwd",
                str(self.root),
                "--json",
                *extra,
            ]
        )
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            self.fail(
                f"audit emitted invalid JSON exit={completed.returncode}: "
                f"stdout={completed.stdout!r} stderr={completed.stderr!r}; {exc}"
            )
        return completed, payload

    def test_clean_surface_accepts_namespaced_display_name(self) -> None:
        first = self.write_skill("alpha", "alpha", "Runs alpha workflows.")
        second = self.write_skill("site", "site-building", "Builds sites.")
        prompt = self.write_prompt(
            [
                ("alpha", "Runs alpha workflows.", first),
                ("sites:site-building", "Builds sites.", second),
            ]
        )

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["status"], "clean")
        self.assertEqual(payload["counts"]["visible"], 2)
        self.assertEqual(payload["findings"]["duplicate_display_names"], [])

    def test_catalog_uses_codex_parsed_yaml_metadata(self) -> None:
        cases = [
            (
                "inline-comment",
                "Runs alpha.",
                "---\nname: alpha\ndescription: Runs alpha. # note\n---\n",
            ),
            (
                "single-quote",
                "It's a Skill.",
                "---\nname: 'alpha'\ndescription: 'It''s a Skill.'\n---\n",
            ),
            (
                "continued-plain",
                "Runs alpha across continued plain lines.",
                "---\nname: alpha\ndescription: Runs alpha across\n  continued plain lines.\n---\n",
            ),
            (
                "literal-block",
                "Runs alpha. Verifies beta.",
                "---\nname: alpha\ndescription: |-\n  Runs alpha.\n  Verifies beta.\n---\n",
            ),
        ]
        for index, (label, description, content) in enumerate(cases):
            with self.subTest(label=label):
                skill_file = self.write_skill(
                    f"alpha-{index}", "alpha", description, content=content
                )
                prompt = self.write_prompt([("alpha", description, skill_file)])
                completed, payload = self.run_audit(prompt)
                self.assertEqual(completed.returncode, 0)
                self.assertEqual(payload["counts"]["full_descriptions"], 1)

    def test_codex_yaml_scan_error_is_invalid_evidence(self) -> None:
        skill_file = self.write_skill("alpha", "alpha", "Runs alpha workflows.")
        prompt = self.write_prompt(
            [("alpha", "Runs alpha workflows.", skill_file)],
            inventory_errors=[
                {"path": str(skill_file), "message": "invalid YAML frontmatter"}
            ],
        )

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["status"], "invalid")

    def test_truncated_description_is_catalog_pressure(self) -> None:
        skill_file = self.write_skill(
            "alpha", "alpha", "Runs alpha workflows with recovery and verification."
        )
        prompt = self.write_prompt([("alpha", "Runs alpha workflows", skill_file)])

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["status"], "pressure")
        self.assertEqual(payload["counts"]["truncated_descriptions"], 1)

    def test_non_prefix_description_mismatch_is_not_called_truncation(self) -> None:
        skill_file = self.write_skill("alpha", "alpha", "Runs alpha workflows.")
        prompt = self.write_prompt([("alpha", "Does something else.", skill_file)])

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["counts"]["description_mismatches"], 1)
        self.assertEqual(payload["counts"]["truncated_descriptions"], 0)

    def test_duplicate_frontmatter_names_from_distinct_paths_are_reported(self) -> None:
        first = self.write_skill("one", "alpha", "Runs alpha workflows.")
        second = self.write_skill("two", "alpha", "Runs another alpha workflow.")
        prompt = self.write_prompt(
            [
                ("plugin-one:alpha", "Runs alpha workflows.", first),
                ("plugin-two:alpha", "Runs another alpha workflow.", second),
            ]
        )

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(len(payload["findings"]["duplicate_frontmatter_names"]), 1)

    def test_two_visible_aliases_of_one_source_are_catalog_pressure(self) -> None:
        source = self.write_skill("source", "alpha", "Runs alpha workflows.")
        first_bundle = self.skills_root / "first"
        second_bundle = self.skills_root / "second"
        first_bundle.symlink_to(source.parent, target_is_directory=True)
        second_bundle.symlink_to(source.parent, target_is_directory=True)
        prompt = self.write_prompt(
            [
                ("one:alpha", "Runs alpha workflows.", first_bundle / "SKILL.md"),
                ("two:alpha", "Runs alpha workflows.", second_bundle / "SKILL.md"),
            ]
        )

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(len(payload["findings"]["duplicate_source_entries"]), 1)

    def test_hidden_exact_path_can_share_source_with_visible_alias(self) -> None:
        source = self.write_skill("source", "alpha", "Runs alpha workflows.")
        visible_bundle = self.skills_root / "visible-alpha"
        visible_bundle.symlink_to(source.parent, target_is_directory=True)
        visible_skill = visible_bundle / "SKILL.md"
        self.config.write_text(
            textwrap.dedent(
                f"""
                [[skills.config]]
                path = {json.dumps(str(source))}
                enabled = false
                """
            ),
            encoding="utf-8",
        )
        prompt = self.write_prompt([("alpha", "Runs alpha workflows.", visible_skill)])

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["findings"]["disabled_but_visible"], [])

    def test_disabled_exact_discovery_path_still_visible_is_drift(self) -> None:
        skill_file = self.write_skill("alpha", "alpha", "Runs alpha workflows.")
        self.config.write_text(
            textwrap.dedent(
                f"""
                [[skills.config]]
                path = {json.dumps(str(skill_file))}
                enabled = false
                """
            ),
            encoding="utf-8",
        )
        prompt = self.write_prompt([("alpha", "Runs alpha workflows.", skill_file)])

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["findings"]["disabled_but_visible"], [str(skill_file)])

    def test_stale_disabled_path_is_pressure(self) -> None:
        skill_file = self.write_skill("alpha", "alpha", "Runs alpha workflows.")
        missing = self.skills_root / "missing" / "SKILL.md"
        self.config.write_text(
            textwrap.dedent(
                f"""
                [[skills.config]]
                path = {json.dumps(str(missing))}
                enabled = false
                """
            ),
            encoding="utf-8",
        )
        prompt = self.write_prompt([("alpha", "Runs alpha workflows.", skill_file)])

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["findings"]["stale_disabled_paths"], [str(missing)])

    def test_broken_model_visible_locator_is_invalid(self) -> None:
        source = self.write_skill("source", "alpha", "Runs alpha workflows.")
        broken_bundle = self.skills_root / "broken"
        broken_bundle.symlink_to(self.skills_root / "gone", target_is_directory=True)
        broken_skill = broken_bundle / "SKILL.md"
        prompt = self.write_prompt([("alpha", "Runs alpha workflows.", source)])
        prompt_text = json.loads(prompt.read_text())[0]["content"][0]["text"]
        prompt_text = prompt_text.replace("r0/source/SKILL.md", "r0/broken/SKILL.md")
        prompt.write_text(
            json.dumps([{"content": [{"text": prompt_text}]}]), encoding="utf-8"
        )
        self.write_inventory(
            [
                {
                    "name": "alpha",
                    "description": "Runs alpha workflows.",
                    "path": str(broken_skill),
                    "enabled": True,
                    "scope": "user",
                }
            ]
        )

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["status"], "invalid")

    def test_active_manifest_requires_the_direct_user_entry_to_be_visible(self) -> None:
        skill_file = self.write_skill("alpha", "alpha", "Runs alpha workflows.")
        self.manifest.write_text(
            json.dumps({"schema_version": 1, "active_skills": ["alpha"]}),
            encoding="utf-8",
        )
        prompt = self.write_prompt(
            [("plugin:alpha", "Runs alpha workflows.", skill_file)]
        )

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["findings"]["active_missing_visible"], ["alpha"])

    def test_broken_activation_link_is_pressure(self) -> None:
        beta = self.write_skill("beta", "beta", "Runs beta workflows.")
        broken = self.skills_root / "alpha"
        broken.symlink_to(self.skills_root / "gone", target_is_directory=True)
        self.manifest.write_text(
            json.dumps({"schema_version": 1, "active_skills": ["alpha"]}),
            encoding="utf-8",
        )
        prompt = self.write_prompt([("beta", "Runs beta workflows.", beta)])

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["findings"]["active_missing_links"], ["alpha"])

    def test_wrong_direct_activation_identity_is_pressure(self) -> None:
        skill_file = self.write_skill("alpha", "other", "Runs other workflows.")
        self.manifest.write_text(
            json.dumps({"schema_version": 1, "active_skills": ["alpha"]}),
            encoding="utf-8",
        )
        prompt = self.write_prompt([("other", "Runs other workflows.", skill_file)])

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["findings"]["active_missing_links"], ["alpha"])

    def test_explicit_missing_manifest_is_invalid_for_both_cli_spellings(self) -> None:
        skill_file = self.write_skill("alpha", "alpha", "Runs alpha workflows.")
        prompt = self.write_prompt([("alpha", "Runs alpha workflows.", skill_file)])
        missing = self.root / "missing-activation.json"

        for equals_form in (False, True):
            with self.subTest(equals_form=equals_form):
                completed, payload = self.run_audit(
                    prompt,
                    activation_manifest=missing,
                    manifest_equals=equals_form,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(payload["status"], "invalid")

    def test_enabled_inventory_entry_omitted_from_prompt_is_pressure(self) -> None:
        alpha = self.write_skill("alpha", "alpha", "Runs alpha workflows.")
        beta = self.write_skill("beta", "beta", "Runs beta workflows.")
        prompt = self.write_prompt(
            [("alpha", "Runs alpha workflows.", alpha)],
            extra_inventory=[self.inventory_item(beta)],
        )

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(
            [item["name"] for item in payload["findings"]["enabled_missing_visible"]],
            ["beta"],
        )

    def test_required_router_and_optional_count_ceiling_are_independent(self) -> None:
        router = self.write_skill("router", "router", "Routes cold skills.")
        prompt = self.write_prompt([("router", "Routes cold skills.", router)])

        completed, payload = self.run_audit(
            prompt, "--require-visible", "router", "--max-visible", "0"
        )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["findings"]["required_missing_visible"], [])
        self.assertTrue(payload["findings"]["max_visible_exceeded"])

    def test_missing_required_router_is_pressure(self) -> None:
        skill_file = self.write_skill("alpha", "alpha", "Runs alpha workflows.")
        prompt = self.write_prompt([("alpha", "Runs alpha workflows.", skill_file)])

        completed, payload = self.run_audit(prompt, "--require-visible", "router")

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["findings"]["required_missing_visible"], ["router"])

    def test_missing_available_skills_section_is_invalid(self) -> None:
        skill_file = self.write_skill("alpha", "alpha", "Runs alpha workflows.")
        self.write_inventory([self.inventory_item(skill_file)])
        prompt = self.root / "bad-prompt.json"
        prompt.write_text(
            json.dumps([{"content": [{"text": "## Skills\n### Skill roots"}]}]),
            encoding="utf-8",
        )

        completed, payload = self.run_audit(prompt)

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
