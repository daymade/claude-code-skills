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

import json
import re
from dataclasses import dataclass
from typing import Callable, Optional
from pathlib import Path

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


# Explicit denial must take an authority citation as its immediate object.
# Only enumerated objects continue that phrase; unrelated negative statements
# and independently obtained citations retain the existing authority rules.
_DENIED_AUTHORITY_RE = re.compile(r"不声称|没有")
# A bounded object prefix: determiner, acquisition verb, validity modifier.
# Punctuation, unrelated prose and independent obtained/contrast clauses are
# not object modifiers. This is citation syntax, not general language inference.
_DENIAL_OBJECT_PREFIX_RE = re.compile(r"(?:\s|任何|取得|获得|有效的?)*")

USER_ANSWER_PREFIX = "[user_answer] "
ENTITY_REFERENCE_PREFIX = "[entity_reference] "
WORDING_REFERENCE_PREFIX = "[wording_reference] "
NONPERSON_CUES = {
    "system": ("系统", "平台", "system", "platform"),
    "product": ("产品", "软件", "product", "software"),
    "organization": ("公司", "集团", "机构", "company", "organization"),
    "place": ("市", "区", "县", "镇", "路", "city", "district"),
}


def _citation_occurrence(original: str, context: Optional[str], offset: Optional[int]) -> int:
    """Bind type evidence to one recorded slot, never a sibling mention."""
    if not isinstance(original, str) or not original or not isinstance(context, str) or not context:
        raise ValueError("entity_reference requires a nonempty original and occurrence context")
    if offset is None:
        positions = [m.start() for m in re.finditer("(?=" + re.escape(original) + ")", context)]
        if len(positions) != 1:
            raise ValueError("entity_reference repeated original requires context_offset")
        return positions[0]
    if type(offset) is not int or offset < 0 or context[offset:offset + len(original)] != original:
        raise ValueError("entity_reference context_offset must select this original")
    return offset


# This finite organization-introduction syntax is intentionally narrower than
# entity classification. A source-attested name extension is not itself a cue.
_ORG_UNSAFE_RE = re.compile(r"不|没|并非|产品|软件|系统|老师|先生|女士|我叫|来自|属于")
_ORG_NEGATIVE_RE = re.compile(r"不|没|并非")
_ORG_SOURCE_CONNECTOR_RE = re.compile(r"的|是|由|来自|属于|产品|软件|系统")
_ORG_INTRO_PREFIX_RE = re.compile(
    r"(?:^|[，,])\s*(?:我是|我就是|我叫[^，,。.!！?？;；\n]{1,20}[，,])\s*$")
_ORG_COMPANY_PREDICATE_RE = re.compile(r"(?:是|做|研发|生产|成立|从事|主要|专注|提供|开发|经营)")


