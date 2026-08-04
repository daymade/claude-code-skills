"""Tests for the --add / --check-corpus command guards (review-driven)."""
import argparse
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.commands import cmd_add_correction, cmd_approve  # noqa: E402


def _args(**kw):
    base = dict(
        add_correction=("词", "正确词"), from_text="词", to_text="正确词",
        domain=None, force=False, check_corpus=False, corpus_dir=None,
        json_output=False,
    )
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture()
def isolated_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("TRANSCRIPT_FIXER_CONFIG_DIR", str(config_dir))
    return config_dir


class TestCheckCorpusGuard:
    def test_missing_corpus_dir_fails_fast_no_write(self, isolated_config):
        # Review finding: a typo'd --corpus used to print the "0 occurrences /
        # zero-risk" verdict and then write the rule — false safety evidence at
        # the decision gate. Must exit 2 BEFORE any service write.
        with pytest.raises(SystemExit) as exc:
            cmd_add_correction(_args(
                check_corpus=True,
                corpus_dir="/nonexistent/tinkle-corpus",
                domain="proj-alpha",
            ))
        assert exc.value.code == 2

    def test_missing_corpus_flag_fails_fast(self, isolated_config):
        with pytest.raises(SystemExit) as exc:
            cmd_add_correction(_args(check_corpus=True, domain="proj-alpha"))
        assert exc.value.code == 2

    def test_existing_corpus_probes_then_writes(self, isolated_config, tmp_path, capsys):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "a.md").write_text("目标词出现一次。", encoding="utf-8")
        cmd_add_correction(_args(
            from_text="目标词", to_text="正确词",
            check_corpus=True, corpus_dir=str(corpus), domain="demo",
        ))
        out = capsys.readouterr().out
        assert "probe:" in out
        assert "Added: '目标词' -> '正确词' (domain: demo)" in out


class TestDomainWriteGuards:
    def test_add_multi_domain_fails_fast(self, isolated_config):
        with pytest.raises(SystemExit) as exc:
            cmd_add_correction(_args(domain="a,b"))
        assert exc.value.code == 2

    def test_add_writes_normalized_domain(self, isolated_config, capsys):
        # Trailing comma used to pass the count check and then die in the
        # pattern validator with a misleading attribution; the write must use
        # the normalized single domain.
        cmd_add_correction(_args(domain="demo ,"))
        out = capsys.readouterr().out
        assert "(domain: demo)" in out

    def test_approve_multi_domain_fails_fast(self, isolated_config):
        with pytest.raises(SystemExit) as exc:
            cmd_approve(_args(domain="a,b"))
        assert exc.value.code == 2

    def test_add_without_domain_falls_back_to_general(self, isolated_config, capsys):
        # Pre-existing crash (explicit None defeated the service default);
        # no --domain now lands in "general".
        cmd_add_correction(_args(domain=None))
        out = capsys.readouterr().out
        assert "(domain: general)" in out
