#!/usr/bin/env python3
"""Build the phase 0 market picture from the processed tables.

Reads data/processed/ta1_wide.csv and ro4_wide.csv (run build_from_extracts.py first)
and writes:

  the council tables, which name every council beside its ratio to its peers (kept out of
  anything shared, docs/adr/0001):
    data/processed/picture_councils_2024-25.csv, picture_councils_2025-26.csv
  and, with no council named:
    data/processed/picture_summary.json
    reports/phase0_picture.md
  private working copies, gitignored, with council names in the comparison lists:
    reports/private/phase0_picture_named.md
    data/private/picture_named.json, data/private/picture_councils_<year>_flags.csv

Every number in the reports is computed here from the processed tables, so a report cannot
drift from the data. Definitions are in tamarket/picture.py.

The tracked report and summary compare the councils the shared demo shows: councils with a data
check outstanding (tamarket/display.py, left_out_codes) are left out and counted for England
only, so that read beside the demo no count points at one council. The council tables and the
private named report keep every council that can be compared.

Contains public sector information licensed under the Open Government Licence v3.0.
"""

from __future__ import annotations

import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from tamarket import ATTRIBUTION  # noqa: E402
from tamarket import picture as P  # noqa: E402
from tamarket.display import left_out_codes  # noqa: E402
from tamarket.mhclg import ACCOMMODATION_TYPES  # noqa: E402

PROC = ROOT / "data" / "processed"
PRIVATE_DATA = ROOT / "data" / "private"
PRIVATE_REPORTS = ROOT / "reports" / "private"
YEARS = ("2024-25", "2025-26")
OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
LICENCE_LINE = f"{ATTRIBUTION} Licence: {OGL_URL}"

SOURCES = [
    ("MHCLG, Live tables on homelessness (detailed local authority tables, sheet TA1)",
     "https://www.gov.uk/government/statistical-data-sets/live-tables-on-homelessness"),
    ("MHCLG, Local authority revenue expenditure and financing England: 2023 to 2024 individual local authority data, outturn",
     "https://www.gov.uk/government/statistics/local-authority-revenue-expenditure-and-financing-england-2023-to-2024-individual-local-authority-data-outturn"),
    ("MHCLG, the same for 2024 to 2025",
     "https://www.gov.uk/government/statistics/local-authority-revenue-expenditure-and-financing-england-2024-to-2025-individual-local-authority-data-outturn"),
    ("MHCLG, the same for 2025 to 2026 (first release, 17 September 2026)",
     "https://www.gov.uk/government/statistics/local-authority-revenue-expenditure-and-financing-england-2025-to-2026-individual-local-authority-data-outturn"),
    ("MHCLG, 2025 to 2026 first release, section 3.4 and footnote 3 (changes within the TA sub-categories)",
     "https://www.gov.uk/government/statistics/local-authority-revenue-expenditure-and-financing-england-2025-to-2026-first-release/local-authority-revenue-expenditure-and-financing-england-2025-to-2026-first-release"),
    ("MHCLG, 2025 to 2026 technical notes (377 of 413 returns; estimates for missing returns; second release in December)",
     "https://www.gov.uk/government/statistics/local-authority-revenue-expenditure-and-financing-england-2025-to-2026-first-release/local-authority-revenue-expenditure-and-financing-england-2025-to-2026-technical-notes"),
    ("Shelter, press release of 18 September 2025",
     "https://england.shelter.org.uk/media/press_release/bill_for_homeless_accommodation_soars_by_25_hitting_28_bn_"),
    ("Open Government Licence v3.0", OGL_URL),
]

TRACKED_COLUMNS = [
    "code", "name", "peer_group", "year", "snapshots", "estimated", "avg_total", "avg_with_children",
    "avg_nightly_paid_self_contained", "avg_bed_and_breakfast", "avg_private_sector_leased",
    "te_accom", "nce_accom", "te_admin", "te_nightly_paid_self_contained", "te_bed_and_breakfast",
    "te_private_sector_leased", "gross_per_household", "net_per_household", "share_households_np_bb",
    "share_spend_np_bb", "share_with_children", "largest_line", "largest_line_share",
    "share_spend_on_types_without_households", "certification", "compared", "not_compared_because",
    "peer_median_gross", "ratio_to_peer_median",
]
FLAG_COLUMNS = ["code", "name", "year", "lead_high_cost", "check_recording"]


# ---------------------------------------------------------------- formatting (half up)

def _half_up(x: float, places: int = 0) -> Decimal:
    q = Decimal(1).scaleb(-places)
    return Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP)


