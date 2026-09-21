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


class TestUnobtainedWindowIsNotACharacterCount:
    """判据必须是「什么算未取得」，不能是「离得多近算未取得」。

    第一版用 `(?:需|待|未|尚|等|要|请|盼)[^。；;，,\\n]{0,6}$` 在权威名词**前面
    6 字**里找 need-marker——那个宽度是任意的，留下的是这道闸门立命要关的那类
    事故本身：2026-09-16 多数派收敛形状只要换个长点的连接词、或换成英文就原样
    穿过。下面每一条都在 incident 原配（乙琳→乙林 + lookup 全 False）上实测过
    放行，即闸门对同一起事故形状失效。"""

    # 假放行：每条都命名了权威源类别，同时声明它尚未取得。
    FALSE_PASSES = [
        "需先与用户当面确认群昵称",              # 需 与 群昵称 隔 9 字
        "需要先去听完整的那一段音频再判断",        # 隔 11 字
        "需再向群里的群主本人确认群昵称后再定",
        "pending roster confirmation",           # 英文，一个中文 marker 都没有
        "TBD 群昵称 double-read",                # 同上
        "需向该段音频的录音人核对音频后判定",
    ]

    @pytest.mark.parametrize("evidence", FALSE_PASSES)
    def test_long_connector_still_counts_as_unobtained(self, evidence):
        # 判据本身
        assert evidence_names_authority(evidence) is False, f"误放行: {evidence!r}"

    @pytest.mark.parametrize("evidence", FALSE_PASSES)
    def test_gate_refuses_every_false_pass_end_to_end(self, evidence, isolated_config, capsys):
        # 端到端：同样的 incident 原配，必须拒、且什么都不写
        item_id = _enqueue_pending("乙琳", "乙林", kind="entity", evidence=evidence)
        with pytest.raises(SystemExit) as exc:
            cmd_resolve_review(_args(
                resolve_review=item_id, review_decision="accepted",
            ))
        assert exc.value.code == 2, f"放行了: {evidence!r}"
        assert _get_review_queue().get(item_id).status == "pending"

    def test_already_obtained_roster_citation_next_to_a_pending_one_passes(self):
        # 反向假拒（fail-closed 方向，不危险但白拦合法写入）：前半句说「待用户
        # 裁定」，后半句是**已取得**的 roster ### 引用。模块的既有原则是「任何
        # 一条无阻碍的引用就够」，所以这条必须放——一个只数字数的判据会把整个
        # 子句都算成未取得。
        assert evidence_names_authority("待用户裁定 roster 行 ### 王晓明") is True

    def test_short_chinese_unobtained_still_refused(self):
        # 修好窗口后，最短的中文未取得形状不能反被放过
        assert evidence_names_authority("需名册确认") is False

    def test_obtained_authority_still_passes(self):
        assert evidence_names_authority("roster 行 ### 王晓明") is True

    def test_marker_after_the_noun_governs_it_too(self):
        # 「名册需确认」的 marker 在名词**后面**——旧实现只看名词前面的文本，
        # 这种形状整个漏掉。
        assert evidence_names_authority("名册需确认") is False

    def test_pending_clause_then_obtained_clause_still_passes(self):
        # 子句边界是句读，不是空格：前一句未取得、后一句已取得 = 放行
        assert evidence_names_authority(
            "需名册确认，people roster 行 ### 汪晓明") is True

    def test_colon_does_not_end_a_pending_claim(self):
        # 冒号不是子句边界：「用户裁定：需先听音频确认」整体仍是未取得
        assert evidence_names_authority("用户裁定：需先听音频确认") is False


