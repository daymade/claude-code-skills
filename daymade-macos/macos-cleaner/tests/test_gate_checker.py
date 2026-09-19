#!/usr/bin/env python3

"""Tests for the Phase 2 entry-gate checker.

Run with:
    uv run python3 -m unittest discover -s tests -v
    uv run python3 tests/test_gate_checker.py

The two calibration classes at the bottom are the load-bearing ones. They run
the checker over real historical outputs — a plan that passed an independent
review, and the report whose failures the gate was written to catch — because a
checker that only passes its own unit tests proves nothing about whether it
catches the failure it exists for, or whether it would block a healthy plan.
"""

import importlib.util
import io
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'check_gate_plan.py'
SPEC = importlib.util.spec_from_file_location('check_gate_plan', SCRIPT_PATH)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)

# The corpus lives in the bundle so anyone can re-run the calibration without
# the replay workspace. It is copied verbatim from the 2026-09-19 outputs except
# that machine identity and absolute home paths are replaced with placeholders
# (`~/`, Example Mac — the repo's gitleaks rule flags any /Users/<name>/ form):
# the shapes the checker parses are unchanged and
# path basenames still carry the tokens the matching depends on. Because the
# copies are in the repo, a checker change that breaks them fails here rather than
# relying on someone's memory of what the corpus used to say.
CORPUS = Path(__file__).resolve().parent / 'fixtures' / 'corpus'
KNOWN_GOOD = CORPUS / 'known-good-arm1.md'
KNOWN_BAD = CORPUS / 'known-bad-original.md'
ROUND2_TABLE = CORPUS / 'known-good-round2-table.md'
ROUND2_PLAN = CORPUS / 'known-good-round2-plan.md'
ROUND2_ZAI_TABLE = CORPUS / 'known-good-zai.md'


def run_checker(*arguments):
    output = io.StringIO()
    with redirect_stdout(output):
        code = CHECKER.main(list(arguments))
    return code, output.getvalue()


def table_of(text):
    return CHECKER.parse_tables(text)[0]


class NormalizeTests(unittest.TestCase):
    def test_markdown_noise_is_stripped(self):
        self.assertEqual(
            'uv cache | downloaded | keep unless approved',
            CHECKER.normalize('uv cache \\| `downloaded` \\| **keep unless approved**'))

    def test_code_fence_markers_do_not_break_a_cross_fence_quote(self):
        # cleanup_targets.md puts the command in a fenced block under the
        # sentence; a plan quotes the two as one continuous rule.
        reference = ('**Cleanup after the redownload impact is approved**:\n'
                     '```bash\npip cache purge\n```\n')
        self.assertEqual(
            'Cleanup after the redownload impact is approved: pip cache purge',
            CHECKER.normalize(reference))

    def test_whitespace_is_collapsed(self):
        self.assertEqual('a b c', CHECKER.normalize('a\n  b\tc'))


class QuoteSegmentTests(unittest.TestCase):
    def test_ellipsis_splits_a_quote_into_independently_checked_parts(self):
        cell = '"Never replace this narrow target ... exact redownload approval."'
        self.assertEqual(
            ['Never replace this narrow target',
             'exact redownload approval.'],
            CHECKER.quote_segments(cell))

    def test_no_rule_found_is_not_checked_as_a_quote(self):
        self.assertEqual([], CHECKER.quote_segments('"no rule found"'))

    def test_escaped_quotes_inside_a_quote_survive(self):
        # The dangling-volume rule quotes a phrase of its own inside the quote.
        cell = r'"\"Not referenced by any current container\" is tempting."'
        self.assertEqual(
            ['"Not referenced by any current container" is tempting.'],
            CHECKER.quote_segments(cell))

    def test_an_apostrophe_pair_is_not_a_quotation(self):
        # The same rule's real wording ends "... they're safe to remove. **It
        # isn't**: ..." — read naively, the two apostrophes invent a segment
        # ("re safe to remove. It isn") and the check verifies a fragment that
        # exists in the reference while the real quote went unchecked.
        cell = ('"Not referenced by any container is tempting to treat as '
                "sufficient evidence they're safe to remove. **It isn't**.\"")
        self.assertEqual(
            ['Not referenced by any container is tempting to treat as sufficient '
             "evidence they're safe to remove. It isn't."],
            CHECKER.quote_segments(cell))

    def test_curly_quotes_are_recognized(self):
        self.assertEqual(
            ['Keep when tests or automation use Playwright'],
            CHECKER.quote_segments('“Keep when tests or automation use Playwright”'))


class VerdictTests(unittest.TestCase):
    def test_negated_marker_beats_the_positive_substring(self):
        # 不入动作集 contains 入动作集, and "not in action set" contains
        # "in action set": the negated form has to win or every PRESERVE row
        # reads as a proposal.
        row = table_of('| Candidate | Verdict |\n|---|---|\n'
                       '| `~/.cache/uv` | 不入动作集，除非你接受 |\n')
        self.assertEqual('not in action set', CHECKER.row_verdict(row.rows[0].cells))

    def test_chinese_positive_marker(self):
        row = table_of('| Candidate | Verdict |\n|---|---|\n| `_npx` | **入动作集** |\n')
        self.assertEqual('in action set', CHECKER.row_verdict(row.rows[0].cells))

    def test_english_markers(self):
        row = table_of('| Candidate | Verdict |\n|---|---|\n'
                       '| a | in action set |\n| b | not in action set |\n'
                       '| c | unlocked by user |\n')
        self.assertEqual(
            ['in action set', 'not in action set', 'unlocked by user'],
            [CHECKER.row_verdict(item.cells) for item in row.rows])

    def test_zai_dongzuoji_is_a_positive_marker(self):
        # An agent wrote the verdict as 在动作集 rather than 入动作集. Reading it
        # as no-verdict made the action set silently unchecked while the checker
        # still printed a green light.
        row = table_of('| 候选 | 裁决 |\n|---|---|\n| `_npx` | **在动作集** |\n')
        self.assertEqual('in action set', CHECKER.row_verdict(row.rows[0].cells))

    def test_bu_zai_dongzuoji_is_a_negated_marker(self):
        row = table_of('| 候选 | 裁决 |\n|---|---|\n| `~/.cache/uv` | 不在动作集 |\n')
        self.assertEqual('not in action set', CHECKER.row_verdict(row.rows[0].cells))

    def test_a_table_with_no_readable_verdict_fails_closed(self):
        # Green on an unchecked action set is worse than a false alarm: it
        # teaches the reader that this PASS means something it does not.
        gate = ('| 候选 | 类别 | 裁决 |\n|---|---|---|\n'
                '| `~/.npm/_npx` | **PROPOSABLE** | 待确认 |\n'
                '| `~/Library/Caches/pip` | **REBUILDABLE** | 待你回复 |\n')
        result = CHECKER.check_action_set_classes(CHECKER.collect_gate_rows(gate))
        self.assertFalse(result.passed)
        self.assertIn('verdict column unrecognized', '\n'.join(result.details))
        self.assertIn('在动作集', '\n'.join(result.details))

    def test_a_table_with_some_unreadable_verdicts_still_passes(self):
        gate = ('| 候选 | 类别 | 管辖规则 | 裁决 |\n|---|---|---|---|\n'
                '| `~/.npm/_npx` | **PROPOSABLE** | "`_npx` may go to Trash after '
                'confirming no `npx` process." | **入动作集** |\n'
                '| `~/Library/Caches/pnpm` | **USER-DECISION** | no rule found | 等你定 |\n')
        result = CHECKER.check_action_set_classes(CHECKER.collect_gate_rows(gate))
        self.assertTrue(result.passed, result.details)
        self.assertIn('state no action-set position', '\n'.join(result.details))

    def test_class_is_found_by_content_not_by_header(self):
        # Agents translate the template, so the columns do not keep their names.
        row = table_of('| 候选 | 类别 |\n|---|---|\n'
                       '| `~/.npm/_npx` | **PROPOSABLE** |\n')
        self.assertEqual('PROPOSABLE', CHECKER.row_class(row.rows[0].cells))


