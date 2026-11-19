import json
import os
import tempfile
import unittest

from dayalib.recipe import (
    MAX_RECIPE_BYTES,
    Checker,
    RecipeError,
    check_int,
    check_no_unknown_keys,
    check_string,
    load_recipe,
)


class LoadRecipeTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def _write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_loads_object(self):
        data = load_recipe(self._write("ok.json", '{"domain": "web"}'))
        self.assertEqual(data, {"domain": "web"})

    def test_missing_file(self):
        with self.assertRaises(RecipeError) as ctx:
            load_recipe(os.path.join(self.dir, "nope.json"))
        self.assertIn("cannot read", str(ctx.exception))

    def test_invalid_json_reports_position(self):
        with self.assertRaises(RecipeError) as ctx:
            load_recipe(self._write("bad.json", '{"a": }'))
        message = str(ctx.exception)
        self.assertIn("not valid JSON", message)
        self.assertIn("line 1", message)

    def test_top_level_must_be_object(self):
        with self.assertRaises(RecipeError) as ctx:
            load_recipe(self._write("list.json", '["web"]'))
        self.assertIn("top level must be a JSON object", str(ctx.exception))

    def test_oversize_rejected(self):
        big = '{"domain": "web", "pad": "%s"}' % ("x" * MAX_RECIPE_BYTES)
        with self.assertRaises(RecipeError) as ctx:
            load_recipe(self._write("big.json", big))
        self.assertIn("too large", str(ctx.exception))


class CheckerTests(unittest.TestCase):
    def test_collects_paths(self):
        check = Checker()
        check_string(check, 5, "title", 1, 80)
        check_int(check, "sixty", "sections[0].seconds", 5, 3600)
        self.assertEqual(
            check.errors,
            ["title: must be a string", "sections[0].seconds: must be a whole number"],
        )

    def test_bool_is_not_int(self):
        check = Checker()
        self.assertIsNone(check_int(check, True, "start", 0, 10))
        self.assertEqual(check.errors, ["start: must be a whole number"])

    def test_bounds(self):
        check = Checker()
        check_string(check, "abc", "title", 4, 5)
        check_int(check, 11, "start", 0, 10)
        self.assertEqual(
            check.errors,
            [
                "title: must be 4..5 characters, got 3",
                "start: must be between 0 and 10, got 11",
            ],
        )

    def test_unknown_keys_flagged(self):
        check = Checker()
        check_no_unknown_keys(check, {"type": "text", "url": "https://x"}, {"type"}, "sections[0]")
        self.assertEqual(check.errors, ["sections[0]: unknown field 'url'"])


if __name__ == "__main__":
    unittest.main()
