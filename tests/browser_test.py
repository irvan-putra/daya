#!/usr/bin/env python3
"""Live-browser interaction tests for daya's web domain.

Builds a fixture page, appends a click-driving test script, runs it in
headless Chrome with virtual time (timers run fast), and checks the
results the page reports. Not part of the unittest suite; run directly:

    python3 tests/browser_test.py

Requires a Chrome/Chromium binary. Exits 0 when every check passes.
"""

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dayalib.domains import web

FIXTURE = {
    "domain": "web",
    "title": "browser fixture",
    "sections": [
        {"type": "counter", "label": "alpha"},
        {"type": "counter", "label": "beta", "start": 42},
        {
            "type": "quiz",
            "question": "pick second",
            "choices": ["wrong", "right"],
            "answer": 1,
        },
        {
            "type": "quiz",
            "question": "pick wrong",
            "choices": ["a", "b", "correct"],
            "answer": 2,
        },
        {"type": "timer", "label": "short", "seconds": 5},
        {
            "type": "todo",
            "heading": "errands",
            "storage_key": "daya-test-a",
            "items": ["seed item"],
        },
        {"type": "todo", "storage_key": "daya-test-b"},
        {"type": "todo", "storage_key": "daya-test-c"},
    ],
}

# Runs before the page's own script: one storage key is pre-seeded so the
# load path is tested, the other is left empty so the seed-item path is.
# daya-test-b carries a legacy archived entry (a bare string, the 0.2.0/0.3.0
# format) to check old stored data still loads.
# daya-test-c is a full list (200 items) with one archived entry, for the
# restore-at-capacity data-loss regression.
SEEDER = r"""
window.localStorage.clear();
window.localStorage.setItem(
  "daya-test-b",
  JSON.stringify({
    items: [
      { text: "stored one", done: true },
      { text: "stored two", done: false }
    ],
    archived: ["old one"]
  })
);
var bigItems = [];
for (var i = 0; i < 200; i++) {
  bigItems.push({ text: "bulk " + i, done: false });
}
window.localStorage.setItem(
  "daya-test-c",
  JSON.stringify({ items: bigItems, archived: [{ text: "archived one", done: true }] })
);
"""

