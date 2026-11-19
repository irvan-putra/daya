"""The web domain: a recipe becomes one self-contained HTML mini-app.

Safety model: every recipe string is data, never code. Strings are
HTML-escaped before they reach the page; the only JavaScript is the
fixed, reviewed template in this file; interactive behaviour is driven
by data-* attributes holding validated integers. A recipe cannot inject
markup, scripts, styles, links or images.

Determinism: the output depends only on the recipe and this file. No
timestamps, no randomness, no network access: same recipe, same bytes.
"""

import html

from .. import __version__
from ..recipe import Checker, check_int, check_no_unknown_keys, check_string

DOMAIN = "web"
DESCRIPTION = (
    "One self-contained HTML mini-app: styled text, lists, counters, "
    "quizzes and timers. No links, images or custom code."
)

ACCENTS = {
    "indigo": "#4f46e5",
    "teal": "#0f766e",
    "amber": "#b45309",
    "rose": "#be123c",
    "green": "#15803d",
    "slate": "#334155",
}
DEFAULT_ACCENT = "indigo"

MAX_SECTIONS = 24
MAX_LIST_ITEMS = 50
SECTION_TYPES = ("text", "list", "counter", "quiz", "timer")

_TOP_KEYS = {"domain", "title", "description", "theme", "sections"}


def validate(recipe):
    """Return (model, errors). model is cleaned input safe to generate from."""
    check = Checker()
    model = {"sections": []}

    check_no_unknown_keys(check, recipe, _TOP_KEYS, "recipe")

    title = check_string(check, recipe.get("title"), "title", 1, 80)
    if title is not None:
        model["title"] = title

    if "description" in recipe:
        description = check_string(check, recipe.get("description"), "description", 1, 280)
        if description is not None:
            model["description"] = description

    accent = DEFAULT_ACCENT
    theme = recipe.get("theme")
    if theme is not None:
        if not isinstance(theme, dict):
            check.fail("theme", "must be an object")
        else:
            check_no_unknown_keys(check, theme, {"accent"}, "theme")
            if "accent" in theme:
                if theme["accent"] not in ACCENTS:
                    check.fail(
                        "theme.accent",
                        "must be one of: {}".format(", ".join(sorted(ACCENTS))),
                    )
                else:
                    accent = theme["accent"]
    model["accent"] = accent

    sections = recipe.get("sections")
    if not isinstance(sections, list):
        check.fail("sections", "must be a list")
    elif not 1 <= len(sections) <= MAX_SECTIONS:
        check.fail(
            "sections",
            "must have 1..{} items, got {}".format(MAX_SECTIONS, len(sections)),
        )
    else:
        for i, section in enumerate(sections):
            cleaned = _validate_section(check, section, "sections[{}]".format(i))
            if cleaned is not None:
                model["sections"].append(cleaned)

    return model, check.errors


