#!/usr/bin/env python3
"""Live-browser interaction tests for daya's tindak-view domain.

Builds a focus-view page, injects a MOCK controller (test-only double of
the owner-authored js/itd-controller.js contract: snapshot/subscribe/
addTitle/toggleDone), runs it in headless Chrome and checks the results
the page reports. Not part of the unittest suite; run directly:

    python3 tests/browser_test_view.py

Requires a Chrome/Chromium binary. Exits 0 when every check passes.
"""

import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dayalib.domains import tindak_view as view
from tests.browser_test import find_chrome

FIXTURE = {
    "domain": "tindak-view",
    "title": "Focus",
    "description": "Unfinished items only.",
}

# Test-only double of the controller contract. Starts "loading" and flips
# to "ready" after one tick so the loading path is exercised too.
MOCK = r"""
(function () {
  var items = [
    { id: "item-a", title: "finish report", note: "two pages", due: "2026-11-20", done: false },
    { id: "item-b", title: "already done chore", note: null, due: null, done: true },
    { id: "item-c", title: "sneaky <img src=x onerror=alert(1)>", note: null, due: null, done: false }
  ];
  var status = "loading";
  var listeners = [];
  function emit() { listeners.slice().forEach(function (fn) { fn(); }); }
  window.ItdController = {
    snapshot: function () {
      return { status: status, error: null, items: items.slice() };
    },
    subscribe: function (fn) {
      listeners.push(fn);
      return function () {
        listeners = listeners.filter(function (l) { return l !== fn; });
      };
    },
    addTitle: function (t) {
      items.push({ id: "item-new-" + items.length, title: t, note: null, due: null, done: false });
      emit();
    },
    toggleDone: function (id) {
      items = items.map(function (it) {
        return it.id === id ? { id: it.id, title: it.title, note: it.note, due: it.due, done: !it.done } : it;
      });
      emit();
    }
  };
  setTimeout(function () { status = "ready"; emit(); }, 0);
})();
"""

DRIVER = r"""
(function () {
  var out = [];
  function ok(name, cond, detail) {
    out.push((cond ? "PASS " : "FAIL ") + name + (cond ? "" : " :: got " + detail));
  }
  function txt(el) { return el ? el.textContent : "<missing>"; }
  function titles() {
    return Array.prototype.map.call(
      document.querySelectorAll(".daya-view-title"),
      function (el) { return el.textContent; }
    ).join(",");
  }

  try {
    ok("loading state shown before ready",
       txt(document.getElementById("daya-view-status")) === "Loading...",
       txt(document.getElementById("daya-view-status")));
  } catch (e) {
    out.push("FAIL exception " + e.message);
  }

  setTimeout(function () {
    try {
      ok("status hidden once ready",
         document.getElementById("daya-view-status").hidden === true, "visible");
      ok("unfinished items rendered",
         titles().indexOf("finish report") !== -1 &&
         titles().indexOf("sneaky") !== -1, titles());
      ok("done item hidden in focus view",
         titles().indexOf("already done chore") === -1, titles());
      ok("note shown",
         txt(document.querySelector(".daya-view-note")) === "two pages",
         txt(document.querySelector(".daya-view-note")));
      ok("due shown",
         txt(document.querySelector(".daya-view-due")) === "Due: 2026-11-20",
         txt(document.querySelector(".daya-view-due")));
      ok("recipe-injection title stays text (no img element)",
         document.querySelector(".daya-view-items img") === null, "img found");
      ok("full-view link present",
         document.querySelector('a.daya-view-full[href="index.html"]') !== null,
         "missing");

      document.getElementById("daya-view-title").value = "  buy milk  ";
      document.querySelector('#daya-view-add button[type="submit"]').click();
      ok("add goes through controller and re-renders",
         titles().indexOf("buy milk") !== -1, titles());
      ok("add clears input",
         document.getElementById("daya-view-title").value === "", "not cleared");

      document.getElementById("daya-view-title").value = "   ";
      var before = titles();
      document.querySelector('#daya-view-add button[type="submit"]').click();
      ok("blank add ignored", titles() === before, titles());

      var firstCheck = document.querySelector("button.daya-view-check");
      firstCheck.click();
      ok("toggle goes through controller; item leaves focus view",
         titles().indexOf("finish report") === -1, titles());
    } catch (e) {
      out.push("FAIL exception " + e.message);
    }
    finish();
  }, 50);

  function finish() {
    var fails = out.filter(function (r) { return r.indexOf("FAIL") === 0; });
    var pre = document.createElement("pre");
    pre.id = "daya-test-results";
    pre.textContent = "DAYA-TEST " + (fails.length ? "FAILURES " + fails.length : "ALL PASS " + out.length) +
      "\n" + out.join("\n");
    document.body.appendChild(pre);
  }
})();
"""


def main():
    chrome = find_chrome()
    if not chrome:
        print("no Chrome/Chromium found; cannot run browser tests", file=sys.stderr)
        return 2

    model, errors = view.validate(FIXTURE)
    if errors:
        print("fixture recipe invalid: {}".format(errors), file=sys.stderr)
        return 2
    page = view.generate(model)
    harness = page.replace(
        '<script src="js/itd-controller.js"></script>',
        "<script>\n{}\n</script>".format(MOCK),
    )
    harness = harness.replace(
        "</body>", "<script>\n{}\n</script>\n</body>".format(DRIVER)
    )

    workdir = tempfile.mkdtemp()
    harness_path = os.path.join(workdir, "harness-view.html")
    with open(harness_path, "w", encoding="utf-8") as fh:
        fh.write(harness)

    result = subprocess.run(
        [
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--virtual-time-budget=5000",
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
