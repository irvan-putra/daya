#!/usr/bin/env python3
"""Render handwriting with PenGPT and emit a daya web recipe.

Bridges the experiment and dayalib's "handwriting" section: the model
runs here, at authoring time, so the generated app stays a static
self-contained page (inline SVG, no weights, no network). The output
recipe is validated with dayalib itself before it is written.

Usage:
  python3 render_recipe.py input.json output.json

input.json, handwriting mode (default):
  {"text": "hello from daya", "writer": "sam",
   "temperature": 0, "seed": 0, "title": "Handwritten note"}
input.json, drawing mode:
  {"mode": "draw", "text": "a penguin wearing a top hat",
   "temperature": 0.6, "seed": 0, "guidance": 2, "title": "Sketch"}
title is optional (default "Handwritten note" / "Drawing").
Handwriting needs vendor/hand.npz; drawing needs vendor/sketch.npz
and vendor/words.npz (see README). Also needs a Chrome/Chromium binary.
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from websocket import create_connection

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from dayalib.domains import web  # noqa: E402

OUT = os.path.join(HERE, "out")
DRIVER = os.path.join(OUT, "render-recipe.html")
DEBUG_PORT = 9444
LOAD_TIMEOUT_S = 180

DRIVER_HTML = """<!doctype html>
<meta charset="utf-8">
<script type="module">
import {npz, Pen, accelerate, spans} from '../vendor/pengpt-core.js'

const INPUT = __INPUT_JSON__
const facts = {viewbox: null, strokes: null, error: null}
const div = document.createElement('div')
div.id = 'render-test-result'
div.style.display = 'none'
document.body.appendChild(div)

// Same sheet layout as the demo UI (greydanus/pengpt web/index.html,
// Apache-2.0): PAD, TOP, LINE, SPACE and the wrap rule.
const PAD = 0.25, TOP = 0.42, LINE = 0.55, SPACE = 0.16, WIDTH = 8
let x = 0, ln = 0
const strokes = []

function placeWord(p){
  if (!p.length) return
  let lo = Infinity, hi = -Infinity
  for (let i = 0; i < p.length; i += 3) [lo,hi] = [Math.min(lo,p[i]), Math.max(hi,p[i])]
  if (x > 0 && x + hi - lo > WIDTH) [x,ln] = [0, ln+1]
  for (const [a,b] of spans(p)){
    const stroke = []
    for (let i = a; i < b; i++) stroke.push([p[3*i] + x - lo, p[3*i+1] + ln*LINE])
    strokes.push(stroke)
  }
  x += hi - lo + SPACE
}

try {
  const buf = await (await fetch('../vendor/hand.npz')).arrayBuffer()
  const pen = new Pen(await npz(buf))
  await accelerate(pen).catch(() => pen)
  if (!pen.writers.includes(INPUT.writer))
    throw new Error(`unknown hand "${INPUT.writer}" (${pen.writers.length} hands in the model)`)
  for await (const p of pen.write(INPUT.text, INPUT.writer, INPUT.temperature, null, INPUT.seed))
    placeWord(p)
  facts.strokes = strokes
  facts.viewbox = [-PAD, -TOP, WIDTH + 2*PAD, TOP + Math.max(ln, 2)*LINE + 0.3]
} catch (e) {
  facts.error = String(e && e.message || e)
}
div.textContent = JSON.stringify(facts)
</script>
"""


DRAW_DRIVER_HTML = """<!doctype html>
<meta charset="utf-8">
<script type="module">
import {npz, Pen, Words, accelerate, mulberry, spans} from '../vendor/pengpt-core.js'

const INPUT = __INPUT_JSON__
const facts = {viewbox: null, strokes: null, error: null}
const div = document.createElement('div')
div.id = 'render-test-result'
div.style.display = 'none'
document.body.appendChild(div)

