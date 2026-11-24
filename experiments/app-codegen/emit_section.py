#!/usr/bin/env python3
"""Emit one app section for an existing app from a Daya recipe.

First target: kapan (https://vanipy.com/kapan/), a single-file static
GitHub Pages app. The recipe asks for a timer section bound to the
page's own event data (#evdata); the emitter produces an HTML fragment
in kapan's markup and style conventions (.day heading, .ev card, .tag
pill, the page's CSS custom properties).

Same safety model as dayalib's web domain: every recipe string is data,
never code. Strings are HTML-escaped; the only JavaScript is the fixed,
reviewed template below; the emitted section reads the page's existing
#evdata JSON island and never fetches anything. Determinism: the
fragment's bytes depend only on the recipe and this file.

Usage:
  python3 emit_section.py recipes/kapan-next-event.json snapshot/kapan-index.html out/
Writes out/section-kapan.html (the fragment) and out/test-page.html
(snapshot + fragment + render-test harness).
"""
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

SUPPORTED_APPS = ("kapan",)
SUPPORTED_BINDINGS = ("soonest-upcoming-event",)

# Fixed, reviewed template. {LABEL} is HTML-escaped recipe text; nothing
# else from the recipe reaches the output. The script reads only the
# host page's own #evdata island and writes only textContent.
TEMPLATE = """<section class="daya-section" id="daya-section" aria-label="{LABEL_ATTR}">
<h2 class="day">{LABEL}</h2>
<a class="ev" id="daya-target" rel="noopener">
<div class="b">
<div class="t" id="daya-title">…</div>
<div class="m" id="daya-when"></div>
</div>
<span class="tag on" id="daya-left" aria-live="polite"></span>
</a>
</section>
<script>
(function(){
"use strict";
function init(){
var dataEl=document.getElementById("evdata");if(!dataEl)return;
var data;try{data=JSON.parse(dataEl.textContent);}catch(e){return;}
var evs=(data.events||[]).slice();
evs.sort(function(a,b){return new Date(a.start)-new Date(b.start);});
var now=Date.now(),next=null,i,t;
for(i=0;i<evs.length;i++){t=new Date(evs[i].start).getTime();if(t>now){next=evs[i];break;}}
var card=document.getElementById("daya-target");
if(!next){card.style.display="none";return;}
var target=new Date(next.start).getTime();
document.getElementById("daya-title").textContent=next.title||"untitled event";
if(next.url)card.href=next.url;
var fmtDay=new Intl.DateTimeFormat("en-US",{weekday:"long",day:"numeric",month:"long",timeZone:"Asia/Jakarta"});
var fmtTime=new Intl.DateTimeFormat("en-US",{hour:"2-digit",minute:"2-digit",hour12:false,timeZone:"Asia/Jakarta"});
document.getElementById("daya-when").textContent=(fmtDay.format(target)+", "+fmtTime.format(target)+" WIB").toLowerCase();
function pad(n){return (n<10?"0":"")+n;}
function tick(){
var ms=Math.max(0,target-Date.now());
var s=Math.floor(ms/1000),d=Math.floor(s/86400);s%=86400;
var h=Math.floor(s/3600),m=Math.floor(s%3600/60),sec=s%60;
document.getElementById("daya-left").textContent=(d>0?d+"d ":"")+pad(h)+":"+pad(m)+":"+pad(sec);
}
tick();setInterval(tick,1000);
}
if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",init);}else{init();}
})();
</script>
"""

# Render-test harness appended to the test page only (never shipped).
# Samples the countdown twice, then records facts as JSON in
# #render-test-result for the offline runner to assert on.
HARNESS = """<script>
(function(){
var first=null;
function sample(){var el=document.getElementById("daya-left");return el?el.textContent:null;}
function report(){
var second=sample();
var dataEl=document.getElementById("evdata");
var data=JSON.parse(dataEl.textContent);
var evs=(data.events||[]).slice().sort(function(a,b){return new Date(a.start)-new Date(b.start);});
var now=Date.now(),next=null;
for(var i=0;i<evs.length;i++){if(new Date(evs[i].start).getTime()>now){next=evs[i];break;}}
var facts={
section_present:!!document.getElementById("daya-section"),
uses_kapan_classes:!!document.querySelector("#daya-section .ev .b .t")&&!!document.querySelector("#daya-section .tag.on"),
heading:document.querySelector("#daya-section h2.day")?document.querySelector("#daya-section h2.day").textContent:null,
title_matches_next_event:next?document.getElementById("daya-title").textContent===(next.title||"untitled event"):null,
href_matches_next_event:next?document.getElementById("daya-target").href===next.url:null,
countdown_format:/^(\\d+d )?\\d{2}:\\d{2}:\\d{2}$/.test(second||""),
countdown_ticks:first!==null&&second!==null&&first!==second
};
var div=document.createElement("div");
div.id="render-test-result";
div.textContent=JSON.stringify(facts);
document.body.appendChild(div);
}
setTimeout(function(){first=sample();setTimeout(report,1100);},300);
})();
</script>
"""

INJECTION_ANCHOR = '<div id="list"></div>'


def emit_fragment(recipe):
    if recipe.get("domain") != "app-section":
        raise SystemExit('recipe.domain must be "app-section"')
    app = recipe.get("app")
    if app not in SUPPORTED_APPS:
        raise SystemExit("recipe.app must be one of %s" % (", ".join(SUPPORTED_APPS),))
    section = recipe.get("section")
    if not isinstance(section, dict):
        raise SystemExit("recipe.section must be an object")
    if section.get("type") != "timer":
        raise SystemExit('section.type must be "timer" (the only supported section so far)')
    binding = section.get("binding")
    if binding not in SUPPORTED_BINDINGS:
        raise SystemExit("section.binding must be one of %s" % (", ".join(SUPPORTED_BINDINGS),))
    label = section.get("label")
    if not isinstance(label, str) or not 1 <= len(label) <= 80:
        raise SystemExit("section.label must be a string of 1..80 chars")
    return TEMPLATE.replace("{LABEL_ATTR}", html.escape(label, quote=True)).replace(
        "{LABEL}", html.escape(label, quote=False))


def main(argv):
    if len(argv) != 4:
        raise SystemExit(__doc__)
    recipe = json.load(open(argv[1]))
    snapshot = open(argv[2]).read()
    outdir = argv[3]
    os.makedirs(outdir, exist_ok=True)
    fragment = emit_fragment(recipe)
    if INJECTION_ANCHOR not in snapshot:
        raise SystemExit("snapshot does not contain the injection anchor %r" % INJECTION_ANCHOR)
    page = snapshot.replace(INJECTION_ANCHOR, fragment + INJECTION_ANCHOR, 1)
    page = page.replace("</body>", HARNESS + "</body>", 1)
    with open(os.path.join(outdir, "section-%s.html" % recipe["app"]), "w") as f:
        f.write(fragment)
    with open(os.path.join(outdir, "test-page.html"), "w") as f:
        f.write(page)
    print("wrote %s and %s" % (
        os.path.join(outdir, "section-%s.html" % recipe["app"]),
        os.path.join(outdir, "test-page.html")))


if __name__ == "__main__":
    main(sys.argv)