DRIVER = r"""
(function () {
  var out = [];
  function ok(name, cond, detail) {
    out.push((cond ? "PASS " : "FAIL ") + name + (cond ? "" : " :: got " + detail));
  }
  function txt(el) { return el ? el.textContent : "<missing>"; }

  var counters = document.querySelectorAll(".daya-counter");
  var c0 = counters[0], c1 = counters[1];
  var quizzes = document.querySelectorAll(".daya-quiz");
  var q0 = quizzes[0], q1 = quizzes[1];
  var timer = document.querySelector(".daya-timer");
  var tbtn = timer.querySelector(".daya-timer-btn");
  var tdisplay = timer.querySelector(".daya-timer-display");
  var treset = timer.querySelector(".daya-timer-reset");

  try {
    c0.querySelector(".daya-counter-btn").click();
    c0.querySelector(".daya-counter-btn").click();
    c0.querySelector(".daya-counter-btn").click();
    ok("counter from 0: 3 clicks -> 3", txt(c0.querySelector(".daya-counter-value")) === "3",
       txt(c0.querySelector(".daya-counter-value")));
    c1.querySelector(".daya-counter-btn").click();
    ok("counter from 42: 1 click -> 43", txt(c1.querySelector(".daya-counter-value")) === "43",
       txt(c1.querySelector(".daya-counter-value")));

    q0.querySelector('[data-choice="1"]').click();
    ok("quiz correct answer says Correct.", txt(q0.querySelector(".daya-quiz-result")) === "Correct.",
       txt(q0.querySelector(".daya-quiz-result")));
    ok("quiz correct has good style",
       q0.querySelector(".daya-quiz-result").getAttribute("class").indexOf("daya-good") !== -1,
       q0.querySelector(".daya-quiz-result").getAttribute("class"));
    ok("quiz answered disables all choices",
       Array.prototype.every.call(q0.querySelectorAll(".daya-choice"), function (b) { return b.disabled; }),
       "not all disabled");

    q1.querySelector('[data-choice="0"]').click();
    ok("quiz wrong answer says Not quite",
       txt(q1.querySelector(".daya-quiz-result")).indexOf("Not quite") === 0,
       txt(q1.querySelector(".daya-quiz-result")));
    ok("quiz wrong marks the right answer",
       q1.querySelector('[data-choice="2"]').classList.contains("daya-answer"), "not marked");

    ok("timer initial display 00:05", txt(tdisplay) === "00:05", txt(tdisplay));
    ok("timer reset starts hidden", treset.hidden === true, "visible");
    tbtn.click();
    ok("timer start -> button Pause", txt(tbtn) === "Pause", txt(tbtn));
    ok("timer start shows reset", treset.hidden === false, "hidden");
  } catch (e) {
    out.push("FAIL exception " + e.message);
  }

  try {
    var todos = document.querySelectorAll(".daya-todo");
    var ta = todos[0], tb = todos[1];
    var aItems = function () {
      return ta.querySelectorAll(".daya-todo-items li");
    };
    var aTexts = function () {
      return Array.prototype.map.call(aItems(), function (li) {
        return li.querySelector(".daya-todo-text").textContent;
      }).join(",");
    };

    var bRows = tb.querySelectorAll(".daya-todo-items li");
    ok("todo B loads stored items", bRows.length === 2, bRows.length);
    ok("todo B stored done state kept",
       bRows[0].getAttribute("class") === "daya-done", bRows[0].getAttribute("class"));
    ok("todo B done row offers Undo",
       txt(bRows[0].querySelector(".daya-todo-toggle")) === "Undo",
       txt(bRows[0].querySelector(".daya-todo-toggle")));
    ok("todo B archived count shown",
       txt(tb.querySelector(".daya-todo-archived-count")) === "1",
       txt(tb.querySelector(".daya-todo-archived-count")));
    ok("todo B archived list unhidden",
       tb.querySelector(".daya-todo-archived").hidden === false, "hidden");
    ok("todo B legacy string archive entry renders",
       txt(tb.querySelector(".daya-todo-archived-items .daya-todo-text")) === "old one",
       txt(tb.querySelector(".daya-todo-archived-items .daya-todo-text")));

    var bTexts = function () {
      return Array.prototype.map.call(
        tb.querySelectorAll(".daya-todo-items .daya-todo-text"),
        function (s) { return s.textContent; }
      ).join(",");
    };
    bRows[0].querySelector(".daya-todo-archive").click();
    ok("todo B archive moves done item out",
       bTexts() === "stored two", bTexts());
    tb.querySelectorAll(".daya-todo-archived-items li")[1]
      .querySelector(".daya-todo-unarchive").click();
    var bRestored = tb.querySelectorAll(".daya-todo-items li");
    ok("todo B restored item keeps done state",
       bRestored.length === 2 &&
         bRestored[1].getAttribute("class") === "daya-done" &&
         txt(bRestored[1].querySelector(".daya-todo-text")) === "stored one",
       bTexts());
    tb.querySelector(".daya-todo-archived-items .daya-todo-unarchive").click();
    ok("todo B legacy archived string restores as item",
       bTexts().indexOf("old one") !== -1, bTexts());

    var tc = todos[2];
    ok("todo C full list loads", 
       tc.querySelectorAll(".daya-todo-items li").length === 200,
       tc.querySelectorAll(".daya-todo-items li").length);
    tc.querySelector(".daya-todo-unarchive").click();
    ok("todo C restore at capacity keeps archived entry",
       txt(tc.querySelector(".daya-todo-archived-count")) === "1",
       txt(tc.querySelector(".daya-todo-archived-count")));
    ok("todo C active list stays at capacity",
       tc.querySelectorAll(".daya-todo-items li").length === 200,
       tc.querySelectorAll(".daya-todo-items li").length);
    var cSaved = JSON.parse(window.localStorage.getItem("daya-test-c"));
    ok("todo C archived entry still in storage",
       cSaved && cSaved.archived.length === 1 &&
         cSaved.archived[0].text === "archived one",
       window.localStorage.getItem("daya-test-c").slice(-120));

    ok("todo A starts from seed item", aTexts() === "seed item", aTexts());
    ok("todo A archived area hidden while empty",
       ta.querySelector(".daya-todo-archived").hidden === true, "visible");

    var input = ta.querySelector(".daya-todo-add input");
    input.value = "  buy milk  ";
    ta.querySelector('.daya-todo-add button[type="submit"]').click();
    ok("todo add appends trimmed item", aTexts() === "seed item,buy milk", aTexts());
    ok("todo add clears input", input.value === "", input.value);

    aItems()[0].querySelector(".daya-todo-toggle").click();
    ok("todo toggle marks done",
       aItems()[0].getAttribute("class") === "daya-done",
       aItems()[0].getAttribute("class"));
    aItems()[0].querySelector(".daya-todo-toggle").click();
    ok("todo toggle again undoes",
       aItems()[0].getAttribute("class") !== "daya-done",
       aItems()[0].getAttribute("class"));

    aItems()[0].querySelector(".daya-todo-archive").click();
    ok("todo archive removes from list", aTexts() === "buy milk", aTexts());
    ok("todo archive grows archived count",
       txt(ta.querySelector(".daya-todo-archived-count")) === "1",
       txt(ta.querySelector(".daya-todo-archived-count")));
    ok("todo archived row keeps text",
       txt(ta.querySelector(".daya-todo-archived-items .daya-todo-text")) === "seed item",
       txt(ta.querySelector(".daya-todo-archived-items .daya-todo-text")));

    ta.querySelector(".daya-todo-unarchive").click();
    ok("todo restore returns item", aTexts() === "buy milk,seed item", aTexts());
    ok("todo restore empties archive",
       ta.querySelector(".daya-todo-archived").hidden === true, "visible");

    var saved = JSON.parse(window.localStorage.getItem("daya-test-a"));
    ok("todo state saved to storage",
       saved && saved.items.length === 2 && saved.archived.length === 0 &&
       saved.items[0].text === "buy milk" && saved.items[1].text === "seed item",
       window.localStorage.getItem("daya-test-a"));

    input.value = "   ";
    ta.querySelector('.daya-todo-add button[type="submit"]').click();
    ok("todo blank add ignored", aTexts() === "buy milk,seed item", aTexts());
  } catch (e) {
    out.push("FAIL exception " + e.message);
  }

  setTimeout(function () {
    try {
      ok("timer counts down to 00:03", txt(tdisplay) === "00:03", txt(tdisplay));
      tbtn.click();
      ok("timer pause -> button Resume", txt(tbtn) === "Resume", txt(tbtn));
    } catch (e) { out.push("FAIL exception " + e.message); }
    setTimeout(function () {
      try {
        ok("timer paused value frozen", txt(tdisplay) === "00:03", txt(tdisplay));
        tbtn.click();
        ok("timer resume -> button Pause", txt(tbtn) === "Pause", txt(tbtn));
      } catch (e) { out.push("FAIL exception " + e.message); }
      setTimeout(function () {
        try {
          ok("timer expires to Done", txt(tdisplay) === "Done", txt(tdisplay));
          ok("timer expiry restores Start", txt(tbtn) === "Start", txt(tbtn));
          ok("timer expiry hides reset", treset.hidden === true, "visible");
          tbtn.click();
          ok("timer restart runs again", txt(tbtn) === "Pause", txt(tbtn));
          treset.click();
          ok("timer reset restores 00:05", txt(tdisplay) === "00:05", txt(tdisplay));
          ok("timer reset restores Start", txt(tbtn) === "Start", txt(tbtn));
          ok("timer reset hides reset", treset.hidden === true, "visible");
        } catch (e) { out.push("FAIL exception " + e.message); }
        finish();
      }, 3600);
    }, 1300);
  }, 2100);

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


def find_chrome():
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def main():
    chrome = find_chrome()
    if not chrome:
        print("no Chrome/Chromium found; cannot run browser tests", file=sys.stderr)
        return 2

    model, errors = web.validate(FIXTURE)
    if errors:
        print("fixture recipe invalid: {}".format(errors), file=sys.stderr)
        return 2
    page = web.generate(model)
    harness = page.replace(
        "<body>", "<body>\n<script>\n{}\n</script>".format(SEEDER), 1
    ).replace("</body>", "<script>\n{}\n</script>\n</body>".format(DRIVER))

    workdir = tempfile.mkdtemp()
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
