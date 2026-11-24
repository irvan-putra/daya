#!/usr/bin/env python3
"""Offline render test for an emitted app section.

Loads out/test-page.html in headless Chrome (virtual time so the
countdown ticks), reads the #render-test-result facts the in-page
harness recorded, asserts each one, and writes a screenshot for visual
inspection. No network: the page is a local snapshot plus the fragment.

Usage: python3 test/render_test.py
Exit 0 with PASS lines, or 1 naming the failed facts.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out")
TEST_PAGE = os.path.join(OUT, "test-page.html")
DOM_DUMP = os.path.join(OUT, "rendered-dom.html")
SCREENSHOT = os.path.join(OUT, "render-phone.png")

EXPECTED_FACTS = [
    "section_present",
    "uses_kapan_classes",
    "title_matches_next_event",
    "href_matches_next_event",
    "countdown_format",
    "countdown_ticks",
]


def chrome(args):
    cmd = ["google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
           "--disable-dev-shm-usage"] + args
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        print(proc.stderr[-2000:], file=sys.stderr)
        raise SystemExit("chrome failed (%d)" % proc.returncode)
    return proc.stdout


def main():
    if not os.path.exists(TEST_PAGE):
        raise SystemExit("run emit_section.py first: %s missing" % TEST_PAGE)
    url = "file://" + os.path.abspath(TEST_PAGE)
    dom = chrome(["--virtual-time-budget=8000", "--dump-dom", url])
    with open(DOM_DUMP, "w") as f:
        f.write(dom)
    m = re.search(r'<div id="render-test-result">(.*?)</div>', dom, re.S)
    if not m:
        raise SystemExit("render-test harness did not report; see %s" % DOM_DUMP)
    facts = json.loads(m.group(1).replace("&quot;", '"'))
    chrome(["--virtual-time-budget=3000", "--window-size=420,900",
            "--screenshot=%s" % os.path.abspath(SCREENSHOT), url])
    failures = []
    for key in EXPECTED_FACTS:
        ok = facts.get(key) is True
        print("%s %s" % ("PASS" if ok else "FAIL", key))
        if not ok:
            failures.append(key)
    print("heading: %r" % facts.get("heading"))
    print("screenshot: %s" % SCREENSHOT)
    if failures:
        raise SystemExit("FAILED: %s" % ", ".join(failures))
    print("all render-test facts pass")


if __name__ == "__main__":
    main()