def _validate_section(check, section, path):
    if not isinstance(section, dict):
        check.fail(path, "must be an object")
        return None
    stype = section.get("type")
    if stype not in SECTION_TYPES:
        check.fail(path + ".type", "must be one of: {}".format(", ".join(SECTION_TYPES)))
        return None

    if stype == "text":
        check_no_unknown_keys(check, section, {"type", "heading", "body"}, path)
        heading = check_string(check, section.get("heading"), path + ".heading", 1, 80)
        body = check_string(check, section.get("body"), path + ".body", 1, 2000)
        if heading is None or body is None:
            return None
        return {"type": "text", "heading": heading, "body": body}

    if stype == "list":
        check_no_unknown_keys(check, section, {"type", "heading", "items"}, path)
        heading = section.get("heading")
        if heading is not None:
            heading = check_string(check, heading, path + ".heading", 1, 80)
        items = section.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_LIST_ITEMS:
            check.fail(
                path + ".items", "must be a list of 1..{} items".format(MAX_LIST_ITEMS)
            )
            return None
        clean_items = []
        ok = True
        if section.get("heading") is not None and heading is None:
            ok = False
        for j, item in enumerate(items):
            cleaned_item = check_string(check, item, "{}.items[{}]".format(path, j), 1, 200)
            if cleaned_item is None:
                ok = False
            else:
                clean_items.append(cleaned_item)
        if not ok:
            return None
        return {"type": "list", "heading": heading, "items": clean_items}

    if stype == "counter":
        check_no_unknown_keys(check, section, {"type", "label", "start"}, path)
        label = check_string(check, section.get("label"), path + ".label", 1, 80)
        start = check_int(check, section.get("start", 0), path + ".start", -1000000, 1000000)
        if label is None or start is None:
            return None
        return {"type": "counter", "label": label, "start": start}

    if stype == "quiz":
        check_no_unknown_keys(
            check, section, {"type", "question", "choices", "answer"}, path
        )
        question = check_string(check, section.get("question"), path + ".question", 1, 280)
        choices = section.get("choices")
        clean_choices = []
        choices_ok = True
        if not isinstance(choices, list) or not 2 <= len(choices) <= 6:
            check.fail(path + ".choices", "must be a list of 2..6 choices")
            choices_ok = False
        else:
            for j, choice in enumerate(choices):
                c = check_string(check, choice, "{}.choices[{}]".format(path, j), 1, 120)
                if c is None:
                    choices_ok = False
                else:
                    clean_choices.append(c)
        if "answer" not in section:
            check.fail(path + ".answer", "is required")
            answer = None
        elif choices_ok:
            answer = check_int(
                check, section.get("answer"), path + ".answer", 0, len(clean_choices) - 1
            )
        else:
            answer = None
        if question is None or not choices_ok or answer is None:
            return None
        return {
            "type": "quiz",
            "question": question,
            "choices": clean_choices,
            "answer": answer,
        }

    if stype == "timer":
        check_no_unknown_keys(check, section, {"type", "label", "seconds"}, path)
        label = check_string(check, section.get("label"), path + ".label", 1, 80)
        seconds = check_int(check, section.get("seconds"), path + ".seconds", 5, 3600)
        if label is None or seconds is None:
            return None
        return {"type": "timer", "label": label, "seconds": seconds}

    raise AssertionError("unhandled section type")  # pragma: no cover


def _esc(text):
    return html.escape(text, quote=True)


def _esc_multiline(text):
    return "<br>\n".join(_esc(line) for line in text.split("\n"))


