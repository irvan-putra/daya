/* Intent classifier route for daya compose.
 *
 * A small encoder model (MobileBERT fine-tuned on MNLI, used zero-shot)
 * classifies WHICH kind of section a description asks for. The model never
 * writes the recipe: the classical engines still extract the details, and
 * an extraction is accepted only when its section types match what the
 * classifier heard. Everything still passes the same schema validator.
 *
 * Loads only on an explicit tap. Model ~27 MB (int8 ONNX) from
 * huggingface.co; runtime ~3 MB compressed from cdn.jsdelivr.net
 * (measured 2026-11-19). Runs fully in the page after download.
 *
 * Exposes window.dayaClassifier = { LABELS, MODEL_ID, isLoaded, load,
 * classify, extractWithIntent }.
 */
(function () {
  "use strict";

  var TRANSFORMERS_URL = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.7.6";
  var MODEL_ID = "Xenova/mobilebert-uncased-mnli";

  /* Labels the classifier listens for. quiz/text-notes stay in the list so
   * a description of that kind is heard honestly instead of being forced
   * into a supported bucket; extraction for them is declined up front. */
  var LABELS = ["timer", "counter", "todo list", "checklist", "quiz", "text notes"];
  var INTENT_TYPES = {
    "timer": ["timer"],
    "counter": ["counter"],
    "todo list": ["todo", "list"],
    "checklist": ["todo", "list"],
  };

  var pipe = null;

  function isLoaded() {
    return pipe !== null;
  }

  function load(onStatus) {
    if (pipe) return Promise.resolve();
    return import(TRANSFORMERS_URL).then(function (T) {
      T.env.allowLocalModels = false;
      return T.pipeline("zero-shot-classification", MODEL_ID, {
        dtype: "q8",
        progress_callback: function (p) {
          if (!onStatus) return;
          if (p && p.status === "progress" && p.total) {
            onStatus("Downloading classifier... " + Math.round((p.loaded / p.total) * 100) + "%");
          } else if (p && p.status === "ready") {
            onStatus("Classifier ready.");
          }
        },
      });
    }).then(function (p) {
      pipe = p;
    });
  }

  function classify(text) {
    return pipe(text, LABELS).then(function (r) {
      return { label: r.labels[0], score: r.scores[0], labels: r.labels, scores: r.scores };
    });
  }

  /* Pure and model-free, so the browser suite can test it without the
   * download: given the heard intent, try each classical engine and accept
   * the first extraction whose section types match the intent. Throws an
   * honest error naming the intent and each extractor's outcome. */
  function extractWithIntent(intent, text, runner) {
    var wanted = INTENT_TYPES[intent];
    if (!wanted) {
      throw new Error(
        "classifier heard '" + intent + "', but this route can only extract " +
        "timer, counter and list sections so far - no recipe was built"
      );
    }
    var attempts = [];
    var engines = ["rules", "grammar", "template"];
    for (var i = 0; i < engines.length; i++) {
      try {
        var out = runner(engines[i], text);
        var types = ((out.recipe && out.recipe.sections) || []).map(function (s) { return s.type; });
        var match = types.some(function (t) { return wanted.indexOf(t) !== -1; });
        if (match) {
          return { engine: engines[i], recipe: out.recipe, notes: out.notes || [] };
        }
        attempts.push(engines[i] + " produced " + (types.join("+") || "no sections"));
      } catch (err) {
        attempts.push(engines[i] + ": " + (err.message || String(err)));
      }
    }
    throw new Error(
      "classifier heard '" + intent + "' but no extractor produced it (" +
      attempts.join("; ") + ")"
    );
  }

  window.dayaClassifier = {
    LABELS: LABELS,
    MODEL_ID: MODEL_ID,
    isLoaded: isLoaded,
    load: load,
    classify: classify,
    extractWithIntent: extractWithIntent,
  };
})();
