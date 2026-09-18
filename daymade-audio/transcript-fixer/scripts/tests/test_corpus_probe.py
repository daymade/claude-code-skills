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


class TestProbeExcludesCorrectionRecords:
    """The probe's evidence must not include records of past corrections.

    Both an `asr_note` ledger and a `*_changes.md` sidecar quote the OLD form
    by construction. Counting them makes every correction already made read as
    fresh evidence that the term is always an ASR error — which is exactly the
    verdict `--probe` exists to inform, so the bias points straight at "add the
    rule". Real case 2026-09-18: a probe reported 42 occurrences across 11
    files; 11 of them were ledger text.
    """

    def _corpus(self) -> Path:
        d = Path(tempfile.mkdtemp())
        # A real transcript: two genuine body occurrences, plus a ledger line
        # citing the old form, plus an unrelated frontmatter field that must
        # stay visible (it is an ASR-derived search surface).
        (d / "t.md").write_text(
            "---\n"
            "title: 云锅的讨论\n"
            "asr_note: 云锅=云国、甲乙=甲已\n"
            "---\n"
            "\n"
            "他说云锅很好用。\n"
            "后来云锅又崩了。\n",
            encoding="utf-8")
        # The tool's own sidecar — output, not corpus evidence.
        (d / "t_changes.md").write_text(
            "- **From**: `云锅`\n- **To**: `云国`\n- 云锅 again\n",
            encoding="utf-8")
        return d

    def test_ledger_and_sidecar_occurrences_leave_the_count(self):
        result = probe_corpus("云锅", self._corpus())
        # 2 body + 1 title; the asr_note line and the whole sidecar are out.
        assert result.total == 3
        assert result.excluded_ledger == 1
        assert result.excluded_sidecar == 2  # sidecar cites it twice
        assert {f for f, _ in result.per_file} == {"t.md"}

    def test_exclusions_are_reported_not_silently_folded(self):
        result = probe_corpus("云锅", self._corpus())
        out = format_probe(result, Path("/corpus"))
        assert "excluded from the count: 3" in out
        assert "correction ledgers (asr_note)" in out
        assert "transcript-fixer sidecars" in out
        # The operator is told what is NOT auto-detected.
        assert "ingest log" in out
        payload = probe_to_json(result)
        assert payload["excluded_ledger"] == 1
        assert payload["excluded_sidecar"] == 2

    def test_sample_line_numbers_survive_the_projection(self):
        """The projection preserves newlines, so line 6/7 stay line 6/7."""
        result = probe_corpus("云锅", self._corpus())
        lines = sorted(s.line for s in result.samples)
        assert lines == [2, 6]  # title line + first body line (cap 2/file)

    def test_sidecar_suffix_list_matches_the_cli_constant(self):
        """The copy in core/ must not drift from cli.commands' canonical list."""
        from core.corpus_probe import _SIDECAR_SUFFIXES
        from cli.commands import STAGE1_SIDECAR_SUFFIXES
        assert list(_SIDECAR_SUFFIXES) == list(STAGE1_SIDECAR_SUFFIXES)
