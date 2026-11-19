"""Turn a short plain-text description into a valid daya recipe.

This is a bounded, rule-based parser, not a language model: a fixed set
of documented phrasings is recognized, anything else is reported as not
understood, and the same input text always produces the same recipe
(deterministic, like everything else daya emits). No network calls, no
external services, no cost.

The parser only ever emits recipes for the "web" domain, and every
emitted recipe is run through that domain's own validate() before it
reaches the caller, so a description can never smuggle in a recipe the
normal validation would reject.

Supported phrasings (case-insensitive), one sentence each:

  App identity
    "... called NAME" / "... named NAME" / "... titled NAME"   title
    "description: TEXT" / "described as TEXT"                  description
    any of the accent color names (indigo, blue, ...)          theme

  Sections (one per sentence, split on ".", ";" or newlines)
    "a 25 minute timer for focus" / "pomodoro" / "countdown of 90 seconds"
    "a counter" / "a counter for push ups"
    "a todo list" / "task list" / "errands with items: buy rice, call ana"
    "a list: one, two and three" / "a list of apples, pears"
    "text: some intro words" / "a note that says hello"

Anything that does not match is listed in the notes as not understood,
and a description with no recognized sections is rejected with the list
of supported phrasings instead of guessing.
"""

import re

from .domains import web

