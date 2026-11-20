#!/usr/bin/env node
/* Eval harness for the purpose-trained-model experiment.
 *
 * Loads the SHIPPED engines (docs/compose-core.js + docs/compose-engines.js,
 * read-only, no modifications) and scores them on a split file:
 *   - dataset-train.json : synthetic training split (coverage sanity check)
 *   - heldout.json       : hand-authored paraphrases (the number that matters)
 *
 * Arms:
 *   engines : rules, grammar, template, bayes, auto (end-to-end: recipe must
 *             parse AND section types match expected AND timer seconds match)
 *   nb-full : a standalone multinomial naive Bayes intent classifier trained
 *             here on dataset-train.json (harness-only, NOT shipped)
 *   nb-tiny : the same classifier trained on a small per-intent subset,
 *             approximating the data scale of the page's built-in samples
 *
 * Usage: node eval.cjs <split.json> [--nb-train <dataset-train.json>]
 */
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
global.window = {};
require(path.join(ROOT, "docs", "compose-core.js"));
require(path.join(ROOT, "docs", "compose-engines.js"));
const engines = global.window.dayaEngines;

const splitPath = process.argv[2];
const nbTrainIdx = process.argv.indexOf("--nb-train");
const nbTrainPath = nbTrainIdx !== -1 ? process.argv[nbTrainIdx + 1] : null;
const split = JSON.parse(fs.readFileSync(splitPath, "utf8"));

/* Normalize to a common case shape: {text, refuse, tier, intentSets, seconds} */
function casesOf(split) {
  const raw = split.cases || split.samples.map(s => ({
    text: s.text, tier: "train", intents: [s.intent], seconds: s.seconds != null ? [s.seconds] : null,
  }));
  return raw.map(c => ({
    text: c.text,
    tier: c.tier || "train",
    refuse: !!c.refuse,
    intentSets: c.intents_any ? c.intents_any : (c.intents ? [c.intents] : null),
    seconds: c.seconds || null,
  }));
}
const cases = casesOf(split);

function check(recipe, c) {
  const types = recipe.sections.map(s => s.type);
  const match = c.intentSets.some(set =>
    set.length === types.length && set.every((t, i) => t === types[i]));
  if (!match) return { ok: false, why: "intents " + JSON.stringify(types) };
  if (c.seconds) {
    const timers = recipe.sections.filter(s => s.type === "timer");
    const want = c.seconds;
    if (timers.length !== want.length || !want.every((w, i) => timers[i].seconds === w)) {
      return { ok: false, why: "seconds " + JSON.stringify(timers.map(t => t.seconds)) + " want " + JSON.stringify(want) };
    }
  }
  return { ok: true };
}

function evalEngine(name, cases) {
  const r = { engine: name, should_parse: 0, correct: 0, wrong_recipe: 0, refused: 0,
              should_refuse: 0, refuse_correct: 0, refuse_violated: 0, failures: [], tiers: {} };
  for (const c of cases) {
    let recipe = null, err = null;
    try { recipe = engines.run(name, c.text).recipe; } catch (e) { err = e.message; }
    if (c.refuse) {
      r.should_refuse++;
      if (err) r.refuse_correct++;
      else { r.refuse_violated++; r.failures.push({ text: c.text, got: "parsed " + JSON.stringify(recipe.sections.map(s=>s.type)) }); }
      continue;
    }
    r.should_parse++;
    const t = r.tiers[c.tier] = r.tiers[c.tier] || { should_parse: 0, correct: 0 };
    t.should_parse++;
    if (err) { r.refused++; r.failures.push({ text: c.text, got: "refused: " + err.slice(0, 110) }); }
    else {
      const res = check(recipe, c);
      if (res.ok) { r.correct++; t.correct++; }
      else { r.wrong_recipe++; r.failures.push({ text: c.text, got: res.why }); }
    }
  }
  return r;
}

