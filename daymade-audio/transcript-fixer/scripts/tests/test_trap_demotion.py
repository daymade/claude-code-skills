#!/usr/bin/env python3
"""
Tests for trap-aware demotion (禁裸词/勿修 vetoes) and domain-scoped
context rules.

Covers:
A. extract_demotion_sets parsing (marker inside the bold annotation, the
   established production convention) and its effect on _assess_risk /
   DictionaryProcessor behavior.
B. context_rules v2.4: domain column migration SQL, domain-filtered loading,
   add/list CLI service methods, and unmigrated-database fallbacks.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.dictionary_processor import DictionaryProcessor
from core.trap_scanner import extract_demotion_sets
from core.correction_repository import CorrectionRepository
from core.correction_service import CorrectionService, ValidationError
from utils.migrations import MIGRATION_V2_4


# ---------------------------------------------------------------------------
# A1. extract_demotion_sets parsing
# ---------------------------------------------------------------------------

class TestExtractDemotionSets:
    def test_marker_inside_bold_annotation_bans_from_variants(self):
        """The production convention puts 禁裸词 inside the bold parens."""
        text = "- **妙计 → 妙记（飞书妙记产品语境，禁裸词）** — 说明文字\n"
        sets = extract_demotion_sets(text)
        assert "妙计" in sets.banned_froms
        assert "妙记" not in sets.banned_froms

    def test_marker_after_bold_span_also_bans(self):
        text = "- **绘画 → 会话** — AI 对话语境，禁裸词\n"
        sets = extract_demotion_sets(text)
        assert "绘画" in sets.banned_froms

    def test_trap_without_marker_does_not_ban(self):
        text = "- **asms → AICMS** — 产品名误识，已入库\n"
        sets = extract_demotion_sets(text)
        assert sets.banned_froms == frozenset()

    def test_multi_variant_from_side_all_banned(self):
        text = "- **卖吸引/卖新鲜 → 麦锡颖（禁入词典）** — cue\n"
        sets = extract_demotion_sets(text)
        assert "卖吸引" in sets.banned_froms
        assert "卖新鲜" in sets.banned_froms

    def test_confirmed_correct_record_becomes_keep_token(self):
        text = "- **薛辉 = 真实实体，勿修** — 域内 11 处引用\n"
        sets = extract_demotion_sets(text)
        assert "薛辉" in sets.keep_tokens
        assert sets.banned_froms == frozenset()

    def test_marker_in_unrelated_line_does_not_ban_other_traps(self):
        text = (
            "- **公开 → 工勘** — 渠道语境判，无标记\n"
            "- **妙计 → 妙记（禁裸词）** — cue\n"
        )
        sets = extract_demotion_sets(text)
        assert "公开" not in sets.banned_froms
        assert "妙计" in sets.banned_froms


# ---------------------------------------------------------------------------
# A2. demoted_by_trap grading in _assess_risk
# ---------------------------------------------------------------------------

def _make_processor(meta):
    return DictionaryProcessor(
        {"绿点": "绿电", "asms": "AICMS"},
        [],
        meta,
        speaker_labels=set(),
    )


class TestDemotedByTrapGrading:
    def test_demotion_beats_trusted_domain(self):
        processor = _make_processor(
            {"绿点": {"confidence": 1.0,
                      "trusted_domain": True, "demoted_by_trap": True},
             "asms": {"confidence": 1.0, "trusted_domain": True}}
        )
        assert processor._assess_risk("绿点", "绿电") == "medium"
        assert processor._assess_risk("asms", "AICMS") == "low"

    def test_safe_mode_defers_demoted_rule_and_applies_normal_rule(self):
        processor = _make_processor(
            {"绿点": {"confidence": 1.0,
                      "trusted_domain": True, "demoted_by_trap": True},
             "asms": {"confidence": 1.0, "trusted_domain": True}}
        )
        corrected, changes = processor.process(
            "那不是有个绿点吗？不是 asms docs。", review_mode=True)
        assert "绿点" in corrected, "demoted rule must not auto-apply"
        assert "绿电" not in corrected
        assert "AICMS" in corrected, "trusted normal rule still applies"
        demoted = [c for c in changes if c.from_text == "绿点"]
        assert demoted and demoted[0].risk == "medium"

    def test_apply_all_still_applies_demoted_rule(self):
        """--apply-all is the operator's explicit override: review_mode off."""
        processor = _make_processor(
            {"绿点": {"confidence": 1.0,
                      "trusted_domain": True, "demoted_by_trap": True},
             "asms": {"confidence": 1.0, "trusted_domain": True}}
        )
        corrected, _ = processor.process("那不是有个绿点吗？", review_mode=False)
        assert "绿电" in corrected

    def test_context_rule_not_demoted_by_matching_from_text(self):
        """A context rule carries its own context: even when its match text
        equals a demoted FROM (lookahead-style pattern), the demotion must
        not fire on it — otherwise --add-context-rule stops being the escape
        channel the docs prescribe."""
        processor = DictionaryProcessor(
            {"妙计": "妙记"},
            [{"pattern": r"妙计(?=比)", "replacement": "妙记",
              "description": "妙记后接比"}],
            {"妙计": {"confidence": 1.0,
                      "trusted_domain": True, "demoted_by_trap": True}},
            speaker_labels=set(),
        )
        corrected, changes = processor.process("妙计比它更准吗", review_mode=True)
        assert "妙记比它更准吗" in corrected
        context_changes = [c for c in changes if c.rule_type == "context_rule"]
        assert context_changes and context_changes[0].risk != "medium"


