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
        {
            "type": "todo",
            "heading": "Errands",
            "storage_key": "valid-errands",
            "items": ["Buy rice"],
        },
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
        self.assertIn('class="daya-timer-reset" hidden>Reset</button>', page)
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


class BackLinkTests(unittest.TestCase):
    def test_back_link_renders(self):
        recipe = dict(VALID, back={"href": "index.html", "label": "All examples"})
        page = build(recipe)
        self.assertIn(
            '<p class="daya-back"><a href="index.html">All examples</a></p>', page
        )

    def test_back_link_directory_index(self):
        recipe = dict(VALID, back={"href": "./", "label": "All examples"})
        page = build(recipe)
        self.assertIn('<p class="daya-back"><a href="./">All examples</a></p>', page)

    def test_back_href_must_be_relative_html(self):
        for bad in (
            "https://evil.example/x.html",
            "//evil.example/x.html",
            "../up.html",
            "a/../b.html",
            "index.html?x=1",
            "index.htm",
            "INDEX.HTML",
            "",
            5,
        ):
            recipe = dict(VALID, back={"href": bad, "label": "x"})
            _model, errors = web.validate(recipe)
            self.assertTrue(
                any(e.startswith("back.href:") for e in errors),
                "href={!r} should fail".format(bad),
            )

    def test_back_label_escaped(self):
        raw = "<script>alert(1)</script>"
        recipe = dict(VALID, back={"href": "index.html", "label": raw})
        page = build(recipe)
        self.assertNotIn(raw, page)
        self.assertIn(html.escape(raw, quote=True), page)

    def test_back_unknown_field(self):
        recipe = dict(
            VALID, back={"href": "index.html", "label": "x", "target": "_blank"}
        )
        _model, errors = web.validate(recipe)
        self.assertIn("back: unknown field 'target'", errors)

    def test_back_not_an_object(self):
        recipe = dict(VALID, back="index.html")
        _model, errors = web.validate(recipe)
        self.assertIn("back: must be an object", errors)


class ScriptBlockTests(unittest.TestCase):
    def test_script_block_is_exactly_the_fixed_template(self):
        page = build(VALID)
        marker = "<script>\n"
        start = page.index(marker) + len(marker)
        end = page.index("\n</script>")
        self.assertEqual(page[start:end], web._JS)

    def test_no_recipe_data_inside_script_block(self):
        sneaky = 'line seps \u2028 and \u2029 and </script><script>alert(1)</script>'
        recipe = {
            "domain": "web",
            "title": "t",
            "sections": [{"type": "text", "heading": sneaky, "body": sneaky}],
        }
        page = build(recipe)
        start = page.index("<script>\n")
        end = page.index("\n</script>") + len("\n</script>")
        script_block = page[start:end]
        self.assertNotIn("alert(1)", script_block)
        self.assertNotIn("\u2028", script_block)
        self.assertNotIn("\u2029", script_block)
        # the whole recipe string only survives in the escaped body region
        self.assertIn(html.escape(sneaky, quote=True), page[:start])


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


