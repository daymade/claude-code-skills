"""Tests for multi-domain support: --domain a,b loads the union, and the
write commands still refuse ambiguity.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.correction_repository import CorrectionRepository, normalize_domains  # noqa: E402
from core.correction_service import CorrectionService  # noqa: E402
from cli.commands import _format_domain_hint  # noqa: E402


class TestNormalizeDomains:
    def test_none(self):
        assert normalize_domains(None) is None

    def test_single_string(self):
        assert normalize_domains("alpha") == ["alpha"]

    def test_comma_separated(self):
        assert normalize_domains("alpha,beta") == ["alpha", "beta"]

    def test_whitespace_and_duplicates_cleaned_order_kept(self):
        assert normalize_domains(" b , a ,b ") == ["b", "a"]

    def test_empty_string_is_no_filter(self):
        assert normalize_domains("") is None
        assert normalize_domains(" , ,") is None

    def test_malformed_only_commas_is_no_filter(self):
        assert normalize_domains(",,") is None

    def test_list_passthrough_with_comma_pieces(self):
        assert normalize_domains(["a,b", "c"]) == ["a", "b", "c"]


def _make_service() -> CorrectionService:
    test_dir = Path(tempfile.mkdtemp())
    repo = CorrectionRepository(test_dir / "corrections.db")
    service = CorrectionService(repo)
    service.add_correction("错词甲", "对词甲", "proj-alpha", force=True)
    service.add_correction("错词乙", "对词乙", "proj-beta", force=True)
    service.add_correction("克劳锐", "Claude", "tech", force=True)
    return service


class TestMultiDomainLoading:
    def test_union_loads_all_listed_domains(self):
        service = _make_service()
        corrections, meta = service.get_corrections_with_metadata(["proj-alpha", "proj-beta"])
        assert corrections == {"错词甲": "对词甲", "错词乙": "对词乙"}
        # Each rule's own domain travels in metadata, so a union load never
        # loses which project a rule came from.
        assert meta["错词甲"]["domain"] == "proj-alpha"
        assert meta["错词乙"]["domain"] == "proj-beta"

    def test_string_with_commas_behaves_like_list(self):
        service = _make_service()
        corrections, _ = service.get_corrections_with_metadata("proj-alpha, proj-beta")
        assert set(corrections) == {"错词甲", "错词乙"}

    def test_single_domain_still_filters(self):
        service = _make_service()
        corrections, _ = service.get_corrections_with_metadata("proj-alpha")
        assert corrections == {"错词甲": "对词甲"}

    def test_no_domain_loads_everything(self):
        service = _make_service()
        corrections, _ = service.get_corrections_with_metadata(None)
        assert "克劳锐" in corrections

    def test_get_corrections_multi(self):
        service = _make_service()
        corrections = service.get_corrections(["proj-alpha", "tech"])
        assert corrections == {"错词甲": "对词甲", "克劳锐": "Claude"}


class TestCrossDomainCollision:
    def _service_with_collision(self) -> CorrectionService:
        test_dir = Path(tempfile.mkdtemp())
        service = CorrectionService(CorrectionRepository(test_dir / "corrections.db"))
        service.add_correction("同词", "项目A版", "proj-a", force=True)
        service.add_correction("同词", "项目B版", "proj-b", force=True)
        return service

    def test_earliest_named_domain_wins(self):
        service = self._service_with_collision()
        corrections, meta = service.get_corrections_with_metadata(["proj-a", "proj-b"])
        assert corrections["同词"] == "项目A版"
        assert meta["同词"]["domain"] == "proj-a"

    def test_order_flip_flips_winner(self):
        service = self._service_with_collision()
        corrections, _ = service.get_corrections_with_metadata(["proj-b", "proj-a"])
        assert corrections["同词"] == "项目B版"

    def test_get_corrections_same_rule(self):
        service = self._service_with_collision()
        assert service.get_corrections(["proj-a", "proj-b"])["同词"] == "项目A版"
        assert service.get_corrections(["proj-b", "proj-a"])["同词"] == "项目B版"

    def test_no_filter_keeps_last_writer(self):
        # Historical behavior with no --domain: SQLite scan order (later insert
        # wins). Locked in so the deterministic rule never leaks into the
        # unfiltered path.
        service = self._service_with_collision()
        assert service.get_corrections(None)["同词"] == "项目B版"


class TestMultiDomainHint:
    STATS = {"myproject": 7, "myproject-alt": 2, "general": 51, "tech": 350}

    def test_multi_domain_excludes_every_requested(self):
        hint = _format_domain_hint(0, ["myproject", "myproject-alt"], self.STATS)
        assert "0 of 9 rules in domain 'myproject,myproject-alt' matched" in hint
        assert "myproject (7)" not in hint
        assert "myproject-alt (2)" not in hint
        assert "general (51)" in hint

    def test_raw_comma_string_still_works(self):
        hint = _format_domain_hint(0, "myproject,myproject-alt", self.STATS)
        assert "0 of 9 rules" in hint

    def test_single_domain_unchanged(self):
        hint = _format_domain_hint(0, "myproject", self.STATS)
        assert "0 of 7 rules in domain 'myproject' matched" in hint
        assert "myproject (7)" not in hint
