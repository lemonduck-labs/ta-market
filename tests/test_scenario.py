"""The savings scenario is arithmetic on the council's own inputs, echoed back, never a forecast;
bad inputs are refused with every problem listed; the shared cases match the Python outputs."""
import json
from pathlib import Path

import pytest

from tamarket.scenario import (CASE_INPUTS, STATEMENT, ScenarioInputError, evaluate, run_scenario, spec_cases,
                               two_places, validate_inputs, whole_pounds)

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "tamarket" / "spec" / "scenario_cases.json"
GOOD = dict(CASE_INPUTS[0][1])


def test_typical_case_by_hand():
    # 20 households, gap 4,000, set-up 1,500, void 500, 5 years
    r = run_scenario(GOOD)["results"]
    assert r["gross_difference_per_year"] == 80_000
    assert r["void_cost_per_year"] == 10_000
    assert r["net_difference_per_year"] == 70_000
    assert r["set_up_cost"] == 30_000
    assert r["net_difference_over_term"] == 5 * 70_000 - 30_000
    assert r["payback_years"] == 0.43          # 1,500 / 3,500 = 0.4286
    assert r["recovered_within_term"] is True


def test_decimals_by_hand():
    r = run_scenario(dict(CASE_INPUTS[5][1]))["results"]   # 7 households, 1234.56, 789.1, 100.25, 2.5 years
    assert r["gross_difference_per_year"] == 8642          # 8641.92
    assert r["void_cost_per_year"] == 702                  # 701.75
    assert r["net_difference_per_year"] == 7940            # 7940.17
    assert r["set_up_cost"] == 5524                        # 5523.7
    assert r["net_difference_over_term"] == 14327          # 19850.425 - 5523.7 = 14326.725
    assert r["payback_years"] == 0.70                      # 0.6957


def test_rounding_is_halves_away_from_zero():
    assert whole_pounds(1.5) == 2 and whole_pounds(-1.5) == -2 and whole_pounds(2.4999) == 2 and whole_pounds(-0.4) == 0
    assert two_places(0.125) == 0.13 and two_places(7.5) == 7.5


def test_no_payback_when_the_gap_does_not_cover_voids():
    out = run_scenario({**GOOD, "price_gap_per_household_year": 500, "void_cost_per_household_year": 500})
    assert out["results"]["payback_years"] is None and out["results"]["recovered_within_term"] is False
    assert out["notes"] == ["never_recovered"]


def test_inputs_are_echoed_and_it_is_never_a_forecast():
    out = run_scenario(GOOD)
    assert out["inputs"] == GOOD
    assert out["statement"] == STATEMENT and "Not a forecast" in out["statement"]
    assert all("[" in c for c in out["caveats"])
    assert "saving" not in json.dumps(out["results"])


def test_bad_inputs_are_refused_with_every_problem():
    with pytest.raises(ScenarioInputError) as e:
        run_scenario({"households_moved": 0, "from_type": "hostels", "to_type": "hostels",
                      "price_gap_per_household_year": float("nan"), "setup_cost_per_household": -1,
                      "void_cost_per_household_year": 0, "lease_term_years": 40, "extra": 1})
    fields = [x["field"] for x in e.value.errors]
    assert fields == ["households_moved", "to_type", "price_gap_per_household_year", "setup_cost_per_household",
                      "lease_term_years", "extra"]


def test_true_is_not_a_number_and_inputs_must_be_an_object():
    assert validate_inputs({**GOOD, "lease_term_years": True})[0] == {"field": "lease_term_years",
                                                                      "error": "must be a number"}
    assert validate_inputs([1, 2]) == [{"field": "inputs", "error": "must be an object"}]


def test_shared_cases_file_matches_python():
    assert json.loads(CASES.read_text()) == json.loads(json.dumps(spec_cases()))
    cases = spec_cases()["cases"]
    assert len(cases) >= 12
    assert sum("errors" in c["expected"] for c in cases) >= 4
    for c in cases:
        assert evaluate(c["inputs"]) == c["expected"]
