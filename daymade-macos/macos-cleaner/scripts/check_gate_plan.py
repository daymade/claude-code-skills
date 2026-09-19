#!/usr/bin/env python3
"""
Phase 2 entry-gate checker for the macos-cleaner skill.

Reads the classification table and the plan the agent wrote, then mechanically
enforces the gate rules stated in SKILL.md ("Phase 2 entry gate — four steps
before any plan text"). Exit 0 is required before a plan may be sent.

Usage:
    uv run scripts/check_gate_plan.py --table <gate-table.md> --plan <plan.md> \
        [--reference <path>]

Options:
    --reference   Reference corpus the governing-rule quotes are verified
                  against. Defaults to the bundle's references/cleanup_targets.md
                  (resolved relative to this script). When the default is used,
                  the sibling references/*.md files and SKILL.md are accepted as
                  provenance too, because the gate contract allows a quote from
                  "the route's dedicated reference" and real plans also quote the
                  skill body. An explicit --reference is authoritative on its own.
    --verbose     Also print per-row parse details.

Exit codes:
    0  every rule passed
    1  at least one rule failed (each failure names the rule and the detail)
    2  usage or parse error (missing/unreadable file, no arguments)
"""

import argparse
import re
import sys
from pathlib import Path

# --- vocabulary -------------------------------------------------------------
# Everything below is matched on cell *content*, never on English column
# headers: agents translate the template, so the columns do not keep their names.

CLASSES = ('PRESERVE', 'PROPOSABLE', 'REBUILDABLE', 'USER-DATA', 'USER-DECISION')

IN_ACTION_MARKERS = (
    (r'入动作集', 'zh'),
    (r'在动作集', 'zh'),
    (r'在\s*action\s*set', 'en'),
    (r'\bin\s+action\s+set\b', 'en'),
)
# Negated forms must win over the positive markers: 不入动作集 and
# "not in action set" both contain the positive marker as a substring.
# The negation is not always the character 不: 保留在动作集之外 and 排除在动作集
# both contain 在动作集, so without these the positive marker wins and a row that
# is explicitly kept OUT of the action set reads as a proposal.
NOT_IN_ACTION_MARKERS = (
    r'不[入进在]动作集', r'未[入进]动作集', r'没有[入进]动作集',
    r'保留[^，。,;；|]{0,6}动作集[^，。,;；|]{0,4}之外',
    r'排除[^，。,;；|]{0,4}动作集', r'移出动作集', r'排除于动作集',
    r'\bnot\s+in\s+(?:the\s+)?action\s+set\b',
)
UNLOCK_MARKERS = (
    r'unlocked\s+by\s+user', r'用户点名', r'用户解锁', r'用户指定', r'用户明确要求',
)
HOTSPOT_MARKERS = ('热点', '瓶颈', 'hotspot', 'bottleneck')

# The action set is "the rows marked in action set PLUS the rows marked unlocked
# by user" (SKILL.md's gate rules). Treating only the literal marker as
# membership let an unlocked PRESERVE row accept a state-changing command with
# no class, category-wide, ranking, or verification check applied to it.
ACTION_SET_VERDICTS = ('in action set', 'unlocked by user')

# The release column is named differently too: 预计回收空间 and 回收空间 both mean
# the same thing, and a name the parser does not know leaves every release
# unknown — which silently disables the ranking rule rather than failing it.
RELEASE_COLUMN_KEYWORDS = ('expected physical release', '预期物理释放', '预期释放',
                           '预计回收', '回收空间', '预计释放', 'release')
# The governing-rule column is named differently in every template translation
# (管辖规则 / 规则依据 / Rule (verbatim quote) / Governing rule ...).
# No bare 依据: the template's "Expected physical release + basis" translates to
# 预期物理释放 + 依据, which would otherwise claim the release column. 规则 still
# matches 规则依据, so translated headers keep working.
RULE_COLUMN_KEYWORDS = ('管辖规则', 'governing', 'rule', '规则', 'quote')
# Evidence a target is genuinely dead. A claim is not a verification — the
# mechanical limit is that the checker can only see the claim, so a human spot
# check at the gate is still what catches a fabricated one.
NEVER_USED_RE = re.compile(
    r'never[\s-]?used|verified\s+unused|dead\s+project|obsolete|'
    r'已废弃|已删除|项目已删|无引用|不再使用|已卸载|确认无.{0,4}进程|'
    r'用户[^，。,;；|]{0,8}?(?:勾选|确认|选择|点名|批准|接受)',
    re.IGNORECASE,
)
NO_RULE_MARKER_RE = re.compile(r'no\s+rule\s+found|无直接条目|没有规则|无规则覆盖', re.IGNORECASE)
# The one case where the governing-rule quote *is* the evidence: the reference
# names an exact narrow target and sanctions removing it. `_npx`'s rule reads
# "`_npx` may go to Trash after confirming no `npx` process", which is the
# reference itself stating the target is disposable after a cheap check. Without
# this, every row whose evidence lives in that sentence would fail — including
# the known-good corpus's `_npx` row.
SANCTIONED_TARGET_RE = re.compile(
    r'may\s+go\s+to\s+Trash|go(?:es)?\s+to\s+Trash|safe\s+to\s+remove|'
    r'may\s+be\s+removed',
    re.IGNORECASE,
)
# Words every cache entry shares, so they identify none of them.
GENERIC_PRESERVE_TOKENS = ('cache', 'caches', 'docker')
# A rule cell that cites the row above instead of repeating its quote.
DITTO_RE = re.compile(
    r'^(?:同上|同前|同上所述|同上一行|同前一行|ditto|same\s+as\s+above)', re.IGNORECASE)


def in_action_set(row):
    return row.verdict in ACTION_SET_VERDICTS


def evidence_cells(row):
    """The cells that may carry never-used evidence — everything but the rule.

    The rule cell is mandatory and quotes the reference verbatim, and the
    reference's own preserve text contains the words "obsolete" and "never-used".
    Searching the whole row therefore let any preserve target cite its own
    compliant quote as proof it was dead, which is the original 2026-09-17
    failure wearing a new format.
    """
    cells = list(row.row.cells)
    if row.rule_column is not None and row.rule_column < len(cells):
        del cells[row.rule_column]
    return cells


def rule_sanctions_target(row):
    """Whether the reference itself vouches for this target.

    Two shapes. Either the rule quote contains a sanctioned-disposal phrase
    ("may go to Trash", "safe to remove", "may be removed"), or it names the
    supported management command for the target (`brew cleanup -s`,
    `pip cache purge`). Both are the reference speaking about this exact target
    rather than the plan asserting something, which is why the rule cell counts
    here and nowhere else.
    """
    if SANCTIONED_TARGET_RE.search(row.rule):
        return True
    return any(pattern.search(row.rule)
               for _tools, pattern, _wide, _versioned in DESTRUCTIVE_PATTERNS)


def has_never_used_evidence(row, strict=False):
    """Whether the row states evidence, or quotes a rule that sanctions it.

    `strict` is for a preserve-by-default target being downgraded. There the bar
    is higher: only stated evidence in the row's own cells, or a rule that
    sanctions *disposing of the target*. A rule that merely names a supported
    management command (`uv cache clean <exact-package>`) is an instruction about
    how to clean, not a statement that the target is dead, and accepting it let a
    downgraded preserve target cite its own compliant quote as proof.
    """
    if any(NEVER_USED_RE.search(cell) for cell in evidence_cells(row)):
        return True
    if strict:
        return bool(SANCTIONED_TARGET_RE.search(row.rule))
    return rule_sanctions_target(row)


def preserve_by_default_targets(raw_references):
    """Target names from cleanup_targets.md's preserve-by-default table.

    Parsed from the raw reference text rather than hard-coded, so the table
    stays the single source: adding a target there extends this check without
    touching the checker.
    """
    names = []
    for name, text in sorted(raw_references.items()):
        if name != 'cleanup_targets.md':
            continue
        for table in parse_tables(text):
            if table.column('target') is None or \
                    table.column('value retained', 'real deletion impact') is None:
                continue
            for row in table.rows:
                target = table.cell(row, 0).strip()
                if target:
                    names.append(target)
    return names


def name_tokens(text):
    """Every alphanumeric token of a short identifier-like string.

    The prose tokenizer drops anything under four characters, which discards
    "uv" and "npm" — the exact identifiers that make a preserve entry
    recognizable. Preserve names are short labels, not sentences, so they get
    their own tokenizer with a two-character floor.
    """
    return {token.lower() for token in re.split(r'[^0-9A-Za-z]+', text)
            if len(token) >= 2 and not token.isdigit()}


