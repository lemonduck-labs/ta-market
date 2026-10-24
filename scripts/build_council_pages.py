"""Render each private council pack as one self-contained HTML page for that council's officers.

Reads data/private/packs/<ONS code>.json (scripts/build_packs.py) and writes
reports/private/councils/<ONS code>.html, which git ignores; the script checks that before it
writes and stops if not. Each page names its own council only. The other councils in its peer
group appear only as a count, a band and a median, never by name or code (docs/adr/0001). A page
shows what its pack holds: households in temporary accommodation, the accommodation mix, spend
per household-year, where the council sits among the others and the questions that raises, the
data checks, the caveats, sources and releases, the Open Government Licence line and link, and a
footer saying the page is private, for that council only, built on a date from a commit. Plain
HTML and CSS: no script, nothing loaded from elsewhere, light and dark, print and phone.

Every page is checked in memory before it is written:
- no other council's name or code: every local authority in data/processed/ta1_wide.csv and
  ro4_wide.csv, the tables the packs are built from (TA1 councils and every RO4 authority but
  the England row), by name, ONS code and RO4 code;
- no ONS code but the council's own;
- the licence line and the link to the licence;
- and its own name, no em or en dash, nothing that loads or runs.
A page that fails is not written, and the script exits 1 listing why. It prints counts and ONS
codes only, never a council's name.

Usage:  python scripts/build_council_pages.py                write every page
        python scripts/build_council_pages.py --check        build and check in memory; write nothing
        python scripts/build_council_pages.py --only CODE    one council's page (repeatable)
        python scripts/build_council_pages.py --out DIR      another folder: git must ignore it, or it
                                                             must sit outside any git repository

The pages never leave the owner's machine except to the council each one names, and only after
the release gate in its pack: the owner switches naming on for that copy (docs/adr/0001), a
person has done its data checks, and the fact-checker and the guardrails reviewer pass it.

Contains public sector information licensed under the Open Government Licence v3.0.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tamarket.pack import RELEASE_GATE  # noqa: E402
from tamarket.picture import RECODES, snapshot_quarters  # noqa: E402

PACKS = ROOT / "data" / "private" / "packs"
OUT = ROOT / "reports" / "private" / "councils"
TABLES = ROOT / "data" / "processed"
OGL_LINE = "Contains public sector information licensed under the Open Government Licence v3.0."
OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
# What a page is built from. The footer names the commit, and says when any of these differs from it.
INPUTS = ["scripts/build_council_pages.py", "tamarket/pack.py", "tamarket/display.py", "tamarket/picture.py",
          "tamarket/mhclg.py", "data/processed/ta1_wide.csv", "data/processed/ro4_wide.csv"]
# The Sources card of the shared demo (demo/ta/index.html), word for word, links included.
SOURCES = [
    '<a href="https://www.gov.uk/government/statistical-data-sets/live-tables-on-homelessness">MHCLG, live tables '
    'on homelessness</a>: detailed local authority tables, sheet TA1, quarter ends from 31 March 2024 to 31 March '
    '2026. Latest file 13 August 2026; the other quarters from the files on that page, revised versions where MHCLG '
    'has published them.',
    'MHCLG, local authority revenue expenditure and financing, individual local authority data, RO4: <a href="https:'
    '//www.gov.uk/government/statistics/local-authority-revenue-expenditure-and-financing-england-2023-to-2024-'
    'individual-local-authority-data-outturn">2023-24</a> (all authorities) and <a href="https://www.gov.uk/'
    'government/statistics/local-authority-revenue-expenditure-and-financing-england-2024-to-2025-individual-local-'
    'authority-data-outturn">2024-25</a> (410 of 411 authorities), both updated 11 June 2026; <a href="https://www.'
    'gov.uk/government/statistics/local-authority-revenue-expenditure-and-financing-england-2025-to-2026-individual-'
    'local-authority-data-outturn">2025-26</a>, first release of 17 September 2026 (377 of 413 authorities; second '
    'release due December 2026).',
    '<a href="https://www.gov.uk/government/statistics/local-authority-revenue-expenditure-and-financing-england-2025-'
    'to-2026-first-release/local-authority-revenue-expenditure-and-financing-england-2025-to-2026-first-release">MHCLG,'
    ' 2025-26 first release</a>, on the changes between the TA lines, and its <a href="https://www.gov.uk/government/'
    'statistics/local-authority-revenue-expenditure-and-financing-england-2025-to-2026-first-release/local-authority-'
    'revenue-expenditure-and-financing-england-2025-to-2026-technical-notes">technical notes</a>, on its coverage (377 '
    'of 413 authorities) and the second release.',
    '<a href="https://www.gov.uk/government/statistics/announcements/statutory-homelessness-in-england-april-to-june-'
    '2026">MHCLG, announcement of the April to June 2026 statistics</a>: the provisional release date.',
]
GROUP = {"London": ("London", "in London"), "Rest of England": ("the rest of England", "outside London")}
COUNT_WORD = {1: "One", 2: "Two", 3: "Three", 4: "Four"}
CHECK_KIND = {"quarter change": "Change between quarter ends", "empty TA lines": "Empty TA lines"}
STATUS_SHORT = {"compared": "compared", "provisional: data check outstanding": "provisional (data check outstanding)",
                "not compared": "not compared"}

CSS = """
:root {
  color-scheme: light dark;
  --bg: #f3f1ec; --panel: #fdfcfa; --panel-2: #ebe8e1; --line: #d9d4ca; --line-strong: #b8b1a4;
  --fg: #1f2421; --fg-2: #3c4540; --muted: #5d6660; --accent: #1d6157; --context: #8a8478;
  --warn: #7d540a; --warn-soft: #f5e9d2;
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, "Times New Roman", serif;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #141816; --panel: #1b201d; --panel-2: #222824; --line: #2f3632; --line-strong: #424b46;
    --fg: #e6e9e7; --fg-2: #c5ccc8; --muted: #98a29c; --accent: #6cc0b1; --context: #7d8680;
    --warn: #e2b55a; --warn-soft: #3a3019;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.5 var(--sans); }
main { max-width: 64rem; margin: 0 auto; padding: 20px 16px 40px; display: flex; flex-direction: column; gap: 20px; }
h1, h2, h3 { margin: 0; text-wrap: balance; }
h1 { font-family: var(--serif); font-weight: 600; font-size: clamp(1.55rem, 1.2rem + 1.6vw, 2.1rem); line-height: 1.2; }
h2 { font-size: 1.125rem; font-weight: 600; line-height: 1.3; }
h3 { font-size: 1rem; font-weight: 600; }
p { margin: 0; max-width: 72ch; }
a { color: inherit; text-decoration: underline; text-underline-offset: 2px; overflow-wrap: anywhere; }
a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
ul, ol { margin: 0; padding-left: 1.25em; display: flex; flex-direction: column; gap: 8px; max-width: 76ch; }
.private { border: 1px solid var(--warn); background: var(--warn-soft); border-radius: 6px; padding: 8px 12px; font-size: .9375rem; }
header { display: flex; flex-direction: column; gap: 8px; }
.meta { color: var(--fg-2); font-size: .9375rem; }
.lede { color: var(--fg-2); }
.note, .cap, .tag { color: var(--muted); }
.note { font-size: .9375rem; }
.cap { font-size: .875rem; }
.tag { font-size: .8125rem; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 9.5rem), 1fr)); gap: 12px; }
.kpi, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; min-width: 0; }
.kpi { padding: 14px 16px; display: flex; flex-direction: column; gap: 4px; }
.kpi .lbl { font-size: .875rem; color: var(--fg-2); }
.kpi .val { font-family: var(--serif); font-size: 1.75rem; line-height: 1.15; overflow-wrap: anywhere; }
.kpi .val.word { font-size: 1.3rem; }
.card { padding: 16px 18px; display: flex; flex-direction: column; gap: 12px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 26rem), 1fr)); gap: 20px; align-items: start; }
.flag { border-left: 3px solid var(--warn); padding: 2px 0 2px 10px; }
.questions li p + p { margin-top: 2px; font-weight: 600; }
.kind { font-weight: 600; }
.strip { position: relative; padding-top: 1.7rem; }
.strip-label { position: absolute; top: 0; font-size: .875rem; font-weight: 600; white-space: nowrap; }
.strip-pin { position: absolute; top: 1.35rem; height: calc(.35rem + 9px); width: 2px; margin-left: -1px; background: var(--accent); }
.strip-track { position: relative; height: 32px; background: var(--panel-2); border-radius: 6px; }
.strip-grid { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--line); }
.strip-band { position: absolute; top: 5px; bottom: 5px; background: var(--context); opacity: .45; border-radius: 4px; }
.strip-median { position: absolute; top: 0; bottom: 0; width: 2px; margin-left: -1px; background: var(--fg-2); }
.strip-own { position: absolute; top: 50%; width: 14px; height: 14px; margin: -7px 0 0 -7px; border-radius: 50%;
  background: var(--accent); box-shadow: 0 0 0 2px var(--panel-2); }
