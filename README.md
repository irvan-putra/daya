# daya

Deterministic code generator: a chatbot (or a person) writes a small
structured recipe, daya validates it and compiles it into working code.
Same recipe in, byte-identical code out.

The idea: a chatbot that cannot write code can still fill in a small
structured form. Deterministic tools do the rest. Validation reports
every problem with a field path, so the chatbot can fix its recipe and
try again without human help.

## Quickstart

No dependencies, no install. Python 3 standard library only.

```sh
./daya build examples/focus-timer.json -o focus-timer.html
./daya validate examples/reading-quiz.json
./daya domains
./daya schema web
```

Open the generated `.html` in any browser. It is one self-contained
file that works offline.

## How it works

1. A recipe is a small JSON object with a `domain` field.
2. The domain pack validates the whole recipe and lists every problem
   with a path (`sections[2].choices: must be a list of 2..6 choices`).
3. A valid recipe compiles through fixed, reviewed templates. Generated
   output passes a self-check before it is written.

## From words to a recipe: daya describe (route 1 of 3)

`daya describe` turns a short plain-text description into a valid web
recipe. It is a **bounded rule-based parser**: a fixed set of documented
phrasings is recognized, anything else is reported as "not understood"
instead of guessed, and the same text always yields the same recipe.
No network, no AI service, no cost. The parsed recipe passes the same
validation as a hand-written one before it is printed, so a description
can never produce a recipe the schema would reject.

```sh
./daya describe 'a 25 minute timer for focus, called "Focus"'
./daya describe 'a todo list with items: buy rice, call ana and book the train, called "Errands"' -o errands.json
./daya build errands.json -o errands.html
```

Recognized phrasings (case-insensitive), one per sentence:

- `... called "Name"` / `named` / `titled` — the page title
- `description: ...` / `described as ...` — the description
- a color name (`indigo`, `blue`, `violet`, `rose`, `green`, `slate`) —
  the accent