# ---------------------------------------------------------------------------
# A3. CLI wiring: _load_trap_demotion_sets
# ---------------------------------------------------------------------------

class TestLoadTrapDemotionSets:
    def test_reads_each_named_domain_context_file(self, tmp_path, monkeypatch):
        contexts = tmp_path / ".transcript-fixer" / "contexts"
        contexts.mkdir(parents=True)
        (contexts / "huawei.md").write_text(
            "- **妙计 → 妙记（禁裸词）** — cue\n- **薛辉 = 真实实体，勿修**\n",
            encoding="utf-8")
        (contexts / "pkm.md").write_text(
            "- **新一 → 星壹（禁入词典）** — cue\n", encoding="utf-8")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        from cli.commands import _load_trap_demotion_sets
        banned, keep = _load_trap_demotion_sets(["huawei", "pkm"])
        assert banned == frozenset({"妙计", "新一"})
        assert keep == frozenset({"薛辉"})

    def test_no_domain_returns_empty(self):
        from cli.commands import _load_trap_demotion_sets
        assert _load_trap_demotion_sets(None) == (frozenset(), frozenset())

    def test_missing_context_file_is_silent_skip(self, tmp_path, monkeypatch):
        (tmp_path / ".transcript-fixer" / "contexts").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        from cli.commands import _load_trap_demotion_sets
        assert _load_trap_demotion_sets(["nosuchdomain"]) == \
            (frozenset(), frozenset())


# ---------------------------------------------------------------------------
# B1. Migration v2.4 SQL
# ---------------------------------------------------------------------------

_OLD_CONTEXT_RULES_DDL = """
CREATE TABLE context_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    replacement TEXT NOT NULL,
    description TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    added_by TEXT
);
"""


def _old_style_db(path: Path) -> sqlite3.Connection:
    """A context_rules table as it existed before v2.4 (no domain column)."""
    conn = sqlite3.connect(path)
    conn.execute(_OLD_CONTEXT_RULES_DDL)
    conn.execute(
        "INSERT INTO context_rules (pattern, replacement, description) "
        "VALUES ('legacy', 'legacy-repl', 'legacy rule')")
    conn.commit()
    return conn


class TestMigrationV24:
    def test_forward_adds_domain_column_and_preserves_rows(self, tmp_path):
        conn = _old_style_db(tmp_path / "corrections.db")
        conn.executescript(MIGRATION_V2_4.forward_sql)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(context_rules)")}
        assert "domain" in cols
        row = conn.execute(
            "SELECT pattern, domain FROM context_rules WHERE pattern = 'legacy'"
        ).fetchone()
        assert row == ("legacy", None), "existing rows must stay global (NULL)"
        conn.close()

    def test_backward_drops_domain_column(self, tmp_path):
        conn = _old_style_db(tmp_path / "corrections.db")
        conn.executescript(MIGRATION_V2_4.forward_sql)
        conn.executescript(MIGRATION_V2_4.backward_sql)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(context_rules)")}
        assert "domain" not in cols
        conn.close()


# ---------------------------------------------------------------------------
# B2. Service: domain-filtered load, add, list
# ---------------------------------------------------------------------------

