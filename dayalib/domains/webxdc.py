"""The webxdc domain: a recipe becomes a complete .xdc mini-app.

A .xdc is a zip with an index.html and a manifest.toml, the format
DeltaChat mini-apps use (our intodo shared list is one). This pack
wraps the web domain: the recipe's page fields validate and generate
through the web pack unchanged, and the "app" object adds the manifest
fields. The result drops straight into a chat client's "publish mini
app" flow.

Safety model is the web domain's, plus: manifest strings are validated
against restrictive character sets before they are written as TOML, so
a recipe cannot inject TOML syntax. No icon support yet.

Determinism: zip entries have fixed timestamps, fixed order and fixed
permissions. Same recipe, same daya version, same bytes.
"""

import io
import re
import zipfile

from ..recipe import Checker, check_no_unknown_keys, check_string
from . import web

DOMAIN = "webxdc"
DESCRIPTION = (
    "A complete .xdc mini-app (zip: index.html + manifest.toml) for "
    "DeltaChat-style clients. Page content is the web domain's."
)

_TOP_KEYS = {"domain", "app", "title", "description", "theme", "sections"}
_APP_KEYS = {"name", "version", "source_code_url"}

_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
# TOML basic strings cannot hold these; reject instead of escaping.
_NAME_BAD = re.compile(r'["\\\x00-\x1f\x7f]')
_URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+(/[A-Za-z0-9._~/?%&=+-]*)?$")

_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def validate(recipe):
    """Return (model, errors): {"app": {...}, "page": <web model>}."""
    check = Checker()

    check_no_unknown_keys(check, recipe, _TOP_KEYS, "recipe")

    app = recipe.get("app")
    app_model = {}
    if not isinstance(app, dict):
        check.fail("app", "must be an object")
    else:
        check_no_unknown_keys(check, app, _APP_KEYS, "app")
        name = check_string(check, app.get("name"), "app.name", 1, 50)
        if name is not None:
            if _NAME_BAD.search(name):
                check.fail(
                    "app.name",
                    'cannot contain quotes, backslashes or control characters',
                )
            else:
                app_model["name"] = name
        version = app.get("version")
        if not isinstance(version, str) or not _VERSION_RE.match(version):
            check.fail("app.version", 'must be a version like "1.2.0"')
        else:
            app_model["version"] = version
        if "source_code_url" in app:
            url = app.get("source_code_url")
            if not isinstance(url, str) or len(url) > 200 or not _URL_RE.match(url):
                check.fail(
                    "app.source_code_url",
                    "must be a simple https:// URL (host plus optional path)",
                )
            else:
                app_model["source_code_url"] = url

    inner = {"domain": "web"}
    for key in ("title", "description", "theme", "sections"):
        if key in recipe:
            inner[key] = recipe[key]
    page_model, page_errors = web.validate(inner)
    check.errors.extend(page_errors)

    model = {"app": app_model, "page": page_model}
    return model, check.errors


def _manifest(app):
    lines = [
        'version = "{}"'.format(app["version"]),
        'name = "{}"'.format(app["name"]),
    ]
    if app.get("source_code_url"):
        lines.append('source_code_url = "{}"'.format(app["source_code_url"]))
    return "\n".join(lines) + "\n"


def generate(model):
    """Render a validated model as the bytes of a .xdc zip."""
    page_text = web.generate(model["page"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in (
            ("index.html", page_text),
            ("manifest.toml", _manifest(model["app"])),
        ):
            info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            zf.writestr(info, text.encode("utf-8"))
    return buf.getvalue()


def self_check(payload, model):
    """Sanity-check generated .xdc bytes before they are written."""
    problems = []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = zf.namelist()
            if names != ["index.html", "manifest.toml"]:
                problems.append("zip entries mismatch: {!r}".format(names))
            else:
                page = zf.read("index.html").decode("utf-8")
                manifest = zf.read("manifest.toml").decode("utf-8")
    except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise ValueError("generated .xdc failed self-check: {}".format(exc))
    if not problems:
        try:
            web.self_check(page, model["page"])
        except ValueError as exc:
            problems.append("inner page: {}".format(exc))
        for needle in (
            'version = "{}"'.format(model["app"]["version"]),
            'name = "{}"'.format(model["app"]["name"]),
        ):
            if needle not in manifest:
                problems.append("manifest missing {}".format(needle))
        if model["app"].get("source_code_url"):
            if model["app"]["source_code_url"] not in manifest:
                problems.append("manifest missing source_code_url")
    if problems:
        raise ValueError("generated .xdc failed self-check: " + "; ".join(problems))


def schema():
    """A plain-JSON description of the webxdc recipe format."""
    return {
        "domain": "webxdc",
        "description": DESCRIPTION,
        "fields": {
            "domain": 'the string "webxdc"',
            "app": {
                "name": 'string 1..50, shown in the chat client; no quotes, backslashes or control characters',
                "version": '"x.y.z", three numbers',
                "source_code_url": "optional https:// URL, host plus optional path",
            },
            "page fields": "title, description, theme, sections: exactly the web domain's",
        },
        "output": (
            "A .xdc zip holding index.html (the generated page) and "
            "manifest.toml. No icon yet. The app works standalone and inside "
            "a chat client; state stays on the device (no webxdc sync yet)."
        ),
        "safety": (
            "Page safety is the web domain's. Manifest strings are "
            "character-restricted so a recipe cannot inject TOML."
        ),
    }
