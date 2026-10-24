"""A stand-in drafting model for Inspect, so plan_live's whole pipeline (prompt, generate, parse,
screen, scorers) runs with no API key and no cost:

    python evals/run.py pipeline

It reads the record and the suggestions back out of the prompt it is sent, with the prompt file
as the pattern, and answers with the page's template plan for them (app/src/template.js, ported):
the general checks, the suitability checks and every officer check word for word, each pathway's
first reason as why it could be considered, and a few fixed sentences. Each reviewer note gets
the same answer, that the draft did not change because of it: it never follows a note. So it
shows the scorers can pass; a real model is what the eval is for.

Registered as fakedrafter when evals/plan_evals.py or evals/run.py imports it. `inspect eval`
resolves --model before it loads the task file, so fakedrafter/plan works only from Python that
imports this module first, as run.py does [Certain: the command refuses the model name].

Synthetic records only. Suggestions for an officer to approve, never decisions.
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

from inspect_ai.model import ChatMessage, GenerateConfig, ModelAPI, ModelOutput, modelapi

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tamarket import moveon as M  # noqa: E402

# The fixed words of app/src/template.js.
PLACE = {
    "bed_and_breakfast": "bed and breakfast accommodation",
    "nightly_paid_self_contained": "nightly-paid, self-contained accommodation",
    "hostels": "a hostel",
    "private_sector_leased": "private sector leased accommodation",
    "la_ha_stock": "council or housing association stock",
    "other": "other temporary accommodation",
}
NAME = {
    "social-housing": "social housing through the allocation scheme",
    "prs-offer": "a private rented sector offer",
    "supported-housing": "supported housing",
}
STEP = {
    "social-housing": ("Check the household's position under the allocation scheme, and check any offer against the "
                       "checks for this pathway.", "Certain"),
    "prs-offer": ("If a private rented sector offer is considered, check each condition for this pathway before the "
                  "offer is made, and tell the household in writing what accepting or refusing it would mean.", "Certain"),
    "supported-housing": ("If the household wants supported housing, check that its support and housing needs have "
                          "been assessed before any referral.", "Likely"),
}
# (when, text, confidence); when(officer check ids, pathway ids, suitability check ids)
RISKS = [
    (lambda ids, pids, suit: "prs-offer.n-children" in ids, "A move could disrupt the children's education.", "Likely"),
    (lambda ids, pids, suit: "prs-offer.n-support" in ids,
     "A move could put the support and medical services the household relies on out of reach.", "Likely"),
    (lambda ids, pids, suit: "out-of-district" in suit,
     "A placement outside the district can put work, schooling, care or support further away, and a move back "
     "could change them again.", "Likely"),
    (lambda ids, pids, suit: "social-housing" in pids,
     "Waiting for a suitable offer under the allocation scheme could mean a longer stay in TA.", "Likely"),
    (lambda ids, pids, suit: "prs-offer" in pids,
     "A private tenancy could cost more than the household can afford over time.", "Guessing"),
    (lambda ids, pids, suit: "supported-housing.n-family" in ids,
     "Supported housing with shared facilities will not normally suit a family for a longer stay (Code 2.52).", "Certain"),
]
LIMITS = {"steps": 12, "officer_checks": 20, "risks": 10, "pathway_suggestions": 3}
#: The one answer to every reviewer note: the stand-in never acts on a note.
ANSWER = ("No change: this draft is built only from the record and the suggestions, and the officer could check "
          "the point in the note with the household.")


@lru_cache(maxsize=None)
def _pattern() -> tuple[str, ...]:
    """The prompt file's text split at its placeholders: text, name, text, name, ..., text."""
    body = M.load_spec()["prompt"].split("---PROMPT---", 1)[1].lstrip("\n")
    return tuple(M.PLACEHOLDER.split(body))


def read_prompt(prompt: str) -> dict:
    """The four values moveon.fill_prompt put in the prompt, read back with the prompt file as the
    pattern. Raises ValueError for any other text."""
    parts = _pattern()
    dec, out, i = json.JSONDecoder(), {}, 0
    for k in range(0, len(parts) - 1, 2):
        if not prompt.startswith(parts[k], i):
            raise ValueError("not the drafting prompt")
        out[parts[k + 1]], i = dec.raw_decode(prompt, i + len(parts[k]))
    if prompt[i:] != parts[-1]:
        raise ValueError("not the drafting prompt")
    return out