class TodoTests(unittest.TestCase):
    def recipe(self, section, title="t"):
        return {"domain": "web", "title": title, "sections": [section]}

    def test_todo_builds(self):
        page = build(
            self.recipe(
                {
                    "type": "todo",
                    "heading": "This week",
                    "storage_key": "my-app-list",
                    "items": ["one", "two"],
                }
            )
        )
        self.assertIn('data-storage-key="my-app-list"', page)
        self.assertIn("<h2>This week</h2>", page)
        self.assertIn('<span class="daya-todo-text">one</span>', page)
        self.assertIn('<form class="daya-todo-add">', page)
        self.assertIn('class="daya-todo-archived" hidden', page)

    def test_todo_minimal(self):
        page = build(self.recipe({"type": "todo", "storage_key": "bare1"}))
        self.assertIn('data-storage-key="bare1"', page)
        self.assertNotIn("<h2>", page)

    def test_todo_deterministic_bytes(self):
        recipe = self.recipe(
            {"type": "todo", "storage_key": "det1", "items": ["a", "b", "c"]}
        )
        self.assertEqual(build(recipe), build(recipe))

    def test_todo_storage_key_required_and_slug(self):
        for bad in (None, "", "Has Upper", "under_score", "-lead", "x" * 33, 7):
            section = {"type": "todo"}
            if bad is not None:
                section["storage_key"] = bad
            _model, errors = web.validate(self.recipe(section))
            self.assertTrue(
                any(e.startswith("sections[0].storage_key:") for e in errors),
                "storage_key={!r} should fail".format(bad),
            )

    def test_todo_duplicate_storage_key_rejected(self):
        recipe = {
            "domain": "web",
            "title": "t",
            "sections": [
                {"type": "todo", "storage_key": "same-key"},
                {"type": "todo", "storage_key": "same-key"},
            ],
        }
        _model, errors = web.validate(recipe)
        self.assertIn("sections[1].storage_key: duplicates an earlier todo section", errors)

    def test_todo_items_bounded(self):
        for bad_items in (
            "nope",
            [""],
            ["x" * 201],
            [1],
            ["ok"] * (web.MAX_TODO_SEED_ITEMS + 1),
        ):
            section = {"type": "todo", "storage_key": "b1", "items": bad_items}
            _model, errors = web.validate(self.recipe(section))
            self.assertTrue(errors, "items={!r} should fail".format(bad_items))

    def test_todo_unknown_field_rejected(self):
        section = {"type": "todo", "storage_key": "u1", "url": "https://x.example"}
        _model, errors = web.validate(self.recipe(section))
        self.assertIn("sections[0]: unknown field 'url'", errors)

    def test_todo_item_escaped(self):
        raw = '<img src=x onerror="alert(1)">'
        page = build(
            self.recipe({"type": "todo", "storage_key": "esc1", "items": [raw]})
        )
        self.assertNotIn(raw, page)
        self.assertIn(html.escape(raw, quote=True), page)
        self.assertEqual(page.count("<script>"), 1)


class ValidateTests(unittest.TestCase):
    def test_missing_title(self):
        _model, errors = web.validate({"domain": "web", "sections": [{"type": "counter", "label": "x"}]})
        self.assertIn("title: must be a string", errors)

    def test_unknown_section_type(self):
        _model, errors = web.validate(
            {"domain": "web", "title": "t", "sections": [{"type": "video"}]}
        )
        self.assertIn("sections[0].type: must be one of: text, list, counter, quiz, timer, todo, handwriting, drawing", errors)

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


