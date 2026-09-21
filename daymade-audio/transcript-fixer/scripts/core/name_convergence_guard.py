"""Name-convergence guard: fail-closed gate against collapsing a person name
onto a phonetic neighbour whose target form nothing in the library claims.

Real incident 2026-09-16: an agent normalized 乙琳→乙林 and 丙盛→丙胜 by
transcript-majority spelling; both targets were wrong (the group-chat
displayName said so afterwards), and the error reached a pushed commit before
anyone re-read the roster. triage / accept / --add all ran on agent
discretion, and discretion is exactly what failed. This module is the
mechanical gate that discretion used to be: it fires at the two write points
(`--resolve-review --decision accepted|overridden`, and `--add` when the new
mapping is person-name shaped) and refuses the write when the target is
either someone else's recorded ASR variant or a string no store knows.

The gate asks four questions, in order, first hit decides:

a. Is the target a roster entry name (### header) or the to_text of an ACTIVE
   dictionary rule?  -> PASS: the form is already claimed as somebody's
   canonical form; converging onto a claimed form is the normal correction.
b. Is the target ONLY someone's roster ASR variant?  -> REJECT, naming the
   canonical: a variant is a recorded mishearing, so rewriting text onto it
   manufactures the error the roster exists to fix.
c. Is the target found NOWHERE (dictionary / roster / context rules / review
   queue, --lookup semantics) AND the evidence names no authority source?
   -> REJECT: majority-spelling convergence onto an unclaimed string is the
   incident shape verbatim. The remediation is written into the message:
   enqueue kind:entity, or name the authority (roster line / group
   displayName+nickName double-read / user ruling / audio evidence).
d. Otherwise (target claimed somewhere, or evidence names an authority)
   -> PASS.

Everything the guard needs to know about the library arrives through the
injected ``lookup_fn`` so the decision logic stays pure and unit-testable;
the CLI wires the production lookup (dictionary + roster + context rules +
review queue).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from rapidfuzz.distance import Levenshtein

# Review-queue kinds that name a person-name question. 'entity' covers 人名/专名,
# 'homophone' the 音近误写 class; both are the kinds the 2026-09-16 pairs would
# have carried.
PERSON_NAME_KINDS = frozenset({"entity", "homophone"})

# Authority sources an operator may cite to pass branch (c)/(d): a roster line,
# the group-chat displayName (+nickName double-read), an explicit user ruling,
# or audio evidence (音证/音频/StepFun re-transcription/dashboard listen).
_AUTHORITY_RE = re.compile(
    # 「用户…裁决/裁定/拍板」要有界且取完整词形：裸「用户.*裁」会把
    # 「用户在讨论裁员时提到的名字」「用户群里聊仲裁的事」当成用户裁决
    # （2026-09-16 verify 端到端实测放行洞）。{0,16} 容忍「用户 2026-09-16
    # 直接裁决」这类日期+副词插段；裁员/仲裁/裁判/裁军 均不含三词，不匹配。
    r"roster|名册|displayName|群昵称|用户.{0,16}(?:裁决|裁定|拍板)|音证|音频|StepFun|dashboard",
    re.IGNORECASE,
)

# Naming an authority class is not the same as HAVING it. 「需名册确认」
# 「需听该段音频」「待用户裁定」 cite the class while saying it was never
# obtained — 2026-09-20 audit of the live queue: 46 gated rows passed branch
# (d), a majority of them on exactly this shape (#746「需名册/音频确认
# canonical」, #950「需听该段音频」, #945「需耳核/用户裁定」). The lookbehind
# window covers the connectors between the need-marker and the noun
# (需/待/未/尚/等/要/请/盼 + up to 6 chars of 「听该段」-style filler).
_UNOBTAINED_PREFIX_RE = re.compile(r"(?:需|待|未|尚|等|要|请|盼)[^。；;，,\n]{0,6}$")


@dataclass
class NameLookup:
    """What the whole library already claims about one candidate target string.

    roster_entry:        the string is a ### header in the people roster
    roster_variant_of:   canonical name when the string is that person's
                         recorded ASR 变体 (None when it is nobody's variant)
    dictionary_active_to: an ACTIVE dictionary rule already maps onto it
    found_anywhere:      any trace at all — dictionary from/to (any state),
                         context rule pattern/replacement, roster entry/alias/
                         variant, review-queue original/suggested (any status)
    """
    roster_entry: bool = False
    roster_variant_of: Optional[str] = None
    dictionary_active_to: bool = False
    found_anywhere: bool = False


@dataclass
class GuardRejection:
    """A refused write. ``code`` is machine-stable; ``message`` is the
    operator-facing text, remediation included."""
    code: str          # "target_is_variant" | "target_unknown"
    message: str


def _is_cjk_char(ch: str) -> bool:
    codepoint = ord(ch)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x20000 <= codepoint <= 0x2EE5F
        or 0x2F800 <= codepoint <= 0x2FA1F
        or 0x30000 <= codepoint <= 0x323AF
        or 0x3040 <= codepoint <= 0x30FF
        or 0xAC00 <= codepoint <= 0xD7AF
    )


def is_person_name_shape(from_text: str, to_text: str) -> bool:
    """Phonetic-neighbour heuristic: both sides 2-4 char all-CJK, one edit
    apart (乙琳→乙林, 丙盛→丙胜). Catches the person-name collapse shape at
    --add, where no review kind exists to classify the mapping."""
    for s in (from_text, to_text):
        if not (2 <= len(s) <= 4) or not all(_is_cjk_char(c) for c in s):
            return False
    return Levenshtein.distance(from_text, to_text) <= 1


def evidence_names_authority(evidence: Optional[str]) -> bool:
    """True when the evidence string names an authority source class (branch
    d): roster line / 名册 / group displayName / 群昵称 / 用户…裁决 / 音证 /
    音频 / StepFun / dashboard.

    A citation that is itself marked as not-yet-obtained (「需名册确认」
    「待用户裁定」) does NOT count — see _UNOBTAINED_PREFIX_RE. Any single
    unobstructed citation in the string is enough; a string whose every
    citation is unobtained is not an authority."""
    if not evidence:
        return False
    for m in _AUTHORITY_RE.finditer(evidence):
        if not _UNOBTAINED_PREFIX_RE.search(evidence[: m.start()]):
            return True
    return False


def guard(
    from_text: str,
    to_text: str,
    evidence: Optional[str],
    kind: Optional[str],
    *,
    lookup_fn: Callable[[str], NameLookup],
) -> Optional[GuardRejection]:
    """Decide whether converging ``from_text`` onto ``to_text`` may be written.

    Returns None to allow the write, a GuardRejection to refuse it. The caller
    is fail-closed: a rejection means exit non-zero with nothing written.

    Fires only on person-name questions: ``kind`` in PERSON_NAME_KINDS, or the
    from/to pair matches the phonetic-neighbour shape (so --add, which carries
    no kind, is still gated on exactly the incident shape).
    """
    if kind not in PERSON_NAME_KINDS and not is_person_name_shape(from_text, to_text):
        return None

    look = lookup_fn(to_text)

    # (a) The target is already somebody's canonical form: a roster entry, or
    # the to_text of an active dictionary rule. Converging onto a claimed
    # canonical form is an ordinary correction, not a collapse.
    if look.roster_entry or look.dictionary_active_to:
        return None

    # (b) The target is ONLY someone's recorded ASR mishearing. Rewriting text
    # onto it manufactures the error the roster documents.
    if look.roster_variant_of:
        return GuardRejection(
            "target_is_variant",
            f"拒绝收敛 {from_text!r} → {to_text!r}：{to_text!r} 是 "
            f"{look.roster_variant_of!r} 的 ASR 误写形态，目标应为 "
            f"{look.roster_variant_of!r}（roster 变体是被记录的误写，不是可写入的目标形）",
        )

    # (c) Nothing anywhere claims the target AND the evidence names no
    # authority — the 2026-09-16 incident shape (多数派收敛 onto an unknown
    # spelling). Remediation is part of the refusal, not a separate step.
    if not look.found_anywhere and not evidence_names_authority(evidence):
        return GuardRejection(
            "target_unknown",
            f"拒绝收敛 {from_text!r} → {to_text!r}：人名族内不一致或名册查无，"
            f"禁止按多数派收敛（{to_text!r} 在词典/名册/context rules/review queue 全库查无）。"
            f"先 --enqueue-review kind:entity，或在 evidence 命名权威源"
            f"（roster 行 / 群 displayName+nickName 双读 / 用户裁决 / 音证）；"
            f"已入队的行用 --resolve-review <id> --decision <...> --authority <权威源> "
            f"补录权威（注意：权威源必须是已经取得的——「需名册确认」这类未取得的引用不算）。",
        )

    # (d) The evidence names an authority source, or the target is claimed
    # somewhere even though it is no canonical form — not the guard's call.
    return None