# Longest strings first so "shopping list" wins over "list".
_TODO_RE = re.compile(
    r"(?:a |an |my |another )?(to-?do(?: list)?|task list|errands?|shopping list"
    r"|grocer(?:y|ies) list|editable list|checklist to edit)\b"
    r"(?:\s+(?:with|containing)\s+(?:items?\s*)?:?\s*(.+))?$",
    re.IGNORECASE,
)
_LIST_RE = re.compile(
    r"(?:a |an )?(?:check)?list(?:\s+of)?\s*:?\s+(.+)$", re.IGNORECASE
)
_COUNTER_RE = re.compile(
    r"(?:a |an )?counter(?:\s+(?:for|labeled|called)\s+(.+))?$", re.IGNORECASE
)
_TIMER_A_RE = re.compile(
    r"(?:a |an )?(\d+)\s*(second|minute|hour)s?\s+(timer|countdown)"
    r"(?:\s+(?:for|labeled|called)\s+(.+))?$",
    re.IGNORECASE,
)
_TIMER_B_RE = re.compile(
    r"(timer|countdown)(?:\s+(?:of|for))?\s+(\d+)\s*(second|minute|hour)s?"
    r"(?:\s+(?:for|labeled|called)\s+(.+))?$",
    re.IGNORECASE,
)
_POMODORO_RE = re.compile(r"(?:a )?(pomodoro|focus timer)\b\.?$", re.IGNORECASE)
_TEXT_RE = re.compile(
    r"(?:a |an )?(text|note|intro|about)(?:\s+(?:that says|saying))?"
    r"\s*:?\s*(.+)$",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(
    r"(?:called|named|titled)\s+(\"[^\"]+\"|'[^']+'|[^,.]+?)"
    r"\s*(?=,|\.|$)",
    re.IGNORECASE,
)
_DESCRIPTION_RE = re.compile(
    r"(?:description|tagline)\s*[:=]\s*(.+)$|described as\s+(.+)$", re.IGNORECASE
)
_UNITS = {"second": 1, "minute": 60, "hour": 3600}
_MAX_ITEM_LEN = 200


class DescribeError(Exception):
    """The description could not be turned into a recipe at all."""


def _strip_quotes(text):
    text = text.strip()
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
        text = text[1:-1].strip()
    return text


def _split_items(text, notes):
    parts = re.split(r",|\band\b", text)
    items = []
    for part in parts:
        item = _strip_quotes(part)
        if not item:
            continue
        if len(item) > _MAX_ITEM_LEN:
            notes.append(
                "item {!r}... is over {} characters; truncated".format(
                    item[:20], _MAX_ITEM_LEN
                )
            )
            item = item[:_MAX_ITEM_LEN]
        items.append(item)
    if len(items) > web.MAX_LIST_ITEMS:
        notes.append(
            "only the first {} items were kept".format(web.MAX_LIST_ITEMS)
        )
        items = items[: web.MAX_LIST_ITEMS]
    return items


def _slug(title, suffix, taken):
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "app"
    base = base[:24].strip("-")
    key = "{}-{}".format(base, suffix)[:32].strip("-")
    n = 2
    while key in taken:
        key = "{}-{}-{}".format(base, suffix, n)[:32].strip("-")
        n += 1
    taken.add(key)
    return key


def _timer_section(value, unit, label, notes):
    seconds = value * _UNITS[unit.lower()]
    if seconds > 3600:
        notes.append(
            "timer of {} {}s is over the 3600 second limit; capped".format(
                value, unit.lower()
            )
        )
        seconds = 3600
    if seconds < 5:
        notes.append(
            "timer of {} {}s is under the 5 second minimum; raised to 5".format(
                value, unit.lower()
            )
        )
        seconds = 5
    label = _strip_quotes(label or "{} timer".format(unit.capitalize()))[:80]
    return {"type": "timer", "label": label, "seconds": seconds}


def _parse_section(sentence, title, taken_keys, notes):
    """Match one sentence to one section, or return None."""
    match = _TIMER_A_RE.match(sentence)
    if match:
        return _timer_section(int(match.group(1)), match.group(2), match.group(4), notes)
    match = _TIMER_B_RE.match(sentence)
    if match:
        return _timer_section(int(match.group(2)), match.group(3), match.group(4), notes)
    match = _POMODORO_RE.match(sentence)
    if match:
        notes.append("no duration given for the pomodoro; used 25 minutes")
        return {"type": "timer", "label": "Focus", "seconds": 25 * 60}
    match = _COUNTER_RE.match(sentence)
    if match:
        label = _strip_quotes(match.group(1) or "Count")[:80]
        return {"type": "counter", "label": label}
    match = _TODO_RE.match(sentence)
    if match:
        section = {
            "type": "todo",
            "heading": match.group(1).strip().capitalize()[:80],
            "storage_key": _slug(title, "todo", taken_keys),
        }
        if match.group(2):
            section["items"] = _split_items(match.group(2), notes)
        return section
    match = _LIST_RE.match(sentence)
    if match:
        items = _split_items(match.group(1), notes)
        if items:
            return {"type": "list", "items": items}
        notes.append("a list needs at least one item; ignored {!r}".format(sentence))
        return None
    match = _TEXT_RE.match(sentence)
    if match:
        body = _strip_quotes(match.group(2))
        if len(body) > 2000:
            notes.append("text section is over 2000 characters; truncated")
            body = body[:2000]
        heading = {"text": "Text", "note": "Note", "intro": "Intro", "about": "About"}[
            match.group(1).lower()
        ]
        return {"type": "text", "heading": heading, "body": body}
    return None


def describe(text):
    """Parse a description. Return (recipe, notes); raise DescribeError."""
    if not isinstance(text, str) or not text.strip():
        raise DescribeError("the description is empty")
    if len(text) > 8000:
        raise DescribeError(
            "the description is too long (limit 8000 characters); "
            "describe the app in a few sentences"
        )

    notes = []
    title = None
    description = None
    accent = None
    leftovers = []

    for sentence in re.split(r"[.\n;]+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        match = _TITLE_RE.search(sentence)
        if match and title is None:
            title = _strip_quotes(match.group(1))[:80]
            sentence = (sentence[: match.start()] + " " + sentence[match.end() :]).strip(" ,")
            if not sentence:
                continue
        for name in sorted(web.ACCENTS):
            if re.search(r"\b{}\b".format(name), sentence, re.IGNORECASE):
                if accent is None:
                    accent = name
                    sentence = re.sub(
                        r"\b{}\b".format(name), "", sentence, count=1,
                        flags=re.IGNORECASE,
                    ).strip()
                break
        match = _DESCRIPTION_RE.search(sentence)
        if match and description is None:
            description = _strip_quotes(match.group(1) or match.group(2)).strip(" ,")[:280]
            sentence = (sentence[: match.start()] + " " + sentence[match.end() :]).strip(" ,")
            if not sentence:
                continue
        sentence = re.sub(r"\s*,\s*", ", ", sentence).strip(" ,")
        if sentence:
            leftovers.append(sentence)

    if title is None:
        title = "My app"
        notes.append("no name found (try: called \"Errands\"); used {!r}".format(title))

    taken_keys = set()
    sections = []
    for sentence in leftovers:
        section = _parse_section(sentence, title, taken_keys, notes)
        if section is None:
            notes.append("not understood, ignored: {!r}".format(sentence))
        else:
            sections.append(section)

    if not sections:
        raise DescribeError(
            "no recognizable sections. Supported phrasings: "
            '"a 25 minute timer for X", "pomodoro", "a counter for X", '
            '"a todo list with items: a, b and c", "a list: a, b", '
            '"text: some words". Add a name with: called "My app".'
        )

    recipe = {"domain": "web", "title": title, "sections": sections}
    if description is not None:
        recipe["description"] = description
    if accent is not None:
        recipe["theme"] = {"accent": accent}

    model, errors = web.validate(recipe)
    if errors:
        raise DescribeError(
            "internal error: parsed recipe failed validation: {}".format(
                "; ".join(errors)
            )
        )
    # Emit exactly the validated model, so nothing unvalidated reaches disk.
    recipe = {"domain": "web", "title": model["title"], "sections": model["sections"]}
    if "description" in model:
        recipe["description"] = model["description"]
    recipe["theme"] = {"accent": model["accent"]}
    return recipe, notes
