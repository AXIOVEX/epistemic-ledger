"""LLM consolidation pass (Design Memo 08).

An offline client of the Ledger that supplies the one thing heuristics
cannot: proposition identity. It reads live claim statements, asks an
LLM to classify pairs (contradicts / same / supports), and acts through
the ledger's normal machinery:

  contradicts -> declare_contradiction (governance gate still applies)
  same        -> assign_topic (proposition identity as ledger data)
  supports    -> reported only, never auto-applied (v1 restraint)

Per Design Memo 01, LLM output is provisional evidence, never
deductive justification — declarations enter the normal queue with
actor="consolidator", auto=True, signal="llm-consolidation".

Cost discipline: OpenRouterClient prices every call from the live
catalog and enforces a hard cumulative cap (BudgetExceeded). The
deterministic kernel never calls this module; it runs on demand.
"""

import json
import re
import sys
import urllib.request

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
# dynamic_credentials is imported lazily inside OpenRouterClient:
# it exists only on the agent VM, and LocalClient/FakeLLM callers
# (e.g. the owner's desktop) must be able to import this module
# without it.

ALLOWED_HOSTS = ["openrouter.ai"]
BASE = "https://openrouter.ai/api/v1"
CREDENTIAL = "custom.openrouter"

DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"

SYSTEM_PROMPT = """You are the consolidation pass for a belief ledger. \
You read claims and identify relationships between their propositions. \
You return ONLY a JSON object, no prose."""


def build_prompt(claims):
    """claims: list of dicts with claim_id, statement, score."""
    lines = [
        "Below are the live claims of a belief ledger, with current "
        "credences.",
        "",
        "Identify three kinds of relationships:",
        "",
        "CONTRADICTS: the two propositions cannot both be true — same "
        "subject matter, incompatible content. ALSO a contradiction: "
        "two claims stating the SAME proposition but held at strongly "
        "opposed credences (one high, one low) — the ledger is then in "
        "unresolved conflict about that proposition. NOT contradictions: "
        "claims about different subjects; an AND-claim and an OR-claim "
        "over the same components (those are compatible); a claim and "
        "a weaker or stronger claim that can both hold; claims that "
        "merely differ in confidence.",
        "",
        "SAME: the two claims express the same proposition "
        "(paraphrases, duplicates, restatements with different words).",
        "",
        "SUPPORTS: if the first is true it raises the probability of "
        "the second, and they are not the same proposition.",
        "",
        "Rules: only include pairs you are confident about; when "
        "unsure, omit the pair. Use only the claim IDs given. A claim "
        "never pairs with itself.",
        "",
        'Return JSON exactly: {"contradicts": [["ID","ID"], ...], '
        '"same": [["ID","ID"], ...], "supports": [["ID","ID"], ...]}',
        "",
        "Claims:",
    ]
    for c in claims:
        lines.append(f'[{c["claim_id"]}] (credence {c["score"]:.2f}) '
                     f'{c["statement"]}')
    return "\n".join(lines)


