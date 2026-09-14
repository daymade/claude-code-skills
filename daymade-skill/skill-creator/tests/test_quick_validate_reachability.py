"""Reference reachability: every bundled reference must have a route from SKILL.md.

A reference nothing links is dead weight at runtime — the executing agent is
never told to open it — and it passes every other gate, because the file exists
and the frontmatter is fine. These cases were drawn from real skills in this
marketplace at the time the check was added.
"""
from pathlib import Path

from scripts.quick_validate import find_unreachable_references


def _skill(root: Path, body: str, refs: dict[str, str] | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(body, encoding="utf-8")
    for name, text in (refs or {}).items():
        target = root / "references" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def test_no_references_directory_is_not_a_finding(tmp_path):
    skill = _skill(tmp_path / "bare", "# Bare\n\nNo bundled references at all.\n")
    content = (skill / "SKILL.md").read_text()
    assert find_unreachable_references(skill, content) == []


def test_directly_linked_reference_is_reachable(tmp_path):
    skill = _skill(
        tmp_path / "linked",
        "# Linked\n\nRead [references/guide.md](references/guide.md) before starting.\n",
        {"guide.md": "# Guide\n"},
    )
    content = (skill / "SKILL.md").read_text()
    assert find_unreachable_references(skill, content) == []


def test_unlinked_reference_is_reported(tmp_path):
    skill = _skill(
        tmp_path / "orphan",
        "# Orphan\n\nSKILL.md never mentions the bundled file.\n",
        {"orphan.md": "# Orphan\n"},
    )
    content = (skill / "SKILL.md").read_text()
    assert find_unreachable_references(skill, content) == ["references/orphan.md"]


def test_reachability_is_transitive(tmp_path):
    """A reference linked from a reachable reference is reachable — the agent
    can follow the chain, so flagging it would be a false positive."""
    skill = _skill(
        tmp_path / "chain",
        "# Chain\n\nStart at [references/entry.md](references/entry.md).\n",
        {
            "entry.md": "# Entry\n\nThen read references/deeper.md for the details.\n",
            "deeper.md": "# Deeper\n",
        },
    )
    content = (skill / "SKILL.md").read_text()
    assert find_unreachable_references(skill, content) == []


def test_bare_filename_in_skill_md_counts_as_a_link(tmp_path):
    """The healthy form this check first got wrong.

    A `### references/` section listing each file by name with a line on what it
    holds is exactly what the reference guidance asks for. Requiring the full
    `references/<name>` path flagged a skill doing it correctly, and a check that
    fails on healthy input is the one that gets bypassed.
    """
    skill = _skill(
        tmp_path / "section",
        "# Section\n\n### references/\n\n"
        "- `api_notes.md`: endpoint shapes and payloads.\n"
        "- `limits.md`: rate limits and failure handling.\n",
        {"api_notes.md": "# API notes\n", "limits.md": "# Limits\n"},
    )
    content = (skill / "SKILL.md").read_text()
    assert find_unreachable_references(skill, content) == []


def test_bare_filename_counts_as_a_link_between_references(tmp_path):
    """References routinely cite siblings by name alone rather than by path."""
    skill = _skill(
        tmp_path / "byname",
        "# ByName\n\nSee [references/entry.md](references/entry.md).\n",
        {
            "entry.md": "# Entry\n\nThe field table lives in schema_notes.md.\n",
            "schema_notes.md": "# Schema notes\n",
        },
    )
    content = (skill / "SKILL.md").read_text()
    assert find_unreachable_references(skill, content) == []


def test_reports_only_the_unreachable_ones(tmp_path):
    skill = _skill(
        tmp_path / "mixed",
        "# Mixed\n\nRead [references/used.md](references/used.md) first.\n",
        {"used.md": "# Used\n", "unused.md": "# Unused\n"},
    )
    content = (skill / "SKILL.md").read_text()
    assert find_unreachable_references(skill, content) == ["references/unused.md"]


def test_nested_reference_directories_are_covered(tmp_path):
    skill = _skill(tmp_path / "nested", "# Nested\n\nNothing linked.\n")
    nested = skill / "references" / "route-a"
    nested.mkdir(parents=True)
    (nested / "layout.md").write_text("# Layout\n", encoding="utf-8")
    content = (skill / "SKILL.md").read_text()
    assert find_unreachable_references(skill, content) == ["references/route-a/layout.md"]


def test_non_markdown_files_are_ignored(tmp_path):
    """Data files under references/ are loaded by scripts, not linked in prose."""
    skill = _skill(tmp_path / "data", "# Data\n\nNothing linked.\n")
    (skill / "references").mkdir()
    (skill / "references" / "table.json").write_text("{}\n", encoding="utf-8")
    content = (skill / "SKILL.md").read_text()
    assert find_unreachable_references(skill, content) == []
