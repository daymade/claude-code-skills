"""Exercise the documented import recipe through actual unittest discovery."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


class OptionalDependencyRecipeTests(unittest.TestCase):
    def run_case(self, vendor):
        reference = Path(__file__).resolve().parents[1] / "references/stateful-script-verification.md"
        snippets = re.findall(
            r"<!-- optional-test-import-example -->\s*```python\n(.*?)\n```",
            reference.read_text(), re.S,
        )
        self.assertEqual(len(snippets), 1, "One authoritative executable import recipe required")
        with tempfile.TemporaryDirectory(prefix="optional dependency recipe ") as directory:
            root = Path(directory)
            (root / "test_optional.py").write_text(snippets[0] + '''
import unittest
class ActualAssertion(unittest.TestCase):
    def test_dependency_is_used(self):
        self.assertEqual(optional_vendor.SENTINEL, "synthetic-loaded")
''')
            if vendor is not None:
                (root / "optional_vendor.py").write_text(vendor)
            result = subprocess.run(
                [sys.executable, "-I", "-S", "-m", "unittest", "discover",
                 "-s", str(root), "-p", "test_optional.py", "-v"],
                capture_output=True, text=True, timeout=20,
            )
        return result.returncode, result.stdout + result.stderr

    def test_present_dependency_executes_the_assertion(self):
        code, output = self.run_case('SENTINEL = "synthetic-loaded"\n')
        self.assertEqual(code, 0, output)
        self.assertIn("test_dependency_is_used", output)
        self.assertIn("Ran 1 test", output)
        self.assertNotIn("skipped", output)

    def test_exact_optional_absence_is_an_explicit_skip(self):
        code, output = self.run_case(None)
        self.assertEqual(code, 0, output)
        self.assertIn("Optional tests require optional_vendor", output)
        self.assertIn("OK (skipped=1)", output)

    def test_transitive_missing_dependency_still_fails(self):
        code, output = self.run_case("import synthetic_transitive_dependency_absent\n")
        self.assertEqual(code, 1, output)
        self.assertIn("synthetic_transitive_dependency_absent", output)
        self.assertIn("FAILED (errors=1)", output)
        self.assertNotIn("skipped", output)


if __name__ == "__main__":
    unittest.main()
