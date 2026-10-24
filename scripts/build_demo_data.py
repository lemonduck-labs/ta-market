"""Data for the TA demo page: "your council against the rest", with no council named.

Writes demo/ta_demo_data.json and one JSON file of row objects per dataset to demo/ta/,
from the processed tables (every number computed here):
- England figures, spend by year and by type (MHCLG England rows);
- for 2024-25 and each peer group, every council shown as an unnamed point (gross and net
  per household-year, households to the nearest 10), sorted by cost so that the order
  carries no code or name;
- quartiles per peer group over the councils shown;
- two example councils chosen by fixed rules (docs/adr/0001: unnamed, rounded figures),
  each with its mix by type and the questions its figures raise;
- counts of councils by coverage and by pattern, never a council on its own.

Councils with a data check outstanding (a quarter-to-quarter change of more than 40% in the
counts held, or nothing on the TA lines in either year) are left out of the points,
quartiles and examples and only counted, until a person checks them (docs/decision_log.md).

Usage:  python scripts/build_demo_data.py

Contains public sector information licensed under the Open Government Licence v3.0.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tamarket import picture as P  # noqa: E402
from tamarket.display import (CLASS_LABEL, PLACE, about_households, half_up, left_out_codes,  # noqa: E402,F401
                              line_checks, pounds, shown_set, whole_percent)
from tamarket.mhclg import ACCOMMODATION_TYPES  # noqa: E402

PROC, OUT = ROOT / "data" / "processed", ROOT / "demo"
YEAR = "2024-25"                     # the year councils are compared in
YEARS = ("2024-25", "2025-26")       # England figures
FIRST_RELEASE = "2025-26"            # RO4 first release (second release due December 2026)
GROUPS = ("London", "Rest of England")
ATTRIBUTION = ("Contains public sector information licensed under the Open Government Licence v3.0. "
               "Licence: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/")
#: Example rules: in each peer group, the council shown closest to the median, with all five
#: counts and at least this many households on average.
EXAMPLE_MIN_HOUSEHOLDS = {"London": 500, "Rest of England": 200}
ENGLAND_ONLY = {"left_out"}   # given for England only; it does not hide these councils (decision log, 22 Oct 2026)
#: Files in demo/ta written by other builders, never deleted here (tamarket/synthetic.py).
KEEP = {"synthetic_caseload.json"}


def points(s: pd.DataFrame, group: str) -> list[dict]:
    c = s[s.peer_group == group].sort_values("gross_per_household", kind="stable")
    return [{"gross": half_up(r.gross_per_household, 10), "net": half_up(r.net_per_household, 10),
             "households": int(half_up(r.avg_total, 10))} for r in c.itertuples()]


def quartiles(s: pd.DataFrame, group: str) -> dict:
    """Gross per household-year at the quartiles of the grey dots, the councils shown less the
    example (the chart's band and median line). The example is left out so that the median and
    its neighbouring dot cannot give its figure back more precisely than it is shown."""
    c = s[s.peer_group == group]
    return {"gross": [half_up(float(c.gross_per_household.quantile(p)), 10) for p in (0.25, 0.5, 0.75)],
            "councils": int(len(c))}


def mix(r) -> list[dict]:
    hh = whole_percent([float(r[f"avg_{ty}"]) for ty in ACCOMMODATION_TYPES])
    te = whole_percent([float(r[f"te_{ty}"]) for ty in ACCOMMODATION_TYPES])
    return [{"type": P.TYPE_LABELS[ty], "households_share": h / 100, "spend_share": e / 100}
            for ty, h, e in zip(ACCOMMODATION_TYPES, hh, te)]


def questions(r) -> list[str]:
    """What the figures of a council near the median raise, facts first, each tagged. The
    checks come from tamarket.display.line_checks, shared with the private packs."""
    q = ["Nothing stands out on the total: its figure is about the median of the other councils shown [Certain]."]
    for c in line_checks(r):
        if c["check"] == "stock_without_spend":
            spend = "nothing recorded" if c.get("nothing") else "almost no spend"
            q.append(f"About {c['households_about']} households are {PLACE[c['type']]}, with {spend} on that line [Certain]. "
                     "That stock is mostly costed outside these lines [Likely].")
        elif c["check"] == "line_without_spend":
            what = "nothing is recorded" if c["nothing"] else "almost nothing is recorded"
            q.append(f"About {c['households_about']} households are {PLACE[c['type']]}, but {what} on that line [Certain]. "
                     "Is the cost on another line, or outside the TA lines?")
        elif c["check"] == "spend_without_households":
            q.append("More than a quarter of spend sits on types where the council reports fewer than one household "
                     "[Certain]. Is spend classified on different lines from the households?")
        elif c["check"] == "compare_totals":
            q.append("Compare totals, not types: councils classify spend between lines differently [Likely].")
    return q


def choose(s: pd.DataFrame) -> list:
    """The two examples, by fixed rules, so the choice is repeatable and not hand-picked: in
    each peer group, among the councils shown with all five counts and at least
    EXAMPLE_MIN_HOUSEHOLDS, the one closest to the median of the councils shown. With an even
    number of councils the two in the middle are equally close, so the gap is rounded before
    sorting (floating-point noise must not decide) and a tie goes to the lower gross figure."""
    c = s[~s.estimated & (s.snapshots == 5)]
    picks = []
    for role, group in (("typical-london", "London"), ("typical-rest", "Rest of England")):
        g = c[(c.peer_group == group) & (c.avg_total >= EXAMPLE_MIN_HOUSEHOLDS[group])]
        r = g.assign(gap=(g.ratio_shown - 1).abs().round(9)).sort_values(["gap", "gross_per_household"], kind="stable").iloc[0]
        if r.far_above or r.far_below:
            raise SystemExit(f"{role}: the example rule picked a council far from the median")
        picks.append((role, r))
    return picks


def example(r, s: pd.DataFrame, role: str) -> dict:
    peers = s[(s.peer_group == r.peer_group) & (s.code != r.code)]
    lower = int((peers.gross_per_household < r.gross_per_household).sum())
    return {"id": role, "label": CLASS_LABEL.get(r["class"], "A council"), "group": r.peer_group, "year": YEAR,
            "households_about": about_households(float(r.avg_total)),
            "gross_per_household": half_up(float(r.gross_per_household), 100),
            "net_per_household": half_up(float(r.net_per_household), 100),
            "ratio_to_peer_median": half_up(float(r.gross_per_household / peers.gross_per_household.median()), 0.1),
            "peers_lower": lower, "peers_shown": int(len(peers)),
            "share_of_peers_lower_gross": half_up(lower / len(peers), 0.01),
            "mix": mix(r), "questions": questions(r)}


def patterns(t: pd.DataFrame, s: pd.DataFrame, left_out: set[str]) -> list[dict]:
    """Counts of councils, by peer group: coverage first, then patterns among the councils
    shown. Counts only; no council appears on its own."""
    comp = t[t.compared]
    rows = [
        ("in_tables", "coverage", "Councils in the tables",
         "Housing authorities in both MHCLG tables for 2024-25 [Certain].", t, None),
        ("not_shown", "coverage", "Not shown as dots",
         "Not compared: two or more of the five counts missing, no positive spend on lines 80 to 85, or fewer "
         "than 50 households on average [Certain]. Or left out until a person checks them: councils averaging "
         "at least 100 households whose count changes by more than 40% between quarters, or with nothing on "
         "lines 80 to 86 in 2024-25 or 2025-26 [Certain on the rules]. A change that size may be a reporting "
         "slip or a real move [Likely].", t, ~t.code.isin(s.code)),
        ("left_out", "coverage", "Of these, left out for a data check",
         "Given for England only. Councils are unnamed, not anonymous: each dot matches one council in MHCLG's "
         "published tables [Certain].",
         comp, comp.code.isin(left_out)),
        ("shown", "coverage", "Shown",
         "The councils on the chart: each example, and the grey dots behind its band and median [Certain].", s, None),
        ("far_above", "pattern",
         "More than twice the median of all the councils shown in the group, with at least 100 households",
         "The spend may cover households the count does not, be classified differently, or prices may be "
         "higher [Likely].", s, s.far_above),
        ("far_below", "pattern", "Under a quarter of the median of all the councils shown in the group",
         "Spend is probably recorded outside the TA lines, or placements are mostly in cheaper types [Likely].",
         s, s.far_below),
        ("spend_without_households", "pattern",
         "More than a quarter of spend on types where the council reports fewer than one household",
         "Spend and households classified on different lines; compare totals, not types [Likely].",
         s, s.spend_without_households),
        ("estimated", "pattern", "One of the five counts missing",
         "The missing count is estimated, between its neighbours or, for the first or last count, copied from "
         "the nearest one, so the yearly average is an estimate [Certain].", s, s.estimated),
    ]
    out = []
    for pid, section, pattern, may_mean, frame, mask in rows:
        m = pd.Series(True, index=frame.index) if mask is None else mask.astype(bool)
        by = {g: int((m & (frame.peer_group == g)).sum()) for g in GROUPS}
        england_only = pid in ENGLAND_ONLY
        out.append({"pattern_id": pid, "section": section, "pattern": pattern, "may_mean": may_mean,
                    "london": None if england_only else by["London"],
                    "rest_of_england": None if england_only else by["Rest of England"], "england": int(m.sum())})
    n = {r["pattern_id"]: r for r in out}
    for g in ("london", "rest_of_england", "england"):
        assert n["in_tables"][g] - n["not_shown"][g] == n["shown"][g], g
    assert n["left_out"]["england"] == len(set(comp.code) & left_out)
    return out


def write_datasets(data: dict) -> None:
    """The same figures as row tables, one JSON file per dataset, for the dashboard."""
    d = OUT / "ta"
    d.mkdir(exist_ok=True)
    nat = [{"year": y, **n} for y, n in data["national"].items()]
    by_type = [{"year": y, "type": t, **v} for y, types in data["by_type"].items() for t, v in types.items()]
    spend = data["spend_by_year"]
    peers = [{"point": f"{y}-{'L' if g == 'London' else 'R'}{i + 1:03d}", "year": y, "group": g, **pt}
             for y, gs in data["peers"].items() for g, pts in gs.items() for i, pt in enumerate(pts)]
    quart = [{"year": y, "group": g, "measure": m, "lower_quartile": q[m][0], "median": q[m][1],
              "upper_quartile": q[m][2], "councils": q["councils"]}
             for y, gs in data["quartiles"].items() for g, q in gs.items() for m in ("gross",)]
    ex = [{k: v for k, v in e.items() if k not in ("mix", "questions")} for e in data["examples"]]
    mx = [{"example_type": f"{e['id']}|{m['type']}", "id": e["id"], **m} for e in data["examples"] for m in e["mix"]]
    qs = [{"question_id": f"{e['id']}-{i + 1}", "id": e["id"], "question": q}
          for e in data["examples"] for i, q in enumerate(e["questions"])]
    for f in d.glob("*.json"):
        if f.name not in KEEP:
            f.unlink()
    for name, rows in {"national": nat, "by_type": by_type, "spend_by_year": spend, "peers": peers,
                       "quartiles": quart, "examples": ex, "example_mix": mx, "example_questions": qs,
                       "patterns": data["patterns"]}.items():
        (d / f"{name}.json").write_text(json.dumps(rows, indent=1, default=float))


def main() -> int:
    ta1 = pd.read_csv(PROC / "ta1_wide.csv")
    ro4 = pd.read_csv(PROC / "ro4_wide.csv")
    tables = {y: P.council_table(ta1, ro4, y) for y in YEARS}
    nat = {y: P.national_figures(ta1, ro4, y) for y in YEARS}
    left_out = left_out_codes(ta1, tables)
    t = tables[YEAR]
    s = shown_set(t, left_out)
    picks = choose(s)
    example_codes = {r.code for _, r in picks}   # drawn once, as "this council", not as a grey dot
    spend = P.spend_by_year(ro4)
    data = {
        "meta": {"attribution": ATTRIBUTION, "built_from": "data/processed (MHCLG TA1 and RO4)", "year": YEAR,
                 "first_release": FIRST_RELEASE,
                 "note": "No council is named. Examples are chosen by fixed rules in scripts/build_demo_data.py. "
                         "Councils with a data check outstanding are counted, not shown."},
        "national": {y: {"households": int(half_up(n["avg_households_england"], 1)),
                         "gross_accom": pounds(n["te_accom_england_row"]), "net_accom": pounds(n["nce_accom_england_row"]),
                         "ta_total": pounds(n["te_ta_total_england_row"]),
                         "gross_per_household": half_up(n["gross_per_household_england"], 10),
                         "net_per_household": half_up(n["net_per_household_england"], 10),
                         "first_release": y == FIRST_RELEASE}
                     for y, n in nat.items()},
        "by_type": {YEAR: {P.TYPE_LABELS[k]: {"households": int(half_up(v["avg_households"], 1)),
                                              "gross": pounds(v["te"]),
                                              "gross_per_household": half_up(v["gross_per_household"], 10)}
                           for k, v in nat[YEAR]["by_type"].items()}},
        "spend_by_year": [{"year": r["year"], **{ty: pounds(r[ty]) for ty in ACCOMMODATION_TYPES},
                           "first_release": r["year"] == FIRST_RELEASE} for r in spend.to_dict(orient="records")],
        "peers": {YEAR: {g: points(s[~s.code.isin(example_codes)], g) for g in GROUPS}},
        "quartiles": {YEAR: {g: quartiles(s[~s.code.isin(example_codes)], g) for g in GROUPS}},
        "examples": [example(r, s, role) for role, r in picks],
        "patterns": patterns(t, s, left_out),
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "ta_demo_data.json").write_text(json.dumps(data, indent=1, default=float))
    write_datasets(data)
    print(f"wrote demo/ta_demo_data.json and demo/ta/: {sum(len(v) for v in data['peers'][YEAR].values())} "
          f"unnamed points, {len(data['examples'])} examples, {len(data['patterns'])} pattern rows")
    print(ATTRIBUTION)
    return 0


if __name__ == "__main__":
    sys.exit(main())