def _organization_short_name(quote: str, target: str, original: str,
                             context: str, offset: int) -> bool:
    """Recognise a company self-introduction or its same-paragraph account reference.

    The source must literally name TARGET+extension+corporate suffix. The selected
    occurrence must carry the same extension, and be the founder introduction or
    an explicit first-person account reference following that introduction.
    """
    if _ORG_UNSAFE_RE.search(quote):
        return False
    # Paragraph boundaries prevent a company introduced by a different speaker
    # or in another paragraph from supplying this occurrence's referent.
    lo, hi = 0, len(context)
    for boundary in re.finditer(r"\n\s*\n", context):
        if boundary.end() <= offset:
            lo = boundary.end()
        elif boundary.start() > offset:
            hi = boundary.start()
            break
    paragraph, selected = context[lo:hi], offset - lo
    source_names = re.finditer(re.escape(target) +
        r"(?P<extension>[A-Za-z0-9\u3400-\u9fff·&-]{2,24}?)(?:有限公司|公司|集团|机构)", quote)
    for source_name in source_names:
        extension = source_name["extension"]
        if _ORG_SOURCE_CONNECTOR_RE.search(extension):
            continue
        for size in range(2, len(extension) + 1):
            short = original + extension[:size]
            end = selected + len(short)
            if not paragraph.startswith(short, selected) or not re.match(r"[的，,。.!！?？;；\s]", paragraph[end:end + 1]):
                continue
            # Both supported forms have an affirmative company self-introduction.
            declaration = re.compile(re.escape(short) + r"的创始人[，,。.!！\s]*我们公司")
            for intro in declaration.finditer(paragraph):
                clause_start = max([m.end() for m in re.finditer(r"[，,。.!！?？;；\n]", paragraph[:intro.start()])], default=0)
                sentence_start = max([m.end() for m in re.finditer(r"[。.!！?？;；\n]", paragraph[:intro.start()])], default=0)
                if (not _ORG_INTRO_PREFIX_RE.search(paragraph[sentence_start:intro.start()])
                        or _ORG_UNSAFE_RE.search(paragraph[clause_start:intro.start()])
                        or _ORG_NEGATIVE_RE.search(paragraph[sentence_start:intro.start()])):
                    continue
                company_clause = re.split(r"[。.!！?？;；\n]", paragraph[intro.end():], maxsplit=1)[0]
                if (not _ORG_COMPANY_PREDICATE_RE.match(company_clause)
                        or _ORG_NEGATIVE_RE.search(company_clause)):
                    continue
                if intro.start() == selected:
                    return True
                if intro.end() > selected:
                    continue
                if _ORG_NEGATIVE_RE.search(paragraph[intro.start():selected]):
                    continue
                # A repeated name is supported only in this explicit account
                # reference, not merely because it shares a company paragraph.
                clause_start = max([m.end() for m in re.finditer(r"[，,。.!！?？;；\n]", paragraph[:selected])], default=0)
                before, after = paragraph[clause_start:selected], paragraph[end:]
                sentence_end = re.search(r"[。.!！?？;；\n]", after)
                sentence_start = max([m.end() for m in re.finditer(r"[。.!！?？;；\n]", paragraph[:selected])], default=0)
                sentence = paragraph[sentence_start:end] + (after[:sentence_end.start()] if sentence_end else after)
                if (not _ORG_UNSAFE_RE.search(sentence)
                        and re.fullmatch(r"(?:可以)?关注(?:一下)?(?:这个|这家|我们)?", before)
                        and re.match(r"[，,]\s*我们(?:在|有|是|做)", after)):
                    return True
    return False


def entity_reference_citation(record: object, *, item_id: int, target: str,
                              entity_type: str, original: str, context: Optional[str],
                              context_offset: Optional[int] = None) -> str:
    """Verify a typed written citation and its actual source quote.

    This is not an identity classifier. The operator still judges source authority;
    a free nonperson label alone never waives the person-name guard.
    """
    if not isinstance(record, dict) or record.get("kind") != "entity_reference":
        raise ValueError("authority record requires kind=entity_reference")
    if entity_type not in NONPERSON_CUES or record.get("entity_type") != entity_type:
        raise ValueError("entity_reference requires the item's explicit nonperson entity_type")
    if type(record.get("item_id")) is not int or record["item_id"] != item_id or record.get("target") != target:
        raise ValueError("entity_reference item_id/target does not match this verdict")
    for key in ("source_ref", "source_path", "quote"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f"entity_reference requires nonempty {key}")
    quote = record["quote"]
    if target not in quote:
        raise ValueError("entity_reference quote must contain the exact target")
    source = Path(record["source_path"]).expanduser()
    if quote not in source.read_text(encoding="utf-8"):
        raise ValueError("entity_reference quote is absent from source_path")
    # A typed citation must describe the selected occurrence as that referent.
    offset = _citation_occurrence(original, context, context_offset)
    cues = NONPERSON_CUES[entity_type]
    adjacent = any(re.match(r"\s*" + re.escape(cue), context[offset + len(original):], re.I) for cue in cues)
    short_name = entity_type == "organization" and _organization_short_name(quote, target, original, context, offset)
    if not adjacent and not short_name:
        raise ValueError("this occurrence has no supported source-bound cue for entity_type")
    return ENTITY_REFERENCE_PREFIX + json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def _message_clause(text: str, offset: int, selected: str) -> bool:
    """A whole arrival clause, rather than a token embedded in a name/quote."""
    boundaries = r"[。.!！?？;；\n\r]"
    start = max((m.end() for m in re.finditer(boundaries, text[:offset])), default=0)
    end_match = re.search(boundaries, text[offset + len(selected):])
    end = offset + len(selected) + end_match.start() if end_match else len(text)
    clause = text[start:end].strip()
    return clause in (selected, "还" + selected)


