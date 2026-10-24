"""Display rules shared by the shared demo (scripts/build_demo_data.py) and the private
per-council packs (tamarket/pack.py), so that both draw the same councils, round the same
way and raise the same questions.

- Rounding: half_up, about_households (to 10 under 1,000, to 50 from 1,000), pounds,
  whole_percent (shares that add to exactly 100).
- Which councils are shown: left_out_codes (a data check outstanding) and shown_set
  (compared councils less those left out, with the median, ratio and patterns recomputed
  over the councils shown).
- What a council's own lines raise: line_checks, a structured list that the demo and the
  packs word in their own way.

A council far from the others is a question for a person to look into, never a finding.

Contains public sector information licensed under the Open Government Licence v3.0.
"""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

from tamarket import picture as P
from tamarket.mhclg import ACCOMMODATION_TYPES

CLASS_LABEL = {"SD": "A district council", "UA": "A unitary council", "MD": "A metropolitan council",
               "LB": "A London borough"}
PLACE = {"bed_and_breakfast": "in bed and breakfast", "nightly_paid_self_contained": "in nightly-paid, self-contained homes",
         "hostels": "in hostels", "private_sector_leased": "in private sector leased homes",
         "la_ha_stock": "in council or housing association stock", "other": "in other accommodation"}
#: Spend on types where the council reports fewer than one household, above this share of
#: positive spend, is a pattern worth a question.
SPEND_WITHOUT_HOUSEHOLDS_SHARE = 0.25
#: A line holding at least this many households on average is checked for missing spend.
LINE_MIN_HOUSEHOLDS = 50


def half_up(x: float, step: float) -> float:
    return float(Decimal(str(x / step)).quantize(Decimal(1), rounding=ROUND_HALF_UP) * Decimal(str(step)))


def about_households(x: float) -> float:
    return half_up(x, 10 if x < 1000 else 50)


def pounds(x: float) -> float:
    """A money total to the nearest pound, kept as a number with a decimal point so that a
    long total is never read as a phone number."""
    return float(half_up(x, 1))


def whole_percent(values: list[float]) -> list[int]:
    """Shares of the total as whole per cent that add to exactly 100 (largest remainder:
    round every share down, then add one point to the shares with the largest remainders)."""
    total = sum(values)
    raw = [v / total * 100 for v in values]
    out = [math.floor(x) for x in raw]
    short = round(100 - sum(out))
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - out[i], reverse=True)[:short]:
        out[i] += 1
    return out


def left_out_codes(ta1: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> set[str]:
    """Councils with a data check outstanding: a quarter-to-quarter change of more than 40%
    anywhere in the counts held (councils averaging at least 100 households), or nothing on
    TA lines 80 to 86 in either year despite at least 100 households."""
    codes = set(P.quarter_jumps(ta1).code)
    for t in tables.values():
        codes |= set(P.zero_ta_lines(t).code)
    return codes


def spend_without_households(share: float) -> bool:
    """More than a quarter of positive spend on types where the council reports fewer than
    one household on average."""
    return bool(pd.notna(share) and share > SPEND_WITHOUT_HOUSEHOLDS_SHARE)


def shown_set(t: pd.DataFrame, left_out: set[str]) -> pd.DataFrame:
    """Compared councils less those left out, with the median, ratio and patterns
    recomputed over the councils shown."""
    s = t[t.compared & ~t.code.isin(left_out)].copy()
    s["median_shown"] = s.groupby("peer_group").gross_per_household.transform("median")
    s["ratio_shown"] = s.gross_per_household / s.median_shown
    s["far_above"] = (s.avg_total >= P.LEAD_MIN_HOUSEHOLDS) & (s.ratio_shown > P.PEER_MULTIPLE)
    s["far_below"] = s.ratio_shown < P.LOW_RATIO
    s["spend_without_households"] = s.share_spend_on_types_without_households.fillna(0) > SPEND_WITHOUT_HOUSEHOLDS_SHARE
    return s


def line_checks(r) -> list[dict]:
    """What a council's own lines raise, as structured items for the demo and the packs to
    word: households on a line with almost no spend on it, council or housing association
    stock with almost no spend, more than a quarter of spend on types without households, and
    (when any line item is raised) a reminder to compare totals, not types."""
    out = []
    by_line = False
    if not float(r["te_accom"]) > 0:      # nothing positive on the TA lines: no per-line shares
        return out
    for ty in ACCOMMODATION_TYPES:
        hh, te = float(r[f"avg_{ty}"]), float(r[f"te_{ty}"])
        share = te / float(r["te_accom"])
        if not hh >= LINE_MIN_HOUSEHOLDS:   # NaN-safe: a council with too few counts has no average
            continue
        about = int(about_households(hh))
        if ty == "la_ha_stock":
            if share < 0.02:
                out.append({"check": "stock_without_spend", "type": ty, "households_about": about,
                            "nothing": te == 0})
            continue
        if share < 0.01:
            out.append({"check": "line_without_spend", "type": ty, "households_about": about,
                        "nothing": te == 0})
            by_line = True
    if spend_without_households(r["share_spend_on_types_without_households"]):
        out.append({"check": "spend_without_households"})
        by_line = True
    if by_line:
        out.append({"check": "compare_totals"})
    return out