class CommandExtractionTests(unittest.TestCase):
    PLAN = '\n'.join([
        '## Tool verification',
        '',
        '- `brew cleanup -s -n` was run read-only: brew 7.0.1, see --help.',
        '- 未跑 `npm cache clean`.',
        '- never ran `uv cache prune`.',
        '- `docker rmi abc123` verified against docker 29.4.0 with --filter.',
        '',
        '| # | 命令 | 精确目标 |',
        '|---|---|---|',
        '| 1 | `pip cache purge` | pip 缓存 |',
        '',
        '```bash',
        'rm -rf /tmp/gone',
        '```',
    ])

    def test_dry_run_is_not_a_destructive_command(self):
        commands = CHECKER.find_destructive_commands(self.PLAN)
        self.assertFalse(any('cleanup -s -n' in command.text for command in commands))

    def test_declared_unused_command_is_not_a_proposal(self):
        commands = CHECKER.find_destructive_commands(self.PLAN)
        self.assertFalse(any('npm cache clean' in command.text for command in commands))
        self.assertFalse(any('uv cache prune' in command.text for command in commands))

    def test_a_line_mixing_an_exclusion_with_a_real_command_is_not_exempt(self):
        # "不使用 `pip cache purge`，改用 `rm -rf ...`" — the negation covers the
        # first command and hides the second, so the line gets no exemption.
        commands = CHECKER.find_destructive_commands(
            '本轮不使用 `pip cache purge`，改用 `rm -rf ~/Library/Caches/pip` 直接清掉。\n')
        self.assertTrue(any('rm -rf' in command.text for command in commands))

    def test_commands_are_found_in_prose_cells_and_code_blocks(self):
        commands = CHECKER.find_destructive_commands(self.PLAN)
        texts = ' '.join(command.text for command in commands)
        self.assertIn('docker rmi', texts)
        self.assertIn('pip cache purge', texts)
        self.assertIn('rm -rf', texts)

    def test_read_only_probe_is_not_a_destructive_command(self):
        plan = '`du -sk ~/Library/Caches/pip` and `docker system df` were read.\n'
        self.assertEqual([], CHECKER.find_destructive_commands(plan))

    def test_a_quoted_governing_rule_is_not_a_command(self):
        # The rule cell quotes cleanup_targets.md verbatim; the command inside
        # the quote is a citation, not the plan's own command.
        plan = ('| 候选 | 管辖规则 |\n|---|---|\n'
                '| `~/Library/Caches/pip` | "Cleanup after the redownload impact '
                'is approved: `pip cache purge`" |\n')
        self.assertEqual([], CHECKER.find_destructive_commands(plan))


class ActionSetRuleTests(unittest.TestCase):
    def rows(self, body):
        return CHECKER.collect_gate_rows(
            '| 候选 | 类别 | 判定 |\n|---|---|---|\n' + body + '\n')

    def test_preserve_row_in_the_action_set_fails(self):
        result = CHECKER.check_action_set_classes(self.rows(
            '| `~/.cache/uv` | **PRESERVE** | **入动作集** |\n'))
        self.assertFalse(result.passed)
        self.assertIn('PRESERVE', '\n'.join(result.details))

    def test_user_data_row_in_the_action_set_fails(self):
        result = CHECKER.check_action_set_classes(self.rows(
            '| `~/Documents` | **USER-DATA** | 入动作集 |\n'))
        self.assertFalse(result.passed)

    HEAD = '| 候选 | 类别 | 管辖规则 | 判定 |\n|---|---|---|---|\n'

    def test_proposable_row_in_the_action_set_passes(self):
        # The rule quote is the `_npx` sanction, which is what vouches for the
        # target when the row itself states no evidence.
        result = CHECKER.check_action_set_classes(CHECKER.collect_gate_rows(
            self.HEAD + '| `~/.npm/_npx` | **PROPOSABLE** | "`_npx` may go to Trash '
            'after confirming no `npx` process." | **入动作集** |\n'))
        self.assertTrue(result.passed, result.details)

    def test_proposable_row_without_evidence_or_sanction_fails(self):
        result = CHECKER.check_action_set_classes(CHECKER.collect_gate_rows(
            self.HEAD + '| `~/Library/Caches/Spotify` | **PROPOSABLE** | "Local cache '
            'copies are regenerated, but redownload time, bandwidth, authentication, '
            'and offline availability may matter" | **入动作集** |\n'))
        self.assertFalse(result.passed)
        self.assertIn('never-used evidence', '\n'.join(result.details))

    def test_unlocked_preserve_row_passes_only_with_the_direction_quoted(self):
        # The template's verdict value is "unlocked by user (quote the
        # direction)", so the direction quote is what the checker looks for.
        without = CHECKER.check_action_set_classes(self.rows(
            '| `~/.cache/uv` | **PRESERVE** | unlocked by user |\n'))
        self.assertFalse(without.passed)
        with_direction = CHECKER.check_action_set_classes(self.rows(
            '| `~/.cache/uv` | **PRESERVE** | unlocked by user（用户点名："接受重下代价"） |\n'))
        self.assertTrue(with_direction.passed)

    def test_empty_action_set_is_a_legitimate_outcome(self):
        result = CHECKER.check_action_set_classes(self.rows(
            '| `~/.cache/uv` | **PRESERVE** | 不入动作集 |\n'))
        self.assertTrue(result.passed)


class CategoryWideExclusionTests(unittest.TestCase):
    GATE = ('| 候选 | 类别 | 判定 |\n|---|---|---|\n'
            '| `~/.cache/uv` | **PRESERVE** | 不入动作集，除非你接受 |\n'
            '| `~/.npm/_cacache` | **PROPOSABLE** | **入动作集** |\n')

    def test_category_wide_command_in_the_action_set_fails(self):
        plan = self.GATE.replace('`~/.npm/_cacache`', '`~/.npm`') + \
            '\nProposal: `npm cache clean --force`\n'
        rows = CHECKER.collect_gate_rows(self.GATE.replace('`~/.npm/_cacache`', '`~/.npm`'))
        commands = CHECKER.find_destructive_commands('\nProposal: `npm cache clean --force`\n')
        result = CHECKER.check_category_wide_exclusion(
            commands, rows, CHECKER.parse_tables(plan))
        self.assertFalse(result.passed)

    def test_same_command_as_an_unlock_option_does_not_fail(self):
        # The rule bans a category-wide command from sitting *in the action set*.
        # Offered as an unlock option for a PRESERVE row it is the documented
        # way to hand the decision to the user, so it must not fail.
        rows = CHECKER.collect_gate_rows(self.GATE)
        commands = CHECKER.find_destructive_commands(
            '\n解锁选项（未入动作集）：`uv cache prune`\n')
        result = CHECKER.check_category_wide_exclusion(
            commands, rows, CHECKER.parse_tables(self.GATE))
        self.assertTrue(result.passed)

    def test_explicit_package_argument_narrows_the_scope(self):
        command = CHECKER.find_destructive_commands('`uv cache clean torch`\n')[0]
        self.assertFalse(command.category_wide)
        self.assertTrue(CHECKER.find_destructive_commands('`uv cache prune`\n')[0]
                        .category_wide)


class LeadRuleTests(unittest.TestCase):
    GATE = ('| 候选 | 类别 | 判定 |\n|---|---|---|\n'
            '| `~/.cache/uv` | **PRESERVE** | 不入动作集 |\n'
            '| `~/.npm/_npx` | **PROPOSABLE** | **入动作集** |\n'
            '| `~/Library/Caches/pip` | **PROPOSABLE** | **入动作集** |\n')
    RANKING = ('\n| 排名 | 候选 | 预期物理释放 |\n|---|---|---|\n'
               '| 1 | `~/.npm/_npx` | ≈4.84 GiB |\n'
               '| 2 | `~/Library/Caches/pip` | ≈301 MiB |\n')

    def rows_and_commands(self, plan):
        return (CHECKER.find_destructive_commands(plan),
                CHECKER.collect_gate_rows(self.GATE))

    def test_leading_with_the_largest_release_passes(self):
        plan = ('| 命令 | 精确目标 |\n|---|---|\n'
                '| `osascript ... -- "~/.npm/_npx"` | `_npx` |\n'
                '| `pip cache purge` | pip 缓存 |\n' + self.RANKING)
        commands, rows = self.rows_and_commands(plan)
        result = CHECKER.check_lead_rule(commands, rows, plan)
        self.assertTrue(result.passed, result.details)

    def test_leading_with_the_small_fish_fails(self):
        plan = ('| 命令 | 精确目标 |\n|---|---|\n'
                '| `pip cache purge` | pip 缓存 |\n'
                '| `osascript ... -- "~/.npm/_npx"` | `_npx` |\n'
                + self.RANKING)
        commands, rows = self.rows_and_commands(plan)
        result = CHECKER.check_lead_rule(commands, rows, plan)
        self.assertFalse(result.passed)
        self.assertIn('hotspot', '\n'.join(result.details))

    def test_unknown_releases_do_not_fire_the_rule(self):
        gate = ('| 候选 | 类别 | 判定 |\n|---|---|---|\n'
                '| `~/.npm/_npx` | **PROPOSABLE** | **入动作集** |\n')
        plan = '| 命令 | 精确目标 |\n|---|---|\n| `osascript ...` | `_npx` |\n'
        result = CHECKER.check_lead_rule(
            CHECKER.find_destructive_commands(plan),
            CHECKER.collect_gate_rows(gate), plan)
        self.assertTrue(result.passed)

    def test_hotspot_marker_justifies_a_smaller_lead(self):
        gate = ('| 候选 | 类别 | 判定 |\n|---|---|\n'
                '| `~/.npm/_npx` | **PROPOSABLE** | **入动作集** |\n'
                '| `~/Library/Caches/pip` | **PROPOSABLE** | **入动作集**（热点：磁盘压力来源，'
                '95% 容量告警来自此目录） |\n')
        plan = ('| 命令 | 精确目标 |\n|---|---|\n'
                '| `pip cache purge` | pip 缓存 |\n'
                '| `osascript ... -- "~/.npm/_npx"` | `_npx` |\n'
                + self.RANKING)
        result = CHECKER.check_lead_rule(
            CHECKER.find_destructive_commands(plan),
            CHECKER.collect_gate_rows(gate), plan)
        self.assertTrue(result.passed)


