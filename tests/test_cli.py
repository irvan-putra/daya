import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAYA = os.path.join(ROOT, "daya")


def run_daya(*args):
    return subprocess.run(
        [sys.executable, DAYA] + list(args),
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def _write(self, name, data):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return path

    def test_build_example(self):
        out = os.path.join(self.dir, "app.html")
        result = run_daya("build", os.path.join(ROOT, "examples", "focus-timer.json"), "-o", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.exists(out))
        self.assertIn("sha256", result.stdout)

    def test_build_is_byte_identical_across_runs(self):
        first = os.path.join(self.dir, "a.html")
        second = os.path.join(self.dir, "b.html")
        recipe = os.path.join(ROOT, "examples", "reading-quiz.json")
        self.assertEqual(run_daya("build", recipe, "-o", first).returncode, 0)
        self.assertEqual(run_daya("build", recipe, "-o", second).returncode, 0)
        with open(first, "rb") as fh:
            a = fh.read()
        with open(second, "rb") as fh:
            b = fh.read()
        self.assertEqual(a, b)

    def test_invalid_recipe_exit_2_with_paths(self):
        recipe = self._write("bad.json", {"domain": "web", "sections": []})
        result = run_daya("build", recipe, "-o", os.path.join(self.dir, "x.html"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("title:", result.stderr)
        self.assertIn("sections:", result.stderr)

    def test_unknown_domain_exit_2(self):
        recipe = self._write("android.json", {"domain": "android", "title": "t"})
        result = run_daya("validate", recipe)
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown domain", result.stderr)
        self.assertIn("web", result.stderr)

    def test_validate_ok(self):
        result = run_daya("validate", os.path.join(ROOT, "examples", "focus-timer.json"))
        self.assertEqual(result.returncode, 0)
        self.assertIn("valid web recipe", result.stdout)

    def test_domains_lists_web(self):
        result = run_daya("domains")
        self.assertEqual(result.returncode, 0)
        self.assertIn("web:", result.stdout)

    def test_schema_web(self):
        result = run_daya("schema", "web")
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed["domain"], "web")

    def test_schema_unknown(self):
        result = run_daya("schema", "android")
        self.assertEqual(result.returncode, 2)

    def test_version(self):
        result = run_daya("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn("0.1.0", result.stdout)


if __name__ == "__main__":
    unittest.main()
