"""The tindak-view domain: a recipe becomes one view page for the tindak
shared-list webxdc app.

PROPOSAL STAGE: no app uses this output yet. The page is generated
against a controller contract that the tindak owner authors and owns:
a headless controller script (contract name js/itd-controller.js,
global window.ItdController) shared by the existing UI and generated
views, exposing:

  snapshot()          -> {status: "loading"|"ready"|"error", items: [...],
                          error: string|null}
                         items are immutable: {id, title, note, due, done}
  subscribe(fn)       -> calls fn on every state change; returns
                         an unsubscribe function
  addTitle(title)     -> commands; the ONLY way the view writes
  toggleDone(id)      ->

The generated page holds no state: no storage, no transport, no webxdc
listener, no MergeDoc access. self_check asserts "localStorage" and
"webxdc" never appear in the output. Ordering is whatever the snapshot
carries (the app's own ordering); the view only filters.

Safety model: recipe strings are escaped data; the only JavaScript is
the fixed template below; the only link is the fixed constant
href="index.html" (the app's full view).
"""

import html

from .. import __version__
from ..recipe import Checker, check_no_unknown_keys, check_string
from . import web

DOMAIN = "tindak-view"
DESCRIPTION = (
    "One focus-view page for the tindak webxdc shared list, rendered "
    "against the owner's headless controller. Proposal stage."
)

_TOP_KEYS = {"domain", "title", "description", "theme"}

# Contract constants, pending the tindak owner's confirmation.
CONTROLLER_SRC = "js/itd-controller.js"
CONTROLLER_GLOBAL = "ItdController"
FULL_VIEW_HREF = "index.html"


def validate(recipe):
    """Return (model, errors). model is cleaned input safe to generate from."""
    check = Checker()
    model = {}

    check_no_unknown_keys(check, recipe, _TOP_KEYS, "recipe")

    title = check_string(check, recipe.get("title"), "title", 1, 80)
    if title is not None:
        model["title"] = title

    if "description" in recipe:
        description = check_string(check, recipe.get("description"), "description", 1, 280)
        if description is not None:
            model["description"] = description

    accent = web.DEFAULT_ACCENT
    theme = recipe.get("theme")
    if theme is not None:
        if not isinstance(theme, dict):
            check.fail("theme", "must be an object")
        else:
            check_no_unknown_keys(check, theme, {"accent"}, "theme")
            if "accent" in theme:
                if theme["accent"] not in web.ACCENTS:
                    check.fail(
                        "theme.accent",
                        "must be one of: {}".format(", ".join(sorted(web.ACCENTS))),
                    )
                else:
                    accent = theme["accent"]
    model["accent"] = accent

    return model, check.errors


def _esc(text):
    return html.escape(text, quote=True)


_CSS_EXTRA = """
.daya-view-status { color: #52606d; text-align: center; padding: 1rem 0; }
.daya-view-items { list-style: none; padding-left: 0; }
.daya-view-item { display: flex; align-items: flex-start; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #f0f2f5; }
.daya-view-check { background: #fff; color: var(--accent); border: 1px solid var(--accent); padding: 0.2rem 0.55rem; }
.daya-view-body { flex: 1; min-width: 0; }
.daya-view-title { overflow-wrap: anywhere; }
.daya-view-note, .daya-view-due { color: #52606d; font-size: 0.85rem; margin-top: 0.15rem; overflow-wrap: anywhere; }
.daya-view-full { display: inline-block; margin-top: 1rem; color: var(--accent); }
""".strip()

# The view's whole script. It renders from controller snapshots and sends
# commands; it stores nothing and talks to no transport.
_JS = """
"use strict";
(function () {
  var C = window.__CONTROLLER_GLOBAL__;
  var statusEl = document.getElementById("daya-view-status");
  var listEl = document.getElementById("daya-view-items");
  var form = document.getElementById("daya-view-add");
  var input = document.getElementById("daya-view-title");

  function render() {
    var snap = C.snapshot();
    listEl.textContent = "";
    if (snap.status !== "ready") {
      statusEl.hidden = false;
      statusEl.textContent =
        snap.status === "error"
          ? "List unavailable" + (snap.error ? ": " + snap.error : "")
          : "Loading...";
      return;
    }
    statusEl.hidden = true;
    var shown = 0;
    snap.items.forEach(function (item) {
      if (item.done) {
        return;
      }
      shown += 1;
      var li = document.createElement("li");
      li.className = "daya-view-item";
      var check = document.createElement("button");
      check.type = "button";
      check.className = "daya-view-check";
      check.textContent = "Done";
      check.setAttribute("data-item-id", item.id);
      var body = document.createElement("div");
      body.className = "daya-view-body";
      var title = document.createElement("div");
      title.className = "daya-view-title";
      title.textContent = item.title;
      body.appendChild(title);
      if (item.note) {
        var note = document.createElement("div");
        note.className = "daya-view-note";
        note.textContent = item.note;
        body.appendChild(note);
      }
      if (item.due) {
        var due = document.createElement("div");
        due.className = "daya-view-due";
        due.textContent = "Due: " + item.due;
        body.appendChild(due);
      }
      li.appendChild(check);
      li.appendChild(body);
      listEl.appendChild(li);
    });
    if (shown === 0) {
      statusEl.hidden = false;
      statusEl.textContent = "Nothing unfinished. Nice.";
    }
  }

  document.addEventListener("click", function (event) {
    var btn = event.target.closest("button.daya-view-check");
    if (!btn) {
      return;
    }
    C.toggleDone(btn.getAttribute("data-item-id"));
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text) {
      return;
    }
    C.addTitle(text);
    input.value = "";
  });

  C.subscribe(render);
  render();
})();
""".strip()


