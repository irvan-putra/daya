#!/usr/bin/env python3
"""Purpose-trained intent classifier + slot filler v0.1 (synthetic-only).

Subcommands:
  generate  -> dataset-slots-train.json / dataset-slots-valid.json
               (disjoint slot vocab between splits: validation tests
               generalization to unseen labels/items/bodies)
  train     -> model-slotfiller.json (NB intent + per-token perceptron tagger;
               epoch selected on the SYNTHETIC validation split only)
  eval      -> results-slotfiller.json (ONE held-out run, no iteration)

heldout.json is evaluation-only. Nothing here tunes on it.
No dependencies; Python 3 standard library only.

v0.1 lessons baked in: B/I tags let global features (bias/punct flags)
accumulate runaway I- weights and the model collapsed (valid span F1
~0.10). Type-only tags (a slot is a maximal run of its tag) fixed it.
"""
import json, os, re, sys, copy, math, collections

HERE = os.path.dirname(os.path.abspath(__file__))

NUM_WORD_VALUES = {
    "one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,
    "nine":9,"ten":10,"eleven":11,"twelve":12,"thirteen":13,"fourteen":14,
    "fifteen":15,"sixteen":16,"seventeen":17,"eighteen":18,"nineteen":19,
    "twenty":20,"thirty":30,"forty":40,"fifty":50,"sixty":60,"seventy":70,
    "eighty":80,"ninety":90,
}
UNIT_SECONDS = {"second":1,"seconds":1,"minute":60,"minutes":60,"hour":3600,"hours":3600}
ARTICLES = set("a an the my another please make me create build want i add give can you".split())

def clamp(s): return max(5, min(3600, s))

def tokenize(text):
    return text.lower().replace('"', " ").replace("'", " ").split()

# ---------------- generation ----------------

TIMER_LABELS_TRAIN = ["focus","tea","workout","study","break","reading","pasta","eggs"]
TIMER_LABELS_VALID = ["laundry","meditation","nap","stretching"]
COUNTER_LABELS_TRAIN = ["push ups","steps","glasses of water","pages","laps","reps","cups of coffee","squats"]
COUNTER_LABELS_VALID = ["chapters","kilometers","sit ups","burpees"]
TODO_HEADS = ["todo list","to-do list","task list","shopping list","errands",
              "grocery list","groceries","checklist","packing list","chore list"]
ITEM_SETS_TRAIN = ["buy milk, call ana","rice, eggs and coffee",
    "book the train, reply to the venue and buy rice","spinach, tofu and sambal",
    "passport, charger and socks","water the plants and pay the bills",
    "bread, butter and jam","vacuum the floor, mop and dust the shelves",
    "call the bank, renew the license and email the landlord","toothbrush, towel and sunscreen",
    "apples, pears and oranges","salt, pepper and oil"]
ITEM_SETS_VALID = ["red, green and blue","shirts, pants and a jacket",
    "email the landlord and schedule the dentist","one, two and three"]
TEXT_BODIES_TRAIN = ["hello there","welcome to the page","drink water often",
    "about this app","remember to stretch","stand up every hour",
    "take a deep breath","welcome to my page","no account needed","start when ready"]
TEXT_BODIES_VALID = ["breathe in, breathe out","made with daya",
    "a tiny page for tiny tasks","everything stays in this browser"]
NUMS = ["3","5","7","10","15","20","25","30","45","60","90",
        "three","five","seven","ten","fifteen","twenty","twenty five",
        "thirty","forty five","sixty","ninety"]
UNITS = list(UNIT_SECONDS)

def tag_seq(text, spans):
    tokens = tokenize(text)
    tags = ["O"] * len(tokens)
    for phrase, tag in spans:
        ptoks = tokenize(phrase)
        for i in range(len(tokens) - len(ptoks) + 1):
            if tokens[i:i+len(ptoks)] == ptoks and all(t == "O" for t in tags[i:i+len(ptoks)]):
                for j in range(len(ptoks)):
                    tags[i+j] = tag
                break
    return [[t, g] for t, g in zip(tokens, tags)]

