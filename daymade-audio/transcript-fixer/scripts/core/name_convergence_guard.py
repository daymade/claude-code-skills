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
# canonical」, #950「需听该段音频」, #945「需耳核/用户裁定」).
#
# The criterion has to answer "what counts as unobtained", not "how short is the
# gap". The first version measured a fixed 6-character window in front of each
# authority noun; that width was arbitrary, and the hole it left defeated the
# gate's whole reason to exist: 「需要先去听完整的那一段音频再判断」 (marker 11
# characters away) and 「pending roster confirmation」 (English — no Chinese
# marker at all) both passed, i.e. the 2026-09-16 majority-spelling shape
# survived the fix whenever the connector got a little longer or changed
# language. Measured on the incident pair with an all-False lookup:
#
#   需名册确认                      -> refused  (correct)
#   需先与用户当面确认群昵称          -> PASSED   (9 chars away)
#   需要先去听完整的那一段音频再判断   -> PASSED   (11 chars away)
#   pending roster confirmation     -> PASSED   (English, no marker)
#   TBD 群昵称 double-read          -> PASSED   (English, no marker)
#   待用户裁定 roster 行 ### 王晓明   -> refused  (false refusal: that roster
#                                       citation WAS obtained)
#
# So: split the evidence into clauses on sentence punctuation, and inside a
# clause a need-marker governs the noun phrase it is attached to. The governed
# phrase ends at the clause end, or at the first whitespace that CLOSES an
# authority noun — once 「用户裁定」 or 「roster」 has been cited in full, a
# whitespace-separated segment after it is a fresh citation the marker does not
# reach (that is what keeps 「待用户裁定 roster 行 ### 王晓明」 obtained). A
# marker that FOLLOWS a noun governs it too (「名册需确认」), so the question is
# "is any authority noun ungoverned", not "how far away is the marker".
#
# The remaining hole is the mirror image of that boundary rule: when the marker
# comes AFTER the noun and nothing but a citation-closing whitespace sits
# between them, the boundary severed the pair and the noun was left ungoverned:
#
#   roster 需确认              -> PASSED   (should be refused)
#   dashboard 听音待核         -> PASSED   (should be refused)
#   群昵称 TBD                 -> PASSED   (should be refused)
#
# while the same shape in Chinese (「名册需确认」, no whitespace inside the noun)
# was refused correctly. So a marker that the boundary rule leaves reaching NO
# noun governs every noun in the clause. It could not be the plainer "each
# marker governs the nearest noun on either side": 「用户裁定：需先听音频确认」
# has 需 three characters from 音频 but five from 用户裁定, and nearest-only
# would leave 用户裁定 ungoverned and let that pending ruling pass — the
# colon is not a boundary, and the marker governs both sides across it. The
# fallback only ever turns a pass into a refusal, never the reverse.

# Sentence punctuation ends a claim. So does a comma: 「疑此人，需名册确认」 is
# one pending citation, and 「需名册确认，roster 行 ### 王晓明」 carries an
# obtained one beside it — the module's standing rule is that any single
# unobstructed citation is enough. A colon deliberately does NOT end a claim:
# 「用户裁定：需先听音频确认」 is still pending.
_CLAUSE_END_RE = re.compile(r"[。！？!?；;\n\r，,]+")

# A need-marker: the authority class is named but declared not-yet-obtained.
# Chinese markers are usually prefixes on the noun (需名册 / 待用户裁定 / 未有音证),
# English ones are words that take the citation as their object
# (pending roster confirmation / TBD / awaiting). A marker can also FOLLOW the
# noun, with or without a citation-closing whitespace in between (「名册需确认」
# / 「roster 需确认」); which of those it governs is decided in
# _ungoverned_authority_starts, not by the pattern here.
_UNOBTAINED_MARKER_RE = re.compile(
    r"[需待未尚等要请盼]"
    r"|\bpending\b"
    r"|\btbd\b"
    r"|\bto be confirmed\b"
    r"|\bawaiting\b"
    r"|\bunconfirmed\b"
    r"|\bneeds?\s+(?:roster|audio|confirmation|名册|音频|确认|核对)",
    re.IGNORECASE,
)


def _ungoverned_authority_starts(clause: str) -> set[int]:
    """Start offsets of the authority nouns in ``clause`` no need-marker governs.

    Empty set means every authority noun in the clause is declared
    unobtained, or the clause names none."""
    nouns = list(_AUTHORITY_RE.finditer(clause))
    if not nouns:
        return set()
    markers = list(_UNOBTAINED_MARKER_RE.finditer(clause))
    if not markers:
        return {m.start() for m in nouns}
    # A whitespace that closes an authority noun terminates the governed noun
    # phrase: the citation is complete, so what follows is a new one.
    boundaries = {
        m.end() for m in nouns
        if m.end() < len(clause) and clause[m.end()].isspace()
    }
    governed: set[int] = set()
    for mk in markers:
        reachable = set()
        for noun in nouns:
            lo, hi = sorted((mk.start(), noun.start()))
            if not any(lo < b < hi for b in boundaries):
                reachable.add(noun.start())
        if not reachable:
            # The marker reaches NO noun: every one is cut off from it by a
            # citation-closing boundary, which in practice means the marker sits
            # right after the noun with only whitespace between (「roster 需确认」
            # 「群昵称 TBD」 「dashboard 听音待核」). Reading that whitespace as the
            # start of a fresh citation is exactly the hole that let those three
            # through — the string names one authority and declares it
            # not-yet-obtained. A marker that governs nothing governs them all;
            # this can only add refusals, never let one pass.
            reachable = {noun.start() for noun in nouns}
        governed |= reachable
    return {m.start() for m in nouns} - governed


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
    「pending roster confirmation」) does NOT count — see
    _UNOBTAINED_MARKER_RE. Any single unobstructed citation in the string is
    enough; a string whose every citation is unobtained is not an authority.

    The evidence is split into clauses on sentence punctuation, and the check
    runs per clause: one clause that carries an authority noun no need-marker
    governs is enough to pass, even when another clause is entirely pending
    (「等名册查完再裁；people roster 行 ### 汪晓明」).

    Inside a clause a marker governs the nouns it is attached to; a whitespace
    that closes an authority noun starts a fresh citation the marker does not
    reach, and a marker that reaches no noun at all governs every noun in the
    clause (so 「roster 需确认」 is refused while 「待用户裁定 roster 行 ### 王晓明」
    passes). The full rule and its measured failure modes are documented above
    ``_UNOBTAINED_MARKER_RE``."""
    if not evidence:
        return False
    for clause in _CLAUSE_END_RE.split(evidence):
        if _ungoverned_authority_starts(clause):
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