def preserve_tokens(names):
    """Identifiers that belong to exactly one preserve entry.

    Document frequency is counted **within the Target column** — the names the
    table itself lists. Counting over the whole reference text made every
    frequent word look shared: "uv" occurs throughout cleanup_targets.md, so it
    was filtered out and the uv cache entry became unmatchable, which is how a
    downgraded uv row passed untouched. "cache" is dropped outright on top of
    that, because several entries carry it and a reference listing only one
    cache entry would otherwise make every cache row match it.
    """
    counts = {}
    for name in names:
        for token in name_tokens(name):
            counts[token] = counts.get(token, 0) + 1
    return {token for token, count in counts.items()
            if count == 1 and token not in GENERIC_PRESERVE_TOKENS}


def tokens_overlap(left, right):
    """Case-insensitive exact token match.

    Containment was too loose in one direction: `facetime` starts with `face`,
    so a FaceTime cache matched the Hugging Face cache entry. Splitting a
    hyphenated basename into its parts (`ms-playwright` -> ms, playwright) is
    what makes the Playwright path still match, so exactness costs nothing there.
    """
    return bool(left & right)


def preserve_match(gate_row, preserve_names, distinctive):
    """The preserve-by-default entry this gate row is really about, if any.

    The row has to name the preserve target *itself*: `~/.npm/_cacache` against
    "npm `_cacache`" is the same target, while `.../DerivedData/ProjA` against
    "Xcode DerivedData" is a narrower child — removing an exact inactive project
    child is the form the reference itself prescribes, and blocking it would
    teach the agent that the sanctioned narrow target is a violation. The test
    is whether the row's own identifier (its path basename) is one of the
    preserve entry's distinctive identifiers.
    """
    path_match = re.search(r'(?:~|\.\.?)?/[\w./{}+*-]+', gate_row.target)
    if path_match:
        base = path_match.group(0).rstrip('/').rsplit('/', 1)[-1]
        own = {token.lower() for token in re.split(r'[^0-9A-Za-z]+', base)
               if len(token) >= 2 and not token.isdigit()}
    else:
        own = name_tokens(gate_row.target)
    for name in preserve_names:
        entry = name_tokens(name) & distinctive
        if entry and tokens_overlap(own, entry):
            return name
    return None


def bundle_cleanup_targets(bundle):
    """The bundle's own cleanup_targets.md, whatever --reference was given.

    The preserve-by-default table is the skill's contract, not part of the plan's
    citation scope, so narrowing --reference to one file must not silently
    disable the cross-check.
    """
    path = bundle / 'references' / 'cleanup_targets.md'
    return {path.name: path.read_text(encoding='utf-8')} if path.is_file() else {}


def check_preserve_downgrade(gate_rows, raw_references, bundle=None):
    """A preserve-by-default target needs evidence or a user direction to move.

    This is the gate's core promise, and the one the original 2026-09-17 failure
    broke in a new format: relabel a preserve target PROPOSABLE, keep its rule
    quote intact, and every other check passes. A downgrade is legitimate on
    never-used evidence or an explicit user direction — a *claim* of either is
    what the checker can see, so the claim is accepted here and the human spot
    check at the gate is what catches a fabricated one.
    """
    if bundle is not None:
        raw_references = bundle_cleanup_targets(bundle)
    preserve_names = preserve_by_default_targets(raw_references)
    distinctive = preserve_tokens(preserve_names)
    violations = []
    checked = 0
    for row in gate_rows:
        name = preserve_match(row, preserve_names, distinctive)
        if name is None:
            continue
        if not in_action_set(row):
            continue  # a preserved row that stays out is exactly right
        checked += 1
        if row.cls == 'PRESERVE':
            continue  # still labelled preserve: only the evidence question is open
        if row.verdict == 'unlocked by user' and has_quoted_direction(row.verdict_cells()):
            continue
        if row.cls in ('PROPOSABLE', 'REBUILDABLE') and has_never_used_evidence(
                row, strict=True):
            continue
        violations.append('line %d: %s — %s is in the preserve-by-default table; '
                          'a downgrade requires never-used evidence or an explicit '
                          'user direction — row states neither'
                          % (row.lineno, row.target[:50], name))
    details = ['%d preserve-by-default target(s) parsed from cleanup_targets.md, '
               '%d row(s) wanting into the action set' % (len(preserve_names), checked)]
    if not preserve_names:
        details.append('preserve-by-default table could not be parsed from the '
                       'reference: this check did not run')
    if violations:
        details.extend(violations)
        return Result('preserve_by_default', False, details)
    return Result('preserve_by_default', True, details)

RELEASE_UNITS = ('GiB', 'MiB', 'KiB', 'GB', 'MB', 'kB')
UNIT_BYTES = {
    'GiB': 1024 ** 3, 'MiB': 1024 ** 2, 'KiB': 1024,
    'GB': 1000 ** 3, 'MB': 1000 ** 2, 'kB': 1000,
}

# --- destructive commands ---------------------------------------------------
# A conservative list: a command that is not matched here is not checked, which
# is the safe direction (a missed command cannot produce a false FAIL).
#
# Each entry: (owning tools, compiled destructive pattern, category-wide?,
#              versioned?) — `versioned` is False for system controls and
#              application controls, where the gate asks for "the owning
#              application or service" instead of a version number.

DESTRUCTIVE_PATTERNS = (
    (('rm',), re.compile(r'\brm\s+(?:-\w+[=\w]*\s+)*[/~$"\']'), False, True),
    (('osascript', 'Finder'), re.compile(r'\bosascript\b'), False, False),
    # Not category-wide on its own: the gate names `brew cleanup --prune`
    # specifically, and the reference prescribes plain `brew cleanup -s` as the
    # safe form. CATEGORY_WIDE_RES below is what widens the --prune variant.
    (('brew', 'Homebrew'), re.compile(r'\bbrew\s+cleanup\b'), False, True),
    (('npm',), re.compile(r'\bnpm\s+cache\s+clean\b'), True, True),
    (('pnpm',), re.compile(r'\bpnpm\s+store\s+prune\b'), True, True),
    (('pip', 'pip3'), re.compile(r'\bpip3?\s+cache\s+purge\b'), False, True),
    (('uv',), re.compile(r'\buv\s+cache\s+(?:clean|prune)\b'), True, True),
    (('docker', 'OrbStack'), re.compile(
        r'\bdocker\s+(?:rmi|rm|prune|system\s+prune|builder\s+prune|'
        r'buildx\s+prune|image\s+prune|volume\s+prune|container\s+prune)\b'), True, True),
    (('defaults', 'AssetCache'), re.compile(r'\bdefaults\s+write\b'), False, False),
    (('AssetCacheManagerUtil',), re.compile(r'\bAssetCacheManagerUtil\b'), False, False),
    (('tmutil',), re.compile(r'\btmutil\s+deletelocalsnapshots\b'), False, False),
    (('mdutil',), re.compile(r'\bmdutil\s+-[Ei]\b'), False, False),
    (('orb', 'orbctl', 'OrbStack'), re.compile(r'\borb(?:ctl)?\s+config\s+set\b'), False, False),
    (('killall',), re.compile(r'\bkillall\b'), False, True),
    # `docker volume rm <name>` is the per-object form the reference itself
    # prescribes; it is not prune-family and must not escape the gate.
    (('docker', 'OrbStack'), re.compile(r'\bdocker\s+volume\s+rm\b'), False, True),
    (('yarn',), re.compile(r'\byarn\s+cache\s+clean\b'), True, True),
    (('pnpm',), re.compile(r'\bpnpm\s+cache\s+clean\b'), True, True),
    (('conda',), re.compile(r'\bconda\s+clean\b'), True, True),
    (('find',), re.compile(r'\bfind\b[^|]*\s-delete\b'), False, True),
    (('diskutil',), re.compile(r'\bdiskutil\s+(?:secureErase|eraseDisk|eraseVolume)\b'),
     False, False),
    (('xattr',), re.compile(r'\bxattr\s+(?:-[a-zA-Z]+\s+)*-d\b'), False, False),
)

