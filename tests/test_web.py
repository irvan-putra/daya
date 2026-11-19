import html
import random
import unittest

from dayalib.domains import web


def build(recipe):
    model, errors = web.validate(recipe)
    assert not errors, errors
    page = web.generate(model)
    web.self_check(page, model)
    return page


VALID = {
    "domain": "web",
    "title": "Focus timer",
    "description": "A tiny helper page.",
    "theme": {"accent": "teal"},
    "sections": [
        {"type": "text", "heading": "How it works", "body": "Start. Work. Rest."},
        {"type": "timer", "label": "Focus block", "seconds": 1500},
        {"type": "counter", "label": "Glass of water"},
        {
            "type": "quiz",
            "question": "How long is one block?",
            "choices": ["5 minutes", "25 minutes"],
            "answer": 1,
        },
        {"type": "list", "heading": "Rules", "items": ["Phone away", "One task"]},
    ],
}


class GenerateTests(unittest.TestCase):
    def test_valid_recipe_builds(self):
        page = build(VALID)
        self.assertTrue(page.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>Focus timer</title>", page)
        self.assertIn("25:00", page)  # 1500 seconds rendered mm:ss
        self.assertIn('data-answer="1"', page)
        self.assertIn('data-seconds="1500"', page)
        self.assertIn("#0f766e", page)  # teal accent

    def test_deterministic_bytes(self):
        self.assertEqual(build(VALID), build(VALID))

    def test_description_and_heading_optional(self):
        recipe = {
            "domain": "web",
            "title": "Bare",
            "sections": [{"type": "list", "items": ["one"]}],
        }
        page = build(recipe)
        self.assertIn("<li>one</li>", page)
        self.assertNotIn('<p class="lede">', page)

    def test_body_newlines_become_breaks(self):
        recipe = {
            "domain": "web",
            "title": "Lines",
            "sections": [{"type": "text", "heading": "h", "body": "first\nsecond"}],
        }
        self.assertIn("first<br>\nsecond", build(recipe))


class SecurityTests(unittest.TestCase):
    def test_html_in_title_is_escaped(self):
        raw = '<img src=x onerror="alert(1)">'
        recipe = dict(VALID, title=raw)
        page = build(recipe)
        self.assertNotIn(raw, page)
        self.assertIn(html.escape(raw, quote=True), page)

    def test_script_breakout_impossible(self):
        raw = "</script><script>alert(1)</script>"
        recipe = {
            "domain": "web",
            "title": "t",
            "sections": [{"type": "text", "heading": raw, "body": raw}],
        }
        page = build(recipe)
        self.assertEqual(page.count("<script>"), 1)  # only the fixed template
        self.assertEqual(page.count("</script>"), 1)
        self.assertNotIn(raw, page)

    def test_no_link_or_image_fields_exist(self):
        recipe = {
            "domain": "web",
            "title": "t",
            "sections": [
                {"type": "text", "heading": "h", "body": "b", "url": "https://example.com"}
            ],
        }
        _model, errors = web.validate(recipe)
        self.assertIn("sections[0]: unknown field 'url'", errors)

    def test_fuzz_recipe_strings_stay_escaped(self):
        rng = random.Random(20261119)
        alphabet = "<>&\"'`=/script(){}[];:\\"
        for round_no in range(200):
            raw = "ZZ" + "".join(
                rng.choice(alphabet) for _ in range(rng.randrange(1, 30))
            ) + "ZZ"  # trailing sentinel: raw can never prefix its escaped form
            recipe = {
                "domain": "web",
                "title": "fuzz",
                "sections": [{"type": "text", "heading": raw, "body": raw}],
            }
            page = build(recipe)
            escaped = html.escape(raw, quote=True)
            if escaped != raw:
                self.assertNotIn(
                    raw, page, "round {}: raw recipe string leaked".format(round_no)
                )
            self.assertIn(escaped, page)
            self.assertEqual(page.count("<script>"), 1)

    def test_oversized_recipe_shape_rejected(self):
        recipe = {
            "domain": "web",
            "title": "t",
            "sections": [
                {"type": "text", "heading": "h", "body": "b"}
                for _ in range(web.MAX_SECTIONS + 1)
            ],
        }
        _model, errors = web.validate(recipe)
        self.assertTrue(any(e.startswith("sections: must have 1..24") for e in errors))


class ValidateTests(unittest.TestCase):
    def test_missing_title(self):
        _model, errors = web.validate({"domain": "web", "sections": [{"type": "counter", "label": "x"}]})
        self.assertIn("title: must be a string", errors)

    def test_unknown_section_type(self):
        _model, errors = web.validate(
            {"domain": "web", "title": "t", "sections": [{"type": "video"}]}
        )
        self.assertIn("sections[0].type: must be one of: text, list, counter, quiz, timer", errors)

    def test_quiz_answer_must_be_valid_index(self):
        recipe = {
            "domain": "web",
            "title": "t",
            "sections": [
                {"type": "quiz", "question": "q", "choices": ["a", "b"], "answer": 2}
            ],
        }
        _model, errors = web.validate(recipe)
        self.assertIn("sections[0].answer: must be between 0 and 1, got 2", errors)

    def test_quiz_needs_two_choices(self):
        recipe = {
            "domain": "web",
            "title": "t",
            "sections": [{"type": "quiz", "question": "q", "choices": ["a"], "answer": 0}],
        }
        _model, errors = web.validate(recipe)
        self.assertIn("sections[0].choices: must be a list of 2..6 choices", errors)

    def test_timer_bounds(self):
        for bad in (4, 3601, "sixty"):
            recipe = {
                "domain": "web",
                "title": "t",
                "sections": [{"type": "timer", "label": "x", "seconds": bad}],
            }
            _model, errors = web.validate(recipe)
            self.assertTrue(errors, "seconds={!r} should fail".format(bad))

    def test_counter_start_must_be_int_not_bool(self):
        recipe = {
            "domain": "web",
            "title": "t",
            "sections": [{"type": "counter", "label": "x", "start": True}],
        }
        _model, errors = web.validate(recipe)
        self.assertIn("sections[0].start: must be a whole number", errors)

    def test_unknown_accent_listed(self):
        recipe = {
            "domain": "web",
            "title": "t",
            "theme": {"accent": "neon"},
            "sections": [{"type": "counter", "label": "x"}],
        }
        _model, errors = web.validate(recipe)
        self.assertTrue(any(e.startswith("theme.accent: must be one of:") for e in errors))

    def test_multiple_errors_all_reported(self):
        recipe = {
            "domain": "web",
            "sections": [{"type": "quiz", "question": "", "choices": "nope"}],
        }
        _model, errors = web.validate(recipe)
        self.assertGreaterEqual(len(errors), 3)


if __name__ == "__main__":
    unittest.main()
