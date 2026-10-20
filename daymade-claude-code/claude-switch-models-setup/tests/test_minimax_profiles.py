"""MiniMax profile regressions; opt-in wire tests use Claude against localhost only.

CSMS_RUN_CLAUDE_WIRE_TESTS=1 python3 -m unittest discover -s tests -p test_minimax_profiles.py -v
Requires Claude Code 2.1.204 or newer for the opt-in tests; no API credentials needed.
"""
from __future__ import annotations

import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

SKILL = Path(__file__).resolve().parents[1]
TEMPLATES = SKILL / "assets/templates"
MODEL_KEYS = (
    "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_MODEL",
    "ANTHROPIC_REASONING_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL",
)
ACTIVE = {
    "minimax": ("MiniMax-M3.1-Flash", "https://api.minimax.io/anthropic"),
    "minimax-cn": ("MiniMax-M3.1-Flash", "https://api.minimaxi.com/anthropic"),
    "minimax-m3": ("MiniMax-M3", "https://api.minimax.io/anthropic"),
    "minimax-m3-cn": ("MiniMax-M3", "https://api.minimaxi.com/anthropic"),
}


class MiniMaxTemplateTests(unittest.TestCase):
    def test_active_catalog_and_aliases(self):
        self.assertEqual({p.stem for p in TEMPLATES.glob("minimax*.json")}, set(ACTIVE))
        for profile, (model, endpoint) in ACTIVE.items():
            with self.subTest(profile=profile):
                settings = json.loads((TEMPLATES / f"{profile}.json").read_text())
                env = settings["env"]
                self.assertEqual(env["ANTHROPIC_BASE_URL"], endpoint)
                self.assertEqual({env[key] for key in MODEL_KEYS}, {model + "[1m]"})
                self.assertEqual(env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"], "1000000")
                if model == "MiniMax-M3.1-Flash":
                    self.assertTrue(settings["alwaysThinkingEnabled"])
                    self.assertEqual(env["CLAUDE_CODE_EFFORT_LEVEL"], "max")
                else:
                    self.assertNotIn("CLAUDE_CODE_EFFORT_LEVEL", env)

    def test_explicit_legacy_templates_remain_available(self):
        for suffix in ("", "-cn"):
            env = json.loads((TEMPLATES / "legacy" / f"minimax-m2-7{suffix}.json").read_text())["env"]
            self.assertEqual({env[key] for key in MODEL_KEYS}, {"MiniMax-M2.7"})
            self.assertEqual(env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"], "204800")
            self.assertNotIn("CLAUDE_CODE_EFFORT_LEVEL", env)


@unittest.skipUnless(os.environ.get("CSMS_RUN_CLAUDE_WIRE_TESTS") == "1", "opt-in: requires local Claude Code")
class MiniMaxWireTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(shutil.which("claude"), "Install Claude Code before enabling wire tests")
        self.temp = tempfile.TemporaryDirectory(prefix="minimax-wire-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        policy_dir = self.home / ".config/claude-switch-models-setup"
        policy_dir.mkdir(parents=True)
        shutil.copyfile(TEMPLATES / "codex-active-skills.json", policy_dir / "codex-active-skills.json")
        self.requests = []
        requests = self.requests

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.path, body))
                # A non-streaming response also exercises Claude's stream fallback.
                reply = json.dumps({
                    "id": "msg_test", "type": "message", "role": "assistant", "model": body["model"],
                    "content": [{"type": "text", "text": "OK"}], "stop_reason": "end_turn",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        # Explicit allowlist: do not inherit real provider credentials, proxies, or config.
        self.env = {
            "PATH": os.environ["PATH"], "HOME": str(self.home), "LANG": "C.UTF-8",
            "CLAUDE_PROFILES_CONFIG_DIR": str(SKILL / "scripts"),
            "CLAUDE_PROFILES_AUTO_SYNC": "0", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "NO_PROXY": "127.0.0.1,localhost",
        }

    def stop_server(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def launch(self, profile, *, model=None, effort=None, thinking=None, image=False):
        settings = json.loads((TEMPLATES / f"{profile}.json").read_text())
        if model:
            for key in MODEL_KEYS:
                settings["env"][key] = model
        if effort:
            settings["env"]["CLAUDE_CODE_EFFORT_LEVEL"] = effort
        if thinking is not None:
            settings["alwaysThinkingEnabled"] = thinking
        settings["env"].update({
            "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{self.server.server_port}/anthropic",
            "ANTHROPIC_AUTH_TOKEN": "dummy-local-test", "ANTHROPIC_API_KEY": "dummy-local-test",
        })
        config = self.home / ".claude-profiles" / "selected"
        config.mkdir(parents=True, exist_ok=True)
        settings_dir = self.home / ".claude" / "settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_path = settings_dir / "selected.json"
        original = json.dumps(settings)
        settings_path.write_text(original)
        content = [{"type": "text", "text": "Say OK."}]
        if image:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6k0cAAAAASUVORK5CYII="}})
        payload = json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + "\n"
        self.requests.clear()
        result = subprocess.run([
            "bash", "-c", 'source "$1"; shift; claude-profile selected "$@"', "test",
            str(SKILL / "scripts/claude-profiles.sh"), "--bare", "-p", "--input-format", "stream-json",
            "--tools", "", "--disable-slash-commands", "--setting-sources", "",
            "--strict-mcp-config", "--output-format", "stream-json", "--verbose", "--no-session-persistence",
        ], input=payload, cwd=self.home, env=self.env, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(settings_path.read_text(), original, "launch must not rewrite saved selections")
        self.assertTrue(self.requests, "Claude must reach the local HTTP boundary")
        output = json.loads(result.stdout.splitlines()[-1])
        self.assertFalse(output["is_error"])
        self.assertEqual(output["result"], "OK")
        return [body for path, body in self.requests if path.startswith("/anthropic/v1/messages")], output

    def test_active_profiles_reach_request_boundary(self):
        for profile, (model, _) in ACTIVE.items():
            with self.subTest(profile=profile):
                bodies, output = self.launch(profile)
                self.assertTrue(bodies)
                self.assertEqual(output["modelUsage"][model + "[1m]"]["contextWindow"], 1000000)
                for body in bodies:
                    self.assertEqual(body["model"], model)
                    if model == "MiniMax-M3.1-Flash":
                        self.assertEqual(body["thinking"]["type"], "adaptive")
                        self.assertEqual(body["output_config"]["effort"], "max")
                        self.assertNotIn("budget_tokens", body["thinking"])

    def test_all_flash_effort_levels_reach_request_boundary(self):
        for effort in ("low", "medium", "high", "xhigh", "max"):
            with self.subTest(effort=effort):
                bodies, _ = self.launch("minimax", effort=effort)
                for body in bodies:
                    self.assertEqual(body["output_config"]["effort"], effort)
                    self.assertEqual(body["thinking"]["type"], "adaptive")

    def test_explicit_m3_non_thinking_and_saved_custom_models(self):
        bodies, _ = self.launch("minimax-m3", thinking=False)
        for body in bodies:
            self.assertEqual(body["model"], "MiniMax-M3")
            self.assertIn(body.get("thinking", {}).get("type"), (None, "disabled"))
        for model in ("MiniMax-M2.7", "my-private-text-model"):
            with self.subTest(model=model):
                bodies, _ = self.launch("minimax-m3", model=model)
                self.assertTrue(bodies)
                self.assertEqual({body["model"] for body in bodies}, {model})

    def test_flash_preserves_image_input(self):
        bodies, _ = self.launch("minimax", image=True)
        self.assertTrue(bodies)
        for body in bodies:
            images = [block for message in body["messages"] for block in message["content"] if block["type"] == "image"]
            self.assertEqual(len(images), 1)
            self.assertEqual(images[0]["source"]["media_type"], "image/png")


if __name__ == "__main__":
    unittest.main()
