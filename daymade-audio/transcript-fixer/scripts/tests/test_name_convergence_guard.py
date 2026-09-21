"""Tests for the name-convergence guard and the two --add write guards.

The guard is the mechanical gate born from the 2026-09-16 incident: 乙琳→乙林
and 丙盛→丙胜 were normalized by transcript-majority spelling, both targets
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
    cmd_attach_authority,
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
        # 阳性①: from=乙琳 to=乙林, target claimed nowhere, evidence="同段互证"
        # names no authority — the exact 2026-09-16 first pair.
        r = guard("乙琳", "乙林", "同段互证", "entity", lookup_fn=lambda t: _lookup())
        assert isinstance(r, GuardRejection)
        assert r.code == "target_unknown"
        assert "--enqueue-review" in r.message

    def test_incident_pair_xusheng_majority_collapse_rejected(self):
        # 阳性②: from=丙盛 to=丙胜 — the second incident pair.
        r = guard("丙盛", "丙胜", "同段互证", "entity", lookup_fn=lambda t: _lookup())
        assert isinstance(r, GuardRejection)
        assert r.code == "target_unknown"

    def test_phonetic_shape_alone_gates_without_kind(self):
        # --add carries no kind; the 2-4 char CJK one-edit shape must gate on
        # its own, or the --add path stays exactly as discretionary as before.
        r = guard("乙琳", "乙林", None, None, lookup_fn=lambda t: _lookup())
        assert isinstance(r, GuardRejection)
        assert r.code == "target_unknown"

    def test_target_that_is_someones_variant_points_at_canonical(self):
        # 阳性③: 乙林 exists ONLY as 乙霖's recorded ASR 变体 — converging onto
        # it manufactures the documented mishearing; the refusal must name 乙霖.
        r = guard(
            "乙琳", "乙林", None, "entity",
            lookup_fn=lambda t: _lookup(roster_variant_of="乙霖", found_anywhere=True),
        )
        assert isinstance(r, GuardRejection)
        assert r.code == "target_is_variant"
        assert "乙霖" in r.message


class TestGuardNegative:
    """Writes the guard must NOT touch."""

    def test_target_is_roster_entry_passes(self):
        # 阴性①: from=乙琳 to=乙霖, and 乙霖 is a roster ### entry.
        assert guard(
            "乙琳", "乙霖", None, "entity",
            lookup_fn=lambda t: _lookup(roster_entry=True, found_anywhere=True),
        ) is None

    def test_target_is_active_dictionary_to_passes(self):
        # 阴性② first leg: from=顶见 to=丁姐, 丁姐 already an active rule's to.
        assert guard(
            "顶见", "丁姐", None, "entity",
            lookup_fn=lambda t: _lookup(dictionary_active_to=True, found_anywhere=True),
        ) is None

    def test_authority_evidence_passes_unknown_target(self):
        # 阴性② second leg: target claimed nowhere, but the evidence names the
        # user ruling — a named authority, not majority spelling.
        assert guard(
            "顶见", "丁姐", "用户裁决 2026-09-16", "entity",
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
        ("乙琳", "乙林", True),     # one substitution
        ("丙盛", "丙胜", True),     # one substitution
        ("妙计", "妙记", True),     # one substitution — shape fires, kind decides
        ("顶见", "丁姐", False),    # two substitutions — no shape
        ("乙霖", "乙霖", True),     # identical is one-edit-away (service blocks a==b)
        ("小明", "小明同学", False),  # 4-char side vs 2-char side is fine, but two inserts
        ("乙琳", "yilin", False),   # not all-CJK
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
        add_correction=("萍姐", "丁姐"), from_text="萍姐", to_text="丁姐",
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
    """A people roster that claims 丁姐 as a ### entry, so the name guard's
    branch (a) passes and the --add tests exercise the guard under test rather
    than the name gate."""
    roster = tmp_path / "people.md"
    roster.write_text("### 丁姐\n- **身份**: 测试名册条目\n", encoding="utf-8")
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
        _enqueue_pending("别的问题", "丁姐")
        with pytest.raises(SystemExit) as exc:
            cmd_add_correction(_args(from_text="萍姐", to_text="丁姐"))
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
            cmd_add_correction(_args(from_text="萍姐", to_text="丁姐"))
        assert exc.value.code == 2
        assert "--check-corpus" in capsys.readouterr().err

    def test_real_word_from_with_check_corpus_written(self, isolated_config, roster_with_target, tmp_path, capsys):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "a.md").write_text("萍姐没有出现，只是语料。", encoding="utf-8")
        cmd_add_correction(_args(
            from_text="萍姐", to_text="丁姐",
            check_corpus=True, corpus_dir=str(corpus), domain="demo",
        ))
        out = capsys.readouterr().out
        assert "Added: '萍姐' -> '丁姐' (domain: demo)" in out

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
                from_text="乙琳", to_text="乙林", review_note=None, domain="demo",
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
            from_text="乙琳", to_text="乙林",
            review_note="用户裁决 2026-09-16：以群 displayName 为准",
            check_corpus=True, corpus_dir=str(corpus), domain="demo",
        ))
        assert "Added: '乙琳' -> '乙林' (domain: demo)" in capsys.readouterr().out


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
        # The incident's entry point: accepting 乙琳→乙林 on 同段互证 alone.
        item_id = _enqueue_pending("乙琳", "乙林", kind="entity", evidence="同段互证")
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
            "乙琳", "乙霖", kind="entity",
            evidence="用户裁决 + 群 displayName 双读",
        )
        cmd_resolve_review(_args(resolve_review=item_id, review_decision="accepted"))
        item = _get_review_queue().get(item_id)
        assert item.status == "accepted"
        assert item.resolved_text == "乙霖"

    def test_override_to_someones_variant_refused(self, isolated_config, tmp_path, monkeypatch, capsys):
        # 乙林 registered ONLY as 乙霖's roster variant: overriding onto it is
        # refused and must point at 乙霖.
        roster = tmp_path / "people.md"
        roster.write_text(
            "### 乙霖\n- **身份**: 测试\n- **ASR 变体**: 乙林\n", encoding="utf-8",
        )
        monkeypatch.setenv("TRANSCRIPT_FIXER_PEOPLE_ROSTER", str(roster))
        item_id = _enqueue_pending("乙琳", "一琳", kind="entity", evidence="同段互证")
        with pytest.raises(SystemExit) as exc:
            cmd_resolve_review(_args(
                resolve_review=item_id, review_decision="overridden",
                review_override_to="乙林",
            ))
        assert exc.value.code == 2
        assert "乙霖" in capsys.readouterr().err
        assert _get_review_queue().get(item_id).status == "pending"

    def test_kept_original_not_gated(self, isolated_config):
        # kept_original writes no target form, so the guard does not fire even
        # on an incident-shaped pair.
        item_id = _enqueue_pending("乙琳", "乙林", kind="entity", evidence="同段互证")
        cmd_resolve_review(_args(
            resolve_review=item_id, review_decision="kept_original",
            review_note="original was right as spoken",
        ))
        assert _get_review_queue().get(item_id).status == "kept_original"


class TestUnobtainedAuthorityIsNotAuthority:
    """「需名册确认」「需听该段音频」引用了权威源类别却说它尚未取得——
    2026-09-20 队列审计：46 条 gated 行靠这个形状过了 branch (d)，其中一多半
    本该被拒（#746/#950/#945）。命名一个权威类 ≠ 拥有它。"""

    @pytest.mark.parametrize("text", [
        "需名册/音频确认 canonical",
        "需听该段音频",
        "待用户裁定",
        "未有音证",
        "等用户拍板后再改",
        "需查 roster 后再裁",
        "尚待名册确认",
        "要听音确认",
    ])
    def test_unobtained_citations_are_not_authority(self, text):
        assert evidence_names_authority(text) is False, f"误放行: {text!r}"

    @pytest.mark.parametrize("text", [
        "roster: 王晓明=东吴HK销售",
        "用户裁决 2026-09-20 以群 displayName 为准",
        "people roster 行 ### 汪晓明",
        "音证：clip 00:12:33 双引擎均识别为 X",
        "等名册查完再裁；people roster 行 ### 汪晓明",  # 前句未取得、后句已取得
    ])
    def test_obtained_citations_still_pass(self, text):
        assert evidence_names_authority(text) is True, f"误拦截: {text!r}"

    def test_gate_rejects_unobtained_authority_end_to_end(self, isolated_config, capsys):
        # 同一对 incident-shaped 词：evidence 说「需名册确认」时闸门必须拒。
        item_id = _enqueue_pending("乙琳", "一琳", kind="entity",
                                   evidence="疑此人，需名册确认 canonical")
        with pytest.raises(SystemExit) as exc:
            cmd_resolve_review(_args(
                resolve_review=item_id, review_decision="overridden",
                review_override_to="乙林",
            ))
        assert exc.value.code == 2
        assert _get_review_queue().get(item_id).status == "pending"


