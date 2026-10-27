"""Execute the published Code Mode recipe verbatim with known command receipts."""

import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CodexReadRecipeTests(unittest.TestCase):
    def test_verbatim_recipe_emits_body_only_after_terminal_success(self):
        text = (ROOT / "references/stateful-script-verification.md").read_text()
        section = text.split("### Codex Code Mode receipt\n", 1)[1]
        recipe = section.split("```javascript\n", 1)[1].split("```", 1)[0]
        body = "Line one\n非 ASCII 正文\n"
        receipts = [
            {"exit_code": 0, "output": body},
            {"exit_code": 1, "output": body},
            {"exit_code": "0", "output": body},
            {"output": body},
            {"exit_code": 0},
            {"exit_code": 0, "output": None},
            {"exit_code": 0, "output": body, "session_id": 123},
            {"exit_code": 0, "output": body, "session_id": None},
            None,
        ]
        harness = r"""
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
(async () => {
  const rows = [];
  for (const receipt of input.receipts) {
    const outputs = []; let calls = 0;
    const tools = {exec_command: async () => { calls++; return receipt; }};
    const stop = Symbol('exit');
    try {
      await new AsyncFunction('tools', 'text', 'exit', input.recipe)(tools,
        value => outputs.push(value), () => { throw stop; });
    } catch (error) { if (error !== stop) throw error; }
    rows.push({calls, strings: outputs.filter(value => typeof value === 'string')});
  }
  process.stdout.write(JSON.stringify(rows));
})().catch(error => { process.stderr.write(String(error)); process.exitCode = 1; });
"""
        def run(candidate, cases=receipts):
            result = subprocess.run(
                ["node", "-e", harness],
                input=json.dumps({"recipe": candidate, "receipts": cases}),
                text=True, capture_output=True, check=True,
            )
            return json.loads(result.stdout)

        rows = run(recipe)
        self.assertEqual(len(rows), len(receipts))
        self.assertTrue(all(row["calls"] == 1 for row in rows))
        self.assertEqual(rows[0]["strings"], [body])
        self.assertTrue(all(row["strings"] == [] for row in rows[1:]))
        missing_body = run(recipe.replace("text(result.output);", 'text("Read finished");'))
        self.assertNotEqual(missing_body[0]["strings"], [body])
        no_gate = re.sub(r'if \(result === null.*?exit\(\);', '', recipe, flags=re.S)
        self.assertNotEqual(no_gate, recipe)
        ungated = run(no_gate, receipts[:-1])
        self.assertEqual(ungated[1]["strings"], [body])
        self.assertEqual(ungated[6]["strings"], [body])


if __name__ == "__main__":
    unittest.main()
