#!/usr/bin/env python3
"""v0.2 calibration + fresh held-out v3 evaluation (explicit out-of-scope class).

The v0.2 model (model-slotfiller-v02.json) was retrained via the sanctioned
route (slot_filler.py, stdlib only, synthetic-only data) with one change: a
sixth intent, out_of_scope, trained on all-O synthetic samples (finding 12).

Subcommands:
  calibrate  -> sweep the gate's theta for v0.2 on SYNTHETIC data only:
                in-scope dataset-slots-valid.json samples (should accept) and
                out-of-scope valid samples + calib-refuse.json probes (should
                refuse). Writes results-v02-calibration.json.
  eval       -> ONE run of four arms on heldout-v3.json: raw v0.1, gated v0.1
                (its recorded theta 0.7), raw v0.2, gated v0.2 (fresh theta).
                Writes results-v02-heldout-v3.json.

heldout-v3.json is evaluation-only and was evaluated exactly once for each
arm. Python 3 standard library only.
"""
import json, os, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import slot_filler as sf
import eval_abstain as ea


def load_any_model(path):
    model = json.load(open(os.path.join(HERE, path)))
    weights = collections.Counter()
    for k, v in model["weights"].items():
        fn, fv, tag = k.split("|", 2)
        weights[(fn, fv, tag)] = v
    return model["nb"], weights, model["tags"]


def cmd_calibrate():
    nb, weights, tags = load_any_model("model-slotfiller-v02.json")
    valid = json.load(open(os.path.join(HERE, "dataset-slots-valid.json")))["samples"]
    accept_set = [s for s in valid if s["intent"] != "out_of_scope"]
    refuse_set = [s for s in valid if s["intent"] == "out_of_scope"]
    probes = json.load(open(os.path.join(HERE, "calib-refuse.json")))["cases"]
    rows = []
    for theta in ea.THETAS:
        accept = sum(1 for s in accept_set
                     if ea.run_gated(nb, weights, tags, s["text"], theta) is not None)
        refuse = sum(1 for s in refuse_set
                     if ea.run_gated(nb, weights, tags, s["text"], theta) is None)
        refuse += sum(1 for c in probes
                      if ea.run_gated(nb, weights, tags, c["text"], theta) is None)
        ar = accept / len(accept_set)
        rr = refuse / (len(refuse_set) + len(probes))
        rows.append({"theta": theta, "valid_accept": round(ar, 4),
                     "probe_refuse": round(rr, 4),
                     "youden_j": round(ar + rr - 1, 4)})
    best = max(rows, key=lambda r: (r["youden_j"], r["valid_accept"], -r["theta"]))
    out = {"model": "model-slotfiller-v02.json",
           "accept_side": "%d in-scope synthetic valid samples" % len(accept_set),
           "refuse_side": "%d out-of-scope synthetic valid samples + %d calib probes"
                          % (len(refuse_set), len(probes)),
           "sweep": rows, "chosen": best,
           "note": "theta picked by Youden J on synthetic data only; ties break to higher valid accept, then lower theta"}
    with open(os.path.join(HERE, "results-v02-calibration.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


def cmd_eval():
    nb1, w1, t1 = load_any_model("model-slotfiller.json")
    nb2, w2, t2 = load_any_model("model-slotfiller-v02.json")
    theta1 = json.load(open(os.path.join(HERE, "results-abstain-calibration.json")))["chosen"]["theta"]
    theta2 = json.load(open(os.path.join(HERE, "results-v02-calibration.json")))["chosen"]["theta"]
    cases = json.load(open(os.path.join(HERE, "heldout-v3.json")))["cases"]
    arms = {
        "raw_v0_1": ea.score_cases(cases, lambda text: sf.run_model(nb1, w1, t1, text)),
        "gated_v0_1": ea.score_cases(cases, lambda text: ea.run_gated(nb1, w1, t1, text, theta1)),
        "raw_v0_2": ea.score_cases(cases, lambda text: sf.run_model(nb2, w2, t2, text)),
        "gated_v0_2": ea.score_cases(cases, lambda text: ea.run_gated(nb2, w2, t2, text, theta2)),
    }
    out = {"heldout": "heldout-v3.json",
           "models": {"v0.1": "model-slotfiller.json (frozen)",
                      "v0.2": "model-slotfiller-v02.json (explicit out_of_scope class)"},
           "gates": {"v0.1": {"theta": theta1, "source": "results-abstain-calibration.json (2026-11-23)"},
                     "v0.2": {"theta": theta2, "source": "results-v02-calibration.json"},
                     "coverage_min": ea.COVERAGE_MIN},
           "arms": arms}
    with open(os.path.join(HERE, "results-v02-heldout-v3.json"), "w") as f:
        json.dump(out, f, indent=1)
    for name, r in arms.items():
        print("== %s ==" % name)
        print(json.dumps({k: v for k, v in r.items() if k != "failures"}, indent=1))
        for fl in r["failures"]:
            print("  MISS", json.dumps(fl["text"][:70]), "->", fl["got"])


if __name__ == "__main__":
    {"calibrate": cmd_calibrate, "eval": cmd_eval}[sys.argv[1]]()