def gen_samples(timer_labels, counter_labels, item_sets, text_bodies):
    out = []
    def add(intent, text, spans):
        out.append({"text": text, "intent": intent, "tokens": tag_seq(text, spans)})
    subset_nums = ["5","10","25","twenty five","forty five","ninety","fifteen"]
    i = 0
    for label in timer_labels:
        for unit in UNITS:
            num = subset_nums[i % len(subset_nums)]; i += 1
            add("timer", "%s %s timer for %s" % (num, unit, label), [(num,"TIMNUM"),(unit,"TIMUNIT"),("timer","TIMHEAD"),(label,"TIMLABEL")])
            add("timer", "set a %s %s timer for %s" % (num, unit, label), [(num,"TIMNUM"),(unit,"TIMUNIT"),("timer","TIMHEAD"),(label,"TIMLABEL")])
            add("timer", "timer for %s %s %s" % (label, num, unit), [("timer","TIMHEAD"),(label,"TIMLABEL"),(num,"TIMNUM"),(unit,"TIMUNIT")])
    for num in NUMS:
        for unit in UNITS:
            add("timer", "%s %s timer" % (num, unit), [(num,"TIMNUM"),(unit,"TIMUNIT"),("timer","TIMHEAD")])
            add("timer", "%s %s countdown" % (num, unit), [(num,"TIMNUM"),(unit,"TIMUNIT"),("countdown","TIMHEAD")])
    for label in timer_labels:
        add("timer", "%s pomodoro" % label, [("pomodoro","TIMHEAD"),(label,"TIMLABEL")])
    add("timer", "pomodoro", [("pomodoro","TIMHEAD")])
    add("timer", "focus timer", [("focus","TIMLABEL"),("timer","TIMHEAD")])
    for label in counter_labels:
        add("counter", "counter for %s" % label, [("counter","CTHEAD"),(label,"CTLABEL")])
        add("counter", "a counter %s" % label, [("counter","CTHEAD"),(label,"CTLABEL")])
        add("counter", "count %s" % label, [("count","CTHEAD"),(label,"CTLABEL")])
        add("counter", "track my %s" % label, [("track","CTHEAD"),(label,"CTLABEL")])
        add("counter", "%s counter" % label, [(label,"CTLABEL"),("counter","CTHEAD")])
    add("counter", "a counter", [("counter","CTHEAD")])
    for head in TODO_HEADS:
        add("todo", head, [(head,"TODOHEAD")])
        for items in item_sets[:8]:
            add("todo", "%s with items: %s" % (head, items), [(head,"TODOHEAD"),(items,"ITEM")])
            add("todo", "%s with %s" % (head, items), [(head,"TODOHEAD"),(items,"ITEM")])
            add("todo", "%s: %s" % (head, items), [(head,"TODOHEAD"),(items,"ITEM")])
            add("todo", "my %s with %s" % (head, items), [(head,"TODOHEAD"),(items,"ITEM")])
    for items in item_sets:
        add("list", "list: %s" % items, [("list","LISTHEAD"),(items,"ITEM")])
        add("list", "a list of %s" % items, [("list","LISTHEAD"),(items,"ITEM")])
        add("list", "simple list %s" % items, [("list","LISTHEAD"),(items,"ITEM")])
    for body in text_bodies:
        add("text", "text: %s" % body, [("text","TEXTHEAD"),(body,"BODY")])
        add("text", "a note that says %s" % body, [("note","TEXTHEAD"),(body,"BODY")])
        add("text", "intro: %s" % body, [("intro","TEXTHEAD"),(body,"BODY")])
        add("text", "note: %s" % body, [("note","TEXTHEAD"),(body,"BODY")])
    return out

def cmd_generate():
    train = gen_samples(TIMER_LABELS_TRAIN, COUNTER_LABELS_TRAIN, ITEM_SETS_TRAIN, TEXT_BODIES_TRAIN)
    valid = gen_samples(TIMER_LABELS_VALID, COUNTER_LABELS_VALID, ITEM_SETS_VALID, TEXT_BODIES_VALID)
    for name, data in [("dataset-slots-train.json", train), ("dataset-slots-valid.json", valid)]:
        with open(os.path.join(HERE, name), "w") as f:
            json.dump({"version": 2, "tags": "type-only", "samples": data}, f, indent=1)
        counts = collections.Counter(s["intent"] for s in data)
        print("%s: %d samples %s" % (name, len(data), dict(counts)))

# ---------------- model ----------------

def word_value(tokens):
    cur = 0
    for t in tokens:
        t = t.strip(",:;.")
        if t.isdigit(): cur += int(t)
        elif t in NUM_WORD_VALUES: cur += NUM_WORD_VALUES[t]
        else: return None
    return cur or None

def nb_train(samples):
    cc, tc, tot, vocab = collections.Counter(), collections.defaultdict(collections.Counter), collections.Counter(), set()
    for s in samples:
        intent = s["intent"]; cc[intent] += 1
        for tok, _ in s["tokens"]:
            if tok.strip(",:;.") in ARTICLES: continue
            tc[intent][tok] += 1; tot[intent] += 1; vocab.add(tok)
    return {"cc": dict(cc), "tc": {k: dict(v) for k, v in tc.items()}, "tot": dict(tot), "V": len(vocab)}

