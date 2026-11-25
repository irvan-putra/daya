#!/usr/bin/env python3
"""Offline render test for an emitted pengpt handwriting page.

Serves the experiment root over local HTTP (the page imports an ES
module and fetches weights, so file:// will not do), loads
out/test-page.html in headless Chrome, waits for the in-page harness to
record its facts into #render-test-result (inference is real compute,
so we poll over CDP instead of trusting a virtual-time budget), asserts
each fact, and writes a phone-width screenshot for visual inspection.
No network beyond localhost: the weights are the vendored hand.npz.

Usage: python3 test/render_test.py
Exit 0 with PASS lines, or 1 naming the failed facts.
"""
import base64
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
ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "out")
TEST_PAGE = os.path.join(OUT, "test-page.html")
DOM_DUMP = os.path.join(OUT, "rendered-dom.html")
SCREENSHOT = os.path.join(OUT, "render-phone.png")
DEBUG_PORT = 9333
LOAD_TIMEOUT_S = 180

EXPECTED_FACTS = ["weights_loaded", "writer_ok"]


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class CDP:
    def __init__(self, ws_url):
        self.ws = create_connection(ws_url, timeout=LOAD_TIMEOUT_S + 30)
        self.next_id = 0

    def call(self, method, **params):
        self.next_id += 1
        mid = self.next_id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError("%s: %s" % (method, msg["error"]))
                return msg.get("result", {})

    def eval(self, expression):
        r = self.call("Runtime.evaluate", expression=expression,
                      returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")


def main():
    if not os.path.exists(TEST_PAGE):
        raise SystemExit("run emit_handwriting.py first: %s missing" % TEST_PAGE)

    os.chdir(ROOT)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/out/test-page.html" % port

    chrome = subprocess.Popen(
        ["google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
         "--disable-dev-shm-usage", "--remote-debugging-port=%d" % DEBUG_PORT,
         "--window-size=420,900", "about:blank"],
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

        cdp = CDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Page.navigate", url=url)

        deadline = time.time() + LOAD_TIMEOUT_S
        facts = None
        while time.time() < deadline:
            raw = cdp.eval(
                "(document.getElementById('render-test-result')||{textContent:null})"
                ".textContent")
            if raw:
                facts = json.loads(raw)
                break
            time.sleep(1)
        if facts is None:
            dom = cdp.eval("document.documentElement.outerHTML") or ""
            with open(DOM_DUMP, "w") as f:
                f.write(dom)
            raise SystemExit("render-test harness did not report in %ds; see %s"
                             % (LOAD_TIMEOUT_S, DOM_DUMP))

        cdp.call("Emulation.setDeviceMetricsOverride", width=420, height=900,
                 deviceScaleFactor=2, mobile=True)
        time.sleep(0.5)
        shot = cdp.call("Page.captureScreenshot", format="png")
        with open(SCREENSHOT, "wb") as f:
            f.write(base64.b64decode(shot["data"]))
    finally:
        chrome.terminate()
        httpd.shutdown()

    failures = []
    for key in EXPECTED_FACTS:
        ok = facts.get(key) is True
        print("%s %s" % ("PASS" if ok else "FAIL", key))
        if not ok:
            failures.append(key)
    print("error: %r" % facts.get("error"))
    print("writers in model: %s" % facts.get("writers_count"))
    print("words written: %s" % facts.get("words_written"))
    print("strokes: %s, points: %s" % (facts.get("path_count"),
                                       facts.get("point_total")))
    print("inference+load: %.2f s" % (facts.get("ms", 0) / 1000.0))
    print("viewbox: %s" % facts.get("viewbox"))
    print("screenshot: %s" % SCREENSHOT)
    if facts.get("error"):
        raise SystemExit("page reported error: %s" % facts["error"])
    if not facts.get("words_written") or not facts.get("path_count"):
        failures.append("no_output")
    if failures:
        raise SystemExit("FAILED: %s" % ", ".join(failures))
    print("all render-test facts pass")


if __name__ == "__main__":
    main()
