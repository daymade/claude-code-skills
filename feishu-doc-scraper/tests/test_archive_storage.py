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

    def nas_row(self):
        return {"storage": "nas", "role": "external_video_original",
                "locator": {"system": "nas", "device": "synthetic-nas-001",
                            "account": "archive-user", "path": "Downloads/course name.webm",
                            "source_url": "https://www.youtube.com/watch?v=BaW_jenozKc"},
                "cache_path": "media/course name.webm", "bytes": 123,
                "sha256": "a" * 64, "mime": "video/webm"}

    def test_nas_primary_and_replica_retain_identity_and_integrity(self):
        row = self.nas_row()
        self.assertEqual(MODULE.validate_manifest({"files": [row]}), [])
        # Same object under different source URL aliases must still deduplicate.
        alias = {**row, "locator": {**row["locator"], "source_url": "https://youtu.be/BaW_jenozKc"}}
        self.assertTrue(any("duplicate durable" in e for e in MODULE.validate_manifest({"files": [row, alias]})))
        git_row = {"storage": "git", "role": "document_snapshot", "path": "source.txt",
                   "mime": "text/plain", "bytes": 123, "sha256": "a" * 64,
                   "replicas": [{"storage": "nas", "locator": row["locator"]}]}
        self.assertEqual(MODULE.validate_manifest({"files": [git_row]}), [])
        git_row.pop("sha256")
        self.assertTrue(any("SHA-256" in e for e in MODULE.validate_manifest({"files": [git_row]})))

    def test_nas_missing_empty_null_unsafe_and_extra_locator_fields(self):
        for key in ("system", "device", "account", "path", "source_url"):
            for value in (None, "", " ", 12):
                row = self.nas_row(); row["locator"][key] = value
                with self.subTest(key=key, value=value):
                    self.assertTrue(MODULE.validate_manifest({"files": [row]}))
            row = self.nas_row(); del row["locator"][key]
            self.assertTrue(MODULE.validate_manifest({"files": [row]}))
        for value in ("/Downloads/clip.webm", "../clip.webm", "Downloads/../clip.webm",
                      "Downloads//clip.webm", "Downloads/./clip.webm", "Downloads/", "Downloads\\clip.webm", "a\x00b"):
            row = self.nas_row(); row["locator"]["path"] = value
            self.assertTrue(MODULE.validate_manifest({"files": [row]}), value)
        for value in ("file:///private/clip.webm", "https://user:password@example.org/video",
                      "https://example.org/video#fragment", "https://[bad/video"):
            row = self.nas_row(); row["locator"]["source_url"] = value
            self.assertTrue(MODULE.validate_manifest({"files": [row]}), value)
        row = self.nas_row(); row["locator"]["cookie"] = "synthetic-value"
        self.assertTrue(any("unsupported fields" in e for e in MODULE.validate_manifest({"files": [row]})))
        for key in ("bytes", "sha256", "mime"):
            for value in (None, "", 0, False):
                row = self.nas_row(); row[key] = value
                self.assertTrue(MODULE.validate_manifest({"files": [row]}))
            row = self.nas_row(); del row[key]
            self.assertTrue(MODULE.validate_manifest({"files": [row]}))

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

    def test_double_extension_is_rejected_even_with_structured_role_and_mime(self) -> None:
        errors = MODULE.validate_manifest(
            {
                "files": [
                    {
                        "storage": "git",
                        "role": "document_snapshot",
                        "path": "archive/raw.mp4.md",
                        "mime": "text/plain",
                    }
                ]
            }
        )
        self.assertTrue(any("one extension only" in error for error in errors))

    def test_unknown_double_extensions_are_rejected_but_versions_are_allowed(self) -> None:
        for path in ("archive/photo.heic.md", "archive/payload.bin.md"):
            with self.subTest(path=path):
                errors = MODULE.validate_manifest(
                    {
                        "files": [
                            {
                                "storage": "git",
                                "role": "document_snapshot",
                                "path": path,
                                "mime": "text/plain",
                            }
                        ]
                    }
                )
                self.assertTrue(any("one extension only" in error for error in errors))

        versioned = {
            "files": [
                {
                    "storage": "git",
                    "role": "document_snapshot",
                    "path": "archive/report-v2.0.md",
                    "mime": "text/markdown",
                }
            ]
        }
        self.assertEqual(MODULE.validate_manifest(versioned), [])
        composed = {
            "files": [
                {
                    "storage": "git",
                    "role": "document_snapshot",
                    "path": "archive/raw.mp4-v2.0.md",
                    "mime": "text/markdown",
                }
            ]
        }
        self.assertTrue(
            any("one extension only" in error for error in MODULE.validate_manifest(composed))
        )

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
                            "source_url": "local-cache/raw.docx",
                        },
                    }
                ]
            }
        )
        self.assertTrue(any("stable Feishu/Lark" in error for error in local_path))

    def test_locator_rejects_local_path_hidden_beside_valid_feishu_fields(self) -> None:
        errors = MODULE.validate_manifest(
            {
                "files": [
                    {
                        "storage": "source",
                        "locator": {
                            "system": "feishu",
                            "token": "FileTokenAbCdEfGhIjKlMnOpQr",
                            "source_url": (
                                "https://example.feishu.cn/wiki/"
                                "AbCdEfGhIjKlMnOpQrStUvWxYz1"
                            ),
                            "path": "local-cache/raw.mp4",
                        },
                    }
                ]
            }
        )
        self.assertTrue(any("unsupported fields" in error for error in errors))

    def test_lark_locator_is_accepted(self) -> None:
        payload = {
            "files": [
                {
                    "storage": "source",
                    "locator": {
                        "system": "feishu",
                        "token": "MinuteTokenAbCdEfGhIjKlMnOp",
                        "source_url": (
                            "https://example.larkoffice.com/minutes/"
                            "MinuteTokenAbCdEfGhIjKlMnOp"
                        ),
                    },
                }
            ]
        }
        self.assertEqual(MODULE.validate_manifest(payload), [])

    def test_git_row_rejects_locator_and_replica_locators_are_validated(self) -> None:
        git_with_locator = {
            "files": [
                {
                    "storage": "git",
                    "role": "document_snapshot",
                    "path": "archive/source.md",
                    "mime": "text/markdown",
                    "locator": {
                        "system": "feishu",
                        "token": "FileTokenAbCdEfGhIjKlMnOpQr",
                        "source_url": (
                            "https://example.feishu.cn/wiki/"
                            "AbCdEfGhIjKlMnOpQrStUvWxYz1"
                        ),
                    },
                }
            ]
        }
        self.assertTrue(
            any("unsupported fields" in error for error in MODULE.validate_manifest(git_with_locator))
        )

        invalid_replica = {
            "files": [
                {
                    "storage": "source",
                    "locator": {
                        "system": "feishu",
                        "token": "FileTokenAbCdEfGhIjKlMnOpQr",
                        "source_url": (
                            "https://example.feishu.cn/wiki/"
                            "AbCdEfGhIjKlMnOpQrStUvWxYz1"
                        ),
                    },
                    "replicas": [
                        {
                            "storage": "oss",
                            "locator": {
                                "system": "oss",
                                "uri": "oss://archive/raw.mp4",
                                "path": "local-cache/raw.mp4",
                            },
                        }
                    ],
                }
            ]
        }
        self.assertTrue(
            any("unsupported fields" in error for error in MODULE.validate_manifest(invalid_replica))
        )

    def test_valid_oss_replica_wechat_source_and_markdown_mime_are_accepted(self) -> None:
        payload = {
            "files": [
                {
                    "storage": "git",
                    "role": "document_snapshot",
                    "path": "archive/source.md",
                    "mime": "text/markdown",
                    "replicas": [
                        {
                            "storage": "oss",
                            "locator": {
                                "system": "oss",
                                "uri": "oss://archive/source.md",
                            },
                        }
                    ],
                },
                {
                    "storage": "source",
                    "locator": {
                        "system": "wechat",
                        "message_id": "1786003683000244",
                        "chat": "project-group",
                    },
                },
            ]
        }
        self.assertEqual(MODULE.validate_manifest(payload), [])

    def test_manifest_root_rejects_storage_authority_fields(self) -> None:
        payload = {
            "files": [],
            "storage": "source",
            "locator": {"system": "unknown", "token": "x"},
            "path": "local-cache/raw.mp4",
        }
        errors = MODULE.validate_manifest(payload)
        self.assertTrue(any("manifest root" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
