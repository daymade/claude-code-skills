#!/usr/bin/env python3
"""Keep the Lark business router outside the Claude Code suite in committed trees."""

from __future__ import annotations

import copy
import json
import posixpath
import subprocess
import unittest
from pathlib import Path, PurePosixPath


REPO = Path(__file__).resolve().parents[1]
ROUTER = "lark-cli-router"
CODE_SUITE = "daymade-claude-code"


def ownership_violations(manifest: dict, files: set[str]) -> list[str]:
    """Check this named business decision without prescribing a future owner."""
    roots = {
        str(PurePosixPath(name).parent)
        for name in files
        if PurePosixPath(name).name == "SKILL.md"
        and PurePosixPath(name).parent.name == ROUTER
    }
    registrations = []
    for plugin in manifest.get("plugins", []):
        source = posixpath.normpath(plugin["source"])
        members = plugin.get("skills")
        paths = (
            [posixpath.normpath(posixpath.join(source, item)) for item in members]
            if members else [source]
        )
        registrations.extend(
            (plugin["name"], path) for path in paths if path in roots
        )

    errors = []
    if not roots:
        errors.append("Lark router source is missing")
    if len(registrations) != 1:
        errors.append(f"Lark router needs one registration, found {len(registrations)}")
    if any(owner == CODE_SUITE for owner, _ in registrations):
        errors.append("Lark router must not be owned by the Claude Code suite")
    if any(path.startswith(CODE_SUITE + "/") for path in roots):
        errors.append("Lark router must not reside beneath the Claude Code suite")
    return errors


class LarkRouterOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = {"plugins": [
            {"name": CODE_SUITE, "source": "./" + CODE_SUITE,
             "skills": ["./claude-code-hooks"]},
            {"name": ROUTER, "source": "./" + ROUTER},
        ]}
        self.files = {CODE_SUITE + "/claude-code-hooks/SKILL.md", ROUTER + "/SKILL.md"}

    def test_committed_repository_preserves_the_business_owner(self) -> None:
        manifest = json.loads(subprocess.check_output([
            "git", "-C", str(REPO), "show", "HEAD:.claude-plugin/marketplace.json",
        ]))
        files = set(subprocess.check_output([
            "git", "-C", str(REPO), "ls-tree", "-r", "--name-only", "HEAD",
        ], text=True).splitlines())
        self.assertEqual(ownership_violations(manifest, files), [])

    def test_current_standalone_fixture_passes(self) -> None:
        self.assertEqual(ownership_violations(self.manifest, self.files), [])

    def test_code_owner_is_rejected_with_a_safe_physical_location(self) -> None:
        manifest = {"plugins": [{
            "name": CODE_SUITE, "source": "./collaboration-suite",
            "skills": ["./" + ROUTER],
        }]}
        files = {"collaboration-suite/" + ROUTER + "/SKILL.md"}
        self.assertEqual(ownership_violations(manifest, files), [
            "Lark router must not be owned by the Claude Code suite",
        ])

    def test_code_directory_is_rejected_with_an_acceptable_owner(self) -> None:
        manifest = {"plugins": [{
            "name": "collaboration-suite", "source": "./" + CODE_SUITE,
            "skills": ["./" + ROUTER],
        }]}
        files = {CODE_SUITE + "/" + ROUTER + "/SKILL.md"}
        self.assertEqual(ownership_violations(manifest, files), [
            "Lark router must not reside beneath the Claude Code suite",
        ])

    def test_stale_code_copy_is_rejected_after_registration_moves(self) -> None:
        files = self.files | {CODE_SUITE + "/" + ROUTER + "/SKILL.md"}
        self.assertEqual(ownership_violations(self.manifest, files), [
            "Lark router must not reside beneath the Claude Code suite",
        ])

    def test_missing_registration_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["plugins"].pop()
        self.assertEqual(ownership_violations(manifest, self.files), [
            "Lark router needs one registration, found 0",
        ])

    def test_two_owners_cannot_register_the_same_router(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["plugins"].append({
            "name": "another-collaboration-plugin", "source": "./" + ROUTER,
        })
        self.assertEqual(ownership_violations(manifest, self.files), [
            "Lark router needs one registration, found 2",
        ])

    def test_duplicate_members_in_one_owner_are_counted(self) -> None:
        manifest = {"plugins": [{
            "name": "collaboration-suite", "source": "./collaboration-suite",
            "skills": ["./" + ROUTER, "./" + ROUTER],
        }]}
        files = {"collaboration-suite/" + ROUTER + "/SKILL.md"}
        self.assertEqual(ownership_violations(manifest, files), [
            "Lark router needs one registration, found 2",
        ])

    def test_future_collaboration_suite_is_allowed(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["plugins"][1] = {
            "name": "collaboration-suite", "source": "./collaboration-suite",
            "skills": ["./" + ROUTER],
        }
        files = (self.files - {ROUTER + "/SKILL.md"}) | {
            "collaboration-suite/" + ROUTER + "/SKILL.md",
        }
        self.assertEqual(ownership_violations(manifest, files), [])

    def test_unrelated_code_suite_growth_is_allowed(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["plugins"][0]["skills"].append("./another-code-capability")
        files = self.files | {CODE_SUITE + "/another-code-capability/SKILL.md"}
        self.assertEqual(ownership_violations(manifest, files), [])

    def test_missing_physical_router_is_not_a_pass(self) -> None:
        errors = ownership_violations(self.manifest, self.files - {ROUTER + "/SKILL.md"})
        self.assertIn("Lark router source is missing", errors)

    def test_normalized_code_directory_is_still_rejected(self) -> None:
        manifest = {"plugins": [{
            "name": "collaboration-suite", "source": "./other/../" + CODE_SUITE,
            "skills": ["./" + ROUTER],
        }]}
        files = {CODE_SUITE + "/" + ROUTER + "/SKILL.md"}
        self.assertEqual(ownership_violations(manifest, files), [
            "Lark router must not reside beneath the Claude Code suite",
        ])


if __name__ == "__main__":
    unittest.main()
