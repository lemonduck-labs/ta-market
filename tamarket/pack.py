"""A private pack for one council: its own figures against unnamed peers.

council_pack(code, year) returns a dict for one council that names that council only. Its
peers are never named or coded: they appear only as a count, a band and a median. The
peers are the councils shown on the shared demo (tamarket.display.shown_set: compared, with
no data check outstanding) in the same peer group (London, or the rest of England), with the
council itself left out, so the band and median are over the other councils.

The pack holds:
- households (average over the financial year from five quarter-end counts) and gross and
  net accommodation spend per household-year (RO4 lines 80 to 85);
- the ratio to the median of the others, and the share of the others with a lower figure;
- the trend over the years held: every quarter-end count, and spend per household-year in
  each year with five counts;
- the mix of households and spend by type;
- questions, each with its reasons first and a confidence tag, for councils near the median
  and far from it;
- a data check, when the council is left out of the dots on the shared chart: a check to
  make, never a finding;
- release notes, caveats and the Open Government Licence line.

Packs are private. scripts/build_packs.py writes them to data/private/packs/ (gitignored),
for a one-council private page only, never a shared page. None is shared until the owner
switches naming on for that copy (docs/adr/0001), a person has done that council's data
checks, and the fact-checker and guardrails reviewer pass it (docs/decision_log.md).

A council far from the others is a question for a person to look into, never a finding.

Contains public sector information licensed under the Open Government Licence v3.0.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from tamarket import picture as P
from tamarket.display import (CLASS_LABEL, LINE_MIN_HOUSEHOLDS, PLACE, about_households, half_up, left_out_codes,
                              line_checks, pounds, shown_set, spend_without_households, whole_percent)
from tamarket.mhclg import ACCOMMODATION_TYPES

ROOT = Path(__file__).resolve().parent.parent
PACK_VERSION = "1"
YEAR = "2024-25"                     # the year the shared demo compares councils in
YEARS = ("2024-25", "2025-26")       # years with five quarter-end counts held
FIRST_RELEASE = "2025-26"            # RO4 first release (second release due December 2026)
ATTRIBUTION = ("Contains public sector information licensed under the Open Government Licence v3.0. "
               "Licence: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/")
QUARTER_END = {"Q1": "31 March", "Q2": "30 June", "Q3": "30 September", "Q4": "31 December"}

SHARING = ("Private to this council. Built in data/private/packs (gitignored) for a one-council private page, "
           "never a shared page. It names this council only; other councils appear only as a count, a band and "
           "a median, never by name or code.")
RELEASE_GATE = [
    "The owner switches naming on for this copy (docs/adr/0001).",
    "A person has done this council's data checks, if any are listed under data_check.",
    "The fact-checker and the guardrails reviewer pass it.",
]
RELEASE_NOTES = [
    "Households: MHCLG statutory homelessness detailed local authority tables, sheet TA1, quarter ends from "
    "31 March 2024 to 31 March 2026 [Certain]. The 31 March 2026 count is expected to be revised with the April "
    "to June 2026 release, announced provisionally for 29 October 2026 [Likely for the revision; Certain for the "
    "date as announced].",
    "Spend: MHCLG revenue outturn RO4, 2023-24 and 2024-25 (both updated 11 June 2026) and 2025-26, a first "
    "release of 17 September 2026 covering 377 of 413 authorities, with the second release due in December 2026 "
    "[Certain, as MHCLG states it]. 2025-26 figures will probably move [Likely].",
]
CAVEATS = [
    "Gross (net) spend per household-year is accommodation spend on RO4 lines 80 to 85 divided by the average "
    "households in TA over the year. It is an average outturn per household-year, not a price [Certain].",
    "RO4 spend can include placements that the quarter-end counts do not capture, such as short stays between "
    "counts [Likely].",
    "Net spend is gross spend less income such as rents and housing benefit [Certain].",
    "The others are the councils shown on the shared chart in the same peer group, this council left out: compared "
    "(at least 4 of 5 counts, positive spend, at least 50 households on average) and with no data check "
    "outstanding [Certain on the rule].",
    "No other council is named or coded in this pack [Certain].",
    "A council far from the others is a question for a person to look into, never a finding [Certain on the rule].",
]


@dataclass
class PackInputs:
    """Everything a pack is built from, loaded once for many packs."""
    ta1: pd.DataFrame
    ro4: pd.DataFrame
    tables: dict[str, pd.DataFrame]
    left_out: set[str]
    jumps: pd.DataFrame
    shown: dict[str, pd.DataFrame] | None = None     # shown_set per year, filled in from_frames
    spend: dict[str, pd.DataFrame] | None = None     # P.spend per RO4 year
    ta1_harmonised: pd.DataFrame | None = None

    @classmethod
    def load(cls, root: Path = ROOT) -> "PackInputs":
        ta1 = pd.read_csv(root / "data" / "processed" / "ta1_wide.csv")
        ro4 = pd.read_csv(root / "data" / "processed" / "ro4_wide.csv")
        return cls.from_frames(ta1, ro4)

    @classmethod
    def from_frames(cls, ta1: pd.DataFrame, ro4: pd.DataFrame) -> "PackInputs":
        tables = {y: P.council_table(ta1, ro4, y) for y in YEARS}
        left_out = left_out_codes(ta1, tables)
        return cls(ta1=ta1, ro4=ro4, tables=tables, left_out=left_out, jumps=P.quarter_jumps(ta1),
                   shown={y: shown_set(t, left_out) for y, t in tables.items()},
                   spend={y: P.spend(ro4, y) for y in sorted(ro4.year.unique())},
                   ta1_harmonised=P.harmonise(ta1, "code"))

    def codes(self, year: str = YEAR) -> list[str]:
        return sorted(self.tables[year].code)


def _quarter_label(q: str) -> str:
    year, part = q.split("-")
    return f"{QUARTER_END[part]} {year}"


def _position(own: float, quartiles: list[float], ratio: float) -> str:
    if ratio > P.PEER_MULTIPLE:
        return "more than twice the median of the others"
    if ratio < P.LOW_RATIO:
        return "under a quarter of the median of the others"
    if own > quartiles[2]:
        return "above the upper quartile of the others"
    if own < quartiles[0]:
        return "below the lower quartile of the others"
    return "within the middle half of the others"


def _comparison(r, s: pd.DataFrame, year: str, left_out: set[str]) -> dict:
    out = {"year": year, "peer_group": r.peer_group,
           "households_average": int(half_up(float(r.avg_total), 1)) if pd.notna(r.avg_total) else None,
           "households_estimated": bool(r.estimated),
           "gross_per_household": pounds(r.gross_per_household) if pd.notna(r.gross_per_household) and np.isfinite(r.gross_per_household) else None,
           "net_per_household": pounds(r.net_per_household) if pd.notna(r.net_per_household) and np.isfinite(r.net_per_household) else None}
    if not r.compared:
        out.update(status="not compared", not_compared_because=r.not_compared_because, others=None,
                   ratio_to_median_of_others=None, others_lower=None, share_of_others_lower=None, position=None)
        return out
    others = s[(s.peer_group == r.peer_group) & (s.code != r.code)]
    q = [half_up(float(others.gross_per_household.quantile(p)), 10) for p in (0.25, 0.5, 0.75)]
    median = float(others.gross_per_household.median())
    ratio = float(r.gross_per_household) / median
    lower = int((others.gross_per_household < r.gross_per_household).sum())
    out.update(
        status="provisional: data check outstanding" if r.code in left_out else "compared",
        not_compared_because="",
        others={"councils": int(len(others)), "lower_quartile_gross": q[0], "median_gross": q[1],
                "upper_quartile_gross": q[2],
                "rule": "Councils shown on the shared chart in the same peer group, this council left out."},
        ratio_to_median_of_others=half_up(ratio, 0.01),
        others_lower=lower, share_of_others_lower=half_up(lower / len(others), 0.01),
        position=_position(out["gross_per_household"], q, ratio))
    return out


def _trend(code: str, inputs: PackInputs) -> dict:
    t = inputs.ta1_harmonised
    own = t[t.code == code].groupby("quarter").total.first()
    counts = [{"quarter": q, "quarter_end": _quarter_label(q),
               "households": None if pd.isna(own.get(q)) else int(own.get(q))}
              for q in sorted(t.quarter.unique())]
    by_year = []
    for y in YEARS:
        row = inputs.tables[y]
        row = row[row.code == code]
        if row.empty:
            continue
        r = row.iloc[0]
        by_year.append({
            "year": y, "first_release": y == FIRST_RELEASE,
            "households_average": int(half_up(float(r.avg_total), 1)) if pd.notna(r.avg_total) else None,
            "households_estimated": bool(r.estimated),
            "gross_accommodation_spend": pounds(r.te_accom) if pd.notna(r.te_accom) else None,
            "net_accommodation_spend": pounds(r.nce_accom) if pd.notna(r.nce_accom) else None,
            "gross_per_household": pounds(r.gross_per_household) if pd.notna(r.gross_per_household) and np.isfinite(r.gross_per_household) else None,
            "net_per_household": pounds(r.net_per_household) if pd.notna(r.net_per_household) and np.isfinite(r.net_per_household) else None})
    spend = []
    for y, sp in inputs.spend.items():
        sp = sp[(sp.code == code) & sp.housing_authority]
        if sp.empty:
            continue
        e = sp.iloc[0]
        spend.append({"year": y, "first_release": y == FIRST_RELEASE,
                      "gross_lines_80_85": pounds(e.te_accom) if pd.notna(e.te_accom) else None,
                      "gross_admin_line_86": pounds(e.te_admin) if pd.notna(e.te_admin) else None})
    return {"households_at_quarter_end": counts, "by_year": by_year, "spend_by_year": spend}


def _mix(r) -> dict:
    hh = [float(r[f"avg_{ty}"]) if pd.notna(r[f"avg_{ty}"]) else 0.0 for ty in ACCOMMODATION_TYPES]
    te = [float(r[f"te_{ty}"]) if pd.notna(r[f"te_{ty}"]) else 0.0 for ty in ACCOMMODATION_TYPES]
    hh_share = whole_percent(hh) if sum(hh) > 0 else [None] * len(hh)
    positive = [max(v, 0.0) for v in te]
    te_share = whole_percent(positive) if sum(positive) > 0 else [None] * len(te)
    rows = []
    for ty, h, e, hs, es in zip(ACCOMMODATION_TYPES, hh, te, hh_share, te_share):
        rows.append({"type": P.TYPE_LABELS[ty], "households_average": int(half_up(h, 1)),
                     "households_share": None if hs is None else hs / 100,
                     "gross_spend": pounds(e), "spend_share": None if es is None else es / 100,
                     "gross_per_household": pounds(e / h) if h >= LINE_MIN_HOUSEHOLDS else None})
    return {"year": r.year, "types": rows,
            "note": ("Shares are whole per cent and add to 100; spend shares are of positive spend [Certain]. Spend per "
                     f"household on a type is given only where at least {LINE_MIN_HOUSEHOLDS} households are on it on "
                     "average, since a few placements can move it a long way [Likely].")}


_COUNT_WORDS = {1: "one", 2: "two", 3: "three", 4: "four"}


def _questions(r, cmp: dict) -> list[dict]:
    """Questions with the reasons first: why the figure may be wrong, then what it shows."""
    qs: list[dict] = []

    def add(reason: str, question: str):
        qs.append({"id": f"q{len(qs) + 1}", "reason": reason, "question": question})

    if cmp["status"] == "not compared":
        for why in [w.strip() for w in str(r.not_compared_because).split(";") if w.strip()]:
            if why.startswith("households:"):
                m = re.fullmatch(r"households: (\d) of 5 snapshots missing", why)
                n = int(m.group(1)) if m else None
                which = ("all five are" if n == 5 else f"{_COUNT_WORDS.get(n, n)} of them {'is' if n == 1 else 'are'}"
                         if n is not None else why.removeprefix("households: "))
                add(f"The yearly average needs at least four of the five quarter-end counts, and {which} missing from "
                    "the published tables [Certain].", "Can the missing counts be supplied or confirmed?")
            elif why == "spend: no RO4 return":
                add("Spend per household-year needs an RO4 return for the year, and none is held for it [Certain].",
                    "Has the RO4 return for the year been submitted, or is it being revised?")
            elif why.startswith("spend: nothing positive"):
                add("Councils can record TA spend outside lines 80 to 85, for example in the housing revenue account "
                    "[Likely]. Nothing positive is recorded on lines 80 to 85 for the year [Certain].",
                    "Where is the spend on these households recorded?")
        return qs

    ratio = cmp["ratio_to_median_of_others"]
    pos = cmp["position"]
    few = ""
    if cmp["households_average"] is not None and cmp["households_average"] < P.LEAD_MIN_HOUSEHOLDS:
        few = (f" With about {int(about_households(cmp['households_average']))} households on average, a few "
               "placements can move the figure a long way [Likely].")
    if pos == "more than twice the median of the others":
        add("Spend can cover placements the quarter-end counts miss, councils classify spend differently, and prices "
            f"differ [Likely].{few} On these figures, gross spend per household-year is about {ratio:.1f} times the "
            "median of the other councils shown [Certain].",
            "Does spend on lines 80 to 85 cover households that the TA1 counts do not, or spend that other councils "
            "record elsewhere?")
    elif pos == "under a quarter of the median of the others":
        add("TA spend is sometimes recorded outside lines 80 to 85, for example in the housing revenue account, and "
            f"some types cost less [Likely].{few} On these figures, gross spend per household-year is under a quarter of the "
            "median of the other councils shown [Certain].",
            "Is some of the spend on these households recorded outside lines 80 to 85?")
    elif pos == "above the upper quartile of the others":
        add("Prices, the mix of types and how spend is classified all differ between councils [Likely]. On these "
            "figures, gross spend per household-year is above the upper quartile of the other councils shown "
            "[Certain].", "Which types of accommodation account for most of the difference?")
    elif pos == "below the lower quartile of the others":
        add("Prices, the mix of types and how spend is classified all differ between councils [Likely]. On these "
            "figures, gross spend per household-year is below the lower quartile of the other councils shown "
            "[Certain].", "Is any TA spend recorded outside lines 80 to 85, or are placements mostly in lower-cost types?")
    if r.estimated:
        add("One of the five quarter-end counts is missing and was estimated, so the yearly average is an estimate "
            "[Certain].", "Can the missing count be supplied or confirmed?")
    if cmp["net_per_household"] is not None and cmp["net_per_household"] < 0:
        add("Income booked on the TA lines, such as rents and housing benefit, can exceed the spend recorded there "
            "[Likely]. Net spend per household-year is below zero [Certain].",
            "Is income booked on these lines that relates to spend recorded elsewhere?")
    for c in line_checks(r):
        if c["check"] == "stock_without_spend":
            add("Council or housing association stock is mostly costed outside these lines [Likely]. "
                f"About {c['households_about']} households are {PLACE[c['type']]}, with "
                f"{'nothing recorded' if c.get('nothing') else 'almost no spend'} on that line [Certain].", "Are the costs of these placements recorded outside lines 80 to 85, for example in the "
                "housing revenue account?")
        elif c["check"] == "line_without_spend":
            what = "nothing is recorded" if c["nothing"] else "almost nothing is recorded"
            add("Councils classify spend between the TA lines differently [Likely]. "
                f"About {c['households_about']} households are {PLACE[c['type']]}, but {what} on that line [Certain].",
                "Is the cost on another line, or outside the TA lines?")
        elif c["check"] == "spend_without_households":
            add("Spend and households can be classified on different lines [Likely]. More than a quarter of spend "
                "sits on types where the council reports fewer than one household on average [Certain].",
                "Is spend classified on different lines from the households?")
    return qs


def _data_check(code: str, inputs: PackInputs) -> dict:
    items = []
    for j in inputs.jumps[inputs.jumps.code == code].to_dict("records"):
        text = (f"The count changed by {j['change']:+.0%} between {_quarter_label(j['from_quarter'])} and "
                f"{_quarter_label(j['to_quarter'])}, from {int(j['from'])} to {int(j['to'])} households [Certain].")
        if j["one_quarter_dip"]:
            text += (" Over the neighbouring quarters the count comes back to within 20% of its earlier level, "
                     "which can point to a reporting slip [Likely].")
        items.append({"kind": "quarter change", "text": text})
    for y, t in inputs.tables.items():
        z = P.zero_ta_lines(t)
        for r in z[z.code == code].itertuples():
            items.append({"kind": "empty TA lines",
                          "text": f"Nothing is recorded on TA lines 80 to 86 in {y}, with about "
                                  f"{int(about_households(r.avg_total))} households on average [Certain]."})
    left = code in inputs.left_out
    kinds = {i["kind"] for i in items}
    why = []
    if "quarter change" in kinds:
        why.append("A change that size may be a reporting slip or a real move [Likely].")
    if "empty TA lines" in kinds:
        why.append("Nothing on the TA lines can mean spend recorded elsewhere, for example in the housing revenue "
                   "account, or a return still to be revised [Likely].")
    note = ("This council is left out of the dots on the shared chart until a person checks the items below. "
            "Each is a check to make, never a finding." + "".join(" " + w for w in why))
    return {"left_out_of_shared_chart": left, "items": items,
            "note": note if left else "No data check is outstanding for this council [Certain on the rules]."}


def council_pack(code: str, year: str = YEAR, inputs: PackInputs | None = None) -> dict:
    """The private pack for one council (its ONS code, after the 1 April 2025 recodes) in one
    comparison year. Names this council only."""
    if year not in YEARS:
        raise ValueError(f"year must be one of {YEARS}")
    inputs = inputs or PackInputs.load()
    code = P.RECODES.get(code, code)
    t = inputs.tables[year]
    row = t[t.code == code]
    if row.empty:
        raise KeyError(f"{code}: not a housing authority in the {year} tables")
    r = row.iloc[0]
    cmp = _comparison(r, inputs.shown[year], year, inputs.left_out)
    name = r["name"]
    caveats = list(CAVEATS)
    if any(c["check"] in ("line_without_spend", "spend_without_households") for c in line_checks(r)):
        caveats.append("Compare totals, not types: councils classify spend between lines differently [Likely].")
    if year == FIRST_RELEASE:
        caveats.append("This comparison uses a first release of RO4 [Certain].")
    return {
        "pack": {"version": PACK_VERSION, "private": True, "year": year, "sharing": SHARING,
                 "release_gate": RELEASE_GATE, "built_from": "data/processed (MHCLG TA1 and RO4)"},
        "council": {"code": code, "name": name, "label": CLASS_LABEL.get(r["class"], "A council"),
                    "peer_group": r.peer_group},
        "comparison": cmp,
        "trend": _trend(code, inputs),
        "mix": _mix(r),
        "questions": _questions(r, cmp),
        "spend_on_types_without_households": spend_without_households(r.share_spend_on_types_without_households),
        "data_check": _data_check(code, inputs),
        "release_notes": RELEASE_NOTES,
        "caveats": caveats,
        "attribution": ATTRIBUTION,
    }
