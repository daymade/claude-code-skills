"""Calibration tests for diagnose.py's verdict logic.

This script exists to tell somebody whether a web tool is dead, and people act on
what it says. So the thing that needs testing is not that it runs — it is that it
says *unavailable* only when it saw evidence of unavailability, and never when it
merely saw silence.

Both directions are covered on purpose. A checker that only ever proves "it catches
the bad case" is half an instrument: the expensive failure here is calling a healthy
endpoint broken, because that is the same misdiagnosis the skill exists to correct.

Standard library only, no network: `post` is replaced with a canned reply, so every
case is a fixture whose right answer is known before the test runs.
"""

import importlib.util
import io
import json
import os
import pathlib
import re
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr

_HERE = pathlib.Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "diagnose", _HERE.parent / "scripts" / "diagnose.py"
)
diagnose = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(diagnose)


class FakePost:
    """Stands in for diagnose.post, returning one canned (status, body) per call."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, url, payload, headers, timeout):
        self.calls.append({"url": url, "payload": payload, "headers": headers})
        return self.replies.pop(0) if self.replies else (200, {})


def _with_post(fake):
    original = diagnose.post
    diagnose.post = fake
    return original


class AnthropicVerdicts(unittest.TestCase):
    """One reply shape in, one verdict out."""

    def setUp(self):
        self.original = diagnose.post

    def tearDown(self):
        diagnose.post = self.original

    def _probe(self, status, body, tool="web_search"):
        diagnose.post = FakePost((status, body))
        return diagnose.probe("https://relay.example", "k", "m", tool, 5)

    def test_server_tool_use_is_working(self):
        r = self._probe(200, {"content": [{"type": "server_tool_use", "id": "srvtoolu_1"},
                                          {"type": "text"}]})
        self.assertEqual(r["verdict"], diagnose.VERDICT_WORKS)

    def test_tool_result_block_is_working(self):
        """Defensive, not observed: every working reply seen so far carried
        server_tool_use, but the result block on its own is just as much proof that
        the tool ran, and accepting it costs nothing."""
        r = self._probe(200, {"content": [{"type": "web_search_tool_result"}]})
        self.assertEqual(r["verdict"], diagnose.VERDICT_WORKS)

    def test_plain_tool_use_is_unavailable(self):
        """Handed back for a client to run means it never executed."""
        r = self._probe(200, {"content": [{"type": "tool_use", "id": "toolu_bdrk_9"}]})
        self.assertEqual(r["verdict"], diagnose.VERDICT_BROKEN)

    def test_http_400_is_unavailable(self):
        r = self._probe(400, {"error": {"message": "Invalid schema for function 'web_search'"}})
        self.assertEqual(r["verdict"], diagnose.VERDICT_BROKEN)
        self.assertIn("web_search", r["detail"])

    def test_text_only_reply_is_inconclusive_not_broken(self):
        """The false-positive guard. A model that did not reach for the tool proves
        nothing about the endpoint, and calling that 'broken' is the misdiagnosis
        this whole skill exists to prevent."""
        r = self._probe(200, {"content": [{"type": "text", "text": "I think so."}]})
        self.assertEqual(r["verdict"], diagnose.VERDICT_UNKNOWN)

    def test_empty_content_is_inconclusive_not_broken(self):
        r = self._probe(200, {"content": []})
        self.assertEqual(r["verdict"], diagnose.VERDICT_UNKNOWN)

    def test_timeout_is_inconclusive_and_says_so(self):
        """Slow and dead look identical from one request; only one of them is a verdict."""
        diagnose.post = FakePost((None, {"_timeout": 180}))
        r = diagnose.probe("https://relay.example", "k", "m", "web_search", 180)
        self.assertEqual(r["verdict"], diagnose.VERDICT_UNKNOWN)
        self.assertIn("slowness, not a verdict", r["detail"])

    def test_transport_failure_is_inconclusive(self):
        diagnose.post = FakePost((None, {"_transport_error": "name resolution failed"}))
        r = diagnose.probe("https://relay.example", "k", "m", "web_search", 5)
        self.assertEqual(r["verdict"], diagnose.VERDICT_UNKNOWN)

    def test_backend_named_from_tool_id_prefix(self):
        r = self._probe(200, {"content": [{"type": "tool_use", "id": "toolu_vrtx_abc"}]})
        self.assertIn("Vertex AI", r["backend"])
        r = self._probe(200, {"content": [{"type": "tool_use", "id": "toolu_bdrk_abc"}]})
        self.assertIn("Bedrock", r["backend"])

    def test_unknown_prefix_leaves_backend_unnamed(self):
        """Do not guess a cloud from an id shape nobody has seen."""
        r = self._probe(200, {"content": [{"type": "tool_use", "id": "toolu_zzz_abc"}]})
        self.assertIsNone(r["backend"])

    def test_web_fetch_probe_supplies_a_url(self):
        """web_fetch refuses URLs absent from the conversation, so a probe without
        one fails for a reason that has nothing to do with the endpoint."""
        fake = FakePost((200, {"content": []}))
        diagnose.post = fake
        diagnose.probe("https://relay.example", "k", "m", "web_fetch", 5)
        sent = fake.calls[0]["payload"]["messages"][0]["content"]
        self.assertIn("https://example.com", sent)


class OpenAIVerdicts(unittest.TestCase):
    """The Responses API path, which is how Codex reaches its backend."""

    def setUp(self):
        self.original = diagnose.post

    def tearDown(self):
        diagnose.post = self.original

    def _probe(self, status, body):
        diagnose.post = FakePost((status, body))
        return diagnose.probe_openai("https://relay.example", "k", "m", 5)

    def test_web_search_call_is_working(self):
        r = self._probe(200, {"output": [
            {"type": "web_search_call", "id": "ws_1", "status": "completed"},
            {"type": "message"},
        ]})
        self.assertEqual(r["verdict"], diagnose.VERDICT_WORKS)
        self.assertIn("OpenAI", r["backend"])

    def test_message_only_is_inconclusive_not_broken(self):
        """A compatibility layer that drops built-in tools and a model that chose
        not to search produce the same reply. One reply cannot separate them."""
        r = self._probe(200, {"output": [{"type": "message", "id": "msg_1"}]})
        self.assertEqual(r["verdict"], diagnose.VERDICT_UNKNOWN)

    def test_http_400_is_unavailable(self):
        r = self._probe(400, {"error": {"message": "Invalid schema for function 'web_search'"}})
        self.assertEqual(r["verdict"], diagnose.VERDICT_BROKEN)

    def test_missing_responses_route_on_a_live_openai_relay_is_unavailable(self):
        """Measured shape: a relay answers the older Chat Completions route but has
        no /v1/responses. Hosted search is served through the Responses API, so it
        cannot run there — that is a verdict, not a shrug."""
        diagnose.post = FakePost(
            (404, {"message": "not found or method not allowed"}),
            (200, {"choices": [{"message": {"content": "hi"}}]}),
        )
        r = diagnose.probe_openai("https://relay.example", "k", "m", 5)
        self.assertEqual(r["verdict"], diagnose.VERDICT_BROKEN)
        self.assertEqual(r["chat_completions_http"], 200)
        self.assertIn("Codex", r["detail"])

    def test_missing_both_routes_stays_inconclusive(self):
        """If neither route answers, the endpoint may speak no OpenAI dialect at all
        or the key may be wrong. Neither is a statement about the tool."""
        diagnose.post = FakePost(
            (404, {"message": "not found"}),
            (401, {"error": {"message": "invalid api key"}}),
        )
        r = diagnose.probe_openai("https://relay.example", "k", "m", 5)
        self.assertEqual(r["verdict"], diagnose.VERDICT_UNKNOWN)
        self.assertIn("key", r["detail"])

    def test_the_follow_up_probe_targets_chat_completions(self):
        fake = FakePost((404, {"message": "not found"}), (200, {"choices": []}))
        diagnose.post = fake
        diagnose.probe_openai("https://relay.example", "k", "m", 5)
        self.assertEqual([c["url"] for c in fake.calls], [
            "https://relay.example/v1/responses",
            "https://relay.example/v1/chat/completions",
        ])

    def test_posts_to_the_responses_route_with_a_bearer_token(self):
        fake = FakePost((200, {"output": []}))
        diagnose.post = fake
        diagnose.probe_openai("https://relay.example", "secret", "gpt-x", 5)
        call = fake.calls[0]
        self.assertEqual(call["url"], "https://relay.example/v1/responses")
        self.assertEqual(call["headers"]["authorization"], "Bearer secret")
        self.assertEqual(call["payload"]["tools"], [{"type": "web_search"}])
        self.assertIsInstance(call["payload"]["input"], str)


class ExitCodes(unittest.TestCase):
    """The exit code is the part a caller branches on, so it gets its own cases."""

    def setUp(self):
        self.original = diagnose.post

    def tearDown(self):
        diagnose.post = self.original

    def _run(self, *argv, replies=()):
        if replies:
            diagnose.post = FakePost(*replies)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = diagnose.main(list(argv))
        return code, out.getvalue() + err.getvalue()

    def test_broken_exits_1(self):
        code, text = self._run(
            "--url", "https://relay.example", "--key", "k", "--model", "m",
            "--tool", "web_search",
            replies=[(200, {"content": [{"type": "tool_use", "id": "toolu_bdrk_1"}]})],
        )
        self.assertEqual(code, 1)
        self.assertIn("unavailable", text.lower())

    def test_working_exits_0(self):
        code, _ = self._run(
            "--url", "https://relay.example", "--key", "k", "--model", "m",
            "--tool", "web_search",
            replies=[(200, {"content": [{"type": "server_tool_use", "id": "srvtoolu_1"}]})],
        )
        self.assertEqual(code, 0)

    def test_inconclusive_exits_2(self):
        code, _ = self._run(
            "--url", "https://relay.example", "--key", "k", "--model", "m",
            "--tool", "web_search",
            replies=[(200, {"content": [{"type": "text"}]})],
        )
        self.assertEqual(code, 2)

    def test_missing_key_exits_2(self):
        code, text = self._run("--url", "https://relay.example", "--key", "")
        self.assertEqual(code, 2)
        self.assertIn("no key", text.lower())

    def test_anthropic_direct_is_not_affected(self):
        code, text = self._run("--url", "https://api.anthropic.com", "--key", "k")
        self.assertEqual(code, 0)
        self.assertIn("directly", text)

    def test_openai_direct_is_not_affected(self):
        """The vendor check has to follow --api, or an OpenAI user probing the real
        OpenAI endpoint gets told it is a relay."""
        code, text = self._run("--api", "openai", "--url", "https://api.openai.com", "--key", "k")
        self.assertEqual(code, 0)
        self.assertIn("OpenAI", text)

    def test_openai_endpoint_is_not_excused_by_the_anthropic_host_check(self):
        code, _ = self._run(
            "--api", "openai", "--url", "https://relay.example", "--key", "k", "--model", "m",
            replies=[(400, {"error": {"message": "Invalid schema for function 'web_search'"}})],
        )
        self.assertEqual(code, 1)

    def test_context_marker_is_stripped_from_the_model_id(self):
        """A client-side hint such as "[1m]" is not part of any model id the API knows."""
        fake = FakePost((200, {"content": []}))
        diagnose.post = fake
        self._run("--url", "https://relay.example", "--key", "k",
                  "--model", "claude-opus-5[1m]", "--tool", "web_search")
        self.assertEqual(fake.calls[0]["payload"]["model"], "claude-opus-5")

    def test_json_output_parses_as_one_document(self):
        code, text = self._run(
            "--json", "--url", "https://relay.example", "--key", "k", "--model", "m",
            "--tool", "web_search",
            replies=[(200, {"content": [{"type": "tool_use", "id": "toolu_bdrk_1"}]})],
        )
        self.assertEqual(code, 1)
        parsed = json.loads(text)
        self.assertEqual(parsed["conclusion"], "affected")

    def test_both_probes_run_when_api_is_both(self):
        """--openai-model is passed explicitly because the two APIs do not share a
        model namespace; the skip path when it is absent is covered separately."""
        fake = FakePost(
            (200, {"content": [{"type": "tool_use", "id": "toolu_bdrk_1"}]}),
            (200, {"content": [{"type": "tool_use", "id": "toolu_bdrk_2"}]}),
            (200, {"output": [{"type": "message"}]}),
        )
        diagnose.post = fake
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            diagnose.main(["--api", "both", "--url", "https://relay.example",
                           "--key", "k", "--model", "m", "--openai-model", "gpt-5"])
        routes = [c["url"] for c in fake.calls]
        self.assertEqual(routes.count("https://relay.example/v1/messages"), 2)
        self.assertEqual(routes.count("https://relay.example/v1/responses"), 1)


class FourHundredIsNotAlwaysAboutTheTool(unittest.TestCase):
    """The expensive direction. A relay answers 400 for an unknown model id, a
    malformed body or a policy rule; reading any of those as "the tool is dead"
    makes the caller delete a tool that works."""

    def setUp(self):
        self.original = diagnose.post

    def tearDown(self):
        diagnose.post = self.original

    def _anthropic(self, message):
        diagnose.post = FakePost((400, {"error": {"message": message}}))
        return diagnose.probe("https://relay.example", "k", "m", "web_search", 5)

    def _openai(self, message):
        diagnose.post = FakePost((400, {"error": {"message": message}}))
        return diagnose.probe_openai("https://relay.example", "k", "m", 5)

    def test_message_naming_the_tool_is_unavailable(self):
        r = self._anthropic("Invalid schema for function 'web_search'")
        self.assertEqual(r["verdict"], diagnose.VERDICT_BROKEN)

    def test_message_about_the_model_is_inconclusive(self):
        r = self._anthropic("model 'claude-haiku-4-5' does not exist")
        self.assertEqual(r["verdict"], diagnose.VERDICT_UNKNOWN)
        self.assertIn("--model", r["detail"])

    def test_message_about_credits_is_inconclusive(self):
        r = self._anthropic("Insufficient balance for this account")
        self.assertEqual(r["verdict"], diagnose.VERDICT_UNKNOWN)

    def test_openai_message_about_the_model_is_inconclusive(self):
        r = self._openai("The model `gpt-x` does not exist or you do not have access")
        self.assertEqual(r["verdict"], diagnose.VERDICT_UNKNOWN)
        self.assertIn("--openai-model", r["detail"])

    def test_openai_message_naming_the_tool_is_unavailable(self):
        r = self._openai("Invalid schema for function 'web_search'")
        self.assertEqual(r["verdict"], diagnose.VERDICT_BROKEN)

    def test_the_endpoint_message_is_always_kept(self):
        """Whatever the verdict, the reader needs the original text."""
        for message in ("Invalid schema for function 'web_search'", "model not found"):
            self.assertIn(message.split()[0], self._anthropic(message)["detail"])


class ModelNamespaces(unittest.TestCase):
    """The two APIs do not share a model namespace, and guessing across them
    produces a 400 about the model that reads like a verdict about the tool."""

    def setUp(self):
        self.original = diagnose.post
        self.saved_env = {k: os.environ.pop(k, None) for k in ("OPENAI_MODEL",)}

    def tearDown(self):
        diagnose.post = self.original
        for k, v in self.saved_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

    def _run(self, argv, replies):
        fake = FakePost(*replies)
        diagnose.post = fake
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = diagnose.main(argv)
        return code, fake

    def test_both_without_an_openai_model_does_not_send_the_anthropic_id(self):
        code, fake = self._run(
            ["--api", "both", "--url", "https://relay.example", "--key", "k",
             "--model", "claude-haiku-4-5"],
            [(200, {"content": [{"type": "text"}]}),
             (200, {"content": [{"type": "text"}]})],
        )
        routes = [c["url"] for c in fake.calls]
        self.assertNotIn("https://relay.example/v1/responses", routes)
        self.assertEqual(code, 2)

    def test_both_with_an_openai_model_sends_each_id_to_its_own_route(self):
        code, fake = self._run(
            ["--api", "both", "--url", "https://relay.example", "--key", "k",
             "--model", "claude-haiku-4-5", "--openai-model", "gpt-5"],
            [(200, {"content": [{"type": "text"}]}),
             (200, {"content": [{"type": "text"}]}),
             (200, {"output": [{"type": "message"}]})],
        )
        by_route = {c["url"]: c["payload"]["model"] for c in fake.calls}
        self.assertEqual(by_route["https://relay.example/v1/messages"], "claude-haiku-4-5")
        self.assertEqual(by_route["https://relay.example/v1/responses"], "gpt-5")

    def test_openai_model_env_var_is_honoured_by_both(self):
        os.environ["OPENAI_MODEL"] = "gpt-from-env"
        _, fake = self._run(
            ["--api", "both", "--url", "https://relay.example", "--key", "k",
             "--model", "m"],
            [(200, {"content": [{"type": "text"}]}),
             (200, {"content": [{"type": "text"}]}),
             (200, {"output": [{"type": "message"}]})],
        )
        sent = {c["url"]: c["payload"]["model"] for c in fake.calls}
        self.assertEqual(sent["https://relay.example/v1/responses"], "gpt-from-env")


class ClientFacingNames(unittest.TestCase):
    """A deny list takes `WebSearch`; the API takes `web_search`. Reporting only
    the API spelling makes the caller write a string that matches nothing."""

    def setUp(self):
        self.original = diagnose.post

    def tearDown(self):
        diagnose.post = self.original

    def test_every_result_carries_the_client_spelling(self):
        diagnose.post = FakePost((200, {"content": [{"type": "tool_use", "id": "toolu_bdrk_1"}]}))
        r = diagnose.probe("https://relay.example", "k", "m", "web_search", 5)
        self.assertEqual(r["client_tool"], "WebSearch")

        diagnose.post = FakePost((200, {"content": [{"type": "tool_use", "id": "toolu_bdrk_1"}]}))
        r = diagnose.probe("https://relay.example", "k", "m", "web_fetch", 5)
        self.assertEqual(r["client_tool"], "WebFetch")

    def test_the_human_conclusion_names_the_spelling_the_client_accepts(self):
        diagnose.post = FakePost((200, {"content": [{"type": "tool_use", "id": "toolu_bdrk_1"}]}))
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            diagnose.main(["--url", "https://relay.example", "--key", "k", "--model", "m",
                           "--tool", "web_search"])
        text = out.getvalue()
        self.assertIn("WebSearch", text)
        self.assertIn("permissions.deny", text)


class MissingKeyGuidance(unittest.TestCase):
    """The hint has to name the variable that matters for the chosen API, and say
    where the value actually lives on a relay."""

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = diagnose.main(argv)
        return code, out.getvalue() + err.getvalue()

    def test_openai_mode_names_the_openai_variable(self):
        saved = {k: os.environ.pop(k, None)
                 for k in ("OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")}
        try:
            code, text = self._run(["--api", "openai", "--url", "https://relay.example",
                                    "--key", ""])
            self.assertEqual(code, 2)
            self.assertIn("OPENAI_API_KEY", text)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_the_hint_says_where_the_value_lives(self):
        saved = {k: os.environ.pop(k, None)
                 for k in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")}
        try:
            _, text = self._run(["--url", "https://relay.example", "--key", ""])
            self.assertIn("settings.json", text)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


class TheDocumentedProcedureStaysRunnable(unittest.TestCase):
    """Guards the two instructions a reader copies verbatim.

    These are prose, not code, which is exactly why they need a mechanical check:
    the first published version of this skill told the reader to register the
    server at ``--scope project`` and then add the grant to ``permissions.allow``.
    Both lines were individually true. Together they produce a setup where the
    client silently drops the grant and the model answers that it is waiting for
    permission -- indistinguishable, from the user's chair, from the broken search
    the procedure exists to fix. Nothing in the test suite could fail on that,
    because nothing in the test suite read the documents.

    The assertions are deliberately narrow. They pin the two strings that were
    wrong; they do not police wording, so ordinary editing cannot trip them.
    """

    SKILL = _HERE.parent / "SKILL.md"
    BACKENDS = _HERE.parent / "references" / "backends.md"

    @staticmethod
    def _install_commands(text):
        """Every `claude mcp add ...` a reader could copy, one per match."""
        return re.findall(r"claude mcp add[^\n`]*", text)

    def test_the_fixtures_are_where_the_test_thinks_they_are(self):
        # Calibration: if these files move, the checks below would pass by
        # reading nothing at all. Fail loudly instead.
        for path in (self.SKILL, self.BACKENDS):
            self.assertTrue(path.is_file(), f"{path} missing")
            self.assertGreater(len(path.read_text(encoding="utf-8")), 2000)

    def test_the_install_command_is_calibrated_against_a_known_positive(self):
        # Prove the extractor finds a command at all before trusting it to
        # report that none is malformed.
        found = self._install_commands(self.BACKENDS.read_text(encoding="utf-8"))
        self.assertTrue(found, "extractor found no install command -- it is broken")
        self.assertTrue(any("--scope" in c for c in found))

    def test_no_documented_install_registers_into_a_project(self):
        for path in (self.SKILL, self.BACKENDS):
            for command in self._install_commands(path.read_text(encoding="utf-8")):
                self.assertNotIn(
                    "--scope project", command,
                    f"{path.name} tells the reader to register at project scope; "
                    "the grant that follows is then dropped in any untrusted "
                    "workspace and the procedure ends in a permission refusal",
                )

    def test_both_documents_send_the_grant_to_the_user_settings_file(self):
        for path in (self.SKILL, self.BACKENDS):
            text = path.read_text(encoding="utf-8")
            self.assertIn("permissions.allow", text)
            self.assertIn(
                "~/.claude/settings.json", text,
                f"{path.name} mentions the grant without naming the file the "
                "client actually reads it from",
            )

    def test_the_stderr_only_warning_is_quoted_so_a_reader_can_search_for_it(self):
        # The client reports this on stderr and nowhere else; an agent reading
        # --output-format json sees the denial with no reason attached. The exact
        # string is the only thing that makes it findable.
        #
        # Collapse whitespace first. Prose wraps, and the first version of this
        # check searched the raw text for a phrase the document had split across
        # two lines -- a red that said "the warning is missing" about a file that
        # quotes it in full. An instrument that fails that way on healthy input is
        # the one that gets switched off.
        for path in (self.SKILL, self.BACKENDS):
            flat = " ".join(path.read_text(encoding="utf-8").split())
            self.assertTrue(
                "this workspace has not been trusted" in flat,
                f"{path.name} drops the one line that explains the refusal",
            )

    def test_that_warning_check_can_still_go_red(self):
        # Calibration for the check above: the same predicate, run against text
        # that genuinely lacks the line, must fail. Otherwise a whitespace-
        # collapsing search that matched everything would look identical.
        flat = " ".join("permissions.allow goes in the settings file".split())
        self.assertFalse("this workspace has not been trusted" in flat)


if __name__ == "__main__":
    unittest.main()
