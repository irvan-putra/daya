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