# A command that itself carries a dry-run flag is a read-only probe.
DRY_RUN_RE = re.compile(r'(?:^|\s)(?:-n\b|--dry-run\b|--dryrun\b)')
# Asking a tool about itself changes nothing, so quoting `docker rmi --help` in a
# semantics note is not a proposal to remove an image.
HELP_INVOCATION_RE = re.compile(r'(?:^|\s)(?:--help\b|-h\b)|\bhelp\b')
# Category-wide is "an entire class of objects with no per-object selection".
# An explicit object argument narrows it, so these are the exclusions.
EXPLICIT_OBJECT_RES = (
    re.compile(r'\buv\s+cache\s+clean\s+(\S+)'),
    # `docker rmi <id>` names one object, so it is not prune-family. A subshell or
    # a give-me-everything flag puts it back in the category-wide class.
    re.compile(r'\bdocker\s+(?:rmi|rm)\s+(?![^(|]*\$\()(?![^(|]*(?:-q\b|--all\b|'
               r'-a\b))[\w:.@/-]+'),
)
# The mirror image: forms that widen a command to category-wide because they drop
# per-object selection. `brew cleanup --prune=all` removes every cached download.
CATEGORY_WIDE_RES = (
    re.compile(r'\bbrew\s+cleanup\b[^|]*--prune'),
)
READ_ONLY_PROBE_RE = re.compile(
    r'^\s*(?:du|df|lsof|ps|ls|cat|file|grep|mdls|sysctl|sw_vers|head|tail|wc)\b'
)
VERSION_RE = re.compile(r'\d+\.\d+(?:\.\d+)?')
SEMANTICS_RE = re.compile(
    r'--help|\bhelp\b|\bdocs?\b|文档|semantics|语义|帮助|手册|原文|输出格式'
)
# The gate text sanctions the live tool as the substitute for help text
# ("verify cheaply against the live tool"), so a recorded probe counts too.
LIVE_PROBE_RE = re.compile(
    r'逐对象|已核|实测|--filter|--format|\bps\s+-a\b|\binspect\b|config\s+get|'
    r'--version|status|images|volume\s+ls|system\s+df|store\s+path|cache\s+dir'
)
TOOL_VERIFICATION_SECTION_RE = re.compile(
    r'工具验证|版本验证|tool\s+verification|semantics|语义来源|已知问题'
)
QUOTE_SPLIT_RE = re.compile(r'…|\.\.\.')


# --- normalization ----------------------------------------------------------

def normalize(text):
    """Collapse a reference or quote to the shape substring matching needs.

    Strips the markdown the two sides disagree about (emphasis, inline code,
    code fences, escaped table pipes) and collapses whitespace, so a quote
    copied across a fenced-code boundary in the reference still matches.
    """
    text = text.replace('\\|', '|')
    text = text.replace('\\"', '"')
    text = text.replace('\\`', '`')
    text = re.sub(r'^\s*```[A-Za-z0-9_+-]*\s*$', ' ', text, flags=re.MULTILINE)
    text = text.replace('**', '').replace('`', '')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def code_and_path_tokens(text):
    """Tokens from paths and backticked spans — the plan's own identifiers.

    These are distinctive on their own, so short ones count (`.../Caches/pip`).
    """
    tokens = set()
    spans = re.findall(r'`([^`]+)`', text) + re.findall(r'(?:~|\.\.?)?/[\w./{}+*-]+', text)
    for span in spans:
        for path in re.findall(r'(?:~|\.\.?)?/[\w./{}+*-]+', span):
            base = path.rstrip('/').rsplit('/', 1)[-1]
            tokens.update(token for token in re.split(r'[^0-9A-Za-z]+', base)
                          if len(token) >= 2 and not token.isdigit())
        for token in re.split(r'[^0-9A-Za-z]+', span):
            if len(token) >= 2 and not token.isdigit():
                tokens.add(token)
    return tokens


def prose_tokens(text):
    """Tokens from free prose.

    Four characters or more, otherwise sizes such as "12.90 GiB" would make
    every row overlap every other row.
    """
    return {token for token in re.split(r'[^0-9A-Za-z]+', text)
            if len(token) >= 4 and not token.isdigit()}


def argv0(command_text):
    """The invoked program, which names the thing a package-manager cache acts on.

    Chunks arrive with their markdown quoting attached (`pip cache purge`), so
    the leading backtick has to come off before the program name is read.
    """
    head = command_text.strip().lstrip('`\'" ')
    token = re.split(r'\s', head, maxsplit=1)[0] if head else ''
    if '/' in token:
        token = token.rsplit('/', 1)[-1]
    return token if re.fullmatch(r'[A-Za-z][\w.+-]*', token) else ''


# --- markdown tables --------------------------------------------------------

class Row(object):
    def __init__(self, lineno, cells):
        self.lineno = lineno
        self.cells = cells

    def text(self):
        return ' | '.join(self.cells)


class Table(object):
    def __init__(self, header, rows):
        self.header = header
        self.rows = rows

    def column(self, *keywords):
        """Index of the first header cell containing any keyword."""
        for index, cell in enumerate(self.header):
            low = cell.lower()
            if any(keyword in low for keyword in keywords):
                return index
        return None

    def cell(self, row, index):
        if index is None or index >= len(row.cells):
            return ''
        return row.cells[index]


def split_row(line):
    body = line.strip()
    if body.startswith('|'):
        body = body[1:]
    if body.endswith('|'):
        body = body[:-1]
    # Unescaped pipes split cells; \| is a literal pipe inside a cell.
    parts = re.split(r'(?<!\\)\|', body)
    return [part.strip() for part in parts]


def is_separator_row(cells):
    return all(re.fullmatch(r':?-{2,}:?', cell.replace(' ', '')) for cell in cells if cell)


def parse_tables(text):
    """Every markdown table, in document order. Column count is not assumed."""
    tables = []
    lines = text.split('\n')
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.lstrip().startswith('|'):
            index += 1
            continue
        header = split_row(line)
        if index + 1 >= len(lines) or not is_separator_row(split_row(lines[index + 1])):
            index += 1
            continue
        index += 2
        rows = []
        while index < len(lines) and lines[index].lstrip().startswith('|'):
            rows.append(Row(index + 1, split_row(lines[index])))
            index += 1
        tables.append(Table(header, rows))
    return tables


def parse_sections(text):
    """Heading -> (start, end) line ranges, for scoping evidence searches."""
    sections = []
    lines = text.split('\n')
    for number, line in enumerate(lines):
        match = re.match(r'^(#{1,6})\s+(.*)$', line)
        if match:
            sections.append((match.group(2).strip(), number))
    ranges = []
    for position, (title, start) in enumerate(sections):
        end = sections[position + 1][1] if position + 1 < len(sections) else len(lines)
        ranges.append((title, start, end))
    return ranges


# --- gate table -------------------------------------------------------------

def row_class(cells):
    for cell in cells:
        plain = cell.replace('**', '')
        for name in CLASSES:
            if re.search(r'\b' + re.escape(name) + r'\b', plain, re.IGNORECASE):
                return name
    return None


def row_verdict(cells):
    """The row's verdict, or None when it states no action-set position.

    Order matters: 不入动作集 contains 入动作集 and "not in action set" contains
    "in action set", so the negated form has to be settled first or every
    PRESERVE row reads as a proposal.
    """
    for cell in cells:
        plain = cell.replace('**', '')
        for marker in NOT_IN_ACTION_MARKERS:
            if re.search(marker, plain, re.IGNORECASE):
                return 'not in action set'
    for cell in cells:
        plain = cell.replace('**', '')
        if any(re.search(marker, plain, re.IGNORECASE) for marker in UNLOCK_MARKERS):
            return 'unlocked by user'
    for cell in cells:
        plain = cell.replace('**', '')
        for pattern, _kind in IN_ACTION_MARKERS:
            if re.search(pattern, plain, re.IGNORECASE):
                return 'in action set'
    return None


def row_is_hotspot(cells):
    """Whether the row marks itself the user-visible hotspot *with a reason*.

    The gate allows a smaller lead row when the table marks another row as the
    hotspot "with a stated reason". A bare 热点 is a label, not a reason, and
    accepting it let a 0.5 GiB row lead a 41 GiB one on the strength of two
    characters. Whether the accompanying text is a *good* reason is not
    mechanically checkable — twelve characters is a proxy for "someone wrote
    something", and the human reading the plan is what judges the reasoning.
    """
    for cell in cells:
        low = cell.lower()
        for marker in HOTSPOT_MARKERS:
            position = low.find(marker)
            if position < 0:
                continue
            around = cell[:position] + cell[position + len(marker):]
            if len(re.sub(r'[\s*`|，。,;；、()（）\[\]]', '', around)) >= 12:
                return True
    return False