.strip-axis { position: relative; height: 1.4rem; margin-top: 4px; font-size: .8125rem; color: var(--muted); font-variant-numeric: tabular-nums; }
.strip-axis span { position: absolute; top: 0; transform: translateX(-50%); white-space: nowrap; }
.strip-axis span:first-child { transform: none; }
.strip-axis span:last-child { transform: translateX(-100%); }
.key { list-style: none; padding: 0; flex-direction: row; flex-wrap: wrap; gap: 6px 18px; font-size: .875rem; color: var(--fg-2); }
.key li { display: flex; align-items: center; gap: 8px; }
.sw { display: inline-block; flex: none; }
.sw-band { width: 18px; height: 12px; background: var(--context); opacity: .45; border-radius: 3px; }
.sw-median { width: 2px; height: 16px; background: var(--fg-2); }
.sw-own { width: 12px; height: 12px; border-radius: 50%; background: var(--accent); }
.sw-hh, .sw-sp { width: 12px; height: 12px; border-radius: 3px; }
.sw-hh, .bar-hh { background: var(--context); }
.sw-sp, .bar-sp, .bar-ct { background: var(--accent); }
.mix { list-style: none; padding: 0; gap: 12px; max-width: none; }
.mix li { display: grid; grid-template-columns: minmax(8rem, 15rem) 1fr; gap: 4px 14px; align-items: center; }
.mix .t { font-size: .9375rem; }
.bars { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.barline { display: flex; align-items: center; gap: 6px; font-size: .8125rem; color: var(--fg-2); font-variant-numeric: tabular-nums; }
.bar { display: block; flex: none; height: 10px; border-radius: 0 4px 4px 0; }
.scroll { overflow-x: auto; position: relative; }
table { border-collapse: collapse; width: 100%; font-size: .9375rem; font-variant-numeric: tabular-nums; }
caption { text-align: left; font-weight: 600; padding-bottom: 6px; }
th, td { text-align: left; vertical-align: top; padding: 6px 10px 6px 0; border-bottom: 1px solid var(--line); }
thead th { color: var(--fg-2); font-weight: 600; font-size: .875rem; vertical-align: bottom; }
.num { text-align: right; white-space: nowrap; }
td.barcell { width: 32%; min-width: 5rem; vertical-align: middle; }
th small, td small { display: block; font-weight: 400; color: var(--muted); font-size: .8125rem; }
thead th.num { white-space: normal; }
footer { display: flex; flex-direction: column; gap: 6px; font-size: .875rem; color: var(--fg-2); border-top: 1px solid var(--line); padding-top: 14px; }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
@media (max-width: 40rem) {
  .mix li { grid-template-columns: 1fr; }
  .card { padding: 14px; }
  table { font-size: .875rem; }
  .barcol, td.barcell { display: none; }
  table.stack thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  table.stack, table.stack caption, table.stack tbody, table.stack tr, table.stack th, table.stack td { display: block; }
  table.stack tr { padding: 6px 0; border-bottom: 1px solid var(--line); }
  table.stack th, table.stack td { border: 0; padding: 2px 0; text-align: left; }
  table.stack td { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
  table.stack td::before { content: attr(data-label); color: var(--muted); white-space: normal; }
  table.stack td > span { text-align: right; }
}
@media print {
  :root { color-scheme: light; --bg: #fff; --panel: #fff; --panel-2: #eee; --line: #bbb; --line-strong: #888;
    --fg: #000; --fg-2: #222; --muted: #444; --accent: #1d6157; --context: #8a8478; --warn: #6b4500; --warn-soft: #fff; }
  body { font-size: 10.5pt; }
  main { max-width: none; padding: 0; gap: 12pt; }
  .kpi, .private, .strip, .key, tr, li { break-inside: avoid; }
  h2, h3, caption { break-after: avoid; }
  .grid { display: block; }
  .grid > * + * { margin-top: 12pt; }
  .scroll { overflow: visible; }
  .strip *, .sw, .bar { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .sources a::after { content: " (" attr(href) ")"; font-size: 8.5pt; overflow-wrap: anywhere; }
}
@page { margin: 15mm; }
"""


# ------------------------------------------------------------------ formatting

def esc(value) -> str:
    return html.escape(str(value), quote=True)


TAG = re.compile(r"\[(?:Certain|Likely|Guessing)[^\]]*\]")


def prose(text: str) -> str:
    """Pack text, escaped, with each confidence tag set in its own span."""
    out, last = [], 0
    for m in TAG.finditer(text):
        out += [esc(text[last:m.start()]), f'<span class="tag">{esc(m.group(0))}</span>']
        last = m.end()
    return "".join(out) + esc(text[last:])


def money(v) -> str:
    if v is None:
        return "n/a"
    n = int(round(float(v)))
    return ("-£" if n < 0 else "£") + f"{abs(n):,}"


def whole(v) -> str:
    return "n/a" if v is None else f"{int(round(float(v))):,}"


def pct(v) -> str:
    return "n/a" if v is None else f"{int(round(float(v) * 100))}%"


def times(v) -> str:
    return "n/a" if v is None else f"{float(v):.2f}"


def long_date(d: dt.date) -> str:
    return f"{d.day} {d:%B %Y}"


def quarter_end(year: str, first: bool) -> str:
    start = int(year[:4])
    return f"31 March {start if first else start + 1}"


# ------------------------------------------------------------------ sections

@dataclass
class Build:
    date: str
    commit: str
    dirty: bool


def kpis(pack: dict) -> str:
    cmp, year = pack["comparison"], pack["comparison"]["year"]
    where = GROUP.get(cmp["peer_group"], (cmp["peer_group"], f"in {cmp['peer_group']}"))[1]
    compared = cmp["status"] != "not compared"
    hh_cap = f"from the five quarter-end counts, {quarter_end(year, True)} to {quarter_end(year, False)}"
    if cmp["households_average"] is None:
        hh_cap = "too few quarter-end counts for an average (see below)"
    elif cmp["households_estimated"]:
        hh_cap += '; one count missing and estimated <span class="tag">[Certain]</span>'
    gross_cap = (f"{times(cmp['ratio_to_median_of_others'])} times the median of the others" if compared
                 else "not compared with the others (see below)")
    if compared:
        o = cmp["others"]
        last_val = pct(cmp["share_of_others_lower"])
        last_cap = f"{cmp['others_lower']} of the {o['councils']} other councils shown {where}"
        if cmp["status"] != "compared":
            last_cap += "; provisional, a data check is outstanding"
        last = ("Others with a lower gross figure", last_val, "", last_cap)
    else:
        last = ("Against the others", "Not compared", " word", "see why below")
    tiles = [("Households in TA, yearly average", whole(cmp["households_average"]), "", hh_cap),
             ("Gross spend per household-year", money(cmp["gross_per_household"]), "", gross_cap),
             ("Net, after income such as housing benefit", money(cmp["net_per_household"]), "", "per household-year"),
             last]
    cells = "".join(f'<div class="kpi"><span class="lbl">{esc(lbl)}</span><span class="val{cls}">{esc(val)}</span>'
                    f'<span class="cap">{cap}</span></div>' for lbl, val, cls, cap in tiles)
    return f'<section class="kpis" aria-label="Four figures for {esc(year)}">{cells}</section>'


def axis(top: float, ticks: int = 4) -> tuple[float, list[float]]:
    """A round end for the scale and its ticks, about `ticks` steps of 1, 2, 2.5 or 5 times a power of ten."""
    raw = max(top, 1.0) / ticks
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    end = math.ceil(top / step) * step
    return end, [i * step for i in range(int(round(end / step)) + 1)]


def strip(own: float, o: dict) -> str:
    """Where this council's figure sits against the band and median of the others, in HTML and CSS."""
    lq, med, uq = o["lower_quartile_gross"], o["median_gross"], o["upper_quartile_gross"]
    end, ticks = axis(max(own, uq) * 1.1)
    x = lambda v: max(0.0, min(100.0, v / end * 100))  # noqa: E731
    side = f"left: {x(own):.2f}%" if x(own) <= 50 else f"right: {100 - x(own):.2f}%"
    grid = "".join(f'<span class="strip-grid" style="left: {x(t):.2f}%"></span>' for t in ticks[1:-1])
    label = (f"Gross spend per household-year: this council {money(own)}; the middle half of the other councils "
             f"{money(lq)} to {money(uq)}, their median {money(med)}.")
    return (f'<div class="strip" role="img" aria-label="{esc(label)}">'
            f'<span class="strip-label" style="{side}" aria-hidden="true">This council {money(own)}</span>'
            f'<span class="strip-pin" style="left: {x(own):.2f}%" aria-hidden="true"></span>'
            f'<div class="strip-track" aria-hidden="true">{grid}'
            f'<span class="strip-band" style="left: {x(lq):.2f}%; width: {x(uq) - x(lq):.2f}%"></span>'
            f'<span class="strip-median" style="left: {x(med):.2f}%"></span>'
            f'<span class="strip-own" style="left: {x(own):.2f}%"></span></div>'
            '<div class="strip-axis" aria-hidden="true">'
            + "".join(f'<span style="left: {x(t):.2f}%">{money(t)}</span>' for t in ticks) + "</div></div>"
            '<ul class="key">'
            f'<li><span class="sw sw-own"></span>This council: {money(own)}</li>'
            f'<li><span class="sw sw-band"></span>Middle half of the others: {money(lq)} to {money(uq)}</li>'
            f'<li><span class="sw sw-median"></span>Their median: {money(med)}</li></ul>')


def not_compared_reasons(text: str, year: str) -> list[str]:
    out = []
    for why in [w.strip() for w in str(text).split(";") if w.strip()]:
        missing = re.fullmatch(r"households: (\d) of 5 snapshots missing", why)
        few = re.fullmatch(r"fewer than (\d+) households on average", why)
        if missing:
            n = int(missing.group(1))
            which = "All five" if n == 5 else f"{COUNT_WORD.get(n, n)} of the five"
            out.append(f"{which} quarter-end counts for {year} {'is' if n == 1 else 'are'} missing from the "
                       "published tables, and a yearly average needs at least four [Certain].")
        elif why == "spend: no RO4 return":
            out.append(f"No RO4 return for {year} is in the published tables [Certain].")
        elif why.startswith("spend: nothing positive"):
            out.append(f"Nothing positive is recorded on RO4 lines 80 to 85 for {year} [Certain].")
        elif few:
            out.append(f"Fewer than {few.group(1)} households were in TA on average in {year}, and councils are "
                       f"compared only from {few.group(1)} [Certain on the rule].")
        else:
            out.append(why[:1].upper() + why[1:] + " [Certain].")
    return out


def among(pack: dict) -> str:
    cmp, year = pack["comparison"], pack["comparison"]["year"]
    group, where = GROUP.get(cmp["peer_group"], (cmp["peer_group"], f"in {cmp['peer_group']}"))
    if cmp["status"] == "not compared":
        items = "".join(f"<li>{prose(r)}</li>" for r in not_compared_reasons(cmp["not_compared_because"], year))
        return ('<section class="card" id="among"><h2>Why it is not compared with the other councils</h2>'
                f'<ul>{items}</ul><p class="note">Its own figures are shown on this page as published '
                '<span class="tag">[Certain]</span>.</p></section>')
    o = cmp["others"]
    provisional = ""
    if cmp["status"] != "compared":
        provisional = ('<p class="flag">Provisional: this council is left out of the shared chart until a person '
                       'checks the items under Data check, so it is set against all the councils that chart shows '
                       'in its peer group <span class="tag">[Certain on the rules]</span>.</p>')
    return (
        '<section class="card" id="among"><h2>Where it sits among the other councils</h2>'
        f'<p class="note">Gross spend per household-year, {esc(year)}, against the {o["councils"]} other councils '
        f'shown {esc(where)}, unnamed. The band is the middle half of them and the line is their median. A figure '
        'far from the band may reflect spend on households the count does not cover, or spend classified '
        'differently, before any difference in price <span class="tag">[Likely]</span>.</p>'
        f'{provisional}{strip(cmp["gross_per_household"], o)}'
        f'<p>On these figures, its gross spend per household-year is {esc(cmp["position"])}: '
        f'{times(cmp["ratio_to_median_of_others"])} times their median, and {cmp["others_lower"]} of the '
        f'{o["councils"]} have a lower figure ({pct(cmp["share_of_others_lower"])}) '
        '<span class="tag">[Certain]</span>.</p>'
        f'<p class="note">The others: {prose(o["rule"][:1].lower() + o["rule"][1:])} Peer group: {esc(group)}.</p>'
        '</section>')


def questions(pack: dict) -> str:
    qs = pack["questions"]
    cmp = pack["comparison"]
    if qs:
        body = "<ol>" + "".join(f'<li><p>{prose(q["reason"])}</p><p>{esc(q["question"])}</p></li>' for q in qs) + "</ol>"
    elif cmp["status"] == "not compared":
        body = ('<p>No question beyond why it is not compared, above <span class="tag">[Certain on the rules]'
                '</span>.</p>')
    else:
        body = (f'<p>None under the rules used here: its gross spend per household-year is {esc(cmp["position"])}'
                ' <span class="tag">[Certain on the rules]</span>.</p>')
    return ('<section class="card questions" id="questions"><h2>Questions its figures raise</h2>'
            '<p class="note">Each gives the reasons the figure may be wrong first, then the question to ask. A '
            'question is a check for a person to make, never a finding <span class="tag">[Certain on the rule]'
            f'</span>.</p>{body}</section>')


def data_check(pack: dict) -> str:
    dc = pack["data_check"]
    items = "".join(f'<li><span class="kind">{esc(CHECK_KIND.get(i["kind"], i["kind"].capitalize()))}.</span> '
                    f'{prose(i["text"])}</li>' for i in dc["items"])
    return (f'<section class="card" id="check"><h2>Data check</h2><p>{prose(dc["note"])}</p>'
            + (f"<ul>{items}</ul>" if items else "") + "</section>")


def mix(pack: dict) -> str:
    m = pack["mix"]
    bars, rows = [], []
    for t in m["types"]:
        lines = []
        for share, cls, what in ((t["households_share"], "bar-hh", "households"), (t["spend_share"], "bar-sp", "spend")):
            width = 0.0 if share is None else max(0.0, float(share))
            lines.append(f'<span class="barline"><span class="bar {cls}" style="width: calc((100% - 3.5rem) * '
                         f'{width:.4f})" aria-hidden="true"></span><span>{pct(share)}<span class="visually-hidden">'
                         f' of {what}</span></span></span>')
        bars.append(f'<li><span class="t">{esc(t["type"])}</span><span class="bars">' + "".join(lines) + "</span></li>")
        rows.append(f'<tr><th scope="row">{esc(t["type"])}</th>'
                    f'<td class="num" data-label="Households, average and share"><span>{whole(t["households_average"])}'
                    f'<small>{pct(t["households_share"])}</small></span></td>'
                    f'<td class="num" data-label="Gross spend and share"><span>{money(t["gross_spend"])}'
                    f'<small>{pct(t["spend_share"])}</small></span></td>'
                    f'<td class="num" data-label="Gross per household-year">{money(t["gross_per_household"])}</td></tr>')
    flag = ""
    if pack["spend_on_types_without_households"]:
        flag = ('<p class="flag">More than a quarter of positive spend sits on types where this council reports '
                'fewer than one household on average <span class="tag">[Certain]</span>. Spend and households may be '
                'classified on different lines, so compare totals, not types <span class="tag">[Likely]</span>.</p>')
    return (
        f'<section class="card" id="mix"><h2>Where its households are, and where its money goes, {esc(m["year"])}</h2>'
        '<p class="note">Share of households by type of accommodation against share of accommodation spend on each '
        'line. Types cost different amounts, so the two shares differ anyway <span class="tag">[Likely]</span>. '
        'Households on a line with no spend, or spend on a line with almost no households, usually means spend is '
        f'classified on another line or held outside the TA lines <span class="tag">[Likely]</span>. {prose(m["note"])}'
        f'</p>{flag}<ul class="key"><li><span class="sw sw-hh"></span>Share of households</li>'
        '<li><span class="sw sw-sp"></span>Share of spend</li></ul>'
        f'<ul class="mix">{"".join(bars)}</ul>'
        f'<div class="scroll"><table class="stack"><caption>By type, {esc(m["year"])}</caption><thead><tr><th scope="col">Type</th>'
        '<th scope="col" class="num">Households, average<small>and share</small></th>'
        '<th scope="col" class="num">Gross spend<small>and share of positive spend</small></th>'
        '<th scope="col" class="num">Gross per household-year<small>where 50 households or more</small></th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div></section>')


def years(pack: dict) -> str:
    tr = pack["trend"]
    counts = tr["households_at_quarter_end"]
    by_year = {b["year"]: b for b in tr["by_year"]}
    spend = {s["year"]: s for s in tr["spend_by_year"]}
    ys = sorted(set(by_year) | set(spend))
    first = {y for y in ys if (by_year.get(y) or spend.get(y) or {}).get("first_release")}
    feeds: dict[str, list[str]] = {}
    for y in by_year:
        for q in snapshot_quarters(y):
            feeds.setdefault(q, []).append(y)
    top = max([c["households"] for c in counts if c["households"] is not None] or [0])
    rows = []
    for c in counts:
        n = c["households"]
        bar = "" if not n or not top else (f'<span class="bar bar-ct" style="width: {n / top * 100:.1f}%" '
                                           'aria-hidden="true"></span>')
        rows.append(f'<tr><th scope="row">{esc(c["quarter_end"])}</th><td class="num">'
                    f'{"no count published" if n is None else whole(n)}</td><td class="barcell">{bar}</td>'
                    f'<td>{esc(" and ".join(feeds.get(c["quarter"], [])))}</td></tr>')
    head = "".join(f'<th scope="col" class="num">{esc(y)}{"<small>first release</small>" if y in first else ""}</th>'
                   for y in ys)
    labels = {y: esc(y + (", first release" if y in first else "")) for y in ys}

    def row(label: str, src: dict, key: str, fmt) -> str:
        cells = "".join(f'<td class="num" data-label="{labels[y]}">{fmt(src[y][key]) if y in src else "not held"}</td>'
                        for y in ys)
        return f'<tr><th scope="row">{label}</th>{cells}</tr>'

    measures = [row("Households in TA, yearly average", by_year, "households_average", whole),
                row("Gross accommodation spend, lines 80 to 85", spend, "gross_lines_80_85", money),
                row("Net accommodation spend, lines 80 to 85", by_year, "net_accommodation_spend", money),
                row("Gross per household-year", by_year, "gross_per_household", money),
                row("Net per household-year", by_year, "net_per_household", money),
                row("TA administration, line 86, gross", spend, "gross_admin_line_86", money)]
    estimated = sorted(y for y, b in by_year.items() if b["households_estimated"])
    est = ""
    if len(estimated) == 1:
        est = f' The {estimated[0]} average is estimated: one of its five counts is missing <span class="tag">[Certain]</span>.'
    elif estimated:
        est = (f' The {" and ".join(estimated)} averages are estimated: one of the five counts behind each is missing '
               '<span class="tag">[Certain]</span>.')
    note_first = (f' {" and ".join(sorted(first))} is a first release of RO4; its figures will probably move at the '
                  'second release, and a council\'s own lines can move between releases <span class="tag">[Likely]'
                  '</span>.') if first else ""
    return (
        '<section class="card" id="years"><h2>Over the years held</h2>'
        '<p class="note">Households in TA at each quarter end, as MHCLG publishes them; council counts are as '
        f'submitted <span class="tag">[Certain]</span>. Each yearly average uses five of them.{est}</p>'
        '<div class="scroll"><table><caption>Households in TA at each quarter end</caption><thead><tr>'
        '<th scope="col">Quarter end</th><th scope="col" class="num">Households</th><th scope="col" class="barcol">'
        '<span class="visually-hidden">Bar</span></th><th scope="col">In the yearly average for</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        f'<p class="note">Spend is RO4 as published, in cash.{note_first}</p>'
        '<div class="scroll"><table class="stack"><caption>By financial year</caption><thead><tr><th scope="col">Measure</th>'
        f'{head}</tr></thead><tbody>{"".join(measures)}</tbody></table></div></section>')


def method(pack: dict) -> str:
    year = pack["comparison"]["year"]
    items = [
        "Households in TA: MHCLG's count of households in temporary accommodation at each quarter end (table TA1), "
        f"averaged over each financial year from its five counts (for {year}, {quarter_end(year, True)} to "
        f"{quarter_end(year, False)}), assuming a straight line between counts. A missing count is estimated between "
        "its neighbours or, for the first or last count, copied from the nearest one, and the average is marked as "
        "estimated [Certain on the method].",
        "Spend: council revenue outturn, form RO4, lines 80 to 85 for accommodation and line 86 for administration, "
        "published in thousands of pounds. Gross is total spend; net is after income such as housing benefit "
        "[Certain].",
        "Compared councils: at least four of the five counts, positive spend on lines 80 to 85 and at least 50 "
        "households on average. Peer groups: London (its 33 councils) and the rest of England [Certain on the rules].",
        "The others: the councils on the shared chart, in the market picture that is shared without council names, "
        "which shows each council it compares as an unnamed dot and leaves out those with a data check "
        "outstanding: a change of more than 40% "
        "from one quarter-end count to the next (counts held from March 2024 to March 2026; councils averaging at "
        "least 100 households), or nothing on lines 80 to 86 in 2024-25 or 2025-26 despite at least 100 households. "
        "Here they appear only as a count, a band and a median, and this council is never one of them [Certain on "
        "the rules].",
        "Rounding: this council's money to the nearest pound and its households to the nearest household; the "
        "others' quartiles and median to the nearest £10; ratios to two decimal places; shares to whole per cent, "
        "those by type adjusted so each set adds to 100; halves rounded up [Certain].",
    ]
    return ('<section class="card" id="method"><h2>How the figures are made</h2><ul>'
            + "".join(f"<li>{prose(i)}</li>" for i in items) + "</ul></section>")


def caveats(pack: dict) -> str:
    return ('<section class="card" id="caveats"><h2>What could make these numbers wrong</h2><ul>'
            + "".join(f"<li>{prose(c)}</li>" for c in pack["caveats"]) + "</ul></section>")


def sources(pack: dict) -> str:
    return ('<section class="card sources" id="sources"><h2>Sources and releases</h2><ul>'
            + "".join(f"<li>{prose(r)}</li>" for r in pack["release_notes"]) + "</ul><h3>Sources</h3><ul>"
            + "".join(f"<li>{s}</li>" for s in SOURCES) + "</ul></section>")


def render(pack: dict, build: Build) -> str:
    """The page for one council, as one HTML document with its CSS inline and no script."""
    c, cmp = pack["council"], pack["comparison"]
    name, year = c["name"], cmp["year"]
    group = GROUP.get(c["peer_group"], (c["peer_group"],))[0]
    built = f"Built on {build.date} from commit {build.commit}" + (" (with changes not yet committed)" if build.dirty else "")
    return (
        '<!doctype html>\n<html lang="en-GB">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; '
        'base-uri \'none\'; form-action \'none\'">\n'
        '<meta name="referrer" content="no-referrer">\n<meta name="robots" content="noindex, nofollow">\n'
        '<meta name="color-scheme" content="light dark">\n'
        f"<title>{esc(name)}: temporary accommodation, {esc(year)} (private)</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n<main>\n"
        f'<p class="private"><strong>Private.</strong> For the officers of {esc(name)} only. No other council is '
        "named on this page.</p>\n"
        f"<header><h1>{esc(name)}: temporary accommodation, {esc(year)}</h1>"
        f'<p class="meta">{esc(c["label"])} · Peer group: {esc(group)} · ONS code {esc(c["code"])} · '
        f"{esc(STATUS_SHORT.get(cmp['status'], cmp['status']).capitalize())}</p>"
        '<p class="lede">From MHCLG\'s published statistics: households in temporary accommodation (TA) at each '
        "quarter end, and the council's own spend on it. The other councils in its peer group are not named: they "
        "appear only as a count, a band and a median. A council far from the others is a question to ask, not a "
        "finding.</p></header>\n"
        f"{kpis(pack)}\n{among(pack)}\n"
        f'<div class="grid">{questions(pack)}{data_check(pack)}</div>\n'
        f"{mix(pack)}\n{years(pack)}\n"
        f'<div class="grid">{method(pack)}{caveats(pack)}</div>\n'
        f"{sources(pack)}\n"
        f'<footer><p>{esc(OGL_LINE)} Licence: <a href="{OGL_URL}" rel="license noopener noreferrer">{OGL_URL}</a></p>'
        f"<p>Private: for {esc(name)} only, and not for sharing beyond it. {esc(built)}.</p>"
        "<p>No other council is named or coded on this page; the others appear only as a count, a band and a median "
        '<span class="tag">[Certain: checked when the page was built]</span>. Figures are aggregates; nothing here '
        'identifies a household <span class="tag">[Certain]</span>.</p></footer>\n'
        "</main>\n</body>\n</html>\n")


# ------------------------------------------------------------------ checks

ONS_CODE = re.compile(r"(?<![A-Za-z0-9])[EWSNK]\d{8}(?![A-Za-z0-9])")
COMMENT = re.compile(r"<!--.*?-->", re.S)
STYLE = re.compile(r"<style\b.*?</style\s*>", re.S | re.I)
TAGS = re.compile(r"<[^>]*>")
SPACE = re.compile(r"\s+")
LOADS = re.compile(r"<\s*(script|link|img|iframe|frame|object|embed|video|audio|source|picture|base)\b", re.I)


def trie(words: list[str]) -> str:
    """One regular expression for many literal strings, longest first at every branch."""
    root: dict = {}
    for w in words:
        node = root
        for ch in w:
            node = node.setdefault(ch, {})
        node[""] = {}

    def emit(node: dict) -> str:
        end = "" in node
        branches = [re.escape(ch) + emit(sub) for ch, sub in sorted(node.items()) if ch]
        if not branches:
            return ""
        if len(branches) == 1 and not end:
            return branches[0]
        return "(?:" + "|".join(branches) + ")" + ("?" if end else "")
    return emit(root)


@dataclass
class Councils:
    """Every local authority's names and codes in the tables the packs are built from, by ONS code
    after the 1 April 2025 recodes: TA1 councils, and every RO4 authority but the England row."""
    by_code: dict[str, set[str]]
    owner: dict[str, str]
    pattern: re.Pattern

    @classmethod
    def load(cls, tables: Path = TABLES) -> "Councils":
        import pandas as pd
        ta1 = pd.read_csv(tables / "ta1_wide.csv", usecols=["code", "name", "level"])
        ro4 = pd.read_csv(tables / "ro4_wide.csv", usecols=["ons_code", "la_name", "e_code", "class"])
        by_code: dict[str, set[str]] = {}
        ta1 = ta1[ta1.level == "council"]
        for code, name in zip(ta1.code, ta1.name):
            by_code.setdefault(RECODES.get(code, code), set()).update({code, name})
        ro4 = ro4[ro4["class"] != "Eng"]
        for code, name, ecode in zip(ro4.ons_code, ro4.la_name, ro4.e_code):
            by_code.setdefault(RECODES.get(code, code), set()).update({code, name, ecode})
        by_code = {k: {SPACE.sub(" ", v).strip() for v in vs if isinstance(v, str) and len(v.strip()) > 3}
                   for k, vs in by_code.items() if isinstance(k, str)}
        owner = {v: k for k, vs in by_code.items() for v in vs}
        words = sorted(owner, key=lambda s: (-len(s), s))
        pattern = re.compile(r"(?<![A-Za-z0-9])" + trie(words) + r"(?![A-Za-z0-9])")
        return cls(by_code, owner, pattern)

    def others_in(self, text: str, code: str) -> set[str]:
        """The other councils named or coded in text, by ONS code. Matches are leftmost and longest,
        so this council's own name never hides another council's name, nor counts as one."""
        found = set()
        for m in self.pattern.finditer(text):
            k = self.owner.get(m.group(0))
            if k is not None and k != code:
                found.add(k)
        return found


def texts(page: str) -> tuple[str, str]:
    """The page as its source reads and as its text reads, entities decoded and white space collapsed."""
    source = SPACE.sub(" ", html.unescape(page))
    visible = SPACE.sub(" ", html.unescape(TAGS.sub(" ", STYLE.sub(" ", COMMENT.sub(" ", page)))))
    return source, visible


def check_page(page: str, code: str, name: str, councils: Councils) -> list[str]:
    """Why a page may not be written; empty when it may."""
    problems = []
    source, visible = texts(page)
    others = councils.others_in(source, code) | councils.others_in(visible, code)
    if others:
        problems.append("names another council: " + ", ".join(sorted(others)))
    codes = {m.group(0) for t in (source, visible) for m in ONS_CODE.finditer(t)} - {code}
    if codes:
        problems.append("carries an ONS code other than its own: " + ", ".join(sorted(codes)))
    if OGL_LINE not in visible:
        problems.append("the Open Government Licence line is missing")
    if not re.search(r'<a\s[^>]*\bhref="' + re.escape(OGL_URL) + '"', page):
        problems.append("the link to the Open Government Licence is missing")
    if SPACE.sub(" ", name).strip() not in visible:
        problems.append("does not name its own council")
    if "\u2014" in page or "\u2013" in page:
        problems.append("has an em or en dash")
    loads = {m.group(1).lower() for m in LOADS.finditer(page)}
    tags = TAGS.findall(STYLE.sub(" ", page))
    if any(re.search(r"\s(?:src|srcset)\s*=|\son[a-z]+\s*=|javascript:", t, re.I) for t in tags):
        loads.add("an attribute that loads or runs something")
    if re.search(r"url\s*\(|@import|@font-face", page, re.I):
        loads.add("CSS that loads something")
    if loads:
        problems.append("loads or runs something: " + ", ".join(sorted(loads)))
    return problems


# ------------------------------------------------------------------ git and the build

def run_git(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def folder_problem(out: Path) -> str:
    """Why `out` may not take council pages, or '' when it may: git must ignore it, with no tracked
    file in it, in the repository that holds it; or it must sit outside any git repository."""
    out = out.resolve()
    anchor = out
    while not anchor.exists():
        anchor = anchor.parent
    if not anchor.is_dir():
        return f"{anchor} is a file, not a folder"
    try:
        top = run_git("rev-parse", "--show-toplevel", cwd=anchor)
    except OSError:
        return "git cannot be run, so whether git ignores the folder cannot be checked"
    if top.returncode != 0:
        if "not a git repository" in top.stderr:
            return ""            # outside any repository: nothing written here can be committed
        return f"git cannot check the folder: {top.stderr.strip()}"
    repo = Path(top.stdout.strip())
    ignored = run_git("check-ignore", "-q", str(out / "page.html"), cwd=repo)
    if ignored.returncode == 1:
        return f"{out} is not gitignored in {repo}, so a page written there could be committed"
    if ignored.returncode != 0:
        return f"git cannot check the folder: {ignored.stderr.strip()}"
    if run_git("ls-files", "--", str(out), cwd=repo).stdout.strip():
        return f"{out} holds files that git tracks"
    return ""


def build_info() -> Build:
    """Today, the commit the inputs come from, and whether any input differs from that commit."""
    date = long_date(dt.date.today())
    try:
        head = run_git("rev-parse", "--short", "HEAD")
    except OSError:
        return Build(date, "unknown", True)
    if head.returncode != 0:
        return Build(date, "unknown", True)
    dirty = False
    for p in INPUTS:
        tracked = run_git("ls-files", "--error-unmatch", p).returncode == 0
        if not tracked or run_git("diff", "--quiet", "HEAD", "--", p).returncode != 0:
            dirty = True
    return Build(date, head.stdout.strip(), dirty)


@dataclass
class Page:
    code: str
    status: str
    html: str
    problems: list[str]


def build_pages(packs: list[Path], councils: Councils, build: Build) -> list[Page]:
    """Every page in memory, each with the reasons it may not be written."""
    pages = []
    for path in packs:
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
            code, name = pack["council"]["code"], pack["council"]["name"]
            status = pack["comparison"]["status"]
            if code != path.stem:
                raise ValueError(f"the pack is for {code}, not {path.stem}")
            if pack["pack"].get("private") is not True:
                raise ValueError("the pack is not marked private")
            page = render(pack, build)
        except (OSError, ValueError, KeyError, TypeError, IndexError) as e:
            pages.append(Page(path.stem, "unreadable", "", [f"the pack cannot be rendered: {type(e).__name__}: {e}"]))
            continue
        pages.append(Page(code, status, page, check_page(page, code, name, councils)))
    return pages


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="build and check every page in memory; write nothing")
    ap.add_argument("--only", action="append", metavar="CODE", help="build only this council's page (repeatable)")
    ap.add_argument("--out", type=Path, default=OUT, help="folder for the pages (default reports/private/councils)")
    ap.add_argument("--packs", type=Path, default=PACKS, help="folder of packs (default data/private/packs)")
    args = ap.parse_args(argv)
    if not args.check:
        problem = folder_problem(args.out)
        if problem:
            raise SystemExit(f"not writing any page: {problem}")
    packs = sorted(args.packs.glob("*.json")) if args.packs.is_dir() else []
    if not packs:
        raise SystemExit(f"no packs in {args.packs}: build them first with python scripts/build_packs.py")
    if args.only:
        wanted = {RECODES.get(c.strip(), c.strip()) for c in args.only}
        packs = [p for p in packs if p.stem in wanted]
        missing = sorted(wanted - {p.stem for p in packs})
        if missing:
            raise SystemExit(f"no pack for {', '.join(missing)} in {args.packs}")
    build = build_info()
    pages = build_pages(packs, Councils.load(), build)
    good = [p for p in pages if not p.problems]
    bad = [p for p in pages if p.problems]
    status = Counter(STATUS_SHORT.get(p.status, p.status) for p in good)
    if not args.check:
        out = args.out.resolve()
        out.mkdir(parents=True, exist_ok=True)
        for p in good:
            (out / f"{p.code}.html").write_text(p.html, encoding="utf-8")
        where = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
        print(f"wrote {len(good)} private council page{'s' * (len(good) != 1)} to {where}, from commit "
              f"{build.commit}{' (uncommitted changes)' if build.dirty else ''}: "
              + ", ".join(f"{n} {s}" for s, n in sorted(status.items())))
    else:
        print(f"checked {len(pages)} page{'s' * (len(pages) != 1)} in memory and wrote nothing: {len(good)} pass")
    if good:
        print("Each passes the checks: no other council named or coded, no ONS code but its own, the licence line "
              "and link present.")
    if bad:
        print(f"{'failed' if args.check else 'not written'}, {len(bad)} page{'s' * (len(bad) != 1)}:")
        for p in bad:
            print(f"  {p.code}.html: " + "; ".join(p.problems))
        return 1
    if not args.check:
        print("Private: each page names its own council only. Before a page is sent, and only to the council it "
              "names: " + " ".join(RELEASE_GATE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