class ReleaseTableFallbackTests(unittest.TestCase):
    def test_a_summary_row_restating_preserve_targets_cannot_win_the_ranking(self):
        # The known-good plan's ranking table ends with a "—" row that lists the
        # PRESERVE block and its nominal sizes. Reading its release cell is what
        # keeps that row from outranking the real lead candidate.
        plan = ('| 排名 | 精确候选 | 名义 | 预期物理释放 |\n|---|---|---|---|\n'
                '| 1 | `~/.npm/_npx` | 4.84 GiB | ≈4.84 GiB |\n'
                '| — | `~/.cache/uv` 41.45 GiB / `~/.npm/_cacache` 12.90 GiB | 见证据表 '
                '| 不确定，且按规则默认保留 |\n')
        readings = CHECKER.plan_release_table(plan)
        self.assertEqual(1, len(readings))
        self.assertAlmostEqual(4.84 * 1024 ** 3, readings[0][1])


class ReleaseColumnDisciplineTests(unittest.TestCase):
    """A number is only a release if the release column says so.

    An agent annotated the Homebrew row "du 路径口径 2.0 GB 不构成释放承诺" and
    the checker read the 2.0 GB as its release, which outranked the real lead
    candidate and made the honest annotation the thing that had to be deleted.
    """

    GATE = ('| 目标 | Nominal size | 预期物理释放 | Class | 判定 |\n'
            '|---|---|---|---|---|\n'
            '| Homebrew 缓存 | 2.0 GB | unknown（取决于缓存构成，未逐对象测量） '
            '| REBUILDABLE | 入动作集 |\n'
            '| pip 缓存 | 308.7 MB | ≤308.7 MB（du 路径口径上界） '
            '| REBUILDABLE | 入动作集 |\n')

    def test_a_reserved_release_cell_yields_no_number(self):
        rows = {row.target: row for row in CHECKER.collect_gate_rows(self.GATE)}
        self.assertIsNone(rows['Homebrew 缓存'].release)
        self.assertAlmostEqual(308.7 * 1000 ** 2, rows['pip 缓存'].release)

    def test_a_nominal_size_column_cannot_participate_in_the_ranking(self):
        plan = ('| 命令 | 精确目标 |\n|---|---|\n'
                '| `pip cache purge` | pip 缓存 |\n'
                '| `brew cleanup -s` | Homebrew 缓存 |\n')
        result = CHECKER.check_lead_rule(
            CHECKER.find_destructive_commands(plan),
            CHECKER.collect_gate_rows(self.GATE), plan)
        self.assertTrue(result.passed, result.details)
        self.assertIn('pip 缓存', '\n'.join(result.details))

    def test_reservation_wording_inside_the_release_cell_is_ignored(self):
        # The shape the agent actually wrote: the number and the withdrawal in
        # the same cell.
        gate = ('| 目标 | 预期物理释放 | Class | 判定 |\n|---|---|---|---|\n'
                '| Homebrew 缓存 | du 路径口径 2.0 GB 不构成释放承诺 | REBUILDABLE '
                '| 入动作集 |\n'
                '| pip 缓存 | ≤308.7 MB | REBUILDABLE | 入动作集 |\n')
        rows = {row.target: row for row in CHECKER.collect_gate_rows(gate)}
        self.assertIsNone(rows['Homebrew 缓存'].release)
        self.assertAlmostEqual(308.7 * 1000 ** 2, rows['pip 缓存'].release)


class ProgramNamePrefixTests(unittest.TestCase):
    GATE = ('| 目标 | Class | 判定 |\n|---|---|---|\n'
            '| pip 缓存（`~/Library/Caches/pip`） | REBUILDABLE | 入动作集 |\n')

    def test_pip3_matches_a_pip_row(self):
        command = CHECKER.find_destructive_commands('`pip3 cache purge`\n')[0]
        rows = CHECKER.collect_gate_rows(self.GATE)
        row, _resolvable, _target = CHECKER.attribute(
            command, rows, CHECKER.parse_tables(self.GATE))
        self.assertIsNotNone(row)
        self.assertIn('pip', row.target)

    def test_pip3_leads_when_it_is_the_biggest_release(self):
        plan = ('| 命令 | 精确目标 |\n|---|---|\n| `pip3 cache purge` | pip 缓存 |\n')
        result = CHECKER.check_lead_rule(
            CHECKER.find_destructive_commands(plan),
            CHECKER.collect_gate_rows(self.GATE), plan)
        self.assertTrue(result.passed, result.details)


class ActionSetMembershipTests(unittest.TestCase):
    """An unlocked row is in the action set for every consumer, not just one."""

    GATE = ('| 候选 | 类别 | 判定 |\n|---|---|---|\n'
            '| `~/.npm/_cacache` | **PROPOSABLE** | unlocked by user（用户点名："删吧"） |\n')

    def rows(self):
        return CHECKER.collect_gate_rows(self.GATE)

    def test_unlocked_row_counts_as_action_set_membership(self):
        self.assertTrue(CHECKER.in_action_set(self.rows()[0]))

    def test_a_category_wide_command_on_an_unlocked_row_fails(self):
        commands = CHECKER.find_destructive_commands('`npm cache clean --force`\n')
        result = CHECKER.check_category_wide_exclusion(
            commands, self.rows(), CHECKER.parse_tables(self.GATE))
        self.assertFalse(result.passed)
        self.assertIn('unlocked by user', '\n'.join(result.details))

    def test_an_unlocked_row_is_checked_for_tool_verification(self):
        commands = CHECKER.find_destructive_commands('`npm cache clean --force`\n')
        result = CHECKER.check_tool_verification(commands, '## Proposal\n`npm cache clean '
                                              '--force`\n', self.rows(),
                                              CHECKER.parse_tables(self.GATE))
        self.assertFalse(result.passed)

    def test_an_unlocked_row_joins_the_ranking(self):
        gate = ('| 候选 | 预期物理释放 | 类别 | 判定 |\n|---|---|---|---|\n'
                '| `~/.cache/uv` | 41.45 GiB | PRESERVE | unlocked by user（用户点名："删"） |\n'
                '| `~/.npm/_npx` | 4.84 GiB | PROPOSABLE | 入动作集 |\n')
        plan = ('| 命令 | 目标 |\n|---|---|\n'
                '| `uv cache clean` | `~/.cache/uv` |\n')
        result = CHECKER.check_lead_rule(
            CHECKER.find_destructive_commands(plan),
            CHECKER.collect_gate_rows(gate), plan)
        self.assertTrue(result.passed, result.details)
        self.assertIn('41.45 GiB', '\n'.join(result.details))

    def test_user_data_row_is_barred_under_every_action_set_verdict(self):
        gate = ('| 候选 | 类别 | 判定 |\n|---|---|---|\n'
                '| `~/Documents` | **USER-DATA** | unlocked by user（用户点名："删"） |\n')
        result = CHECKER.check_action_set_classes(CHECKER.collect_gate_rows(gate))
        self.assertFalse(result.passed)
        self.assertIn('USER-DATA', '\n'.join(result.details))


