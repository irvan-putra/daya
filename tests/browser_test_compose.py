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
     expectations are written out here (AI-written) rather than fixture-generated). */
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

  /* Manual chatbot route: prompt builder content. */
  try {
    var pr = window.dayaCore.chatbotPrompt('a counter for steps, called "Steps"');
    report(pr.indexOf('"type":"timer"') !== -1 &&
           pr.indexOf('a counter for steps') !== -1 &&
           pr.indexOf("Example recipe") !== -1 &&
           pr.indexOf("no markdown fences") !== -1,
           "chatbot prompt content", pr.slice(0, 100));
    var prEmpty = window.dayaCore.chatbotPrompt("   ");
    report(prEmpty.indexOf("<your app description here>") !== -1,
      "chatbot prompt empty description", prEmpty.slice(-60));
  } catch (e) {
    report(false, "chatbot prompt content", e.message);
  }

  /* Show-prompt button reveals the prompt as selectable text and also
     puts exactly the built prompt on the clipboard seam. */
  try {
    var copied = null;
    window.dayaCopyText = function (t) { copied = t; return Promise.resolve(); };
    document.getElementById("description").value = "a todo list called Chores";
    var po = document.getElementById("prompt-out");
    po.hidden = true;
    document.getElementById("copy-prompt").click();
    var expected = window.dayaCore.chatbotPrompt("a todo list called Chores");
    report(copied === expected && po.hidden === false && po.value === expected &&
           po.style.height !== "",
      "show prompt button", String(copied).slice(0, 100));
  } catch (e) {
    report(false, "show prompt button", e.message);
  }

  /* Clipboard failure must not hide the prompt: it stays selectable. */
  try {
    window.dayaCopyText = function () { return Promise.reject(new Error("denied")); };
    var po2 = document.getElementById("prompt-out");
    po2.hidden = true; po2.value = "";
    document.getElementById("copy-prompt").click();
    report(po2.hidden === false && po2.value.indexOf("App description") !== -1,
      "prompt visible without clipboard", po2.value.slice(0, 60));
  } catch (e) {
    report(false, "prompt visible without clipboard", e.message);
  }

  /* Paste-back validation through the page DOM. */
  var VALID_JSON = '{"domain":"web","title":"Steps","theme":{"accent":"teal"},' +
    '"sections":[{"type":"counter","label":"steps","start":0}]}';
  function pasteAndValidate(text) {
    document.getElementById("pasted").value = text;
    document.getElementById("validate-pasted").click();
    return {
      heading: document.getElementById("result-heading").textContent,
      notes: document.getElementById("notes").textContent,
      out: document.getElementById("recipe-out").textContent,
    };
  }
  try {
    var r1 = pasteAndValidate(VALID_JSON);
    report(r1.heading === "Recipe (chatbot paste)" &&
           JSON.parse(r1.out).title === "Steps",
      "paste valid recipe", r1.heading);
    var r2 = pasteAndValidate("Sure! Here is the recipe:\n```json\n" + VALID_JSON + "\n```\nHope this helps");
    report(r2.heading === "Recipe (chatbot paste)" && JSON.parse(r2.out).title === "Steps",
      "paste fenced recipe with prose", r2.heading);
    var r3 = pasteAndValidate("I cannot help with that.");
    report(r3.heading === "No JSON found in the pasted answer", "paste garbage", r3.heading);
    var r4 = pasteAndValidate('{"domain":"web","title":42}');
    report(r4.heading === "The pasted answer is not a valid recipe" && r4.notes.indexOf("title") !== -1,
      "paste schema-invalid recipe", r4.heading + " | " + r4.notes.slice(0, 80));
  } catch (e) {
    report(false, "paste validation flow", e.message);
  }

  /* The manual route must not weaken validation: it is shape-only. */
  try {
    var r5 = pasteAndValidate(VALID_JSON);
    report(r5.notes.indexOf("not that the chatbot understood") !== -1,
      "paste result carries shape-not-meaning note", r5.notes.slice(0, 120));
  } catch (e) {
    report(false, "paste result carries shape-not-meaning note", e.message);
  }

  /* The revealed prompt box holds the complete prompt (byte-exact) and
     is grown to fit it: no inner scrolling, nothing truncated. */
  try {
    document.getElementById("description").value = "verify full prompt";
    document.getElementById("copy-prompt").click();
    var po3 = document.getElementById("prompt-out");
    var full = window.dayaCore.chatbotPrompt("verify full prompt");
    report(po3.value === full &&
           po3.value.indexOf("You convert an app description") === 0 &&
           po3.value.slice(-20).indexOf("verify full prompt") !== -1 &&
           po3.scrollHeight <= po3.clientHeight + 6,
      "prompt box full value, no inner scroll",
      "len " + po3.value.length + "/" + full.length +
      " scroll " + po3.scrollHeight + " vs client " + po3.clientHeight);
  } catch (e) {
    report(false, "prompt box full value, no inner scroll", e.message);
  }

  /* Classifier route, model-free parts (the 27 MB download is not part
     of this suite; real-model evidence is gathered separately). */
  try {
    var ex1 = window.dayaClassifier.extractWithIntent(
      "timer", 'a 5 minute timer for tea, called "Tea"',
      function (e, t) { return window.dayaEngines.run(e, t); });
    report(ex1.recipe.sections[0].type === "timer" && ex1.recipe.sections[0].seconds === 300,
      "classifier extract timer via " + ex1.engine, JSON.stringify(ex1.recipe.sections[0]));
    var ex2 = window.dayaClassifier.extractWithIntent(
      "todo list", 'a todo list with items: rice, eggs, called "Groceries"',
      function (e, t) { return window.dayaEngines.run(e, t); });
    report(ex2.recipe.sections[0].type === "todo" && ex2.recipe.sections[0].items.length === 2,
      "classifier extract todo via " + ex2.engine, JSON.stringify(ex2.recipe.sections[0]).slice(0, 120));
  } catch (e) {
    report(false, "classifier extraction", e.message);
  }

  /* Mismatch and unsupported intents fail honestly. */
  try {
    window.dayaClassifier.extractWithIntent("counter", 'a 5 minute timer for tea',
      function (e, t) { return window.dayaEngines.run(e, t); });
    report(false, "classifier mismatch refusal", "accepted a timer as a counter");
  } catch (err) {
    report(err.message.indexOf("counter") !== -1 && err.message.indexOf("no extractor produced") !== -1,
      "classifier mismatch refusal", err.message.slice(0, 120));
  }
  try {
    window.dayaClassifier.extractWithIntent("quiz", "a quiz about plants",
      function (e, t) { return window.dayaEngines.run(e, t); });
    report(false, "classifier unsupported intent", "built a quiz recipe");
  } catch (err) {
    report(err.message.indexOf("can only extract") !== -1,
      "classifier unsupported intent", err.message.slice(0, 120));
  }

  /* Page glue: go without loading the classifier fails visibly. */
  try {
    document.getElementById("radio-classifier").checked = true;
    document.getElementById("radio-classifier").dispatchEvent(new Event("change"));
    var loadBtnVisible = !document.getElementById("load-classifier").hidden;
    document.getElementById("go").click();
    var h0 = document.getElementById("result-heading").textContent;
    report(h0 === "Classifier not loaded" && loadBtnVisible,
      "classifier route requires tap-to-load", h0);
  } catch (e) {
    report(false, "classifier route requires tap-to-load", e.message);
  }

  /* Page glue with a synchronously-stubbed classifier: intent is heard,
     classical engines extract, validator still gates the output. */
  function resolvedSync(v) {
    return {
      then: function (f) {
        try {
          var r = f(v);
          return r && typeof r.then === "function" ? r : resolvedSync(r);
        } catch (e) {
          return { then: function () { return this; }, catch: function (cf) { cf(e); return this; } };
        }
      },
      catch: function () { return this; }
    };
  }
  try {
    window.dayaClassifier.isLoaded = function () { return true; };
    window.dayaClassifier.classify = function () {
      return resolvedSync({ label: "timer", score: 0.97, labels: ["timer"], scores: [0.97] });
    };
    document.getElementById("description").value = 'a 5 minute timer for tea, called "Tea"';
    document.getElementById("go").click();
    var hc = document.getElementById("result-heading").textContent;
    var pc = JSON.parse(document.getElementById("recipe-out").textContent);
    var nc = document.getElementById("notes").textContent;
    report(hc.indexOf("classifier") !== -1 && pc.sections[0].seconds === 300 &&
           nc.indexOf("not a probability") !== -1,
      "classifier route via DOM (stubbed model)", hc + " | " + nc.slice(0, 80));
    document.getElementById("description").value = "";
    document.querySelector('input[name="route"][value="deterministic"]').checked = true;
  } catch (e) {
    report(false, "classifier route via DOM (stubbed model)", e.message);
  }

  /* The AI prompt carries two few-shot pairs (regression pin: the
     single-example prompt made a 360M model imitate the timer shape). */
  try {
    var msgs = window.dayaCore.aiChatMessages("test description");
    report(msgs.length === 6 && msgs[0].role === "system" &&
           msgs[5].content.indexOf("test description") !== -1,
      "ai prompt has two few-shot pairs", JSON.stringify(msgs.length));
  } catch (e) {
    report(false, "ai prompt has two few-shot pairs", e.message);
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
    for name in ("compose-engines.js", "compose-classifier.js"):
        with open(os.path.join(ROOT, "docs", name), encoding="utf-8") as src:
            code = src.read()
        with open(os.path.join(workdir, name), "w", encoding="utf-8") as fh:
            fh.write(code)
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
