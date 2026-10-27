"""Check credential delivery through the real launcher without model calls or user state."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'scripts/claude-profiles.sh'


class CredentialBindingTests(unittest.TestCase):
    def launch(self, template, *, bound=True, legacy=False, shell='/bin/bash'):
        with tempfile.TemporaryDirectory() as name:
            task = Path(name)
            base = task / 'base'
            (base / 'settings').mkdir(parents=True)
            profiles = task / 'profiles'
            (profiles / 'sample').mkdir(parents=True)
            helpers = task / 'helpers'
            helpers.mkdir()  # No production source-sync helper is run by this fixture.
            settings = json.loads(template.read_text())
            if legacy:
                settings['env']['ANTHROPIC_AUTH_TOKEN'] = 'SYNTHETIC_LEGACY'
            target = base / 'settings/sample.json'
            target.write_text(json.dumps(settings))
            probe = task / 'consumer.py'
            probe.write_text('''import json,os,sys
from pathlib import Path
assert sys.argv[1]=="--settings"
p=Path(sys.argv[2]); data=json.loads(p.read_text())
token=data.get("env",{}).get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
assert token in {"SYNTHETIC_BOUND","SYNTHETIC_LEGACY"}, "credential binding absent or overridden"
assert sys.argv[3:]==["-p","fixture"]
assert Path(os.environ["CLAUDE_CONFIG_DIR"]).name=="sample"
print(json.dumps({"credential_consumed":True,"settings_argument":True}))
''')
            exports = task / 'exports.zsh'
            exports.write_text('export SAMPLE_API_KEY=SYNTHETIC_BOUND\n')
            rc = task / 'bindings.zsh'
            rc.write_text("alias sample='ANTHROPIC_AUTH_TOKEN=\"$SAMPLE_API_KEY\" claude-profile sample'\n" if bound else "alias sample='claude-profile sample'\n")
            env = {k: v for k, v in os.environ.items() if k not in {'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_API_KEY'}}
            env.update(CLAUDE_BASE_DIR=str(base), CLAUDE_PROFILES_DIR=str(profiles),
                       CLAUDE_PROFILES_CONFIG_DIR=str(helpers), FIXTURE_PROBE=str(probe))
            source = ('shopt -s expand_aliases\n' if shell.endswith('bash') else '') + '''
source "$1"
source "$2"
source "$3"
claude() { python3 "$FIXTURE_PROBE" "$@"; }
eval 'sample -p fixture'
'''
            args = [shell, '--noprofile', '--norc'] if shell.endswith('bash') else [shell, '-f']
            return subprocess.run([*args, '-c', source, 'fixture', str(LAUNCHER), str(exports), str(rc)],
                                  env=env, capture_output=True, text=True, timeout=15)

    def test_every_template_works_with_bound_export(self):
        paths = sorted((ROOT / 'assets/templates').glob('*.json'))
        self.assertIn('kimi.json', {p.name for p in paths})
        self.assertGreaterEqual(len(paths), 10)
        shells = [s for s in ['/bin/bash', '/bin/zsh'] if shutil.which(s)]
        examined = 0
        for path in paths:
            self.assertNotIn('ANTHROPIC_AUTH_TOKEN', json.loads(path.read_text()).get('env', {}))
            for shell in shells:
                with self.subTest(template=path.name, shell=shell):
                    result = self.launch(path, shell=shell)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('"credential_consumed": true', result.stdout)
                    examined += 1
        self.assertEqual(examined, len(paths) * len(shells))

    def test_missing_binding_is_a_real_failure(self):
        result = self.launch(ROOT / 'assets/templates/kimi.json', bound=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"credential_consumed": true', result.stdout)

    def test_legacy_settings_are_still_forwarded(self):
        result = self.launch(ROOT / 'assets/templates/kimi.json', bound=False, legacy=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"credential_consumed": true', result.stdout)


if __name__ == '__main__':
    unittest.main()