class RuleColumnTests(unittest.TestCase):
    def test_quote_fidelity_fails_when_the_rule_column_cannot_be_located(self):
        gate = ('| 候选 | 类别 | 出处 | 判定 |\n|---|---|---|---|\n'
                '| `~/.npm/_npx` | **PROPOSABLE** | somewhere | 入动作集 |\n')
        result = CHECKER.check_quote_fidelity(CHECKER.collect_gate_rows(gate), {})
        self.assertFalse(result.passed)
        self.assertIn('rule column not located', '\n'.join(result.details))
        self.assertIn('候选', '\n'.join(result.details))

    def test_a_row_without_a_quotation_or_a_no_rule_marker_fails(self):
        gate = ('| 候选 | 类别 | 管辖规则 | 判定 |\n|---|---|---|---|\n'
                '| `~/.npm/_cacache` | **PROPOSABLE** | cleanup_targets.md says keep '
                'this by default | 入动作集 |\n')
        result = CHECKER.check_quote_fidelity(CHECKER.collect_gate_rows(gate), {})
        self.assertFalse(result.passed)
        self.assertIn('states no quotation', '\n'.join(result.details))

    def test_a_no_rule_found_marker_satisfies_the_citation_requirement(self):
        gate = ('| 候选 | 类别 | 管辖规则 | 判定 |\n|---|---|---|---|\n'
                '| `~/Library/Caches/pnpm` | **USER-DECISION** | no rule found | 不入动作集 |\n')
        result = CHECKER.check_quote_fidelity(CHECKER.collect_gate_rows(gate), {})
        self.assertTrue(result.passed)

    def test_a_ditto_cell_cites_the_row_above(self):
        gate = ('| 候选 | 类别 | 管辖规则 | 判定 |\n|---|---|---|---|\n'
                '| `~/Library/Caches/Google` | **PRESERVE** | "Do not remove an exact '
                'cache directory while its owning application or service is using it." '
                '| 不入动作集 |\n'
                '| `~/Library/Caches/LarkShell` | **PRESERVE** | 同上 | 不入动作集 |\n')
        rows = CHECKER.collect_gate_rows(gate)
        reference = 'Do not remove an exact cache directory while its owning ' \
                    'application or service is using it.\n'
        result = CHECKER.check_quote_fidelity(rows, {'cleanup_targets.md': reference})
        self.assertTrue(result.passed, result.details)
        # The ditto row verifies the same segment as the row it cites.
        self.assertIn('2 quoted segment(s)', '\n'.join(result.details))

    def test_a_ditto_pointing_at_another_ditto_resolves_to_a_real_quote(self):
        gate = ('| 候选 | 类别 | 管辖规则 | 判定 |\n|---|---|---|---|\n'
                '| `~/Library/Caches/Google` | **PRESERVE** | "Do not remove an exact '
                'cache directory while its owning application or service is using it." '
                '| 不入动作集 |\n'
                '| `~/Library/Caches/LarkShell` | **PRESERVE** | 同上 | 不入动作集 |\n'
                '| `~/Library/Caches/ShipIt` | **PRESERVE** | 同上 | 不入动作集 |\n')
        reference = 'Do not remove an exact cache directory while its owning ' \
                    'application or service is using it.\n'
        result = CHECKER.check_quote_fidelity(
            CHECKER.collect_gate_rows(gate), {'cleanup_targets.md': reference})
        self.assertTrue(result.passed, result.details)

    def test_a_table_that_does_not_classify_is_not_read_as_the_gate_table(self):
        # A ranking table whose summary row mentions PRESERVE in prose is not the
        # classification table, and applying the gate to it would invent rows.
        ranking = ('| 排名 | 候选 | 预期物理释放 |\n|---|---|---|\n'
                   '| — | uv 41.45 GiB 都属于 PRESERVE | 不确定 |\n')
        self.assertEqual([], CHECKER.collect_gate_rows(ranking))


class PreserveDowngradeTests(unittest.TestCase):
    """A preserve-by-default target needs evidence or a user direction."""

    def rows(self, body):
        return CHECKER.collect_gate_rows(
            '| 候选 | 类别 | 管辖规则 | 判定 |\n|---|---|---|---|\n' + body)

    def references(self):
        return {'cleanup_targets.md': (
            '| Target | Value retained | Real deletion impact | Default |\n'
            '|---|---|---|---|\n'
            '| Xcode DerivedData | indexes | slower build | Keep |\n'
            '| npm `_cacache` | content | redownload | Keep; do not confuse it with `_npx` |\n'
            '| uv cache | packages | rebuild | Keep |\n')}

    def test_a_relabelled_preserve_target_fails(self):
        rows = self.rows('| `~/.npm/_cacache` | **PROPOSABLE** | "Keep; do not confuse it '
                         'with `_npx`" | 入动作集 |\n')
        result = CHECKER.check_preserve_downgrade(rows, self.references())
        self.assertFalse(result.passed)
        self.assertIn('preserve-by-default table', '\n'.join(result.details))

    def test_a_preserve_row_that_stays_out_is_not_asked_for_evidence(self):
        rows = self.rows('| `~/.cache/uv` | **PRESERVE** | "Keep unless the user accepts '
                         'dependency restoration cost" | 不入动作集 |\n')
        result = CHECKER.check_preserve_downgrade(rows, self.references())
        self.assertTrue(result.passed)

    def test_never_used_evidence_is_accepted_as_a_claim(self):
        rows = self.rows('| `~/.npm/_cacache` | **PROPOSABLE** | "Keep; do not confuse it '
                         'with `_npx`" | 入动作集（项目已删，确认无 npm 进程） |\n')
        result = CHECKER.check_preserve_downgrade(rows, self.references())
        self.assertTrue(result.passed)

    def test_an_exact_child_of_a_preserve_target_is_the_sanctioned_narrow_form(self):
        # The reference prescribes removing an exact inactive project child, so a
        # child row must not be treated as the preserve target itself.
        rows = self.rows('| `~/Library/Developer/Xcode/DerivedData/ProjA` | **PROPOSABLE** '
                         '| "Quit Xcode; prefer removing an exact inactive project child." '
                         '| 入动作集 |\n')
        result = CHECKER.check_preserve_downgrade(rows, self.references())
        self.assertTrue(result.passed)

    def test_a_generic_token_does_not_match_an_unrelated_preserve_entry(self):
        # "cache" appears in several preserve names, so it identifies none of
        # them; a Homebrew row must not read as the uv cache entry.
        rows = self.rows('| `$(brew --cache)` | **REBUILDABLE** | "brew cleanup -s" '
                         '| 入动作集 |\n')
        result = CHECKER.check_preserve_downgrade(rows, self.references())
        self.assertTrue(result.passed)


class CommandArgumentTests(unittest.TestCase):
    def test_object_ids_are_a_stated_target(self):
        self.assertTrue(CHECKER.command_arguments('docker rmi a02c40cc28df 555434521374'))

    def test_a_subcommand_word_is_not_a_stated_target(self):
        self.assertFalse(CHECKER.command_arguments('docker rmi'))

    def test_a_placeholder_is_a_stated_target(self):
        self.assertTrue(CHECKER.command_arguments('docker rmi <IMAGE_ID>'))

    def test_a_command_in_bare_prose_is_found(self):
        commands = CHECKER.find_destructive_commands(
            'Step 3 runs uv cache prune to reclaim 50.9 GiB. No backticks are used here.\n')
        self.assertTrue(any('uv cache prune' in command.text for command in commands))


