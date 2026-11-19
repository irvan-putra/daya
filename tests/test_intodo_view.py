import html
import unittest

from dayalib.domains import intodo_view as view


VALID = {
    "domain": "intodo-view",
    "title": "Focus",
    "description": "Unfinished items only.",
    "theme": {"accent": "green"},
}


def build(recipe):
    model, errors = view.validate(recipe)
    assert not errors, errors
    page = view.generate(model)
    view.self_check(page, model)
    return page


class GenerateTests(unittest.TestCase):
    def test_valid_recipe_builds(self):
        page = build(VALID)
        self.assertTrue(page.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>Focus</title>", page)
        self.assertIn('src="js/itd-controller.js"', page)
        self.assertIn('href="index.html"', page)
        self.assertIn("#15803d", page)  # green accent

    def test_deterministic_bytes(self):
        self.assertEqual(build(VALID), build(VALID))

    def test_description_optional(self):
        recipe = {"domain": "intodo-view", "title": "t"}
        page = build(recipe)
        self.assertNotIn('<p class="lede">', page)

    def test_no_state_or_transport_references(self):
        page = build(VALID)
        for banned in ("localStorage", "webxdc", "MergeDoc", "sendUpdate"):
            self.assertNotIn(banned, page)

    def test_script_block_is_exactly_the_fixed_template(self):
        page = build(VALID)
        marker = "<script>\n"
        start = page.index(marker) + len(marker)
        end = page.index("\n</script>")
        self.assertEqual(
            page[start:end],
            view._JS.replace("__CONTROLLER_GLOBAL__", view.CONTROLLER_GLOBAL),
        )

    def test_recipe_strings_escaped(self):
        raw = '<img src=x onerror="alert(1)">'
        page = build({"domain": "intodo-view", "title": raw})
        self.assertNotIn(raw, page)
        self.assertIn(html.escape(raw, quote=True), page)

    def test_self_check_rejects_state_leak(self):
        model, errors = view.validate(VALID)
        assert not errors
        page = view.generate(model)
        with self.assertRaises(ValueError):
            view.self_check(page + "localStorage", model)


class ValidateTests(unittest.TestCase):
    def errors(self, recipe):
        _model, errors = view.validate(recipe)
        return errors

    def test_missing_title(self):
        self.assertIn(
            "title: must be a string",
            self.errors({"domain": "intodo-view"}),
        )

    def test_unknown_fields_rejected(self):
        errors = self.errors(
            {"domain": "intodo-view", "title": "t", "storage_key": "x", "sections": []}
        )
        self.assertIn("recipe: unknown field 'storage_key'", errors)
        self.assertIn("recipe: unknown field 'sections'", errors)

    def test_accent_rules(self):
        errors = self.errors(
            {"domain": "intodo-view", "title": "t", "theme": {"accent": "neon"}}
        )
        self.assertTrue(any(e.startswith("theme.accent:") for e in errors))


if __name__ == "__main__":
    unittest.main()
