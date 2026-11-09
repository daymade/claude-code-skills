"""Description schema regression and repository identity-field preservation."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import check_marketplace


class MarketplaceMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".claude-plugin").mkdir()
        skill = self.root / "fixture-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\nname: fixture-skill\ndescription: Synthetic fixture.\n---\n"
        )
        self.manifest = self.root / ".claude-plugin" / "marketplace.json"
        self.entry = {
            "name": "fixture-skill",
            "source": "./fixture-skill",
            "version": "1.0.0",
        }

    def validate(self, entry):
        self.manifest.write_text(json.dumps({"plugins": [entry]}))
        output = io.StringIO()
        with (
            mock.patch.object(check_marketplace, "REPO_ROOT", self.root),
            mock.patch.object(check_marketplace, "MANIFEST", self.manifest),
            contextlib.redirect_stdout(output),
        ):
            result = check_marketplace.main()
        return result, output.getvalue()

    def test_description_can_be_absent_or_a_string(self):
        for extra in ({}, {"description": ""}, {"description": "Fixture plugin"}):
            with self.subTest(extra=extra):
                result, output = self.validate(self.entry | extra)
                self.assertEqual(result, 0, output)

    def test_present_description_rejects_non_string_values(self):
        for value in (None, 7, [], {}):
            with self.subTest(value=value):
                result, output = self.validate(self.entry | {"description": value})
                self.assertEqual(result, 1, output)
                self.assertIn("description", output)

    def test_required_identity_fields_still_reject_missing_empty_and_null(self):
        for field in ("name", "source", "version"):
            for form in ("missing", "empty", "null"):
                with self.subTest(field=field, form=form):
                    entry = self.entry | {"description": "Fixture plugin"}
                    if form == "missing":
                        entry.pop(field)
                    else:
                        entry[field] = "" if form == "empty" else None
                    result, output = self.validate(entry)
                    self.assertEqual(result, 1, output)
                    self.assertIn(field, output)


if __name__ == "__main__":
    unittest.main()