try {
  const [pen, words] = await Promise.all([
    (async () => {
      const buf = await (await fetch('../vendor/sketch.npz')).arrayBuffer()
      const p = new Pen(await npz(buf))
      await accelerate(p).catch(() => p)
      return p
    })(),
    (async () => new Words(await npz(await (await fetch('../vendor/words.npz')).arrayBuffer())))(),
  ])
  pen.encoder = text => words.encode(text)
  let latest = null
  const rng = mulberry(INPUT.seed)
  for await (const p of pen.draw(INPUT.text.toLowerCase(), '', INPUT.temperature, null, rng, INPUT.guidance))
    latest = p
  const strokes = spans(latest).map(([a,b]) =>
    Array.from({length: b - a}, (_, i) => [latest[3*(a+i)], latest[3*(a+i)+1]]))
  if (!strokes.length) throw new Error('the model drew nothing')
  facts.strokes = strokes
  // Same fixed sheet as the demo's draw grid (web/index.html, Apache-2.0).
  facts.viewbox = [-0.62, -0.62, 1.24, 1.24]
} catch (e) {
  facts.error = String(e && e.message || e)
}
div.textContent = JSON.stringify(facts)
</script>
"""


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def render(source, mode):
    """Run the model headless; return {"viewbox": ..., "strokes": ...}."""
    os.makedirs(OUT, exist_ok=True)
    template = DRIVER_HTML if mode == "write" else DRAW_DRIVER_HTML
    with open(DRIVER, "w") as f:
        f.write(template.replace("__INPUT_JSON__", json.dumps(source)))

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/out/render-recipe.html" % httpd.server_address[1]

    chrome = subprocess.Popen(
        ["google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
         "--disable-dev-shm-usage", "--remote-debugging-port=%d" % DEBUG_PORT,
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(
                    "http://127.0.0.1:%d/json/list" % DEBUG_PORT, timeout=2))
                pages = [t for t in targets if t.get("type") == "page"]
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                pass
            time.sleep(0.2)
        if not ws_url:
            raise SystemExit("chrome devtools endpoint did not come up")
        ws = create_connection(ws_url, timeout=LOAD_TIMEOUT_S + 30)
        next_id = 0

        def call(method, **params):
            nonlocal next_id
            next_id += 1
            ws.send(json.dumps({"id": next_id, "method": method,
                                "params": params}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == next_id:
                    if "error" in msg:
                        raise RuntimeError(msg["error"])
                    return msg.get("result", {})

        def evaljs(expression):
            r = call("Runtime.evaluate", expression=expression,
                     returnByValue=True, awaitPromise=True)
            return r.get("result", {}).get("value")

        call("Page.enable")
        call("Page.navigate", url=url)
        deadline = time.time() + LOAD_TIMEOUT_S
        while time.time() < deadline:
            raw = evaljs(
                "(document.getElementById('render-test-result')||{textContent:''})"
                ".textContent")
            if raw:
                facts = json.loads(raw)
                break
            time.sleep(1)
        else:
            raise SystemExit("render driver did not report in %ds" % LOAD_TIMEOUT_S)
    finally:
        chrome.terminate()
        httpd.shutdown()

    if facts.get("error"):
        raise SystemExit("render failed: %s" % facts["error"])
    return {"viewbox": facts["viewbox"], "strokes": facts["strokes"]}


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    source = json.load(open(sys.argv[1]))
    mode = source.get("mode", "write")
    if mode not in ("write", "draw"):
        raise SystemExit('mode must be "write" or "draw"')
    text = source["text"]
    if not 1 <= len(text.strip()) <= web.MAX_HANDWRITING_TEXT:
        raise SystemExit("text must be 1..%d chars" % web.MAX_HANDWRITING_TEXT)
    if mode == "write":
        request = {
            "text": text.strip(),
            "writer": source.get("writer", "sam"),
            "temperature": float(source.get("temperature", 0)),
            "seed": int(source.get("seed", 0)),
        }
        section_type = "handwriting"
        default_title = "Handwritten note"
    else:
        request = {
            "text": text.strip(),
            "temperature": float(source.get("temperature", 0.6)),
            "seed": int(source.get("seed", 0)),
            "guidance": float(source.get("guidance", 2)),
        }
        section_type = "drawing"
        default_title = "Drawing"
    rendered = render(request, mode)
    recipe = {
        "domain": "web",
        "title": source.get("title", default_title),
        "sections": [{
            "type": section_type,
            "text": request["text"],
            "viewbox": rendered["viewbox"],
            "strokes": rendered["strokes"],
        }],
    }
    model, errors = web.validate(recipe)
    if errors:
        raise SystemExit("rendered recipe failed dayalib validation: %s" % errors)
    clean_sections = [
        {k: v for k, v in section.items() if v is not None}
        for section in model["sections"]
    ]
    recipe = {
        "domain": "web",
        "title": model["title"],
        "sections": clean_sections,
    }
    with open(sys.argv[2], "w") as f:
        json.dump(recipe, f, indent=2)
        f.write("\n")
    points = sum(len(s) for s in clean_sections[0]["strokes"])
    print("wrote %s: %d strokes, %d points, viewbox %s"
          % (sys.argv[2], len(clean_sections[0]["strokes"]), points,
             clean_sections[0]["viewbox"]))


if __name__ == "__main__":
    main()
