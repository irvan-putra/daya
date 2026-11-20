# Purpose-trained model experiment

Question: can a small model trained for daya's narrow recipe intents beat
(a) the classical cascade and (b) a general zero-shot classifier, on
hand-written paraphrases, using synthetic-only data, free compute and no
model download?

Status: **step 1 done** — dataset, held-out set and baselines measured.
No shipped code, route or download changed; this directory is offline
tooling and its results, nothing else.

Approved scope (WhatsApp 2026-11-19, "yes, add all as options"):
synthetic-only data, no paid compute, no new accounts, no private data,
no quality claims without held-out paraphrase results.

## Pieces

- `generate_dataset.py` — deterministic blueprint cross-product (no
  randomness; same script, same dataset) with richer slots than the
  page's built-in sample generator. Writes `dataset-train.json`
  (v2: 1,579 samples, 5 intents, roughly balanced).
- `heldout.json` — 45 hand-authored cases, **written by hand, not
  derived from the blueprints** (so template leak cannot inflate
  scores): 18 core (documented-adjacent phrasings), 20 stretch
  (plausible wording beyond the current spec; misses here are product
  gaps, not engine bugs) and 7 should-refuse. Scores on this set are
  the ones that matter.
- `eval.cjs` — loads the shipped engines read-only
  (`docs/compose-core.js` + `docs/compose-engines.js`) and scores a
  split. An engine answer is correct only if the recipe parses AND the
  section types match AND any expected timer seconds match; refusal
  correctness is measured on the should-refuse cases. The `nb-full` /
  `nb-tiny` arms train a standalone multinomial naive Bayes in-harness
  (not shipped) on the synthetic split for intent-only accuracy.
  Usage: `node eval.cjs heldout.json --nb-train dataset-train.json`
- `eval-classifier.cjs` — end-to-end measurement of the shipped
  MobileBERT zero-shot route (`docs/compose-classifier.js`) on
  `heldout.json`. Needs `npm install @huggingface/transformers@3.7.6
  onnxruntime-node@1.21.0 --onnxruntime-node-install-cuda=skip`; the
  model downloads from huggingface.co on first run (~27 MB, free, no
  account).

## Results (2026-11-20; heldout.json v1, dataset-train.json v2)

| method                                  | end-to-end correct | refused correctly |
| --------------------------------------- | ------------------ | ----------------- |
| rules (regex)                           | 39.5% (15/38)      | 6/7               |
| grammar parser                          | 63.2% (24/38)      | 7/7               |
| template matching                       | 23.7% (9/38)       | 7/7               |
| bayes (shipped tiny samples)            | 65.8% (25/38)      | 5/7               |
| **auto cascade (what the page runs)**   | **84.2% (32/38)**  | **4/7**           |
| classifier route, end-to-end            | 55.3% (21/38)      | 7/7               |

| intent classification only (35 single-intent cases) | accuracy |
| --------------------------------------------------- | -------- |
| naive Bayes on 1,579 synthetic samples (nb-full)    | 97.1%    |
| naive Bayes on 200 synthetic samples (nb-tiny)      | 88.6%    |
| MobileBERT-MNLI zero-shot (~27 MB download)         | 85.7%    |

End-to-end splits: rules core 11/18, stretch 4/20; grammar 15/18, 9/20;
template 6/18, 3/20; bayes 14/18, 11/20; auto 16/18, 16/20; classifier
route 13/18, 8/20. Full per-case rows: `results-heldout.json`,
`results-classifier.json`, `results-train.json`.

## Findings

1. **The cascade invents apps for out-of-scope text** (refused only
   4/7): "a map of jogja" became a counter, "a video player for my
   clips" became a counter, "a quiz about world capitals" became a text
   section. Causes: the bayes fallback guesses above its 55% threshold
   on unrelated text, and the rules "about" text head fires on any
   sentence containing "about". The intent-gated classifier route
   refused all 7 — its gate blocks exactly this failure mode.
2. **Grammar silently misreads "half an hour timer" as 3600 s** ("an
   hour" = 1 hour; "half" is dropped). A silently wrong duration is
   worse than a refusal. The classifier route accepted the same
   misparse: an intent gate cannot catch slot errors.
3. **Colon-form todo heads are a systematic gap**: "packing list: a,
   b", "groceries: a, b", "todo list: a, b" parse as a plain list or
   refuse in every engine (also 162/162 of the cascade's wrong answers
   on the train split).
4. **The shipped tiny-sample bayes calls countdowns with unseen numbers
   "counter"** (53/53 such train-split cases): a Laplace-smoothing
   artifact of 21 counter vs 500+ timer training samples.
5. **Grammar fires on head words inside text bodies**: "text: a tiny
   page for tiny tasks" becomes a todo (it hears "tasks").
6. **The template unit slot has no typo tolerance**: "a 15 minite
   timer" declines, although literals tolerate one edit.
7. **Extraction, not classification, is the classifier route's
   bottleneck**: it heard the right intent in 30/35 cases (85.7%) but
   reached a correct recipe in only 21/38 (55.3%); 13 declines were the
   classical extractors failing on a correctly-heard intent. A
   purpose-trained slot filler addresses exactly this gap.
8. **On this narrow domain, a purpose-trained naive Bayes beat the
   27 MB general zero-shot model** on held-out intent accuracy
   (97.1% vs 85.7%), with no download, and data scale mattered
   (nb-tiny 88.6% vs nb-full 97.1%).

## Honest limits

- 45 held-out cases is small; treat percentages as directional, not
  precise. The set should grow as real phrasings arrive (from public or
  synthetic sources only, never private chats).
- The nb arms measure intent only and have no refusal mechanism; the
  engines are measured end-to-end, a harder task. The 97.1% is not
  comparable to the engines' 84.2% one-to-one.
- dataset-train.json labels are the semantic intents of synthetic
  blueprints; some blueprint phrasings ("todo list: a, b") are ones
  today's engines mis-handle. Engine scores on the train split measure
  coverage of the synthetic distribution, not a target to maximize.
- The classifier-route run used the q8 ONNX model on a desktop CPU via
  onnxruntime-node; the page runs the same model in the browser.
  Classification speed here is not a phone-speed measurement.
- Nothing here changed shipped code, routes or downloads.

## Next steps (proposals, not started)

- Purpose-trained slot filler (intent + duration/items/label) trained
  on the synthetic split and evaluated on held-out, running free
  (candidates: CRF-style tagger, tiny seq2seq).
- An abstention gate for the classifier route: correct hears scored
  0.40-0.95 here, several wrong hears scored under 0.5, but "countdown
  of 90 seconds" scored 0.506, so a threshold needs care.
- Fix the cascade's out-of-scope guessing (finding 1), the colon-form
  todo heads (finding 3) and the half-hour misparse (finding 2) in the
  classical engines, with regression fixtures from heldout.json.
- Unit aliases ("mins") and fraction durations ("a minute and a half").