def generate(model):
    """Render a validated model as one self-contained view page."""
    accent = web.ACCENTS[model["accent"]]
    script = _JS.replace("__CONTROLLER_GLOBAL__", CONTROLLER_GLOBAL)
    out = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="generator" content="daya {}">'.format(__version__),
        "<title>{}</title>".format(_esc(model["title"])),
        "<style>",
        (web._CSS + "\n" + _CSS_EXTRA).replace("__ACCENT__", accent),
        "</style>",
        "</head>",
        "<body>",
        "<main>",
        "<h1>{}</h1>".format(_esc(model["title"])),
    ]
    if model.get("description"):
        out.append('<p class="lede">{}</p>'.format(
            "<br>\n".join(_esc(line) for line in model["description"].split("\n"))
        ))
    out.extend(
        [
            '<form class="daya-todo-add" id="daya-view-add">',
            '<input type="text" id="daya-view-title" maxlength="200" required'
            ' autocomplete="off" aria-label="New item">',
            '<button type="submit">Add</button>',
            "</form>",
            '<p class="daya-view-status" id="daya-view-status">Loading...</p>',
            '<ul class="daya-view-items" id="daya-view-items"></ul>',
            '<a class="daya-view-full" href="{}">Full list</a>'.format(FULL_VIEW_HREF),
            "</main>",
            '<script src="{}"></script>'.format(CONTROLLER_SRC),
            "<script>",
            script,
            "</script>",
            "</body>",
            "</html>",
            "",
        ]
    )
    return "\n".join(out)


def self_check(page, model):
    """Sanity-check generated output before it is written to disk."""
    problems = []
    if not page.startswith("<!DOCTYPE html>"):
        problems.append("missing doctype")
    if not page.rstrip().endswith("</html>"):
        problems.append("missing closing </html>")
    if page.count("<script") != 2:
        problems.append("expected the controller tag plus one inline template")
    for needle in (_esc(model["title"]), 'href="{}"'.format(FULL_VIEW_HREF),
                   'src="{}"'.format(CONTROLLER_SRC)):
        if needle not in page:
            problems.append("missing expected content: {!r}".format(needle[:40]))
    if model.get("description") and _esc(model["description"].split("\n")[0]) not in page:
        problems.append("escaped description missing")
    # Contract guard: generated views hold no state and touch no transport.
    for banned in ("localStorage", "webxdc", "MergeDoc", "sendUpdate"):
        if banned in page:
            problems.append("forbidden reference in view: {}".format(banned))
    if problems:
        raise ValueError("generated view failed self-check: " + "; ".join(problems))


def schema():
    """A plain-JSON description of the tindak-view recipe format."""
    return {
        "domain": "tindak-view",
        "description": DESCRIPTION,
        "fields": {
            "domain": 'the string "tindak-view"',
            "title": "string, 1..80 characters",
            "description": "optional string, 1..280 characters",
            "theme": {"accent": "optional, one of: " + ", ".join(sorted(web.ACCENTS))},
        },
        "view": (
            "Fixed focus contract: unfinished items (title, note, due), "
            "add-by-title and mark-done commands, a fixed link to the app's "
            "full view. Snapshot ordering is the app's own."
        ),
        "controller contract": {
            "script": CONTROLLER_SRC + " (owner-authored)",
            "global": "window." + CONTROLLER_GLOBAL,
            "methods": ["snapshot()", "subscribe(fn) -> unsubscribe",
                        "addTitle(title)", "toggleDone(id)"],
        },
        "safety": (
            "The view holds no state: self_check rejects any output "
            "referencing localStorage, webxdc, MergeDoc or sendUpdate."
        ),
    }
