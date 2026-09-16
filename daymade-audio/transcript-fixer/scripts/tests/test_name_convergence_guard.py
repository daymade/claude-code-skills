"""Tests for the name-convergence guard and the two --add write guards.

The guard is the mechanical gate born from the 2026-09-16 incident: 依琳→依林
and 徐盛→徐胜 were normalized by transcript-majority spelling, both targets
were wrong, and nothing mechanical stood between that judgement and a pushed
commit. These tests pin the incident pairs as POSITIVE cases (must refuse) so
the gate cannot silently widen back into discretion.
"""
import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.commands import (  # noqa: E402
    _get_review_queue,
    _get_service,
    cmd_add_correction,
    cmd_resolve_review,
)
from core.name_convergence_guard import (  # noqa: E402
    GuardRejection,
    NameLookup,
    evidence_names_authority,
    guard,
    is_person_name_shape,
)
from utils.config import reset_config  # noqa: E402


def _lookup(**kw) -> NameLookup:
    base = dict(
        roster_entry=False,
        roster_variant_of=None,
        dictionary_active_to=False,
        found_anywhere=False,
    )
    base.update(kw)
    return NameLookup(**base)


class TestGuardPositive:
    """The incident shapes — every one of these MUST be refused."""

    def test_incident_pair_yilin_majority_collapse_rejected(self):
        # 阳性①: from=依琳 to=依林, target claimed nowhere, evidence="同段互证"
        # names no authority — the exact 2026-09-16 first pair.
        r = guard("依琳", "依林", "同段互证", "entity", lookup_fn=lambda t: _lookup())
        assert isinstance(r, GuardRejection)
        assert r.code == "target_unknown"
        assert "--enqueue-review" in r.message

    def test_incident_pair_xusheng_majority_collapse_rejected(self):
        # 阳性②: from=徐盛 to=徐胜 — the second incident pair.
        r = guard("徐盛", "徐胜", "同段互证", "entity", lookup_fn=lambda t: _lookup())
        assert isinstance(r, GuardRejection)
        assert r.code == "target_unknown"

    def test_phonetic_shape_alone_gates_without_kind(self):
        # --add carries no kind; the 2-4 char CJK one-edit shape must gate on
        # its own, or the --add path stays exactly as discretionary as before.
        r = guard("依琳", "依林", None, None, lookup_fn=lambda t: _lookup())
        assert isinstance(r, GuardRejection)
        assert r.code == "target_unknown"

    def test_target_that_is_someones_variant_points_at_canonical(self):
        # 阳性③: 依林 exists ONLY as 艺霖's recorded ASR 变体 — converging onto
        # it manufactures the documented mishearing; the refusal must name 艺霖.
        r = guard(
            "依琳", "依林", None, "entity",
            lookup_fn=lambda t: _lookup(roster_variant_of="艺霖", found_anywhere=True),
        )
        assert isinstance(r, GuardRejection)
        assert r.code == "target_is_variant"
        assert "艺霖" in r.message


class TestGuardNegative:
    """Writes the guard must NOT touch."""

    def test_target_is_roster_entry_passes(self):
        # 阴性①: from=依琳 to=艺霖, and 艺霖 is a roster ### entry.
        assert guard(
            "依琳", "艺霖", None, "entity",
            lookup_fn=lambda t: _lookup(roster_entry=True, found_anywhere=True),
        ) is None

    def test_target_is_active_dictionary_to_passes(self):
        # 阴性② first leg: from=骗见 to=翩姐, 翩姐 already an active rule's to.
        assert guard(
            "骗见", "翩姐", None, "entity",
            lookup_fn=lambda t: _lookup(dictionary_active_to=True, found_anywhere=True),
        ) is None

    def test_authority_evidence_passes_unknown_target(self):
        # 阴性② second leg: target claimed nowhere, but the evidence names the
        # user ruling — a named authority, not majority spelling.
        assert guard(
            "骗见", "翩姐", "用户裁决 2026-09-16", "entity",
            lookup_fn=lambda t: _lookup(),
        ) is None

    def test_wording_fix_with_claimed_target_untouched(self):
        # 阴性③: 妙计→妙记 is not a person-name question (kind=wording); the
        # phonetic shape fires, but the target is already claimed somewhere,
        # so the guard stays out of an ordinary wording fix.
        assert guard(
            "妙计", "妙记", None, "wording",
            lookup_fn=lambda t: _lookup(found_anywhere=True),
        ) is None

    def test_non_name_shape_never_calls_lookup(self):
        called = []
        result = guard(
            "ASR", "ASR 识别", None, None,
            lookup_fn=lambda t: called.append(t) or _lookup(),
        )
        assert result is None
        assert not called


