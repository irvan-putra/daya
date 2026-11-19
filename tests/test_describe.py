"""Unit tests for the bounded text-to-recipe parser."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dayalib.describe import DescribeError, describe
from dayalib.domains import web


class TimerParsingTests(unittest.TestCase):
    def test_minutes_before_timer(self):
        recipe, notes = describe('a 25 minute timer for focus, called "Focus"')
        self.assertEqual(recipe["title"], "Focus")
        self.assertEqual(recipe["sections"][0]["type"], "timer")
        self.assertEqual(recipe["sections"][0]["seconds"], 25 * 60)
        self.assertEqual(recipe["sections"][0]["label"], "focus")

    def test_timer_first(self):
        recipe, _notes = describe("countdown of 90 seconds")
        self.assertEqual(recipe["sections"][0]["seconds"], 90)

    def test_pomodoro_default(self):
        recipe, notes = describe("pomodoro")
        self.assertEqual(recipe["sections"][0]["seconds"], 25 * 60)
        self.assertTrue(any("25 minutes" in n for n in notes))

    def test_over_limit_capped(self):
        recipe, notes = describe("a 3 hour timer")
        self.assertEqual(recipe["sections"][0]["seconds"], 3600)
        self.assertTrue(any("capped" in n for n in notes))

    def test_under_minimum_raised(self):
        recipe, notes = describe("a 2 second timer")
        self.assertEqual(recipe["sections"][0]["seconds"], 5)
        self.assertTrue(any("minimum" in n for n in notes))


class SectionParsingTests(unittest.TestCase):
    def test_counter(self):
        recipe, _notes = describe('a counter for push ups, called "Gym"')
        self.assertEqual(recipe["sections"][0]["type"], "counter")
        self.assertEqual(recipe["sections"][0]["label"], "push ups")

    def test_todo_with_items(self):
        recipe, _notes = describe(
            'a todo list with items: buy rice, call ana and book the train, '
            'called "Errands"'
        )
        section = recipe["sections"][0]
        self.assertEqual(section["type"], "todo")
        self.assertEqual(
            section["items"], ["buy rice", "call ana", "book the train"]
        )
        self.assertRegex(section["storage_key"], r"^[a-z0-9][a-z0-9-]{0,31}$")

    def test_two_todo_sections_get_distinct_keys(self):
        recipe, _notes = describe(
            'a todo list. another todo list, called "Two lists"'
        )
        keys = [s["storage_key"] for s in recipe["sections"]]
        self.assertEqual(len(set(keys)), 2)

    def test_static_list(self):
        recipe, _notes = describe("a list: one, two and three")
        self.assertEqual(recipe["sections"][0]["type"], "list")
        self.assertEqual(recipe["sections"][0]["items"], ["one", "two", "three"])

    def test_text_section(self):
        recipe, _notes = describe("text: hello there, general kenobi")
        section = recipe["sections"][0]
        self.assertEqual(section["type"], "text")
        self.assertEqual(section["body"], "hello there, general kenobi")

    def test_description_and_accent(self):
        recipe, _notes = describe(
            'description: a calm timer. a 10 minute timer, called "Tea", green'
        )
        self.assertEqual(recipe["description"], "a calm timer")
        self.assertEqual(recipe["theme"], {"accent": "green"})

    def test_multiple_sections_in_order(self):
        recipe, _notes = describe(
            'text: welcome. a counter. a list: a, b, called "Multi"'
        )
        self.assertEqual(
            [s["type"] for s in recipe["sections"]], ["text", "counter", "list"]
        )


class FailureAndHonestyTests(unittest.TestCase):
    def test_empty(self):
        with self.assertRaises(DescribeError):
            describe("   ")

    def test_nothing_recognized(self):
        with self.assertRaises(DescribeError) as ctx:
            describe("something completely different")
        self.assertIn("no recognizable sections", str(ctx.exception))
        self.assertIn("timer", str(ctx.exception))

    def test_unrecognized_sentences_are_listed(self):
        _recipe, notes = describe("a counter. quantum blockchain synergy")
        self.assertTrue(
            any("quantum blockchain synergy" in n for n in notes),
            "ignored sentences must be reported, notes={!r}".format(notes),
        )

    def test_too_long(self):
        with self.assertRaises(DescribeError):
            describe("a counter. " * 1000)

    def test_deterministic(self):
        text = 'a todo list with items: a, b. a 5 minute timer, called "Det"'
        first, _n1 = describe(text)
        second, _n2 = describe(text)
        self.assertEqual(first, second)


class EmittedRecipeTests(unittest.TestCase):
    def test_every_output_validates(self):
        samples = [
            'a 25 minute timer for focus, called "Focus"',
            "pomodoro",
            'a counter for steps, called "Walk", description: counts things',
            "a todo list with items: one, two and three",
            'text: hi. a list: x, y. a counter. a 90 second timer, called "All"',
        ]
        for text in samples:
            recipe, _notes = describe(text)
            _model, errors = web.validate(recipe)
            self.assertEqual(errors, [], "sample {!r}: {}".format(text, errors))

    def test_recipe_json_round_trips(self):
        recipe, _notes = describe('a counter, called "Round"')
        loaded = json.loads(json.dumps(recipe))
        _model, errors = web.validate(loaded)
        self.assertEqual(errors, [])

    def test_html_in_strings_is_built_escaped(self):
        recipe, _notes = describe('text: <script>alert(1)</script>, called "X"')
        model, errors = web.validate(recipe)
        self.assertEqual(errors, [])
        page = web.generate(model)
        self.assertNotIn("<script>alert(1)</script>", page)
        web.self_check(page, model)

    def test_cli_describe_writes_valid_recipe(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "recipe.json")
            result = subprocess.run(
                [
                    sys.executable,
                    os.path.join(root, "daya"),
                    "describe",
                    "a 10 minute timer for tea, called Tea",
                    "-o",
                    out,
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            recipe = json.load(open(out))
            self.assertEqual(recipe["title"], "Tea")
            _model, errors = web.validate(recipe)
            self.assertEqual(errors, [])

    def test_cli_describe_failure_explains(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        result = subprocess.run(
            [sys.executable, os.path.join(root, "daya"), "describe", "gibberish"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("no recognizable sections", result.stderr)


if __name__ == "__main__":
    unittest.main()