def gbp(x: float, unit: str = "auto") -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    sign, x = ("-" if x < 0 else ""), abs(x)
    if unit == "bn" or (unit == "auto" and x >= 1e9):
        return f"{sign}£{_half_up(x / 1e9, 3):,}bn"
    if unit == "m" or (unit == "auto" and x >= 1e6):
        return f"{sign}£{_half_up(x / 1e6, 1):,}m"
    return f"{sign}£{_half_up(x):,}"


def per_hh(x: float) -> str:
    if x is None or np.isnan(x):
        return "n/a"
    sign = "-" if x < 0 else ""
    return f"{sign}£{int(_half_up(abs(x) / 10)) * 10:,}"


def pct(x: float, dp: int = 1) -> str:
    return "n/a" if x is None or np.isnan(x) else f"{_half_up(x * 100, dp)}%"


def num(x: float) -> str:
    return "n/a" if x is None or np.isnan(x) else f"{int(_half_up(x)):,}"


def md_table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


# ---------------------------------------------------------------- build

def compute(shown: bool = False) -> dict:
    """Everything the reports use. shown=True compares only the councils the shared demo shows,
    leaving out those with a data check outstanding (tamarket/display.py)."""
    ta1 = pd.read_csv(PROC / "ta1_wide.csv")
    ro4 = pd.read_csv(PROC / "ro4_wide.csv")
    tables = {y: P.council_table(ta1, ro4, y) for y in YEARS}
    left_out = left_out_codes(ta1, tables)
    if shown:
        tables = {y: P.council_table(ta1, ro4, y, left_out) for y in YEARS}
    eng_rows = {}
    for y in YEARS:
        sp = P.spend(ro4, y)
        eng = sp[sp["code"] == P.ENGLAND].iloc[0]
        h = sp[sp["housing_authority"]]
        other = sp[~sp["housing_authority"] & (sp["code"] != P.ENGLAND)]
        eng_rows[y] = {
            "england_minus_returns_80_85": float(eng["te_accom"] - h["te_accom"].sum() - other["te_accom"].sum()),
            "england_minus_returns_80_86": float(eng["te_ta_total"] - h["te_ta_total"].sum() - other["te_ta_total"].sum()),
            "housing_authorities_without_return": int(h["ro4_missing"].sum()),
        }
    return {
        "ta1": ta1, "ro4": ro4, "tables": tables, "left_out": left_out, "shown": shown,
        "national": {y: P.national_figures(ta1, ro4, y) for y in YEARS},
        "groups": {y: {g: {"inclusive": P.group_figures(tables[y], g).as_dict(),
                           "strict": P.group_figures(tables[y], g, strict=True).as_dict()}
                       for g in ("England", "London", "Rest of England")} for y in YEARS},
        "by_year": P.spend_by_year(ro4),
        "change": P.change_between(ta1, "2025-Q1", "2026-Q1"),
        "sensitivity": {y: P.estimate_sensitivity(ta1, y) for y in YEARS},
        "zero_lines": {y: P.zero_ta_lines(tables[y]) for y in YEARS},
        "jumps": P.quarter_jumps(ta1),
        "shifts": P.recording_shifts(ro4),
        "england_rows": eng_rows,
    }


CLASS_LABEL = {"SD": "district council", "UA": "unitary council", "MD": "metropolitan council",
               "LB": "London borough"}


def about(x: float, step: int) -> float:
    """Round to a step for 'about' figures in unnamed examples (halves up)."""
    return float(int(_half_up(x / step)) * step)


def worked_example(t: pd.DataFrame) -> dict | None:
    """The lead furthest above its peers whose largest line has under 50 households,
    described with rounded figures so the text does not single the council out."""
    leads = t[t["lead_high_cost"] & t["largest_line"].notna()].copy()
    if leads.empty:
        return None
    leads["line_households"] = [r[f"avg_{r['largest_line']}"] for _, r in leads.iterrows()]
    leads = leads[leads["line_households"] < 50]
    if leads.empty:
        return None
    r = leads.sort_values("ratio_to_peer_median", ascending=False).iloc[0]
    line_spend = r[f"te_{r['largest_line']}"]
    return {"kind": CLASS_LABEL.get(r["class"], "council"), "households": about(r["avg_total"], 50),
            "share": round(r["largest_line_share"] * 20) / 20, "line": r["largest_line"],
            "line_households": about(r["line_households"], 10),
            "per_household": about(line_spend / r["line_households"], 10_000)}


