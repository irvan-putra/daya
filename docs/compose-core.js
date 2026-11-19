/* daya compose core: browser port of dayalib/describe.py and the web
 * domain's validate(). Parity with the Python implementations is
 * test-covered (tests/browser_test_compose.py against
 * tests/compose_fixtures.json, which the Python side generates).
 *
 * Exposes window.dayaCore = { describe, validateRecipe, ACCENTS }.
 * Plain script, no modules, no network: the deterministic route and the
 * validator must work fully offline.
 */
(function () {
  "use strict";

  var ACCENTS = {
    indigo: "#4f46e5",
    teal: "#0f766e",
    amber: "#b45309",
    rose: "#be123c",
    green: "#15803d",
    slate: "#334155",
  };
  var DEFAULT_ACCENT = "indigo";
  var MAX_SECTIONS = 24;
  var MAX_LIST_ITEMS = 50;
  var MAX_TODO_SEED_ITEMS = 50;
  var SECTION_TYPES = ["text", "list", "counter", "quiz", "timer", "todo"];
  var STORAGE_KEY_RE = /^[a-z0-9][a-z0-9-]{0,31}$/;
  var BACK_HREF_RE = /^(?!.*(?:\.\.|\/\/|:))[a-z0-9][a-z0-9./-]{0,60}\.html$/;

  /* ---- validator (port of dayalib/domains/web.py validate) ---- */

  function makeCheck() {
    return {
      errors: [],
      fail: function (path, message) {
        this.errors.push(path + ": " + message);
      },
    };
  }

  function checkString(check, value, path, minLen, maxLen) {
    if (typeof value !== "string") {
      check.fail(path, "must be a string");
      return null;
    }
    if (value.length < minLen || value.length > maxLen) {
      check.fail(
        path,
        "must be " + minLen + ".." + maxLen + " characters, got " + value.length
      );
      return null;
    }
    return value;
  }

  function checkInt(check, value, path, minV, maxV) {
    if (typeof value !== "number" || !Number.isInteger(value)) {
      check.fail(path, "must be a whole number");
      return null;
    }
    if (value < minV || value > maxV) {
      check.fail(path, "must be between " + minV + " and " + maxV + ", got " + value);
      return null;
    }
    return value;
  }

  function checkNoUnknownKeys(check, obj, allowed, path) {
    Object.keys(obj).forEach(function (key) {
      if (allowed.indexOf(key) === -1) {
        check.fail(path, "unknown field '" + key + "'");
      }
    });
  }

  function validateSection(check, section, path) {
    if (section === null || typeof section !== "object" || Array.isArray(section)) {
      check.fail(path, "must be an object");
      return null;
    }
    var stype = section.type;
    if (SECTION_TYPES.indexOf(stype) === -1) {
      check.fail(path + ".type", "must be one of: " + SECTION_TYPES.join(", "));
      return null;
    }

    if (stype === "text") {
      checkNoUnknownKeys(check, section, ["type", "heading", "body"], path);
      var theading = checkString(check, section.heading, path + ".heading", 1, 80);
      var body = checkString(check, section.body, path + ".body", 1, 2000);
      if (theading === null || body === null) return null;
      return { type: "text", heading: theading, body: body };
    }

    if (stype === "list") {
      checkNoUnknownKeys(check, section, ["type", "heading", "items"], path);
      var lheading = section.heading;
      if (lheading !== undefined && lheading !== null) {
        lheading = checkString(check, lheading, path + ".heading", 1, 80);
      }
      var items = section.items;
      if (!Array.isArray(items) || items.length < 1 || items.length > MAX_LIST_ITEMS) {
        check.fail(path + ".items", "must be a list of 1.." + MAX_LIST_ITEMS + " items");
        return null;
      }
      var cleanItems = [];
      var ok = true;
      if (section.heading !== undefined && section.heading !== null && lheading === null) {
        ok = false;
      }
      items.forEach(function (item, j) {
        var cleaned = checkString(check, item, path + ".items[" + j + "]", 1, 200);
        if (cleaned === null) ok = false;
        else cleanItems.push(cleaned);
      });
      if (!ok) return null;
      return { type: "list", heading: lheading === undefined ? null : lheading, items: cleanItems };
    }

    if (stype === "counter") {
      checkNoUnknownKeys(check, section, ["type", "label", "start"], path);
      var clabel = checkString(check, section.label, path + ".label", 1, 80);
      var start = checkInt(
        check,
        section.start === undefined ? 0 : section.start,
        path + ".start",
        -1000000,
        1000000
      );
      if (clabel === null || start === null) return null;
      return { type: "counter", label: clabel, start: start };
    }

    if (stype === "quiz") {
      checkNoUnknownKeys(check, section, ["type", "question", "choices", "answer"], path);
      var question = checkString(check, section.question, path + ".question", 1, 280);
      var choices = section.choices;
      var cleanChoices = [];
      var choicesOk = true;
      if (!Array.isArray(choices) || choices.length < 2 || choices.length > 6) {
        check.fail(path + ".choices", "must be a list of 2..6 choices");
        choicesOk = false;
      } else {
        choices.forEach(function (choice, j) {
          var c = checkString(check, choice, path + ".choices[" + j + "]", 1, 120);
          if (c === null) choicesOk = false;
          else cleanChoices.push(c);
        });
      }
      var answer = null;
      if (!("answer" in section)) {
        check.fail(path + ".answer", "is required");
      } else if (choicesOk) {
        answer = checkInt(check, section.answer, path + ".answer", 0, cleanChoices.length - 1);
      }
      if (question === null || !choicesOk || answer === null) return null;
      return { type: "quiz", question: question, choices: cleanChoices, answer: answer };
    }

    if (stype === "timer") {
      checkNoUnknownKeys(check, section, ["type", "label", "seconds"], path);
      var tlabel = checkString(check, section.label, path + ".label", 1, 80);
      var seconds = checkInt(check, section.seconds, path + ".seconds", 5, 3600);
      if (tlabel === null || seconds === null) return null;
      return { type: "timer", label: tlabel, seconds: seconds };
    }

    if (stype === "todo") {
      checkNoUnknownKeys(check, section, ["type", "heading", "storage_key", "items"], path);
      var oheading = section.heading;
      if (oheading !== undefined && oheading !== null) {
        oheading = checkString(check, oheading, path + ".heading", 1, 80);
      }
      var key = section.storage_key;
      if (typeof key !== "string" || !STORAGE_KEY_RE.test(key)) {
        check.fail(
          path + ".storage_key",
          "must be 1..32 chars: lowercase letters, digits, hyphens, " +
            "starting with a letter or digit (it becomes the browser " +
            "storage key and must be unique per app)"
        );
        key = null;
      }
      var oitems = section.items === undefined ? [] : section.items;
      var cleanOItems = [];
      var ook = true;
      if (section.heading !== undefined && section.heading !== null && oheading === null) {
        ook = false;
      }
      if (!Array.isArray(oitems) || oitems.length > MAX_TODO_SEED_ITEMS) {
        check.fail(
          path + ".items",
          "must be a list of 0.." + MAX_TODO_SEED_ITEMS + " starter items"
        );
        ook = false;
      } else {
        oitems.forEach(function (item, j) {
          var cleaned = checkString(check, item, path + ".items[" + j + "]", 1, 200);
          if (cleaned === null) ook = false;
          else cleanOItems.push(cleaned);
        });
      }
      if (key === null || !ook) return null;
      return {
        type: "todo",
        heading: oheading === undefined ? null : oheading,
        storage_key: key,
        items: cleanOItems,
      };
    }

    throw new Error("unhandled section type");
  }

  function validateRecipe(recipe) {
    var check = makeCheck();
    var model = { sections: [] };

    if (recipe === null || typeof recipe !== "object" || Array.isArray(recipe)) {
      check.fail("recipe", "must be an object");
      return { model: null, errors: check.errors };
    }

    checkNoUnknownKeys(check, recipe, ["domain", "title", "description", "theme", "back", "sections"], "recipe");

    var title = checkString(check, recipe.title, "title", 1, 80);
    if (title !== null) model.title = title;

    if ("description" in recipe) {
      var description = checkString(check, recipe.description, "description", 1, 280);
      if (description !== null) model.description = description;
    }

    var accent = DEFAULT_ACCENT;
    var theme = recipe.theme;
    if (theme !== undefined && theme !== null) {
      if (typeof theme !== "object" || Array.isArray(theme)) {
        check.fail("theme", "must be an object");
      } else {
        checkNoUnknownKeys(check, theme, ["accent"], "theme");
        if ("accent" in theme) {
          if (!(theme.accent in ACCENTS)) {
            check.fail("theme.accent", "must be one of: " + Object.keys(ACCENTS).sort().join(", "));
          } else {
            accent = theme.accent;
          }
        }
      }
    }
    model.accent = accent;

    if ("back" in recipe) {
      var back = recipe.back;
      if (back === null || typeof back !== "object" || Array.isArray(back)) {
        check.fail("back", "must be an object");
      } else {
        checkNoUnknownKeys(check, back, ["href", "label"], "back");
        var href = back.href;
        var hrefOk = true;
        if (typeof href !== "string" || !BACK_HREF_RE.test(href)) {
          check.fail(
            "back.href",
            "must be a relative .html path (no scheme, host, port or parent traversal)"
          );
          hrefOk = false;
        }
        var blabel = checkString(check, back.label, "back.label", 1, 80);
        if (hrefOk && blabel !== null) {
          model.back = { href: href, label: blabel };
        }
      }
    }

    var sections = recipe.sections;
    if (!Array.isArray(sections)) {
      check.fail("sections", "must be a list");
    } else if (sections.length < 1 || sections.length > MAX_SECTIONS) {
      check.fail("sections", "must have 1.." + MAX_SECTIONS + " items, got " + sections.length);
    } else {
      sections.forEach(function (section, i) {
        var cleaned = validateSection(check, section, "sections[" + i + "]");
        if (cleaned !== null) model.sections.push(cleaned);
      });
    }

    var seenKeys = {};
    model.sections.forEach(function (cleaned, i) {
      if (cleaned.type === "todo") {
        if (seenKeys[cleaned.storage_key]) {
          check.fail("sections[" + i + "].storage_key", "duplicates an earlier todo section");
        }
        seenKeys[cleaned.storage_key] = true;
      }
    });

    return { model: model, errors: check.errors };
  }

  /* ---- deterministic parser (port of dayalib/describe.py) ---- */

  var TODO_RE = /(?:a |an |my |another )?(to-?do(?: list)?|task list|errands?|shopping list|grocer(?:y|ies) list|editable list|checklist to edit)\b(?:\s+(?:with|containing)\s+(?:items?\s*)?:?\s*(.+))?$/i;
  var LIST_RE = /(?:a |an )?(?:check)?list(?:\s+of)?\s*:?\s+(.+)$/i;
  var COUNTER_RE = /(?:a |an )?counter(?:\s+(?:for|labeled|called)\s+(.+))?$/i;
  var TIMER_A_RE = /(?:a |an )?(\d+)\s*(second|minute|hour)s?\s+(timer|countdown)(?:\s+(?:for|labeled|called)\s+(.+))?$/i;
  var TIMER_B_RE = /(timer|countdown)(?:\s+(?:of|for))?\s+(\d+)\s*(second|minute|hour)s?(?:\s+(?:for|labeled|called)\s+(.+))?$/i;
  var POMODORO_RE = /(?:a )?(pomodoro|focus timer)\b\.?$/i;
  var TEXT_RE = /(?:a |an )?(text|note|intro|about)(?:\s+(?:that says|saying))?\s*:?\s*(.+)$/i;
  var TITLE_RE = /(?:called|named|titled)\s+("[^"]+"|'[^']+'|[^,.]+?)\s*(?=,|\.|$)/i;
  var DESCRIPTION_RE = /(?:description|tagline)\s*[:=]\s*(.+)$|described as\s+(.+)$/i;
  var UNITS = { second: 1, minute: 60, hour: 3600 };
  var MAX_ITEM_LEN = 200;

  function DescribeError(message) {
    this.message = message;
    this.name = "DescribeError";
  }

  function stripQuotes(text) {
    text = text.trim();
    if (text.length >= 2 && (text[0] === '"' || text[0] === "'") && text[text.length - 1] === text[0]) {
      text = text.slice(1, -1).trim();
    }
    return text;
  }

  function splitItems(text, notes) {
    var parts = text.split(/,|\band\b/);
    var items = [];
    parts.forEach(function (part) {
      var item = stripQuotes(part);
      if (!item) return;
      if (item.length > MAX_ITEM_LEN) {
        notes.push("item '" + item.slice(0, 20) + "'... is over " + MAX_ITEM_LEN + " characters; truncated");
        item = item.slice(0, MAX_ITEM_LEN);
      }
      items.push(item);
    });
    if (items.length > MAX_LIST_ITEMS) {
      notes.push("only the first " + MAX_LIST_ITEMS + " items were kept");
      items = items.slice(0, MAX_LIST_ITEMS);
    }
    return items;
  }

  function slug(title, suffix, taken) {
    var base = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "app";
    base = base.slice(0, 24).replace(/^-+|-+$/g, "");
    var key = (base + "-" + suffix).slice(0, 32).replace(/-+$/g, "");
    var n = 2;
    while (taken[key]) {
      key = (base + "-" + suffix + "-" + n).slice(0, 32).replace(/-+$/g, "");
      n += 1;
    }
    taken[key] = true;
    return key;
  }

  function timerSection(value, unit, label, notes) {
    var seconds = value * UNITS[unit.toLowerCase()];
    if (seconds > 3600) {
      notes.push("timer of " + value + " " + unit.toLowerCase() + "s is over the 3600 second limit; capped");
      seconds = 3600;
    }
    if (seconds < 5) {
      notes.push("timer of " + value + " " + unit.toLowerCase() + "s is under the 5 second minimum; raised to 5");
      seconds = 5;
    }
    label = stripQuotes(label || unit[0].toUpperCase() + unit.slice(1).toLowerCase() + " timer").slice(0, 80);
    return { type: "timer", label: label, seconds: seconds };
  }

  function parseSection(sentence, title, takenKeys, notes) {
    var match = TIMER_A_RE.exec(sentence);
    if (match) return timerSection(parseInt(match[1], 10), match[2], match[4], notes);
    match = TIMER_B_RE.exec(sentence);
    if (match) return timerSection(parseInt(match[2], 10), match[3], match[4], notes);
    match = POMODORO_RE.exec(sentence);
    if (match) {
      notes.push("no duration given for the pomodoro; used 25 minutes");
      return { type: "timer", label: "Focus", seconds: 25 * 60 };
    }
    match = COUNTER_RE.exec(sentence);
    if (match) {
      return { type: "counter", label: stripQuotes(match[1] || "Count").slice(0, 80) };
    }
    match = TODO_RE.exec(sentence);
    if (match) {
      var rawHeading = match[1].trim();
      var section = {
        type: "todo",
        heading: (rawHeading[0].toUpperCase() + rawHeading.slice(1).toLowerCase()).slice(0, 80),
        storage_key: slug(title, "todo", takenKeys),
      };
      if (match[2]) section.items = splitItems(match[2], notes);
      return section;
    }
    match = LIST_RE.exec(sentence);
    if (match) {
      var items = splitItems(match[1], notes);
      if (items.length) return { type: "list", items: items };
      notes.push("a list needs at least one item; ignored '" + sentence + "'");
      return null;
    }
    match = TEXT_RE.exec(sentence);
    if (match) {
      var body = stripQuotes(match[2]);
      if (body.length > 2000) {
        notes.push("text section is over 2000 characters; truncated");
        body = body.slice(0, 2000);
      }
      var heading = { text: "Text", note: "Note", intro: "Intro", about: "About" }[match[1].toLowerCase()];
      return { type: "text", heading: heading, body: body };
    }
    return null;
  }

  function describe(text) {
    if (typeof text !== "string" || !text.trim()) {
      throw new DescribeError("the description is empty");
    }
    if (text.length > 8000) {
      throw new DescribeError(
        "the description is too long (limit 8000 characters); describe the app in a few sentences"
      );
    }

    var notes = [];
    var title = null;
    var description = null;
    var accent = null;
    var leftovers = [];

    text.split(/[.\n;]+/).forEach(function (rawSentence) {
      var sentence = rawSentence.trim();
      if (!sentence) return;
      var match = TITLE_RE.exec(sentence);
      if (match && title === null) {
        title = stripQuotes(match[1]).slice(0, 80);
        sentence = (sentence.slice(0, match.index) + " " + sentence.slice(match.index + match[0].length)).replace(/^[ ,]+|[ ,]+$/g, "");
        if (!sentence) return;
      }
      Object.keys(ACCENTS).sort().forEach(function (name) {
        if (accent !== null) return;
        var re = new RegExp("\\b" + name + "\\b", "i");
        var m = re.exec(sentence);
        if (m) {
          accent = name;
          sentence = sentence.replace(re, "").trim();
        }
      });
      match = DESCRIPTION_RE.exec(sentence);
      if (match && description === null) {
        description = stripQuotes(match[1] || match[2]).replace(/^[ ,]+|[ ,]+$/g, "").slice(0, 280);
        sentence = (sentence.slice(0, match.index) + " " + sentence.slice(match.index + match[0].length)).replace(/^[ ,]+|[ ,]+$/g, "");
        if (!sentence) return;
      }
      sentence = sentence.replace(/\s*,\s*/g, ", ").replace(/^[ ,]+|[ ,]+$/g, "");
      if (sentence) leftovers.push(sentence);
    });

    if (title === null) {
      title = "My app";
      notes.push('no name found (try: called "Errands"); used "My app"');
    }

    var takenKeys = {};
    var sections = [];
    leftovers.forEach(function (sentence) {
      var section = parseSection(sentence, title, takenKeys, notes);
      if (section === null) {
        notes.push("not understood, ignored: '" + sentence + "'");
      } else {
        sections.push(section);
      }
    });

    if (!sections.length) {
      throw new DescribeError(
        'no recognizable sections. Supported phrasings: "a 25 minute timer for X", ' +
          '"pomodoro", "a counter for X", "a todo list with items: a, b and c", ' +
          '"a list: a, b", "text: some words". Add a name with: called "My app".'
      );
    }

    var recipe = { domain: "web", title: title, sections: sections };
    if (description !== null) recipe.description = description;
    if (accent !== null) recipe.theme = { accent: accent };

    var result = validateRecipe(recipe);
    if (result.errors.length) {
      throw new DescribeError("internal error: parsed recipe failed validation: " + result.errors.join("; "));
    }
    var out = { domain: "web", title: result.model.title, sections: result.model.sections };
    if (result.model.description !== undefined) out.description = result.model.description;
    out.theme = { accent: result.model.accent };
    return { recipe: out, notes: notes };
  }

  window.dayaCore = {
    describe: describe,
    validateRecipe: validateRecipe,
    DescribeError: DescribeError,
    ACCENTS: ACCENTS,
  };
})();