@pytest.fixture
def service(tmp_path):
    repo = CorrectionRepository(tmp_path / "corrections.db")
    return CorrectionService(repo)


class TestContextRuleService:
    def test_add_and_list_round_trip(self, service):
        rule_id = service.add_context_rule(
            r"上传到妙计", "上传到妙记", domain="huawei",
            description="飞书妙记语境", added_by="test")
        assert rule_id > 0
        rules = service.list_context_rules(domain="huawei")
        assert len(rules) == 1
        r = rules[0]
        assert r["pattern"] == r"上传到妙计"
        assert r["domain"] == "huawei"
        assert r["is_active"] is True

    def test_domain_filtered_loading(self, service):
        service.add_context_rule("global-rule", "g", description="global")
        service.add_context_rule("huawei-rule", "h", domain="huawei")
        service.add_context_rule("pkm-rule", "p", domain="pkm")

        patterns = {r["pattern"] for r in service.load_context_rules(["huawei"])}
        assert patterns == {"global-rule", "huawei-rule"}

        patterns = {r["pattern"] for r in service.load_context_rules(["other"])}
        assert patterns == {"global-rule"}

        patterns = {r["pattern"] for r in service.load_context_rules(None)}
        assert patterns == {"global-rule", "huawei-rule", "pkm-rule"}

    def test_add_rejects_duplicate_pattern(self, service):
        service.add_context_rule("dup", "x")
        with pytest.raises(ValidationError, match="already exists"):
            service.add_context_rule("dup", "y")

    def test_add_rejects_invalid_regex(self, service):
        with pytest.raises(ValidationError, match="invalid context rule pattern"):
            service.add_context_rule("(unclosed", "x")

    def test_add_rejects_empty_fields(self, service):
        with pytest.raises(ValidationError):
            service.add_context_rule("", "x")
        with pytest.raises(ValidationError):
            service.add_context_rule("p", "")

    def test_audit_log_written(self, service):
        rule_id = service.add_context_rule("audited", "x", domain="huawei")
        with service.repository._pool.get_connection() as conn:
            row = conn.execute(
                "SELECT action, entity_id FROM audit_log "
                "WHERE action = 'add_context_rule' AND entity_id = ?",
                (rule_id,)).fetchone()
        assert row is not None
        assert tuple(row) == ("add_context_rule", rule_id)

    def test_list_include_inactive(self, service):
        rule_id = service.add_context_rule("off", "x")
        with service.repository._pool.get_connection() as conn:
            conn.execute(
                "UPDATE context_rules SET is_active = 0 WHERE id = ?",
                (rule_id,))
            conn.commit()
        assert service.list_context_rules() == []
        assert len(service.list_context_rules(include_inactive=True)) == 1

    def test_all_flag_reaches_include_inactive(self, tmp_path):
        """--all must parse and reach include_inactive (the flag once existed
        only in docs and died at argparse)."""
        from cli.argument_parser import create_argument_parser
        parser = create_argument_parser()
        args = parser.parse_args(["--list-context-rules", "--all"])
        assert args.list_context_rules is True
        assert getattr(args, "all", False) is True


# ---------------------------------------------------------------------------
# B3. Unmigrated-database behavior
# ---------------------------------------------------------------------------

class TestUnmigratedDatabase:
    def _service_on_old_db(self, tmp_path) -> CorrectionService:
        old_db = tmp_path / "corrections.db"
        conn = _old_style_db(old_db)
        conn.close()
        # CorrectionRepository on an existing file must not recreate the
        # table; verify our fixture still lacks the column.
        repo = CorrectionRepository(old_db)
        with repo._pool.get_connection() as c:
            cols = {row[1] for row in c.execute("PRAGMA table_info(context_rules)")}
        assert "domain" not in cols
        return CorrectionService(repo)

    def test_load_falls_back_to_legacy_behavior(self, tmp_path):
        """No domain column ⇒ every rule is global by construction; loading
        must not crash, and domain filtering must not drop anything."""
        service = self._service_on_old_db(tmp_path)
        rules = service.load_context_rules(["huawei"])
        assert [r["pattern"] for r in rules] == ["legacy"]

    def test_add_fails_loud_with_migration_direction(self, tmp_path):
        service = self._service_on_old_db(tmp_path)
        with pytest.raises(ValidationError, match="migration"):
            service.add_context_rule("new-rule", "x", domain="huawei")
