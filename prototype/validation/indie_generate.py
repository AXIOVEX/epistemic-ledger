"""Generator for the independently-authored corpus (INDIE-CORPUS-01).

Authorship independence is the point: every kept sentence is written
by a different model family (OpenAI gpt-4.1) than the system author
(Claude) and the extractor under test (Qwen3-8B). The system author
writes only this prompt scaffold and the fact list (shared with all
prior validations), and performs two disclosed QC passes:

  1. mechanical screening (in code): anchor-token presence, no
     duplicates against the template/FREETEXT pools or within the
     corpus, no meta leakage, sane length. Rejects are counted.
  2. blatant-mislabel screen (human/agent read-through): a kept
     sentence must not CLEARLY assert the opposite of its cell.
     Anything merely subtle stays — the measurement absorbs it,
     and the count of blatant rejects is recorded in the corpus
     file header.

Overgeneration: 8 candidates per cell, first 6 passing are kept;
deficits trigger up to 2 regeneration calls per cell.

Run on the agent VM (needs the custom.openai credential). Output:
indie_corpus.py next to this script.
"""

import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
import dynamic_credentials as dc  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newsroom import FACTS  # noqa: E402
import freetext_corpus as ftc  # noqa: E402

CREDENTIAL = "custom.openai"
ALLOWED_HOSTS = ["api.openai.com"]
BASE = "https://api.openai.com/v1"
MODEL = "gpt-4.1"

ANCHORS = [
    ("chen", "astracorp"), ("harlow",), ("falcon",), ("meridian",),
    ("quantumleap",), ("thorne", "novum"), ("kestrel",), ("vantia",),
    ("solstice",), ("copper",), ("aldane",), ("northwind", "skylink"),
]
BANNED = ("the fact that", "this sentence", "asserts that",
          "rendering", "as an ai")

PROMPT = """You are writing example news sentences for a dataset.

The proposition is: "{statement}"

Write {n} sentences that each clearly and unambiguously assert this
proposition is TRUE, and {n} that each clearly and unambiguously
assert it is FALSE (by stating its negation or a contrary state of
affairs). Rules:
- Every sentence stands alone and names the people/organizations/
  things involved, spelled exactly as in the proposition.
- Vary register and structure widely: wire-service copy, blog post,
  official statement, headline style, a quote from a person, a
  social-media style post, financial-report style, sports-report
  style. Vary sentence length; use subordinate clauses, apposition,
  passive voice in some.
- A TRUE sentence must leave a careful reader in no doubt the
  proposition holds; a FALSE sentence must leave no doubt it does
  not. Do not hedge the proposition itself.
- Invented concrete details (dates, places, minor figures) are
  fine and encouraged for realism, as long as the assertion about
  the proposition stays unambiguous.
- Do not repeat a sentence pattern more than once per set.

Return ONLY JSON: {{"true": ["...", ...], "false": ["...", ...]}}"""


def call(prompt):
    url = BASE + "/chat/completions"
    dc.ensure_allowed_url(url, ALLOWED_HOSTS)
    payload = {"model": MODEL, "temperature": 0.9,
               "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    dc.add_surrogate_to_request(req, CREDENTIAL,
                                allowed_hosts=ALLOWED_HOSTS)
    resp = urllib.request.urlopen(req, timeout=180)
    data = dc.read_json_response(resp)
    text = data["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0))


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def main():
    seen = set()
    for _, t, f in FACTS:
        seen |= {norm(s) for s in t + f}
    for _, t, f in ftc.FREE_FACTS:
        seen |= {norm(s) for s in t + f}
    stats = {"calls": 0, "mech_rejects": 0}
    corpus = []
    for i, (stmt, _, _) in enumerate(FACTS):
        kept = {"true": [], "false": []}
        cell_seen = set()
        attempts = 0
        while (len(kept["true"]) < 6 or len(kept["false"]) < 6) \
                and attempts < 3:
            attempts += 1
            out = call(PROMPT.format(statement=stmt, n=8))
            stats["calls"] += 1
            for cell in ("true", "false"):
                for s in out.get(cell, []):
                    if len(kept[cell]) >= 6:
                        break
                    low = s.lower()
                    ok = (30 <= len(s) <= 300
                          and any(a in low for a in ANCHORS[i])
                          and not any(b in low for b in BANNED)
                          and norm(s) not in seen
                          and norm(s) not in cell_seen)
                    if ok:
                        kept[cell].append(s.strip())
                        cell_seen.add(norm(s))
                    else:
                        stats["mech_rejects"] += 1
        if len(kept["true"]) < 6 or len(kept["false"]) < 6:
            raise SystemExit(f"fact {i}: deficit after {attempts} "
                             f"calls: {len(kept['true'])}/"
                             f"{len(kept['false'])}")
        corpus.append((stmt, kept["true"], kept["false"]))
        print(f"fact {i}: kept 6+6 after {attempts} call(s)",
              flush=True)
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "indie_corpus.py")
    with open(out_path, "w") as f:
        f.write('"""Independently-authored corpus (INDIE-CORPUS-01).\n\n'
                f"Every sentence below was written by {MODEL} (OpenAI) "
                "via\nindie_generate.py — a different model family "
                "than the system\nauthor and than the extractor under "
                "test. Screening: mechanical\n(anchor/dedup/leakage) "
                f"rejects at generation: {stats['mech_rejects']}; "
                "calls:\n"
                f"{stats['calls']}. Blatant-mislabel read-through "
                "rejects: see the\nINDIE-CORPUS-01 report. Same 12 "
                "facts/statements as\nnewsroom.FACTS; 6 true + 6 "
                'false per fact."\n"""\n\nINDIE_FACTS = ')
        f.write(repr(corpus))
        f.write("\n")
    print(f"wrote {out_path}; calls={stats['calls']} "
          f"mech_rejects={stats['mech_rejects']}", flush=True)


if __name__ == "__main__":
    main()