def _mmss(seconds):
    return "{:02d}:{:02d}".format(seconds // 60, seconds % 60)


_CSS = """
:root { --accent: __ACCENT__; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background: #fafafa; color: #1f2933; line-height: 1.55; }
main { max-width: 40rem; margin: 0 auto; padding: 1.25rem; }
h1 { font-size: 1.6rem; margin: 0.5rem 0; }
.lede { color: #52606d; margin-top: 0; }
section { background: #fff; border: 1px solid #e4e7eb; border-radius: 0.75rem; padding: 1rem 1.25rem; margin: 1rem 0; }
h2 { font-size: 1.1rem; margin: 0 0 0.5rem; }
section p { margin: 0.25rem 0; }
ul { margin: 0.25rem 0; padding-left: 1.25rem; }
button { font: inherit; color: #fff; background: var(--accent); border: none; border-radius: 0.5rem; padding: 0.6rem 1rem; cursor: pointer; }
button:disabled { opacity: 0.55; cursor: default; }
.daya-counter { display: flex; align-items: center; gap: 0.75rem; }
.daya-counter-value { font-size: 1.5rem; font-weight: 600; min-width: 3ch; text-align: center; font-variant-numeric: tabular-nums; }
.daya-quiz-choices { display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.5rem; }
.daya-choice { background: #fff; color: var(--accent); border: 1px solid var(--accent); text-align: left; }
.daya-choice.daya-answer { background: var(--accent); color: #fff; }
.daya-quiz-result { margin: 0.75rem 0 0; font-weight: 600; }
.daya-good { color: #15803d; }
.daya-bad { color: #be123c; }
.daya-timer { text-align: center; }
.daya-timer-display { display: block; font-size: 2.25rem; font-weight: 700; font-variant-numeric: tabular-nums; margin: 0.5rem 0; }
footer { text-align: center; color: #9aa5b1; font-size: 0.8rem; margin: 2rem 0 1rem; }
""".strip()

_JS = """
"use strict";
document.addEventListener("click", function (event) {
  var btn = event.target.closest("button");
  if (!btn) {
    return;
  }

  if (btn.classList.contains("daya-counter-btn")) {
    var out = btn.parentElement.querySelector(".daya-counter-value");
    out.textContent = String(parseInt(out.textContent, 10) + 1);
    return;
  }

  if (btn.classList.contains("daya-choice")) {
    var quiz = btn.closest(".daya-quiz");
    var result = quiz.querySelector(".daya-quiz-result");
    var picked = parseInt(btn.getAttribute("data-choice"), 10);
    var answer = parseInt(quiz.getAttribute("data-answer"), 10);
    quiz.querySelectorAll(".daya-choice").forEach(function (b) {
      b.disabled = true;
    });
    result.hidden = false;
    if (picked === answer) {
      result.textContent = "Correct.";
      result.setAttribute("class", "daya-quiz-result daya-good");
    } else {
      result.textContent = "Not quite. The right answer is marked.";
      result.setAttribute("class", "daya-quiz-result daya-bad");
      quiz
        .querySelector('[data-choice="' + answer + '"]')
        .classList.add("daya-answer");
    }
    return;
  }

  if (btn.classList.contains("daya-timer-btn")) {
    var box = btn.closest(".daya-timer");
    var display = box.querySelector(".daya-timer-display");
    var left = parseInt(box.getAttribute("data-seconds"), 10);
    if (box._dayaRunning) {
      return;
    }
    box._dayaRunning = true;
    btn.disabled = true;
    var tick = function () {
      var m = Math.floor(left / 60);
      var s = left % 60;
      display.textContent = (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
      if (left <= 0) {
        clearInterval(box._dayaTimer);
        box._dayaRunning = false;
        display.textContent = "Done";
        btn.disabled = false;
        return;
      }
      left -= 1;
    };
    tick();
    box._dayaTimer = setInterval(tick, 1000);
    return;
  }
});
""".strip()


def _section_html(section):
    stype = section["type"]

    if stype == "text":
        return [
            '<section class="daya-text">',
            "<h2>{}</h2>".format(_esc(section["heading"])),
            "<p>{}</p>".format(_esc_multiline(section["body"])),
            "</section>",
        ]

    if stype == "list":
        lines = ['<section class="daya-list">']
        if section["heading"]:
            lines.append("<h2>{}</h2>".format(_esc(section["heading"])))
        lines.append("<ul>")
        for item in section["items"]:
            lines.append("<li>{}</li>".format(_esc(item)))
        lines.append("</ul>")
        lines.append("</section>")
        return lines

    if stype == "counter":
        return [
            '<section class="daya-counter">',
            '<button type="button" class="daya-counter-btn">{}</button>'.format(
                _esc(section["label"])
            ),
            '<output class="daya-counter-value">{}</output>'.format(section["start"]),
            "</section>",
        ]

    if stype == "quiz":
        lines = [
            '<section class="daya-quiz" data-answer="{}">'.format(section["answer"]),
            '<p class="daya-quiz-q">{}</p>'.format(_esc(section["question"])),
            '<div class="daya-quiz-choices">',
        ]
        for idx, choice in enumerate(section["choices"]):
            lines.append(
                '<button type="button" class="daya-choice" data-choice="{}">{}</button>'.format(
                    idx, _esc(choice)
                )
            )
        lines.append("</div>")
        lines.append('<p class="daya-quiz-result" hidden></p>')
        lines.append("</section>")
        return lines

    if stype == "timer":
        return [
            '<section class="daya-timer" data-seconds="{}">'.format(section["seconds"]),
            '<p class="daya-timer-label">{}</p>'.format(_esc(section["label"])),
            '<output class="daya-timer-display">{}</output>'.format(
                _mmss(section["seconds"])
            ),
            '<button type="button" class="daya-timer-btn">Start</button>',
            "</section>",
        ]

    raise AssertionError("unhandled section type")  # pragma: no cover


def generate(model):
    """Render a validated model as one self-contained HTML document."""
    accent = ACCENTS[model["accent"]]
    out = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="generator" content="daya {}">'.format(__version__),
        "<title>{}</title>".format(_esc(model["title"])),
        "<style>",
        _CSS.replace("__ACCENT__", accent),
        "</style>",
        "</head>",
        "<body>",
        "<main>",
        "<h1>{}</h1>".format(_esc(model["title"])),
    ]
    if model.get("description"):
        out.append('<p class="lede">{}</p>'.format(_esc_multiline(model["description"])))
    for section in model["sections"]:
        out.extend(_section_html(section))
    out.extend(
        [
            "</main>",
            "<footer>generated by daya {} &middot; deterministic, works offline</footer>".format(
                __version__
            ),
            "<script>",
            _JS,
            "</script>",
            "</body>",
            "</html>",
            "",
        ]
    )
    return "\n".join(out)