class MainUsageTests(unittest.TestCase):
    @patch('sys.argv', ['check_gate_plan.py', '--table', '/nope.md', '--plan', '/nope.md'])
    def test_missing_table_file_is_a_usage_error(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(2, CHECKER.main())

    def test_missing_required_arguments_exit_two(self):
        with self.assertRaises(SystemExit) as raised:
            with redirect_stdout(io.StringIO()):
                CHECKER.main(['--table', KNOWN_GOOD.name])
        self.assertEqual(2, raised.exception.code)


@unittest.skipUnless(KNOWN_GOOD.is_file(),
                     'calibration corpus absent: %s (see tests/test_gate_checker.py '
                     'header — the replay workspace is cleaned up periodically)'
                     % KNOWN_GOOD)
class CalibrationKnownGoodTests(unittest.TestCase):
    """False-positive calibration: a healthy plan must exit 0 with zero FAILs.

    Corpus: /tmp/macos-cleaner-workspace/replay-arm1/output.md — the with-skill
    replay of the 2026-09-19 run, written after the Phase 2 entry gate existed.
    It is the known-good sample because an independent review of that gate draft
    found no blocking defect in this output's classification: 19 classified rows,
    governing rules quoted from cleanup_targets.md and docker_analysis.md, four
    PROPOSABLE rows in the action set, every PRESERVE row excluded, no prune
    family command proposed, and the lead command pointing at the largest
    in-action-set release. Its shapes are what forced the parser's tolerances:
    Chinese column headers, a gate table with no expected-release column (the
    release ranking lives in a later section), `\\|` escapes inside quoted rules,
    a quoted rule that spans a fenced code block, commands that appear in table
    cells, inline backticks and a "we did not run these" list, and a Finder
    Trash command whose owning control is an application rather than a versioned
    tool.
    """

    @classmethod
    def setUpClass(cls):
        cls.code, cls.output = run_checker(
            '--table', str(KNOWN_GOOD), '--plan', str(KNOWN_GOOD))

    def test_exit_zero(self):
        self.assertEqual(0, self.code, self.output)

    def test_no_check_fails(self):
        self.assertNotIn('FAIL', self.output)

    def test_every_rule_was_actually_evaluated(self):
        for name in ('table_exists', 'quote_fidelity', 'target_coverage',
                     'action_set_classes', 'category_wide_exclusion', 'lead_rule',
                     'tool_verification'):
            self.assertIn(name, self.output)

    def test_the_gate_table_was_found_and_quotes_were_verified(self):
        # A PASS here must mean something: the table has to have been parsed and
        # the quotes checked, not skipped for want of a parser. Anchored on the
        # line start, because "20 quoted segment(s)" contains "0 quoted ...".
        self.assertIn('gate row(s) classified', self.output)
        self.assertRegex(self.output, r'(?m)^\s+[1-9]\d* quoted segment\(s\) verified')


@unittest.skipUnless(KNOWN_BAD.is_file(),
                     'calibration corpus absent: %s' % KNOWN_BAD)
class CalibrationKnownBadTests(unittest.TestCase):
    """Recall calibration: the failure the gate exists for must exit 1.

    Corpus: /tmp/macos-cleaner-workspace/fixtures/known-bad-original-20260917.md
    — a faithful reproduction of the first 2026-09-17 Phase 2 report, the run
    that triggered the gate. It is the known-bad sample because it shows every
    failure mode the gate names: no classification table at all, category-wide
    commands (`npm cache clean --force`, `brew cleanup`, `uv cache clean`,
    `uv cache prune`) offered as a low-risk green combination, `uv cache prune`
    recommended as the headline on the strength of a --help line plus size
    ratios with no version or semantics check, and a 2 GB item ranked beside a
    91 GB candidate with no free-space target. exit 1 must name the missing
    table and the uncovered targets at minimum.
    """

    @classmethod
    def setUpClass(cls):
        cls.code, cls.output = run_checker(
            '--table', str(KNOWN_BAD), '--plan', str(KNOWN_BAD))

    def test_exit_one(self):
        self.assertEqual(1, self.code, self.output)

    def test_names_the_missing_table(self):
        self.assertIn('FAIL table_exists', self.output)

    def test_names_the_uncovered_targets(self):
        self.assertIn('FAIL target_coverage', self.output)

    def test_names_each_category_wide_command_it_offered(self):
        for command in ('npm cache clean', 'brew cleanup', 'uv cache clean',
                        'uv cache prune'):
            self.assertIn(command, self.output)


@unittest.skipUnless(ROUND2_TABLE.is_file() and ROUND2_PLAN.is_file(),
                     'calibration corpus absent: %s' % ROUND2_TABLE)
class CalibrationRoundTwoTests(unittest.TestCase):
    """False-positive calibration #2: an end-to-end replay must exit 0.

    Corpus: /tmp/macos-cleaner-workspace/replay-round2/{gate-table.md,plan.md} —
    the table and plan a fresh agent produced from the revised skill on a real
    task. It is the known-good sample because it passed the gate honestly: it
    classified 14 candidates, quoted rules from cleanup_targets.md and
    docker_analysis.md, put only two REBUILDABLE rows in the action set, kept
    every PRESERVE and USER-DECISION row out, declared its prune-family
    exclusions, recorded tool versions and semantics for every proposed command,
    and — the part that matters most — led with the smaller of its two proposed
    rows while writing "unknown" and "不构成释放承诺" next to the bigger ones.

    That last property is a regression guard, not decoration. An earlier draft
    of this plan annotated Homebrew's row "du 路径口径 2.0 GB 不构成释放承诺"
    and the checker read 2.0 GB as the row's release, outranked the real lead
    candidate, and forced the agent to delete the annotation to get a green
    light. Honest wording must never be the thing that fails.
    """

    @classmethod
    def setUpClass(cls):
        cls.code, cls.output = run_checker(
            '--table', str(ROUND2_TABLE), '--plan', str(ROUND2_PLAN))

    def test_exit_zero(self):
        self.assertEqual(0, self.code, self.output)

    def test_no_check_fails(self):
        self.assertNotIn('FAIL', self.output)

    def test_the_action_set_was_actually_read(self):
        # Both in-action-set rows are REBUILDABLE, and the verdict column is
        # named 裁决 here rather than 判定 — the header name is not load-bearing.
        self.assertIn('in action set: 2', self.output)
        self.assertNotIn('verdict column unrecognized', self.output)

    def test_the_lead_row_is_the_only_row_with_a_real_release(self):
        self.assertIn('PASS lead_rule', self.output)
        self.assertIn('pip 缓存', self.output)
        # The Homebrew row says unknown, so its 2.0 GB nominal size must not
        # appear as a release figure in the ranking.
        self.assertNotIn('2.0 GB', self.output)

    @unittest.skipUnless(ROUND2_ZAI_TABLE.is_file(),
                         'zai variant absent: %s' % ROUND2_ZAI_TABLE)
    def test_the_zai_wording_variant_reads_the_same_action_set(self):
        # Same table with the verdicts written 在动作集 / 不在动作集 instead of
        # 入动作集 / 不入动作集. This is the wording the end-to-end replay
        # actually used, and it is what exposed the false green: the checker
        # read every verdict as unrecognized, skipped the action set entirely,
        # and still printed exit 0. The two wordings must produce the same
        # verdict counts, not one green and one red.
        code, output = run_checker(
            '--table', str(ROUND2_ZAI_TABLE), '--plan', str(ROUND2_PLAN))
        self.assertEqual(0, code, output)
        self.assertIn('in action set: 2, unlocked by user: 0, not in action set: 12',
                      output)
        self.assertNotIn('verdict column unrecognized', output)


PROBE_DIR = Path(__file__).resolve().parent / 'fixtures' / 'review-probes'


def probe(name):
    """(table, plan) for an adversarial probe, either file standing in for both."""
    gate = PROBE_DIR / ('%s_gate.md' % name)
    plan = PROBE_DIR / ('%s_plan.md' % name)
    return (gate if gate.is_file() else plan, plan if plan.is_file() else gate)


class ProbeCase(unittest.TestCase):
    """Base for the adversarial probes.

    Each probe is a shape an independent reviewer built to attack one gate rule.
    They are the recall half of the calibration: the known-good corpora prove the
    checker does not cry wolf, these prove it does not stay silent. A probe that
    stops failing after a later change is a regression, not an improvement.
    """

    NAME = None
    EXPECT_EXIT = 1
    EXPECT_RULES = ()

    @classmethod
    def setUpClass(cls):
        if not probe(cls.NAME)[0].is_file():
            raise unittest.SkipTest('probe absent: %s' % cls.NAME)
        cls.code, cls.output = run_checker(
            '--table', str(probe(cls.NAME)[0]), '--plan', str(probe(cls.NAME)[1]))

    def test_exit_code(self):
        self.assertEqual(self.EXPECT_EXIT, self.code, self.output)

    def test_names_the_violated_rules(self):
        for rule in self.EXPECT_RULES:
            self.assertIn('FAIL %s' % rule, self.output)


class ProbeP1UnlockedRowTakesCommands(ProbeCase):
    """An unlocked PRESERVE row is in the action set, so the rules apply to it.

    The row says `unlocked by user（用户点名："删吧"）` and the plan proposes
    `npm cache clean --force` — category-wide, with no version and no semantics
    source recorded. Before the action set included unlocked rows, nothing
    checked any of that and the plan exited 0.
    """

    NAME = 'p1'
    EXPECT_RULES = ('category_wide_exclusion', 'tool_verification')


class ProbeP2UnlockedRowRanksFirst(ProbeCase):
    """An unlocked row's release participates in the ranking.

    The 41.45 GiB unlocked uv row leads and the 4.84 GiB in-action-set row
    follows, which is what the ranking rule asks for. lead_rule now agrees; the
    probe still exits 1 because its plan proposes a whole-cache command and
    records no tool verification — two violations the probe itself contains,
    independent of whether unlocked rows rank.
    """

    NAME = 'p2'
    EXPECT_RULES = ('tool_verification',)

    def test_lead_rule_accepts_the_unlocked_row_as_the_lead(self):
        self.assertIn('PASS lead_rule', self.output)
        self.assertIn('41.45 GiB', self.output)


class ProbeP3FabricationInTheReleaseColumn(ProbeCase):
    """A fabricated string in the *release* column is not a rule quote.

    The rule column carries a real quote; the invented text sits in "Expected
    physical release + basis", which the gate defines as an estimate plus its
    derivation, not a verbatim citation. Nothing verifies prose there, so this
    shape is correctly green — p3b is the same table with the two swapped, and
    that one is red.
    """

    NAME = 'p3'
    EXPECT_EXIT = 0

    def test_no_check_fails(self):
        self.assertNotIn('FAIL', self.output)


class ProbeP3bRuleColumnOffByOne(ProbeCase):
    """Locating the rule column by position read the release column instead.

    The rule cell holds an invented quote and the release cell holds a real one.
    A positional guess (third from the end) landed on the release column, so the
    fabricated rule was never checked. The column is now found by its header.
    """

    NAME = 'p3b'
    EXPECT_RULES = ('quote_fidelity',)


class ProbeP4PreserveDowngradeWithVerification(ProbeCase):
    """The original 2026-09-17 failure, in the new table format.

    `~/.npm/_cacache` is relabelled PROPOSABLE with its rule quote intact, and
    the plan even records npm's version and semantics. Every pre-existing check
    passed. What catches it is that the target is in the preserve-by-default
    table and the row states neither never-used evidence nor a user direction.
    """

    NAME = 'p4'
    EXPECT_RULES = ('preserve_by_default',)


class ProbeP4bPreserveDowngradeViaFinderTrash(ProbeCase):
    """The same downgrade reached through the Finder Trash branch.

    Identical table to p4 with the destructive command expressed as an
    application control instead of a package-manager cache wipe, so the
    category-wide rule does not fire. The preserve downgrade is the check that
    still catches it.
    """

    NAME = 'p4b'
    EXPECT_RULES = ('preserve_by_default',)


class ProbeP5UncoveredDockerObjects(ProbeCase):
    """A destructive command naming objects with no row in the table.

    The gate table classifies `_npx` only, and the plan proposes
    `docker rmi <two object IDs>`. Explicit object IDs are a stated target, so
    the absence of any Docker row is a coverage violation.
    """

    NAME = 'p5'
    EXPECT_RULES = ('target_coverage',)


class ProbeP6CommandInBareProse(ProbeCase):
    """A command with no markdown quoting anywhere.

    "Step 3 runs uv cache prune to reclaim 50.9 GiB. No backticks are used here."
    A checker that only reads code spans, fences and table cells sees no command
    at all, so an unsanctioned prune command passes unnoticed.
    """

    NAME = 'p6'
    EXPECT_RULES = ('table_exists',)


class ProbeP7ChineseRuleHeader(ProbeCase):
    """A translated header name must not disable the check.

    The rule column is named 规则依据. When the parser only knew 管辖规则, the
    whole column went unverified and the fabricated quote in the `_cacache` row
    passed. That row is also a preserve downgrade, which is caught independently.
    """

    NAME = 'p7'
    EXPECT_RULES = ('quote_fidelity', 'preserve_by_default')


class ProbeP8PreserveRowInTheActionSet(ProbeCase):
    """A PRESERVE row marked in-action-set, proposing an unsanctioned command.

    Three rules fire: the class may not sit in the action set, the category-wide
    command maps to a row that is in it, and the tool verification is missing.
    """

    NAME = 'p8'
    EXPECT_RULES = ('action_set_classes', 'category_wide_exclusion')


class ProbeP9RuleCellWithoutQuotes(ProbeCase):
    """A rule cell that paraphrases instead of quoting.

    "cleanup_targets.md says keep this by default" cites nothing checkable. A
    pass here would mean the checker verified zero quotes while reporting success,
    which is the failure mode the gate exists to prevent.
    """

    NAME = 'p9'
    EXPECT_RULES = ('quote_fidelity',)


class ProbeP10UnknownReleaseCannotWin(ProbeCase):
    """A row whose release is unknown cannot win the ranking.

    Chromium code-sign clones share extents, so its nominal size is not a
    release. The ranking half of that property now lives in the r3/r4 ranking
    probes (r3-07b, r3-07c, r3-10); this row is red for a different, later rule —
    a PROPOSABLE row in the action set with no never-used evidence — and the
    assertion below is what preserves the original point.
    """

    NAME = 'p10'
    EXPECT_EXIT = 1
    EXPECT_RULES = ('action_set_classes',)

    def test_the_unknown_release_row_is_not_treated_as_a_preserve_target(self):
        self.assertNotIn('FAIL preserve_by_default', self.output)

    def test_the_measured_row_still_leads(self):
        self.assertIn('PASS lead_rule', self.output)


class ProbeP11NarrowChildOfAPreserveTarget(ProbeCase):
    """Removing one exact inactive DerivedData child is the sanctioned form.

    The row targets `.../DerivedData/ProjA`, not "Xcode DerivedData" itself, and
    the reference prescribes removing an exact inactive project child. Treating
    the child as the preserve target would tell the agent that the one form the
    reference allows is a violation.
    """

    NAME = 'p11'
    EXPECT_EXIT = 1
    EXPECT_RULES = ('action_set_classes',)

    def test_the_child_is_not_treated_as_the_preserve_target_itself(self):
        self.assertNotIn('FAIL preserve_by_default', self.output)


class ProbeP12NarrowChildWithSizeInTheTargetCell(ProbeCase):
    """The same narrow child, with its nominal size written into the target cell.

    The target cell reads `.../DerivedData/ProjA（30.0 GiB）`. Reading a release
    out of the target column made that 30.0 GiB outrank the brew row's measured
    2.00 GiB and failed a plan that ranks correctly.
    """

    NAME = 'p12'
    EXPECT_EXIT = 1
    EXPECT_RULES = ('action_set_classes',)

    def test_the_child_is_not_treated_as_the_preserve_target_itself(self):
        self.assertNotIn('FAIL preserve_by_default', self.output)

    def test_its_nominal_size_is_not_read_as_a_release(self):
        # The target cell reads `.../DerivedData/ProjA（30.0 GiB）`, so the string
        # does appear in the row listing; what must not happen is the ranking
        # treating that 30.0 GiB as a release.
        self.assertNotIn('30.0 GiB)', self.output.split('PASS lead_rule')[-1])


PROBE3_DIR = Path(__file__).resolve().parent / 'fixtures' / 'review-probes-r3'


def probe3(table_name, plan_name=None):
    """(table, plan) for a round-3 probe.

    Some probes ship only one file: the A/B pairs share a plan or a gate table,
    so each assertion class names both halves explicitly.
    """
    table = PROBE3_DIR / ('%s_gate.md' % table_name)
    plan = PROBE3_DIR / ('%s_plan.md' % (plan_name or table_name))
    return (table if table.is_file() else plan, plan if plan.is_file() else table)


class Probe3Case(unittest.TestCase):
    """Base for the round-3 adversarial probes."""

    TABLE = None
    PLAN = None
    EXPECT_EXIT = 1
    EXPECT_RULES = ()

    @classmethod
    def setUpClass(cls):
        table, plan = probe3(cls.TABLE, cls.PLAN)
        if not table.is_file():
            raise unittest.SkipTest('probe absent: %s' % cls.TABLE)
        cls.code, cls.output = run_checker('--table', str(table), '--plan', str(plan))

    def test_exit_code(self):
        self.assertEqual(self.EXPECT_EXIT, self.code, self.output)

    def test_names_the_violated_rules(self):
        for rule in self.EXPECT_RULES:
            self.assertIn('FAIL %s' % rule, self.output)


class Probe3WhitelistTests(unittest.TestCase):
    """Commands the allowlist missed are now recognized rather than invisible.

    `docker volume rm <name>` is the per-object form cleanup_targets.md itself
    prescribes; yarn/conda clear whole caches; `find ... -delete` and
    `diskutil secureErase` mutate; `xattr -d` strips quarantine. Before, none
    matched a pattern and the checker reported zero commands checked — which
    reads as "checked and clean" rather than "not looked at".
    """

    def test_docker_volume_rm_is_recognized(self):
        table, plan = probe3('r3-01')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        # Red since the evidence rule landed: the row is PROPOSABLE with no
        # never-used evidence. What this probe still proves is that the command
        # is seen at all, which is what "0 destructive command(s) checked" hid.
        self.assertEqual(1, code, output)
        self.assertIn('FAIL action_set_classes', output)
        # Recognized, not invisible: the proposal and its help-text citation are
        # both seen, which is what "0 destructive command(s) checked" used to hide.
        self.assertRegex(output, r'[1-9]\d* destructive command\(s\) checked')
        # Being counted is what makes the target and tool checks apply at all.
        self.assertRegex(output, r'[1-9]\d* proposed command\(s\) checked')

    def test_yarn_and_conda_are_category_wide(self):
        table, plan = probe3('r3-02')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(1, code, output)
        self.assertIn('FAIL category_wide_exclusion', output)

    def test_find_delete_and_diskutil_secure_erase_are_recognized(self):
        table, plan = probe3('r3-03')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(1, code, output)
        self.assertIn('FAIL target_coverage', output)

    def test_unrecognized_commands_are_counted_not_silently_dropped(self):
        # The allowlist is a declared limit; a plan whose commands are all
        # outside it must say so instead of reporting "0 checked".
        plan = '## Proposal\n\n`someobscurecleaner --all`\n'
        with open(str(PROBE3_DIR / 'r3-01_gate.md')) as handle:
            table_text = handle.read()
        commands = CHECKER.find_destructive_commands(plan)
        missed = CHECKER.unrecognized_command_lines(plan, commands)
        self.assertEqual(1, len(missed))
        self.assertIn('someobscurecleaner', missed[0][1])


class Probe3ExclusionScopeTests(unittest.TestCase):
    """A "we will not run this" statement has to reach the command.

    A table row is a record: the release cell describing an exclusion does not
    retract the command stated in the command cell. Prose is contiguous, so a
    sentence-level negation still covers the commands inside it.
    """

    TABLE = 'r3-04d'

    def test_exclusion_in_another_cell_does_not_exempt_the_command(self):
        table, plan = probe3('r3-04d')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(1, code, output)
        self.assertIn('FAIL preserve_by_default', output)

    def test_the_same_wording_in_the_command_cell_still_exempts(self):
        table, plan = probe3('r3-04d')
        exempt = ('## Proposal\n\n`uv cache prune` 不使用（prune 家族硬排除）\n')
        commands = CHECKER.find_destructive_commands(exempt)
        self.assertEqual([], commands)

    def test_a_prose_negation_covers_its_command(self):
        prose = '本轮未跑 `npm cache clean`。\n'
        self.assertEqual([], CHECKER.find_destructive_commands(prose))


class Probe3UnlockDirectionTests(Probe3Case):
    """Only the verdict cell's quote counts as the user's direction.

    The governing-rule cell always carries quotes — that is what the gate asks
    for — so scanning the whole row confirmed an "unlocked by user" that had no
    user instruction at all.
    """

    TABLE = 'r3-05'
    PLAN = 'r3-05b'
    EXPECT_RULES = ('action_set_classes',)


class Probe3PreserveDowngradeTests(unittest.TestCase):
    """Downgraded preserve targets are caught through their real identifiers."""

    def test_uv_cache_is_reachable(self):
        # "uv" is two characters, and a prose tokenizer with a four-character
        # floor dropped it, which made the uv cache entry unmatchable.
        table, plan = probe3('r3-06')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(1, code, output)
        self.assertIn('FAIL preserve_by_default', output)
        self.assertIn('uv cache', output)

    def test_playwright_matches_by_containment(self):
        table, plan = probe3('r3-06b')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(1, code, output)
        self.assertIn('FAIL preserve_by_default', output)
        self.assertIn('Playwright', output)


class Probe3ReleaseRankingTests(unittest.TestCase):
    """A number labelled nominal is not a release, whoever wrote the label."""

    def test_a_nominal_figure_beside_a_real_one_does_not_win(self):
        table, plan = probe3('r3-07', 'r3-07b')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(1, code, output)
        self.assertIn('FAIL lead_rule', output)

    def test_the_control_without_the_nominal_sentence_behaves_the_same(self):
        table, plan = probe3('r3-07c', 'r3-07b')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(1, code, output)
        self.assertIn('FAIL lead_rule', output)

    def test_the_plan_that_already_leads_with_the_biggest_passes(self):
        table, plan = probe3('r3-07', 'r3-07')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(0, code, output)


class Probe3CoverageBasenameTests(Probe3Case):
    """Shared path components do not attribute a command to a row.

    `rm -rf ~/Library/Keychains` shares "Library" with the `~/Library/Logs` row;
    matching on that made the command look classified when no row covered it.
    """

    TABLE = 'r3-08'
    EXPECT_RULES = ('target_coverage',)


class Probe3ShortQuoteTests(unittest.TestCase):
    """A fabricated short quote is still a fabricated quote.

    "Zzqqxx" and "Keep" were dropped by a twelve-character floor before
    verification, so the check reported nothing quoted and passed.
    """

    def test_short_fabricated_quotes_fail(self):
        table, plan = probe3('r3-09b', 'r3-09')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(1, code, output)
        self.assertIn('FAIL quote_fidelity', output)

    def test_the_same_content_lengthened_also_fails(self):
        table, plan = probe3('r3-09c', 'r3-09')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(1, code, output)
        self.assertIn('FAIL quote_fidelity', output)


class Probe3BrewPruneTests(Probe3Case):
    """`brew cleanup --prune=all` is category-wide; plain `brew cleanup -s` is not.

    The gate names the --prune form specifically, and the reference prescribes
    `brew cleanup -s` as the safe one, so only the flag widens the scope.
    """

    TABLE = 'r3-10'
    EXPECT_RULES = ('category_wide_exclusion',)


class Probe3HotspotReasonTests(unittest.TestCase):
    """A bare hotspot label is not the stated reason the gate asks for."""

    def test_a_two_character_reason_does_not_excuse_a_small_lead(self):
        table, plan = probe3('r3-11')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(1, code, output)
        self.assertIn('FAIL lead_rule', output)

    def test_the_control_without_any_marker_fails_the_same_way(self):
        table, plan = probe3('r3-11c', 'r3-11')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(1, code, output)
        self.assertIn('FAIL lead_rule', output)

    def test_a_section_named_for_semantics_does_not_exempt_the_real_lead(self):
        # The plan puts the small-fish command first under a heading that merely
        # contains the word "semantics". An earlier keyword exemption skipped it
        # and ranked the bigger row first, which is the wrong answer.
        table, plan = probe3('r3-11c', 'r3-12')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(1, code, output)
        self.assertIn('FAIL lead_rule', output)


class Probe3NegatedVerdictTests(unittest.TestCase):
    """「保留在动作集之外」 keeps a row OUT of the action set.

    The string contains 在动作集, so the positive marker won and a compliant row
    read as a proposal — a false positive, which is the more damaging direction.
    """

    def test_the_compliant_row_is_not_read_as_a_proposal(self):
        table, plan = probe3('r3-14b', 'r3-14')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(0, code, output)

    def test_the_proposable_variant_is_unchanged(self):
        table, plan = probe3('r3-14', 'r3-14')
        code, output = run_checker('--table', str(table), '--plan', str(plan))
        self.assertEqual(0, code, output)


PROBE4_DIR = Path(__file__).resolve().parent / 'fixtures' / 'review-probes-r4'


def probe4(table_name, plan_name=None):
    """(table, plan) for a round-4 probe; either file may stand in for both."""
    table = PROBE4_DIR / ('%s_table.md' % table_name)
    plan = PROBE4_DIR / ('%s_plan.md' % (plan_name or table_name))
    return (table if table.is_file() else plan, plan if plan.is_file() else table)


class Probe4Case(unittest.TestCase):
    """Base for the round-4 adversarial probes."""

    TABLE = None
    PLAN = None
    EXPECT_EXIT = 1
    EXPECT_RULES = ()

    @classmethod
    def setUpClass(cls):
        table, plan = probe4(cls.TABLE, cls.PLAN)
        if not table.is_file():
            raise unittest.SkipTest('probe absent: %s' % cls.TABLE)
        cls.code, cls.output = run_checker('--table', str(table), '--plan', str(plan))

    def test_exit_code(self):
        self.assertEqual(self.EXPECT_EXIT, self.code, self.output)

    def test_names_the_violated_rules(self):
        for rule in self.EXPECT_RULES:
            self.assertIn('FAIL %s' % rule, self.output)


class Probe4PreserveSelfUnlockTests(Probe4Case):
    """The mandatory rule quote may not stand in for never-used evidence.

    The reference's own preserve text contains "obsolete" and "never-used", so
    searching the whole row let a downgraded preserve target cite its own
    compliant quote as proof it was dead. This is the 2026-09-17 failure in the
    new table format, which is why the evidence search now excludes the rule cell
    and a preserve downgrade gets the stricter of the two bars.
    """

    TABLE = 'r4-01'
    EXPECT_RULES = ('preserve_by_default',)


class Probe4PreserveSelfUnlockControlTests(Probe4Case):
    """The same downgrade with a quote that carries no evidence word.

    The control uses the other uv rule. It was already red; the point of the pair
    is that both quotes now land in the same place, because what changed is where
    the evidence is looked for, not which words appear in the quote.
    """

    TABLE = 'r4-01ctl'
    EXPECT_RULES = ('preserve_by_default',)


class Probe4PreserveSelfUnlockSecondTargetTests(Probe4Case):
    """`_cacache` downgraded with a quote about "verified never-used evidence".

    The quote is the gate's own sentence describing what a downgrade requires, so
    matching it as evidence is circular.
    """

    TABLE = 'r4-18'
    EXPECT_RULES = ('preserve_by_default',)


class Probe4UnplacedCategoryWideTests(Probe4Case):
    """A category-wide command the table cannot place is not "outside" the set.

    The plan lists `uv cache prune` and `npm cache clean --force` against targets
    the classification table never mentions. Attributing them to nothing used to
    print "none of them in the action set" — a false clean bill on exactly the
    shape the hard-exclusion rules exist to stop.
    """

    TABLE = 'r4-02b'
    EXPECT_RULES = ('category_wide_exclusion',)

    def test_it_does_not_claim_they_are_outside_the_action_set(self):
        self.assertNotIn('none of them in the action set', self.output)


class Probe4NoRuleFoundMustBeUserDecisionTests(Probe4Case):
    """A target no reference covers is USER-DECISION, not PROPOSABLE.

    The gate says such a target is asked about before anything is proposed for
    it, and labelling it PROPOSABLE let an uncovered target lead the action set.
    """

    TABLE = 'r4-03'
    EXPECT_RULES = ('action_set_classes',)


class Probe4UnlockDirectionNeedsVerdictColumnTests(Probe4Case):
    """Without a verdict column, an unlock cannot be confirmed.

    The table puts the rule column last, so the last-cell fallback read the rule
    quote as the user's direction. With no verdict column to read, the row fails
    closed instead.
    """

    TABLE = 'r4-04'
    EXPECT_RULES = ('action_set_classes',)


class Probe4UnlockDirectionControlTests(Probe4Case):
    """The same row with a verdict column present and no quote in it.

    Caught by the ordinary missing-quote rule rather than the fail-closed one.
    """

    TABLE = 'r4-04ctl'
    EXPECT_RULES = ('action_set_classes',)


class Probe4RuleColumnKeywordCollisionTests(Probe4Case):
    """A bare 依据 must not claim the release column.

    "Expected physical release + basis" translates to 预期物理释放 + 依据, which
    matched the rule-column keywords and made the checker read the release cell
    as the rule — so a fabricated rule quote passed while the real quote sat in
    the column being read as an estimate.
    """

    TABLE = 'r4-05'
    EXPECT_RULES = ('quote_fidelity',)


class Probe4PreserveFacePrefixTests(Probe4Case):
    """`facetime` is not `face`.

    Prefix containment made a FaceTime cache match the Hugging Face cache entry.
    Exact token matching fixes it, and splitting a hyphenated basename is what
    keeps `ms-playwright` matching Playwright.
    """

    TABLE = 'r4-07'
    EXPECT_EXIT = 0

    def test_no_check_fails(self):
        self.assertNotIn('FAIL', self.output)


class Probe4ReleaseColumnSynonymTests(Probe4Case):
    """A release column the parser does not know silently disables the ranking.

    The column is named 预计回收空间; with no keyword for it every release read as
    unknown and the ranking rule passed without ranking anything.
    """

    TABLE = 'r4-09'
    EXPECT_RULES = ('lead_rule',)


class Probe4NegatedNominalMarkerTests(Probe4Case):
    """「不是 du 名义值」 confirms the figure it follows.

    A bare 不是 used to void the whole cell, so "6.47 GiB（引擎 UNIQUE SIZE 求和，
    不是 du 名义值）" lost its 6.47 and the checker called the 2.0 GiB row the
    biggest. Nominal markers now only withdraw a number when nothing negates them.
    """

    TABLE = 'r4-10'
    EXPECT_RULES = ('lead_rule',)

    def test_the_defended_number_is_the_one_ranked(self):
        self.assertIn('6.47 GiB', self.output)


class Probe4DockerPerObjectTests(Probe4Case):
    """`docker rmi <id>` names one object, so it is not prune-family.

    The reference prescribes this form; a subshell or a give-me-everything flag
    puts it back in the category-wide class, which is what the sibling probe
    covers.
    """

    TABLE = 'r4-15'
    EXPECT_EXIT = 0

    def test_no_check_fails(self):
        self.assertNotIn('FAIL', self.output)


class Probe4DockerCategoryWideStillCaughtTests(Probe4Case):
    """`docker rmi $(docker images -q)` is still category-wide."""

    TABLE = 'r4-14'
    EXPECT_RULES = ('category_wide_exclusion',)


class Probe4ReferenceScopeKeepsPreserveTableTests(Probe4Case):
    """Narrowing --reference must not disable the preserve cross-check.

    The preserve-by-default table is the skill's own contract, not part of the
    plan's citation scope, so it is always read from the bundle.
    """

    TABLE = 'r4-16'

    def test_preserve_table_survives_a_narrowed_reference(self):
        bundle = SCRIPT_PATH.resolve().parents[1]
        code, output = run_checker(
            '--table', str(probe4('r4-16')[0]), '--plan', str(probe4('r4-16')[1]),
            '--reference', str(bundle / 'references' / 'cleanup_targets.md'))
        self.assertEqual(1, code, output)
        self.assertIn('FAIL preserve_by_default', output)
        self.assertIn('9 preserve-by-default target(s) parsed', output)


class Probe4MultilineTrashTests(Probe4Case):
    """The skill's own documented Trash command spans lines and must pass.

    The `-- "<path>"` line never mentions osascript, so it was never recognized
    as part of the command — the gate rejected the form its own documentation
    prescribes.
    """

    TABLE = 'r4-11b'
    EXPECT_EXIT = 0

    def test_no_check_fails(self):
        self.assertNotIn('FAIL', self.output)


class Probe4MultilineTrashControlTests(Probe4Case):
    """The same command on one line already worked and still does."""

    TABLE = 'r4-12'
    EXPECT_EXIT = 0

    def test_no_check_fails(self):
        self.assertNotIn('FAIL', self.output)


class Probe4EvidenceRequirementTests(Probe4Case):
    """A PROPOSABLE row in the action set must state never-used evidence.

    Previously the requirement only existed inside the preserve-downgrade branch,
    so a non-preserve target could enter the action set on an assertion alone.
    """

    TABLE = 'r4-13'
    EXPECT_RULES = ('action_set_classes',)


class Probe4EvidenceRequirementControlTests(Probe4Case):
    """The same shape against a preserve target, caught by both rules."""

    TABLE = 'r4-13ctl'
    EXPECT_RULES = ('action_set_classes', 'preserve_by_default')


if __name__ == '__main__':
    unittest.main()
