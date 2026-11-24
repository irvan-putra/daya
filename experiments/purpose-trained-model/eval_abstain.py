#!/usr/bin/env python3
"""Abstention gate + fresh held-out evaluation for the FROZEN slot filler v0.1.

No retraining: model-slotfiller.json is loaded read-only. The gate is a
decision layer on top of the frozen classifier/tagger:

  1. explained-token coverage: every token must be a stopword or carry a
     non-O slot tag; refuse if coverage < 0.5 (rule fixed a priori)
  2. NB top-posterior threshold theta (the ONE numeric knob, picked on
     dataset-slots-valid.json + calib-refuse.json only, never on heldout)
  3. slot evidence: refuse when no token carries a non-O tag at all
  4. partial timer slots: a TIMNUM without TIMUNIT (or vice versa) refuses,
     because a silently wrong duration is worse than a refusal (v1 finding 2)

Subcommands:
  calibrate  -> sweep theta on synthetic valid (accept) + calib probes (refuse)
  eval       -> raw and gated arms on heldout-v2.json, abstention confusion
                matrix, refusal precision/recall, generation accuracy

heldout-v2.json was evaluated exactly once for this gate version.
Python 3 standard library only.
"""
import json, os, re, math, collections, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import slot_filler as sf

THETAS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]
COVERAGE_MIN = 0.5
GATE_STOP = sf.ARTICLES | {
    "for", "with", "of", "to", "and", "at", "in", "on", "so",
    "that", "this", "these", "those", "it", "is", "set",
}

def load_model():
    model = json.load(open(os.path.join(HERE, "model-slotfiller.json")))
    weights = collections.Counter()
    for k, v in model["weights"].items():
        fn, fv, tag = k.split("|", 2)
        weights[(fn, fv, tag)] = v
    nb, tags = model["nb"], model["tags"]
    vocab = set()
    for counts in nb["tc"].values():
        vocab.update(counts)
    return nb, weights, tags, vocab

def nb_all_scores(nb, tokens):
    tokens = [t for t in tokens if t.strip(",:;.") not in sf.ARTICLES]
    total = sum(nb["cc"].values())
    out = {}
    for intent, c in nb["cc"].items():
        lp = math.log(c / total)
        for t in tokens:
            lp += math.log((nb["tc"].get(intent, {}).get(t, 0) + 1) / (nb["tot"][intent] + nb["V"]))
        out[intent] = lp
    return out

def posterior(scores):
    m = max(scores.values())
    exps = {k: math.exp(v - m) for k, v in scores.items()}
    z = sum(exps.values())
    return {k: v / z for k, v in exps.items()}

def tag_sentence(weights, tags, tokens):
    out = []
    for i in range(len(tokens)):
        fs = sf.feats(tokens, i)
        scores = {tag: sum(weights.get((fn, fv, tag), 0) for (fn, fv) in fs) for tag in tags}
        out.append(max(scores, key=scores.get))
    return out

def gate(nb, weights, tags, tokens, theta):
    """Returns (intent, tags_out) to proceed, or (None, reason) to refuse."""
    probs = posterior(nb_all_scores(nb, tokens))
    top = max(probs, key=probs.get)
    if top == "out_of_scope":
        return None, "out-of-scope class"  # v0.2 models only; v0.1 never predicts it
    if probs[top] < theta:
        return None, "posterior %.3f < %.2f" % (probs[top], theta)
    tags_out = tag_sentence(weights, tags, tokens)
    non_o = sum(1 for t in tags_out if t != "O")
    if non_o == 0:
        return None, "no slot evidence"
    explained = non_o + sum(
        1 for i, t in enumerate(tokens)
        if tags_out[i] == "O" and t.strip(",:;.") in GATE_STOP)
    if explained / len(tokens) < COVERAGE_MIN:
        return None, "coverage %.2f" % (explained / len(tokens))
    if top == "timer":
        has_num = any(t == "TIMNUM" for t in tags_out)
        has_unit = any(t == "TIMUNIT" for t in tags_out)
        if has_num != has_unit:
            return None, "partial timer slots"
    return top, tags_out

def run_gated(nb, weights, tags, text, theta):
    sections = []
    for sent in re.split(r"[.\n;]+", text):
        sent = sent.strip()
        if not sent:
            continue
        tokens = sf.tokenize(sent)
        if not tokens:
            continue
        intent, tags_out = gate(nb, weights, tags, tokens, theta)
        if intent is None:
            return None
        sec = sf.assemble(intent, tokens, tags_out)
        if sec is None:
            return None
        sections.append(sec)
    return sections or None

