"""Tests for scripts.harvest_corrections — native-pass -> trap-candidate harvest.

Fixtures model the 2026-08-22 某支付域 transcript fixes (the session that
motivated the tool): CJK entity traps need their disambiguating neighbor
char (云国 not 缺陷), glue chars mark word boundaries, Latin runs must
never be cut mid-token, and every emitted bullet must round-trip through
core.trap_scanner's real parser.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harvest_corrections import (  # noqa: E402
    _bullet,
    _candidates_from_pair,
    _common_affixes,
    _expand,
    _keep,
    _latin_cut,
    _parses,
    _quote,
    harvest,
)


def _cands(raw: str, new: str) -> list[tuple[str, str]]:
    from harvest_corrections import _extract_pairs
    out = []
    for f, t in _extract_pairs(raw, new):
        out.extend(_candidates_from_pair(f, t))
    return out


class TestCandidateGranularity:
    """The seven shapes from the real 某支付域 pair."""

    def test_two_entity_fixes_in_one_clause_split(self):
        got = _cands("我拿云信信去蓝活通开出来一个商户号", "我拿云果去蓝付通开出来一个商户号")
        assert ("云信信", "云果") in got
        assert ("蓝活通", "蓝付通") in got

    def test_neighbor_char_survives(self):
        got = _cands("域名是以云国为主", "域名是以云果为主")
        assert ("云国", "云果") in got
        assert ("缺陷", "确幸") not in got
        assert ("以云国", "以云果") not in got

    def test_glue_char_vetoes_left_right_still_grows(self):
        # 去 is glue on the left; the completer 通 on the right must win.
        got = _cands("去蓝活通官方", "去蓝付通官方")
        assert ("蓝活通", "蓝付通") in got
        assert ("去生活", "去盛付") not in got

    def test_right_truncation_is_substring_consistent(self):
        got = _cands("我是有一个三溪支付的文档站", "我是有一个三江智付的文档站")
        assert ("三溪支", "三江智") in got  # 截短形：子串替换下自洽

    def test_mixed_span_trims_cjk_affixes(self):
        got = _cands("docs 点云小星派还没部署上去", "docs 点example还没部署上去")
        assert ("云小星派", "example") in got

    def test_latin_run_never_cut(self):
        got = _cands("我没走那unifyorder", "我没走那unifyOrder")
        assert ("unifyorder", "unifyOrder") in got
        assert ("nifyorder", "nifyOrder") not in got

    def test_spoken_domain_span_kept_whole(self):
        got = _cands("merchant 点云国派点cn", "mch.example.com")
        assert len(got) == 1
        f, t = got[0]
        assert "merchant" in f and "mch" in t


class TestKeepFilter:
    def test_punct_only_dropped(self):
        assert not _keep("，", "。")
        assert not _keep("点", ".")

    def test_to_punct_dropped(self):
        assert not _keep("云果派", "，")

    def test_identical_dropped(self):
        assert not _keep("abc", "abc")

    def test_overlong_dropped(self):
        assert not _keep("超" * 25, "短")
        assert not _keep("短", "超" * 25)

    def test_real_term_kept(self):
        assert _keep("云国", "云果")


class TestExpand:
    def test_grows_to_min_len(self):
        cnt = "恒阳科技".count
        assert _expand("阳", "央", "恒", "科技", cnt) == ("恒阳科", "恒央科")

    def test_glue_stops_growth(self):
        # 两侧都是黏着字时保持短形，不硬凑长度
        f, t = _expand("缺陷", "确幸", "的", "这个", lambda s: 0)
        assert f == "缺陷"

    def test_frequency_oracle_picks_recurring_side(self):
        # 器蓝活出现 1 次、蓝活通出现 3 次 → 向右扩展
        raw = "器蓝活通。又说蓝活通。还是蓝活通。"
        f, t = _expand("蓝活", "蓝付", "器", "通", raw.count)
        assert (f, t) == ("蓝活通", "蓝付通")

    def test_frequency_oracle_left_when_left_dominant(self):
        raw = "云国，云国，国为"
        f, t = _expand("国", "果", "云", "为", raw.count)
        assert (f, t) == ("云国", "云果")

    def test_tie_goes_left_deterministic(self):
        # 同分回退左侧（确定性兜底）——count=1 时语料无法判断哪侧邻居属于
        # 词，可能带出一个游离邻字，由裁决环节人工修齐（见 _expand docstring）
        f, t = _expand("阳", "央", "恒", "科技", lambda s: 1)
        assert (f, t) == ("恒阳科", "恒央科")


class TestLatinCut:
    def test_mid_run(self):
        assert _latin_cut("merchant", 3)

    def test_boundary_ok(self):
        assert not _latin_cut("merchant 点", 9)

    def test_common_affixes_reextend(self):
        p, s = _common_affixes("unifyorder", "unifyOrder")
        assert p == 0  # 'o|O' 切进词内 → 回退到 0


class TestQuoteAndParses:
    def test_bare_unquoted(self):
        assert _quote("云国") == "云国"

    def test_space_backticked(self):
        assert _quote("test scale") == "`test scale`"

    def test_emitted_bullets_roundtrip(self):
        for f, t in [("云国", "云果"), ("`test scale`", "tailscale"),
                     ("三溪支", "三江智")]:
            bullet = f"- **{_quote(f)} → {_quote(t)}** — cue"
            assert _parses(bullet), bullet


class TestHarvestEndToEnd:
    RAW = "我去蓝物通开了一个云国的号，test scale 连上了，云国为主"
    NEW = "我去蓝付通开了一个云果的号，tailscale 连上了，云果为主"

    def test_counts_and_fields(self):
        out, _ = harvest(self.RAW, self.NEW)
        by_from = {c["from"]: c for c in out}
        assert by_from["云国"]["fixed"] == 2
        assert by_from["蓝物通"]["to"] == "蓝付通"
        assert by_from["test scale"]["to"] == "tailscale"
        assert by_from["云国"]["raw_occurrences"] == 2
        assert by_from["云国"]["remaining"] == 0

    def test_clustering_absorbs_wider_form(self):
        # merchant 点云国派点 是 Latin 保护留下的宽形；并入窄形 云国派点
        raw = "merchant 点云国派点cn，云国派点"
        new = "mch.example.com，example."
        out, _ = harvest(raw, new)
        by_from = {c["from"]: c for c in out}
        assert "云国派点" in by_from
        assert not any("merchant" in f for f in by_from)
        assert by_from["云国派点"]["fixed"] == 2

    def test_same_from_different_to_not_merged(self):
        # from 相同、to 不同 = 两个不同修正，各自呈现（分隔符不变才能切开）
        raw = "云小星派，云小星派"
        new = "example，example.com"
        out, _ = harvest(raw, new)
        tos = {c["to"] for c in out if c["from"] == "云小星派"}
        assert tos == {"example", "example.com"}

    def test_multi_change_cjk_run_with_latin_target_stays_whole(self):
        # 已知边界：一个 CJK run 内两处改动且目标是 Latin 时无法切分
        # （old 侧是单个 token），整段作为一条候选呈现，交给人工裁决
        out, _ = harvest("云小星派和云小星派", "example和example.com")
        assert len(out) == 1
        assert out[0]["from"] == "云小星派和云小星派"

    def test_remaining_flagged(self):
        out, _ = harvest("code 和 code", "Code 和 code")
        code = next(c for c in out if c["from"] == "code")
        assert code["remaining"] == 1


class TestReviewFixes20260823:
    """独立审阅 2026-08-23 的回归网——每条对应一个实测发现。"""

    def test_cross_paragraph_fused_region_recovers_term(self):
        # HIGH-1：实体+标点+段落相邻修改熔合，term 对必须回收、不产生
        # 含换行的不可解析 bullet（原形态 exit 2 杀全批）
        out, _ = harvest("云国。\n\n新话题开始", "云果，旧话题结束")
        froms = [c["from"] for c in out]
        assert "云国" in froms
        assert all("\n" not in f for f in froms)

    def test_bare_numbers_dropped(self):
        # HIGH-3：费率/日期/错误码修正是数据不是词汇
        for raw, new in [("费率 3 个点", "费率 2 个点"),
                         ("日期 21 号", "日期 22 号"),
                         ("错误码 401 要处理", "错误码 402 要处理")]:
            out, _ = harvest(raw, new)
            assert not any(c["from"].isdigit() for c in out), raw

    def test_slash_pair_dropped(self):
        # MED-6：/ 在 FROM 会被 parser 拆成多 variant，无法表达 → 丢弃
        out, _ = harvest("接口是 API/SDK 两套", "接口是 REST-GRPC 两套")
        assert not any("/" in c["from"] for c in out)

    def test_substring_fusion_dropped(self):
        # MED-5 变体：插入型错位（你好→你好世界）不是替换修正
        out, _ = harvest("他说：你好，世界。", "他说：你好世界。")
        assert not any(c["from"] == "你好" for c in out)

    def test_phantom_alignment_dropped(self):
        # MED-5：TO 在 raw 已存在 + FROM 在 corrected 残留 = 对齐幻影
        out, _ = harvest("他说：你好，世界。然后走了；真的。",
                         "他说：你好世界，然后走了；真的。")
        assert not any(c["to"] == "然后走了" for c in out)

    def test_fragmentation_converges(self):
        # MED-7：同一 trap 的不同左邻字不再碎裂，计数合并到高频形
        out, _ = harvest("器蓝活通在用。又说蓝活通。还是蓝活通。",
                         "器蓝付通在用。又说蓝付通。还是蓝付通。")
        top = out[0]
        assert (top["from"], top["to"]) == ("蓝活通", "蓝付通")
        assert top["fixed"] == 3

    def test_trailing_punct_stripped(self):
        # LOW-12：口述域名修正的 TO 不带游离句号
        out, _ = harvest("merchant 点云小星派点cn。", "mch.example.com。")
        assert all(not c["to"].endswith(".") for c in out)

    def test_bare_cjk_marked(self):
        # MED-8：两侧黏着字扩不动的裸形被标记（--write 跳过）
        out, _ = harvest("它的缺陷。", "它的确幸。")
        bare = [c for c in out if c["bare"]]
        assert any(c["from"] == "缺陷" for c in bare)

    def test_dropped_count_reported(self):
        _, dropped = harvest("费率 3 个点", "费率 2 个点")
        assert dropped >= 1

    def test_end_to_end_punct_only_yields_nothing(self):
        # 审阅指出的集成层缺口：纯标点修改端到端必须零候选
        out, _ = harvest("他说：你好，世界。然后走了；真的。第二段，没什么。",
                         "他说：你好世界，然后走了；真的。第二段，没什么。")
        assert out == []


class TestRound2Fixes20260823:
    """二轮审阅（修复引入的新问题）回归网。"""

    def test_partially_fixed_real_trap_survives(self):
        # R2-HIGH-1：部分修复 + 正确形在 raw 预存在 = 真 trap，必须存活
        # （旧幻影过滤把它和「残留>0 要 surfaced」的设计一起杀死）
        out, _ = harvest("蓝活通开户。蓝付通不错。蓝活通也行。",
                         "蓝付通开户。蓝付通不错。蓝活通也行。")
        assert any(c["from"] == "蓝活通" and c["remaining"] == 1 for c in out)

    def test_long_latin_quoted_no_exit2(self):
        # R2-HIGH-2：13-24 字 Latin 候选加反引号走 explicit-literal 路径，
        # 产出的每条 bullet 都能过真 parser（不再触发 exit 2）
        out, _ = harvest("走paypalstandard通道", "走stripecheckout通道")
        assert out and all(_parses(_bullet(c["from"], c["to"], "cue")) for c in out)

    def test_to_interior_punct_rejected(self):
        # R2-HIGH-2 触发形 2：TO 含句读 → parser 硬拒 → 提前在 _keep 丢弃
        out, _ = harvest("他说axc了", "他说a。b了")
        assert not any("。" in c["to"] for c in out)

    def test_verb_glue_blocked(self):
        # R2-HIGH-3：用 已入黏着字集——用蓝活→用蓝付 不再生成，右补全胜出
        out, _ = harvest("我说用蓝活通付款很快", "我说用蓝付通付款很快")
        assert any(c["from"] == "蓝活通" for c in out)
        assert not any(c["from"] == "用蓝活" for c in out)

    def test_bare_never_absorbs_good(self):
        # R2-MED-4：裸形不作吸收方——好候选与裸形并列呈现，不被吞
        out, _ = harvest("它的缺陷很大。域名是云国为主。",
                         "它的确幸很大。域名是云果为主。")
        froms = [c["from"] for c in out]
        assert "云国" in froms

    def test_dedup_symmetric_containment(self):
        # R2-LOW-6：已知宽 trap 也吞窄候选（恒阳科技 覆盖 恒阳）
        import tempfile, subprocess
        with tempfile.TemporaryDirectory() as d:
            ctx = f"{d}/ctx.md"
            with open(ctx, "w") as fh:
                fh.write("- **恒阳科技 → 恒央科技** — 已有\n")
            raw_f, new_f = f"{d}/r.md", f"{d}/n.md"
            with open(raw_f, "w") as fh:
                fh.write("他说恒阳的事。")
            with open(new_f, "w") as fh:
                fh.write("他说恒央的事。")
            r = subprocess.run(
                ["uv", "run", "scripts/harvest_corrections.py", raw_f, new_f,
                 "--context-file", ctx],
                capture_output=True, text=True,
                cwd=str(Path(__file__).resolve().parent.parent.parent))
            assert "恒阳" not in r.stdout or "已跳过 context 已有 trap" in r.stdout

    def test_split_fused_recovers_and_no_unparsable(self):
        # R2-MED-5 补充：fused 区域的每条产出 bullet 都必须可解析
        out, _ = harvest("云国。\n\n新话题开始", "云果，旧话题结束")
        assert out and all(_parses(_bullet(c["from"], c["to"], "cue")) for c in out)
