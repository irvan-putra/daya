# Purpose-trained model experiment

Question: can a small model trained for daya's narrow recipe intents beat
(a) the classical cascade and (b) a general zero-shot classifier, on
hand-written paraphrases, using synthetic-only data, free compute and no
model download?

Status: **step 3 completed** — baselines measured, slot filler v0.1 trained,
abstention gate added (no retraining) and both arms measured once on a
fresh held-out set (bottom section). No shipped code, route or download
changed; this directory is offline tooling and its results, nothing else.

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

- 45 held-out cases is small and agent-authored; treat percentages as
  directional, not precise, and not independent external validation.
  The set should grow as real phrasings arrive (from public or
  synthetic sources only, never private chats).
- heldout.json v1 was a genuine held-out set for v0.1's single
  evaluation. Because v0.2's proposals are informed by v0.1's known
  failures on these exact 45 cases, the set is a development benchmark
  from here on: version iterations measured against it are development
  scores, not fresh held-out proof. Any future independent quality
  claim needs a new, separately authored test set that no training,
  tuning or failure analysis has touched.
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

## Purpose-trained slot filler v0.1 (2026-11-20, second sitting)

`slot_filler.py` trains a naive Bayes intent classifier plus a per-token
perceptron slot tagger on slot-annotated synthetic data
(`dataset-slots-train.json`, 865 samples). A disjoint-vocabulary synthetic
validation split (`dataset-slots-valid.json`, 561 samples: unseen timer
labels, counter labels, item sets and text bodies) drove the ONE tuning
decision (epoch count, 12, at validation span F1 0.908). `heldout.json`
was evaluated exactly once for this model version and stays
evaluation-only. Training takes ~1.5 s with the Python standard library
alone; no downloads, no accounts.

Held-out results (the single evaluation run):

- End-to-end: 31/38 (core 16/18, stretch 15/20). Same range as the auto
  cascade (32/38) and ahead of every single classical engine, with no
  hand-written rules for slots.
- Refusal: 2/7. The model has NO abstention mechanism: the classifier
  always picks an intent and the tagger fills it, so "a map of jogja"
  still becomes a counter. Until an abstention gate exists, this
  direction cannot replace the cascade's honest "not understood"; it
  would have to sit behind one.
- Measured gaps from the failure list: no title/accent handling
  ('called "Weekend"' flipped todo to list), typo'd units refuse
  ("minite"), longer multi-clause sentences lose the duration slots
  ("set a timer for 7 minutes so my pasta does not overcook"),
  fraction durations are out of vocabulary ("half an hour").
- v0.1 lesson: B/I tags collapsed the tagger (runaway I- weights on
  global features; validation F1 ~0.10); type-only run tags fixed it
  (0.908). The journey is in git history, not hidden.

## Abstention gate + fresh held-out v2 (2026-11-23, third sitting)

v0.1's blocking gap was refusal (2/7): the model always picks an intent.
`eval_abstain.py` adds a decision layer on the FROZEN v0.1 weights — no
retraining, no model swap:

1. explained-token coverage: every token must be a stopword or carry a
   non-O slot tag; refuse below 0.5 coverage (rule fixed a priori)
2. naive-Bayes top-posterior threshold theta, the ONE numeric knob
3. refuse when no token carries any slot evidence
4. partial timer slots (number without unit or vice versa) refuse, because
   a silently wrong duration is worse than a refusal (finding 2)

theta was calibrated ONLY on synthetic data: dataset-slots-valid.json
(should accept) plus `calib-refuse.json`, 20 agent-authored out-of-scope
probes (tuning data, never evaluation). Sweep in
`results-abstain-calibration.json`; chosen theta 0.7 (valid accept 97.3%,
probe refuse 90%, Youden J 0.873).

`heldout-v2.json` is a NEW hand-authored set (46 cases: 18 core, 18
stretch, 10 should-refuse), disjoint from v1 and from both synthetic
splits. Both arms were evaluated on it exactly once
(`results-abstain-v2.json`); the cascade comparison is
`results-cascade-v2.json`.

| arm (held-out v2)               | end-to-end correct | refusal P / R | gen-acc on accepted |
| ------------------------------- | ------------------ | ------------- | ------------------- |
| raw slot filler v0.1            | 75.0% (27/36; core 16/18, stretch 11/18) | 0.40 / 0.20 | 81.8% |
| **gated slot filler v0.1**      | **69.4% (25/36; core 15/18, stretch 10/18)** | **0.54 / 0.70** | **83.3%** |
| auto cascade (what the page runs) | 75.0% (27/36; core 15/18, stretch 12/18) | 0.63 / 0.50 | 79.4% |

## Findings (step 3)

9. **The raw v0.1 model confirmed its abstention gap on fresh cases:**
   2/10 correct refusals (recall 0.20); it turned "a stopwatch for my
   runs", "wake me at 6am", "play some lofi music" and "asdf qwer zxcv"
   into counters. This reproduces v1's 2/7 on independently written
   inputs, so the gap is a model property, not a v1 artifact.
10. **A decision-layer gate fixed most of it without retraining:**
    refusal recall 0.20 → 0.70 and generation accuracy on accepted inputs
    rose 81.8% → 83.3%, at the cost of 3 wrongly refused should-parse
    cases (precision 0.54): "list: alpha, beta, gamma" and two stretch
    cases. Refusals are honest failures; invented apps are silent ones.
11. **The gate and the cascade refuse differently:** the cascade refused
    5/10 (its bayes fallback still guesses on unrelated text), the gated
    model 7/10; their misses overlap little, so a cascade-of-last-resort
    or union gate could do better than either.
12. **Remaining gate violations are NB-prior artifacts:** the 3 cases that
    still invented apps ("directions to the airport" → text, "a photo
    gallery for my holiday pictures" → counter, "something fun for the
    weekend" → counter) all-score out-of-vocabulary words smoothest
    toward high-token-count intents. A purpose-trained model needs an
    explicit out-of-scope class or OOV-aware scoring, not just
    thresholds.

## Honest limits (step 3 additions)

- heldout-v2.json shares v1's authorship limit: the author had read v1's
  failure analysis, and these 46 cases are now development-contaminated
  for any future iteration. The NEXT quality claim needs a third set.
- The calibration probe set is 20 agent-authored out-of-scope sentences;
  theta=0.7 is tuned on it, so probe_refuse 90% is a tuning-set number.
- The gate's coverage stopword list is English-only by construction.

## Next steps (proposals, not started)

- Abstention v2: an explicit out-of-scope training class (finding 12) and
  a union of the gate with the grammar engine's refusals (finding 11).
  Tune only on synthetic data; measure on a third fresh held-out set.
- An abstention gate for the classifier route too: correct hears scored
  0.40-0.95 here, several wrong hears scored under 0.5, but "countdown
  of 90 seconds" scored 0.506, so a threshold needs care.
- Slot-filler v0.2 (paused 2026-11-20 after v0.1 completed the bounded
  experiment): title/accent meta handling, typo-tolerant units,
  robustness on multi-clause sentences, fraction durations. Tune only
  on synthetic valid; heldout.json v1 reports development scores only
  (see Honest limits).
- Fix the cascade's out-of-scope guessing (finding 1), the colon-form
  todo heads (finding 3) and the half-hour misparse (finding 2) in the
  classical engines, with regression fixtures from heldout.json.
- Unit aliases ("mins") and fraction durations ("a minute and a half").
