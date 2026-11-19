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
`.html` path validated to exclude schemes, hosts and parent traversal
(the published examples use it to link back to the index). Todo lists
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
- daya is not natural-language programming: the recipe is JSON with a
  fixed schema, not free text.
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
