# App code generation experiment

Question: can Daya recipes generate code for our EXISTING apps, not just
standalone mini-apps? First small step (approved 2026-11-24): emit ONE
section for one existing public app, render-tested offline against a
snapshot of the app's real page. The app itself is unchanged; nothing
here is shipped or proposed for the app yet.

## Target pick: kapan

https://vanipy.com/kapan/ — a single-file static GitHub Pages app
(dark theme via CSS custom properties, `.ev` event cards, `.tag` pills,
vanilla JS reading a `#evdata` JSON island). Chosen because it is the
simplest public web app in the fleet and its domain maps naturally onto
a Daya timer section: a countdown to the next event.

## What the emitter does

`emit_section.py` takes a recipe (`recipes/kapan-next-event.json`: a
timer section bound to the page's soonest upcoming event) and writes:

- `out/section-kapan.html` — the fragment, in kapan's markup and style
  conventions (`.day` heading, `.ev` card, `.tag on` countdown pill).
- `out/test-page.html` — the snapshot with the fragment injected before
  the event list, plus a render-test harness (harness is test-only).

Same safety model as dayalib's web domain: recipe strings are data,
never code (HTML-escaped; the only JS is the fixed, reviewed template in
`emit_section.py`). The emitted section reads only the page's own
`#evdata` island; it fetches nothing. The fragment's bytes depend only
on the recipe and the emitter — deterministic, same as the web domain.

## Render test (offline, no network)

`test/render_test.py` loads the test page in headless Chrome with
virtual time and asserts facts the in-page harness records:

- the section is present and uses kapan's own classes
- its title and link match the soonest upcoming event in `#evdata`
- the countdown shows `Nd HH:MM:SS` and actually ticks

Plus a phone-width screenshot (`out/render-phone.png`) inspected
visually: the section reads as a native part of the page.

Result 2026-11-24: all six facts pass; screenshot verified.

## Files and provenance

- `snapshot/kapan-index.html` — public page fetched from
  https://vanipy.com/kapan/ on 2026-11-24 (~11:20 WIB). Test fixture
  only; the live app changes every six hours.
- `recipes/` — input recipes. `out/` — generated evidence.
- `emit_section.py` — Python standard library only, like dayalib.

Run it:

    python3 emit_section.py recipes/kapan-next-event.json snapshot/kapan-index.html out/
    python3 test/render_test.py

## Honest limits

- One section type (timer), one binding (soonest upcoming event), one
  app. This proves the route, not the general case.
- The test page runs the app's real snapshot, but it is a frozen copy:
  live-data refreshes and the city sub-pages are untested.
- The harness asserts DOM facts; visual judgment is from the screenshot
  alone, not from his phone.
- No app change is proposed yet. A real kapan change (if he wants the
  countdown) would be a separate, reviewed step: kapan's page is built
  from its own repo template, so the section belongs there, not pasted
  into the generated HTML.