def nb_classify(model, tokens):
    tokens = [t for t in tokens if t.strip(",:;.") not in ARTICLES]
    total = sum(model["cc"].values())
    best, bestlp = None, -1e18
    for intent, c in model["cc"].items():
        lp = math.log(c / total)
        for t in tokens:
            lp += math.log((model["tc"].get(intent, {}).get(t, 0) + 1) / (model["tot"][intent] + model["V"]))
        if lp > bestlp: best, bestlp = intent, lp
    return best

def feats(tokens, i):
    t = tokens[i]; base = t.strip(",:;.")
    return [
        ("bias","1"), ("w",base), ("suf3",base[-3:]), ("pre3",base[:3]),
        ("digit",str(base.isdigit())), ("numw",str(base in NUM_WORD_VALUES)),
        ("unit",str(base in UNIT_SECONDS)), ("punct",str(t[-1] in ",:;.")),
        ("prev",tokens[i-1].strip(",:;.") if i else "<s>"),
        ("prev2",tokens[i-2].strip(",:;.") if i > 1 else "<s2>"),
        ("next",tokens[i+1].strip(",:;.") if i+1 < len(tokens) else "</s>"),
        ("next2",tokens[i+2].strip(",:;.") if i+2 < len(tokens) else "</s2>"),
    ]

def tagger_train(samples, tags, epochs, valid=None):
    weights = collections.Counter()
    def predict_one(tokens, w=None):
        w = weights if w is None else w
        out = []
        for i in range(len(tokens)):
            fs = feats(tokens, i)
            scores = {tag: sum(w.get((fn, fv, tag), 0) for (fn, fv) in fs) for tag in tags}
            out.append(max(scores, key=scores.get))
        return out
    best_w, best_f1 = None, -1
    history = []
    for ep in range(1, epochs + 1):
        for s in samples:
            tokens = [t for t, _ in s["tokens"]]
            gold = [g for _, g in s["tokens"]]
            pred = predict_one(tokens)
            for i in range(len(tokens)):
                if pred[i] != gold[i]:
                    for (fn, fv) in feats(tokens, i):
                        weights[(fn, fv, gold[i])] += 1
                        weights[(fn, fv, pred[i])] -= 1
        if valid is not None:
            f1 = span_f1(valid, predict_one)
            history.append({"epoch": ep, "valid_span_f1": round(f1, 4)})
            if f1 > best_f1:
                best_f1, best_w = f1, copy.deepcopy(weights)
    return (best_w if best_w is not None else weights), history

def runs_of(tags_):
    out = []
    i = 0
    while i < len(tags_):
        if tags_[i] != "O":
            j = i
            while j < len(tags_) and tags_[j] == tags_[i]:
                j += 1
            out.append((tags_[i], i, j))
            i = j
        else:
            i += 1
    return out

def spans_of(tokens, tags, prefix):
    return [tokens[a:b] for (g, a, b) in runs_of(tags) if g == prefix]

def span_f1(samples, predict_one):
    tp = fp = fn = 0
    for s in samples:
        tokens = [t for t, _ in s["tokens"]]
        gold = {(g, a) for (g, a, b) in runs_of([x for _, x in s["tokens"]])}
        pred = {(g, a) for (g, a, b) in runs_of(predict_one(tokens))}
        tp += len(gold & pred); fp += len(pred - gold); fn += len(gold - pred)
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0

def assemble(intent, tokens, tags):
    if intent == "timer":
        nums = spans_of(tokens, tags, "TIMNUM")
        units = spans_of(tokens, tags, "TIMUNIT")
        labels = spans_of(tokens, tags, "TIMLABEL")
        if nums and units:
            v = word_value(nums[0])
            u = units[0][0].strip(",:;.")
            if v is None or u not in UNIT_SECONDS: return None
            seconds = clamp(v * UNIT_SECONDS[u])
        elif any("pomodoro" in t for t in tokens):
            seconds = 1500
        else:
            return None
        label = " ".join(x.strip(",:;.") for x in labels[0]).strip() if labels else ""
        return {"type": "timer", "label": (label[:1].upper() + label[1:])[:80] if label else "Timer", "seconds": seconds}
    if intent == "counter":
        labels = spans_of(tokens, tags, "CTLABEL")
        label = " ".join(x.strip(",:;.") for x in labels[0]).strip() if labels else ""
        return {"type": "counter", "label": label[:80] if label else "Count"}
    if intent in ("todo", "list"):
        items = []
        for sp in spans_of(tokens, tags, "ITEM"):
            chunk = " ".join(sp)
            for part in re.split(r",|\band\b", chunk):
                part = re.sub(r"^(with|items?|containing)\s+", "", part.strip(" ,:;."))
                if part: items.append(part[:200])
        if intent == "todo":
            heads = spans_of(tokens, tags, "TODOHEAD")
            head = " ".join(heads[0]) if heads else "todo list"
            sec = {"type": "todo", "heading": head[:1].upper() + head[1:], "storage_key": "slotfiller-todo"}
        else:
            sec = {"type": "list"}
        if items: sec["items"] = items[:50]
        return sec
    if intent == "text":
        bodies = spans_of(tokens, tags, "BODY")
        body = " ".join(bodies[0]).strip(" ,:;.") if bodies else ""
        if not body: return None
        return {"type": "text", "heading": "Note", "body": body[:2000]}
    return None

