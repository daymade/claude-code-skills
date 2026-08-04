"""Tests for core.corpus_probe — in-corpus real-meaning frequency evidence."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.corpus_probe import probe_corpus, format_probe, probe_to_json  # noqa: E402


def _make_corpus() -> Path:
    d = Path(tempfile.mkdtemp())
    (d / "a.md").write_text("目标词讲的内容。\n无关行。\n还是目标词。", encoding="utf-8")
    (d / "b.md").write_text("这行内容完全无关。", encoding="utf-8")
    sub = d / "nested"
    sub.mkdir()
    (sub / "c.md").write_text("目标词又一次。", encoding="utf-8")
    (d / "not-md.txt").write_text("目标词在 txt 里不该计入。", encoding="utf-8")
    return d


class TestProbeCorpus:
    def test_counts_across_files_recursive_md_only(self):
        result = probe_corpus("目标词", _make_corpus())
        assert result.total == 3
        files = {f for f, _ in result.per_file}
        assert files == {"a.md", "nested/c.md"}
        assert not any("txt" in f for f in files)

    def test_samples_carry_line_and_window(self):
        result = probe_corpus("目标词", _make_corpus())
        assert result.samples
        first = result.samples[0]
        assert first.file == "a.md"
        assert first.line == 1
        assert "目标词" in first.context

    def test_zero_occurrences_verdict_aid_differs(self):
        result = probe_corpus("不存在的词", _make_corpus())
        report = format_probe(result, Path("/corpus"))
        assert "total: 0" in report
        assert "zero-risk" in report

    def test_nonzero_verdict_aid_asks_for_sample_judgment(self):
        result = probe_corpus("目标词", _make_corpus())
        report = format_probe(result, Path("/corpus"))
        assert "SAMPLED" in report

    def test_sampling_coverage_is_visible(self):
        result = probe_corpus("目标词", _make_corpus())
        report = format_probe(result, Path("/corpus"))
        assert "caps: 2/file, 8 total" in report
        assert "of 2 file(s)" in report

    def test_unreadable_files_are_skipped_not_fatal(self):
        d = _make_corpus()
        (d / "broken.md").symlink_to(d / "missing-target.md")
        result = probe_corpus("目标词", d)
        assert result.total == 3

    def test_json_shape(self):
        result = probe_corpus("目标词", _make_corpus())
        data = probe_to_json(result)
        assert data["total"] == 3
        assert {"file": "a.md", "count": 2} in data["per_file"]
