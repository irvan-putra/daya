#!/usr/bin/env python3
"""Live-browser parity tests for the compose page (docs/compose.html).

Replays tests/compose_fixtures.json - produced by the Python side
(tests/generate_compose_fixtures.py) - against compose-core.js in
headless Chrome, so the browser port of the deterministic parser and
the web validator must match the Python implementations exactly.

Also checks the compose page itself: it renders, the deterministic
route works end to end through the DOM, no model/CDN network request
happens on page load (the in-page model must load only on tap), and the
browser-AI route reports an availability status instead of assuming.

Not part of the unittest suite; run directly:

    python3 tests/browser_test_compose.py

Requires a Chrome/Chromium binary. Exits 0 when every check passes.
"""

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from browser_test_helpers import find_chrome  # noqa: E402

DRIVER = r"""
(function () {
  var out = [];
  function report(cond, name, detail) {
    out.push((cond ? "PASS " : "FAIL ") + name + (cond ? "" : " :: got " + detail));
  }

  function canon(value) {
    if (value === null || typeof value !== "object") return JSON.stringify(value);
    if (Array.isArray(value)) return "[" + value.map(canon).join(",") + "]";
    var keys = Object.keys(value).sort();
    return "{" + keys.map(function (k) { return JSON.stringify(k) + ":" + canon(value[k]); }).join(",") + "}";
  }

  var fixtures = JSON.parse(document.getElementById("fixtures").textContent);

  fixtures.describe_cases.forEach(function (c, i) {
    var name = "describe[" + i + "] " + JSON.stringify(c.input).slice(0, 50);
    try {
      var got = window.dayaCore.describe(c.input);
      if (c.error !== null) {
        report(false, name, "expected error " + JSON.stringify(c.error) + " but parsed");
      } else {
        report(canon(got.recipe) === canon(c.recipe), name,
          canon(got.recipe) + " expected " + canon(c.recipe));
      }
    } catch (err) {
      if (c.error === null) {
        report(false, name, "unexpected error " + err.message);
      } else {
        report(err.message === c.error, name,
          JSON.stringify(err.message) + " expected " + JSON.stringify(c.error));
      }
    }
  });

  fixtures.validate_cases.forEach(function (c, i) {
    var name = "validate[" + i + "]";
    var got = window.dayaCore.validateRecipe(c.recipe);
    report(JSON.stringify(got.errors) === JSON.stringify(c.errors), name,
      JSON.stringify(got.errors) + " expected " + JSON.stringify(c.errors));
  });

  /* Deterministic route through the real compose page DOM. */
  try {
    document.getElementById("description").value =
      'a 5 minute timer for tea, called "Tea"';
    document.getElementById("go").click();
    var text = document.getElementById("recipe-out").textContent;
    var parsed = JSON.parse(text);
    report(parsed.title === "Tea" &&
           parsed.sections[0].type === "timer" &&
           parsed.sections[0].seconds === 300 &&
           !document.getElementById("result-card").hidden,
           "compose page deterministic flow", text.slice(0, 120));
  } catch (e) {
    report(false, "compose page deterministic flow", e.message);
  }

  /* Classical engine behavior (engines live only in the browser port, so
     expectations are hand-written here rather than fixture-generated). */
  function canon(value) {
    if (value === null || typeof value !== "object") return JSON.stringify(value);
    if (Array.isArray(value)) return "[" + value.map(canon).join(",") + "]";
    var keys = Object.keys(value).sort();
    return "{" + keys.map(function (k) { return JSON.stringify(k) + ":" + canon(value[k]); }).join(",") + "}";
  }

  var engineCases = [
    { engine: "grammar", input: "twenty five minute timer for focus", check: function (r) {
      return r.sections[0].type === "timer" && r.sections[0].seconds === 1500 && r.sections[0].label === "Focus"; } },
    { engine: "grammar", input: "timer for tea of 10 minutes", check: function (r) {
      return r.sections[0].type === "timer" && r.sections[0].seconds === 600 && r.sections[0].label === "Tea"; } },
    { engine: "grammar", input: "a counter for push ups", check: function (r) {
      return r.sections[0].type === "counter" && r.sections[0].label === "push ups"; } },
    { engine: "grammar", input: "a todo list with items: rice, eggs", check: function (r) {
      return r.sections[0].type === "todo" && r.sections[0].items.length === 2; } },
    { engine: "template", input: "25 minute timre", check: function (r) {
      return r.sections[0].type === "timer" && r.sections[0].seconds === 1500; } },
    { engine: "template", input: "please make a counter for steps", check: function (r) {
      return r.sections[0].type === "counter" && r.sections[0].label === "steps"; } },
    { engine: "template", input: "shopping list with items rice, eggs and coffee", check: function (r) {
      return r.sections[0].type === "todo" && r.sections[0].items.length === 3; } },
    { engine: "bayes", input: "set a ten minute timer for study", check: function (r) {
      return r.sections[0].type === "timer" && r.sections[0].seconds === 600; } },
    { engine: "bayes", input: "track my pages", check: function (r) {
      return r.sections[0].type === "counter"; } },
    { engine: "auto", input: "a 25 minute timer for focus", check: function (r, out) {
      return out.engine === "rules" && r.sections[0].seconds === 1500; } },
    { engine: "auto", input: "twenty five minute timer", check: function (r, out) {
      return out.engine === "grammar" && r.sections[0].seconds === 1500; } },
    { engine: "auto", input: "25 minute timre", check: function (r, out) {
      return out.engine === "template" && r.sections[0].seconds === 1500; } }
  ];

  engineCases.forEach(function (c, i) {
    var name = "engine[" + i + "] " + c.engine + " " + JSON.stringify(c.input).slice(0, 45);
    try {
      var out = window.dayaEngines.run(c.engine, c.input);
      var v = window.dayaCore.validateRecipe(out.recipe);
      if (v.errors.length) {
        report(false, name, "output failed validation: " + v.errors.join("; "));
      } else {
        report(c.check(out.recipe, out), name, canon(out.recipe).slice(0, 160) + " engine=" + out.engine);
      }
    } catch (err) {
      report(false, name, "threw: " + err.message);
    }
  });

  /* Bayes must admit low confidence instead of guessing. */
  try {
    window.dayaEngines.run("bayes", "quantum blockchain synergy");
    report(false, "bayes low-confidence refusal", "parsed without error");
  } catch (err) {
    report(/confident|could not/.test(err.message), "bayes low-confidence refusal", err.message);
  }

  /* Auto cascade must list every method's failure when nothing matches. */
  try {
    window.dayaEngines.run("auto", "quantum blockchain synergy");
    report(false, "auto failure lists methods", "parsed without error");
  } catch (err) {
    report(err.message.indexOf("rules") !== -1 && err.message.indexOf("bayes") !== -1,
      "auto failure lists methods", err.message.slice(0, 160));
  }

  /* Engine picker through the page DOM. */
  try {
    document.getElementById("engine").value = "grammar";
    document.getElementById("description").value = "twenty five minute timer, called Tea";
    document.getElementById("go").click();
    var heading2 = document.getElementById("result-heading").textContent;
    var parsed2 = JSON.parse(document.getElementById("recipe-out").textContent);
    report(heading2.indexOf("grammar") !== -1 && parsed2.sections[0].seconds === 1500,
      "engine picker via DOM", heading2);
    document.getElementById("engine").value = "auto";
  } catch (e) {
    report(false, "engine picker via DOM", e.message);
  }

  /* No model/CDN network request may happen before the user taps load. */
  var resources = performance.getEntriesByType("resource").map(function (r) { return r.name; });
  var leaked = resources.filter(function (n) {
    return n.indexOf("huggingface") !== -1 || n.indexOf("jsdelivr") !== -1;
  });
  report(leaked.length === 0, "no model/CDN fetch on load", leaked.join(","));

  /* The browser-AI route must report a status, never silently assume. */
  var status = document.getElementById("browser-ai-status").textContent;
  report(status.trim().length > 20, "browser AI availability explained", status);

  var fails = out.filter(function (r) { return r.indexOf("FAIL") === 0; });
  var pre = document.createElement("pre");
  pre.id = "daya-test-results";
  pre.textContent = "DAYA-TEST " + (fails.length ? "FAILURES " + fails.length : "ALL PASS " + out.length) +
    "\n" + out.join("\n");
  document.body.appendChild(pre);
})();
"""