class GateRow(object):
    def __init__(self, table, row):
        self.table = table
        self.row = row
        self.lineno = row.lineno
        self.cls = row_class(row.cells)
        self.verdict = row_verdict(row.cells)
        self.hotspot = row_is_hotspot(row.cells)
        self.target_column = table.column('候选', '目标', 'target')
        if self.target_column is None:
            # Every template shape puts the target first; a positional guess
            # further right lands on the release column and misreads the row.
            self.target_column = 0
        self.target = table.cell(row, self.target_column)
        # The rule cell is the fallback for coverage: it names the tool even
        # when the target cell holds only a path (Homebrew).
        self.verdict_column = table.column('裁决', '判定', 'verdict')
        self.rule_column = table.column(*RULE_COLUMN_KEYWORDS)
        self.rule = table.cell(row, self.rule_column)
        # Filled in by collect_gate_rows: what a "同上" rule cell cites.
        self.ditto_source = ''
        # The rule cell contributes only its identifiers: its prose is shared
        # boilerplate ("approved", "impact", "cache") that would match anything.
        self.target_tokens = code_and_path_tokens(self.target) | prose_tokens(self.target)
        # Only the identifiers, never the path components: see target_identifiers.
        self.basename_tokens = set()
        for path in re.findall(r'(?:~|\.\.?)?/[\w./{}+*-]+', self.target):
            self.basename_tokens.update(
                name_tokens(path.rstrip('/').rsplit('/', 1)[-1]))
        if not self.basename_tokens:
            self.basename_tokens = name_tokens(self.target)
        self.rule_tokens = code_and_path_tokens(self.rule)
        self.tokens = self.target_tokens | self.rule_tokens
        self.release = table_release_cell(table, row)

    def verdict_cells(self):
        """The verdict cell, or the last cell when no verdict column is named.

        The last-cell fallback is only for reading a verdict that is *stated*
        there; it must not be used to confirm a user direction, because the rule
        column is last in some template translations and its quote would then
        stand in for the user's own words.
        ""

        Every template shape puts the verdict last, so the last cell is the safe
        fallback; the point is that the governing-rule cell is excluded either
        way, because its quotes are the rule's, not the user's.
        """
        if self.verdict_column is not None and self.verdict_column < len(self.row.cells):
            return [self.row.cells[self.verdict_column]]
        return [self.row.cells[-1]] if self.row.cells else []


def collect_gate_rows(table_text):
    """Gate rows are rows of a table that classifies candidates.

    The table has to look like a classification table — its header names a class
    column or a rule column. Without that, any table whose prose happens to
    mention "PRESERVE" (a ranking table's summary row does) would be read as the
    gate table, and every check would then be applied to a table that is not one.
    """
    rows = []
    for table in parse_tables(table_text):
        if table.column('类别', '分类', 'class') is None and \
                table.column(*RULE_COLUMN_KEYWORDS) is None:
            continue
        last_real_rule = ''
        for row in table.rows:
            if row_class(row.cells):
                gate_row = GateRow(table, row)
                # "同上" cites the nearest row above that actually states a rule;
                # a chain of dittos has to resolve to a real quote, not to
                # another ditto.
                gate_row.ditto_source = last_real_rule
                rows.append(gate_row)
                if not DITTO_RE.match(gate_row.rule.strip()):
                    last_real_rule = gate_row.rule
    return rows


def table_release_cell(table, row):
    """Release from the table's own expected-release column, if it has one.

    Only that column is read. Every other column carries path-accounted sizes
    ("du 口径 2.0 GB"), and a nominal number read as a release poisons the
    ranking: it makes an honest "this is not a release promise" annotation look
    like the biggest winner, and the agent's only way out is to delete the
    annotation.
    """
    index = table.column(*RELEASE_COLUMN_KEYWORDS)
    if index is None:
        return None
    return extract_release(table.cell(row, index))


# Wording that withdraws a number from the release ranking. A cell that says
# "unknown" or "does not constitute a release promise" has no number to rank.
# No bare 不是: "6.47 GiB（引擎 UNIQUE SIZE 求和，不是 du 名义值）" is a
# clarification *confirming* the number, and voiding the whole cell for it made
# the checker call the smaller row the biggest.
RESERVATION_RE = re.compile(
    r'不构成|不确定|未知|不可|不承诺|unknown|待测|待定|无法|取决于|未测量|未逐对象',
    re.IGNORECASE,
)


# Wording that labels a number as path accounting rather than physical release.
NOMINAL_MARKER_RE = re.compile(
    r'(?<![不没未])(?:path-accounted|nominal|名义值?|路径计账|apparent\s+size|'
    r'logical\s+size)',
    re.IGNORECASE,
)
# The weaker "du 路径口径" phrasing, which only withdraws a number when the cell
# carries another number it could be disambiguating. A healthy plan writes
# "≤308.7 MB（du 路径口径上界）" as its only estimate, and throwing that away
# would leave the ranking with nothing to rank.
NOMINAL_PATH_PHRASE_RE = re.compile(r'du\s*路径口径|路径口径', re.IGNORECASE)
# A negator anywhere shortly before a nominal marker means the marker is
# defending the number rather than labelling it: 「不是 du 名义值」 confirms the
# figure, while 「is the path-accounted nominal」 withdraws it. The negator is not
# necessarily adjacent, so the window is what decides.
NEGATOR_RE = re.compile(r'[不没未非]')
AFFIRMATIVE_NOMINAL_RE = re.compile(r'名义值?|路径计账|path-accounted|nominal',
                                    re.IGNORECASE)
# How close a nominal label has to be to a number to withdraw it from the
# ranking: same clause, measured in characters. Wide enough for "the 91.0 GiB
# figure is the path-accounted nominal", narrow enough that a genuine release
# estimate in the same cell survives.
NOMINAL_WINDOW = 60


def nominal_labelled(window):
    """Whether the window labels its number as path accounting, not physical release.

    A marker with a negator in front of it is a clarification, not a label.
    """
    for marker in AFFIRMATIVE_NOMINAL_RE.finditer(window):
        if not NEGATOR_RE.search(window[:marker.start()]):
            return True
    return False


RELEASE_NUMBER_RE = re.compile(
    r'\d+(?:\.\d+)?\s*(?:' + '|'.join(RELEASE_UNITS) + r')\b')


def extract_release(text):
    """Largest (value, unit) reading in a cell that is not labelled nominal.

    A cell may legitimately carry both — the reference asks for the release
    estimate plus its basis, and the basis is often the nominal figure it is
    corrected against. Reading the nominal number as the release is what let a
    2 GiB candidate lead beside a 91 GiB one.
    """
    best = None
    for match in re.finditer(
            r'(\d+(?:\.\d+)?)\s*(' + '|'.join(RELEASE_UNITS) + r')\b', text):
        window = text[max(0, match.start() - NOMINAL_WINDOW):
                      min(len(text), match.end() + NOMINAL_WINDOW)]
        if nominal_labelled(window) or RESERVATION_RE.search(window):
            continue
        if NOMINAL_PATH_PHRASE_RE.search(window) and len(RELEASE_NUMBER_RE.findall(text)) > 1:
            continue
        value = float(match.group(1)) * UNIT_BYTES[match.group(2)]
        if best is None or value > best:
            best = value
    return best
    return best


def plan_release_table(plan_text):
    """Fallback release ranking table in the plan prose.

    Used when the gate table has no expected-release column. Only rows whose
    candidate cell parses as a release count, so summary rows that restate a
    whole class of PRESERVE targets cannot win the ranking.
    """
    for table in parse_tables(plan_text):
        if table.column(*RELEASE_COLUMN_KEYWORDS) is None:
            continue
        candidate_column = table.column('候选', 'candidate', '目标', 'target', '项目')
        release_column = table.column(*RELEASE_COLUMN_KEYWORDS)
        readings = []
        for row in table.rows:
            release = extract_release(table.cell(row, release_column))
            if release is None:
                continue
            candidate = table.cell(row, candidate_column) or row.text()
            readings.append((code_and_path_tokens(candidate) | prose_tokens(candidate),
                             release, candidate))
        if readings:
            return readings
    return []


# --- destructive commands ---------------------------------------------------

def command_chunks(plan_text):
    """(lineno, origin, text) for every place a command can hide.

    `origin` is 'cell' or 'prose' and decides how far a "we will not run this"
    statement reaches: prose is contiguous, so a sentence-level negation covers
    the commands it contains, while a table row is a record whose cells say
    different things — a "排除" in the release cell does not retract a command
    stated in the command cell.

    Fenced code lines, inline code spans, and table cells are the three shapes
    real plans actually use. A governing-rule cell is skipped: it quotes the
    reference verbatim, so the commands inside it are citations of a rule, not
    the plan's own commands. Chunks are de-duplicated so a command quoted both
    inline and in a table is checked once.
    """
    chunks = []
    lines = plan_text.split('\n')
    rule_cells = set()
    command_tables = set()
    for table in parse_tables(plan_text):
        index = table.column('管辖规则', 'governing')
        if index is not None:
            for row in table.rows:
                if index < len(row.cells):
                    rule_cells.add((row.lineno, normalize(row.cells[index])))
        if table.column('命令', 'command', '动作') is not None:
            for row in table.rows:
                command_tables.add(row.lineno)
    in_fence = False
    consumed = 0
    for number, line in enumerate(lines):
        if re.match(r'^\s*```', line):
            in_fence = not in_fence
            continue
        if in_fence:
            if line.strip() and not line.lstrip().startswith('#'):
                stripped = line.strip()
                # The skill's own documented Trash command spans lines, and the
                # line carrying `-- "<path>"` never mentions osascript, so it was
                # never recognized as part of the command.
                if (re.match(r'^(?:-e\b|--)', stripped) and chunks
                        and consumed == number):
                    previous = chunks[-1]
                    chunks[-1] = (previous[0], previous[1], previous[2] + ' ' + stripped)
                    consumed = number + 1
                    continue
                chunks.append((number + 1, 'prose', stripped))
                consumed = number + 1
            continue
        if line.lstrip().startswith('|'):
            # A table row is read as cells only: its inline backticks belong to
            # those cells, and a rule cell's backticked command is a citation.
            origin = 'cmdtable' if number + 1 in command_tables else 'cell'
            for cell in split_row(line):
                if not cell or (number + 1, normalize(cell)) in rule_cells:
                    continue
                chunks.append((number + 1, origin, cell))
        else:
            spans = [match.group(1).strip() for match in re.finditer(r'`([^`]+)`', line)]
            for span in spans:
                chunks.append((number + 1, 'prose', span))
            if not spans and line.strip():
                # A prose line with no inline code is still where a command can
                # hide ("runs uv cache prune to reclaim 50.9 GiB"). Lines that do
                # carry backticks are read as those spans only, so a command
                # quoted inside prose is not double-counted.
                chunks.append((number + 1, 'prose', line.strip()))
    seen = set()
    unique = []
    for lineno, origin, text in chunks:
        key = (lineno, origin, normalize(text))
        if key[2] and key not in seen:
            seen.add(key)
            unique.append((lineno, origin, text))
    return unique