def wording_reference_citation(record: object, *, item_id: int, target: str,
                              original: str, context: Optional[str],
                              context_offset: Optional[int], kind: str,
                              entity_type: str) -> str:
    """Validate a deliberately finite written-evidence route for ordinary wording.

    This is not a general nonperson classifier. Only a standalone message-arrival
    clause is supported; other grammatical forms retain the existing gate.
    """
    if not isinstance(record, dict) or record.get("kind") != "wording_reference":
        raise ValueError("authority record requires kind=wording_reference")
    if kind != "wording" or entity_type != "unknown":
        raise ValueError("wording_reference requires kind=wording and entity_type=unknown")
    if record.get("construction") != "message_arrival" or record.get("source_type") != "parallel_transcript":
        raise ValueError("wording_reference supports only message_arrival from a parallel_transcript")
    if type(record.get("item_id")) is not int or record["item_id"] != item_id:
        raise ValueError("wording_reference item_id does not match this queue item")
    if record.get("original") != original or record.get("target") != target or record.get("context") != context:
        raise ValueError("wording_reference original/target/context does not match this occurrence")
    offset = _citation_occurrence(original, context, context_offset)
    if type(record.get("context_offset")) is not int or record["context_offset"] != offset:
        raise ValueError("wording_reference context_offset does not select this occurrence")
    # These literal nouns and the whole-clause check are the positive nonperson
    # discriminator. An arbitrary wording label or 有NAME来 shape is insufficient.
    if re.fullmatch(r"(?:还)?有(?:信息|消息)来", target) is None:
        raise ValueError("wording_reference target is outside the supported message-arrival syntax")
    if re.fullmatch(r"(?:还)?有[\u3400-\u9fff]{2}来", original) is None or not _message_clause(context, offset, original):
        raise ValueError("wording_reference original is not a whole message-arrival clause")
    for key in ("source_ref", "source_path", "quote"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f"wording_reference requires nonempty {key}")
    quote, quote_offset = record["quote"], record.get("quote_offset")
    if (type(quote_offset) is not int or quote_offset < 0
            or quote[quote_offset:quote_offset + len(target)] != target
            or not _message_clause(quote, quote_offset, target)):
        raise ValueError("wording_reference quote_offset must select the exact whole target clause")
    if quote not in Path(record["source_path"]).expanduser().read_text(encoding="utf-8"):
        raise ValueError("wording_reference quote is absent from source_path")
    return WORDING_REFERENCE_PREFIX + json.dumps(record, ensure_ascii=False, separators=(",", ":"))

# This is a citation syntax, not an open-ended sentiment classifier. A target
# mention (including a target followed by a rejection) cannot testify for itself.
_ANSWER_AFFIRMATIONS = ("是", "是的", "对", "对的", "确认", "yes")
_ANSWER_WORD_PATTERN = "|".join(
    "(?i:yes)" if word == "yes" else re.escape(word)
    for word in _ANSWER_AFFIRMATIONS
)