def lead_patterns(t: pd.DataFrame) -> dict:
    leads = t[t["lead_high_cost"]]
    hh_line = []
    for _, r in leads.iterrows():
        line = r["largest_line"]
        hh_line.append(r.get(f"avg_{line}", np.nan) if line else np.nan)
    hh_line = pd.Series(hh_line, index=leads.index, dtype=float)
    near = leads[(leads["ratio_to_peer_median"] < P.PEER_MULTIPLE * 1.05) |
                 (leads["avg_total"] < P.LEAD_MIN_HOUSEHOLDS + 5)]
    return {
        "leads": int(len(leads)),
        "largest_line_few_households": int((hh_line < 10).sum()),
        "largest_line_under_50": int((hh_line < 50).sum()),
        "near_threshold": int(len(near)),
        "checks": int(t["check_recording"].sum()),
    }


def main() -> int:
    c = compute()
    cs = compute(shown=True)
    tables = c["tables"]
    PRIVATE_DATA.mkdir(parents=True, exist_ok=True)
    PRIVATE_REPORTS.mkdir(parents=True, exist_ok=True)
    for y, t in tables.items():
        t[TRACKED_COLUMNS].to_csv(PROC / f"picture_councils_{y}.csv", index=False)
        t[FLAG_COLUMNS].to_csv(PRIVATE_DATA / f"picture_councils_{y}_flags.csv", index=False)

    e = c["change"][c["change"]["code"] == P.ENGLAND].iloc[0]
    lon = c["change"][c["change"]["code"] == P.LONDON].iloc[0]
    summary = {
        "attribution": LICENCE_LINE,
        "national": c["national"],
        "spend_by_year": c["by_year"].to_dict("records"),
        "households_change_2025Q1_2026Q1": {
            "england": {k: float(e[k]) for k in e.index if k not in ("code", "name", "level")},
            "london": {k: float(lon[k]) for k in lon.index if k not in ("code", "name", "level")},
        },
        "groups": cs["groups"],
        "comparison_counts": {y: lead_patterns(cs["tables"][y]) for y in YEARS},
        "left_out_for_a_data_check_england": {y: int((cs["tables"][y]["not_compared_because"] == P.LEFT_OUT_REASON).sum()) for y in YEARS},
        "england_row_against_returns": c["england_rows"],
    }
    (PROC / "picture_summary.json").write_text(json.dumps(summary, indent=2, default=float))
    named = {
        "note": "Private working file: council names in comparison lists. Not for publication.",
        "leads": {y: tables[y].loc[tables[y]["lead_high_cost"], ["code", "name", "avg_total", "gross_per_household",
                                                                 "peer_median_gross", "ratio_to_peer_median"]].to_dict("records")
                  for y in YEARS},
        "recording_checks": {y: tables[y].loc[tables[y]["check_recording"], ["code", "name", "avg_total",
                                                                             "gross_per_household"]].to_dict("records")
                             for y in YEARS},
        "quarter_jumps": c["jumps"].to_dict("records"),
        "recording_shifts": c["shifts"].to_dict("records"),
    }
    (PRIVATE_DATA / "picture_named.json").write_text(json.dumps(named, indent=2, default=float))

    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "phase0_picture.md").write_text(report(cs, named=False))
    (PRIVATE_REPORTS / "phase0_picture_named.md").write_text(report(c, named=True))
    print("wrote reports/phase0_picture.md, data/processed/picture_*; private copies in reports/private and data/private")
    print(LICENCE_LINE)
    return 0


# ---------------------------------------------------------------- report