class TestResolveAuthorityChannel:
    """--authority：裁决时才取得的权威（音频核验、审阅中的用户裁定）必须能
    进 guard。evidence 列曾是入队时一次性写入，导致 67 条活行死锁——
    reopen 后仍是 pending，唯一能让目标变 claimed 的 --add 又被 pending-conflict
    拦住（2026-09-20 实证）。--authority 追加进 evidence（带审计）后再过闸。"""

    def test_authority_flag_unblocks_gate_and_lands(self, isolated_config):
        item_id = _enqueue_pending("王晓琳", "汪晓明", kind="entity",
                                   evidence="同段互证")
        # 无 --authority：被 target_unknown 拒，行保持 pending
        with pytest.raises(SystemExit) as exc:
            cmd_resolve_review(_args(
                resolve_review=item_id, review_decision="accepted",
                review_note="多数派都这么写",
            ))
        assert exc.value.code == 2
        assert _get_review_queue().get(item_id).status == "pending"
        # 带 --authority：用户裁定是合法权威源，写入放行
        cmd_resolve_review(_args(
            resolve_review=item_id, review_decision="accepted",
            review_authority="用户 2026-09-21 裁定：以群 displayName 为准",
            review_note="多数派都这么写",
        ))
        item = _get_review_queue().get(item_id)
        assert item.status == "accepted"
        assert "用户 2026-09-21 裁定" in (item.evidence or "")

    def test_note_alone_does_not_feed_the_gate(self, isolated_config, capsys):
        # --note 是理由不是权威源：把权威字样写进 note 不该放行（文档曾承诺
        # --note 可以，代码从未实现——那个承诺是这次修复要消灭的不一致）。
        item_id = _enqueue_pending("王晓琳", "汪晓明", kind="entity", evidence="同段互证")
        with pytest.raises(SystemExit) as exc:
            cmd_resolve_review(_args(
                resolve_review=item_id, review_decision="accepted",
                review_note="用户裁决：就是这个",
            ))
        assert exc.value.code == 2

    def test_attach_authority_command_appends_without_verdict(self, isolated_config):
        item_id = _enqueue_pending("王晓琳", "汪晓明", kind="entity", evidence="同段互证")
        cmd_attach_authority(_args(
            attach_authority=item_id,
            authority_text="音证 2026-09-21：tight 窗双引擎含建议词",
            review_by="verify_queue_audio",
        ))
        item = _get_review_queue().get(item_id)
        assert item.status == "pending"          # 没有顺手录裁决
        assert "音证 2026-09-21" in item.evidence
        assert "同段互证" in item.evidence        # 追加，不覆盖