def _affirmative_question_matches(question: object, target: str) -> bool:
    """Recognise only bounded positive yes/no questions about this target.

    Do not infer a proposition from an arbitrary question mentioning target;
    negative and multi-candidate questions need operator interpretation.
    """
    if not isinstance(question, str):
        return False
    subjects = "这里|这|这句|这个词|该词|你说的|录音里提到的"
    prefix = rf"(?:(?:{subjects})\s*是|是|是不是)"
    shape = rf"{prefix}\s*{re.escape(target)}\s*(?:吗[？?]?|[？?])"
    english = rf"(?i:Is\s+(?:it|this|that))\s+{re.escape(target)}\s*\?"
    return (re.fullmatch(shape, question.strip()) is not None
            or re.fullmatch(english, question.strip()) is not None)


def user_answer_citation(record: object, *, item_id: int, target: str) -> str:
    """Validate a cited answer's shape and scope, not its authorship or truth.

    The operator must copy an actually received answer. A source reference and
    verbatim quote make that claim traceable; they cannot authenticate it.
    """
    if not isinstance(record, dict) or record.get("kind") != "user_answer":
        raise ValueError("authority record requires kind=user_answer")
    for key in ("source_ref", "quote", "target"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f"authority record requires nonempty {key}")
    if type(record.get("item_id")) is not int or record["item_id"] != item_id:
        raise ValueError("authority record item_id does not match this queue item")
    if record["target"] != target:
        raise ValueError("authority record target does not match the resolved text")
    quote = record["quote"].strip()
    question = record.get("question")
    affirmative = re.fullmatch(rf"(?:{_ANSWER_WORD_PATTERN})[。.!！]?", quote) is not None
    if affirmative:
        if not _affirmative_question_matches(question, target):
            raise ValueError("a bare affirmative answer requires a bounded positive question about target")
    else:
        # Exact affirmative word + optional citation separator + exact target;
        # no extra clause is silently dropped. Keep the original quote in JSON.
        shape = rf"(?:{_ANSWER_WORD_PATTERN})\s*[,，:：]?\s*{re.escape(target)}[。.!！]?"
        if not re.fullmatch(shape, quote):
            raise ValueError("quote is outside the bounded affirmative answer syntax")
    # One JSON line keeps quotes and source punctuation out of legacy clause
    # parsing. A new 明确回答 wording alone is deliberately not a gate bypass.
    return USER_ANSWER_PREFIX + json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def _has_user_answer_citation(evidence: str, target: Optional[str] = None) -> bool:
    for line in evidence.splitlines():
        start = line.find(USER_ANSWER_PREFIX)
        if start < 0:
            continue
        try:
            record = json.loads(line[start + len(USER_ANSWER_PREFIX):])
            if not isinstance(record, dict):
                continue
            user_answer_citation(record, item_id=record.get("item_id"),
                                 target=target if target is not None else record.get("target"))
            return True
        except (TypeError, ValueError):
            continue
    return False