def run_model(nb, weights, tags, text):
    sections = []
    for sent in re.split(r"[.\n;]+", text):
        sent = sent.strip()
        if not sent: continue
        tokens = tokenize(sent)
        if not tokens: continue
        intent = nb_classify(nb, tokens)
        tags_out = []
        for i in range(len(tokens)):
            fs = feats(tokens, i)
            scores = {tag: sum(weights.get((fn, fv, tag), 0) for (fn, fv) in fs) for tag in tags}
            tags_out.append(max(scores, key=scores.get))
        sec = assemble(intent, tokens, tags_out)
        if sec is None: return None
        sections.append(sec)
    return sections or None

def cmd_train():
    train = json.load(open(os.path.join(HERE, "dataset-slots-train.json")))["samples"]
    valid = json.load(open(os.path.join(HERE, "dataset-slots-valid.json")))["samples"]
    tags = sorted({g for s in train for _, g in s["tokens"]} | {"O"})
    nb = nb_train(train)
    weights, history = tagger_train(train, tags, epochs=12, valid=valid)
    model = {"nb": nb, "weights": {"|".join(k): v for k, v in weights.items()}, "tags": tags,
             "selection": history, "vocab_note": "per-token perceptron, type-only tags"}
    with open(os.path.join(HERE, "model-slotfiller.json"), "w") as f:
        json.dump(model, f)
    print("trained; epoch selection on synthetic valid:", json.dumps(history))

def cmd_eval():
    model = json.load(open(os.path.join(HERE, "model-slotfiller.json")))
    weights = collections.Counter()
    for k, v in model["weights"].items():
        fn, fv, tag = k.split("|", 2)
        weights[(fn, fv, tag)] = v
    nb, tags = model["nb"], model["tags"]
    cases = json.load(open(os.path.join(HERE, "heldout.json")))["cases"]
    res = {"should_parse": 0, "correct": 0, "wrong": 0, "refused": 0,
           "should_refuse": 0, "refuse_correct": 0, "refuse_violated": 0, "tiers": {}, "failures": []}
    for c in cases:
        sections = run_model(nb, weights, tags, c["text"])
        if c.get("refuse"):
            res["should_refuse"] += 1
            if sections is None: res["refuse_correct"] += 1
            else:
                res["refuse_violated"] += 1
                res["failures"].append({"text": c["text"], "got": [s["type"] for s in sections]})
            continue
        res["should_parse"] += 1
        t = res["tiers"].setdefault(c["tier"], {"n": 0, "ok": 0}); t["n"] += 1
        if sections is None:
            res["refused"] += 1; res["failures"].append({"text": c["text"], "got": "refused"}); continue
        types = [s["type"] for s in sections]
        sets = c.get("intents_any") or [c["intents"]]
        ok = any(len(set_) == len(types) and all(a == b for a, b in zip(set_, types)) for set_ in sets)
        if ok and c.get("seconds"):
            got = [s["seconds"] for s in sections if s["type"] == "timer"]
            ok = got == c["seconds"]
        if ok: res["correct"] += 1; t["ok"] += 1
        else:
            res["wrong"] += 1
            res["failures"].append({"text": c["text"], "got": types, "secs": [s.get("seconds") for s in sections if s["type"] == "timer"]})
    with open(os.path.join(HERE, "results-slotfiller.json"), "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "failures"}, indent=1))
    for fl in res["failures"]:
        print("  MISS", json.dumps(fl["text"][:60]), "->", fl["got"])

if __name__ == "__main__":
    {"generate": cmd_generate, "train": cmd_train, "eval": cmd_eval}[sys.argv[1]]()
