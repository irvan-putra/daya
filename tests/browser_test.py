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
    ],
}

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
    harness = page.replace("</body>", "<script>\n{}\n</script>\n</body>".format(DRIVER))

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
