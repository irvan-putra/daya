/* daya compose engines: classical (pre-LLM) text-to-recipe methods.
 *
 * Four offline engines, strictest first, in the spirit of the Snips NLU
 * cascade (deterministic parser first, probabilistic parser as fallback;
 * snips found no gain from deep models over CRFs for this task):
 *
 *   rules    - the regex keyword parser (ported from dayalib/describe.py)
 *   grammar  - a small recursive-descent parser: number words ("twenty
 *              five minutes"), flexible word order, one-word answers
 *   template - Chatito-style template/slot matching with typo tolerance
 *              (one edit distance per literal), filler-word skipping
 *   bayes    - a multinomial naive Bayes intent classifier trained in
 *              the page on generated samples (no download), with rule
 *              slot filling; reports its confidence
 *
 * Every engine's output passes window.dayaCore.validateRecipe before it
 * is returned. "auto" runs the cascade and says which engine answered.
 *
 * Exposes window.dayaEngines = { ENGINES, run(engineName, text) } where
 * run returns { recipe, notes, engine } or throws an Error whose
 * message lists what was not understood.
 */
(function () {
  "use strict";

  var core = window.dayaCore;

  /* ---------- shared sentence-level extraction (title/description/accent) ---------- */

  var TITLE_RE = /(?:called|named|titled)\s+("[^"]+"|'[^']+'|[^,.]+?)\s*(?=,|\.|$)/i;
  var DESCRIPTION_RE = /(?:description|tagline)\s*[:=]\s*(.+)$|described as\s+(.+)$/i;

  function stripQuotes(text) {
    text = text.trim();
    if (text.length >= 2 && (text[0] === '"' || text[0] === "'") && text[text.length - 1] === text[0]) {
      text = text.slice(1, -1).trim();
    }
    return text;
  }

  function extractMeta(text, notes) {
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
      Object.keys(core.ACCENTS).sort().forEach(function (name) {
        if (accent !== null) return;
        var re = new RegExp("\\b" + name + "\\b", "i");
        if (re.test(sentence)) {
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
    return { title: title, description: description, accent: accent, leftovers: leftovers };
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

  function assemble(meta, sections, notes) {
    if (!sections.length) {
      throw new Error("no recognizable sections");
    }
    var recipe = { domain: "web", title: meta.title, sections: sections };
    if (meta.description !== null) recipe.description = meta.description;
    if (meta.accent !== null) recipe.theme = { accent: meta.accent };
    var result = core.validateRecipe(recipe);
    if (result.errors.length) {
      throw new Error("internal error: parsed recipe failed validation: " + result.errors.join("; "));
    }
    var out = { domain: "web", title: result.model.title, sections: result.model.sections };
    if (result.model.description !== undefined) out.description = result.model.description;
    out.theme = { accent: result.model.accent };
    return { recipe: out, notes: notes };
  }

  function splitItems(text, notes) {
    var parts = text.split(/,|\band\b/i);
    var items = [];
    parts.forEach(function (part) {
      var item = stripQuotes(part.replace(/^(with|items?|containing)\s+/i, ""));
      if (item) items.push(item.length > 200 ? item.slice(0, 200) : item);
    });
    if (items.length > 50) {
      notes.push("only the first 50 items were kept");
      items = items.slice(0, 50);
    }
    return items;
  }

  /* ---------- token helpers ---------- */

  var NUMBER_WORDS = {
    one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7,
    eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, thirteen: 13,
    fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18,
    nineteen: 19, twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60,
    seventy: 70, eighty: 80, ninety: 90,
  };
  var UNITS = { second: 1, seconds: 1, minute: 60, minutes: 60, hour: 3600, hours: 3600 };
  var ARTICLES = { a: 1, an: 1, the: 1, my: 1, another: 1, please: 1, make: 1, me: 1, create: 1, build: 1, want: 1, i: 1, add: 1, give: 1, can: 1, you: 1 };

  function tokenize(sentence) {
    return sentence.toLowerCase().replace(/["']/g, "").split(/[^a-z0-9]+/).filter(Boolean);
  }

  function tokenizeSpans(sentence) {
    /* Tokens with character offsets into the original sentence. */
    var spans = [];
    var re = /[a-z0-9]+/g;
    var cleaned = sentence.toLowerCase();
    var m;
    while ((m = re.exec(cleaned)) !== null) {
      spans.push({ t: m[0], start: m.index, end: m.index + m[0].length });
    }
    return spans;
  }

  function readNumber(tokens, i) {
    /* Returns { value, next } or null. Handles digits and number words.
       "a"/"an" count as 1 only directly before a unit, never mid-phrase. */
    if (i >= tokens.length) return null;
    if ((tokens[i] === "a" || tokens[i] === "an") && i + 1 < tokens.length && UNITS[tokens[i + 1]]) {
      return { value: 1, next: i + 1 };
    }
    if (/^\d+$/.test(tokens[i])) return { value: parseInt(tokens[i], 10), next: i + 1 };
    var total = 0;
    var j = i;
    var seen = false;
    while (j < tokens.length && NUMBER_WORDS[tokens[j]] !== undefined) {
      total += NUMBER_WORDS[tokens[j]];
      seen = true;
      j++;
    }
    return seen ? { value: total, next: j } : null;
  }

  function clampSeconds(value, unit, notes) {
    var seconds = value * UNITS[unit];
    if (seconds > 3600) {
      notes.push("timer of " + value + " " + unit + "s is over the 3600 second limit; capped");
      seconds = 3600;
    }
    if (seconds < 5) {
      notes.push("timer of " + value + " " + unit + "s is under the 5 second minimum; raised to 5");
      seconds = 5;
    }
    return seconds;
  }

  /* ---------- engine: grammar (recursive descent over tokens) ---------- */

  var GRAMMAR_TIMER_HEADS = { timer: 1, countdown: 1 };
  var GRAMMAR_TODO_HEADS = ["todo list", "to-do list", "todo", "to-do", "task list", "tasks", "errands", "shopping list", "grocery list", "groceries"];

  function grammarParseSection(sentence, meta, takenKeys, notes) {
    var tokens = tokenize(sentence);
    while (tokens.length && ARTICLES[tokens[0]]) tokens.shift();

    /* pomodoro / focus timer */
    if (tokens.join(" ") === "pomodoro" || tokens.join(" ") === "focus timer") {
      notes.push("no duration given for the pomodoro; used 25 minutes");
      return { type: "timer", label: "Focus", seconds: 1500 };
    }

    /* timer: [NUMBER UNIT] HEAD [for LABEL] [of NUMBER UNIT], any order */
    var headIdx = -1;
    tokens.forEach(function (t, i) { if (GRAMMAR_TIMER_HEADS[t] && headIdx === -1) headIdx = i; });
    if (headIdx !== -1) {
      var seconds = null;
      var labelTokens = [];
      var i = 0;
      while (i < tokens.length) {
        if (i === headIdx) { i++; continue; }
        var num = readNumber(tokens, i);
        if (num && num.next < tokens.length && UNITS[tokens[num.next]]) {
          if (seconds !== null) throw new Error("grammar: two durations in one timer");
          seconds = clampSeconds(num.value, tokens[num.next], notes);
          i = num.next + 1;
          continue;
        }
        if (tokens[i] === "for" || tokens[i] === "of") { i++; continue; }
        labelTokens.push(tokens[i]);
        i++;
      }
      if (seconds === null) throw new Error("grammar: timer without a duration");
      var label = labelTokens.join(" ") || "Timer";
      return { type: "timer", label: (label[0].toUpperCase() + label.slice(1)).slice(0, 80), seconds: seconds };
    }

    /* counter */
    if (tokens[0] === "counter" || tokens[1] === "counter") {
      var ci = tokens.indexOf("counter");
      var clabel = tokens.slice(ci + 1).filter(function (t) { return t !== "for" && t !== "labeled"; }).join(" ");
      return { type: "counter", label: (clabel || "Count").slice(0, 80) };
    }

    /* todo */
    var joined = tokens.join(" ");
    for (var h = 0; h < GRAMMAR_TODO_HEADS.length; h++) {
      var head = GRAMMAR_TODO_HEADS[h];
      if (joined.indexOf(head) === 0 || joined.indexOf(" " + head) !== -1) {
        var section = {
          type: "todo",
          heading: (head[0].toUpperCase() + head.slice(1)).slice(0, 80),
          storage_key: slug(meta.title, "todo", takenKeys),
        };
        var after = sentence.toLowerCase().split(head)[1] || "";
        if (/\b(with|containing|items?)\b/.test(after)) {
          var items = splitItems(after, notes);
          if (items.length) section.items = items;
        }
        return section;
      }
    }

    /* list */
    if (tokens[0] === "list" || tokens[0] === "checklist") {
      var rest = sentence.replace(/^[^:]*?:/, "");
      if (rest === sentence) rest = sentence.replace(/^\s*(?:a\s+|an\s+)?(?:check)?list\s+(?:of\s+)?/i, "");
      var litems = splitItems(rest, notes);
      if (litems.length) return { type: "list", items: litems };
      throw new Error("grammar: a list needs at least one item");
    }

    /* text */
    var m = /^(?:a\s+|an\s+)?(text|note|intro|about)\b\s*:?\s*(.+)$/i.exec(sentence);
    if (m) {
      var heading = { text: "Text", note: "Note", intro: "Intro", about: "About" }[m[1].toLowerCase()];
      var body = stripQuotes(m[2]);
      return { type: "text", heading: heading, body: body.slice(0, 2000) };
    }

    return null;
  }

  function engineGrammar(text) {
    var notes = [];
    var meta = extractMeta(text, notes);
    var takenKeys = {};
    var sections = [];
    var failed = [];
    meta.leftovers.forEach(function (sentence) {
      var section = grammarParseSection(sentence, meta, takenKeys, notes);
      if (section === null) failed.push(sentence);
      else sections.push(section);
    });
    if (failed.length) {
      throw new Error("grammar engine could not parse: '" + failed.join("', '") + "'");
    }
    return assemble(meta, sections, notes);
  }

  /* ---------- engine: template (slot matching with typo tolerance) ---------- */

  function editDistance1(a, b) {
    /* true when a and b differ by at most one edit: substitution,
       insertion, deletion, or one adjacent transposition (Damerau). */
    if (a === b) return true;
    var la = a.length, lb = b.length;
    if (Math.abs(la - lb) > 1) return false;
    if (la === lb) {
      var diff = [];
      for (var i = 0; i < la; i++) if (a[i] !== b[i]) diff.push(i);
      if (diff.length === 1) return true;
      if (diff.length === 2 && diff[1] === diff[0] + 1 &&
          a[diff[0]] === b[diff[1]] && a[diff[1]] === b[diff[0]]) return true;
      return false;
    }
    /* one insertion/deletion */
    var short = la < lb ? a : b;
    var long = la < lb ? b : a;
    var si = 0, li = 0, skipped = false;
    while (si < short.length && li < long.length) {
      if (short[si] === long[li]) { si++; li++; continue; }
      if (skipped) return false;
      skipped = true;
      li++;
    }
    return true;
  }

  /* Template tokens: literal words, {slot} placeholders, [literal] optional. */
  var TEMPLATES = [
    { t: "{num} {unit} timer for {label}", make: function (s, notes) {
      return { type: "timer", label: cap(s.label || "Timer"), seconds: clampSeconds(num(s.num), s.unit, notes) };
    } },
    { t: "{num} {unit} timer", make: function (s, notes) {
      return { type: "timer", label: cap(s.unit) + " timer", seconds: clampSeconds(num(s.num), s.unit, notes) };
    } },
    { t: "{num} {unit} countdown", make: function (s, notes) {
      return { type: "timer", label: "Countdown", seconds: clampSeconds(num(s.num), s.unit, notes) };
    } },
    { t: "timer for {label}", make: function (s, notes) {
      var n = readNumber(tokenize(s.label), 0);
      if (n) throw new Error("template: timer label looked like a duration");
      return { type: "timer", label: cap(s.label), seconds: 300, defaultSeconds: true };
    } },
    { t: "counter for {label}", make: function (s) {
      return { type: "counter", label: s.label.slice(0, 80) };
    } },
    { t: "counter", make: function () { return { type: "counter", label: "Count" }; } },
    { t: "pomodoro", make: function () { return { type: "timer", label: "Focus", seconds: 1500, pomodoro: true }; } },
    { t: "{todohead} with items {items}", make: function (s, notes, meta, takenKeys) {
      return todoSection(s.todohead, s.items, notes, meta, takenKeys);
    } },
    { t: "{todohead} with {items}", make: function (s, notes, meta, takenKeys) {
      return todoSection(s.todohead, s.items, notes, meta, takenKeys);
    } },
    { t: "{todohead}", make: function (s, notes, meta, takenKeys) {
      return todoSection(s.todohead, null, notes, meta, takenKeys);
    } },
    { t: "list of {items}", make: function (s, notes) {
      return listSection(s.items, notes);
    } },
    { t: "list {items}", make: function (s, notes) {
      return listSection(s.items, notes);
    } },
    { t: "{texthead} {body}", make: function (s) {
      var heading = { text: "Text", note: "Note", intro: "Intro", about: "About" }[s.texthead];
      if (!heading) throw new Error("template: bad text head");
      return { type: "text", heading: heading, body: s.body.slice(0, 2000) };
    } },
  ];
  var TODO_HEAD_WORDS = { todo: 1, tasks: 1, errands: 1, shopping: 1, grocery: 1, groceries: 1, checklist: 1 };
  var TEXT_HEAD_WORDS = { text: 1, note: 1, intro: 1, about: 1 };

  function cap(s) {
    s = s || "Timer";
    return (s[0].toUpperCase() + s.slice(1)).slice(0, 80);
  }
  function num(word) {
    var tokens = tokenize(word);
    var n = readNumber(tokens, 0);
    if (!n || n.next !== tokens.length) throw new Error("template: bad number '" + word + "'");
    return n.value;
  }
  function todoSection(head, itemsText, notes, meta, takenKeys) {
    if (!TODO_HEAD_WORDS[tokenize(head)[0] || ""]) throw new Error("template: bad todo head '" + head + "'");
    var section = {
      type: "todo",
      heading: cap(head).slice(0, 80),
      storage_key: slug(meta.title, "todo", takenKeys),
    };
    if (itemsText) {
      var items = splitItems(itemsText, notes);
      if (items.length) section.items = items;
    }
    return section;
  }
  function listSection(itemsText, notes) {
    var items = splitItems(itemsText, notes);
    if (!items.length) throw new Error("template: a list needs at least one item");
    return { type: "list", items: items };
  }

  function matchTemplate(template, spans, sentence) {
    /* Left-to-right matching with one typo allowed per literal word.
       Slot values come from the original sentence via character spans,
       so punctuation inside slots (commas in item lists) is preserved.
       Returns a slots object or null. */
    var templateTokens = template.split(" ");
    var slots = {};
    var ii = 0; /* index into spans */

    function slotValue(fromIdx, toIdx) {
      if (toIdx <= fromIdx) return "";
      return sentence.slice(spans[fromIdx].start, spans[toIdx - 1].end).trim();
    }

    for (var ti = 0; ti < templateTokens.length; ti++) {
      var tt = templateTokens[ti];
      if (tt[0] === "{") {
        var name = tt.slice(1, -1);
        if (name === "num") {
          /* one or two tokens fully consumed by readNumber */
          var took = 0;
          for (var len = Math.min(2, spans.length - ii); len >= 1; len--) {
            var words = spans.slice(ii, ii + len).map(function (sp) { return sp.t; });
            var n = readNumber(words, 0);
            if (n && n.next === words.length) { took = len; break; }
          }
          if (!took) return null;
          slots[name] = slotValue(ii, ii + took);
          ii += took;
          continue;
        }
        if (name === "unit") {
          if (ii >= spans.length || !UNITS[spans[ii].t]) return null;
          slots[name] = spans[ii].t;
          ii += 1;
          continue;
        }
        if (name === "todohead" || name === "texthead") {
          var dict = name === "todohead" ? TODO_HEAD_WORDS : TEXT_HEAD_WORDS;
          var took2 = 0;
          for (var len2 = Math.min(2, spans.length - ii); len2 >= 1; len2--) {
            var phrase = spans.slice(ii, ii + len2).map(function (sp) { return sp.t; }).join(" ");
            var first = spans[ii].t;
            if (dict[first]) { took2 = len2; break; }
          }
          if (!took2) return null;
          slots[name] = slotValue(ii, ii + took2);
          ii += took2;
          continue;
        }
        /* free slot: capture until the next literal template token matches */
        var nextLiteral = null;
        for (var tj = ti + 1; tj < templateTokens.length; tj++) {
          if (templateTokens[tj][0] !== "{") { nextLiteral = templateTokens[tj]; break; }
        }
        var start = ii;
        if (nextLiteral === null) {
          ii = spans.length;
        } else {
          var found = -1;
          for (var k = ii; k < spans.length; k++) {
            if (editDistance1(spans[k].t, nextLiteral)) { found = k; break; }
          }
          if (found === -1) return null;
          ii = found;
        }
        slots[name] = slotValue(start, ii);
        if (!slots[name]) return null;
      } else {
        if (ii >= spans.length) return null;
        if (editDistance1(spans[ii].t, tt)) {
          ii++;
        } else if (ARTICLES[spans[ii].t]) {
          ii++; /* skip one filler word and retry this literal */
          if (ii >= spans.length || !editDistance1(spans[ii].t, tt)) return null;
          ii++;
        } else {
          return null;
        }
      }
    }
    if (ii < spans.length) return null; /* trailing input words unmatched */
    return slots;
  }

  function engineTemplate(text) {
    var notes = [];
    var meta = extractMeta(text, notes);
    var takenKeys = {};
    var sections = [];
    var failed = [];
    meta.leftovers.forEach(function (sentence) {
      var spans = tokenizeSpans(sentence);
      while (spans.length && ARTICLES[spans[0].t]) spans.shift();
      var built = null;
      for (var i = 0; i < TEMPLATES.length && !built; i++) {
        var slots = matchTemplate(TEMPLATES[i].t, spans, sentence);
        if (slots) {
          try {
            built = TEMPLATES[i].make(slots, notes, meta, takenKeys);
            if (built.defaultSeconds) {
              notes.push("template matched a timer with no duration; used 5 minutes");
              delete built.defaultSeconds;
            }
            if (built.pomodoro) {
              notes.push("no duration given for the pomodoro; used 25 minutes");
              delete built.pomodoro;
            }
          } catch (e) {
            built = null;
          }
        }
      }
      if (built === null) failed.push(sentence);
      else sections.push(built);
    });
    if (failed.length) {
      throw new Error("template engine could not match: '" + failed.join("', '") + "'");
    }
    return assemble(meta, sections, notes);
  }

  /* ---------- engine: bayes (naive Bayes intent + rule slots) ---------- */

  var INTENTS = ["timer", "counter", "todo", "list", "text"];

  /* Deterministic sample generation (Chatito-style: blueprints x aliases). */
  function generateSamples() {
    var samples = [];
    function add(intent, words) { samples.push({ intent: intent, tokens: tokenize(words) }); }
    var nums = ["5", "10", "25", "twenty five", "ninety"];
    var units = ["minute", "minutes", "second", "seconds", "hour"];
    var timerLabels = ["focus", "tea", "workout", "study", "break", "reading"];
    nums.forEach(function (n) {
      units.forEach(function (u) {
        add("timer", n + " " + u + " timer");
        add("timer", n + " " + u + " countdown");
        timerLabels.forEach(function (l) {
          add("timer", n + " " + u + " timer for " + l);
          add("timer", "timer for " + l + " " + n + " " + u);
          add("timer", "set a " + n + " " + u + " timer for " + l);
        });
      });
    });
    add("timer", "pomodoro");
    add("timer", "focus timer");
    ["push ups", "steps", "glasses of water", "pages", "laps"].forEach(function (l) {
      add("counter", "counter for " + l);
      add("counter", "a counter " + l);
      add("counter", "count " + l);
      add("counter", "track my " + l);
    });
    add("counter", "counter");
    var todoHeads = ["todo list", "task list", "shopping list", "errands", "grocery list", "to do list", "checklist"];
    var itemsets = ["rice, eggs and coffee", "buy milk, call ana", "book the train, reply to the venue and buy rice"];
    todoHeads.forEach(function (h) {
      add("todo", h);
      itemsets.forEach(function (items) {
        add("todo", h + " with items: " + items);
        add("todo", h + " with " + items);
      });
    });
    itemsets.forEach(function (items) {
      add("list", "list: " + items);
      add("list", "a list of " + items);
      add("list", "list of " + items);
      add("list", "simple list " + items);
    });
    ["hello there", "welcome to the page", "drink water often", "about this app"].forEach(function (b) {
      add("text", "text: " + b);
      add("text", "a note that says " + b);
      add("text", "intro: " + b);
      add("text", "note " + b);
    });
    return samples;
  }

  var bayesModel = null;
  function trainBayes() {
    if (bayesModel) return bayesModel;
    var classCounts = {};
    var tokenCounts = {};
    var totals = {};
    var vocab = {};
    INTENTS.forEach(function (intent) {
      classCounts[intent] = 0;
      tokenCounts[intent] = {};
      totals[intent] = 0;
    });
    generateSamples().forEach(function (sample) {
      classCounts[sample.intent]++;
      sample.tokens.forEach(function (t) {
        vocab[t] = 1;
        tokenCounts[sample.intent][t] = (tokenCounts[sample.intent][t] || 0) + 1;
        totals[sample.intent]++;
      });
    });
    bayesModel = { classCounts: classCounts, tokenCounts: tokenCounts, totals: totals, vocabSize: Object.keys(vocab).length };
    return bayesModel;
  }

  function classify(model, tokens) {
    var totalSamples = 0;
    INTENTS.forEach(function (intent) { totalSamples += model.classCounts[intent]; });
    var scores = INTENTS.map(function (intent) {
      var logp = Math.log(model.classCounts[intent] / totalSamples);
      tokens.forEach(function (t) {
        var count = model.tokenCounts[intent][t] || 0;
        logp += Math.log((count + 1) / (model.totals[intent] + model.vocabSize));
      });
      return { intent: intent, logp: logp };
    });
    scores.sort(function (a, b) { return b.logp - a.logp; });
    var max = scores[0].logp;
    var probs = scores.map(function (s) {
      return { intent: s.intent, p: Math.exp(s.logp - max) };
    });
    var sum = 0;
    probs.forEach(function (s) { sum += s.p; });
    probs.forEach(function (s) { s.p /= sum; });
    return probs;
  }

  function bayesSlots(intent, sentence, meta, takenKeys, notes) {
    var tokens = tokenize(sentence);
    if (intent === "timer") {
      var seconds = null;
      var labelTokens = [];
      var i = 0;
      while (i < tokens.length) {
        var n = readNumber(tokens, i);
        if (n && n.next < tokens.length && UNITS[tokens[n.next]]) {
          seconds = clampSeconds(n.value, tokens[n.next], notes);
          i = n.next + 1;
          continue;
        }
        if (!GRAMMAR_TIMER_HEADS[tokens[i]] && !ARTICLES[tokens[i]] && tokens[i] !== "for" && tokens[i] !== "of" && tokens[i] !== "set") {
          labelTokens.push(tokens[i]);
        }
        i++;
      }
      if (seconds === null) {
        if (tokens.join(" ").indexOf("pomodoro") !== -1 || tokens.join(" ").indexOf("focus timer") !== -1) {
          notes.push("no duration given for the pomodoro; used 25 minutes");
          return { type: "timer", label: "Focus", seconds: 1500 };
        }
        throw new Error("bayes: timer intent but no duration found");
      }
      return { type: "timer", label: cap(labelTokens.join(" ") || "Timer"), seconds: seconds };
    }
    if (intent === "counter") {
      var clabel = tokens.filter(function (t) {
        return t !== "counter" && t !== "count" && t !== "track" && !ARTICLES[t] && t !== "for" && t !== "my";
      }).join(" ");
      return { type: "counter", label: (clabel || "Count").slice(0, 80) };
    }
    if (intent === "todo") {
      var joined = tokens.join(" ");
      var head = "todo list";
      GRAMMAR_TODO_HEADS.forEach(function (h) {
        if (joined.indexOf(h) !== -1 && h.length > head.length) head = h;
      });
      return todoSection(head, /\b(with|items?)\b/.test(joined) ? sentence.split(/with|items?[:]?/i).pop() : null, notes, meta, takenKeys);
    }
    if (intent === "list") {
      var rest = sentence.indexOf(":") !== -1 ? sentence.slice(sentence.indexOf(":") + 1) : sentence.replace(/^.*?\blist\b\s*(?:of)?\s*/i, "");
      return listSection(rest, notes);
    }
    if (intent === "text") {
      var m = /^(?:a\s+|an\s+)?(text|note|intro|about)\b\s*:?\s*(?:that says\s+)?(.+)$/i.exec(sentence);
      if (!m) throw new Error("bayes: text intent but no body found");
      var heading = { text: "Text", note: "Note", intro: "Intro", about: "About" }[m[1].toLowerCase()];
      return { type: "text", heading: heading, body: stripQuotes(m[2]).slice(0, 2000) };
    }
    throw new Error("bayes: unknown intent");
  }

  var CONFIDENCE_MIN = 0.55;

  function engineBayes(text) {
    var notes = [];
    var model = trainBayes();
    var meta = extractMeta(text, notes);
    var takenKeys = {};
    var sections = [];
    var failed = [];
    meta.leftovers.forEach(function (sentence) {
      var tokens = tokenize(sentence).filter(function (t) { return !ARTICLES[t]; });
      var probs = classify(model, tokens);
      var best = probs[0];
      if (best.p < CONFIDENCE_MIN) {
        failed.push(sentence + " (best guess '" + best.intent + "' scored only " + Math.round(best.p * 100) + "%); refusing to guess below " + Math.round(CONFIDENCE_MIN * 100) + "%");
        return;
      }
      notes.push("'" + sentence.slice(0, 40) + "' -> intent '" + best.intent + "' (confidence score " + Math.round(best.p * 100) + "% - a model score from a tiny trained sample, not a calibrated probability of being right)");
      try {
        sections.push(bayesSlots(best.intent, sentence, meta, takenKeys, notes));
      } catch (e) {
        failed.push(sentence + " (" + e.message + ")");
      }
    });
    if (failed.length) {
      throw new Error("bayes engine could not parse: '" + failed.join("', '") + "'");
    }
    return assemble(meta, sections, notes);
  }

  /* ---------- engine: rules (the ported regex parser) ---------- */

  function engineRules(text) {
    var out = core.describe(text);
    return { recipe: out.recipe, notes: out.notes };
  }

  /* ---------- cascade ---------- */

  var ENGINES = [
    { name: "rules", label: "Rules (regex keywords): exact documented phrasings", run: engineRules },
    { name: "grammar", label: "Grammar parser: number words, flexible word order", run: engineGrammar },
    { name: "template", label: "Template matching: tolerates a typo and filler words", run: engineTemplate },
    { name: "bayes", label: "Statistical (naive Bayes): guesses paraphrases, shows confidence", run: engineBayes },
  ];

  function run(engineName, text) {
    if (engineName !== "auto") {
      var engine = null;
      ENGINES.forEach(function (e) { if (e.name === engineName) engine = e; });
      if (!engine) throw new Error("unknown engine '" + engineName + "'");
      var out = engine.run(text);
      out.engine = engine.name;
      return out;
    }
    var failures = [];
    for (var i = 0; i < ENGINES.length; i++) {
      try {
        var result = ENGINES[i].run(text);
        result.engine = ENGINES[i].name;
        result.notes.unshift("answered by the " + ENGINES[i].name + " engine (strictest match first)");
        return result;
      } catch (e) {
        failures.push(ENGINES[i].name + ": " + e.message);
      }
    }
    throw new Error(
      "no offline method understood the description. Per method: " + failures.join(" | ") +
      ' Supported phrasings include: "a 25 minute timer for X", "pomodoro", "a counter for X", ' +
      '"a todo list with items: a, b and c", "a list: a, b", "text: some words".'
    );
  }

  window.dayaEngines = { ENGINES: ENGINES, run: run };
})();