class TestMarkerGovernsNounAcrossCitationBoundary:
    """残余漏管：marker 出现在权威名词**后面**、中间只隔着一个「引用完结空白」时，
    边界规则把两者切断，名词没人管 → 放行。

    b37e0c93（本轮修复前）用 22 个对抗输入攻出的 3 个漏管全是这个形状：

        roster 需确认        -> E=True  (放行，错)
        dashboard 听音待核   -> E=True  (放行，错)
        群昵称 TBD           -> E=True  (放行，错)

    而同形中文「名册需确认」（名词内部无空白）一直拒得对。修法：边界规则让某个
    marker 一个名词都够不着时（名词全在它身后、只隔着完结空白），它管住全部名词。

    这个补丁只会把放行变成拒绝、不会反过来，所以健康侧（下面 OBTAINED）在修复
    前后都必须是 True——它们钉的是「别顺手误拦已取得的引用」。真正的「修复前
    失败」用例是 FALSE_PASSES 里标 ★ 的那些。
    """

    # 危险侧：命名了权威源类别，同时声明它尚未取得。★ = 修复前实测放行。
    FALSE_PASSES = [
        "roster 需确认",                  # ★ 本轮 3 个漏管之一
        "dashboard 听音待核",             # ★
        "群昵称 TBD",                     # ★
        "未取得名册",
        "needs roster confirmation",
        "awaiting the roster line",
        "名册 displayName 需确认",         # ★ 两个名词被同一个尾部 marker 切断
        "displayName 待核",               # ★
        "StepFun 待确认",                 # ★
        "roster TBD",                     # ★ 英文名词 + 英文尾部 marker
        "群昵称 pending",                 # ★ 中文名词 + 英文尾部 marker
        "dashboard 需再听一遍",            # ★ 名词 + 尾部 marker + 长连接词
        "音证 待补",                      # ★
        "音频 需确认",                    # ★
        "需名册确认；roster TBD",          # ★ 两个子句各自未取得
        "群昵称双读 roster 需确认",        # ★ 无标点，整句按 fail-closed 读作未取得
        "请确认名册",
        "盼名册确认",
        "尚无名册",
        "等名册",
        "to be confirmed: roster",
        "unconfirmed roster entry",
    ]

    # 健康侧：至少一条无阻碍的已取得引用，必须继续放行。
    OBTAINED = [
        "roster 行 ### 王晓明",
        "群 displayName+nickName 双读",
        "用户 2026-09-21 裁定",
        "音证 2026-09-21",
        "dashboard 听音",
        "待用户裁定 roster 行 ### 王晓明",
        "需确认；名册",
        "需确认，名册",
        "用户裁定；roster 行 ### 王晓明",
        "音证",
        "需先听音频再定，音证 2026-09-21",
        "需先听音频再定。音证 2026-09-21",
        "roster",
        "等名册查完再裁；people roster 行 ### 汪晓明",
        "群昵称双读，roster 需确认",           # 逗号分句，前句已取得
        "名册 displayName 需确认，roster 行 ### 王晓明",
        "roster 需名册确认",                    # marker 夹在两个名词之间
        "音证 2026-09-21：需先听音频再定",      # 冒号不分句：音证已取得
        "已取得 roster 行 ### 王晓明；需名册确认",
        "名册需确认，people roster 行 ### 汪晓明",
    ]

    @pytest.mark.parametrize("evidence", FALSE_PASSES)
    def test_marker_behind_a_boundary_still_refuses(self, evidence):
        assert evidence_names_authority(evidence) is False, f"误放行: {evidence!r}"

    @pytest.mark.parametrize("evidence", OBTAINED)
    def test_obtained_citations_survive_the_fallback(self, evidence):
        assert evidence_names_authority(evidence) is True, f"误拦截: {evidence!r}"

    @pytest.mark.parametrize("evidence,want_refusal", [
        (e, True) for e in FALSE_PASSES
    ] + [
        (e, False) for e in OBTAINED
    ])
    def test_incident_pair_end_to_end_matches_the_criterion(self, evidence, want_refusal):
        # 事故原配 + lookup 全 False：判据说拒就必须 GuardRejection，说放就必须 None。
        r = guard("乙琳", "乙林", evidence, "entity", lookup_fn=lambda t: _lookup())
        if want_refusal:
            assert isinstance(r, GuardRejection), f"放行了: {evidence!r}"
            assert r.code == "target_unknown"
        else:
            assert r is None, f"误拦截: {evidence!r}"

    @pytest.mark.parametrize("evidence", ["roster 需确认", "dashboard 听音待核", "群昵称 TBD"])
    def test_gate_refuses_the_three_residual_leaks_end_to_end(
        self, evidence, isolated_config, capsys
    ):
        # CLI 级：同一条 incident-shaped 行，被拒且什么都不写
        item_id = _enqueue_pending("乙琳", "乙林", kind="entity", evidence=evidence)
        with pytest.raises(SystemExit) as exc:
            cmd_resolve_review(_args(
                resolve_review=item_id, review_decision="accepted",
            ))
        assert exc.value.code == 2, f"放行了: {evidence!r}"
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


