from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts/check_archive_storage.py"
SPEC = importlib.util.spec_from_file_location("check_archive_storage", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ArchiveStorageContractTests(unittest.TestCase):
    def test_structured_git_and_source_cache_are_valid(self) -> None:
        payload = {
            "files": [
                {"storage": "git", "path": "archive/table.csv"},
                {
                    "storage": "source",
                    "locator": {"system": "feishu", "token": "file-token"},
                    "cache_path": "archive/cache/clip.mp4",
                },
            ]
        }
        self.assertEqual(MODULE.validate_manifest(payload), [])

    def test_raw_binary_in_git_is_rejected(self) -> None:
        errors = MODULE.validate_manifest(
            {"files": [{"storage": "git", "path": "archive/clip.mp4"}]}
        )
        self.assertTrue(any("raw binary" in error for error in errors))

    def test_external_path_cannot_masquerade_as_authority(self) -> None:
        errors = MODULE.validate_manifest(
            {
                "files": [
                    {
                        "storage": "source",
                        "locator": {"system": "feishu", "token": "file-token"},
                        "path": "archive/clip.mp4",
                    }
                ]
            }
        )
        self.assertTrue(any("cache_path" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