class Command(object):
    def __init__(self, lineno, text, tools, category_wide, versioned, origin='prose'):
        self.lineno = lineno
        self.text = text
        self.origin = origin
        self.tools = tools
        self.category_wide = category_wide
        self.versioned = versioned


# A command the plan declares it did NOT run and will not propose is not a
# proposal, so neither coverage nor verification applies to it. Real plans list
# these ("未跑 npm cache clean", "不使用任何 prune 家族命令") precisely to show
# the exclusions were deliberate.
DECLARED_UNUSED_RE = re.compile(
    r'未跑|未执行|未使用|不使用|不用|不删|不承诺|不执行|不提议|不列入|排除|'
    r'只报不删|禁\s*prune|不进方案|不在方案|'
    r'never\s+(?:use|used|run|ran|executed?)|not\s+(?:used|run)|do\s+not\s+use',
    re.IGNORECASE,
)


def declared_unused(lineno, origin, chunk, lines, commands_on_line=1):
    """Whether the plan says it will not run this command.

    The statement has to reach the command, and it has to be *about* the command.
    In prose it reaches the line ("未跑 `npm cache clean`"), but a line that
    mixes an exclusion with a real command — "不使用 `pip cache purge`，改用
    `rm -rf ...`" — is not a declaration that nothing runs: the negation covers
    the first command and hides the second. Such a line gets no exemption at all.
    In a table the row's other cells describe the target or the estimate, so the
    scope is the cell itself.
    """
    if origin != 'cell' and commands_on_line > 1:
        return False
    scope = chunk if origin == 'cell' else lines[lineno - 1]
    return bool(DECLARED_UNUSED_RE.search(scope))


def find_destructive_commands(plan_text):
    commands = []
    lines = plan_text.split('\n')
    seen = set()
    per_line = {}
    for lineno, origin, chunk in command_chunks(plan_text):
        per_line[lineno] = per_line.get(lineno, 0) + 1
    for lineno, origin, chunk in command_chunks(plan_text):
        if DRY_RUN_RE.search(chunk) or HELP_INVOCATION_RE.search(chunk):
            continue
        if READ_ONLY_PROBE_RE.match(chunk) and not re.search(r'\brm\b', chunk):
            continue
        if declared_unused(lineno, origin, chunk, lines, per_line.get(lineno, 1)):
            continue
        for tools, pattern, category_wide, versioned in DESTRUCTIVE_PATTERNS:
            match = pattern.search(chunk)
            if not match:
                continue
            if category_wide:
                # An explicit object argument narrows the scope.
                if any(narrow.search(chunk) for narrow in EXPLICIT_OBJECT_RES):
                    category_wide = False
            elif any(widen.search(chunk) for widen in CATEGORY_WIDE_RES):
                category_wide = True
            key = (lineno, match.group(0))
            if key in seen:
                continue
            seen.add(key)
            commands.append(Command(lineno, chunk, tools, category_wide, versioned,
                                    origin))
    commands.sort(key=lambda command: command.lineno)
    return commands


def quoted_target(command_text):
    """The path after a `--` separator: how osascript targets are written."""
    match = re.search(r'--\s+"([^"]+)"', command_text)
    return match.group(1) if match else ''


PATH_TOKEN_RE = re.compile(r'(?:~|\.\.?)?/[\w./{}+*-]+|\$\(?\w')


def resolve_target(command, plan_tables):
    """(stated target, attributable row or None, resolvable?).

    A table row's target column wins when there is one: it is where the agent
    states the exact object, and the command cell alone often holds only IDs.
    """
    for table in plan_tables:
        for row in table.rows:
            if row.lineno != command.lineno:
                continue
            index = table.column('目标', 'target')
            if index is not None and table.cell(row, index):
                return table.cell(row, index), None, True
    target = quoted_target(command.text)
    if target:
        return target, None, True
    if PATH_TOKEN_RE.search(command.text):
        return command.text, None, True
    if command_arguments(command.text):
        # Explicit object IDs or names are a stated target even though they are
        # not paths: `docker rmi a02c40cc28df` names what it will delete.
        return command.text, None, True
    return command.text, None, False


def command_arguments(command_text):
    """Object-shaped arguments after the program name.

    Subcommand words (`rmi`, `clean`, `prune`) are not targets, so only tokens
    that look like an object count — an ID, a path, a placeholder. A bare
    `docker rmi` in prose therefore states no target, while `docker rmi
    a02c40cc28df` does.
    """
    parts = [part for part in command_text.split() if not part.startswith('-')]
    return [part.strip('`\'"') for part in parts[1:]
            if re.search(r'[\d/<*$.]', part)]


def command_tokens(command, target):
    """What identifies the target a command acts on.

    The stated target plus the command's own identifiers: `pip cache purge` says
    nothing about a path, but its program name is what names the target.
    """
    tokens = code_and_path_tokens(target) | prose_tokens(target)
    tokens |= code_and_path_tokens(command.text)
    program = argv0(command.text)
    if program:
        tokens.add(program)
    return tokens


def program_matches(program, row):
    """Whether an invoked program names this row's target.

    `pip3 cache purge` and a row about `~/Library/Caches/pip` are the same
    target, so the program name is allowed to extend a row token by a version
    suffix. It is compared against every alphanumeric token of the target cell,
    not the >=4-character prose set: "pip 缓存" is a legitimate target cell whose
    only identifier is three characters long. Scoped to the program name on
    purpose — spreading prefix matching to free text would make unrelated rows
    match.
    """
    if not program:
        return False
    return any(len(token) >= 3 and program.startswith(token)
               for token in re.split(r'[^0-9A-Za-z]+', row.target)
               if token and not token.isdigit())


def attribute(command, gate_rows, plan_tables):
    """Find the gate row this command is about, if the plan says which one.

    A row has to match on a *basename-level* identifier. Path components such as
    "Library" and "Caches" appear in almost every row, so counting them let
    `rm -rf ~/Library/Keychains` attach itself to the `~/Library/Logs` row and
    disappear from the coverage check. The invoked program is the strongest
    identifier, because for a package-manager cache it *is* the target.
    """
    target, _row, resolvable = resolve_target(command, plan_tables)
    identifiers = target_identifiers(command, target)
    if not identifiers:
        return None, resolvable, target
    program = argv0(command.text)

    def score(row):
        value = 0
        if tokens_overlap(identifiers, row.basename_tokens):
            value += 4
        if program_matches(program, row):
            value += 3
        value += len(identifiers & row.target_tokens)
        return value

    best = max(gate_rows, key=score, default=None)
    if best is not None and (score(best) >= 3 or tokens_overlap(identifiers, best.basename_tokens)):
        return best, resolvable, target
    return None, resolvable, target


def target_identifiers(command, target):
    """The distinctive identifiers a command's target names.

    Path basenames and object IDs — the parts that name *what* is acted on, as
    opposed to the directories it happens to live under.
    """
    identifiers = set()
    for path in re.findall(r'(?:~|\.\.?)?/[\w./{}+*-]+', target):
        base = path.rstrip('/').rsplit('/', 1)[-1]
        identifiers.update(name_tokens(base))
    for span in re.findall(r'`([^`]+)`', target):
        identifiers.update(name_tokens(span))
    if not identifiers:
        identifiers.update(name_tokens(target))
    program = argv0(command.text)
    if program:
        identifiers.add(program.lower())
    return identifiers


