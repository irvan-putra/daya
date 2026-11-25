# pengpt handwriting (experiment)

Can a Daya recipe drive PenGPT's 6 MB handwriting model to render a
handwriting section as SVG? Yes: this experiment emits a self-contained
test page that loads the released `hand.npz` weights in the browser,
writes the recipe text with the recipe's chosen hand, and draws the
strokes into a ruled SVG sheet. Approved by the user on 2026-11-25;
free/synthetic only, no app changes, no retraining.

- PenGPT: https://greydanus.github.io/2026/11/12/pengpt/ (Sam Greydanus)
- Code: https://github.com/greydanus/pengpt (Apache-2.0)
- Weights: release `models-2026-11-16`, `hand.npz` (5,800,624 bytes,
  sha256 `4470544dc428d1da41a7c5c6096652556b1dc6afc4c87d1ccd1ee62716153514`)

## Layout

- `emit_handwriting.py` — validates a recipe and emits the test page.
  Same safety model as `dayalib` and `app-codegen`: recipe values are
  data, never code. The only JavaScript is the fixed template plus the
  vendor core.
- `recipes/hello-hand.json` — the recipe under test (text, hand,
  temperature, seed; deterministic at temperature 0).
- `vendor/pengpt-core.js` — the inference core extracted **verbatim**
  from the demo's `web/index.html` (everything from `const DIRECTIONS`
  to just before the `if (typeof document !== 'undefined')` UI block),
  plus a header noting provenance. To reproduce: fetch
  `web/index.html` from greydanus/pengpt, cut that range, add `export`
  to `Pen`, `Words`, `accelerate`, `backend`, `mulberry`, `npz`,
  `part`, `spans`.
- `vendor/LICENSE-pengpt.txt` — Apache-2.0 license from greydanus/pengpt.
- `test/render_test.py` — serves the experiment root locally, drives
  headless Chrome over CDP, waits for the page's fact harness, asserts
  the facts, writes a phone-width screenshot.
- `render_recipe.py` — the bridge into dayalib: renders text with the
  model at authoring time and writes a daya `web` recipe whose
  `handwriting` section carries the laid-out strokes as validated
  numbers. The generated app inlines them as SVG; it needs no model
  and no network. Example: `examples/handwritten-note.json`.
- `out/` — last emitted page, dumped DOM, screenshot (committed as
  evidence).

Not committed (`.gitignore`): `vendor/hand.npz` (download from the
release above and check the sha256) and `vendor/web-*` (unmodified
greydanus sources kept locally for reference; `pengpt-core.js` is the
committed extract).

## Run

```
# one-time: fetch the weights
curl -L -o vendor/hand.npz \
  https://github.com/greydanus/pengpt/releases/download/models-2026-11-16/hand.npz
sha256sum vendor/hand.npz   # expect 4470544d...

python3 emit_handwriting.py recipes/hello-hand.json out/test-page.html
python3 test/render_test.py
```

The test asserts the weights load, the requested hand exists in the
model, and words/strokes/points were produced, then writes
`out/render-phone.png` for visual inspection. Reference run: "hello
from daya", hand `sam`, temperature 0, seed 0 -> 3 words, 3 strokes,
402 points, ~0.4 s of inference on this machine; 1,193 hands in the
model.

## Recipe schema

`type` must be `"handwriting"`. `text` 1..280 chars (required).
`writer` hand name, default `"sam"` (validated against the model's
1,193 hands at runtime; unknown hands fail the render test).
`temperature` 0..1, default 0 (0 = deterministic greedy).
`seed` non-negative int, default 0.

## Honest limits

- Static render: the demo animates the pen; this draws complete strokes.
- Weights are fetched separately (sha256 above), not committed; the
  render test needs them present.
- `hand.npz` only does handwriting. The 76 MB `pengpt.npz` adds
  drawing/sketching and streaming range-request loading; not used here.
- The weights have no separate license document; the repo is
  Apache-2.0 and the post describes the weights as open. Attribution
  is kept in `vendor/` regardless.
- The SVG layout constants and path helpers in the template are copied
  from the demo's UI (Apache-2.0) with the animation queue removed.
- The `handwriting` section type now lives in `dayalib`'s web domain
  (approved 2026-11-25): the recipe carries pre-rendered strokes, the
  generator only validates and draws them. Publishing a live example
  page is still a separate step.