def _expected_strings(model):
    """Every recipe string as it must appear in the output, fully escaped."""
    found = [_esc(model["title"])]
    if model.get("description"):
        found.append(_esc_multiline(model["description"]))
    for section in model["sections"]:
        if section["type"] == "text":
            found.append(_esc(section["heading"]))
            found.append(_esc_multiline(section["body"]))
        elif section["type"] == "list":
            if section["heading"]:
                found.append(_esc(section["heading"]))
            found.extend(_esc(item) for item in section["items"])
        elif section["type"] == "counter":
            found.append(_esc(section["label"]))
        elif section["type"] == "quiz":
            found.append(_esc(section["question"]))
            found.extend(_esc(choice) for choice in section["choices"])
        elif section["type"] == "timer":
            found.append(_esc(section["label"]))
    return found


def self_check(page, model):
    """Sanity-check generated output before it is written to disk."""
    problems = []
    if not page.startswith("<!DOCTYPE html>"):
        problems.append("missing doctype")
    if not page.rstrip().endswith("</html>"):
        problems.append("missing closing </html>")
    if page.count("<script>") != 1 or page.count("</script>") != 1:
        problems.append("expected exactly one script block")
    if page.count("<section") != len(model["sections"]):
        problems.append("section count mismatch")
    for expected in _expected_strings(model):
        if expected not in page:
            problems.append("escaped content missing: {!r}".format(expected[:40]))
    if problems:
        raise ValueError("generated page failed self-check: " + "; ".join(problems))


def schema():
    """A plain-JSON description of the web recipe format."""
    return {
        "domain": "web",
        "description": DESCRIPTION,
        "fields": {
            "domain": 'the string "web"',
            "title": "string, 1..80 characters",
            "description": "optional string, 1..280 characters",
            "theme": {"accent": "optional, one of: " + ", ".join(sorted(ACCENTS))},
            "sections": "list of 1..{} section objects".format(MAX_SECTIONS),
        },
        "section types": {
            "text": {"heading": "string 1..80", "body": "string 1..2000, newlines kept"},
            "list": {
                "heading": "optional string 1..80",
                "items": "list of 1..{} strings, each 1..200".format(MAX_LIST_ITEMS),
            },
            "counter": {
                "label": "string 1..80 (button text)",
                "start": "optional whole number, -1000000..1000000, default 0",
            },
            "quiz": {
                "question": "string 1..280",
                "choices": "list of 2..6 strings, each 1..120",
                "answer": "whole number, index of the correct choice starting at 0",
            },
            "timer": {
                "label": "string 1..80",
                "seconds": "whole number, 5..3600",
            },
        },
        "safety": (
            "Recipe strings are data only: they are HTML-escaped, cannot add "
            "links, images, styles or scripts, and the generated page makes "
            "no network requests."
        ),
    }
