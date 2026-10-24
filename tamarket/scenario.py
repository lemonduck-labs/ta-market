"""A savings scenario on a council's own inputs: arithmetic only, never a forecast.

The council sets every input: how many households move from one type of accommodation to
another, its own price gap per household-year between the two types, the one-off set-up cost
per household, the void and repair cost per household-year on the new homes, and the lease
term. run_scenario() echoes the inputs back and does the arithmetic below; nothing is
estimated, discounted or inflated. A difference between two types of accommodation is not a
saving in itself: households, places and lease costs differ [Likely].

With H households moved, price gap G, set-up cost S, void cost V and lease term T years:

    gross_difference_per_year = H * G
    void_cost_per_year        = H * V
    net_difference_per_year   = H * (G - V)
    set_up_cost               = H * S
    net_difference_over_term  = T * H * (G - V) - H * S
    payback_years             = S / (G - V), only when G - V > 0
    recovered_within_term     = payback_years <= T

Rounding, stated so that a port gets the same numbers: each money result is computed from the
unrounded inputs in the order written above, in IEEE 754 double precision, then rounded to
whole pounds, halves away from zero (sign(x) * floor(|x| + 0.5)). payback_years is rounded to 2
decimal places the same way (sign(x) * floor(|x| * 100 + 0.5) / 100). Notes are returned as
ids; their wording is in NOTE_TEXTS.

The test cases a JavaScript port must pass are in tamarket/spec/scenario_cases.json.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

from tamarket.mhclg import ACCOMMODATION_TYPES

SPEC_VERSION = "1"
MAX_LEASE_YEARS = 30
NUMBERS = ("price_gap_per_household_year", "setup_cost_per_household", "void_cost_per_household_year",
           "lease_term_years")
FIELDS = ("households_moved", "from_type", "to_type", *NUMBERS, "households_on_from_type")
REQUIRED = FIELDS[:-1]
NOTE_TEXTS = {
    "never_recovered": "On these inputs the new homes cost the same or more each year once voids are counted, so the "
                       "set-up cost is never recovered [Certain: arithmetic].",
    "not_recovered_in_term": "On these inputs the set-up cost is not recovered within the lease term "
                             "[Certain: arithmetic].",
    "negative_gap": "A negative price gap means the new type costs more per household-year on your inputs [Certain].",
}
STATEMENT = "Arithmetic on the inputs you set. Not a forecast, and not a saving the council will make."
CAVEATS = [
    "Households, places and lease costs differ between types of accommodation, and leasing has set-up and void "
    "costs [Likely].",
    "No discounting, inflation, change in demand or change in prices is applied [Certain].",
]
ROUNDING = ("Money results are whole pounds, rounded halves away from zero from the unrounded arithmetic; "
            "payback years to 2 decimal places the same way.")
FORMULAE = {
    "gross_difference_per_year": "households_moved * price_gap_per_household_year",
    "void_cost_per_year": "households_moved * void_cost_per_household_year",
    "net_difference_per_year": "households_moved * (price_gap_per_household_year - void_cost_per_household_year)",
    "set_up_cost": "households_moved * setup_cost_per_household",
    "net_difference_over_term": "lease_term_years * households_moved * (price_gap_per_household_year - "
                                "void_cost_per_household_year) - households_moved * setup_cost_per_household",
    "payback_years": "setup_cost_per_household / (price_gap_per_household_year - void_cost_per_household_year), "
                     "only when the difference is above 0",
}


class ScenarioInputError(ValueError):
    """Raised with every problem found, in field order, as {"field", "error"} dicts."""

    def __init__(self, errors: list[dict]):
        self.errors = errors
        super().__init__("; ".join(f"{e['field']}: {e['error']}" for e in errors))


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def whole_pounds(x: float) -> int:
    """Whole pounds, halves away from zero."""
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def two_places(x: float) -> float:
    """Two decimal places, halves away from zero."""
    return math.copysign(math.floor(abs(x) * 100 + 0.5), x) / 100


def validate_inputs(inputs: Mapping) -> list[dict]:
    """Every problem with the inputs, in the order of FIELDS, then fields that are not inputs."""
    errs: list[dict] = []

    def err(field: str, msg: str):
        errs.append({"field": field, "error": msg})

    if not isinstance(inputs, Mapping):
        return [{"field": "inputs", "error": "must be an object"}]
    one_of = "must be one of: " + ", ".join(ACCOMMODATION_TYPES)
    for f in REQUIRED:
        if f not in inputs:
            err(f, "required")
            continue
        v = inputs[f]
        if f == "households_moved":
            if not _is_number(v):
                err(f, "must be a number")
            elif not float(v).is_integer():
                err(f, "must be a whole number")
            elif v < 1:
                err(f, "must be at least 1")
        elif f in ("from_type", "to_type"):
            if not isinstance(v, str) or v not in ACCOMMODATION_TYPES:
                err(f, one_of)
            elif f == "to_type" and v == inputs.get("from_type"):
                err(f, "must differ from from_type")
        elif not _is_number(v):
            err(f, "must be a number")
        elif f in ("setup_cost_per_household", "void_cost_per_household_year") and v < 0:
            err(f, "must be 0 or more")
        elif f == "lease_term_years" and not v > 0:
            err(f, "must be more than 0")
        elif f == "lease_term_years" and v > MAX_LEASE_YEARS:
            err(f, f"must be {MAX_LEASE_YEARS} or less")
    if "households_on_from_type" in inputs:
        cap = inputs["households_on_from_type"]
        if not _is_number(cap):
            err("households_on_from_type", "must be a number")
        elif cap < 0:
            err("households_on_from_type", "must be 0 or more")
        elif _is_number(inputs.get("households_moved")) and inputs["households_moved"] > cap:
            err("households_moved", "must not be more than households_on_from_type")
    for f in sorted(k for k in inputs if k not in FIELDS):
        err(str(f), "not an input")
    return errs


def run_scenario(inputs: Mapping) -> dict:
    """The arithmetic on valid inputs, with the inputs echoed back. Raises ScenarioInputError
    listing every problem when the inputs are not valid."""
    errors = validate_inputs(inputs)
    if errors:
        raise ScenarioInputError(errors)
    h = inputs["households_moved"]
    g = inputs["price_gap_per_household_year"]
    s = inputs["setup_cost_per_household"]
    v = inputs["void_cost_per_household_year"]
    t = inputs["lease_term_years"]
    per_household = g - v
    payback = two_places(s / per_household) if per_household > 0 else None
    notes = []
    if g < 0:
        notes.append("negative_gap")
    if payback is None:
        notes.append("never_recovered")
    elif payback > t:
        notes.append("not_recovered_in_term")
    return {
        "spec_version": SPEC_VERSION,
        "kind": "arithmetic on your inputs",
        "statement": STATEMENT,
        "inputs": {f: inputs[f] for f in FIELDS if f in inputs},
        "results": {
            "gross_difference_per_year": whole_pounds(h * g),
            "void_cost_per_year": whole_pounds(h * v),
            "net_difference_per_year": whole_pounds(h * (g - v)),
            "set_up_cost": whole_pounds(h * s),
            "net_difference_over_term": whole_pounds(t * h * (g - v) - h * s),
            "payback_years": payback,
            "recovered_within_term": payback is not None and payback <= t,
        },
        "notes": notes,
        "rounding": ROUNDING,
        "formulae": FORMULAE,
        "caveats": CAVEATS,
    }


def evaluate(inputs: Mapping) -> dict:
    """{"errors": [...]} for invalid inputs, else {"results": ..., "notes": ...}: the shape the
    shared test cases use."""
    errors = validate_inputs(inputs)
    if errors:
        return {"errors": errors}
    out = run_scenario(inputs)
    return {"results": out["results"], "notes": out["notes"]}


#: Inputs for the shared test cases (tamarket/spec/scenario_cases.json), each with why it is there.
CASE_INPUTS = [
    ("typical move", {"households_moved": 20, "from_type": "nightly_paid_self_contained",
                      "to_type": "private_sector_leased", "price_gap_per_household_year": 4000,
                      "setup_cost_per_household": 1500, "void_cost_per_household_year": 500, "lease_term_years": 5}),
    ("no set-up or void cost", {"households_moved": 1, "from_type": "bed_and_breakfast", "to_type": "hostels",
                                "price_gap_per_household_year": 1000, "setup_cost_per_household": 0,
                                "void_cost_per_household_year": 0, "lease_term_years": 1}),
    ("negative gap", {"households_moved": 20, "from_type": "private_sector_leased",
                      "to_type": "nightly_paid_self_contained", "price_gap_per_household_year": -2000,
                      "setup_cost_per_household": 1000, "void_cost_per_household_year": 300, "lease_term_years": 5}),
    ("void cost equals the gap", {"households_moved": 12, "from_type": "nightly_paid_self_contained",
                                  "to_type": "private_sector_leased", "price_gap_per_household_year": 500,
                                  "setup_cost_per_household": 250, "void_cost_per_household_year": 500,
                                  "lease_term_years": 3}),
    ("payback after the term", {"households_moved": 10, "from_type": "nightly_paid_self_contained",
                                "to_type": "private_sector_leased", "price_gap_per_household_year": 1000,
                                "setup_cost_per_household": 6000, "void_cost_per_household_year": 200,
                                "lease_term_years": 3}),
    ("decimals and a part-year term", {"households_moved": 7, "from_type": "hostels", "to_type": "la_ha_stock",
                                       "price_gap_per_household_year": 1234.56, "setup_cost_per_household": 789.1,
                                       "void_cost_per_household_year": 100.25, "lease_term_years": 2.5}),
    ("halves round away from zero", {"households_moved": 3, "from_type": "other", "to_type": "hostels",
                                     "price_gap_per_household_year": 0.5, "setup_cost_per_household": 0.5,
                                     "void_cost_per_household_year": 0, "lease_term_years": 1}),
    ("negative halves round away from zero", {"households_moved": 3, "from_type": "hostels", "to_type": "other",
                                              "price_gap_per_household_year": -0.5, "setup_cost_per_household": 0,
                                              "void_cost_per_household_year": 0, "lease_term_years": 2}),
    ("within the households on the type", {"households_moved": 30, "from_type": "bed_and_breakfast",
                                           "to_type": "private_sector_leased", "price_gap_per_household_year": 9000,
                                           "setup_cost_per_household": 2000, "void_cost_per_household_year": 750,
                                           "lease_term_years": 10, "households_on_from_type": 40}),
    ("no households moved", {"households_moved": 0, "from_type": "nightly_paid_self_contained",
                             "to_type": "private_sector_leased", "price_gap_per_household_year": 4000,
                             "setup_cost_per_household": 1500, "void_cost_per_household_year": 500,
                             "lease_term_years": 5}),
    ("several bad inputs at once", {"households_moved": 2.5, "from_type": "hotel",
                                    "price_gap_per_household_year": "1000", "setup_cost_per_household": -5,
                                    "void_cost_per_household_year": -1, "lease_term_years": 0}),
    ("same type twice and too long a term", {"households_moved": 5, "from_type": "hostels", "to_type": "hostels",
                                             "price_gap_per_household_year": 100, "setup_cost_per_household": 0,
                                             "void_cost_per_household_year": 0, "lease_term_years": 31}),
    ("more households than are on the type", {"households_moved": 50, "from_type": "bed_and_breakfast",
                                              "to_type": "private_sector_leased",
                                              "price_gap_per_household_year": 9000, "setup_cost_per_household": 2000,
                                              "void_cost_per_household_year": 750, "lease_term_years": 10,
                                              "households_on_from_type": 40}),
    ("a yes or no is not a number, and unknown inputs", {"households_moved": True,
                                                        "from_type": "nightly_paid_self_contained",
                                                        "to_type": "private_sector_leased",
                                                        "price_gap_per_household_year": 4000,
                                                        "setup_cost_per_household": 1500,
                                                        "void_cost_per_household_year": 500, "lease_term_years": 5,
                                                        "discount_rate": 0.035}),
]


def spec_cases() -> dict:
    """The shared test cases, with Python's exact outputs."""
    return {
        "spec_version": SPEC_VERSION,
        "about": ("Inputs for tamarket/scenario.py with its exact outputs, for testing a port of the arithmetic. "
                  "Arithmetic on the inputs a council sets, never a forecast."),
        "formulae": FORMULAE,
        "rounding": ("Each money result: sign(x) * floor(|x| + 0.5) on the unrounded value, computed in the order of "
                     "the formulae in IEEE 754 double precision. payback_years: sign(x) * floor(|x| * 100 + 0.5) / 100, "
                     "or null when the net difference per household-year is 0 or less. recovered_within_term: "
                     "payback_years is not null and is at most lease_term_years."),
        "validation": ("Errors are listed in the order of the required fields (" + ", ".join(REQUIRED) + "), then "
                       "the checks on households_on_from_type (its own error, or households_moved over it), then "
                       "every field that is not an input, sorted. A required field gives at most one error. A value "
                       "is a number only when it is a finite number and not true or false."),
        "note_texts": NOTE_TEXTS,
        "max_lease_years": MAX_LEASE_YEARS,
        "accommodation_types": list(ACCOMMODATION_TYPES),
        "cases": [{"id": f"s{i + 1:02d}", "what": what, "inputs": inputs, "expected": evaluate(inputs)}
                  for i, (what, inputs) in enumerate(CASE_INPUTS)],
    }
