"""Tests for the market picture calculations (synthetic tables only)."""

import math

import numpy as np
import pandas as pd
import pytest

from tamarket import picture as P
from tamarket.mhclg import ACCOMMODATION_TYPES


def test_trapezoid_and_gaps():
    assert P.trapezoid([100, 100, 100, 100, 100]) == 100
    assert P.trapezoid([0, 40, 80, 120, 160]) == 80
    assert math.isnan(P.trapezoid([0, np.nan, 80, 120, 160]))
    assert list(P.fill_one_gap([0, np.nan, 80, 120, 160])) == [0, 40, 80, 120, 160]
    assert list(P.fill_one_gap([np.nan, 40, 80, 120, 160])) == [40, 40, 80, 120, 160]
    assert list(P.fill_one_gap([0, 40, 80, 120, np.nan])) == [0, 40, 80, 120, 120]
    two = P.fill_one_gap([np.nan, np.nan, 80, 120, 160])
    assert np.isnan(two[:2]).all()


def test_snapshot_quarters():
    assert P.snapshot_quarters("2024-25") == ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4", "2025-Q1"]


def make_ta1(councils: dict[str, list[float]]) -> pd.DataFrame:
    """councils: code -> five totals (NaN allowed). Types: half nightly-paid, half leased."""
    rows = []
    qs = P.snapshot_quarters("2024-25")
    eng = [sum(np.nan_to_num(v[i]) for v in councils.values()) for i in range(5)]
    for code, totals in {**councils, P.ENGLAND: eng, P.LONDON: eng}.items():
        level = "england" if code == P.ENGLAND else "region" if code == P.LONDON else "council"
        for q, t in zip(qs, totals):
            rec = {"quarter": q, "code": code, "name": code, "level": level, "total": t, "with_children": t / 2}
            for ty in ACCOMMODATION_TYPES:
                rec[ty] = 0.0 if not np.isnan(t) else np.nan
            rec["nightly_paid_self_contained"] = t / 2
            rec["private_sector_leased"] = t / 2
            rows.append(rec)
    return pd.DataFrame(rows)


def make_ro4(spend: dict[str, float]) -> pd.DataFrame:
    rows = []
    for code, te in {**spend, P.ENGLAND: sum(v for v in spend.values() if not np.isnan(v))}.items():
        rec = {"year": "2024-25", "ons_code": code, "la_name": code, "e_code": "E0000",
               "class": "Eng" if code == P.ENGLAND else ("LB" if code.startswith("E09") else "SD"),
               "certification": "Y", "housing_authority": code != P.ENGLAND}
        for line in [*ACCOMMODATION_TYPES, "ta_admin", "total_homelessness"]:
            rec[f"{line}_te"] = 0.0 if not np.isnan(te) else np.nan
            rec[f"{line}_nce"] = 0.0 if not np.isnan(te) else np.nan
        rec["nightly_paid_self_contained_te"] = te * 0.6
        rec["private_sector_leased_te"] = te * 0.4
        rec["nightly_paid_self_contained_nce"] = te * 0.3
        rec["private_sector_leased_nce"] = te * 0.1
        rows.append(rec)
    return pd.DataFrame(rows)


@pytest.fixture
def tables():
    councils = {
        "E07000001": [100] * 5,                     # 1.0m -> 10,000
        "E07000002": [200] * 5,                     # 2.0m -> 10,000
        "E07000003": [100, np.nan, 100, 100, 100],  # one gap: estimated
        "E07000004": [np.nan, np.nan, 100, 100, 100],  # two gaps: not compared
        "E07000005": [20] * 5,                      # too small
        "E07000006": [300] * 5,                     # zero spend: not compared
        "E07000007": [150] * 5,                     # 4.5m -> 30,000: a lead (3x the median)
    }
    spend = {"E07000001": 1e6, "E07000002": 2e6, "E07000003": 1e6, "E07000004": 1e6, "E07000005": 1e6,
             "E07000006": 0.0, "E07000007": 4.5e6}
    return make_ta1(councils), make_ro4(spend)


def test_council_table_rules(tables):
    ta1, ro4 = tables
    t = P.council_table(ta1, ro4, "2024-25").set_index("code")
    assert t.loc["E07000001", "gross_per_household"] == pytest.approx(10_000)
    assert t.loc["E07000003", "estimated"] and t.loc["E07000003", "compared"]
    assert not t.loc["E07000004", "compared"] and "2 of 5" in t.loc["E07000004", "not_compared_because"]
    assert not t.loc["E07000005", "compared"] and "fewer than" in t.loc["E07000005", "not_compared_because"]
    assert not t.loc["E07000006", "compared"] and "nothing positive" in t.loc["E07000006", "not_compared_because"]
    # Ranked: 10k, 10k, 10k, 30k -> median 10k; 30k is 3x -> a lead (150 households >= 100)
    assert t.loc["E07000007", "lead_high_cost"]
    assert not t.loc["E07000001", "lead_high_cost"]
    assert t.loc["E07000001", "share_households_np_bb"] == pytest.approx(0.5)
    assert t.loc["E07000001", "share_spend_np_bb"] == pytest.approx(0.6)


def test_councils_left_out_for_a_data_check_are_not_compared_and_move_the_median(tables):
    ta1, ro4 = tables
    base = P.council_table(ta1, ro4, "2024-25").set_index("code")
    t = P.council_table(ta1, ro4, "2024-25", left_out={"E07000007", "E07000004"}).set_index("code")
    # Only a council that would otherwise be compared gets the reason; others keep their own.
    assert not t.loc["E07000007", "compared"] and t.loc["E07000007", "not_compared_because"] == P.LEFT_OUT_REASON
    assert t.loc["E07000004", "not_compared_because"] == base.loc["E07000004", "not_compared_because"]
    # The peer median and the flags are over the councils left in.
    assert not t.loc["E07000007", "lead_high_cost"]
    assert P.group_figures(t.reset_index(), "England").councils_compared == 3
    assert t.loc["E07000001", "peer_median_gross"] == pytest.approx(10_000)


def test_group_and_national_figures(tables):
    ta1, ro4 = tables
    t = P.council_table(ta1, ro4, "2024-25")
    g = P.group_figures(t, "England")
    assert g.councils_compared == 4
    assert g.gross_per_household == pytest.approx((1e6 + 2e6 + 1e6 + 4.5e6) / (100 + 200 + 100 + 150))
    s = P.group_figures(t, "England", strict=True)
    assert s.councils_compared == 3
    n = P.national_figures(ta1, ro4, "2024-25")
    assert n["te_accom_england_row"] == pytest.approx(10.5e6)
    assert n["by_type"]["nightly_paid_self_contained"]["te"] == pytest.approx(10.5e6 * 0.6)


def test_recodes_are_applied():
    ta1 = make_ta1({"E08000016": [100] * 5})
    ta1.loc[ta1["quarter"] == "2025-Q1", "code"] = ta1.loc[ta1["quarter"] == "2025-Q1", "code"].replace(
        {"E08000016": "E08000038"})
    ro4 = make_ro4({"E08000016": 1e6})
    t = P.council_table(ta1, ro4, "2024-25")
    assert t.loc[t["code"] == "E08000038", "snapshots"].item() == 5
