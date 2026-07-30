"""Tests for _format_domain_hint — the 0-correction explanation must not lie.

A 0-match run with --domain has two honest readings: the domain has rules
but this transcript simply matched none (fine), or the domain name has no
rules at all (likely a typo). The old message printed "no rules in domain"
for both, which falsely told operators their loaded domain was empty.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.commands import _format_domain_hint  # noqa: E402


STATS = {"myproject": 7, "general": 51, "tech": 350}


class TestFormatDomainHint:
    def test_domain_has_rules_but_zero_matched(self):
        hint = _format_domain_hint(0, "myproject", STATS)
        assert "0 of 7 rules in domain 'myproject' matched" in hint
        assert "no rules in domain" not in hint
        # The requested domain is excluded from the Other-domains list,
        # but the total counts every rule running without --domain would use.
        assert "myproject (7)" not in hint
        assert "general (51)" in hint
        assert "all 408 rules" in hint

    def test_domain_truly_empty_keeps_no_rules_wording(self):
        hint = _format_domain_hint(0, "typo-domain", STATS)
        assert "no rules in domain 'typo-domain'" in hint
        assert "Available: general (51)" in hint

    def test_no_hint_when_corrections_were_found(self):
        assert _format_domain_hint(3, "myproject", STATS) is None

    def test_no_hint_without_domain_flag(self):
        assert _format_domain_hint(0, None, STATS) is None

    def test_no_hint_when_database_is_empty(self):
        assert _format_domain_hint(0, "myproject", {}) is None

    def test_no_hint_when_requested_domain_is_the_only_domain(self):
        assert _format_domain_hint(0, "general", {"general": 51}) is None
