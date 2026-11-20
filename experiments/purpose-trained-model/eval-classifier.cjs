#!/usr/bin/env node
/* Held-out eval for the shipped MobileBERT zero-shot classifier route
 * (docs/compose-classifier.js): classify intent with the real ~27 MB model,
 * then extractWithIntent through the classical engines, end to end.
 *
 * NOT part of the page: an offline measurement script. Requires:
 *   npm install @huggingface/transformers@3.7.6 onnxruntime-node@1.21.0 --onnxruntime-node-install-cuda=skip
 * Run:
 *   NODE_PATH=/path/to/node_modules node eval-classifier.cjs
 * Model downloads from huggingface.co on first run (~27 MB, free, no account).
 */
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..", "..");
global.window = {};
require(path.join(ROOT, "docs", "compose-core.js"));
require(path.join(ROOT, "docs", "compose-engines.js"));
require(path.join(ROOT, "docs", "compose-classifier.js"));
const engines = global.window.dayaEngines;
const clf = global.window.dayaClassifier;

const { pipeline, env } = require("@huggingface/transformers");
env.allowLocalModels = false;

function matchTypes(types, c) {
  const sets = c.intents_any || (c.intents ? [c.intents] : null);
  return sets && sets.some(set => set.length === types.length && set.every((t, i) => t === types[i]));
}

(async function main() {
  const pipe = await pipeline("zero-shot-classification", clf.MODEL_ID, { dtype: "q8" });
  const cases = JSON.parse(fs.readFileSync(path.join(__dirname, "heldout.json"), "utf8")).cases;
  const rows = [];
  for (const c of cases) {
    const r = await pipe(c.text, clf.LABELS);
    const label = r.labels[0];
    const score = r.scores[0];
    let outcome;
    try {
      const out = clf.extractWithIntent(label, c.text, (n, t) => engines.run(n, t));
      const types = out.recipe.sections.map(s => s.type);
      const secs = out.recipe.sections.filter(s => s.type === "timer").map(s => s.seconds);
      outcome = { types, engine: out.engine, seconds: secs };
    } catch (e) {
      outcome = { declined: (e.message || String(e)).slice(0, 140) };
    }
    rows.push({ text: c.text, tier: c.tier, refuse: !!c.refuse, intents: c.intents || null, intents_any: c.intents_any || null,
                wantSeconds: c.seconds || null, label, score: +score.toFixed(3), outcome });
    console.log((rows.length) + "/" + cases.length, JSON.stringify(label), score.toFixed(3), JSON.stringify(c.text.slice(0, 50)));
  }

  const summary = { should_parse: 0, correct: 0, declined_design: 0, wrong: 0, refused: 0,
                    should_refuse: 0, refuse_correct: 0, refuse_violated: 0, tiers: {} };
  for (const row of rows) {
    if (row.refuse) {
      summary.should_refuse++;
      if (row.outcome.declined) summary.refuse_correct++;
      else summary.refuse_violated++;
      continue;
    }
    summary.should_parse++;
    const t = summary.tiers[row.tier] = summary.tiers[row.tier] || { n: 0, ok: 0 };
    t.n++;
    if (row.outcome.declined) {
      if (/text notes|quiz/.test(row.label) && /can only extract/.test(row.outcome.declined)) summary.declined_design++;
      else summary.refused++;
      continue;
    }
    let ok = matchTypes(row.outcome.types, row);
    if (ok && row.wantSeconds) {
      const got = row.outcome.seconds;
      ok = got.length === row.wantSeconds.length && row.wantSeconds.every((w, i) => got[i] === w);
    }
    if (ok) { summary.correct++; t.ok++; } else summary.wrong++;
  }
  console.log("\n== classifier route (mobilebert-mnli q8, onnxruntime-node cpu) on heldout.json ==");
  /* label-level intent accuracy (classification only, before extraction) */
  const bucket = { timer: "timer", counter: "counter", "todo list": "listish", checklist: "listish" };
  const lab = { n: 0, ok: 0, per_intent: {} };
  for (const row of rows) {
    if (row.refuse) continue;
    const sets = row.intents_any || [row.intents];
    if (!sets || sets.length !== 1 || sets[0].length !== 1) continue;
    const want = sets[0][0];
    lab.n++;
    lab.per_intent[want] = lab.per_intent[want] || { n: 0, ok: 0 };
    lab.per_intent[want].n++;
    const b = bucket[row.label];
    const ok = (want === "text" && row.label === "text notes") ||
               (b === "listish" && (want === "todo" || want === "list")) ||
               b === want;
    if (ok) { lab.ok++; lab.per_intent[want].ok++; }
  }
  summary.label_accuracy = lab;
  console.log(JSON.stringify(summary, null, 1));
  fs.writeFileSync(path.join(__dirname, "results-classifier.json"), JSON.stringify({ summary, rows }, null, 1));
})().catch(e => { console.error(e); process.exit(1); });