class HandwritingTests(unittest.TestCase):
    STROKES = [
        [[0.1, 0.2], [0.3456, 0.2], [0.5, -0.1]],
        [[1, 2]],
    ]

    def recipe(self, section):
        return {"domain": "web", "title": "Note", "sections": [section]}

    def valid_section(self):
        return {
            "type": "handwriting",
            "heading": "A note",
            "text": "hello from daya",
            "viewbox": [-0.25, -0.42, 8.5, 1.82],
            "strokes": self.STROKES,
        }

    def test_handwriting_builds(self):
        page = build(self.recipe(self.valid_section()))
        self.assertIn('<section class="daya-handwriting">', page)
        self.assertIn("<h2>A note</h2>", page)
        self.assertIn(
            '<svg class="daya-hand" viewBox="-0.25 -0.42 8.5 1.82" role="img"'
            ' aria-label="hello from daya">',
            page,
        )
        self.assertIn('<path d="M0.1 0.2 L0.346 0.2 L0.5 -0.1"/>', page)
        self.assertIn('<path d="M1 2 l0.001 0"/>', page)  # single point = dot

    def test_handwriting_deterministic_bytes(self):
        self.assertEqual(
            build(self.recipe(self.valid_section())),
            build(self.recipe(self.valid_section())),
        )

    def test_handwriting_heading_optional(self):
        section = self.valid_section()
        del section["heading"]
        page = build(self.recipe(section))
        self.assertIn('<section class="daya-handwriting">', page)
        self.assertNotIn("<h2>", page)

    def test_handwriting_text_escaped_in_aria_label(self):
        section = self.valid_section()
        section["text"] = '<script>alert(1)</script> & "quotes"'
        page = build(self.recipe(section))
        self.assertIn(
            "aria-label=\"&lt;script&gt;alert(1)&lt;/script&gt; &amp;"
            " &quot;quotes&quot;\"",
            page,
        )
        self.assertNotIn("<script>alert(1)</script>", page.split("<script>")[0])

    def test_handwriting_rejects_unknown_field(self):
        section = self.valid_section()
        section["writer"] = "sam"
        _model, errors = web.validate(self.recipe(section))
        self.assertIn("sections[0]: unknown field 'writer'", errors)

    def test_handwriting_rejects_bad_viewbox(self):
        for bad in (
            None,
            [0, 0, 1],
            [0, 0, -1, 1],
            [0, 0, 0, 1],
            [0, 0, 1, 10001],
            [0, 0, 1, "x"],
        ):
            section = self.valid_section()
            section["viewbox"] = bad
            _model, errors = web.validate(self.recipe(section))
            self.assertTrue(errors, "viewbox={!r} should fail".format(bad))

    def test_handwriting_rejects_bad_strokes(self):
        for bad in (
            None,
            [],
            "not a list",
            [["not a point"]],
            [[[0, 0, 0]]],
            [[[True, 0]]],
            [[[float("inf"), 0]]],
            [[[float("nan"), 0]]],
            [[[1001, 0]]],
            [[]],
        ):
            section = self.valid_section()
            section["strokes"] = bad
            _model, errors = web.validate(self.recipe(section))
            self.assertTrue(errors, "strokes={!r} should fail".format(bad))

    def test_handwriting_rejects_too_many_points(self):
        section = self.valid_section()
        section["strokes"] = [
            [[0, 0]] * 2000 for _ in range(11)  # 22000 points overall
        ]
        _model, errors = web.validate(self.recipe(section))
        self.assertTrue(
            any("too many points" in e for e in errors), errors
        )

    def test_handwriting_rejects_long_text(self):
        section = self.valid_section()
        section["text"] = "x" * 281
        _model, errors = web.validate(self.recipe(section))
        self.assertTrue(errors)

    def test_handwriting_accepts_int_coordinates(self):
        section = self.valid_section()
        section["viewbox"] = [0, 0, 8, 2]
        section["strokes"] = [[[0, 0], [7, 1]]]
        page = build(self.recipe(section))
        self.assertIn('viewBox="0 0 8 2"', page)
        self.assertIn('<path d="M0 0 L7 1"/>', page)


class DrawingTests(unittest.TestCase):
    def recipe(self, section):
        return {"domain": "web", "title": "Sketch", "sections": [section]}

    def valid_section(self):
        return {
            "type": "drawing",
            "heading": "A penguin",
            "text": "a penguin wearing a top hat",
            "viewbox": [-0.62, -0.62, 1.24, 1.24],
            "strokes": [
                [[-0.3, 0.1], [0, -0.4], [0.3, 0.1], [0, 0.45], [-0.3, 0.1]],
                [[-0.1, -0.45], [0.1, -0.45]],
            ],
        }

    def test_drawing_builds(self):
        page = build(self.recipe(self.valid_section()))
        self.assertIn('<section class="daya-drawing">', page)
        self.assertIn("<h2>A penguin</h2>", page)
        self.assertIn(
            '<svg class="daya-drawing" viewBox="-0.62 -0.62 1.24 1.24"'
            ' role="img" aria-label="a penguin wearing a top hat">',
            page,
        )
        self.assertIn(
            '<path d="M-0.3 0.1 L0 -0.4 L0.3 0.1 L0 0.45 L-0.3 0.1"/>', page
        )
        self.assertIn("stroke: #111", page)  # dark ink, not the accent

    def test_drawing_deterministic_bytes(self):
        self.assertEqual(
            build(self.recipe(self.valid_section())),
            build(self.recipe(self.valid_section())),
        )

    def test_drawing_validation_shared_with_handwriting(self):
        section = self.valid_section()
        section["strokes"] = [[[float("nan"), 0]]]
        _model, errors = web.validate(self.recipe(section))
        self.assertTrue(errors)
        section = self.valid_section()
        section["writer"] = "sam"
        _model, errors = web.validate(self.recipe(section))
        self.assertIn("sections[0]: unknown field 'writer'", errors)


if __name__ == "__main__":
    unittest.main()
