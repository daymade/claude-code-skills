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


def four_account_replay():
    """Synthetic identities preserve the 2026-10-26 failure's observed shape."""
    transitions = []
    for ref, before_used, after_used in (("replay-a", 2, 3), ("replay-b", 100, 0),
                                         ("replay-c", 0, 0), ("replay-d", 100, 0)):
        item = natural_bundle()["transitions"][0]
        item["before"].update(account_ref=ref, checked_at_utc="2026-10-26T04:43:19Z",
                              used_percent=before_used, reset_at_utc="2026-11-01T06:10:00Z")
        item["after"].update(account_ref=ref, checked_at_utc="2026-10-26T06:29:49Z",
                             used_percent=after_used, reset_at_utc="2026-11-02T06:08:00Z")
        transitions.append(item)
    return {"transitions": transitions, "events": []}


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
    def test_four_account_replay_keeps_aggregate_and_per_account_distinct(self):
        bundle = four_account_replay()
        result = attr.evaluate(bundle)
        self.assertEqual(result["classification"], "unknown")
        self.assertEqual(result["claim_gate"][attr.CLAIM_MULTI_ACCOUNT], "block")
        self.assertEqual(result["observations"]["cross_account_window_changes"], "observed")
        self.assertEqual(result["observations"]["cross_account_near_simultaneous_reset"], "unknown")
        self.assertEqual(result["claim_gate"][attr.CLAIM_ALL_ACCOUNTS], "block")
        for item in bundle["transitions"]:
            single = attr.evaluate({"transitions": [item], "events": []})
            self.assertEqual(single["claim_gate"][attr.CLAIM_SAME_ACCOUNT], "block")

    def test_near_simultaneous_requires_compatible_narrow_intervals(self):
        bundle = four_account_replay()
        bundle["timing_evidence"] = {"max_span_seconds": 7200, "source_ref": "synthetic-sampling-contract"}
        # The original asynchronous query rounds remain a healthy comparison.
        self.assertEqual(attr.evaluate(bundle)["claim_gate"][attr.CLAIM_CROSS_ACCOUNT], "allow")
        for variant in ("different_day", "wide_overlap", "reversed_time"):
            bad = copy.deepcopy(bundle)
            if variant == "different_day":
                for endpoint in ("before", "after"):
                    bad["transitions"][-1][endpoint]["checked_at_utc"] = (
                        "2026-10-27T04:43:19Z" if endpoint == "before" else "2026-10-27T06:29:49Z")
            elif variant == "wide_overlap":
                for item in bad["transitions"]:
                    item["before"]["checked_at_utc"] = "2026-10-01T00:00:00Z"
            else:
                for item in bad["transitions"]:
                    item["before"]["checked_at_utc"] = "2026-10-26T07:00:00Z"
            with self.subTest(variant=variant):
                result = attr.evaluate(bad)
                self.assertEqual(result["claim_gate"][attr.CLAIM_MULTI_ACCOUNT], "block")
                self.assertEqual(result["claim_gate"][attr.CLAIM_CROSS_ACCOUNT], "block")
                self.assertEqual(result["observations"]["cross_account_near_simultaneous_reset"], "unknown")

    def test_timing_evidence_missing_null_and_malformed_do_not_invent_resolution(self):
        bundle = four_account_replay()
        for value in (None,):
            bundle["timing_evidence"] = value
            result = attr.evaluate(bundle)
            self.assertEqual(result["claim_gate"][attr.CLAIM_MULTI_ACCOUNT], "block")
            self.assertEqual(result["observations"]["cross_account_window_changes"], "observed")
            self.assertIsNone(result["timing_evidence"])
        for value in ({}, {"max_span_seconds": 300}, {"source_ref": "source"},
                      {"max_span_seconds": None, "source_ref": "source"},
                      {"max_span_seconds": 300, "source_ref": ""},
                      {"max_span_seconds": 300, "source_ref": None},
                      {"max_span_seconds": 0, "source_ref": "source"},
                      {"max_span_seconds": True, "source_ref": "source"}, "300"):
            with self.subTest(value=value), self.assertRaises(attr.AttributionError):
                attr.evaluate({**bundle, "timing_evidence": value})

    def test_bounded_direct_events_can_narrow_wide_observation_intervals(self):
        bundle = four_account_replay()
        bundle["timing_evidence"] = {"max_span_seconds": 300, "source_ref": "synthetic-direct-event-intervals"}
        for item in bundle["transitions"]:
            item["before"]["checked_at_utc"] = "2026-10-01T00:00:00Z"
        for item in bundle["transitions"][1::2]:
            bundle["events"].append({"kind": "account_reset_observed",
                "account_ref": item["after"]["account_ref"],
                "interval_start_utc": "2026-10-26T06:08:00Z",
                "interval_end_utc": "2026-10-26T06:10:00Z"})
        self.assertEqual(attr.evaluate(bundle)["claim_gate"][attr.CLAIM_MULTI_ACCOUNT], "allow")
        # Query/confirmation timestamps cannot substitute for occurrence bounds.
        for event in bundle["events"]:
            event.pop("interval_start_utc")
            event.pop("interval_end_utc")
            event["checked_at_utc"] = "2026-10-26T06:10:00Z"
        self.assertEqual(attr.evaluate(bundle)["claim_gate"][attr.CLAIM_MULTI_ACCOUNT], "block")

    def test_independent_banked_redemptions_do_not_prove_platform_reset(self):
        bundle = four_account_replay()
        bundle["timing_evidence"] = {"max_span_seconds": 7200, "source_ref": "synthetic-sampling-contract"}
        bundle["transitions"] = bundle["transitions"][1::2]
        bundle["events"] = [{"kind": "banked_redeem", "account_ref": item["after"]["account_ref"],
                             "checked_at_utc": item["after"]["checked_at_utc"]}
                            for item in bundle["transitions"]]
        result = attr.evaluate(bundle)
        self.assertEqual(result["classification"], "banked_redeem")
        self.assertEqual(result["claim_gate"][attr.CLAIM_SAME_ACCOUNT], "allow")
        self.assertEqual(result["claim_gate"][attr.CLAIM_MULTI_ACCOUNT], "block")
        # An unrelated earlier redemption does not explain this interval.
        for event in bundle["events"]:
            event.update(interval_start_utc="2026-10-01T00:00:00Z",
                         interval_end_utc="2026-10-01T00:01:00Z")
        self.assertEqual(attr.evaluate(bundle)["claim_gate"][attr.CLAIM_MULTI_ACCOUNT], "allow")

    def test_selected_account_claims_do_not_inherit_the_last_account(self):
        bundle = four_account_replay()
        refs = [item["after"]["account_ref"] for item in bundle["transitions"]]
        bundle["selected_account_refs"] = refs
        bundle["events"] = [{"kind": "account_reset_observed", "account_ref": refs[-1],
                             "checked_at_utc": "2026-10-26T06:30:00Z"}]
        messages = ("四个账号都重置了。", "4个账号都重置了。", "我们所有账号都重置了。",
                    "这四个账号都重置了。", "我们全部账户已重置。")
        partial = attr.evaluate(bundle)
        self.assertEqual(partial["claim_gate"][attr.CLAIM_SAME_ACCOUNT], "allow")
        for message in messages:
            with self.subTest(message=message):
                claims = attr.claims_in_message(message)
                self.assertEqual([item["claim"] for item in claims], [attr.CLAIM_SELECTED_ACCOUNTS])
                self.assertFalse(attr.claim_allowed(partial, claims[0]))
        bundle["events"] = [{"kind": "account_reset_observed", "account_ref": ref,
                             "checked_at_utc": "2026-10-26T06:30:00Z"} for ref in refs]
        complete = attr.evaluate(bundle)
        for message in messages:
            self.assertTrue(attr.claim_allowed(complete, attr.claims_in_message(message)[0]))
        self.assertEqual(complete["claim_gate"][attr.CLAIM_ALL_ACCOUNTS], "block")
        self.assertFalse(attr.claim_allowed(complete, attr.claims_in_message("五个账号都重置了。")[0]))

    def test_selected_account_roster_missing_empty_duplicate_and_partial_fail_closed(self):
        bundle = four_account_replay()
        refs = [item["after"]["account_ref"] for item in bundle["transitions"]]
        bundle["events"] = [{"kind": "account_reset_observed", "account_ref": ref,
                             "checked_at_utc": "2026-10-26T06:30:00Z"} for ref in refs]
        for value in (None,):
            bundle["selected_account_refs"] = value
            self.assertEqual(attr.evaluate(bundle)["claim_gate"][attr.CLAIM_SELECTED_ACCOUNTS], "block")
        del bundle["selected_account_refs"]
        self.assertEqual(attr.evaluate(bundle)["claim_gate"][attr.CLAIM_SELECTED_ACCOUNTS], "block")
        for value in ([], [refs[0], refs[0]], [""], [None], "replay-a"):
            with self.subTest(value=value), self.assertRaises(attr.AttributionError):
                attr.evaluate({**bundle, "selected_account_refs": value})
        for variant in ("missing_account", "duplicate_observation", "anonymous", "missing_identity", "missing_after"):
            bad = copy.deepcopy(bundle)
            bad["selected_account_refs"] = refs
            if variant == "missing_account":
                bad["transitions"].pop(0)
            elif variant == "duplicate_observation":
                bad["transitions"].append(copy.deepcopy(bad["transitions"][0]))
            elif variant == "anonymous":
                bad["transitions"][0]["after"]["identity"] = "anonymous"
            elif variant == "missing_identity":
                del bad["transitions"][0]["after"]["identity"]
            else:
                del bad["transitions"][0]["after"]
            with self.subTest(variant=variant):
                if variant == "missing_after":
                    with self.assertRaises(attr.AttributionError):
                        attr.evaluate(bad)
                else:
                    self.assertEqual(attr.evaluate(bad)["claim_gate"][attr.CLAIM_SELECTED_ACCOUNTS], "block")
        for value in (None, ""):
            bad = copy.deepcopy(bundle)
            bad["selected_account_refs"] = refs
            bad["transitions"][0]["after"]["checked_at_utc"] = value
            with self.subTest(time=value), self.assertRaises(attr.AttributionError):
                attr.evaluate(bad)
        bad = copy.deepcopy(bundle)
        bad["selected_account_refs"] = refs
        del bad["transitions"][0]["after"]["checked_at_utc"]
        with self.assertRaises(attr.AttributionError):
            attr.evaluate(bad)

    def test_selected_scope_does_not_hide_a_separate_platform_claim(self):
        bundle = four_account_replay()
        refs = [item["after"]["account_ref"] for item in bundle["transitions"]]
        bundle["selected_account_refs"] = refs
        bundle["events"] = [{"kind": "account_reset_observed", "account_ref": ref,
                             "checked_at_utc": "2026-10-26T06:30:00Z"} for ref in refs]
        selected_only = attr.evaluate(bundle)
        mixed = ("我们四个账号都重置了并且平台所有账号也都重置了。",
                 "我们的四个账号和所有付费账号均已重置。")
        for message in mixed:
            with self.subTest(message=message):
                claims = attr.claims_in_message(message)
                self.assertEqual([item["claim"] for item in claims],
                                 [attr.CLAIM_SELECTED_ACCOUNTS, attr.CLAIM_ALL_ACCOUNTS])
                self.assertEqual([item["claim"] for item in claims
                                  if not attr.claim_allowed(selected_only, item)], [attr.CLAIM_ALL_ACCOUNTS])
        for message in ("我们所有账号都重置了。", "我们的四个账号都重置了。"):
            with self.subTest(message=message):
                claims = attr.claims_in_message(message)
                self.assertEqual([item["claim"] for item in claims], [attr.CLAIM_SELECTED_ACCOUNTS])
                self.assertTrue(all(attr.claim_allowed(selected_only, item) for item in claims))
        bundle["events"].append({"kind": "official_global_reset", "account_ref": None,
                                 "scope": "all_paid", "checked_at_utc": "2026-10-26T06:30:00Z"})
        both_scopes = attr.evaluate(bundle)
        for message in mixed:
            self.assertTrue(all(attr.claim_allowed(both_scopes, item)
                                for item in attr.claims_in_message(message)))

    def test_selected_scope_keeps_independent_current_account_and_each_count(self):
        refs = ["synthetic-a", "synthetic-b", "synthetic-c", "synthetic-d"]
        observations = [current_only_bundle([])["transitions"][0] for _ in range(5)]
        for ref, item in zip(refs + ["synthetic-e"], observations):
            item["after"]["account_ref"] = ref
        bundle = {"transitions": observations, "selected_account_refs": refs,
                  "events": [{"kind": "account_reset_observed", "account_ref": ref,
                              "source_ref": "synthetic-confirmation"} for ref in refs]}
        result = attr.evaluate(bundle)
        self.assertEqual(result["claim_gate"][attr.CLAIM_SELECTED_ACCOUNTS], "allow")
        self.assertEqual(result["claim_gate"][attr.CLAIM_SAME_ACCOUNT], "block")
        selected = attr.claims_in_message("这四个账号已重置。")
        self.assertTrue(all(attr.claim_allowed(result, item) for item in selected))
        current = attr.claims_in_message("当前账号已重置。")
        self.assertEqual([item["claim"] for item in current], [attr.CLAIM_SAME_ACCOUNT])
        self.assertFalse(attr.claim_allowed(result, current[0]))
        mixed = attr.claims_in_message("这四个账号已重置且当前账号已重置。")
        self.assertEqual([item["claim"] for item in mixed],
                         [attr.CLAIM_SELECTED_ACCOUNTS, attr.CLAIM_SAME_ACCOUNT])
        self.assertEqual([item["claim"] for item in mixed if not attr.claim_allowed(result, item)],
                         [attr.CLAIM_SAME_ACCOUNT])
        counts = attr.claims_in_message("四个账号已重置且五个账号已重置。")
        self.assertEqual([item["account_count"] for item in counts], [4, 5])
        self.assertEqual([item["account_count"] for item in counts if not attr.claim_allowed(result, item)], [5])
        # Repeated valid quantities remain valid, and independent current proof
        # can satisfy its own clause without changing the selected roster.
        repeated = attr.claims_in_message("四个账号已重置且这4个账号已重置。")
        self.assertTrue(all(attr.claim_allowed(result, item) for item in repeated))
        bundle["events"].append({"kind": "account_reset_observed", "account_ref": "synthetic-e",
                                 "source_ref": "synthetic-confirmation-e"})
        complete = attr.evaluate(bundle)
        self.assertTrue(all(attr.claim_allowed(complete, item) for item in mixed))

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
        timing = {"max_span_seconds": 7200, "source_ref": "synthetic-sampling-contract"}
        result = attr.evaluate({"transitions": transitions, "events": [], "timing_evidence": timing})
        self.assertEqual(result["claim_gate"][attr.CLAIM_MULTI_ACCOUNT], "allow")
        self.assertEqual(result["claim_gate"][attr.CLAIM_CROSS_ACCOUNT], "allow")

        natural_two = []
        for ref in ("a1b2c3d4", "b2c3d4e5"):
            transition = natural_bundle()["transitions"][0]
            transition["before"]["account_ref"] = ref
            transition["after"]["account_ref"] = ref
            natural_two.append(transition)
        weaker = attr.evaluate({"transitions": natural_two, "events": [], "timing_evidence": timing})
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
        self.assertEqual(result["claim_gate"][attr.CLAIM_MULTI_ACCOUNT], "block")
        self.assertEqual(result["observations"]["cross_account_window_changes"], "observed")
        self.assertTrue(result["blocked"])

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
        result = attr.evaluate({"transitions": transitions, "events": events,
                               "timing_evidence": {"max_span_seconds": 7200,
                                                   "source_ref": "synthetic-sampling-contract"}})
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