class TestShapeAndEvidencePrimitives:
    @pytest.mark.parametrize("a,b,expected", [
        ("依琳", "依林", True),     # one substitution
        ("徐盛", "徐胜", True),     # one substitution
        ("妙计", "妙记", True),     # one substitution — shape fires, kind decides
        ("骗见", "翩姐", False),    # two substitutions — no shape
        ("艺霖", "艺霖", True),     # identical is one-edit-away (service blocks a==b)
        ("小明", "小明同学", False),  # 4-char side vs 2-char side is fine, but two inserts
        ("依琳", "yilin", False),   # not all-CJK
        ("一", "二", False),        # below the 2-char floor
    ])
    def test_person_name_shape(self, a, b, expected):
        assert is_person_name_shape(a, b) is expected

    @pytest.mark.parametrize("evidence,expected", [
        ("roster 行 2026-09-16 更新", True),
        ("名册有此人", True),
        ("微信群 displayName+nickName 双读一致", True),
        ("群昵称核对", True),
        ("用户裁决：以 displayName 为准", True),
        ("音证：重听 00:12:33", True),
        ("音频复核", True),
        ("StepFun 重转写一致", True),
        ("dashboard 人工听过", True),
        ("同段互证", False),
        ("", False),
        (None, False),
    ])
    def test_authority_detection(self, evidence, expected):
        assert evidence_names_authority(evidence) is expected


# ---------- CLI write-path guards ----------


def _args(**kw):
    base = dict(
        add_correction=("萍姐", "翩姐"), from_text="萍姐", to_text="翩姐",
        domain=None, force=False, check_corpus=False, corpus_dir=None,
        json_output=False, review_note=None,
        resolve_review=None, review_decision=None, review_override_to=None,
        review_by=None,
    )
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture()
def isolated_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("TRANSCRIPT_FIXER_CONFIG_DIR", str(config_dir))
    reset_config()
    yield config_dir
    reset_config()


@pytest.fixture()
def roster_with_target(tmp_path, monkeypatch):
    """A people roster that claims 翩姐 as a ### entry, so the name guard's
    branch (a) passes and the --add tests exercise the guard under test rather
    than the name gate."""
    roster = tmp_path / "people.md"
    roster.write_text("### 翩姐\n- **身份**: 测试名册条目\n", encoding="utf-8")
    monkeypatch.setenv("TRANSCRIPT_FIXER_PEOPLE_ROSTER", str(roster))
    return roster


def _enqueue_pending(original: str, suggested: str, kind: str = "entity",
                     evidence: str | None = None) -> int:
    queue = _get_review_queue()
    result = queue.enqueue([{
        "original": original, "suggested": suggested,
        "kind": kind, "evidence": evidence, "source": "manual",
    }])
    return result["added"][0]


class TestAddPendingConflictGuard:
    def test_open_item_about_from_text_refuses_add(self, isolated_config, capsys):
        item_id = _enqueue_pending("孤例词", "正确词")
        with pytest.raises(SystemExit) as exc:
            cmd_add_correction(_args(from_text="孤例词", to_text="正确词"))
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert f"#{item_id}" in err
        # Fail-closed means NOTHING written.
        assert not _get_service().repository.get_all_corrections(active_only=False)

    def test_open_item_about_to_text_refuses_add(self, isolated_config, capsys):
        _enqueue_pending("别的问题", "翩姐")
        with pytest.raises(SystemExit) as exc:
            cmd_add_correction(_args(from_text="萍姐", to_text="翩姐"))
        assert exc.value.code == 2

    def test_decided_item_does_not_block(self, isolated_config, roster_with_target):
        item_id = _enqueue_pending("孤例词", "正确词")
        _get_review_queue().resolve(item_id, "kept_original", note="judged")
        cmd_add_correction(_args(
            from_text="孤例词", to_text="正确词",
            check_corpus=False, domain="demo",
        ))


class TestAddRealWordProbeGuard:
    def test_real_word_from_without_probe_refused(self, isolated_config, roster_with_target, capsys):
        # 萍姐 is 2 chars — substring-prone real-word shape; add-time
        # validators alone cannot measure how often it is real in THIS corpus.
        with pytest.raises(SystemExit) as exc:
            cmd_add_correction(_args(from_text="萍姐", to_text="翩姐"))
        assert exc.value.code == 2
        assert "--check-corpus" in capsys.readouterr().err

    def test_real_word_from_with_check_corpus_written(self, isolated_config, roster_with_target, tmp_path, capsys):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "a.md").write_text("萍姐没有出现，只是语料。", encoding="utf-8")
        cmd_add_correction(_args(
            from_text="萍姐", to_text="翩姐",
            check_corpus=True, corpus_dir=str(corpus), domain="demo",
        ))
        out = capsys.readouterr().out
        assert "Added: '萍姐' -> '翩姐' (domain: demo)" in out

    def test_non_real_word_shape_needs_no_probe(self, isolated_config, roster_with_target, capsys):
        # A 4-char ASR-garble FROM is not a real-word shape; the gate is silent.
        cmd_add_correction(_args(
            from_text="巨升智能", to_text="具身智能", domain="demo",
        ))
        assert "Added: '巨升智能' -> '具身智能' (domain: demo)" in capsys.readouterr().out