class TestResolveRejectsAttachAuthorityCombination:
    """`--attach-authority` 与 `--resolve-review` 写在同一条命令里，曾是最自然的
    「核验完了，顺手裁掉」写法，却得到 exit 0 而裁决从未记录：分派把
    attach_authority 排在 resolve_review **之前**，于是只跑了追加、打印 ✅、
    status 仍是 pending。实测（PR head 61ee8781）：

        ✅ #1 evidence 追加权威源（未记录裁决）   exit=0
        --- status after: pending

    「成功了但什么都没裁」比报错更难发现，所以两个 flag 同现必须拒绝，而不是
    静默选一个。"""

    def test_both_flags_refused_and_nothing_written(
        self, isolated_config, monkeypatch, capsys
    ):
        import fix_transcription

        item_id = _enqueue_pending("王晓琳", "汪晓明", kind="entity", evidence="同段互证")
        monkeypatch.setattr(sys, "argv", [
            "fix_transcription.py",
            "--attach-authority", str(item_id),
            "--authority-text", "音证：tight 窗含建议词",
            "--resolve-review", str(item_id),
            "--decision", "accepted",
            "--by", "probe",
        ])
        with pytest.raises(SystemExit) as exc:
            fix_transcription.main()
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "--attach-authority" in err and "--resolve-review" in err
        after = _get_review_queue().get(item_id)
        assert after.status == "pending", "裁决不许被顺带记录"
        assert after.evidence == "同段互证", "连 authority 追加都不该发生"

    def test_each_flag_alone_still_works(self, isolated_config, monkeypatch, capsys):
        # 拆成两条命令是文档给的修法，必须真的能跑通
        import fix_transcription

        item_id = _enqueue_pending("王晓琳", "汪晓明", kind="entity", evidence="同段互证")
        monkeypatch.setattr(sys, "argv", [
            "fix_transcription.py",
            "--attach-authority", str(item_id),
            "--authority-text", "用户 2026-09-21 裁定：以群 displayName 为准",
            "--by", "probe",
        ])
        fix_transcription.main()
        assert "用户 2026-09-21 裁定" in _get_review_queue().get(item_id).evidence
        monkeypatch.setattr(sys, "argv", [
            "fix_transcription.py",
            "--resolve-review", str(item_id),
            "--decision", "accepted",
            "--by", "probe",
        ])
        fix_transcription.main()
        assert _get_review_queue().get(item_id).status == "accepted"


class TestRefusedVerdictLeavesNoSideEffects:
    """闸门拒绝必须**先于**副作用。

    曾经的顺序是「先 `attach_evidence` 再做 name-convergence 校验」，于是一次
    **被拒**的裁决也在 evidence 列永久留下「权威已挂载」，并多一条
    `review_evidence_attach` 审计行——而审计行本身看不出对应的裁决被拒了。
    不构成放行洞，但审计记录从此说谎。"""

    def _audit_actions(self, item_id: int) -> list[str]:
        import sqlite3
        from utils.config import get_config
        conn = sqlite3.connect(get_config().database.path)
        try:
            return [r[0] for r in conn.execute(
                "SELECT action FROM audit_log WHERE entity_id = ? ORDER BY id",
                (item_id,),
            )]
        finally:
            conn.close()

    def test_refused_authority_writes_neither_evidence_nor_audit(
        self, isolated_config, capsys
    ):
        item_id = _enqueue_pending("王晓琳", "汪晓明", kind="entity", evidence="疑此人")
        assert self._audit_actions(item_id) == ["review_enqueue"]
        with pytest.raises(SystemExit) as exc:
            cmd_resolve_review(_args(
                resolve_review=item_id, review_decision="accepted",
                review_authority="需名册确认", review_by="probe",
            ))
        assert exc.value.code == 2
        after = _get_review_queue().get(item_id)
        assert after.status == "pending"
        assert after.evidence == "疑此人", "evidence 列必须一字节不动"
        assert "[authority" not in (after.evidence or "")
        assert self._audit_actions(item_id) == ["review_enqueue"], \
            "不许留下一条看不出裁决被拒的 review_evidence_attach"

    def test_obtained_authority_still_lands_when_the_gate_passes(
        self, isolated_config
    ):
        # 调整顺序不能把 --authority 这个通道一起修坏：闸门放行时追加照旧发生，
        # 且带审计。
        item_id = _enqueue_pending("王晓琳", "汪晓明", kind="entity", evidence="同段互证")
        cmd_resolve_review(_args(
            resolve_review=item_id, review_decision="accepted",
            review_authority="用户 2026-09-21 裁定：以群 displayName 为准",
            review_by="probe",
        ))
        item = _get_review_queue().get(item_id)
        assert item.status == "accepted"
        assert "用户 2026-09-21 裁定" in item.evidence
        assert self._audit_actions(item_id) == [
            "review_enqueue", "review_evidence_attach", "review_resolve",
        ]
