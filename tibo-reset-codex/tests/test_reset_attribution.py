import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "reset_attribution", Path(__file__).resolve().parents[1] / "scripts" / "reset_attribution.py")
attr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(attr)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "account-switch-replay.json"
REAL_BAD_MESSAGE = (
    "当前 CLI 账号已在 21:10 左右重置；原因与影响范围未核实，"
    "暂时不能称为全员或大范围静默重置。"
)


def load_failure_bundle():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def natural_bundle():
    return {
        "transitions": [{
            "before": {
                "source": "api", "source_ref": "before", "identity": "verified",
                "account_ref": "a1b2c3d4", "checked_at_utc": "2026-10-17T12:00:00Z",
                "window_seconds": 604800, "used_percent": 80,
                "reset_at_utc": "2026-10-17T13:00:00Z", "plan_type": "pro",
            },
            "after": {
                "source": "api", "source_ref": "after", "identity": "verified",
                "account_ref": "a1b2c3d4", "checked_at_utc": "2026-10-17T13:01:00Z",
                "window_seconds": 604800, "used_percent": 0,
                "reset_at_utc": "2026-10-24T13:00:00Z", "plan_type": "pro",
            },
        }],
        "events": [],
    }


def current_only_bundle(events):
    return {
        "transitions": [{
            "before": None,
            "after": {
                "source": "api", "source_ref": "after", "identity": "verified",
                "account_ref": "a1b2c3d4", "checked_at_utc": "2026-10-17T13:32:00Z",
                "window_seconds": 604800, "used_percent": 0,
                "reset_at_utc": "2026-10-24T13:32:00Z", "plan_type": "pro",
            },
        }],
        "events": events,
    }


def usage_payload(account_ref="a1b2c3d4"):
    return {
        "status": "ok",
        "checked_at_utc": "2026-10-17T13:32:00+00:00",
        "source": "https://chatgpt.com/backend-api/wham/usage",
        "email": "redacted@example.invalid",
        "account_ref": account_ref,
        "plan_type": "pro",
        "windows": [{
            "window_seconds": 604800,
            "used_percent": 3,
            "remaining_percent": 97,
            "reset_at_utc": "2026-10-24T13:10:13+00:00",
        }],
        "banked_resets_available": 3,
        "banked_resets_applicable_now": 0,
        "notes": [],
    }


def evaluate_records(records, message=None):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "turn.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                        encoding="utf-8")
        return attr.evaluate_transcript(path, message)