class TestAddNameConvergenceGuard:
    def test_majority_collapse_add_refused(self, isolated_config, capsys):
        # The incident shape at the --add write point: target claimed nowhere,
        # no authority named. (No roster configured in this fixture.)
        with pytest.raises(SystemExit) as exc:
            cmd_add_correction(_args(
                from_text="依琳", to_text="依林", review_note=None, domain="demo",
            ))
        assert exc.value.code == 2
        assert "--enqueue-review" in capsys.readouterr().err
        assert not _get_service().repository.get_all_corrections(active_only=False)

    def test_authority_note_lets_incident_pair_pass(self, isolated_config, capsys):
        # --note is the --add evidence channel: the very pair the incident
        # died on passes when the operator names the authority that settled
        # it. (check_corpus keeps Guard 3 satisfied for the 2-char FROM.)
        corpus = Path(isolated_config) / "corpus"
        corpus.mkdir()
        (corpus / "a.md").write_text("占位语料。", encoding="utf-8")
        cmd_add_correction(_args(
            from_text="依琳", to_text="依林",
            review_note="用户裁决 2026-09-16：以群 displayName 为准",
            check_corpus=True, corpus_dir=str(corpus), domain="demo",
        ))
        assert "Added: '依琳' -> '依林' (domain: demo)" in capsys.readouterr().out


class TestAuthorityRegexBoundary:
    """_AUTHORITY_RE 的「用户…裁决」腿必须有界且取完整词形——裸「用户.*裁」曾把
    「用户在讨论裁员时提到的名字」当用户裁决（2026-09-16 verify 端到端实测放行洞）。"""

    @pytest.mark.parametrize("text", [
        "用户在讨论裁员时提到的名字",
        "用户群里聊仲裁的事",
        "用户找裁判投诉的那次",
        "用户在群里问了裁缝",
    ])
    def test_layoff_arbitration_words_are_not_authority(self, text):
        from core.name_convergence_guard import _AUTHORITY_RE
        assert not _AUTHORITY_RE.search(text), f"误放行: {text!r}"

    @pytest.mark.parametrize("text", [
        "用户 2026-09-16 直接裁决",
        "用户当场裁定",
        "用户裁决",
        "由用户拍板的名字",
    ])
    def test_real_rulings_are_authority(self, text):
        from core.name_convergence_guard import _AUTHORITY_RE
        assert _AUTHORITY_RE.search(text), f"误拦截: {text!r}"


class TestResolveNameConvergenceGuard:
    def test_accept_majority_collapse_refused_and_stays_pending(self, isolated_config, capsys):
        # The incident's entry point: accepting 依琳→依林 on 同段互证 alone.
        item_id = _enqueue_pending("依琳", "依林", kind="entity", evidence="同段互证")
        with pytest.raises(SystemExit) as exc:
            cmd_resolve_review(_args(
                resolve_review=item_id, review_decision="accepted",
            ))
        assert exc.value.code == 2
        assert "--enqueue-review" in capsys.readouterr().err
        item = _get_review_queue().get(item_id)
        assert item.status == "pending"  # fail-closed: verdict NOT recorded

    def test_accept_with_authority_evidence_records(self, isolated_config, capsys):
        item_id = _enqueue_pending(
            "依琳", "艺霖", kind="entity",
            evidence="用户裁决 + 群 displayName 双读",
        )
        cmd_resolve_review(_args(resolve_review=item_id, review_decision="accepted"))
        item = _get_review_queue().get(item_id)
        assert item.status == "accepted"
        assert item.resolved_text == "艺霖"

    def test_override_to_someones_variant_refused(self, isolated_config, tmp_path, monkeypatch, capsys):
        # 依林 registered ONLY as 艺霖's roster variant: overriding onto it is
        # refused and must point at 艺霖.
        roster = tmp_path / "people.md"
        roster.write_text(
            "### 艺霖\n- **身份**: 测试\n- **ASR 变体**: 依林\n", encoding="utf-8",
        )
        monkeypatch.setenv("TRANSCRIPT_FIXER_PEOPLE_ROSTER", str(roster))
        item_id = _enqueue_pending("依琳", "一琳", kind="entity", evidence="同段互证")
        with pytest.raises(SystemExit) as exc:
            cmd_resolve_review(_args(
                resolve_review=item_id, review_decision="overridden",
                review_override_to="依林",
            ))
        assert exc.value.code == 2
        assert "艺霖" in capsys.readouterr().err
        assert _get_review_queue().get(item_id).status == "pending"

    def test_kept_original_not_gated(self, isolated_config):
        # kept_original writes no target form, so the guard does not fire even
        # on an incident-shaped pair.
        item_id = _enqueue_pending("依琳", "依林", kind="entity", evidence="同段互证")
        cmd_resolve_review(_args(
            resolve_review=item_id, review_decision="kept_original",
            review_note="original was right as spoken",
        ))
        assert _get_review_queue().get(item_id).status == "kept_original"