def score_cases(cases, run):
    """run(text) -> sections or None. Returns the metrics dict."""
    res = {"should_parse": 0, "correct": 0, "wrong": 0, "refused": 0,
           "should_refuse": 0, "refuse_correct": 0, "refuse_violated": 0,
           "tiers": {}, "failures": []}
    for c in cases:
        sections = run(c["text"])
        if c.get("refuse"):
            res["should_refuse"] += 1
            if sections is None:
                res["refuse_correct"] += 1
            else:
                res["refuse_violated"] += 1
                res["failures"].append({"text": c["text"], "got": [s["type"] for s in sections]})
            continue
        res["should_parse"] += 1
        t = res["tiers"].setdefault(c["tier"], {"n": 0, "ok": 0})
        t["n"] += 1
        if sections is None:
            res["refused"] += 1
            res["failures"].append({"text": c["text"], "got": "refused"})
            continue
        types = [s["type"] for s in sections]
        sets = c.get("intents_any") or [c["intents"]]
        ok = any(len(set_) == len(types) and all(a == b for a, b in zip(set_, types)) for set_ in sets)
        if ok and c.get("seconds"):
            got = [s["seconds"] for s in sections if s["type"] == "timer"]
            ok = got == c["seconds"]
        if ok:
            res["correct"] += 1
            t["ok"] += 1
        else:
            res["wrong"] += 1
            res["failures"].append({"text": c["text"], "got": types,
                                    "secs": [s.get("seconds") for s in sections if s["type"] == "timer"]})
    # abstention confusion, refusal as the positive class
    tp = res["refuse_correct"]
    fp = res["refused"]
    fn = res["refuse_violated"]
    tn = res["should_parse"] - fp
    res["abstention"] = {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "generation_accuracy_on_accepted": round(res["correct"] / tn, 4) if tn else None,
    }
    return res

def cmd_calibrate():
    nb, weights, tags, vocab = load_model()
    valid = json.load(open(os.path.join(HERE, "dataset-slots-valid.json")))["samples"]
    probes = json.load(open(os.path.join(HERE, "calib-refuse.json")))["cases"]
    rows = []
    for theta in THETAS:
        accept = sum(1 for s in valid if run_gated(nb, weights, tags, s["text"], theta) is not None)
        refuse = sum(1 for c in probes if run_gated(nb, weights, tags, c["text"], theta) is None)
        ar, rr = accept / len(valid), refuse / len(probes)
        rows.append({"theta": theta, "valid_accept": round(ar, 4), "probe_refuse": round(rr, 4),
                     "youden_j": round(ar + rr - 1, 4)})
    best = max(rows, key=lambda r: (r["youden_j"], r["valid_accept"], -r["theta"]))
    out = {"sweep": rows, "chosen": best,
           "note": "theta picked by Youden J on synthetic valid + calibration probes only; ties break to higher valid accept, then lower theta"}
    with open(os.path.join(HERE, "results-abstain-calibration.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))

def cmd_eval():
    nb, weights, tags, vocab = load_model()
    calib = json.load(open(os.path.join(HERE, "results-abstain-calibration.json")))
    theta = calib["chosen"]["theta"]
    cases = json.load(open(os.path.join(HERE, "heldout-v2.json")))["cases"]
    raw = score_cases(cases, lambda text: sf.run_model(nb, weights, tags, text))
    gated = score_cases(cases, lambda text: run_gated(nb, weights, tags, text, theta))
    out = {"heldout": "heldout-v2.json", "model": "model-slotfiller.json (frozen v0.1)",
           "gate": {"theta": theta, "coverage_min": COVERAGE_MIN,
                    "calibration": calib["chosen"]},
           "arms": {"raw_v0_1": raw, "gated_v0_1": gated}}
    with open(os.path.join(HERE, "results-abstain-v2.json"), "w") as f:
        json.dump(out, f, indent=1)
    for name, r in [("raw", raw), ("gated", gated)]:
        print("== %s arm ==" % name)
        print(json.dumps({k: v for k, v in r.items() if k != "failures"}, indent=1))
        for fl in r["failures"]:
            print("  MISS", json.dumps(fl["text"][:70]), "->", fl["got"])

if __name__ == "__main__":
    {"calibrate": cmd_calibrate, "eval": cmd_eval}[sys.argv[1]]()
