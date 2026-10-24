"""A made-up caseload of households in temporary accommodation, for testing the Move forward planner.

SYNTHETIC. Every record is invented by this module from a seed. No record is or describes a
real person, and no record has a name, an address, a postcode or anything that locates
anyone. Every record carries "synthetic": true, an id starting "SYN-" and a record_type that
says so, and every file says so in its meta block.

The mix follows published England figures where MHCLG publishes them, and stated guesses
where it does not (ASSUMPTIONS, each tagged):

- household with children or adults only, bed and breakfast with and without children,
  support needs, the most common length of stay and the main priority need: MHCLG,
  "Statutory homelessness in England: January to March 2026", published 13 August 2026;
- accommodation type and placements in another district: MHCLG statutory homelessness
  detailed local authority tables, sheet TA1, England row at 31 March 2026 (published
  13 August 2026), read from data/processed/ta1_wide.csv;
- weekly cost: MHCLG revenue outturn RO4 2024-25 (published 18 September 2025, updated
  11 June 2026), England gross spend on each TA line per household-year, read from
  data/processed through tamarket.picture.national_figures.

Reproducible: generate_caseload(n, seed) gives the same records for the same n and seed on
any machine. Every draw comes from random.Random(seed).random(), the one method whose
sequence Python keeps stable across versions for a given seed.

Contains public sector information licensed under the Open Government Licence v3.0.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import random
from pathlib import Path

import pandas as pd

from tamarket import picture as P
from tamarket.mhclg import ACCOMMODATION_TYPES

ROOT = Path(__file__).resolve().parent.parent
GENERATOR_VERSION = "2"
DEFAULT_SEED = 20261021
DEFAULT_N = 200
NOTICE = ("SYNTHETIC RECORDS. Made up by tamarket/synthetic.py from a seed for testing the Move forward planner. "
          "No record is or describes a real person; there are no names, addresses or postcodes.")
RECORD_TYPE = "synthetic household, not a real person"
ATTRIBUTION = ("Contains public sector information licensed under the Open Government Licence v3.0. "
               "Licence: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/")
WEEKS_PER_YEAR = 365.25 / 7
COST_YEAR = "2024-25"            # RO4 final year: the 2025-26 first release moves spend between TA lines
SNAPSHOT = "2026-Q1"             # TA1 31 March 2026
#: The day the caseload describes: each placement started weeks_in_ta weeks before it. The seed
#: is the same date. Every record is treated as one placement, entered the day it entered TA.
AS_OF = "2026-10-21"
#: The day a copy with no shared store (the public demo site, the offline copy) runs on: the day
#: after the caseload's date, the first day an officer would open it. The clocks then show what
#: the caseload was drawn to show (the B&B spread, the notices due) on whatever day the copy is
#: opened; a deployment, the live artifact and the browser tests use the real date.
DEMO_DAY = "2026-10-22"
#: The s.208 notices recorded before the planner, made up for the demo by a hash of each record's
#: id (no draw from the seed, so every other field stays as it was): of every 100 records placed
#: out of district, 82 sent within the 14 days, 10 sent later, 8 with no notice on record.
#: Shares guessed, for the demo only; no published figure says how often notices are missed.
S208_HISTORY = {"on_time": 82, "late": 10}

#: Lower-case phrases for the accommodation types, so they read the same mid-sentence.
TYPE_PHRASES = {"bed_and_breakfast": "bed and breakfast", "nightly_paid_self_contained": "nightly-paid, self-contained",
                "hostels": "hostel", "private_sector_leased": "private sector leased",
                "la_ha_stock": "council or housing association stock", "other": "other temporary accommodation"}

SOURCES = [
    {"id": "release_2026_q1", "publisher": "Ministry of Housing, Communities and Local Government",
     "title": "Statutory homelessness in England: January to March 2026", "date": "published 13 August 2026"},
    {"id": "ta1_2026_q1", "publisher": "Ministry of Housing, Communities and Local Government",
     "title": "Statutory homelessness detailed local authority tables, January to March 2026, sheet TA1",
     "date": "published 13 August 2026"},
    {"id": "ro4_2024_25", "publisher": "Ministry of Housing, Communities and Local Government",
     "title": "Local authority revenue expenditure and financing England: 2024 to 2025 individual local "
              "authority data, outturn (RO4)", "date": "published 18 September 2025, updated 11 June 2026"},
    {"id": "hca1996_s189", "publisher": "The National Archives (legislation.gov.uk)",
     "title": "Housing Act 1996, section 189(1)", "date": "revised text up to date to 16 October 2026"},
    {"id": "priority_need_order_2002", "publisher": "The National Archives (legislation.gov.uk)",
     "title": "The Homelessness (Priority Need for Accommodation) (England) Order 2002 (SI 2002/2051), articles 3 to 6",
     "date": "made 30 July 2002, in force 31 July 2002; read 22 October 2026"},
]

# --- Published figures (Certain, as MHCLG publishes them) ------------------------------------
#: Households in TA with children / adults only at 31 March 2026 (release, TA section).
WITH_CHILDREN, ADULTS_ONLY = 86_460, 49_120
CHILDREN_IN_TA = 177_530
#: Households in B&B at 31 March 2026: 1,900 contained children, 10,320 adults only.
BNB_WITH_CHILDREN, BNB_ADULTS_ONLY = 1_900, 10_320
#: Support needs of households owed a prevention or relief duty, January to March 2026.
ANY_SUPPORT_NEED = 0.618
#: Length of stay bands: (label, lowest week, highest week).
STAY_BANDS = [("less than 6 months", 1, 26), ("6 to 12 months", 27, 52), ("1 to 2 years", 53, 104),
              ("2 to 5 years", 105, 260), ("5 years or more", 261, 520)]

# --- Assumed shapes ([Guessing] unless marked) ------------------------------------------------
#: Share of households in each band. Published: for households with children the most common
#: band is 2 to 5 years (25.5%); for adult-only households, less than 6 months (32.2%). The
#: other bands are guesses that keep those bands the most common.
STAY_SHARES = {"with_children": [0.20, 0.17, 0.22, 0.255, 0.155],
               "adults_only": [0.322, 0.22, 0.22, 0.18, 0.058]}
#: Children in a household with children: shape guessed, mean 2.05 to match the published
#: 177,530 children in 86,460 households (2.05 a household).
CHILDREN_SHARES = [(1, 0.405), (2, 0.31), (3, 0.165), (4, 0.08), (5, 0.03), (6, 0.01)]
#: Adults: guessed.
ADULTS_WITH_CHILDREN = [(1, 0.65), (2, 0.35)]
ADULTS_ONLY_SIZES = [(1, 0.80), (2, 0.17), (3, 0.03)]
#: Support needs and their shares of all households. Published: 30.6%, 24.1% and 13.4%. The
#: release names history of homelessness or rough sleeping, and drug or alcohol needs, among
#: the top five without figures; those and the rest are guesses below 13.4%.
SUPPORT_NEEDS = [("history of mental health problems", 0.306), ("physical ill health and disability", 0.241),
                 ("at risk of or has experienced domestic abuse", 0.134),
                 ("history of repeat homelessness or rough sleeping", 0.11), ("drug or alcohol dependency", 0.10),
                 ("offending history", 0.08), ("young person needing support", 0.06), ("learning disability", 0.06)]
#: Priority need of adult-only households: guessed shares over the categories in s.189(1)
#: and the 2002 order. Every household with children is "household includes dependent children".
PRIORITY_ADULTS_ONLY = [("vulnerable: mental illness", 0.30), ("vulnerable: physical disability", 0.22),
                        ("homeless as a result of domestic abuse", 0.14), ("household includes a pregnant woman", 0.08),
                        ("vulnerable: old age", 0.05), ("applicant aged 16 or 17", 0.02),
                        ("care leaver aged 18 to 20", 0.04), ("vulnerable: other reason", 0.14),
                        ("homeless after an emergency such as flood or fire", 0.01)]
#: A priority need that implies a support need sets it.
IMPLIED_SUPPORT = {"vulnerable: mental illness": "history of mental health problems",
                   "vulnerable: physical disability": "physical ill health and disability",
                   "homeless as a result of domestic abuse": "at risk of or has experienced domestic abuse",
                   "applicant aged 16 or 17": "young person needing support",
                   "care leaver aged 18 to 20": "young person needing support"}
LOCAL_CONNECTION = 0.95          # guessed: MHCLG publishes referrals, not this share
COST_SPREAD = 0.35               # guessed: spread of weekly cost around the type's average (log scale)

ASSUMPTIONS = [
    {"field": "household_type", "basis": "63.8% of households in TA had children at 31 March 2026 (86,460 of "
     "135,580)", "confidence": "[Certain]", "source": "release_2026_q1"},
    {"field": "adults", "basis": "one or two adults with children (65% and 35%); one, two or three adults "
     "without (80%, 17%, 3%)", "confidence": "[Guessing]", "source": None},
    {"field": "children", "basis": "1 to 6 children, shape guessed with a mean of 2.05, matching 177,530 "
     "children in 86,460 households", "confidence": "[Guessing] for the shape, [Certain] for the mean",
     "source": "release_2026_q1"},
    {"field": "accommodation_type", "basis": "TA1 England at 31 March 2026. B&B: 1,900 of 86,460 households "
     "with children and 10,320 of 49,120 adult-only households. The other types are split between households "
     "with and without children in proportion to their totals, since the release does not publish that split",
     "confidence": "[Certain] for the totals and the B&B split, [Guessing] for the rest", "source": "ta1_2026_q1"},
    {"field": "placed_in_another_district", "basis": "43,180 of 135,580 households owed a TA duty were in another "
     "council's district at 31 March 2026 (31.8%), drawn the same for every type", "confidence":
     "[Certain] for the share, [Guessing] that it is the same for every type", "source": "ta1_2026_q1"},
    {"field": "weekly_cost_band", "basis": "England gross spend per household-year on each TA line in 2024-25, "
     "divided by 365.25/7 (about 52.18) weeks, spread around that average with a guessed spread, in 100 pound bands. Council or "
     "housing association stock is mostly costed outside the TA lines, so its band shows the TA-line outturn "
     "only [Likely]", "confidence": "[Certain] for the averages, [Guessing] for the spread", "source": "ro4_2024_25"},
    {"field": "weeks_in_ta", "basis": "length-of-stay bands; the most common band is published (2 to 5 years "
     "for households with children, 25.5%; less than 6 months for adult-only households, 32.2%) and the other "
     "bands are guessed; weeks are spread evenly within a band, and 5 years or more is drawn from 5 to 10 years. The release gives 16,280 adult-only households "
     "under 6 months as 32.2%, which is 33.1% of 49,120; the 32.2% is used as published. A priority need "
     "tied to age caps the stay: an applicant aged 16 or 17 at 104 weeks, a care leaver aged 18 to 20 at 156. A family in B&B (children or a "
     "pregnancy) has its stay folded into the last 12 weeks, 1 + (weeks - 1) mod 12, as the Order allows 6 weeks [Guessing]. A household "
     "accepted because it includes a pregnant woman is capped at 36 weeks", "confidence":
     "[Certain] for the two published bands, [Guessing] for the rest", "source": "release_2026_q1"},
    {"field": "priority_need", "basis": "every household with children: household includes dependent children "
     "(the most common priority need of households accepted for the main duty, 56.2%); adult-only households: "
     "guessed shares over the other categories in s.189(1) and the 2002 order", "confidence":
     "[Likely] for households with children, [Guessing] for the adult-only shares",
     "source": "release_2026_q1; hca1996_s189; priority_need_order_2002"},
    {"field": "support_needs", "basis": "61.8% have one or more; 30.6% mental health, 24.1% physical ill health "
     "and disability, 13.4% domestic abuse, all for households owed a prevention or relief duty in January to "
     "March 2026, used here for households in TA. Other needs and how needs combine are guessed. A priority need "
     "that implies a support need sets it, and the other draws are calibrated so that the shares hold overall "
     "(support_probabilities). A household drawn as having a need but none of those listed gets 'another "
     "support need'. A young person's support need is dropped from households whose priority need is old age",
     "confidence": "[Certain] for the published shares, [Guessing] that they hold for households in TA and for "
     "the rest", "source": "release_2026_q1"},
    {"field": "local_connection", "basis": "95% have a local connection to the council's district",
     "confidence": "[Guessing]", "source": None},
    {"field": "placed_on", "basis": "the caseload's date (" + AS_OF + ") less weeks_in_ta weeks; each household "
     "is treated as one placement that began when it entered TA", "confidence": "[Certain] by construction; a "
     "real household may have moved between placements", "source": None},
    {"field": "s208_notice_sent_on", "basis": "made up for the demo, for households placed in another district: "
     "of every 100, 82 notices sent within the 14 days, 10 sent later, 8 with none on record, by a hash of the "
     "record's id; none after the caseload's date (a notice the hash would place later is not on record)", "confidence": "[Guessing]: no published figure says how often notices are missed",
     "source": None},
    {"field": "suitability", "basis": "types are drawn without regard to the suitability rules, so some records "
     "break them (for example a household with children in B&B for longer than 6 weeks) and the planner's checks "
     "flag them", "confidence": "[Certain] by construction", "source": None},
]


def _pick(rng: random.Random, weighted):
    """One value from [(value, weight), ...] using a single rng.random() draw."""
    total = sum(w for _, w in weighted)
    u = rng.random() * total
    acc = 0.0
    for value, w in weighted:
        acc += w
        if u < acc:
            return value
    return weighted[-1][0]


def _normal(rng: random.Random) -> float:
    """A standard normal draw (Box-Muller) from two rng.random() draws."""
    u1, u2 = 1.0 - rng.random(), rng.random()
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2 * math.pi * u2)


def published_inputs(root: Path = ROOT) -> dict:
    """The figures the generator reads from data/processed: TA1 England shares at 31 March 2026
    and RO4 England weekly cost per household by type."""
    ta1 = pd.read_csv(root / "data" / "processed" / "ta1_wide.csv")
    ro4 = pd.read_csv(root / "data" / "processed" / "ro4_wide.csv")
    eng = ta1[(ta1.code == P.ENGLAND) & (ta1.quarter == SNAPSHOT)].iloc[0]
    types = {t: float(eng[t]) for t in ACCOMMODATION_TYPES}
    nat = P.national_figures(ta1, ro4, COST_YEAR)
    weekly = {t: nat["by_type"][t]["gross_per_household"] / WEEKS_PER_YEAR for t in ACCOMMODATION_TYPES}
    return {"total": float(eng.total), "with_children": float(eng.with_children), "types": types,
            "another_district": float(eng.in_ta_in_another_la), "weekly_cost": weekly}


def _type_weights(pub: dict) -> dict[str, list]:
    """Accommodation type shares for households with children and adults only: B&B as
    published, the other types in proportion to their totals."""
    types = pub["types"]
    other = {t: v for t, v in types.items() if t != "bed_and_breakfast"}
    rest_with = WITH_CHILDREN - BNB_WITH_CHILDREN
    rest_adults = ADULTS_ONLY - BNB_ADULTS_ONLY
    total_other = sum(other.values())
    with_children = [("bed_and_breakfast", BNB_WITH_CHILDREN)] + [(t, v / total_other * rest_with) for t, v in other.items()]
    adults_only = [("bed_and_breakfast", BNB_ADULTS_ONLY)] + [(t, v / total_other * rest_adults) for t, v in other.items()]
    return {"with_children": with_children, "adults_only": adults_only}


def _cost_band(weekly: float) -> tuple[str, int, int | None]:
    lo = int(weekly // 100) * 100
    if lo >= 1000:
        return "£1,000 or more", 1000, None
    if lo == 0:
        return "under £100", 0, 99
    return f"£{lo} to £{lo + 99}", lo, lo + 99


OTHER_NEED = "another support need"


def support_probabilities() -> tuple[float, float, dict[str, float]]:
    """Calibrated draw probabilities, so that over all households the published shares hold
    in expectation, counting the needs a priority need sets.

    With a the share with any need, s the share of households whose priority need sets a need,
    and s_j the share whose priority need sets need j: a household with no set need has any
    need with probability (a - s) / (1 - s); then, like every household with a set need, it
    draws each other need j with probability (r_j - s_j) / (a - s_j), where r_j is the
    published (or guessed) share. A household in the first group that draws none gets
    "another support need", one of the many categories not modelled."""
    adults_only = ADULTS_ONLY / (WITH_CHILDREN + ADULTS_ONLY)
    prio = dict(PRIORITY_ADULTS_ONLY)
    s_j = {need: adults_only * sum(prio[k] for k, v in IMPLIED_SUPPORT.items() if v == need) for need, _ in SUPPORT_NEEDS}
    s = adults_only * sum(prio[k] for k in IMPLIED_SUPPORT)
    gate = (ANY_SUPPORT_NEED - s) / (1 - s)
    q = {need: (share - s_j[need]) / (ANY_SUPPORT_NEED - s_j[need]) for need, share in SUPPORT_NEEDS}
    return s, gate, q


def _support_needs(rng: random.Random, implied: str | None, probs) -> list[str]:
    _, gate, q = probs
    needs = set()
    if implied:
        needs.add(implied)
    if implied or rng.random() < gate:
        for need, _share in SUPPORT_NEEDS:
            if need != implied and rng.random() < q[need]:
                needs.add(need)
        if not needs:
            needs.add(OTHER_NEED)
    order = [n for n, _ in SUPPORT_NEEDS] + [OTHER_NEED]
    return [n for n in order if n in needs]


# A priority need tied to age caps the stay, so that no record describes someone older than its
# category: an applicant aged 16 or 17 at 2 years, a care leaver aged 18 to 20 at 3 [Guessing for
# the caps]. The stay is drawn first and then capped, so the other records do not change.
AGE_CAP_WEEKS = {"applicant aged 16 or 17": 104, "care leaver aged 18 to 20": 156}
# A household accepted because it includes a pregnant woman cannot still be one after the
# pregnancy, so its stay is capped at 36 weeks [Guessing for the cap]; a longer stay would make
# it a household with a child. Capped after the draw, as above.
PREGNANCY_CAP_WEEKS = 36
# A family in B&B (children, or a pregnancy) is placed recently: the 2003 Order allows 6 weeks and
# the release counts the families past it (1,000 at 31 March 2026), so a family four years in B&B
# reads as implausible. The drawn stay is folded into the last 12 weeks, 1 + (weeks - 1) mod 12,
# after the draw as above, so no other record changes and the clocks keep families past 6 weeks,
# within 14 days of them and further off [Guessing for the fold].
BNB_FAMILY_WEEKS = 12
# A young person's support need does not go with old age, so it is dropped from those records
# after the draws (which keeps every other record the same) [Guessing].
NOT_WITH = {"vulnerable: old age": "young person needing support"}


def generate_records(n: int = DEFAULT_N, seed: int = DEFAULT_SEED, pub: dict | None = None) -> list[dict]:
    """n synthetic household records from the seed."""
    if not (isinstance(n, int) and 1 <= n <= 9999):
        raise ValueError("n must be a whole number from 1 to 9999")
    pub = pub or published_inputs()
    rng = random.Random(seed)
    type_w = _type_weights(pub)
    p_children = WITH_CHILDREN / (WITH_CHILDREN + ADULTS_ONLY)
    p_away = pub["another_district"] / pub["total"]
    probs = support_probabilities()
    out = []
    for i in range(n):
        has_children = rng.random() < p_children
        group = "with_children" if has_children else "adults_only"
        if has_children:
            adults = _pick(rng, ADULTS_WITH_CHILDREN)
            children = _pick(rng, CHILDREN_SHARES)
            household_type = "one adult with children" if adults == 1 else "two adults with children"
            priority = "household includes dependent children"
        else:
            priority = _pick(rng, PRIORITY_ADULTS_ONLY)
            adults = 1 if priority in ("applicant aged 16 or 17", "care leaver aged 18 to 20") else _pick(rng, ADULTS_ONLY_SIZES)
            children = 0
            household_type = {1: "single adult", 2: "two adults, no children"}.get(adults, "three or more adults, no children")
        acc = _pick(rng, type_w[group])
        away = rng.random() < p_away
        z = _normal(rng)
        weekly = pub["weekly_cost"][acc] * math.exp(COST_SPREAD * z - COST_SPREAD ** 2 / 2)
        band, lo, hi = _cost_band(weekly)
        stay_band = _pick(rng, list(zip(range(len(STAY_BANDS)), STAY_SHARES[group])))
        _, first, last = STAY_BANDS[stay_band]
        weeks = first + int(rng.random() * (last - first + 1))
        if priority in AGE_CAP_WEEKS:
            weeks = min(weeks, AGE_CAP_WEEKS[priority])
        if priority == "household includes a pregnant woman":
            weeks = min(weeks, PREGNANCY_CAP_WEEKS)
        if acc == "bed_and_breakfast" and (children > 0 or priority == "household includes a pregnant woman"):
            weeks = 1 + (weeks - 1) % BNB_FAMILY_WEEKS
        needs = _support_needs(rng, IMPLIED_SUPPORT.get(priority), probs)
        if NOT_WITH.get(priority) in needs:
            needs = [x for x in needs if x != NOT_WITH[priority]] or [OTHER_NEED]
        local = rng.random() < LOCAL_CONNECTION
        out.append({
            "id": f"SYN-{i + 1:04d}", "synthetic": True, "record_type": RECORD_TYPE,
            "household_type": household_type, "adults": adults, "children": children,
            "household_size": adults + children,
            "accommodation_type": acc, "accommodation": TYPE_PHRASES[acc],
            "placed_in_another_district": away,
            "weekly_cost_band": band, "weekly_cost_from": lo, "weekly_cost_to": hi,
            "weeks_in_ta": weeks, "priority_need": priority, "support_needs": needs,
            "local_connection": local,
        })
    for rec in out:
        rec["placed_on"] = placed_on(rec["weeks_in_ta"])
        rec["s208_notice_sent_on"] = s208_history(rec)
    return out


def placed_on(weeks_in_ta: int, as_of: str = AS_OF) -> str:
    """The day a placement of weeks_in_ta weeks began, counted back from the caseload's date."""
    return (dt.date.fromisoformat(as_of) - dt.timedelta(weeks=weeks_in_ta)).isoformat()


