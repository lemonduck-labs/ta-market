"""The temporary accommodation market picture: cost per household, mix, change.

Everything here works on the processed tables written by scripts/build_from_extracts.py
(ta1_wide.csv and ro4_wide.csv). Definitions, so that every number can be re-derived:

* Financial year Y runs from 1 April Y to 31 March Y+1. Its five snapshots are the
  quarter-end counts on 31 March Y, 30 June, 30 September, 31 December and 31 March Y+1.
* Average households in TA over the year is the trapezoid over those five snapshots:
  (0.5 * first + the three middle + 0.5 * last) / 4. A council with one snapshot missing
  gets an estimate (see fill_one_gap) and is marked as estimated; with two or more missing
  it gets no figure.
* Accommodation spend is RO4 lines 80 to 85 (the six TA types). Line 86, TA
  administration, is reported separately. Gross means total expenditure (C3); net
  means net current expenditure (C7), which is gross less income such as rents and
  housing benefit.
* Gross (net) spend per household is accommodation spend divided by the average
  households in TA. It is an average outturn per household-year, not a price.

A council far from its peers is a question for a person to look into, never a finding, and
nothing here assesses any council.

Contains public sector information licensed under the Open Government Licence v3.0.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from tamarket.mhclg import ACCOMMODATION_TYPES

ENGLAND = "E92000001"
LONDON = "E12000007"

#: Recoded councils, old code -> new code (from config/code_changes.csv, 1 April 2025).
RECODES = {"E08000016": "E08000038", "E08000019": "E08000039"}

#: The smallest average number of households in TA for a council to be compared.
MIN_HOUSEHOLDS = 50
#: A high-cost lead: more than this multiple of the peer median, with at least
#: LEAD_MIN_HOUSEHOLDS households on average.
PEER_MULTIPLE = 2.0
LEAD_MIN_HOUSEHOLDS = 100
#: Below this fraction of the peer median, spend is probably recorded somewhere other
#: than the TA lines (for example the housing revenue account); check before any use.
LOW_RATIO = 0.25

TYPE_LABELS = {
    "bed_and_breakfast": "Bed and breakfast",
    "nightly_paid_self_contained": "Nightly-paid, self-contained",
    "hostels": "Hostels",
    "private_sector_leased": "Private sector leased",
    "la_ha_stock": "Council or housing association stock",
    "other": "Other",
}


def snapshot_quarters(year: str) -> list[str]:
    """'2024-25' -> ['2024-Q1', '2024-Q2', '2024-Q3', '2024-Q4', '2025-Q1']."""
    start = int(year[:4])
    return [f"{start}-Q1", f"{start}-Q2", f"{start}-Q3", f"{start}-Q4", f"{start + 1}-Q1"]


def trapezoid(values) -> float:
    """Average over a year from five quarter-end snapshots; NaN if any is missing."""
    v = np.asarray(values, dtype=float)
    if v.shape != (5,) or np.isnan(v).any():
        return np.nan
    return float((0.5 * v[0] + v[1:4].sum() + 0.5 * v[4]) / 4)


def fill_one_gap(values) -> np.ndarray:
    """Fill at most one missing snapshot of five: an inner one by straight-line
    interpolation between its neighbours, an end one with its neighbour's value.
    More than one gap is left as it is (the trapezoid then stays NaN)."""
    v = np.asarray(values, dtype=float).copy()
    gaps = np.flatnonzero(np.isnan(v))
    if len(gaps) != 1:
        return v
    i = int(gaps[0])
    if i == 0:
        v[0] = v[1]
    elif i == len(v) - 1:
        v[i] = v[i - 1]
    else:
        v[i] = (v[i - 1] + v[i + 1]) / 2
    return v


#: For comparison, one snapshot of five may be estimated, two may not.
MIN_SNAPSHOTS = 4


def harmonise(df: pd.DataFrame, code_col: str) -> pd.DataFrame:
    out = df.copy()
    out[code_col] = out[code_col].replace(RECODES)
    return out


def london(code: str) -> bool:
    return str(code).startswith("E09")


# ---------------------------------------------------------------------------
# Households
# ---------------------------------------------------------------------------

def average_households(ta1: pd.DataFrame, year: str) -> pd.DataFrame:
    """Per area (councils, regions, England): the five snapshots, their trapezoid
    average for the total and each type, and how many snapshots are present."""
    qs = snapshot_quarters(year)
    t = harmonise(ta1[ta1["quarter"].isin(qs)], "code")
    have = set(t["quarter"])
    missing_q = [q for q in qs if q not in have]
    if missing_q:
        raise ValueError(f"{year}: snapshots missing from ta1: {missing_q}")
    cols = ["total", "with_children", *ACCOMMODATION_TYPES]
    rows = []
    for code, g in t.groupby("code"):
        g = g.set_index("quarter").reindex(qs)
        n = int(g["total"].notna().sum())
        rec = {"code": code, "name": g["name"].dropna().iloc[-1], "level": g["level"].dropna().iloc[-1],
               "snapshots": n, "estimated": n == MIN_SNAPSHOTS}
        for c in cols:
            # Exact when all five snapshots are present; one missing snapshot is
            # estimated (see fill_one_gap) and the row is marked as estimated.
            rec[f"avg_{c}"] = trapezoid(fill_one_gap(g[c].values))
            rec[f"avg_{c}_strict"] = trapezoid(g[c].values)
        for q in qs:
            rec[f"total_{q}"] = g.loc[q, "total"]
        rows.append(rec)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Spend
# ---------------------------------------------------------------------------

def spend(ro4: pd.DataFrame, year: str) -> pd.DataFrame:
    """Per authority for one year: accommodation spend (lines 80-85) gross and net,
    admin (86), each type gross, and flags."""
    r = harmonise(ro4[ro4["year"] == year], "ons_code")
    out = pd.DataFrame({"code": r["ons_code"], "ro4_name": r["la_name"], "class": r["class"],
                        "certification": r["certification"], "housing_authority": r["housing_authority"]})
    te = [f"{t}_te" for t in ACCOMMODATION_TYPES]
    nce = [f"{t}_nce" for t in ACCOMMODATION_TYPES]
    out["te_accom"] = r[te].sum(axis=1, min_count=len(te))
    out["nce_accom"] = r[nce].sum(axis=1, min_count=len(nce))
    out["te_admin"] = r["ta_admin_te"]
    out["nce_admin"] = r["ta_admin_nce"]
    out["te_ta_total"] = out["te_accom"] + out["te_admin"]
    out["te_total_homelessness"] = r["total_homelessness_te"]
    for t in ACCOMMODATION_TYPES:
        out[f"te_{t}"] = r[f"{t}_te"]
        out[f"nce_{t}"] = r[f"{t}_nce"]
    out["ro4_missing"] = out["te_accom"].isna()
    out["ta_lines_zero"] = (out["te_accom"] == 0) & (out["te_admin"].fillna(0) == 0)
    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Council table
# ---------------------------------------------------------------------------

#: The reason given for a council left out until a person checks its figures (tamarket/display.py).
LEFT_OUT_REASON = "left out for a data check"


def council_table(ta1: pd.DataFrame, ro4: pd.DataFrame, year: str, left_out: set[str] | None = None) -> pd.DataFrame:
    """One row per housing authority: households, spend, per-household figures, mix,
    flags, and whether the council can be compared with its peers. Councils in left_out
    (tamarket.display.left_out_codes: a data check outstanding) that would otherwise be compared
    are not compared, with LEFT_OUT_REASON, so the peer medians and flags are over the councils
    the shared outputs show."""
    hh = average_households(ta1, year)
    hh = hh[hh["level"] == "council"]
    sp = spend(ro4, year)
    sp = sp[sp["housing_authority"]]
    df = hh.merge(sp, on="code", how="outer", indicator=True)
    if (df["_merge"] != "both").any():
        odd = df.loc[df["_merge"] != "both", ["code", "name", "ro4_name", "_merge"]]
        raise ValueError(f"{year}: councils not in both sources:\n{odd}")
    df = df.drop(columns="_merge")
    df["year"] = year
    df["london"] = df["code"].map(london)
    df["gross_per_household"] = df["te_accom"] / df["avg_total"]
    df["net_per_household"] = df["nce_accom"] / df["avg_total"]
    df["share_households_np_bb"] = (df["avg_nightly_paid_self_contained"] + df["avg_bed_and_breakfast"]) / df["avg_total"]
    df["share_spend_np_bb"] = (df["te_nightly_paid_self_contained"] + df["te_bed_and_breakfast"]) / df["te_accom"]
    df["share_with_children"] = df["avg_with_children"] / df["avg_total"]
    te_cols = [f"te_{t}" for t in ACCOMMODATION_TYPES]
    has = df[te_cols].notna().all(axis=1) & (df["te_accom"] > 0)
    df["largest_line"] = None
    df.loc[has, "largest_line"] = df.loc[has, te_cols].idxmax(axis=1).str.removeprefix("te_")
    df["largest_line_share"] = np.nan
    df.loc[has, "largest_line_share"] = df.loc[has, te_cols].max(axis=1) / df.loc[has, "te_accom"]
    # Spend and household types should line up: spend on a type where the council reports
    # (on average) fewer than one household of that type cannot be per-household spend on it.
    unmatched = sum(df[f"te_{t}"].clip(lower=0).where(df[f"avg_{t}"] < 1, 0) for t in ACCOMMODATION_TYPES)
    positive = sum(df[f"te_{t}"].clip(lower=0) for t in ACCOMMODATION_TYPES)
    df["share_spend_on_types_without_households"] = (unmatched / positive).where(positive > 0)

    reasons = []
    for _, r in df.iterrows():
        why = []
        if r["snapshots"] < MIN_SNAPSHOTS:
            why.append(f"households: {5 - int(r['snapshots'])} of 5 snapshots missing")
        if r["ro4_missing"]:
            why.append("spend: no RO4 return")
        elif not r["te_accom"] > 0:
            why.append("spend: nothing positive recorded on TA lines 80 to 85")
        if pd.notna(r["avg_total"]) and r["avg_total"] < MIN_HOUSEHOLDS:
            why.append(f"fewer than {MIN_HOUSEHOLDS} households on average")
        if not why and left_out and r["code"] in left_out:
            why.append(LEFT_OUT_REASON)
        reasons.append("; ".join(why))
    df["not_compared_because"] = reasons
    df["compared"] = df["not_compared_because"] == ""
    df["peer_group"] = np.where(df["london"], "London", "Rest of England")
    df["peer_median_gross"] = np.nan
    for g, sub in df[df["compared"]].groupby("peer_group"):
        df.loc[df["peer_group"] == g, "peer_median_gross"] = sub["gross_per_household"].median()
    ratio = df["gross_per_household"] / df["peer_median_gross"]
    df["ratio_to_peer_median"] = ratio
    # Leads for a person to look into, never findings.
    df["lead_high_cost"] = df["compared"] & (df["avg_total"] >= LEAD_MIN_HOUSEHOLDS) & (ratio > PEER_MULTIPLE)
    df["check_recording"] = df["compared"] & (ratio < LOW_RATIO)
    return df.sort_values("code").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Group summaries
# ---------------------------------------------------------------------------

@dataclass
class GroupFigures:
    group: str
    councils: int
    councils_compared: int
    spend_te_accom_all: float          # every council with a return
    spend_te_accom_compared: float     # matched set only
    avg_households_compared: float
    gross_per_household: float         # matched set: sum spend / sum households
    net_per_household: float
    share_households_np_bb: float
    share_spend_np_bb: float

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def group_figures(table: pd.DataFrame, group: str, strict: bool = False) -> GroupFigures:
    """Matched-set figures for England, London or the rest of England: councils that
    can be compared, summed spend over summed households. strict=True keeps only
    councils with all five snapshots (no estimated snapshot)."""
    if group == "England":
        t = table
    elif group == "London":
        t = table[table["london"]]
    elif group == "Rest of England":
        t = table[~table["london"]]
    else:
        raise ValueError(group)
    m = t[t["compared"] & (~t["estimated"] if strict else True)]
    hh = m["avg_total"].sum()
    te = m["te_accom"].sum()
    return GroupFigures(
        group=group,
        councils=int(len(t)),
        councils_compared=int(len(m)),
        spend_te_accom_all=float(t["te_accom"].sum()),
        spend_te_accom_compared=float(te),
        avg_households_compared=float(hh),
        gross_per_household=float(te / hh),
        net_per_household=float(m["nce_accom"].sum() / hh),
        share_households_np_bb=float((m["avg_nightly_paid_self_contained"].sum() + m["avg_bed_and_breakfast"].sum()) / hh),
        share_spend_np_bb=float((m["te_nightly_paid_self_contained"].sum() + m["te_bed_and_breakfast"].sum()) / te),
    )


def national_figures(ta1: pd.DataFrame, ro4: pd.DataFrame, year: str) -> dict:
    """England from MHCLG's own England rows: the weighted TA1 England totals and the
    RO4 England row (which includes MHCLG's allowance for missing returns)."""
    hh = average_households(ta1, year)
    eng = hh[hh["code"] == ENGLAND].iloc[0]
    lon = hh[hh["code"] == LONDON].iloc[0]
    sp = spend(ro4, year)
    e = sp[sp["code"] == ENGLAND].iloc[0]
    out = {
        "year": year,
        "avg_households_england": float(eng["avg_total"]),
        "avg_households_london": float(lon["avg_total"]),
        "te_accom_england_row": float(e["te_accom"]),
        "nce_accom_england_row": float(e["nce_accom"]),
        "te_admin_england_row": float(e["te_admin"]),
        "te_ta_total_england_row": float(e["te_ta_total"]),
        "gross_per_household_england": float(e["te_accom"] / eng["avg_total"]),
        "net_per_household_england": float(e["nce_accom"] / eng["avg_total"]),
        "by_type": {},
    }
    for t in ACCOMMODATION_TYPES:
        h = float(eng[f"avg_{t}"])
        out["by_type"][t] = {
            "avg_households": h,
            "te": float(e[f"te_{t}"]),
            "nce": float(e[f"nce_{t}"]),
            "gross_per_household": float(e[f"te_{t}"] / h) if h else np.nan,
            "net_per_household": float(e[f"nce_{t}"] / h) if h else np.nan,
        }
    return out


def spend_by_year(ro4: pd.DataFrame) -> pd.DataFrame:
    """MHCLG England row per year: each line, accommodation total, admin, lines 80-86."""
    rows = []
    for year in sorted(ro4["year"].unique()):
        e = spend(ro4, year)
        e = e[e["code"] == ENGLAND].iloc[0]
        rec = {"year": year}
        for t in ACCOMMODATION_TYPES:
            rec[t] = e[f"te_{t}"]
        rec["accommodation_80_85"] = e["te_accom"]
        rec["admin_86"] = e["te_admin"]
        rec["ta_80_86"] = e["te_ta_total"]
        rec["net_accommodation_80_85"] = e["nce_accom"]
        rows.append(rec)
    return pd.DataFrame(rows)


def change_between(ta1: pd.DataFrame, q0: str, q1: str) -> pd.DataFrame:
    """Households in TA at two quarter ends, per area, with absolute and percentage change."""
    t = harmonise(ta1[ta1["quarter"].isin([q0, q1])], "code")
    cols = ["total", "with_children", *ACCOMMODATION_TYPES]
    a = t[t["quarter"] == q0].set_index("code")
    b = t[t["quarter"] == q1].set_index("code")
    out = pd.DataFrame({"name": b["name"].combine_first(a["name"]), "level": b["level"].combine_first(a["level"])})
    for c in cols:
        out[f"{c}_{q0}"] = a[c]
        out[f"{c}_{q1}"] = b[c]
        out[f"{c}_change"] = b[c] - a[c]
    out["total_pct_change"] = out["total_change"] / out[f"total_{q0}"]
    return out.reset_index()


# ---------------------------------------------------------------------------
# Diagnostics for the report's caveats (each a check a person can repeat)
# ---------------------------------------------------------------------------

def estimate_sensitivity(ta1: pd.DataFrame, year: str) -> pd.DataFrame:
    """For councils with exactly one snapshot missing: the average with the gap
    interpolated (as used) against the gap filled by carrying the previous count
    forward (the first count back, if the first is missing)."""
    qs = snapshot_quarters(year)
    t = harmonise(ta1[(ta1["quarter"].isin(qs)) & (ta1["level"] == "council")], "code")
    rows = []
    for code, g in t.groupby("code"):
        v = g.set_index("quarter").reindex(qs)["total"].to_numpy(dtype=float)
        gaps = np.flatnonzero(np.isnan(v))
        if len(gaps) != 1:
            continue
        carry = v.copy()
        i = int(gaps[0])
        carry[i] = carry[i - 1] if i > 0 else carry[1]
        used = trapezoid(fill_one_gap(v))
        alt = trapezoid(carry)
        rows.append({"code": code, "name": g["name"].iloc[-1], "used": used, "carry_forward": alt,
                     "relative_difference": abs(alt - used) / used if used else np.nan})
    return pd.DataFrame(rows)


def zero_ta_lines(table: pd.DataFrame, min_households: float = LEAD_MIN_HOUSEHOLDS) -> pd.DataFrame:
    """Councils with at least min_households on average and nothing on lines 80 to 86."""
    t = table[(table["avg_total"] >= min_households) & ~table["ro4_missing"]]
    return t[(t["te_accom"].fillna(0) == 0) & (t["te_admin"].fillna(0) == 0)]


def quarter_jumps(ta1: pd.DataFrame, min_avg: float = LEAD_MIN_HOUSEHOLDS, threshold: float = 0.4) -> pd.DataFrame:
    """Quarter-on-quarter changes in the total larger than threshold (either way) for councils
    averaging at least min_avg households over the quarters they report. 'dip' marks a change
    that reverses at the next quarter (back within 20% of the earlier level)."""
    t = harmonise(ta1[ta1["level"] == "council"], "code").sort_values(["code", "quarter"])
    out = []
    for code, g in t.groupby("code"):
        g = g.dropna(subset=["total"])
        if g["total"].mean() < min_avg:
            continue
        q, v = g["quarter"].tolist(), g["total"].tolist()
        for i in range(1, len(v)):
            if v[i - 1] <= 0:
                continue
            ch = v[i] / v[i - 1] - 1
            if abs(ch) <= threshold:
                continue
            dip = i + 1 < len(v) and v[i - 1] > 0 and abs(v[i + 1] / v[i - 1] - 1) <= 0.2
            back = i >= 2 and abs(v[i] / v[i - 2] - 1) <= 0.2   # the jump undoes the previous move
            out.append({"code": code, "name": g["name"].iloc[-1], "from_quarter": q[i - 1], "to_quarter": q[i],
                        "from": v[i - 1], "to": v[i], "change": ch, "one_quarter_dip": bool(dip or back)})
    return pd.DataFrame(out)


def recording_shifts(ro4: pd.DataFrame, min_gbp: float = 1e6) -> pd.DataFrame:
    """Housing authorities whose spend on lines 80 to 86 is zero in one year and at least
    min_gbp in another of the years held."""
    r = harmonise(ro4[ro4["housing_authority"]], "ons_code")
    lines = [f"{t}_te" for t in ACCOMMODATION_TYPES] + ["ta_admin_te"]
    r = r.assign(ta_80_86=r[lines].sum(axis=1, min_count=len(lines)))
    wide = r.pivot_table(index=["ons_code", "la_name"], columns="year", values="ta_80_86", aggfunc="first")
    wide = wide.reset_index().groupby("ons_code").first()
    years = [c for c in wide.columns if c not in ("la_name",)]
    vals = wide[years]
    hit = (vals.eq(0).any(axis=1)) & (vals.ge(min_gbp).any(axis=1))
    return wide[hit].reset_index()