def tool_version_re(tool):
    """A version attached to the tool, or a line that declares versions at all.

    Sizes such as "20.26GB" also match a bare version regex, so the version has
    to sit next to the tool name or on a line that declares versions.
    """
    return re.compile(
        r'\b' + re.escape(tool) + r'\b[\s*`]*v?(\d+\.\d+(?:\.\d+)?)'
        r'|(\d+\.\d+(?:\.\d+)?)[\s*`]*\b' + re.escape(tool) + r'\b',
        re.IGNORECASE,
    )


def verification_evidence(command, plan_text):
    """Lines that may carry this command's tool verification.

    Three sources, in widening order: the command's own line, its neighbours,
    and a tool-verification block anywhere in the plan. The block is found by
    its marker in the section title *or* body: real plans write it as a bold
    paragraph inside a larger section rather than as its own heading.
    """
    lines = plan_text.split('\n')
    low = command.lineno - 1
    nearby = [lines[index] for index in range(max(0, low - 2), min(len(lines), low + 3))]
    dedicated = []
    for title, start, end in parse_sections(plan_text):
        body = '\n'.join(lines[start:end])
        if TOOL_VERIFICATION_SECTION_RE.search(title) or \
                TOOL_VERIFICATION_SECTION_RE.search(body):
            dedicated.extend(lines[start:end])
    return nearby + dedicated


def has_verification(command, plan_text):
    """(version, semantics) found for this command's owning tool."""
    evidence = verification_evidence(command, plan_text)
    for tool in command.tools:
        version_re = tool_version_re(tool)
        for line in evidence:
            if not re.search(r'\b' + re.escape(tool) + r'\b', line, re.IGNORECASE):
                continue
            if not (SEMANTICS_RE.search(line) or LIVE_PROBE_RE.search(line)):
                continue
            if not command.versioned:
                return True, tool  # a system control: name the owner, no version
            version = bool(version_re.search(line)) or bool(
                re.search(r'版本|version', line, re.IGNORECASE) and VERSION_RE.search(line))
            if version:
                return True, tool
    return False, None


# --- checks -----------------------------------------------------------------

class Result(object):
    def __init__(self, name, passed, details=None):
        self.name = name
        self.passed = passed
        self.details = details or []

    def render(self):
        head = 'PASS ' + self.name if self.passed else 'FAIL ' + self.name
        if self.details and not self.passed:
            return '\n'.join([head + ':'] + ['  ' + line for line in self.details])
        if self.details:
            return '\n'.join([head] + ['  ' + line for line in self.details])
        return head


def check_table_exists(gate_rows, table_text):
    if gate_rows:
        detail = ['%d gate row(s) classified' % len(gate_rows)]
        for row in gate_rows[:3]:
            detail.append('line %d: %s' % (row.lineno, row.target[:70] or row.row.text()[:70]))
        return Result('table_exists', True, detail)
    return Result('table_exists', False, [
        'no classification table found: no table row carries one of %s'
        % '/'.join(CLASSES),
        'the Phase 2 entry gate requires every candidate classified in a table',
    ])


def check_quote_fidelity(gate_rows, references):
    """Every classified row must cite a rule, and the rule must be real.

    Two failure modes, both silent greens before this existed: a rule column
    named something the parser did not recognise made the check verify nothing
    while reporting PASS, and a rule cell with no quotation at all — prose
    paraphrasing the reference — was equally unchecked. A fabricated quote and a
    missing quote are the same violation: neither is a rule.
    """
    missing = []
    unquoted = []
    checked = 0
    provenance = {}
    headers = None
    for row in gate_rows:
        if row.rule_column is None:
            headers = headers or list(row.table.header)
            unquoted.append('line %d: rule column not located — %s'
                            % (row.lineno, row.target[:60]))
            continue
        cell = row.rule
        if DITTO_RE.match(cell.strip()):
            # "同上" cites the row above rather than repeating its quote. The
            # citation is only as good as that row's, so verify it as that one.
            cell = row.ditto_source
        if not has_quoted_span(cell) and not NO_RULE_MARKER_RE.search(cell):
            unquoted.append('line %d: rule cell states no quotation and no '
                            '"no rule found" marker: %s'
                            % (row.lineno, cell[:90] or '(empty)'))
            continue
        for segment in quote_segments(cell):
            checked += 1
            found = [name for name, text in references.items() if segment in text]
            if found:
                for name in found:
                    provenance[name] = provenance.get(name, 0) + 1
            else:
                missing.append('line %d: %s' % (row.lineno, segment[:150]))
    details = ['%d quoted segment(s) verified against %d reference file(s)'
               % (checked, len(references))]
    if missing:
        details.append('%d quoted segment(s) not found in any reference'
                       % len(missing))
    if not gate_rows:
        # Nothing was checked, so this PASS carries no evidence. It is not a
        # failure — with no gate rows there is no rule column to quote — but it
        # must not read as though the quotes had been verified.
        details.append('no governing-rule cell to check: this check did not run')
    for name in sorted(provenance, key=lambda item: -provenance[item]):
        details.append('  %s: %d' % (name, provenance[name]))
    if headers:
        details.append('rule column not located — headers seen: %s'
                       % ' | '.join(headers))
        details.append('name it 管辖规则 or Governing rule (any of: %s)'
                       % ', '.join(RULE_COLUMN_KEYWORDS))
    if unquoted:
        details.append('%d row(s) cite no verifiable rule:' % len(unquoted))
        details.extend(unquoted)
    if missing:
        details.append('%d segment(s) not found verbatim in the references:'
                       % len(missing))
        details.extend(missing)
    if missing or unquoted or headers:
        return Result('quote_fidelity', False, details)
    return Result('quote_fidelity', True, details)


def has_quoted_span(cell):
    """Whether the cell quotes anything at all.

    Same threshold as quote_segments(), so presence and verification cannot
    disagree about which quotations exist.
    """
    return bool(re.search(r'"[^"]+"|“[^”]+”|‘[^’]+’|「[^」]+」', cell))


def quote_segments(cell):
    """Quoted segments in a governing-rule cell, ellipsis-split.

    Each delimiter has to sit on a word boundary, or an English apostrophe pair
    ("they're ... isn't") reads as a quotation and invents a segment. Segments
    under four characters are dropped as noise.
    """
    segments = []
    patterns = (
        r'(?<![0-9A-Za-z])"((?:[^"\\]|\\.)+)"(?![0-9A-Za-z])',
        r'(?<![0-9A-Za-z])“([^”]+)”(?![0-9A-Za-z])',
        r'(?<![0-9A-Za-z])‘([^’]+)’(?![0-9A-Za-z])',
        r"(?<![0-9A-Za-z])'([^']+)'(?![0-9A-Za-z])",
        r'(?<![0-9A-Za-z])「([^」]+)」(?![0-9A-Za-z])',
    )
    for pattern in patterns:
        for match in re.finditer(pattern, cell):
            raw = match.group(1)
            for part in QUOTE_SPLIT_RE.split(raw):
                plain = normalize(part)
                # Four characters, not twelve: at twelve a fabricated "Zzqqxx"
                # or "Keep" was dropped before verification and reported as
                # though nothing had been quoted.
                if len(plain) < 4 or NO_RULE_MARKER_RE.search(plain):
                    continue
                if plain not in segments:
                    segments.append(plain)
    return segments


def unrecognized_command_lines(plan_text, commands):
    """Command-shaped chunks the destructive-command list did not match.

    DESTRUCTIVE_PATTERNS is a declared allowlist, so an unlisted command is not
    checked rather than failed on. Reporting "0 destructive command(s) checked"
    for a plan full of commands would read as "checked and found clean", which is
    the opposite of the truth, so the count is surfaced instead.
    """
    missed = []
    for lineno, origin, chunk in command_chunks(plan_text):
        if any(pattern.search(chunk) for _tools, pattern, _wide, _versioned
               in DESTRUCTIVE_PATTERNS):
            continue  # recognized — excluded on purpose or not, it was seen
        if READ_ONLY_PROBE_RE.match(chunk) or DRY_RUN_RE.search(chunk):
            continue
        if READ_ONLY_SUBCOMMAND_RE.search(chunk):
            continue
        if not looks_like_command(chunk, origin):
            continue
        missed.append((lineno, chunk))
    return missed


# Read-only invocations whose program name is itself mutating elsewhere
# (`docker rmi` versus `docker system df`), so the program alone cannot decide.
READ_ONLY_SUBCOMMAND_RE = re.compile(
    r'\b(?:docker|orbctl|orb)\s+(?:system\s+df|images|ps|volume\s+ls|inspect|info|'
    r'version|buildx?\s+du)\b|\bbrew\s+--cache\b|\buv\s+cache\s+dir\b|'
    r'\bnpm\s+config\s+get\b|\bpnpm\s+store\s+path\b|\b(?:du|df|lsof)\b|'
    r'\blist\b|--version\b',
    re.IGNORECASE,
)