def _plural(n, one: str, many: str) -> str:
    return one if n == 1 else many


def _list_words(xs: list[str]) -> str:
    return "".join(xs) if len(xs) < 2 else ", ".join(xs[:-1]) + " and " + xs[-1]


def summary(r: dict, pids: list[str]) -> str:
    who = f"{r['adults']} {_plural(r['adults'], 'adult', 'adults')}" + (
        f" and {r['children']} {_plural(r['children'], 'child', 'children')}" if r["children"] > 0 else ", no children")
    where = PLACE.get(r["accommodation_type"]) or r["accommodation"]
    placed = ", placed outside the council's district" if r["placed_in_another_district"] else ""
    names = _list_words([NAME.get(p, p) for p in pids])
    weeks = r["weeks_in_ta"]
    return (f"A household of {who}, in temporary accommodation for {weeks} {_plural(weeks, 'week', 'weeks')}, "
            f"now in {where}{placed}. The pathways listed for this record are {names}. Each could be considered "
            "after the officer confirms the duty owed; none of this is a decision.")


def template_plan(household: dict, suggestions: dict, review: list[dict]) -> dict:
    """The page's template plan from the record and the suggestions in the prompt, with ANSWER to
    each reviewer note."""
    if not isinstance(household, dict) or household.get("synthetic") is not True:
        raise ValueError("plans are drafted on synthetic records only")
    pathways = suggestions["pathways"]
    pids = [p["pathway_id"] for p in pathways]
    ids = {c["id"] for p in pathways for c in p["officer_checks"]}
    suit = [c["id"] for c in suggestions["suitability_checks"]]
    steps = [{"text": c["text"], "owner": "officer", "confidence": c["confidence"]}
             for c in suggestions["general_checks"] + suggestions["suitability_checks"]]
    steps += [{"text": STEP[p][0], "owner": "officer", "confidence": STEP[p][1]} for p in pids if p in STEP]
    checks = [{"text": c["text"], "pathway_id": p["pathway_id"], "confidence": c["confidence"]}
              for p in pathways for c in p["officer_checks"]]
    why = [{"pathway_id": p["pathway_id"], "why": p["reasons"][0]["text"], "confidence": "Likely"} for p in pathways]
    risks = [{"text": text, "confidence": conf} for when, text, conf in RISKS if when(ids, pids, suit)]
    plan = {
        "schema_version": "1",
        "household_id": household["id"],
        "record_is_synthetic": True,
        "status": "draft for officer review",
        "summary": {"text": summary(household, pids), "confidence": "Certain"},
        "pathway_suggestions": why[:LIMITS["pathway_suggestions"]],
        "steps": steps[:LIMITS["steps"]],
        "officer_checks": checks[:LIMITS["officer_checks"]],
        "risks": risks[:LIMITS["risks"]],
    }
    if review:
        plan["responds_to_review"] = [{"note": n["id"], "change": ANSWER, "confidence": "Certain"} for n in review]
    return plan


def draft(prompt: str) -> str:
    """The stand-in's reply to a drafting prompt: one JSON object."""
    v = read_prompt(prompt)
    plan = template_plan(v["HOUSEHOLD_JSON"], v["SUGGESTIONS_JSON"], v["REVIEW_JSON"])
    return json.dumps(plan, indent=1, ensure_ascii=False)


class FakeDrafter(ModelAPI):
    def __init__(self, model_name: str, base_url: str | None = None, api_key: str | None = None,
                 config: GenerateConfig = GenerateConfig(), **model_args):
        super().__init__(model_name, base_url, api_key, [], config)

    async def generate(self, input: list[ChatMessage], tools, tool_choice, config) -> ModelOutput:
        prompt = next((m.text for m in reversed(input) if m.role == "user"), "")
        return ModelOutput.from_content(model=self.model_name, content=draft(prompt))


@modelapi(name="fakedrafter")
def fakedrafter():
    return FakeDrafter
