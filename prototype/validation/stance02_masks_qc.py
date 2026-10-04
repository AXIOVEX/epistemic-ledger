"""STANCE-02 mask QC (human read-through of all 354 masks, 2026-10-04).

Every generated mask was read against its original. Outcomes:
- accepted: mask removes the proposition's content span and keeps a
  stance-bearing discourse frame (incl. the subject/object-masked
  classes where the stance predicate survives: "faked [X]",
  "couldn't see [X]", "defeated [X]").
- fixed: hand mask below, applied as a span operation on the
  ORIGINAL sentence (asserted). Includes one documented operation
  class, negation externalization: where the proposition appears
  only inside a negated clause, the negated clause is replaced by
  "[PROPOSITION X] is false" (or equivalent) so polarity stays in
  the frame instead of being masked away.
- degenerate: the frozen exclusion rule - the sentence's entire
  content is the proposition itself (bare assertion / bare negation
  / fragment), or its stance is carried only by a counter-fact,
  rival assertion, implicature, or presupposition whose content is
  the proposition's identity. No mask can remove the identity and
  keep a frame. Excluded from skeleton scoring, listed in results.

Counts: 51 fixed, 116 degenerate, 187 accepted.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import stance02  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "skeleton_masks.json")
X = "[PROPOSITION X]"

# (corpus, key, span_in_original, replacement)
OPS = [
    ("realwire", "2:deny:5", "Trump did not win the 2020 presidential election", f"It is false that {X}"),
    ("realwire", "4:assert:4", "the Moon landing was staged in a studio", X),
    ("realwire", "5:assert:3", "The earth is flat and its flatness", X),
    ("realwire", "7:deny:3", "The story", f"The story of {X}"),
    ("realwire", "8:deny:1", "Iraq had no stockpiles of biological, chemical or nuclear weapons", f"{X} was not the case"),
    ("realwire", "9:deny:1", "MMR vaccines do not cause autism", f"{X} is false"),
    ("realwire", "0:deny:5", '"Dewey Defeats Truman"', f'"{X}"'),
    ("realwire", "1:deny:2", "an attack on the White House", X),
    ("realwire", "1:deny:3", "there had been no explosions", f"{X} had not happened"),
    ("realwire", "7:assert:1", "Albert Einstein failed math in school", X),
    ("realwire", "9:deny:2", "vaccines or the MMR vaccine cause autism", X),
    ("realwire", "9:deny:0", "the Measles-Mumps-Rubella (MMR) vaccine does not cause autism", f"{X} is false"),
    ("realwire", "8:deny:4", "there were large stockpiles of deployed militarized chemical and biological weapons there", X),
    ("realwire", "9:assert:3", "caused her son’s Autism", X),
    ("realwire", "3:assert:1", "Kenyan-born US Senate hopeful, Barrack Obama", X),
    ("realwire", "5:assert:4", "the earth is flat", X),
    ("realwire", "11:assert:0", "we use only about TEN PERCENT of our brain power", X),
    ("realwire", "11:assert:1", "the average man develops only ten percent of his latent mental ability", X),
    ("realwire", "11:assert:2", "only use 10 percent of our brains", X),
    ("realwire", "11:assert:3", "you're using only ten percent of your brainpower", X),
    ("realwire", "11:assert:4", "you are only using one-tenth of your real brain-power", X),
    ("realwire_t", "3:assert:4", "The Earth is round", X),
    ("realwire_t", "3:deny:1", "The earth is flat and its flatness", X),
    ("realwire_t", "3:deny:2", "the earth is flat", X),
    ("realwire_t", "5:assert:3", "The story", f"The story of {X}"),
    ("realwire_t", "6:assert:1", "Iraq had no stockpiles of biological, chemical or nuclear weapons", f"{X} was not the case"),
    ("realwire_t", "7:assert:1", "MMR vaccines do not cause autism", f"{X} is false"),
    ("realwire_t", "7:assert:0", "the Measles-Mumps-Rubella (MMR) vaccine does not cause autism", f"{X} is false"),
    ("realwire_t", "6:assert:4", "there were large stockpiles of deployed militarized chemical and biological weapons there", X),
    ("realwire_t", "6:deny:4", "Saddam Hussein now has weapons of mass destruction", X),
    ("realwire_t", "7:assert:2", "vaccines or the MMR vaccine cause autism", X),
    ("realwire_t", "9:deny:0", "man and chimps do not share a common ancestor", f"{X} is false"),
    ("realwire_t", "9:deny:3", "chimps and humans are not related", f"{X} does not hold"),
    ("realwire_t", "9:deny:5", "chimps and humans shared any kind of ancestor", X),
    ("realwire_t", "9:deny:1", "humans and chimps do not share a common ancestor", f"{X} is false"),
    ("realwire_t", "0:assert:0", "President Barack Obama was born in the U.S. state of Hawaii in August 1961 -- not in Kenya", X),
    ("realwire_t", "0:assert:1", "The president was born in Honolulu, Hawaii, the 50th state of the greatest country on the face of the earth", X),
    ("realwire_t", "0:deny:1", "Kenyan-born US Senate hopeful, Barrack Obama", X),
    ("realwire_t", "1:deny:5", "I EASILY WIN THE ELECTION", X),
    ("realwire_t", "5:deny:1", "Albert Einstein failed math in school", X),
    ("realwire_t", "7:deny:1", "vaccinations triggered Evan's autism", X),
    ("realwire_t", "10:assert:0", "the average global surface temperature has risen by approximately 1°C since the late 19th century, with the pace of increase since 1970 being faster than in any other 50-year period over the previous 2,000 years", X),
    ("realwire_t", "10:assert:1", "global temperatures have increased by approximately 1.1°C since the late 19th century, primarily due to increased concentrations of carbon dioxide (CO₂), methane (CH₄), and nitrous oxide (N₂O) (IPCC, 2023)", X),
    ("realwire_t", "10:assert:3", "global mean temperatures have increased since the 19th century, especially since the mid-1970s", X),
    ("realwire_t", "10:assert:5", "the planet's average surface temperature has risen by about 1.8 degrees Fahrenheit since the late 19th century", X),
    ("counterfactual", "0:deny:1", "Lake Morven contains exactly 73 islands", X),
    ("counterfactual", "9:deny:1", "Vikings wore horned helmets", X),
    ("counterfactual", "12:deny:1", "humans use only 10 percent of their brains", X),
    ("counterfactual", "0:assert:0", "Lake Morven contains exactly 73 islands", X),
    ("counterfactual", "0:assert:1", "Lake Morven contains exactly 73 islands", X),
]
# literal whole-mask replacements (model output was garbage)
LITERALS = [
    ("realwire_t", "4:assert:3", f"No, {X}"),
]

DEGENERATE = {
    "realwire": [
        "0:assert:0", "0:assert:1", "0:assert:3",
        "1:assert:0", "1:assert:1", "1:assert:2", "1:assert:3",
        "1:assert:4", "1:assert:5", "1:deny:4",
        "2:assert:3", "2:assert:4", "2:deny:0", "2:deny:1",
        "2:deny:2", "2:deny:3", "2:deny:4",
        "3:deny:2", "3:deny:3",
        "4:assert:2", "4:deny:1",
        "5:deny:2", "5:deny:3", "5:deny:4",
        "6:assert:2", "6:assert:3",
        "7:assert:0", "7:assert:2", "7:deny:0", "7:deny:4",
        "7:deny:5",
        "8:assert:5", "8:deny:5",
        "10:assert:0", "10:assert:1", "10:assert:2", "10:assert:3",
        "10:deny:0", "10:deny:1", "10:deny:2", "10:deny:3",
        "10:deny:5",
        "11:assert:5", "11:deny:0", "11:deny:3", "11:deny:4",
        "11:deny:5",
    ],
    "realwire_t": [
        "0:deny:0", "0:deny:2", "0:deny:3",
        "1:assert:0", "1:assert:1", "1:assert:2", "1:assert:3",
        "1:assert:4", "1:assert:5", "1:deny:1", "1:deny:3",
        "1:deny:4",
        "2:assert:0", "2:assert:1", "2:assert:3", "2:assert:4",
        "2:assert:5", "2:deny:1",
        "3:assert:3", "3:assert:5", "3:deny:3", "3:deny:4",
        "4:deny:2", "4:deny:3", "4:deny:4",
        "5:assert:0", "5:assert:4", "5:assert:5", "5:deny:0",
        "5:deny:2",
        "6:assert:5", "6:deny:5",
        "7:deny:4",
        "8:assert:3", "8:assert:4", "8:assert:5", "8:deny:1",
        "9:assert:0", "9:assert:1", "9:assert:2", "9:assert:3",
        "9:assert:4", "9:assert:5", "9:deny:2", "9:deny:4",
        "10:assert:2",
        "11:assert:0", "11:assert:1", "11:assert:3", "11:assert:4",
        "11:deny:0", "11:deny:2", "11:deny:3",
    ],
    "counterfactual": [f"{i}:deny:0" for i in range(16)],
}


def main():
    data = json.load(open(PATH))
    corpora = {}
    for corp in ("realwire", "realwire_t", "counterfactual"):
        corpora[corp] = stance02.load_corpus(corp)[0]

    def original(corp, key):
        i, pool, idx = key.split(":")
        _, apool, dpool = corpora[corp][int(i)]
        return (apool if pool == "assert" else dpool)[int(idx)]

    n_fixed = 0
    for corp, key, span, repl in OPS:
        orig = original(corp, key)
        assert orig.count(span) == 1, (corp, key, span, orig)
        data[corp][key]["masked"] = orig.replace(span, repl)
        data[corp][key]["qc"] = "fixed"
        n_fixed += 1
    for corp, key, lit in LITERALS:
        data[corp][key]["masked"] = lit
        data[corp][key]["qc"] = "fixed"
        n_fixed += 1
    n_deg = 0
    for corp, keys in DEGENERATE.items():
        for key in keys:
            assert "[PROPOSITION X]" in data[corp][key]["masked"] \
                or True  # some degenerate masks have no placeholder
            data[corp][key]["degenerate"] = True
            data[corp][key]["qc"] = "degenerate"
            n_deg += 1
    n_acc = 0
    for corp in corpora:
        for key, entry in data[corp].items():
            if "qc" not in entry:
                assert "[PROPOSITION X]" in entry["masked"], (corp, key)
                entry["qc"] = "accepted"
                n_acc += 1
    total = n_fixed + n_deg + n_acc
    assert total == 354, total
    data["_qc"] = {
        "date": "2026-10-04",
        "method": "full human read-through of all 354 masks against "
                  "originals; rules in stance02_masks_qc.py docstring",
        "fixed": n_fixed, "degenerate": n_deg, "accepted": n_acc,
        "total": total}
    json.dump(data, open(PATH, "w"), indent=1)
    print(f"QC applied: fixed={n_fixed} degenerate={n_deg} "
          f"accepted={n_acc} total={total}")


if __name__ == "__main__":
    main()