def looks_like_command(chunk, origin='prose'):
    """A chunk that reads as a command line: a program, then arguments.

    Chinese prose and plain table values are excluded — two English words such as
    "Docker build cache" or a hostname are not commands — so a chunk also needs a
    flag, a path or a number, unless it sits in the table that lists the plan's
    commands, where a cell is a command by construction.
    """
    text = chunk.strip().lstrip('`\'" ')
    if not text or re.search(r'[\u4e00-\u9fff]', text):
        return False
    parts = text.split()
    if len(parts) < 2 or not re.fullmatch(r'[A-Za-z][\w.+-]*', parts[0].rsplit('/', 1)[-1]):
        return False
    if origin == 'cmdtable':
        return True
    return bool(re.search(r'\s-{1,2}[A-Za-z]|[/~]|\d', text))


def check_target_coverage(commands, gate_rows, plan_tables, plan_text=''):
    """No state-changing command may name a target absent from the table.

    A command with no stated target at all is unattributable rather than
    uncovered. With rows to check against that is a gap in the plan's wording,
    not a missing classification, so it is reported without failing; with an
    empty table nothing can be verified, which is the failure.
    """
    unmatched = []
    unattributed = []
    for command in commands:
        row, resolvable, target = attribute(command, gate_rows, plan_tables)
        if row is not None:
            continue
        if not resolvable and gate_rows:
            unattributed.append('line %d: %s (no stated target to match)'
                                % (command.lineno, command.text[:90]))
            continue
        unmatched.append('line %d: %s' % (command.lineno, command.text[:90]))
        unmatched.append('    stated target: %s' % target[:90])
    details = ['%d destructive command(s) checked' % len(commands)]
    if plan_text:
        missed = unrecognized_command_lines(plan_text, commands)
        if missed:
            details.append('%d command-shaped line(s) not recognized — coverage '
                           'incomplete' % len(missed))
            details.extend('line %d: %s' % (lineno, chunk[:80])
                           for lineno, chunk in missed[:8])
    if unattributed:
        details.append('%d command(s) name no target, so no row could be matched '
                       '(not counted as a violation):' % len(unattributed))
        details.extend(unattributed)
    if unmatched:
        details.append('%d command(s) name a target absent from the table:'
                       % (len(unmatched) // 2))
        details.extend(unmatched)
        return Result('target_coverage', False, details)
    return Result('target_coverage', True, details)


def has_quoted_direction(cells):
    """Whether the row quotes what the user actually said.

    Deliberately not quote_segments(): that one drops short fragments, and a
    quoted direction is often only a handful of characters.
    """
    text = ' '.join(cells)
    return any(re.search(pattern, text)
               for pattern in (r'"[^"]+"', r'“[^”]+”', r'「[^」]+」', r'‘[^’]+’'))


def check_action_set_classes(gate_rows):
    """Police which classes may sit in the action set.

    Fails closed when the table classifies rows but no row's verdict can be
    read: a green light on an unchecked action set is worse than a false alarm,
    because it teaches the reader that a PASS here means something it does not.
    """
    violations = []
    counts = {'in action set': 0, 'unlocked by user': 0, 'not in action set': 0}
    unreadable = []
    for row in gate_rows:
        if not row.verdict:
            unreadable.append(row)
            continue
        counts[row.verdict] = counts.get(row.verdict, 0) + 1
        # "no rule found" is itself a finding, and the gate says such a target is
        # USER-DECISION: the plan asks before proposing anything for it. Labelling
        # it PROPOSABLE let an uncovered target lead the action set.
        if (row.rule and NO_RULE_MARKER_RE.search(row.rule)
                and not has_quoted_span(row.rule) and row.cls != 'USER-DECISION'):
            violations.append('line %d: %s cites "no rule found" — a target no '
                              'reference covers must be USER-DECISION and asked '
                              'about, not %s' % (row.lineno, row.cls, row.cls))
            continue
        # USER-DATA is never in an action set under any verdict, so it is checked
        # before the verdict-specific branches.
        if in_action_set(row) and row.cls == 'USER-DATA':
            violations.append('line %d: USER-DATA row carries a state-changing '
                              'verdict' % row.lineno)
        elif row.verdict == 'in action set':
            if row.cls not in ('PROPOSABLE', 'REBUILDABLE'):
                violations.append('line %d: %s is "%s" — only PROPOSABLE or REBUILDABLE '
                                  'may sit in the action set'
                                  % (row.lineno, row.cls, row.verdict))
            elif row.cls == 'PROPOSABLE' and not has_never_used_evidence(row):
                violations.append('line %d: PROPOSABLE in the action set states no '
                                  'never-used evidence (dead project, explicit user '
                                  'statement or artifact check)' % row.lineno)
        elif row.verdict == 'unlocked by user':
            # The legitimate route in for a PRESERVE row, but only with the
            # user's direction quoted — accepting a cost you stated is not the
            # user naming the target.
            if row.cls in ('PRESERVE', 'USER-DECISION'):
                if row.verdict_column is None:
                    violations.append('line %d: %s marked unlocked but the verdict '
                                      'column cannot be located, so the user\'s '
                                      'direction cannot be read' % (row.lineno, row.cls))
                elif not has_quoted_direction(row.verdict_cells()):
                    violations.append('line %d: %s marked unlocked without the user\'s '
                                      'direction quoted' % (row.lineno, row.cls))
    details = ['in action set: %d, unlocked by user: %d, not in action set: %d'
               % (counts.get('in action set', 0), counts.get('unlocked by user', 0),
                  counts.get('not in action set', 0))]
    if gate_rows and not any(row.verdict for row in gate_rows):
        details.append('verdict column unrecognized — no row states an action-set '
                       'position, so the action set was not checked at all')
        details.append('use one of: in action set / 入动作集 / 在动作集 / '
                       'not in action set / 不入动作集 / 不在动作集 / '
                       'unlocked by user / 用户点名')
        details.append('%d classified row(s) had no readable verdict:' % len(unreadable))
        details.extend('line %d: %s' % (row.lineno, row.row.text()[:90])
                       for row in unreadable[:8])
        return Result('action_set_classes', False, details)
    if unreadable:
        details.append('%d row(s) state no action-set position (reported, not ranked)'
                       % len(unreadable))
    if violations:
        details.extend(violations)
        return Result('action_set_classes', False, details)
    return Result('action_set_classes', True, details)


def verdict_unreadable(gate_rows):
    """Rows exist but not one states an action-set position.

    The checks that scope themselves to "in-action-set rows" would otherwise
    report a clean bill on a table they could not read — the same silent green
    action_set_classes used to produce.
    """
    return bool(gate_rows) and not any(row.verdict for row in gate_rows)


def check_category_wide_exclusion(commands, gate_rows, plan_tables):
    violations = []
    for command in commands:
        if not command.category_wide:
            continue
        row, _resolvable, _target = attribute(command, gate_rows, plan_tables)
        if row is None:
            continue  # mapped to no action set: an unlock option in prose, allowed
        if in_action_set(row):
            violations.append('line %d: category-wide command in the action set: %s'
                              % (command.lineno, command.text[:90]))
            violations.append('    mapped row (line %d) is "%s"' % (row.lineno, row.verdict))
    unplaced = [command for command in commands
                if command.category_wide and command.origin == 'cmdtable'
                and attribute(command, gate_rows, plan_tables)[0] is None]
    if unplaced:
        # A category-wide command the table cannot place is not "outside the
        # action set" — it is undecidable, and saying otherwise is a false clean
        # bill on exactly the shape the hard-exclusion rules exist to stop.
        violations.append('%d category-wide command(s) in the plan\'s command list '
                           'map to no classified row, so whether they sit in the '
                           'action set cannot be determined — classify the target '
                           'or drop the command' % len(unplaced))
        violations.extend('line %d: %s' % (command.lineno, command.text[:90])
                          for command in unplaced)
    if verdict_unreadable(gate_rows):
        # With no readable verdict this check cannot tell a proposal from an
        # unlock option, so it names what it is leaving alone instead of
        # passing silently.
        unplaced = [command for command in commands if command.category_wide]
        if unplaced:
            violations.append('verdict column unrecognized: %d category-wide '
                              'command(s) cannot be placed in or out of the action '
                              'set — fix the verdict column (see action_set_classes)'
                              % len(unplaced))
            violations.extend('line %d: %s' % (command.lineno, command.text[:90])
                              for command in unplaced)
    if violations:
        violations.insert(0, '%d finding(s) about category-wide commands:'
                           % _count_findings(violations))
        return Result('category_wide_exclusion', False, violations)
    return Result('category_wide_exclusion', True, [
        '%d category-wide command(s), none of them in the action set'
        % sum(1 for command in commands if command.category_wide)])


def _count_findings(lines):
    """How many findings a detail list carries, for its own summary line."""
    return sum(1 for line in lines if line.startswith('line '))


def check_lead_rule(commands, gate_rows, plan_text):
    if not commands:
        return Result('lead_rule', True, ['no destructive command to rank'])
    action_rows = [row for row in gate_rows if in_action_set(row)]
    if not action_rows:
        if verdict_unreadable(gate_rows):
            # Not "the action set is legitimately empty" — it could not be read.
            return Result('lead_rule', True, [
                'verdict column unrecognized: no in-action-set row could be '
                'identified, so nothing was ranked (see action_set_classes)'])
        return Result('lead_rule', True, [
            'no in-action-set row: nothing to rank (an empty action set with a '
            'decision list is a legitimate outcome)'])
    releases = []
    for row in action_rows:
        value = row.release
        if value is None:
            value = plan_release_lookup(plan_text, row.tokens)
        if value is not None:
            releases.append((value, row))
    if not releases:
        return Result('lead_rule', True, [
            'every in-action-set release is unknown: the ranking rule cannot apply'])
    biggest, biggest_row = max(releases, key=lambda item: item[0])
    # The lead is the first command in the table that lists the plan's commands.
    # A command restated elsewhere — the tool-verification block, a status
    # section — must not displace it, and no keyword decides which block that
    # is: a plan may legitimately head a section "现状与已知问题（semantics 已
    # 核对）" and still be stating its real lead there.
    listed = [command for command in commands if command.origin == 'cmdtable']
    first = (listed or commands)[0]
    target, _row, _resolvable = resolve_target(first, parse_tables(plan_text))
    identifiers = target_identifiers(first, target)
    program = argv0(first.text)
    leading_row = next(
        (item for item in releases
         if tokens_overlap(identifiers, item[1].basename_tokens)
         or program_matches(program, item[1])), None)
    label = biggest_row.target[:50] or biggest_row.row.text()[:50]
    if leading_row is not None and leading_row[1] is biggest_row:
        return Result('lead_rule', True, [
            'lead command (line %d) targets the largest in-action-set release: '
            '%s (%.2f GiB)' % (first.lineno, label, biggest / UNIT_BYTES['GiB'])])
    hotspot_rows = [row for row in action_rows if row.hotspot]
    if any(tokens_overlap(identifiers, row.basename_tokens)
           or program_matches(program, row) for row in hotspot_rows):
        return Result('lead_rule', True, [
            'lead command (line %d) targets a row marked as the hotspot/bottleneck'
            % first.lineno])
    return Result('lead_rule', False, [
        'lead command (line %d): %s' % (first.lineno, first.text[:90]),
        'its target does not map to the largest in-action-set release '
        '(%s, %.2f GiB, line %d) and carries no hotspot/bottleneck marker'
        % (label, biggest / UNIT_BYTES['GiB'], biggest_row.lineno),
    ])


def plan_release_lookup(plan_text, tokens):
    for row_tokens, value, _candidate in plan_release_table(plan_text):
        if tokens & row_tokens:
            return value
    return None


def check_tool_verification(commands, plan_text, gate_rows, plan_tables):
    """Version + semantics source for every command the plan would actually run.

    Scope is the proposals: a command mapped to a row that is not in the action
    set is a report or an unlock option, and the gate does not demand its tool
    verification. A command that maps to no row at all is checked — an
    unclassified state change is exactly what the gate exists to stop.
    """
    missing = []
    checked = 0
    skipped = 0
    for command in commands:
        row, _resolvable, _target = attribute(command, gate_rows, plan_tables)
        if row is not None and not in_action_set(row):
            skipped += 1
            continue
        checked += 1
        found, tool = has_verification(command, plan_text)
        if not found and command_quoted_in_gate_rule(command, gate_rows):
            found, tool = True, 'skill transcription'
        if not found:
            missing.append('line %d: %s (owning tool: %s)'
                           % (command.lineno, command.text[:90], '/'.join(command.tools)))
    details = ['%d proposed command(s) checked for version + semantics source, '
               '%d not proposed (reported or unlock-only) so not checked'
               % (checked, skipped)]
    if missing:
        details.append('%d command(s) lack a recorded tool verification:' % len(missing))
        details.extend(missing)
        return Result('tool_verification', False, details)
    return Result('tool_verification', True, details)


def command_quoted_in_gate_rule(command, gate_rows):
    """The governing rule that sanctioned this command also states its semantics.

    The gate allows the skill's own transcription as the semantics source when
    it is named as such, and a rule quoting the exact command is that case.
    """
    for gate_row in gate_rows:
        if not in_action_set(gate_row):
            continue
        rule = normalize(gate_row.rule)
        for _tools, pattern, _wide, _versioned in DESTRUCTIVE_PATTERNS:
            match = pattern.search(command.text)
            if match and normalize(match.group(0)) in rule:
                return True
    return False


# --- reference corpus -------------------------------------------------------

def load_references(reference, bundle):
    """Corpus the quotes are verified against.

    An explicit --reference is the whole corpus. The default also accepts the
    sibling reference files and SKILL.md, because the gate contract allows a
    quote from "the route's dedicated reference" and real plans quote the skill
    body as well; SKILL.md-only resolutions are reported so they stay visible.

    Returns (normalized corpus, raw corpus, includes_skill). Both forms are
    needed: quotes are matched against the normalized text, while anything that
    reads a *table* out of the reference needs the raw text — normalization
    collapses newlines, which would turn every table into one long line.
    """
    corpus = {}
    raw = {}
    if reference:
        paths = [Path(reference)] if Path(reference).is_file() else \
            sorted(Path(reference).glob('*.md'))
        for path in paths:
            text = path.read_text(encoding='utf-8')
            corpus[path.name] = normalize(text)
            raw[path.name] = text
        if not corpus:
            raise ValueError('no markdown found under %s' % reference)
        return corpus, raw, False
    for path in sorted((bundle / 'references').glob('*.md')):
        text = path.read_text(encoding='utf-8')
        corpus[path.name] = normalize(text)
        raw[path.name] = text
    skill = bundle / 'SKILL.md'
    if skill.is_file():
        text = skill.read_text(encoding='utf-8')
        corpus['SKILL.md'] = normalize(text)
        raw['SKILL.md'] = text
    return corpus, raw, True


# --- entry point ------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        description='Check a macos-cleaner Phase 2 plan against the entry gate.')
    parser.add_argument('--table', required=True,
                        help='file holding the classification table')
    parser.add_argument('--plan', required=True,
                        help='file holding the plan')
    parser.add_argument('--reference', default=None,
                        help='reference corpus for governing-rule quotes '
                             '(default: the whole bundle — references/*.md plus '
                             'SKILL.md. An explicit path becomes the ONLY corpus '
                             'and may reject compliant plans that quote elsewhere; '
                             'the default is the calibrated configuration.)')
    parser.add_argument('--verbose', action='store_true',
                        help='print the parsed rows as well as the verdicts')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    bundle = Path(__file__).resolve().parents[1]
    for label, path in (('table', args.table), ('plan', args.plan)):
        if not Path(path).is_file():
            print('exit 2: %s file not found: %s' % (label, path), file=sys.stderr)
            return 2
    try:
        table_text = Path(args.table).read_text(encoding='utf-8')
        plan_text = Path(args.plan).read_text(encoding='utf-8')
        references, raw_references, includes_skill = load_references(
            args.reference, bundle)
    except (OSError, ValueError) as error:
        print('exit 2: %s' % error, file=sys.stderr)
        return 2

    gate_rows = collect_gate_rows(table_text)
    plan_tables = parse_tables(plan_text)
    commands = find_destructive_commands(plan_text)

    results = [
        check_table_exists(gate_rows, table_text),
        check_quote_fidelity(gate_rows, references),
        check_target_coverage(commands, gate_rows, plan_tables, plan_text),
        check_action_set_classes(gate_rows),
        check_preserve_downgrade(gate_rows, raw_references, bundle),
        check_category_wide_exclusion(commands, gate_rows, plan_tables),
        check_lead_rule(commands, gate_rows, plan_text),
        check_tool_verification(commands, plan_text, gate_rows, plan_tables),
    ]

    for result in results:
        print(result.render())

    failures = [result for result in results if not result.passed]
    print('')
    if includes_skill:
        print('reference corpus: bundle references/*.md + SKILL.md '
              '(an explicit --reference would be used alone)')
    print('%d check(s) run, %d passed, %d failed'
          % (len(results), len(results) - len(failures), len(failures)))
    if failures:
        print('exit 1: %s — fix the plan; do not weaken the checker'
              % ', '.join(result.name for result in failures))
        return 1
    print('exit 0: the plan may be sent')
    return 0


if __name__ == '__main__':
    sys.exit(main())