def main():
    chrome = find_chrome()
    if not chrome:
        print("no Chrome/Chromium found; cannot run browser tests", file=sys.stderr)
        return 2

    with open(os.path.join(ROOT, "tests", "compose_fixtures.json"), encoding="utf-8") as fh:
        fixtures = fh.read()
    with open(os.path.join(ROOT, "docs", "compose.html"), encoding="utf-8") as fh:
        page = fh.read()

    harness = page.replace(
        "</body>",
        '<script type="application/json" id="fixtures">' + fixtures + "</script>\n"
        "<script>\n" + DRIVER + "\n</script>\n</body>",
        1,
    )

    workdir = tempfile.mkdtemp()
    with open(os.path.join(ROOT, "docs", "compose-core.js"), encoding="utf-8") as src:
        core = src.read()
    with open(os.path.join(workdir, "compose-core.js"), "w", encoding="utf-8") as fh:
        fh.write(core)
    with open(os.path.join(ROOT, "docs", "compose-engines.js"), encoding="utf-8") as src:
        engines = src.read()
    with open(os.path.join(workdir, "compose-engines.js"), "w", encoding="utf-8") as fh:
        fh.write(engines)
    harness_path = os.path.join(workdir, "harness.html")
    with open(harness_path, "w", encoding="utf-8") as fh:
        fh.write(harness)

    result = subprocess.run(
        [
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--virtual-time-budget=9000",
            "--dump-dom",
            "file://" + harness_path,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    dom = result.stdout
    start = dom.find('<pre id="daya-test-results">')
    if start != -1:
        start = dom.find("DAYA-TEST ", start)
    end = dom.find("</pre>", start)
    if start == -1 or end == -1:
        print("browser test driver did not report; raw output follows", file=sys.stderr)
        print(dom[-3000:], file=sys.stderr)
        print(result.stderr[-1000:], file=sys.stderr)
        return 2
    report = dom[start:end]
    print(report)
    return 0 if "DAYA-TEST ALL PASS" in report else 1


if __name__ == "__main__":
    sys.exit(main())
