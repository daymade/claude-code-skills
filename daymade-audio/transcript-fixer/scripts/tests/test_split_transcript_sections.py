#!/usr/bin/env python3
"""Tests for transcript section splitting."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from split_transcript_sections import (
    SectionSpec,
    sanitize_filename_component,
    split_text_by_markers,
)


class TestSplitTranscriptSections(unittest.TestCase):
    def test_split_text_by_markers(self):
        text = (
            "预热内容\n"
            "开始安装\n"
            "装环境内容\n"
            "我们复盘一下。\n"
            "复盘内容\n"
        )
        parts = split_text_by_markers(
            text,
            first_section_name="课前聊天",
            sections=[
                SectionSpec(name="正式上课", marker="开始安装"),
                SectionSpec(name="课后复盘", marker="我们复盘一下。"),
            ],
        )
        self.assertEqual(parts[0][0], "课前聊天")
        self.assertEqual(parts[1][0], "正式上课")
        self.assertEqual(parts[2][0], "课后复盘")
        self.assertTrue(parts[1][1].startswith("开始安装"))
        self.assertTrue(parts[2][1].startswith("我们复盘一下。"))

    def test_sanitize_filename_component(self):
        self.assertEqual(sanitize_filename_component("课后/复盘"), "课后-复盘")


if __name__ == "__main__":
    unittest.main()