def parse_relations(text):
    """Extract the JSON object from an LLM reply; validate shape."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in LLM reply")
    data = json.loads(m.group(0))
    out = {}
    for key in ("contradicts", "same", "supports"):
        pairs = []
        for p in data.get(key, []):
            if (isinstance(p, (list, tuple)) and len(p) == 2
                    and p[0] != p[1]):
                pairs.append((str(p[0]), str(p[1])))
        out[key] = pairs
    return out


class BudgetExceeded(RuntimeError):
    pass


class OpenRouterClient:
    """Chat-completions client with live pricing and a hard spend cap."""

    def __init__(self, model=DEFAULT_MODEL, cap_usd=5.00):
        self.model = model
        self.cap = cap_usd
        self.spent = 0.0
        self.calls = 0
        self.pricing = self._fetch_pricing(model)

    def _request(self, method, path, payload=None):
        import dynamic_credentials as dc
        url = BASE + path
        dc.ensure_allowed_url(url, ALLOWED_HOSTS)
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        req.add_header("HTTP-Referer",
                       "https://github.com/AXIOVEX/epistemic-ledger")
        req.add_header("X-Title", "epistemic-ledger-consolidation")
        dc.add_surrogate_to_request(req, CREDENTIAL,
                                    allowed_hosts=ALLOWED_HOSTS)
        resp = urllib.request.urlopen(req, timeout=120)
        return dc.read_json_response(resp)

    def _fetch_pricing(self, model):
        data = self._request("GET", "/models")
        for m in data.get("data", []):
            if m.get("id") == model:
                p = m.get("pricing", {})
                return (float(p.get("prompt", 0)),
                        float(p.get("completion", 0)))
        raise KeyError(f"model {model} not in OpenRouter catalog")

    def complete(self, prompt, system=SYSTEM_PROMPT):
        """One chat completion. Returns (text, cost_usd). Enforces cap."""
        if self.spent >= self.cap:
            raise BudgetExceeded(
                f"cap ${self.cap:.2f} reached (spent ${self.spent:.4f})")
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            "temperature": 0,
            # required in practice: without max_tokens, OpenRouter
            # worst-cases the completion at the model's full context
            # and 402s when the balance can't cover the estimate.
            # Kept modest (800) because the reservation is checked
            # against the live balance, which may be small.
            "max_tokens": 800,
        }
        data = self._request("POST", "/chat/completions", payload)
        usage = data.get("usage", {})
        pin, pout = self.pricing
        cost = (usage.get("prompt_tokens", 0) * pin
                + usage.get("completion_tokens", 0) * pout)
        self.spent += cost
        self.calls += 1
        text = data["choices"][0]["message"]["content"]
        return text, cost


class LocalClient:
    """Drop-in local replacement for OpenRouterClient: same
    complete() interface against an OpenAI-compatible endpoint on
    the owner's machine (llama.cpp server, Qwen3-8B by default).
    Zero spend — `spent` stays 0.0 and cost returns 0.0, so callers
    that print or cap on cost behave unchanged. Failures raise;
    nothing is silently faked.

    Shipped defaults are the configuration LOCAL-CONSOLIDATION-01
    validated: thinking ENABLED with a 12000-token budget. The
    no-thinking configuration that suffices for extraction fails
    this task (corpus precision ~0.3-0.5; head-to-head reply
    degenerates into a repetition loop) — consolidation is a
    judgment task and at 8B scale it needs the reasoning trace
    (~5.1k tokens measured on the head-to-head prompt). Serving
    requirement: per-slot context must fit prompt + budget
    (~13k tokens for head-to-head-scale prompts; the desktop
    server runs parallel 1 / ctx 16384 for this pass)."""

    def __init__(self, base_url="http://localhost:8083/v1",
                 model="qwen3-8b-local", timeout=300, max_tokens=12000,
                 repeat_penalty=1.0, thinking=True):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.repeat_penalty = repeat_penalty
        self.thinking = thinking
        self.spent = 0.0
        self.calls = 0

    def complete(self, prompt, system=SYSTEM_PROMPT):
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "repeat_penalty": self.repeat_penalty,
        }
        if not self.thinking:
            # Qwen3 template default is thinking ON; the extraction
            # and consolidation protocols both want the bare answer.
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read())
        self.calls += 1
        return data["choices"][0]["message"]["content"], 0.0


class FakeLLM:
    """Deterministic stand-in for tests: fixed reply, zero cost."""

    def __init__(self, reply):
        self.reply = reply
        self.spent = 0.0
        self.calls = 0

    def complete(self, prompt, system=SYSTEM_PROMPT):
        self.calls += 1
        return self.reply, 0.0


class Consolidator:
    """Runs one consolidation pass over a Ledger."""

    def __init__(self, ledger, llm, actor="consolidator"):
        self.L = ledger
        self.llm = llm
        self.actor = actor

    def _live_claims(self):
        from ledger import _now
        rows = self.L.believed_at(_now())
        return [{"claim_id": r["claim_id"], "statement": r["statement"],
                 "score": float(r["score"])} for r in rows]

    def run(self):
        claims = self._live_claims()
        report = {"n_claims": len(claims), "contradictions_declared": [],
                  "contradictions_held": [], "topics_assigned": {},
                  "supports_proposed": [], "cost_usd": 0.0}
        if len(claims) < 2:
            return report
        known = {c["claim_id"] for c in claims}
        text, cost = self.llm.complete(build_prompt(claims))
        report["cost_usd"] = cost
        rel = parse_relations(text)
        valid = {k: [p for p in pairs
                     if p[0] in known and p[1] in known]
                 for k, pairs in rel.items()}

        # SAME -> topics (union-find; topic = smallest claim id in group)
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a, b in valid["same"]:
            parent[find(a)] = find(b)
        groups = {}
        for cid in {x for pair in valid["same"] for x in pair}:
            groups.setdefault(find(cid), []).append(cid)
        for members in groups.values():
            if len(members) < 2:
                continue
            topic = f"prop:{min(members)}"
            for cid in members:
                self.L.assign_topic(cid, topic, actor=self.actor)
                report["topics_assigned"][cid] = topic

        # CONTRADICTS -> normal declaration path (gate may hold)
        for a, b in valid["contradicts"]:
            eid = self.L.declare_contradiction(
                a, b, actor=self.actor, auto=True,
                signal="llm-consolidation")
            if any(e["event_id"] == eid
                   for e in self.L.open_contradictions()):
                report["contradictions_declared"].append(eid)
            else:
                report["contradictions_held"].append(eid)

        report["supports_proposed"] = valid["supports"]
        return report