def _ungoverned_authority_starts(clause: str) -> set[int]:
    """Start offsets of the authority nouns in ``clause`` no need-marker governs.

    Empty set means every authority noun in the clause is declared
    unobtained, or the clause names none."""
    nouns = list(_AUTHORITY_RE.finditer(clause))
    if not nouns:
        return set()
    denied: set[int] = set()
    for denial in _DENIED_AUTHORITY_RE.finditer(clause):
        following = [noun for noun in nouns if noun.start() >= denial.end()]
        previous_end = denial.end()
        for index, noun in enumerate(following):
            connector = clause[previous_end:noun.start()]
            if index == 0:
                if not _DENIAL_OBJECT_PREFIX_RE.fullmatch(connector):
                    break
            elif not re.match(r"^[、/或和]", connector) or re.search(
                r"但|已(?:取得|获得|获取)", connector
            ):
                break
            denied.add(noun.start())
            if noun.end() < len(clause) and clause[noun.end()].isspace():
                break
            previous_end = noun.end()
    markers = list(_UNOBTAINED_MARKER_RE.finditer(clause))
    if not markers:
        return {m.start() for m in nouns} - denied
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
    return {m.start() for m in nouns} - governed - denied


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
    if _has_user_answer_citation(evidence):
        return True
    # A parallel written transcript never becomes a user ruling/audio citation
    # through words inside its JSON, source identifier or quoted conversation.
    evidence = "\n".join(line for line in evidence.splitlines()
                         if WORDING_REFERENCE_PREFIX not in line)
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
    entity_type: str = "unknown",
    nonperson_reference_validated: bool = False,
    wording_reference_validated: bool = False,
) -> Optional[GuardRejection]:
    """Decide whether converging ``from_text`` onto ``to_text`` may be written.

    Returns None to allow the write, a GuardRejection to refuse it. The caller
    is fail-closed: a rejection means exit non-zero with nothing written.

    Fires only on person-name questions: ``kind`` in PERSON_NAME_KINDS, or the
    from/to pair matches the phonetic-neighbour shape (so --add, which carries
    no kind, is still gated on exactly the incident shape).
    """
    if wording_reference_validated:
        if (kind != "wording" or entity_type != "unknown"
                or re.fullmatch(r"(?:还)?有(?:信息|消息)来", to_text) is None):
            return GuardRejection("wording_reference_scope", "written wording evidence cannot settle an entity/person question")
        cited = False
        for line in (evidence or "").splitlines():
            if WORDING_REFERENCE_PREFIX not in line:
                continue
            try:
                record = json.loads(line.split(WORDING_REFERENCE_PREFIX, 1)[1])
                cited = (isinstance(record, dict) and record.get("kind") == "wording_reference"
                         and record.get("construction") == "message_arrival"
                         and record.get("source_type") == "parallel_transcript"
                         and record.get("original") == from_text and record.get("target") == to_text)
                if cited:
                    break
            except (TypeError, ValueError):
                continue
        if not cited:
            return GuardRejection("wording_authority_required", "written wording evidence requires its validated occurrence-bound citation")
        # Check the phrase and its noun too: a known person's name may itself be
        # a common noun. Classification evidence never overrides a roster.
        terms = {from_text, to_text, from_text.removeprefix("还")[1:-1], to_text.removeprefix("还")[1:-1]}
        if any((claim := lookup_fn(term)).roster_entry or claim.roster_variant_of for term in terms):
            return GuardRejection("nonperson_roster_conflict", "wording reference conflicts with a recorded person; retain person-name authority")
        return None
    if entity_type in NONPERSON_CUES:
        # Known people cannot be relabelled into products/systems to get a
        # written-reference exception. Roster variants also remain protected.
        people = [lookup_fn(term) for term in (from_text, to_text)]
        if any(claim.roster_entry or claim.roster_variant_of for claim in people):
            return GuardRejection("nonperson_roster_conflict", "nonperson type conflicts with a recorded person; retain the person-name authority route")
        for line in (evidence or "").splitlines() if nonperson_reference_validated else []:
            if ENTITY_REFERENCE_PREFIX not in line:
                continue
            try:
                record = json.loads(line.split(ENTITY_REFERENCE_PREFIX, 1)[1])
                if record.get("target") == to_text and record.get("entity_type") == entity_type:
                    # Actual source/occurrence validation is done by the CLI
                    # before this pure decision function. Only this typed
                    # citation opens the nonperson branch, never prose keywords.
                    if all(isinstance(record.get(k), str) and record[k].strip() for k in ("source_ref", "source_path", "quote")) and to_text in record["quote"]:
                        return None
            except (ValueError, TypeError, AttributeError):
                pass
        return GuardRejection("nonperson_authority_required", "explicit nonperson entity_type requires a validated entity_reference --authority-record; a type label or business prose alone is insufficient")
    if kind not in PERSON_NAME_KINDS and entity_type != "person" and not is_person_name_shape(from_text, to_text):
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
    # A structured answer for another target must not qualify through the
    # generic authority-class predicate. Legacy citations keep their contract.
    legacy_evidence = "\n".join(
        line for line in (evidence or "").splitlines()
        if USER_ANSWER_PREFIX not in line
    )
    authority = (_has_user_answer_citation(evidence or "", to_text)
                 or evidence_names_authority(legacy_evidence))
    if not look.found_anywhere and not authority:
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
