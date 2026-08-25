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
                {
                    "storage": "git",
                    "role": "sheet_csv",
                    "path": "archive/table.csv",
                    "mime": "text/csv",
                },
                {
                    "storage": "source",
                    "locator": {
                        "system": "feishu",
                        "source_url": (
                            "https://example.feishu.cn/wiki/"
                            "AbCdEfGhIjKlMnOpQrStUvWxYz1"
                        ),
                        "token": "FileTokenAbCdEfGhIjKlMnOpQr",
                    },
                    "cache_path": "archive/cache/clip.mp4",
                },
            ]
        }
        self.assertEqual(MODULE.validate_manifest(payload), [])

    def test_raw_binary_in_git_is_rejected(self) -> None:
        errors = MODULE.validate_manifest(
            {
                "files": [
                    {
                        "storage": "git",
                        "role": "embedded_media_original",
                        "path": "archive/clip.mp4",
                        "mime": "video/mp4",
                    }
                ]
            }
        )
        self.assertTrue(any("raw binary" in error for error in errors))

    def test_external_path_cannot_masquerade_as_authority(self) -> None:
        errors = MODULE.validate_manifest(
            {
                "files": [
                    {
                        "storage": "source",
                        "locator": {
                            "system": "feishu",
                            "source_url": (
                                "https://example.feishu.cn/wiki/"
                                "AbCdEfGhIjKlMnOpQrStUvWxYz1"
                            ),
                            "token": "FileTokenAbCdEfGhIjKlMnOpQr",
                        },
                        "path": "archive/clip.mp4",
                    }
                ]
            }
        )
        self.assertTrue(any("cache_path" in error for error in errors))

    def test_raw_role_and_mime_cannot_hide_behind_md_suffix(self) -> None:
        errors = MODULE.validate_manifest(
            {
                "files": [
                    {
                        "storage": "git",
                        "role": "embedded_attachment_original",
                        "path": "archive/raw.mp4.md",
                        "mime": "video/mp4",
                    }
                ]
            }
        )
        self.assertTrue(any("not a structured Git role" in error for error in errors))
        self.assertTrue(any("incompatible" in error for error in errors))

    def test_unknown_system_and_local_path_are_not_stable_locators(self) -> None:
        unknown = MODULE.validate_manifest(
            {
                "files": [
                    {
                        "storage": "source",
                        "locator": {"system": "unknown", "token": "x"},
                    }
                ]
            }
        )
        self.assertTrue(any("unsupported source locator system" in error for error in unknown))

        local_path = MODULE.validate_manifest(
            {
                "files": [
                    {
                        "storage": "source",
                        "locator": {
                            "system": "feishu",
                            "token": "FileTokenAbCdEfGhIjKlMnOpQr",
                            "source_url": "/Users/example/local/raw.docx",
                        },
                    }
                ]
            }
        )
        self.assertTrue(any("stable https://*.feishu.cn" in error for error in local_path))


if __name__ == "__main__":
    unittest.main()