/* ---- standalone naive Bayes arm (same tokenization/smoothing as the page) ---- */
const ARTICLES = { a:1, an:1, the:1, my:1, another:1, please:1, make:1, me:1, create:1, build:1, want:1, i:1, add:1, give:1, can:1, you:1 };
const tokenize = s => s.toLowerCase().replace(/["']/g, "").split(/[^a-z0-9]+/).filter(Boolean).filter(t => !ARTICLES[t]);

function trainNB(samples) {
  const classCounts = {}, tokenCounts = {}, totals = {}, vocab = {};
  for (const s of samples) {
    classCounts[s.intent] = (classCounts[s.intent] || 0) + 1;
    tokenCounts[s.intent] = tokenCounts[s.intent] || {};
    for (const t of tokenize(s.text)) {
      vocab[t] = 1;
      tokenCounts[s.intent][t] = (tokenCounts[s.intent][t] || 0) + 1;
      totals[s.intent] = (totals[s.intent] || 0) + 1;
    }
  }
  const intents = Object.keys(classCounts);
  const totalSamples = intents.reduce((a, i) => a + classCounts[i], 0);
  const vocabSize = Object.keys(vocab).length;
  return function classify(text) {
    const tokens = tokenize(text);
    let best = null;
    for (const intent of intents) {
      let logp = Math.log(classCounts[intent] / totalSamples);
      for (const t of tokens) {
        const count = (tokenCounts[intent] || {})[t] || 0;
        logp += Math.log((count + 1) / ((totals[intent] || 0) + vocabSize));
      }
      if (!best || logp > best.logp) best = { intent, logp };
    }
    return best.intent;
  };
}

function evalNB(classify, cases) {
  const r = { should_parse: 0, intent_correct: 0, per_intent: {}, misses: [] };
  for (const c of cases) {
    if (c.refuse) continue;               /* NB arm has no refusal mechanism */
    if (!c.intentSets || c.intentSets.length !== 1 || c.intentSets[0].length !== 1) continue; /* single-intent only */
    const want = c.intentSets[0][0];
    const got = classify(c.text);
    r.should_parse++;
    r.per_intent[want] = r.per_intent[want] || { n: 0, ok: 0 };
    r.per_intent[want].n++;
    if (got === want) { r.intent_correct++; r.per_intent[want].ok++; }
    else r.misses.push({ text: c.text, want, got });
  }
  return r;
}

const out = { split: path.basename(splitPath), engines: {}, nb: {} };
for (const name of ["rules", "grammar", "template", "bayes", "auto"]) {
  out.engines[name] = evalEngine(name, cases);
}
if (nbTrainPath) {
  const train = JSON.parse(fs.readFileSync(nbTrainPath, "utf8")).samples;
  out.nb["nb-full"] = evalNB(trainNB(train), cases);
  const tiny = [];
  const perIntent = {};
  for (const s of train) {
    perIntent[s.intent] = perIntent[s.intent] || 0;
    if (perIntent[s.intent] < 40) { tiny.push(s); perIntent[s.intent]++; }
  }
  out.nb["nb-tiny"] = evalNB(trainNB(tiny), cases);
  out.nb_train = { full: train.length, tiny: tiny.length };
}

const pct = (a, b) => b ? (100 * a / b).toFixed(1) + "%" : "-";
console.log("== engines on " + out.split + " ==");
for (const [name, r] of Object.entries(out.engines)) {
  console.log(name.padEnd(9),
    "parse-acc " + pct(r.correct, r.should_parse),
    "(" + r.correct + "/" + r.should_parse + ")",
    "wrong " + r.wrong_recipe, "refused " + r.refused,
    "| refuse-acc " + pct(r.refuse_correct, r.should_refuse),
    "(" + r.refuse_correct + "/" + r.should_refuse + ")",
    JSON.stringify(Object.fromEntries(Object.entries(r.tiers).map(([k, v]) => [k, v.correct + "/" + v.should_parse]))));
}
for (const [name, r] of Object.entries(out.nb)) {
  console.log(name.padEnd(9), "intent-acc " + pct(r.intent_correct, r.should_parse),
    "(" + r.intent_correct + "/" + r.should_parse + ")",
    JSON.stringify(Object.fromEntries(Object.entries(r.per_intent).map(([k, v]) => [k, v.ok + "/" + v.n]))));
}
if (process.argv.includes("--failures")) {
  for (const [name, r] of Object.entries(out.engines)) {
    console.log("\n-- " + name + " failures --");
    r.failures.forEach(f => console.log("  " + JSON.stringify(f.text), "->", f.got));
  }
  for (const [name, r] of Object.entries(out.nb)) {
    console.log("\n-- " + name + " misses --");
    r.misses.forEach(m => console.log("  " + JSON.stringify(m.text), "want", m.want, "got", m.got));
  }
}
const jsonOut = process.argv[process.argv.indexOf("--json-out") + 1];
if (process.argv.includes("--json-out")) fs.writeFileSync(jsonOut, JSON.stringify(out, null, 1));
