"""Discovery and routing contract for the mixed Daymade audio suite."""

import json
import re
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SUITE = REPO / "daymade-audio"
ROUTER = SUITE / "audio-router/SKILL.md"
COLD = {"stepfun-asr", "stepfun-tts", "meeting-minutes-taker"}
HOT = {"asr-transcribe-to-text", "transcript-fixer"}


def frontmatter(path):
    first, header, _body = path.read_text(encoding="utf-8").split("---", 2)
    assert first == "", path
    return header


class AudioRouterContractTest(unittest.TestCase):
    def test_routes_are_exact_installed_siblings(self):
        body = ROUTER.read_text(encoding="utf-8")
        routes = re.findall(r"\.\./([^/]+)/SKILL\.md", body)
        self.assertEqual(set(routes), COLD)
        self.assertEqual(len(routes), len(set(routes)))
        for name in routes:
            self.assertEqual(
                (ROUTER.parent / ".." / name / "SKILL.md").resolve(strict=True),
                (SUITE / name / "SKILL.md").resolve(),
            )
        with tempfile.TemporaryDirectory() as temp:
            link = Path(temp) / "SKILL.md"
            link.symlink_to(ROUTER)
            self.assertEqual(link.resolve(strict=True), ROUTER.resolve())

        manifest = json.loads((REPO / ".claude-plugin/marketplace.json").read_text())
        plugin = next(item for item in manifest["plugins"] if item["name"] == "daymade-audio")
        self.assertEqual(plugin["source"], "./daymade-audio")
        self.assertEqual(
            set(plugin["skills"]),
            {f"./{path.parent.name}" for path in SUITE.glob("*/SKILL.md")},
        )

    def test_only_selected_children_are_manual_only(self):
        self.assertNotIn("disable-model-invocation: true", frontmatter(ROUTER))
        for name in COLD:
            header = frontmatter(SUITE / name / "SKILL.md")
            self.assertIn("disable-model-invocation: true", header, name)
            self.assertIn(f"name: {name}", header, name)
        for name in HOT:
            self.assertNotIn(
                "disable-model-invocation: true",
                frontmatter(SUITE / name / "SKILL.md"),
                name,
            )

    def test_visible_prefix_and_nearby_tasks_remain_distinct(self):
        header = frontmatter(ROUTER)
        description = " ".join(
            line.strip()
            for line in header.split("description: >-", 1)[1].splitlines()
            if line.startswith("  ")
        )
        for signal in (
            "StepFun ASR/语音识别", "StepFun TTS/配音", "transcript/妙记→会议纪要",
            "merge/review minutes", "generic ASR and correction stay direct",
        ):
            self.assertIn(signal, description[:160], signal)
        body = ROUTER.read_text(encoding="utf-8")
        self.assertIn("General audio/video transcription", body)
        self.assertIn("Correcting\nrecognition mistakes", body)
        self.assertIn("meeting-ingest", body)
        self.assertIn("does not authorize a paid call", body)


if __name__ == "__main__":
    unittest.main()