def s208_history(rec: dict, as_of: str = AS_OF) -> str | None:
    """The day the s.208 notice was sent before the planner, or None: made up, by a hash of the id.
    History ends on the caseload's date: a notice the hash would place after it is not on record."""
    if not rec.get("placed_in_another_district"):
        return None
    h = int(hashlib.sha256((rec["id"] + "/s208").encode("ascii")).hexdigest(), 16)
    bucket, spread = h % 100, (h // 100) % 1000
    start = dt.date.fromisoformat(rec["placed_on"])
    if bucket < S208_HISTORY["on_time"]:
        sent = start + dt.timedelta(days=spread % 14)
    elif bucket < S208_HISTORY["on_time"] + S208_HISTORY["late"]:
        sent = start + dt.timedelta(days=14 + spread % 28)
    else:
        return None
    return sent.isoformat() if sent.isoformat() <= as_of else None


def caseload_meta(n: int, seed: int, pub: dict) -> dict:
    return {
        "synthetic": True, "notice": NOTICE, "generator": "tamarket/synthetic.py",
        "generator_version": GENERATOR_VERSION, "seed": seed, "records": n,
        "fields": {"id": "SYN- and a number; not a reference to any real case",
                   "household_type": "who is in the household, by type",
                   "adults": "number of adults", "children": "number of children",
                   "household_size": "adults and children",
                   "accommodation_type": "TA1 type key", "accommodation": "the same type, in words",
                   "placed_in_another_district": "placed outside the council's own district",
                   "weekly_cost_band": "gross TA-line outturn a week, in 100 pound bands",
                   "weekly_cost_from": "lowest pound figure in the band", "weekly_cost_to": "highest, or null for the top band",
                   "weeks_in_ta": "weeks in TA so far", "priority_need": "priority need category",
                   "support_needs": "support needs, if any", "local_connection": "has a local connection to the district",
                   "placed_on": "the day the placement began (counted back from the caseload's date)",
                   "s208_notice_sent_on": "the day a notice to the receiving council was sent before the planner (made up), or null"},
        "as_of": AS_OF,
        "demo_day": DEMO_DAY,
        "published_inputs": {"ta1_snapshot": "31 March 2026", "cost_year": COST_YEAR,
                             "weekly_cost_by_type": {t: round(v, 2) for t, v in pub["weekly_cost"].items()}},
        "sources": SOURCES, "assumptions": ASSUMPTIONS, "attribution": ATTRIBUTION,
    }


def generate_caseload(n: int = DEFAULT_N, seed: int = DEFAULT_SEED, pub: dict | None = None) -> dict:
    """{"meta": ..., "records": [...]}: the caseload as one document, marked synthetic."""
    pub = pub or published_inputs()
    return {"meta": caseload_meta(n, seed, pub), "records": generate_records(n, seed, pub)}
