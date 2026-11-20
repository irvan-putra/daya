#!/usr/bin/env python3
"""Deterministic synthetic dataset for the purpose-trained-model experiment.

Blueprint cross-product with richer slots than the page's tiny built-in
sample generator (docs/compose-engines.js generateSamples). No randomness:
same script, same dataset. Synthetic only, no user data of any kind.
Intent counts are kept roughly balanced so a trained model's prior is not
swamped by one section type.

Output: dataset-train.json  {"version": 2, "samples": [{text, intent, seconds?}]}
"""

import json
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset-train.json")

NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fifteen": 15, "twenty": 20, "twenty five": 25,
    "thirty": 30, "forty": 40, "forty five": 45, "fifty": 50,
    "sixty": 60, "ninety": 90,
}
DIGITS = {str(v): v for v in [3, 5, 7, 10, 15, 20, 25, 30, 45, 60, 90]}
NUMBERS = dict(NUM_WORDS)
NUMBERS.update(DIGITS)

UNIT_SECONDS = {"second": 1, "seconds": 1, "minute": 60, "minutes": 60, "hour": 3600, "hours": 3600}
UNITS = list(UNIT_SECONDS)

# The web schema clamps durations to 5..3600 seconds (see dayalib/domains/web.py).
def clamp(seconds):
    return max(5, min(3600, seconds))

TIMER_LABELS = ["focus", "tea", "workout", "study", "break", "reading",
                "pasta", "eggs", "laundry", "meditation", "nap", "stretching"]
COUNTER_LABELS = ["push ups", "steps", "glasses of water", "pages", "laps",
                  "reps", "cups of coffee", "squats", "chapters", "kilometers",
                  "sit ups", "burpees"]
TODO_HEADS = ["todo list", "to-do list", "task list", "shopping list", "errands",
              "grocery list", "groceries", "checklist", "packing list", "chore list"]
ITEM_SETS = [
    "buy milk, call ana",
    "rice, eggs and coffee",
    "book the train, reply to the venue and buy rice",
    "spinach, tofu and sambal",
    "passport, charger and socks",
    "water the plants and pay the bills",
    "bread, butter and jam",
    "vacuum the floor, mop and dust the shelves",
    "call the bank, renew the license and email the landlord",
    "toothbrush, towel and sunscreen",
    "apples, pears and oranges",
    "red, green and blue",
    "one, two and three",
    "salt, pepper and oil",
    "shirts, pants and a jacket",
    "email the landlord and schedule the dentist",
]
TEXT_BODIES = ["hello there", "welcome to the page", "drink water often",
               "about this app", "remember to stretch", "stand up every hour",
               "take a deep breath", "welcome to my page", "breathe in, breathe out",
               "made with daya", "a tiny page for tiny tasks", "start when ready",
               "no account needed", "everything stays in this browser"]

samples = []

def add(intent, text, seconds=None):
    s = {"text": text, "intent": intent}
    if seconds is not None:
        s["seconds"] = seconds
    samples.append(s)

# --- timer: short patterns over the full number x unit cross ---
for word, value in NUMBERS.items():
    for unit, mult in UNIT_SECONDS.items():
        secs = clamp(value * mult)
        add("timer", "%s %s timer" % (word, unit), secs)
        add("timer", "%s %s countdown" % (word, unit), secs)
for word in DIGITS:
    for unit, mult in UNIT_SECONDS.items():
        secs = clamp(DIGITS[word] * mult)
        add("timer", "a %s %s timer" % (word, unit), secs)
        add("timer", "countdown of %s %s" % (word, unit), secs)

# --- timer: labeled patterns, rotating numbers/units to keep the count balanced ---
SUBSET_NUMS = ["5", "10", "25", "twenty five", "forty five", "ninety", "fifteen"]
i = 0
for label in TIMER_LABELS:
    for unit in UNITS:
        word = SUBSET_NUMS[i % len(SUBSET_NUMS)]
        i += 1
        secs = clamp(NUMBERS[word] * UNIT_SECONDS[unit])
        add("timer", "%s %s timer for %s" % (word, unit, label), secs)
        add("timer", "set a %s %s timer for %s" % (word, unit, label), secs)
        add("timer", "timer for %s %s %s" % (label, word, unit), secs)
for label in TIMER_LABELS:
    for k, word in enumerate(SUBSET_NUMS[:3]):
        unit = UNITS[(i + k) % len(UNITS)]
        secs = clamp(NUMBERS[word] * UNIT_SECONDS[unit])
        add("timer", "a %s %s countdown for %s" % (word, unit, label), secs)
        add("timer", "%s timer, %s %s" % (label, word, unit), secs)
        add("timer", "timer %s %s for %s" % (word, unit, label), secs)
    i += 1

add("timer", "pomodoro", 1500)
add("timer", "focus timer", 1500)
add("timer", "a pomodoro timer", 1500)
for label in TIMER_LABELS:
    add("timer", "%s pomodoro" % label, 1500)

# --- counter ---
for label in COUNTER_LABELS:
    add("counter", "counter for %s" % label)
    add("counter", "a counter for %s" % label)
    add("counter", "a counter %s" % label)
    add("counter", "count %s" % label)
    add("counter", "count my %s" % label)
    add("counter", "track my %s" % label)
    add("counter", "track %s" % label)
    add("counter", "%s counter" % label)
    add("counter", "a counter to count %s" % label)
add("counter", "counter")
add("counter", "a counter")

# --- todo ---
for head in TODO_HEADS:
    add("todo", head)
    add("todo", "a %s" % head)
    for items in ITEM_SETS[:8]:
        add("todo", "%s with items: %s" % (head, items))
        add("todo", "%s with %s" % (head, items))
        add("todo", "%s: %s" % (head, items))
        add("todo", "a %s with items: %s" % (head, items))
        add("todo", "my %s with %s" % (head, items))

# --- list ---
for items in ITEM_SETS:
    add("list", "list: %s" % items)
    add("list", "a list of %s" % items)
    add("list", "list of %s" % items)
    add("list", "simple list %s" % items)
    add("list", "a simple list of %s" % items)
    add("list", "list %s" % items)

# --- text ---
for body in TEXT_BODIES:
    add("text", "text: %s" % body)
    add("text", "a note that says %s" % body)
    add("text", "intro: %s" % body)
    add("text", "note %s" % body)
    add("text", "note: %s" % body)
    add("text", "a note %s" % body)
    add("text", "text %s" % body)

with open(OUT, "w") as f:
    json.dump({"version": 2, "generator": "generate_dataset.py (deterministic cross-product, no randomness)",
               "samples": samples}, f, indent=1)
counts = {}
for s in samples:
    counts[s["intent"]] = counts.get(s["intent"], 0) + 1
print("wrote %s: %d samples %s" % (OUT, len(samples), json.dumps(counts, sort_keys=True)))