class ResetAttributionTests(unittest.TestCase):
    def test_real_failure_shape_is_window_change_not_reset(self):
        result = attr.evaluate(load_failure_bundle())
        self.assertEqual(result["classification"], "unknown")
        self.assertEqual(result["claim_gate"]["same_account_reset"], "block")
        self.assertEqual(result["claim_gate"]["account_window_change"], "allow")
        self.assertEqual(result["observations"]["current_state"]["remaining_percent"], 97)
        self.assertEqual(result["observations"]["current_state"]["banked_available"], 3)
        self.assertIn("ANONYMOUS_HISTORY_CANNOT_INHERIT_CURRENT_IDENTITY", result["reason_codes"])
        claims = attr.claims_in_message(REAL_BAD_MESSAGE)
        self.assertEqual([c["claim"] for c in claims], [attr.CLAIM_SAME_ACCOUNT])
        self.assertEqual(result["claim_gate"][claims[0]["claim"]], "block")

    def test_direct_user_switch_correction_selects_account_switch(self):
        bundle = load_failure_bundle()
        bundle["events"] = [{
            "kind": "account_switch", "account_ref": "a1b2c3d4",
            "checked_at_utc": "2026-10-17T13:40:00Z",
            "source": "user", "source_ref": "user:account_switch",
        }]
        result = attr.evaluate(bundle)
        self.assertEqual(result["classification"], "account_switch")
        self.assertEqual(result["claim_gate"]["account_switch"], "allow")
        self.assertEqual(result["claim_gate"]["same_account_reset"], "block")
        self.assertEqual(result["observations"]["current_state"]["remaining_percent"], 97)

    def test_a_to_b_to_a_is_switch_even_when_outer_refs_match(self):
        bundle = load_failure_bundle()
        first = copy.deepcopy(bundle["transitions"][0])
        second = copy.deepcopy(bundle["transitions"][0])
        first["after"]["account_ref"] = "b2c3d4e5"
        first["after"]["checked_at_utc"] = "2026-10-17T13:00:00Z"
        second["before"] = copy.deepcopy(first["after"])
        second["after"]["account_ref"] = "a1b2c3d4"
        second["after"]["checked_at_utc"] = "2026-10-17T13:32:00Z"
        bundle["transitions"] = [first, second]
        result = attr.evaluate(bundle)
        self.assertEqual(result["classification"], "account_switch")
        self.assertEqual(result["claim_gate"]["same_account_reset"], "block")

    def test_same_endpoint_refs_and_anonymous_history_do_not_prove_reset(self):
        result = attr.evaluate(load_failure_bundle())
        self.assertFalse(any(c in ("natural_cycle", "banked_redeem", "account_reset_observed")
                             for c in result["candidate_causes"]))
        self.assertEqual(result["observations"]["same_account_reset"], "unknown")

    def test_natural_cycle_shape_allows_true_reset_answer(self):
        result = attr.evaluate(natural_bundle())
        self.assertEqual(result["classification"], "natural_cycle")
        self.assertEqual(result["claim_gate"]["same_account_reset"], "allow")
        claims = attr.claims_in_message("该账户已经重置；影响范围未核实。")
        self.assertEqual(claims[0]["claim"], attr.CLAIM_SAME_ACCOUNT)
        self.assertEqual(result["claim_gate"][claims[0]["claim"]], "allow")

    def test_direct_account_reset_and_banked_redeem_paths(self):
        direct = attr.evaluate(current_only_bundle([{
            "kind": "account_reset_observed", "account_ref": "a1b2c3d4",
            "checked_at_utc": "2026-10-17T13:32:00Z", "source": "user",
        }]))
        self.assertEqual(direct["classification"], "account_reset_observed")
        self.assertEqual(direct["claim_gate"]["same_account_reset"], "allow")

        banked_bundle = natural_bundle()
        banked_bundle["transitions"][0]["after"]["reset_at_utc"] = "2026-10-24T13:30:00Z"
        banked_bundle["events"] = [{
            "kind": "banked_redeem", "account_ref": "a1b2c3d4",
            "checked_at_utc": "2026-10-17T13:01:00Z", "source": "product_event",
        }]
        banked = attr.evaluate(banked_bundle)
        self.assertEqual(banked["classification"], "banked_redeem")
        self.assertEqual(banked["claim_gate"]["same_account_reset"], "allow")

    def test_official_global_scope_allows_only_matching_global_claim(self):
        result = attr.evaluate(current_only_bundle([{
            "kind": "official_global_reset", "account_ref": None, "scope": "all_paid",
            "checked_at_utc": "2026-10-17T13:32:00Z", "source": "official_post",
        }]))
        self.assertEqual(result["classification"], "official_global_reset")
        self.assertEqual(result["claim_gate"]["global_reset"], "allow")
        self.assertEqual(result["claim_gate"]["all_accounts"], "allow")
        claims = attr.claims_in_message("官方确认全员重置。")
        self.assertEqual(result["claim_gate"][claims[0]["claim"]], "allow")

        limited = attr.evaluate(current_only_bundle([{
            "kind": "official_global_reset", "account_ref": None, "scope": "unknown",
            "checked_at_utc": "2026-10-17T13:32:00Z", "source": "official_post",
        }]))
        self.assertEqual(limited["claim_gate"]["all_accounts"], "block")

    def test_last_refresh_never_changes_classification(self):
        classifications = []
        for hint in (None, "2026-10-17T12:59:00Z", "2026-09-01T00:00:00Z"):
            bundle = natural_bundle()
            if hint is not None:
                bundle["auth_hints"] = {"last_refresh_utc": hint}
            result = attr.evaluate(bundle)
            classifications.append(result["classification"])
            if hint is not None:
                self.assertIn("LAST_REFRESH_NON_DETERMINATIVE", result["reason_codes"])
        self.assertEqual(classifications, ["natural_cycle"] * 3)

    def test_missing_empty_and_incomparable_fields_fail_closed(self):
        bundle = natural_bundle()
        bundle["transitions"][0]["before"]["account_ref"] = ""
        with self.assertRaises(attr.AttributionError):
            attr.evaluate(bundle)

        bundle = natural_bundle()
        bundle["transitions"][0]["before"]["checked_at_utc"] = "2026-10-17T12:00:00"
        with self.assertRaises(attr.AttributionError):
            attr.evaluate(bundle)

        bundle = natural_bundle()
        bundle["transitions"][0]["before"]["window_seconds"] = 18000
        result = attr.evaluate(bundle)
        self.assertEqual(result["classification"], "unknown")
        self.assertEqual(result["claim_gate"]["same_account_reset"], "block")

        bundle = natural_bundle()
        bundle["events"] = [{
            "kind": "account_reset_observed", "account_ref": "b2c3d4e5",
            "checked_at_utc": "2026-10-17T13:01:00Z",
        }]
        self.assertEqual(attr.evaluate(bundle)["classification"], "natural_cycle")
        self.assertNotIn("account_reset_observed", attr.evaluate(bundle)["candidate_causes"])

    def test_mere_return_to_full_is_not_a_direct_reset_event(self):
        self.assertEqual(attr.user_events("weekly 回到 100% 了", "a1b2c3d4",
                                           "2026-10-17T13:32:00Z"), [])
        events = attr.user_events("这个账号已经重置了", "a1b2c3d4",
                                   "2026-10-17T13:32:00Z")
        self.assertEqual([e["kind"] for e in events], ["account_reset_observed"])

    def test_transcript_tool_result_and_real_failure_message(self):
        records = [
            {"type": "user", "uuid": "u1", "timestamp": "2026-10-17T13:30:00Z",
             "message": {"role": "user", "content": "现在什么情况"}},
            {"type": "user", "message": {"role": "user",
                 "content": "Base directory for this skill: /tmp/tibo-reset-codex\n\n# injected skill body"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "id": "t1", "input": {"command": "uv run python scripts/query_usage.py"}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": json.dumps(usage_payload())}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "id": "t2", "input": {"command": "scan_rollouts.py"}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t2", "content": "归零区间 20:55 100% → 21:10 3%"}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": REAL_BAD_MESSAGE}]}},
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "turn.jsonl"
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                            encoding="utf-8")
            result = attr.evaluate_transcript(path, REAL_BAD_MESSAGE)
        self.assertEqual(result["classification"], "unknown")
        self.assertTrue(result["blocked"])
        self.assertEqual(result["observations"]["current_state"]["remaining_percent"], 97)

    def test_transcript_user_switch_is_direct_evidence(self):
        records = [
            {"type": "user", "timestamp": "2026-10-17T13:40:00Z",
             "message": {"role": "user", "content": "这次是我换号了，并非重置"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "id": "usage",
                 "input": {"command": "uv run python scripts/query_usage.py"}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "usage", "content": json.dumps(usage_payload())}]}},
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "switch.jsonl"
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                            encoding="utf-8")
            result = attr.evaluate_transcript(path, "已更正：这是换号，不是重置；当前剩余 97%。")
        self.assertEqual(result["classification"], "account_switch")
        self.assertFalse(result["blocked"])

    def test_all_account_tense_and_english_variants(self):
        direct = current_only_bundle([{
            "kind": "account_reset_observed", "account_ref": "a1b2c3d4",
            "checked_at_utc": "2026-10-17T13:32:00Z",
        }])
        result = attr.evaluate(direct)
        for message in ("所有账户已重置。", "所有账户已被重置。", "All accounts have been reset.",
                        "所有付费账户已经重置。", "All paid accounts have been reset.",
                        "Every paid account has been reset."):
            with self.subTest(message=message):
                claims = attr.claims_in_message(message)
                self.assertEqual([c["claim"] for c in claims], [attr.CLAIM_ALL_ACCOUNTS])
                self.assertEqual(result["claim_gate"][attr.CLAIM_ALL_ACCOUNTS], "block")

    def test_banked_distribution_is_not_an_all_account_reset_claim(self):
        for message in ("40M 里程碑的 banked reset 已官宣全员发放并官宣全员到账。",
                        "备用重置已官宣全员发放。"):
            with self.subTest(message=message):
                self.assertEqual(attr.claims_in_message(message), [])
        claims = attr.claims_in_message("所有账户已经重置，banked reset 已兑现。")
        self.assertEqual([item["claim"] for item in claims], [attr.CLAIM_ALL_ACCOUNTS])

    def test_official_exceptions_and_plan_scopes_are_rejected(self):
        for text in ("Reset has landed for everyone except Plus.",
                     "Reset has landed for everyone excluding Plus.",
                     "Reset has landed for everyone but Plus.",
                     "Reset has landed for everyone on Pro and Plus.",
                     "Reset has landed for everyone on Team only."):
            with self.subTest(text=text):
                self.assertEqual(attr.official_events(text, "2026-10-17T13:32:00Z"), [])
        control = attr.official_events(
            "We have now reset usage for all paid subscriptions", "2026-10-17T13:32:00Z")
        self.assertEqual(control[0]["scope"], "all_paid")

    def test_passive_correction_and_unpunctuated_question_are_not_claims(self):
        for message in ("当前账号不是被重置，而是换号了。", "当前账户已经被重置了吗",
                        "当前账号不是已经被重置，而是换号了。", "当前账号并非已经被重置，而是换号了。"):
            with self.subTest(message=message):
                self.assertEqual(attr.claims_in_message(message), [])

    def test_user_questions_and_hedges_do_not_create_direct_events(self):
        for text in ("当前账户已经被重置了吗？", "当前账户已经被重置了吗",
                     "这个账号已经重置了没", "这个账号已经重置了没有",
                     "这个账号可能已经被重置了", "这次可能是我换号了",
                     "这个账号的 banked reset 可能已兑现", "这个账号有没有已经重置",
                     "这个账号是不是已经重置", "这个账号好像已经重置",
                     "这个账号已经重置了，可能", "My account was reset, maybe"):
            records = [
                {"type": "user", "timestamp": "2026-10-17T13:30:00Z",
                 "message": {"role": "user", "content": text}},
                {"type": "assistant", "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "name": "Bash", "id": "usage",
                     "input": {"command": "uv run python scripts/query_usage.py"}}]}},
                {"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "usage", "content": json.dumps(usage_payload())}]}},
            ]
            with self.subTest(text=text):
                self.assertEqual(attr.user_events(text, "a1b2c3d4", "2026-10-17T13:32:00Z"), [])
                result = evaluate_records(records, "当前账户已经重置。")
                self.assertEqual(result["classification"], "unknown")
                self.assertTrue(result["blocked"])
        for text in ("这次是我换号了吗？", "这个账号的 banked reset 已兑现了吗"):
            with self.subTest(text=text):
                self.assertEqual(attr.user_events(text, "a1b2c3d4", "2026-10-17T13:32:00Z"), [])
        mixed = attr.user_events("之前重置了吗？不是，是我换号了", "a1b2c3d4", "2026-10-17T13:32:00Z")
        self.assertEqual([event["kind"] for event in mixed], ["account_switch"])
        confirmed = attr.user_events("这个账号已经重置了，我确认", "a1b2c3d4", "2026-10-17T13:32:00Z")
        self.assertEqual([event["kind"] for event in confirmed], ["account_reset_observed"])

    def test_be_negations_and_uncertainty_are_not_positive_claims(self):
        for text in ("这个账号没有被重置", "这个账号尚未被重置", "这个账号不是被重置", "这个账号并非被重置",
                     "这个账号不是已经被重置", "这个账号并非已经被重置"):
            with self.subTest(text=text):
                self.assertEqual(attr.user_events(text, "a1b2c3d4", "2026-10-17T13:32:00Z"), [])
        for message in ("当前账户没有被重置。", "当前账户尚未被重置。", "无法确定当前账户已被重置。",
                        "当前账号不是已经被重置，而是换号了。", "当前账号并非已经被重置，而是换号了。"):
            with self.subTest(message=message):
                self.assertEqual(attr.claims_in_message(message), [])

    def test_quota_weekly_and_all_account_scope_claims(self):
        for message in ("当前额度已重置，原因未核实。", "weekly 已重置，原因未核实。"):
            with self.subTest(message=message):
                claims = attr.claims_in_message(message)
                self.assertEqual([c["claim"] for c in claims], [attr.CLAIM_SAME_ACCOUNT])
        direct = current_only_bundle([{
            "kind": "account_reset_observed", "account_ref": "a1b2c3d4",
            "checked_at_utc": "2026-10-17T13:32:00Z",
        }])
        result = attr.evaluate(direct)
        claims = attr.claims_in_message("所有账户已经重置。")
        self.assertEqual([c["claim"] for c in claims], [attr.CLAIM_ALL_ACCOUNTS])
        self.assertEqual(result["claim_gate"][attr.CLAIM_ALL_ACCOUNTS], "block")

    def test_official_negative_and_plan_only_scopes_are_rejected(self):
        for text in ("Reset has landed, but not for everyone.",
                     "Reset has landed for everyone on Pro only."):
            with self.subTest(text=text):
                self.assertEqual(attr.official_events(text, "2026-10-17T13:32:00Z"), [])

    def test_product_only_multi_account_and_weaker_cross_account_observation(self):
        transitions = []
        for ref, future in (("a1b2c3d4", "2026-10-20T12:00:00Z"),
                            ("b2c3d4e5", "2026-10-21T12:00:00Z")):
            transition = natural_bundle()["transitions"][0]
            transition["before"]["account_ref"] = ref
            transition["after"]["account_ref"] = ref
            transition["before"]["reset_at_utc"] = future
            transition["after"]["reset_at_utc"] = "2026-10-17T13:30:00Z"
            transitions.append(transition)
        result = attr.evaluate({"transitions": transitions, "events": []})
        self.assertEqual(result["claim_gate"][attr.CLAIM_MULTI_ACCOUNT], "allow")
        self.assertEqual(result["claim_gate"][attr.CLAIM_CROSS_ACCOUNT], "allow")

        natural_two = []
        for ref in ("a1b2c3d4", "b2c3d4e5"):
            transition = natural_bundle()["transitions"][0]
            transition["before"]["account_ref"] = ref
            transition["after"]["account_ref"] = ref
            natural_two.append(transition)
        weaker = attr.evaluate({"transitions": natural_two, "events": []})
        self.assertEqual(weaker["claim_gate"][attr.CLAIM_MULTI_ACCOUNT], "block")
        self.assertEqual(weaker["claim_gate"][attr.CLAIM_CROSS_ACCOUNT], "allow")

    def test_transcript_preserves_all_account_transitions(self):
        observations = []
        for ref, used, reset, checked in (
            ("a1b2c3d4", 80, "2026-10-20T12:00:00Z", "2026-10-17T12:00:00Z"),
            ("a1b2c3d4", 0, "2026-10-24T13:30:00Z", "2026-10-17T13:01:00Z"),
            ("b2c3d4e5", 75, "2026-10-21T12:00:00Z", "2026-10-17T12:02:00Z"),
            ("b2c3d4e5", 0, "2026-10-24T13:31:00Z", "2026-10-17T13:03:00Z"),
        ):
            item = usage_payload(ref)
            item["windows"][0]["used_percent"] = used
            item["windows"][0]["remaining_percent"] = 100 - used
            item["windows"][0]["reset_at_utc"] = reset
            item["checked_at_utc"] = checked
            observations.append(item)
        records = [
            {"type": "user", "message": {"role": "user", "content": "现在什么情况"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "id": f"usage-{i}",
                 "input": {"command": "uv run python scripts/query_usage.py"}} for i in range(4)
            ]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": f"usage-{i}", "content": json.dumps(obs)}
                for i, obs in enumerate(observations)
            ]}},
        ]
        result = evaluate_records(records, "观测到大范围静默重置。")
        self.assertEqual(result["claim_gate"][attr.CLAIM_MULTI_ACCOUNT], "allow")
        self.assertFalse(result["blocked"])

    def test_banked_reverse_order_confirmation(self):
        records = [
            {"type": "user", "message": {"role": "user",
                         "content": "我确认这个账号的 banked reset 已兑现。"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "id": "usage",
                 "input": {"command": "uv run python scripts/query_usage.py"}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "usage", "content": json.dumps(usage_payload())},
            ]}},
        ]
        result = evaluate_records(records, "该账户已经重置。")
        self.assertEqual(result["classification"], "banked_redeem")
        self.assertFalse(result["blocked"])

    def test_common_claim_variants_and_mixed_uncertainty_are_blocked(self):
        messages = [
            "当前账户已经重置。",
            "CLI 账号已在北京时间 21:10 左右重置。",
            "账号已经重置，原因与影响范围未核实。",
            "当前 CLI 账号已重置，但不能确认是否全员重置。",
        ]
        result = attr.evaluate(load_failure_bundle())
        for message in messages:
            with self.subTest(message=message):
                claims = attr.claims_in_message(message)
                self.assertIn(attr.CLAIM_SAME_ACCOUNT, [c["claim"] for c in claims])
                blocked = [c for c in claims if result["claim_gate"].get(c["claim"], "block") == "block"]
                self.assertTrue(blocked)

    def test_negated_reset_user_text_never_becomes_positive_evidence(self):
        for text in ("这个账号还没重置", "这个账号没重置", "这个账号尚未重置"):
            with self.subTest(text=text):
                events = attr.user_events(text, "a1b2c3d4", "2026-10-17T13:32:00Z")
                self.assertEqual(events, [])
                result = attr.evaluate(current_only_bundle(events))
                self.assertEqual(result["classification"], "unknown")
                self.assertEqual(result["claim_gate"]["same_account_reset"], "block")

    def test_official_rejects_upstream_parameters_and_limited_scope(self):
        records = [
            {"type": "user", "message": {"role": "user", "content": "现在什么情况"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "id": "usage", "input": {"command": "uv run python scripts/query_usage.py"}},
                {"type": "tool_use", "name": "WebFetch", "id": "post", "input": {
                    "url": "https://didcodexreset.com/api/status.json?upstream=https://x.com/thsottiaux/status/123"}},
            ]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "usage", "content": json.dumps(usage_payload())},
                {"type": "tool_result", "tool_use_id": "post",
                 "content": "We have now reset usage for all paid subscriptions"},
            ]}},
        ]
        result = evaluate_records(records, "官方确认全员重置。")
        self.assertEqual(result["classification"], "unknown")
        self.assertEqual(result["claim_gate"]["all_accounts"], "block")
        self.assertTrue(result["blocked"])
        self.assertEqual(attr.official_events(
            "The 5h reset has landed for Plus, not all accounts", "2026-10-17T13:32:00Z"), [])

    def test_broad_silent_reset_has_a_distinct_multi_account_gate(self):
        transitions = []
        events = []
        for ref, future in (("a1b2c3d4", "2026-10-20T12:00:00Z"),
                            ("b2c3d4e5", "2026-10-21T12:00:00Z")):
            transition = natural_bundle()["transitions"][0]
            transition["before"]["account_ref"] = ref
            transition["after"]["account_ref"] = ref
            transition["before"]["reset_at_utc"] = future
            transition["after"]["reset_at_utc"] = "2026-10-17T13:30:00Z"
            transitions.append(transition)
            events.append({"kind": "account_reset_observed", "account_ref": ref,
                           "checked_at_utc": "2026-10-17T12:50:00Z"})
        result = attr.evaluate({"transitions": transitions, "events": events})
        claims = attr.claims_in_message("观测到大范围静默重置。")
        self.assertEqual([c["claim"] for c in claims], [attr.CLAIM_MULTI_ACCOUNT])
        self.assertEqual(result["claim_gate"][attr.CLAIM_MULTI_ACCOUNT], "allow")
        self.assertEqual(result["claim_gate"][attr.CLAIM_ALL_ACCOUNTS], "block")
        single = attr.evaluate(load_failure_bundle())
        self.assertEqual(single["claim_gate"][attr.CLAIM_MULTI_ACCOUNT], "block")

    def test_idle_account_natural_rollover_does_not_require_usage_drop(self):
        bundle = natural_bundle()
        bundle["transitions"][0]["before"]["used_percent"] = 0
        result = attr.evaluate(bundle)
        self.assertEqual(result["classification"], "natural_cycle")
        self.assertEqual(result["claim_gate"]["same_account_reset"], "allow")

    def test_banked_selection_honors_event_interval(self):
        bundle = natural_bundle()
        bundle["transitions"][0]["after"]["reset_at_utc"] = "2026-10-24T13:30:00Z"
        bundle["events"] = [
            {"kind": "account_reset_observed", "account_ref": "a1b2c3d4",
             "interval_start_utc": "2026-10-17T12:30:00Z", "interval_end_utc": "2026-10-17T12:45:00Z"},
            {"kind": "banked_redeem", "account_ref": "a1b2c3d4",
             "interval_start_utc": "2026-10-01T00:00:00Z", "interval_end_utc": "2026-10-01T00:01:00Z"},
        ]
        result = attr.evaluate(bundle)
        self.assertEqual(result["classification"], "account_reset_observed")
        self.assertNotIn("banked_redeem", result["candidate_causes"])

    def test_usage_shaped_json_requires_an_actual_query_usage_call(self):
        before = usage_payload()
        before["used_percent"] = 80
        before["reset_at_utc"] = "2026-10-17T13:00:00Z"
        before["checked_at_utc"] = "2026-10-17T12:00:00Z"
        after = usage_payload()
        after["used_percent"] = 0
        after["reset_at_utc"] = "2026-10-24T13:00:00Z"
        after["checked_at_utc"] = "2026-10-17T13:01:00Z"
        records = [
            {"type": "user", "message": {"role": "user", "content": "现在什么情况"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "id": "usage",
                 "input": {"command": "cat unrelated-history.json"}},
            ]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "usage", "content": json.dumps(before)},
                {"type": "tool_result", "tool_use_id": "usage", "content": json.dumps(after)},
            ]}},
        ]
        with self.assertRaises(attr.AttributionError):
            evaluate_records(records, "该账户已经重置。")

    def test_user_banked_confirmation_is_direct_evidence(self):
        records = [
            {"type": "user", "timestamp": "2026-10-17T13:30:00Z",
             "message": {"role": "user",
                         "content": "我已经兑现了这个账号的备用 reset，额度回到 100%。"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "id": "usage",
                 "input": {"command": "uv run python scripts/query_usage.py"}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "usage", "content": json.dumps(usage_payload())},
            ]}},
        ]
        result = evaluate_records(records, "该账户已经重置。")
        self.assertEqual(result["classification"], "banked_redeem")
        self.assertEqual(result["claim_gate"]["same_account_reset"], "allow")
        self.assertFalse(result["blocked"])

    def test_questions_are_not_affirmative_claims(self):
        self.assertEqual(attr.claims_in_message("账号已经重置了吗？"), [])

    def test_official_transcript_requires_official_source_and_completion_wording(self):
        cases = [
            ("https://api.fxtwitter.com/thsottiaux/status/123",
             "We have now reset usage for all paid subscriptions", "official_global_reset", "allow"),
            ("https://didcodexreset.com/api/status.json",
             "We have now reset usage for all paid subscriptions", "unknown", "block"),
            ("https://api.fxtwitter.com/thsottiaux/status/123",
             "Global reset by EOD", "unknown", "block"),
        ]
        for target, post, classification, all_gate in cases:
            with self.subTest(target=target, post=post):
                records = [
                    {"type": "user", "message": {"role": "user", "content": "现在什么情况"}},
                    {"type": "assistant", "message": {"role": "assistant", "content": [
                        {"type": "tool_use", "name": "Bash", "id": "usage", "input": {"command": "uv run python scripts/query_usage.py"}},
                        {"type": "tool_use", "name": "WebFetch", "id": "post", "input": {"url": target}},
                    ]}},
                    {"type": "user", "message": {"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": "usage", "content": json.dumps(usage_payload())},
                        {"type": "tool_result", "tool_use_id": "post", "content": post},
                    ]}},
                ]
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "official.jsonl"
                    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                                    encoding="utf-8")
                    result = attr.evaluate_transcript(path)
                self.assertEqual(result["classification"], classification)
                self.assertEqual(result["claim_gate"]["all_accounts"], all_gate)

    def test_duplicate_weekly_windows_are_rejected(self):
        payload = usage_payload()
        payload["windows"].append(copy.deepcopy(payload["windows"][0]))
        with self.assertRaises(attr.AttributionError):
            attr.observation_from_usage(payload, "duplicate")

    def test_negated_corrective_meta_and_current_state_messages_are_not_claims(self):
        healthy = [
            "当前账号剩余 97%，Next reset 是 10 月 24 日；是否重置未核实。",
            "不能确认当前账号已重置。",
            "此前“该账号已重置”的结论已撤回。",
            "示例：当前 CLI 账号已重置。",
            "当前剩余 97%，备用 reset 有 3 次。",
        ]
        for message in healthy:
            with self.subTest(message=message):
                self.assertEqual(attr.claims_in_message(message), [])


if __name__ == "__main__":
    unittest.main()
