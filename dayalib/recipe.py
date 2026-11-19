"""Recipe loading and validation helpers shared by every domain pack.

A recipe is a small JSON object. Validation collects every problem it
can find and reports each one with a dotted path, so a chatbot (or a
person) can fix everything in one pass instead of one error per run.
"""

import json

MAX_RECIPE_BYTES = 65536


class RecipeError(Exception):
    """The recipe file cannot be read or parsed at all."""


class Checker:
    """Collects validation problems with dotted paths."""

    def __init__(self):
        self.errors = []

    def fail(self, path, message):
        self.errors.append("{}: {}".format(path, message))


def load_recipe(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_RECIPE_BYTES + 1)
    except OSError as exc:
        raise RecipeError("cannot read {}: {}".format(path, exc.strerror or exc))
    if len(raw) > MAX_RECIPE_BYTES:
        raise RecipeError(
            "{}: recipe is too large (limit {} bytes)".format(path, MAX_RECIPE_BYTES)
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise RecipeError("{}: recipe must be UTF-8 text".format(path))
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RecipeError(
            "{}: not valid JSON (line {}, column {}): {}".format(
                path, exc.lineno, exc.colno, exc.msg
            )
        )
    if not isinstance(data, dict):
        raise RecipeError("{}: top level must be a JSON object".format(path))
    return data


def check_string(check, value, path, min_len, max_len):
    if not isinstance(value, str):
        check.fail(path, "must be a string")
        return None
    if not min_len <= len(value) <= max_len:
        check.fail(
            path,
            "must be {}..{} characters, got {}".format(min_len, max_len, len(value)),
        )
        return None
    return value


def check_int(check, value, path, min_v, max_v):
    if isinstance(value, bool) or not isinstance(value, int):
        check.fail(path, "must be a whole number")
        return None
    if not min_v <= value <= max_v:
        check.fail(path, "must be between {} and {}, got {}".format(min_v, max_v, value))
        return None
    return value


def check_no_unknown_keys(check, obj, allowed, path):
    for key in obj:
        if key not in allowed:
            check.fail(path, "unknown field {!r}".format(key))
