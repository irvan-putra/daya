#!/usr/bin/env python3
"""Generate tests/compose_fixtures.json from the Python implementations.

The compose page's compose-core.js is a browser port of dayalib/describe.py
and the web domain's validate(). These fixtures pin the parity: the browser
test replays each case in headless Chrome and compares results exactly.

Run after changing describe.py or web.py validation:

    python3 tests/generate_compose_fixtures.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dayalib.describe import DescribeError, describe
from dayalib.domains import web

DESCRIBE_INPUTS = [
    'a 25 minute timer for focus, called "Focus"',
    "countdown of 90 seconds",
    "pomodoro",
    "a 3 hour timer",
    "a 2 second timer",
    "timer of 10 minutes for tea",
    'a counter for push ups, called "Gym"',
    "a counter",
    'a todo list with items: buy rice, call ana and book the train, called "Errands"',
    "a todo list. another todo list, called 'Two lists'",
    "my shopping list with items: rice, eggs",
    "a list: one, two and three",
    "a list of apples, pears",
    "text: hello there, general kenobi",
    "a note that says drink water",
    'description: a calm timer. a 10 minute timer, called "Tea", green',
    "text: welcome. a counter. a list: a, b, called \"Multi\"",
    'a 25 minute timer for focus, called "Focus", description: a quiet pomodoro page, green',
    'a TO-DO LIST with items: UPPER, lower, called "Cases"',
    "a counter. quantum blockchain synergy",
    "something completely different",
    "   ",
    'errands with items "quoted item", plain item, called "Q"',
]

VALIDATE_RECIPES = [
    {"domain": "web", "title": "ok", "sections": [{"type": "counter", "label": "x"}]},
    {"domain": "web", "sections": []},
    {"domain": "web", "title": "no sections"},
    {"domain": "web", "title": "bad type", "sections": [{"type": "video"}]},
    {"domain": "web", "title": "unknown", "sections": [{"type": "counter", "label": "x", "x": 1}]},
    {"domain": "web", "title": "bad quiz", "sections": [{"type": "quiz", "question": "q", "choices": ["a"], "answer": 5}]},
    {"domain": "web", "title": "no answer", "sections": [{"type": "quiz", "question": "q", "choices": ["a", "b"]}]},
    {"domain": "web", "title": "bad key", "sections": [{"type": "todo", "storage_key": "BAD KEY!"}]},
    {"domain": "web", "title": "dup keys", "sections": [
        {"type": "todo", "storage_key": "same"},
        {"type": "todo", "storage_key": "same"},
    ]},
    {"domain": "web", "title": "bad accent", "theme": {"accent": "purple"}, "sections": [{"type": "counter", "label": "x"}]},
    {"domain": "web", "title": "theme not object", "theme": "green", "sections": [{"type": "counter", "label": "x"}]},
    {"domain": "web", "title": "bad back", "back": {"href": "https://evil.example/x.html", "label": "x"}, "sections": [{"type": "counter", "label": "x"}]},
    {"domain": "web", "title": "back ok", "back": {"href": "index.html", "label": "home"}, "sections": [{"type": "counter", "label": "x"}]},
    {"domain": "web", "title": "back dir", "back": {"href": "./", "label": "home"}, "sections": [{"type": "counter", "label": "x"}]},
    {"domain": "web", "title": "back bad dir", "back": {"href": "../", "label": "home"}, "sections": [{"type": "counter", "label": "x"}]},
    {"domain": "web", "title": "long timer", "sections": [{"type": "timer", "label": "t", "seconds": 99999}]},
    {"domain": "web", "title": "todo no items ok", "sections": [{"type": "todo", "storage_key": "fine-key"}]},
    {"domain": "web", "title": 42, "sections": [{"type": "counter", "label": "x"}]},
    {"domain": "web", "title": "list empty", "sections": [{"type": "list", "items": []}]},
    {"domain": "web", "title": "item types", "sections": [{"type": "list", "items": ["ok", 5, "also ok"]}]},
]


def main():
    describe_cases = []
    for text in DESCRIBE_INPUTS:
        try:
            recipe, notes = describe(text)
            describe_cases.append({"input": text, "recipe": recipe, "error": None})
        except DescribeError as exc:
            describe_cases.append({"input": text, "recipe": None, "error": str(exc)})

    validate_cases = []
    for recipe in VALIDATE_RECIPES:
        _model, errors = web.validate(recipe)
        validate_cases.append({"recipe": recipe, "errors": errors})

    out = {"describe_cases": describe_cases, "validate_cases": validate_cases}
    path = os.path.join(ROOT, "tests", "compose_fixtures.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(
        "wrote {} ({} describe cases, {} validate cases)".format(
            path, len(describe_cases), len(validate_cases)
        )
    )


if __name__ == "__main__":
    main()