def report(c: dict, named: bool) -> str:
    tables, national, groups, by = c["tables"], c["national"], c["groups"], c["by_year"].set_index("year")
    n24, n25 = national["2024-25"], national["2025-26"]
    t24, t25 = tables["2024-25"], tables["2025-26"]
    g24 = groups["2024-25"]
    e = c["change"][c["change"]["code"] == P.ENGLAND].iloc[0]
    lon = c["change"][c["change"]["code"] == P.LONDON].iloc[0]
    rise_2425 = by.loc["2024-25", "ta_80_86"] / by.loc["2023-24", "ta_80_86"] - 1
    rise_2526 = by.loc["2025-26", "ta_80_86"] / by.loc["2024-25", "ta_80_86"] - 1
    rise_np = by.loc["2024-25", "nightly_paid_self_contained"] / by.loc["2023-24", "nightly_paid_self_contained"] - 1

    L = []
    w = L.append
    title = "Temporary accommodation market picture, England: phase 0"
    w(f"# {title}" + (" (private working copy, councils named)" if named else ""))
    w("")
    w(LICENCE_LINE)
    w("")
    if named:
        w("**Private working copy.** This version names councils in the comparison lists. It is gitignored and "
          "not for publication; the tracked report gives counts and patterns instead. A council far from its "
          "peers is a question for a person to look into, not a finding, and no council has been asked about "
          "its figures.")
        w("")
    w("Built only from published aggregate statistics: households in temporary accommodation (TA) at each "
      "quarter end (MHCLG statutory homelessness detailed local authority tables, sheet TA1) and council TA "
      "spend (MHCLG revenue outturn, form RO4, lines 80 to 86). No household-level data. Nothing here assesses "
      "any council.")
    w("")
    w("Generated by `scripts/build_picture.py` from `data/processed/`; every number below is computed there, "
      "and definitions are in `tamarket/picture.py`. Sources are listed at the end.")
    w("")

    # ------------------------------------------------------------ problems first
    w("## What could make these numbers wrong")
    w("")
    miss24 = t24[t24["snapshots"] < P.MIN_SNAPSHOTS]
    lon24 = t24[t24["london"]]
    lon_missing = int((lon24["snapshots"] < P.MIN_SNAPSHOTS).sum())
    lon_small = int(((lon24["snapshots"] >= P.MIN_SNAPSHOTS) & (lon24["avg_total"] < P.MIN_HOUSEHOLDS)).sum())
    none24 = t24[t24["snapshots"] == 0]
    none_lon = int(none24["london"].sum())
    none_text = (f"{len(none24)} London boroughs have none at all" if none_lon == len(none24)
                 else f"{len(none24)} councils have none at all, {none_lon} of them London boroughs")
    small24 = int(((t24["snapshots"] >= P.MIN_SNAPSHOTS) & (t24["avg_total"] < P.MIN_HOUSEHOLDS)).sum())
    left24 = int((t24["not_compared_because"] == P.LEFT_OUT_REASON).sum())
    if named:
        london = (f"The London comparison covers {g24['London']['inclusive']['councils_compared']} of the 33 London "
                  f"councils (32 boroughs and the City of London): {lon_missing} lack counts and {lon_small} has fewer "
                  f"than {P.MIN_HOUSEHOLDS} households on average.")
    else:
        # The reasons are given for England only, so that no small London count points at one council.
        london = (f"The London comparison covers {g24['London']['inclusive']['councils_compared']} of the 33 London "
                  f"councils (32 boroughs and the City). Across England, {len(miss24)} councils lack "
                  f"counts, {small24} have fewer than {P.MIN_HOUSEHOLDS} households on average and {left24} are left "
                  "out until a person checks their figures (points 2 and 7).")
    w(f"1. **Councils missing from the household counts.** In 2024-25, {len(miss24)} councils lack two or more "
      f"of the five quarter-end counts; {none_text}. Together they hold "
      f"{gbp(miss24['te_accom'].sum())} of the {gbp(t24['te_accom'].sum())} councils reported on accommodation "
      f"lines 80 to 85, and no cost per household can be worked out for them. {london} [Certain]")
    z24, z25 = c["zero_lines"]["2024-25"], c["zero_lines"]["2025-26"]
    big25 = z25.sort_values("avg_total", ascending=False).iloc[0] if len(z25) else None
    w(f"2. **Spend that may be booked outside the TA lines.** {len(z24)} councils in 2024-25 and {len(z25)} in "
      f"2025-26 house at least {P.LEAD_MIN_HOUSEHOLDS} households in TA on average but report nothing on any of "
      "lines 80 to 86" + (f"; in 2025-26 they include a London borough with about {num(about(big25['avg_total'], 100))} "
                          "households" if named and big25 is not None and big25['london'] else "") +
      ". They are left out of comparisons, and very low figures are shown as recording checks, not as low "
      "cost. [Certain that the lines are empty; Likely that the spend sits elsewhere]")
    w("3. **The spend and the count may cover different households.** RO4 spend can include placements that "
      "TA1 does not count (TA1 counts households placed under the statutory homelessness duties), so some high "
      "spend per household may reflect a wider group of households, not a higher price. [Likely]")
    er = c["england_rows"]["2025-26"]
    w(f"4. **2025-26 is a first release.** MHCLG's first release covers 377 of 413 authorities and estimates the "
      f"missing returns in its England totals; here {er['housing_authorities_without_return']} of the 296 housing "
      f"authorities have no return, and the England row exceeds the sum of returns by {gbp(er['england_minus_returns_80_85'], 'm')} "
      f"on lines 80 to 85 ({gbp(er['england_minus_returns_80_86'], 'm')} on 80 to 86). MHCLG also reports large "
      "changes within the TA sub-categories, which it puts down to reporting changes by three London boroughs. "
      "[Certain, from MHCLG's release and technical notes] National 2025-26 spend and the 2025-26 by-type figures "
      "will probably move at the second release, which MHCLG schedules for December. [Likely]")
    mis_n = {y: int((tables[y][tables[y]["compared"]]["share_spend_on_types_without_households"] > 0.25).sum())
             for y in YEARS}
    w("5. **By-type figures depend on how councils classify spend.** The 2025-26 national gross spend per "
      f"household in B&B ({per_hh(n25['by_type']['bed_and_breakfast']['gross_per_household'])}) against "
      f"{per_hh(n24['by_type']['bed_and_breakfast']['gross_per_household'])} a year earlier, and in nightly-paid "
      f"accommodation ({per_hh(n25['by_type']['nightly_paid_self_contained']['gross_per_household'])} against "
      f"{per_hh(n24['by_type']['nightly_paid_self_contained']['gross_per_household'])}), point to reclassification "
      f"rather than price change. At council level, {mis_n['2024-25']} compared councils in 2024-25 and "
      f"{mis_n['2025-26']} in 2025-26 put more than a quarter of their accommodation spend on types where they "
      "report fewer than one household of that type on average. Totals per household are unaffected; by-type "
      "comparisons between councils are not safe, so use 2024-25 for national by-type figures. [Certain on the "
      "counts; Likely on the cause]")
    s24, s25 = c["sensitivity"]["2024-25"], c["sensitivity"]["2025-26"]
    est24 = int((t24["compared"] & t24["estimated"]).sum())
    est25 = int((t25["compared"] & t25["estimated"]).sum())
    w("6. **The yearly average is an estimate.** Households in TA are counted on four days a year, and the "
      "average assumes a straight line between counts. Where one of five counts is missing it is interpolated, "
      f"and the council is marked as estimated ({est24} compared councils in 2024-25, {est25} in 2025-26). Over "
      f"every council with one count missing, compared or not ({len(s24)} in 2024-25, {len(s25)} in 2025-26), "
      "filling the gap by carrying the previous count forward instead moves the average by a median of "
      f"{pct(s24['relative_difference'].median())} (largest {pct(s24['relative_difference'].max())}) in 2024-25 and "
      f"{pct(s25['relative_difference'].median())} (largest {pct(s25['relative_difference'].max())}) in 2025-26. "
      "[Certain on the method and these figures; Likely that the effect on group figures is small]")
    j = c["jumps"]
    w(f"7. **Some counts jump between quarters.** {len(j)} quarter-on-quarter changes of more than 40% occur in "
      f"councils averaging at least {P.LEAD_MIN_HOUSEHOLDS} households; {int(j['one_quarter_dip'].sum())} of them are "
      "one-quarter dips or their recovery. A dip lowers that council's average for the year. These may be "
      "reporting slips or real moves; a person needs to check them before any council's figure is used. [Certain "
      "on the counts]")
    w("8. **England and regional counts are MHCLG estimates.** They are weighted for non-response and rounded to "
      "the nearest 10; council counts are as submitted. [Certain]")
    w("9. **All money is cash (nominal), not adjusted for inflation.** [Certain]")
    w("")

    # ------------------------------------------------------------ headline
    w("## Headline (MHCLG England figures)")
    w("")
    w(md_table(
        ["Year", "Average households in TA", "Accommodation spend, gross (lines 80-85)",
         "Net (after income such as housing benefit)", "Gross per household-year", "Net per household-year",
         "TA spend incl. admin (80-86)"],
        [[y, num(national[y]["avg_households_england"]), gbp(national[y]["te_accom_england_row"]),
          gbp(national[y]["nce_accom_england_row"]), per_hh(national[y]["gross_per_household_england"]),
          per_hh(national[y]["net_per_household_england"]), gbp(national[y]["te_ta_total_england_row"])]
         for y in YEARS]))
    w("")
    w(f"- Spend on lines 80 to 86 rose {pct(rise_2425)} from 2023-24 to 2024-25, with nightly-paid self-contained "
      f"accommodation up {pct(rise_np)}. The first release for 2025-26 shows a further {pct(rise_2526)}, which is "
      "not yet comparable (point 4). [Certain for the published rows]")
    w(f"- Households in TA, 31 March 2025 to 31 March 2026: {num(e['total_2025-Q1'])} to {num(e['total_2026-Q1'])} "
      f"({pct(e['total_pct_change'])}). B&B {num(e['bed_and_breakfast_2025-Q1'])} to "
      f"{num(e['bed_and_breakfast_2026-Q1'])}; nightly-paid self-contained "
      f"{num(e['nightly_paid_self_contained_2025-Q1'])} to {num(e['nightly_paid_self_contained_2026-Q1'])}. London "
      f"{num(lon['total_2025-Q1'])} to {num(lon['total_2026-Q1'])}. [Certain, as published]")
    w(f"- Shelter's press release (18 September 2025), based on MHCLG's first release, gave £2.842bn including "
      f"administration, a 25% rise; the rows of MHCLG's latest release give lines 80 to 86 as "
      f"{gbp(by.loc['2024-25', 'ta_80_86'])}, a rise of {pct(rise_2425)} worked out here from those rows. [Certain "
      "for each figure as published or worked out; Likely that they cover the same lines and that the gap is "
      "MHCLG's later revisions]")
    w("")

    # ------------------------------------------------------------ by year
    w("## Spend by year, England (lines 80 to 86; gross unless marked net)")
    w("")
    hdr = ["Line"] + list(by.index)
    rows = [[P.TYPE_LABELS[t]] + [gbp(by.loc[y, t], "m") for y in by.index] for t in ACCOMMODATION_TYPES]
    rows.append(["Accommodation, lines 80 to 85"] + [gbp(by.loc[y, "accommodation_80_85"], "m") for y in by.index])
    rows.append(["TA administration, line 86"] + [gbp(by.loc[y, "admin_86"], "m") for y in by.index])
    rows.append(["**All TA, lines 80 to 86**"] + [f"**{gbp(by.loc[y, 'ta_80_86'], 'm')}**" for y in by.index])
    rows.append(["Net, lines 80 to 85"] + [gbp(by.loc[y, "net_accommodation_80_85"], "m") for y in by.index])
    w(md_table(hdr, rows))
    w("")
    w("2023-24 and 2024-25 are later releases (all or nearly all councils); 2025-26 is the first release.")
    w("")

    # ------------------------------------------------------------ by type
    w("## Spend per household by type of accommodation, England, 2024-25")
    w("")
    rows = []
    for t in ACCOMMODATION_TYPES:
        b = n24["by_type"][t]
        rows.append([P.TYPE_LABELS[t], num(b["avg_households"]), gbp(b["te"], "m"), per_hh(b["gross_per_household"]),
                     per_hh(b["net_per_household"])])
    w(md_table(["Type", "Average households", "Gross spend", "Gross per household-year", "Net per household-year"], rows))
    w("")
    w("These are average outturns per household-year, not prices: each type houses different households in "
      "different places, and councils classify some spend differently (point 5). Council or housing association "
      "stock is mostly costed outside these lines. [Likely]")
    w("")

    # ------------------------------------------------------------ groups
    w("## London and the rest of England (matched councils)")
    w("")
    w("Councils with at least four of the five quarter-end counts, a positive spend on lines 80 to 85 and at least "
      f"{P.MIN_HOUSEHOLDS} households on average, less the councils left out until a person checks their figures "
      "(points 1, 2 and 7). Spend and households are summed over the matched set.")
    w("")
    rows = []
    for y in YEARS:
        for g in ("London", "Rest of England", "England"):
            f, s = groups[y][g]["inclusive"], groups[y][g]["strict"]
            rows.append([y, g, f"{f['councils_compared']} of {f['councils']}",
                         pct(f["spend_te_accom_compared"] / f["spend_te_accom_all"], 0), num(f["avg_households_compared"]),
                         per_hh(f["gross_per_household"]), per_hh(f["net_per_household"]),
                         pct(f["share_households_np_bb"], 0), pct(f["share_spend_np_bb"], 0),
                         per_hh(s["gross_per_household"]), str(s["councils_compared"])])
    w(md_table(["Year", "Group", "Councils matched", "Share of group spend", "Average households", "Gross per household",
                "Net per household", "Households in nightly-paid or B&B", "Spend on nightly-paid or B&B",
                "Gross, five counts only", "Councils, five counts only"], rows))
    w("")
    w("The last two columns drop councils with an estimated count. That changes the set as well as the method, "
      "so the two are not a like-for-like test; together with point 6 they suggest the estimates do not drive the "
      "group figures. [Likely]")
    w("")

    # ------------------------------------------------------------ distribution
    w("## How councils compare with their peers")
    w("")
    rows = []
    for y in YEARS:
        r = tables[y][tables[y]["compared"]]
        for g, s in r.groupby("peer_group"):
            q = s["gross_per_household"].quantile([0.25, 0.5, 0.75])
            qn = s["net_per_household"].quantile([0.25, 0.5, 0.75])
            rows.append([y, g, len(s), per_hh(q[0.25]), per_hh(q[0.5]), per_hh(q[0.75]),
                         per_hh(qn[0.25]), per_hh(qn[0.5]), per_hh(qn[0.75])])
    w(md_table(["Year", "Peer group", "Councils", "Gross, lower quartile", "Gross, median", "Gross, upper quartile",
                "Net, lower quartile", "Net, median", "Net, upper quartile"], rows))
    w("")
    w(f"### Far above the peer median (more than {P.PEER_MULTIPLE:g} times, at least {P.LEAD_MIN_HOUSEHOLDS} households)")
    w("")
    w("Each is a question for a person to ask, not a finding: does the spend cover households outside the TA "
      "count, is spend classified differently, or are prices higher? No council has been asked about its figures.")
    w("")
    rows = []
    for y in YEARS:
        p = lead_patterns(tables[y])
        rows.append([y, p["leads"], p["largest_line_few_households"], p["largest_line_under_50"], p["near_threshold"]])
    w(md_table(["Year", "Councils far above the median", "Of which most spend is on a type with under 10 households",
                "Of which most spend is on a type with under 50 households",
                "Within 5% of the threshold, or within 5 households of 100"], rows))
    w("")
    ex = worked_example(tables["2024-25"]) if named else None
    if not named:
        # A worked example with a council's type, size and shares fits one council in MHCLG's tables
        # (fact-check of 22 October 2026), so the shared report gives the pattern only.
        w("Where most of a council's spend sits on a type that houses few of its households, the spend per "
          "household on that line can look implausibly high. That points to how the spend is recorded rather than "
          "to what is paid per placement [Likely]; the private copy gives a worked example.")
        w("")
    if ex:
        w(f"Worked example (2024-25, rounded, unnamed): one {ex['kind']} housing about {num(ex['households'])} "
          f"households in TA recorded {pct(ex['share'], 0)} of its accommodation spend on the "
          f"{P.TYPE_LABELS[ex['line']].lower()} line, where it housed about {num(ex['line_households'])} households: "
          f"about {per_hh(ex['per_household'])} per household a year on that line. That points to how the spend is "
          "recorded rather than to what is paid per placement. [Likely]")
        w("")
    if named:
        rows = []
        for y in YEARS:
            t = tables[y]
            for _, r in t[t["lead_high_cost"]].sort_values("name").iterrows():
                line = r["largest_line"]
                hh_line = r.get(f"avg_{line}", np.nan) if line else np.nan
                rows.append([y, r["name"], r["peer_group"], num(r["avg_total"]), gbp(r["te_accom"], "m"),
                             per_hh(r["gross_per_household"]), per_hh(r["peer_median_gross"]),
                             f"{_half_up(r['ratio_to_peer_median'], 2)}",
                             f"{P.TYPE_LABELS.get(line, line)} {pct(r['largest_line_share'], 0)} (about {num(hh_line)} households)",
                             "yes" if r["estimated"] else ""])
        w("Named list (private; alphabetical within each year):")
        w("")
        w(md_table(["Year", "Council", "Peer group", "Average households", "Gross spend", "Gross per household",
                    "Peer median", "Ratio to median", "Largest line, share of spend", "Count estimated"], rows))
        w("")
    w(f"### Very low figures (under {P.LOW_RATIO:g} of the peer median)")
    w("")
    w(f"{int(t24['check_recording'].sum())} councils in 2024-25 and {int(t25['check_recording'].sum())} in 2025-26. "
      "A figure this low can reflect spend recorded outside the TA lines, a different mix of placements or lower "
      "costs; which applies to any council is not known. [Guessing]")
    w("")
    if named:
        for y in YEARS:
            t = tables[y]
            w(f"- {y}: {', '.join(t.loc[t['check_recording']].sort_values('name')['name'])}.")
        w("")

    # ------------------------------------------------------------ coverage
    w("## Coverage: which councils are not compared, and why")
    w("")
    rows = []
    for y in YEARS:
        t = tables[y]
        reasons = (t.loc[~t["compared"], "not_compared_because"].str.split("; ").explode()
                   .str.replace(r"^households: \d of 5", "households: two or more of 5", regex=True)
                   .value_counts())
        for reason, n in reasons.items():
            rows.append([y, reason, n])
    w(md_table(["Year", "Reason (a council can have more than one)", "Councils"], rows))
    w("")
    for y in YEARS:
        t = tables[y]
        nc = t[~t["compared"]]
        w(f"- {y}: councils not compared hold {gbp(nc['te_accom'].sum())} of {gbp(t['te_accom'].sum())} accommodation "
          f"spend ({pct(nc['te_accom'].sum() / t['te_accom'].sum(), 0)}).")
    w("")
    if named:
        for y in YEARS:
            t = tables[y]
            big = t[~t["compared"]].sort_values("te_accom", ascending=False).head(8)
            w(f"- Largest accommodation spend among councils not compared, {y}: "
              + "; ".join(f"{r['name']} {gbp(r['te_accom'], 'm')} ({r['not_compared_because']})" for _, r in big.iterrows()) + ".")
        w("")
        jj = c["jumps"].sort_values("change", key=abs, ascending=False)
        w("Quarter-on-quarter changes over 40% (councils averaging 100 or more households):")
        w("")
        w(md_table(["Council", "From", "To", "Change", "One-quarter dip or recovery"],
                   [[r["name"], f"{r['from_quarter']} {num(r['from'])}", f"{r['to_quarter']} {num(r['to'])}",
                     pct(r["change"]), "yes" if r["one_quarter_dip"] else ""] for _, r in jj.iterrows()]))
        w("")
        sh = c["shifts"]
        w("Councils whose spend on lines 80 to 86 is zero in one year and at least £1m in another:")
        w("")
        yrs = [col for col in sh.columns if str(col)[:2] == "20"]
        w(md_table(["Council"] + yrs, [[r["la_name"]] + [gbp(r[y], "m") for y in yrs] for _, r in sh.iterrows()]))
        w("")

    # ------------------------------------------------------------ savings inputs
    w("## Inputs for the savings model (set by the user, never presented as fact)")
    w("")
    npg, psl = n24["by_type"]["nightly_paid_self_contained"], n24["by_type"]["private_sector_leased"]
    w(f"Observed national averages, 2024-25: net spend per household-year {per_hh(npg['net_per_household'])} in "
      f"nightly-paid self-contained accommodation and {per_hh(psl['net_per_household'])} in private sector leased "
      f"accommodation (gross {per_hh(npg['gross_per_household'])} and {per_hh(psl['gross_per_household'])}). The "
      "difference between them is not a saving: the households, places and lease costs differ, and leasing has its "
      "own set-up and void costs. The model takes the gap per household-year and the number of households as inputs "
      "and only does the arithmetic. Illustration only: 100 households times a £1,000 gap is £100,000 a year. "
      "[Certain on the arithmetic; the gap is the user's]")
    w("")

    # ------------------------------------------------------------ method and sources
    w("## Method and files")
    w("")
    w("- Raw extracts: `data/raw/browser/*.txt`, each checked against `data/raw/browser/MANIFEST.csv` (its own "
      "SHA-256, and the source file's name, size and SHA-256), its row count and its column sums. Ingest log: "
      "`data/ingest_log.jsonl`.")
    w("- Processed: `data/processed/ta1_wide.csv`, `ta_households.csv`, `ro4_wide.csv`, `ta_spend.csv`, "
      "`picture_councils_<year>.csv`, `picture_summary.json`.")
    w("- Rebuild: `python scripts/build_from_extracts.py && python scripts/build_picture.py`.")
    if named:
        w("- Barnsley and Sheffield changed codes on 1 April 2025 (E08000016 to E08000038, E08000019 to E08000039); "
          "both years use the new codes.")
    else:
        w("- Two metropolitan councils changed codes on 1 April 2025; both years use the new codes "
          "(`tamarket/picture.py`, RECODES).")
    w("- RO4 classes kept: shire districts, unitaries, metropolitan districts, London boroughs. County councils "
      "and other authorities with small TA lines are in the England row but not in council tables.")
    w("- Rounding: money per household to the nearest £10, £m to one decimal place, £bn to three, halves rounded up.")
    w("")
    w("## Sources")
    w("")
    for label, url in SOURCES:
        w(f"- [{label}]({url})")
    w("")
    w(LICENCE_LINE)
    w("")
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