- `a 25 minute timer for X` / `countdown of 90 seconds` / `pomodoro`
  (durations clamp to the schema's 5..3600 second range, with a note)
- `a counter` / `a counter for X`
- `a todo list` / `task list` / `shopping list ...`
  (`with items: a, b and c` seeds the list; a deterministic storage key
  is derived from the title)
- `a list: a, b and c` — a static list
- `text: ...` / `a note that says ...` — a text section

Anything unrecognized is listed as a note and ignored; a description
with no recognized sections fails with the list of supported phrasings.

This is route 1 (deterministic) of three text-to-recipe routes. The
`docs/compose.html` page (served at `/daya/compose.html`) offers all
three in the browser. The deterministic side is not one method but a
cascade of four offline engines, strictest first (the Snips NLU
pattern: deterministic parser first, statistical fallback; per Snips'
own write-up, deep models gave no gain over classical ones for this
kind of task - https://medium.com/snips-ai/an-introduction-to-snips-nlu-the-open-source-library-behind-snips-embedded-voice-platform-b12b1a60a41a):

1. `rules` - the regex keyword parser (a JS port of `daya describe`,
   parity-tested against fixtures in `tests/compose_fixtures.json`).
2. `grammar` - a small recursive-descent parser: number words
   ("twenty five minutes"), flexible word order ("timer for tea of 10
   minutes").
3. `template` - Chatito-style template/slot matching
   (https://github.com/rodrigopivi/Chatito) that tolerates one typo per
   word (including adjacent transpositions) and filler words.
4. `bayes` - a multinomial naive Bayes intent classifier trained in the
   page on samples generated from the same blueprints (no download),
   with rule slot filling; it reports its confidence per sentence and
   refuses to guess below a threshold.

`auto` tries them strictest first and says which engine answered; when
nothing matches, the error lists each method's reason. Every engine's
output passes the same schema validation. Rules, grammar and template
are exact only within their own grammars: an ambiguous description can
match an unintended template, so the recipe deserves a read before
building. The bayes number is a confidence score from a tiny in-page
training sample, not a calibrated probability of correctness, and the
fixture tests pin behavior on covered cases - they do not establish
semantic quality beyond them. The other two routes:
browser-provided AI (Chrome's
built-in model API, feature-detected; today it exists only on some
desktop Chrome installs, not on Android or iOS), and a small open model
(SmolLM2-360M-Instruct, ~219 MB, Apache-2.0) running in the page via
wllama/WebAssembly - downloaded from Hugging Face only on an explicit
tap, with the size shown first. Every route validates its output
against the same web schema in the page before showing it; the AI
routes retry at most 3 times and then show the validator's errors
as-is. The in-page model is chosen by real in-browser testing
(2026-11-19, all through the production page's own UI, single-thread
wasm on a desktop CPU): SmolLM2-135M (101 MB) answered a shopping-list
description with a schema-valid but wrong timer section, with both the
one-example and two-example prompts. Qwen2.5-0.5B (469 MB) produced the
correct list section but was rejected for its download size.
SmolLM2-360M imitated the wrong shape under the one-example
prompt, then produced the correct todo section with all items once the
prompt carried two examples - verified at its Q4_K_M (271 MB),
Q3_K_M (235 MB) and Q2_K (219 MB) quants (one attempt each, ~66-96 s
of inference). The page ships the Q2_K file. That is
one passing sample, not a reliability claim: speed and output quality
on phones remain untested, and the deterministic route is the reliable
default.
Model revision and sha256 are pinned in the page source.

A fourth, manual route needs no AI support in the browser at all: the
page builds a prompt (your description plus the schema and one example)
for you to copy into any AI chatbot, and validates the answer you paste
back against the same schema before showing it. Nothing is sent
anywhere by the page; the chatbot runs wherever you paste the prompt,
and validation checks the recipe's shape, not that the chatbot
understood the description.

The compose page is
hand-written tooling: pages generated from recipes keep their
self-contained, no-network property.

## Demo

The example recipes are published from `docs/`: `focus-timer.html`,
`reading-quiz.html` and `shared-list.html` as pages, plus
`shared-list-v0.1.1.xdc`, the same list packaged as a mini-app zip.

## Domains

- `web` — one self-contained HTML mini-app: styled text, lists,
  counters, quizzes, timers (with pause, resume and reset) and todo
  lists (add, tick done, archive instead of delete, restore; the list
  persists in the browser's local storage). No links, no images, no
  custom code: the only JavaScript is a fixed template, and every recipe
  string is data that gets escaped before it reaches the page.
- `webxdc` — wraps a `web` recipe into a complete `.xdc` mini-app (a
  zip with `index.html` and `manifest.toml`), the file format DeltaChat
  mini-apps use. Manifest strings are character-restricted so a recipe
  cannot inject TOML. No icon support yet, generated apps keep state on
  the device (no webxdc sync), and the generated `.xdc` has not yet
  been validated inside a chat client.
- `intodo-view` (proposal stage) — one focus-view page for the intodo
  webxdc shared list. The page holds no state of its own: it renders
  immutable snapshots from an owner-authored headless controller and
  writes only through the controller's commands, so merge, sync and
  restore semantics stay exactly the app's own. self_check rejects any
  output referencing localStorage, webxdc, MergeDoc or sendUpdate. No
  app uses this output yet; the controller contract is pending the
  intodo owner's confirmation.

More domains are planned (CLI tools, automations, app screens). Each
domain is a small pack: schema, templates, checks.

The `todo` section is the first piece aimed at an existing app: it
models the core list behavior of
[intodo](https://github.com/irvan-putra/intodo) (add, done, archive
instead of delete) as a generated companion with its own independent
storage. It is not an intodo data client: it does not read, write or
sync intodo's lists. Applying generated code to an app remains a
separate, reviewed step.

## Security

Generated pages make no network requests and contain no images or
forms. The one link exception is the optional `back` field: a relative
`.html` path validated to exclude schemes, hosts and parent traversal,
or the literal `"./"` for the directory index (the published examples
use it to link back to the index). Todo lists
keep their state in the browser's local storage under the recipe's
`storage_key`; nothing leaves the browser. Recipe
strings never enter the JavaScript block: the script
is a fixed template and a test asserts the shipped script matches it
byte for byte. Interactive behaviour is driven by `data-*` attributes
holding validated whole numbers or validated slugs.

Tested threat scope: HTML markup injection, attribute injection via
quotes, `</script>` breakout, and oversized inputs, via explicit cases
plus a 200-round seeded adversarial fuzz. JavaScript string injection
and U+2028/U+2029 line-separator escapes do not apply because no recipe
data reaches the script block. This is a tested scope statement, not an
absolute guarantee.

## Honest limits

- daya removes the need to write code, not the need to describe the
  right result. A valid recipe can still be the wrong app.
- Deterministic generation covers only what a domain schema describes.
  Anything outside it needs a new domain or a new schema version.
- `daya describe` is not natural-language understanding: it recognizes
  the documented phrasings above and honestly reports the rest as not
  understood. Free-language input is the compose page's AI routes,
  whose phone performance and output quality are untested.
- A generated todo list persists only in the browser where it was used;
  there is no sync between devices or people.
- A generated `.xdc` has no icon yet, and its state stays on each
  device: no webxdc sync, no shared state.

## Development

```sh
python3 -m unittest discover -s tests -v
```

Tests cover validation, byte-for-byte determinism, escaping and script
injection (including a seeded adversarial fuzz), bounds, and the CLI.

Live-browser interaction tests (counter, quiz right and wrong, timer
start/pause/resume/expiry/restart/reset, todo add/toggle/archive/
restore and storage load/save) run in headless Chrome:

```sh
python3 tests/browser_test.py
```

The intodo-view pack has its own browser suite against a mock
controller (loading and ready states, rendering, add/done commands,
markup-injection safety):

```sh
python3 tests/browser_test_view.py
```

## License

AGPL-3.0, see LICENSE.
