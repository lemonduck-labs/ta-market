"""Parsers for MHCLG temporary accommodation (TA) statistics.

Two published sources, both aggregate statistics from the Ministry of Housing,
Communities and Local Government (MHCLG) under the Open Government Licence v3.0:

* Statutory homelessness detailed local authority tables (H-CLIC), sheet TA1:
  households in TA at the end of each quarter, by type of accommodation.
* Local authority revenue outturn, form RO4 (housing services): TA spend by
  council and financial year. From 2020-21 the TA lines are 80 to 86.

The spreadsheets are laid out for people rather than machines: titles and notes
above the table, merged headers over two or three rows, footnote markers and
'..' for missing values. The parsers therefore find the table from the data,
not from fixed row numbers:

1. the code column is the column holding the most ONS local authority codes
   (E06, E07, E08, E09);
2. the first row with an ONS code starts the data;
3. the header block is the run of text rows just above it (blank rows and
   uncoded aggregate rows such as England or a region are skipped), with
   merged group headers carried across to the columns beneath them;
4. columns are mapped to accommodation types or RO4 lines by keyword.

The mapping that was used is kept in ``DataFrame.attrs`` so it can be checked
against the real files (scripts/build_tidy.py prints it). Nothing here handles
household-level or personal data.

Tidy outputs (first five columns as agreed for the build, then provenance):

* ta_households: la_code, la_name, quarter, accommodation_type, households,
  source_file
* ta_spend: la_code, la_name, year, line, gbp, measure, source_file
"""

from __future__ import annotations

import os
import re
import warnings
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Schemas and vocabulary
# ---------------------------------------------------------------------------

TA_HOUSEHOLDS_COLUMNS = [
    "la_code", "la_name", "quarter", "accommodation_type", "households", "source_file",
]
TA_SPEND_COLUMNS = ["la_code", "la_name", "year", "line", "gbp", "measure", "source_file"]

#: Accommodation types shared by the household counts (TA1) and the spend lines (RO4).
ACCOMMODATION_TYPES = (
    "bed_and_breakfast",
    "nightly_paid_self_contained",
    "hostels",
    "private_sector_leased",
    "la_ha_stock",
    "other",
)
#: Values of ``accommodation_type`` in ta_households ("total" is all households in TA).
TA1_TYPES = ACCOMMODATION_TYPES + ("total",)
#: Values of ``line`` in ta_spend ("ta_admin" is RO4 line 86, TA administration).
SPEND_LINES = ACCOMMODATION_TYPES + ("ta_admin",)

#: RO4 TA lines from 2020-21, as named in MHCLG's 2021-22 final outturn technical notes.
RO4_TA_LINES: dict[int, tuple[str, str]] = {
    80: ("nightly_paid_self_contained",
         "Nightly paid, privately managed accommodation, self-contained"),
    81: ("private_sector_leased",
         "Private sector accommodation leased by authority or by a registered provider"),
    82: ("hostels", "Hostels (including reception centres, emergency units and refuges)"),
    83: ("bed_and_breakfast", "Bed and breakfast hotels (including shared annexes)"),
    84: ("la_ha_stock", "Local authority or housing association (LA/HA) stock"),
    85: ("other",
         "Any other type of temporary accommodation (including private landlord and not known)"),
    86: ("ta_admin", "Temporary accommodation administration"),
}

#: RO4 lines up to 2019-20 and the 2020-21 line each maps to, per the same notes.
#: Old line 39 also held annexes with shared facilities, which moved to B&B (83).
#: Names are None where the notes give only the number. Old lines 47, 49 and 50
#: (homelessness administration, prevention and support) have no TA equivalent.
RO4_TA_LINES_TO_2019_20: dict[int, tuple[str, str | None]] = {
    39: ("nightly_paid_self_contained", "Other nightly paid, privately managed accommodation"),
    40: ("private_sector_leased", "Private managed accommodation leased by the authority"),
    41: ("hostels", None),
    42: ("bed_and_breakfast", None),
    43: ("private_sector_leased", "Private managed accommodation leased by RSLs"),
    44: ("other", None),
    45: ("la_ha_stock", None),
    46: ("other", None),
    48: ("la_ha_stock", None),
}

#: Revenue outturn column measures. Shelter's GBP 2.842bn uses total expenditure.
RO_MEASURES = (
    "total_expenditure",
    "net_current_expenditure",
    "total_income",
    "other_income",
    "sales_fees_and_charges",
    "running_expenses",
    "employees",
)

HOUSING_AUTHORITY_CODE = re.compile(r"^E0[6-9]\d{6}$")  # unitary, district, met district, London borough
GSS_CODE = re.compile(r"^[EKNSW]\d{8}$")
LGF_CODE = re.compile(r"^E\d{4}$")  # MHCLG local government finance code, for example E0701

MISSING_MARKERS = frozenset({
    "..", ".", "-", "\u2013", "x", "[x]", "[c]", "[z]", "[u]", "[w]", "[low]", "*", ":",
    "n/a", "na", "nan", "none", "not set", "not available",
})

ENGINE_ENV = "TAMARKET_EXCEL_ENGINE"


class TaMarketWarning(UserWarning):
    """Something in a source file needs a person to look at it."""


# ---------------------------------------------------------------------------
# Cell helpers
# ---------------------------------------------------------------------------

_NUMBER = re.compile(r"^[-+]?\(?\u00a3?\d[\d,]*(?:\.\d+)?\)?$")
_FOOTNOTE = re.compile(r"\[(?:note|notes|footnote)[^\]]*\]|\[[a-z]\]|\(\s*note\s*\d+\s*\)", re.I)
_CODE_AT_START = re.compile(r"^([EKNSW]\d{8}|E\d{4})(?![\dA-Za-z])")


def _text(value) -> str:
    """Cell value as clean text ('' for empty)."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    s = str(value).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", s).strip()


def _is_number_text(s: str) -> bool:
    return bool(s) and (bool(_NUMBER.match(s)) or s.lower() in MISSING_MARKERS)


def _to_number(value) -> float:
    """Number from a cell; NaN for blanks and missing markers such as '..'."""
    if isinstance(value, bool):
        return float("nan")
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    s = _text(value)
    if not s or s.lower() in MISSING_MARKERS:
        return float("nan")
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "").replace("\u00a3", "")
    try:
        number = float(s)
    except ValueError:
        return float("nan")
    return -number if negative else number


def _norm(label: str) -> str:
    """Lower-case label without footnote markers, for keyword matching."""
    s = _FOOTNOTE.sub(" ", label).lower()
    s = s.replace("&", " and ").replace("\u2019", "'")
    return re.sub(r"\s+", " ", s).strip()


def _clean_name(name: str) -> str:
    return re.sub(r"\s*\*+$", "", _FOOTNOTE.sub("", name)).strip()


def _code_of(s: str) -> str:
    m = _CODE_AT_START.match(s)
    return m.group(1) if m else ""


def _excel_engine(path: Path, engine: str | None) -> str | None:
    if engine:
        return engine
    env = os.environ.get(ENGINE_ENV, "").strip()
    if env:
        return env
    suffix = path.suffix.lower()
    if suffix == ".ods":
        return "odf"
    if suffix in {".xlsx", ".xlsm"}:
        return "openpyxl"
    return None


def _open_workbook(path: Path, engine: str | None) -> pd.ExcelFile:
    return pd.ExcelFile(path, engine=_excel_engine(path, engine))


def _parse(xl: pd.ExcelFile, sheet) -> pd.DataFrame:
    raw = xl.parse(sheet, header=None, dtype=object)
    raw = raw.dropna(axis=1, how="all")
    raw.index = range(len(raw))
    return raw


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_QUARTER_OF_END_MONTH = {3: 1, 6: 2, 9: 3, 12: 4}
_MONTH_NAMES = "|".join(_MONTHS)
_DAY_MONTH_YEAR = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_NAMES})\s+(20\d{{2}})\b", re.I)
_MONTH_TO_MONTH = re.compile(rf"\b({_MONTH_NAMES})\s+to\s+({_MONTH_NAMES})\s+(20\d{{2}})\b", re.I)
_YYYYMM = re.compile(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(?!\d)")
_FY_LONG = re.compile(r"(?<!\d)(20\d{2})[-_ ]?(20\d{2})(?!\d)")
_FY_SHORT = re.compile(r"(?<!\d)(20\d{2})[-_ /](\d{2})(?!\d)")


def _fy_label(start: int) -> str:
    return f"{start}-{(start + 1) % 100:02d}"


def year_from_text(text: str) -> str | None:
    """Financial year such as '2024-25' from text like 'RO4_LA_Data_2024-25_data_by_LA.ods'."""
    s = str(text)
    for m in _FY_LONG.finditer(s):
        a, b = int(m.group(1)), int(m.group(2))
        if b == a + 1:
            return _fy_label(a)
    for m in _FY_SHORT.finditer(s):
        a, b = int(m.group(1)), int(m.group(2))
        if b == (a + 1) % 100:
            return _fy_label(a)
    return None


def quarter_from_text(text: str) -> str | None:
    """Calendar quarter of a TA snapshot, as 'YYYY-Qn', from a file name or title.

    Tries, in order: an explicit date ('31 March 2026'), a period ('January to
    March 2026'), a YYYYMM stamp ('..._202603.ods'), then a financial year
    ('..._2024-2025...'), which is read as the 31 March snapshot that ends it.
    """
    s = str(text)
    for m in _DAY_MONTH_YEAR.finditer(s):
        month = _MONTHS[m.group(2).lower()]
        if month in _QUARTER_OF_END_MONTH:
            return f"{m.group(3)}-Q{_QUARTER_OF_END_MONTH[month]}"
    for m in _MONTH_TO_MONTH.finditer(s):
        month = _MONTHS[m.group(2).lower()]
        if month in _QUARTER_OF_END_MONTH:
            return f"{m.group(3)}-Q{_QUARTER_OF_END_MONTH[month]}"
    for m in _YYYYMM.finditer(s):
        month = int(m.group(2))
        if month in _QUARTER_OF_END_MONTH:
            return f"{m.group(1)}-Q{_QUARTER_OF_END_MONTH[month]}"
    fy = year_from_text(s)
    if fy:
        return f"{int(fy[:4]) + 1}-Q1"
    return None


def financial_year_of_quarter(quarter: str) -> str:
    """'2025-Q2' (April to June 2025) -> '2025-26'; '2026-Q1' -> '2025-26'."""
    m = re.fullmatch(r"(20\d{2})-Q([1-4])", str(quarter))
    if not m:
        raise ValueError(f"not a quarter label like '2026-Q1': {quarter!r}")
    year, q = int(m.group(1)), int(m.group(2))
    return _fy_label(year - 1 if q == 1 else year)


def _fy_from_year_ending(value) -> str | None:
    """'201803' or 201803 (year ending March 2018) -> '2017-18'."""
    m = re.match(r"^(20\d{2})(\d{2})", _text(value))
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    return _fy_label(year - 1 if month <= 3 else year)


# ---------------------------------------------------------------------------
# Locating the table in a sheet
# ---------------------------------------------------------------------------

_HH_EXCLUDE = re.compile(
    r"\bchild|\b6 weeks\b|\bsix weeks\b|\bpending\b|per 1,?000|per thousand|\brate\b|%|"
    r"\bpercent|\bproportion\b|\bshare\b|\banother\b|out of area|"
    r"other (?:local authority|la) district|no accommodation|homeless at home|"
    r"\badult|\bsingle\b|\bcouple\b"
)
_HH_TYPE_PATTERNS = [
    ("bed_and_breakfast", re.compile(r"bed and breakfast|\bb and b\b")),
    ("nightly_paid_self_contained", re.compile(r"nightly[- ]paid")),
    ("hostels", re.compile(r"\bhostels?\b")),
    ("private_sector_leased", re.compile(r"\bleas(?:e|ed|ing)\b|\bpsl\b")),
    ("la_ha_stock", re.compile(
        r"\bla ?/ ?ha\b|local authority or housing association|\bstock\b|"
        r"social (?:housing|provider|landlord)")),
    ("other", re.compile(
        r"\bany other\b|(?:^|\| )other\b|\bother type\b|\bother (?:temporary )?accommodation\b")),
    ("total", re.compile(
        r"\btotal\b|\ball (?:types|households|temporary accommodation)\b|"
        r"households in (?:ta|temporary accommodation)")),
]
_RO4_LINE_PATTERNS = [
    ("ta_admin", re.compile(r"temporary accommodation[\s:,|\-\u2013]*administration|\bta administration")),
    ("nightly_paid_self_contained", re.compile(r"nightly[- ]paid")),
    ("private_sector_leased", re.compile(r"\bleased\b")),
    ("hostels", re.compile(r"\bhostels?\b")),
    ("bed_and_breakfast", re.compile(r"bed and breakfast|\bb and b\b")),
    ("la_ha_stock", re.compile(
        r"\bla ?/ ?ha\)? stock|local authority or housing association|own stock|\brsl stock|"
        r"registered (?:social landlord|provider) stock")),
    ("other", re.compile(
        r"any other type of (?:temporary )?accommodation|other temporary accommodation|"
        r"private sector landlord")),
]
_RO_MEASURE_PATTERNS = [
    ("net_current_expenditure", re.compile(r"net current expenditure")),
    ("total_expenditure", re.compile(r"total expenditure|gross expenditure")),
    ("total_income", re.compile(r"total income")),
    ("other_income", re.compile(r"other income")),
    ("sales_fees_and_charges", re.compile(r"sales,? fees")),
    ("running_expenses", re.compile(r"running expenses")),
    ("employees", re.compile(r"\bemployees?\b")),
]
# A header label that names its own column, so a group header to its left must
# not be carried across onto it.
_SELF_DESCRIPTIVE = re.compile(
    r"bed and breakfast|\bb and b\b|nightly[- ]paid|\bhostels?\b|\bleas(?:e|ed|ing)\b|\bpsl\b|"
    r"\bla ?/ ?ha\b|local authority or housing association|\bstock\b|\bany other\b|^other\b|"
    r"temporary accommodation administration|total number|households in (?:ta|temporary accommodation)"
)


@dataclass
class TableLayout:
    """Where the table sits in a sheet (0-based row and column labels)."""

    sheet: str
    code_col: object
    name_col: object | None
    header_rows: list[int]
    data_rows: list[int]
    labels: dict = field(default_factory=dict)
    code_kind: str = "ons"

    def describe(self) -> str:
        rows = ", ".join(str(r + 1) for r in self.header_rows) or "none"
        return (f"sheet {self.sheet!r}: header rows {rows} (1-based), first data row "
                f"{self.data_rows[0] + 1 if self.data_rows else '-'}, {len(self.data_rows)} coded rows, "
                f"code column {self.code_col}, name column {self.name_col}")


def locate_table(raw: pd.DataFrame, sheet: str = "", max_header_rows: int = 6,
                 code_kind: str = "ons") -> TableLayout | None:
    """Find the code column, the coded data rows and the header block of a sheet.

    ``raw`` is the sheet read with ``header=None``. ``code_kind`` is 'ons' for
    ONS codes (E06000001) or 'lgf' for MHCLG finance codes (E0701). Returns
    None when no local authority codes are present.
    """
    text = raw.map(_text)
    codes = text.map(_code_of)
    pattern = HOUSING_AUTHORITY_CODE if code_kind == "ons" else LGF_CODE
    counts = {c: int(codes[c].map(lambda s: bool(pattern.match(s))).sum()) for c in codes.columns}
    if not counts or max(counts.values()) == 0:
        return None
    code_col = max(counts, key=counts.get)
    row_pattern = GSS_CODE if code_kind == "ons" else LGF_CODE
    coded = codes[code_col].map(lambda s: bool(row_pattern.match(s)))
    data_rows = [int(r) for r in coded[coded].index]
    first = data_rows[0]

    header_rows: list[int] = []
    started = False
    for r in range(first - 1, -1, -1):
        cells = [v for v in text.loc[r].tolist() if v]
        if not cells:
            if started:
                break
            continue
        numeric = sum(_is_number_text(v) for v in cells)
        data_like = numeric >= 2 and numeric >= 0.5 * len(cells)
        if data_like:
            if started:
                header_rows.append(r)  # a row of line numbers inside the header block
            continue  # uncoded aggregate rows (England, regions) above the coded rows
        if len(cells) < 2:
            break  # a title, units or note line
        header_rows.append(r)
        started = True
        if len(header_rows) >= max_header_rows:
            break
    header_rows.sort()

    name_col = _find_name_column(text, code_col, data_rows, header_rows)
    labels = _header_labels(text, header_rows, exclude={code_col, name_col})
    return TableLayout(sheet=str(sheet), code_col=code_col, name_col=name_col,
                       header_rows=header_rows, data_rows=data_rows, labels=labels,
                       code_kind=code_kind)


def _find_name_column(text: pd.DataFrame, code_col, data_rows: list[int],
                      header_rows: list[int]):
    best, best_score = None, None
    columns = list(text.columns)
    code_pos = columns.index(code_col)
    for pos, c in enumerate(columns):
        if c == code_col:
            continue
        values = text.loc[data_rows, c]
        values = values[values != ""]
        if len(values) < 0.5 * len(data_rows):
            continue
        texty = values[~values.map(_is_number_text)]
        if len(texty) < 0.8 * len(values) or texty.map(_code_of).astype(bool).mean() > 0.5:
            continue
        header = _norm(" ".join(text.loc[header_rows, c])) if header_rows else ""
        named = bool(re.search(r"\bname\b|authority|\barea\b|\bcouncil\b", header))
        regional = bool(re.search(r"\bregion|\bclass\b|\btype\b|\bcode\b", header))
        score = (named and not regional, not regional, -abs(pos - code_pos), pos > code_pos)
        if best_score is None or score > best_score:
            best, best_score = c, score
    return best


def _header_labels(text: pd.DataFrame, header_rows: list[int], exclude: set) -> dict:
    """Combined header label per column, carrying merged group headers across."""
    if not header_rows:
        return {c: "" for c in text.columns if c not in exclude}
    grid = text.loc[header_rows].copy()
    bottom = grid.loc[header_rows[-1]]
    for r in header_rows[:-1]:
        carry = ""
        for c in grid.columns:
            if c in exclude:
                carry = ""
                continue
            value = grid.at[r, c]
            if value:
                carry = value
                continue
            if not carry:
                continue
            own = _norm(bottom[c])
            if not own or not _SELF_DESCRIPTIVE.search(own):
                grid.at[r, c] = carry  # generic sub-header under a merged group header
            elif _HH_EXCLUDE.search(_norm(carry)):
                grid.at[r, c] = carry  # a qualifier such as 'households with children'
            else:
                carry = ""  # the group has ended
    labels = {}
    for c in grid.columns:
        if c in exclude:
            continue
        parts = [v for v in grid[c].tolist() if v]
        labels[c] = " | ".join(dict.fromkeys(parts))
    return labels


def _classify_household_label(label: str) -> str | None:
    s = _norm(label)
    if not s or _HH_EXCLUDE.search(s):
        return None
    for key, pattern in _HH_TYPE_PATTERNS:
        if pattern.search(s):
            return key
    return None


def _classify_ro4_label(label: str) -> tuple[str | None, str | None]:
    s = _norm(label)
    line = next((k for k, p in _RO4_LINE_PATTERNS if p.search(s)), None)
    if line is None:
        return None, None
    measure = next((k for k, p in _RO_MEASURE_PATTERNS if p.search(s)), None)
    return line, measure


def _title_text(raw: pd.DataFrame, layout: TableLayout | None, rows: int = 12) -> str:
    stop = layout.header_rows[0] if layout and layout.header_rows else min(rows, len(raw))
    return " ".join(_text(v) for v in raw.iloc[:max(stop, 1)].to_numpy().ravel() if _text(v))


def _find_sheet(names: Sequence[str], wanted: str) -> str:
    for n in names:
        if str(n).strip().lower() == wanted.lower():
            return n
    rx = re.compile(rf"(?<![a-z0-9]){re.escape(wanted.lower())}(?![a-z0-9])")
    for n in names:
        if rx.search(str(n).strip().lower()):
            return n
    raise ValueError(f"no sheet called {wanted!r}; sheets are: {', '.join(map(str, names))}")


def _keep_code(code: str, include_aggregates: bool) -> bool:
    return bool(HOUSING_AUTHORITY_CODE.match(code)) or (include_aggregates and bool(code))


def _token_counts(values: Iterable) -> dict:
    counts = Counter()
    for v in values:
        s = _text(v)
        if s and not _NUMBER.match(s):
            counts[s] += 1
    return dict(counts)


# ---------------------------------------------------------------------------
# Households in TA (H-CLIC detailed local authority tables, sheet TA1)
# ---------------------------------------------------------------------------

def read_ta_households(path, quarter: str | None = None, sheet: str | None = None,
                       engine: str | None = None, include_aggregates: bool = False) -> pd.DataFrame:
    """Households in TA by council and accommodation type from one detailed LA file.

    Parameters
    ----------
    path : file such as Statutory_Homelessness_Detailed_Local_Authority_Data_202603.ods
    quarter : 'YYYY-Qn' of the snapshot; read from the file name or sheet title if omitted
    sheet : sheet to read; defaults to the sheet named TA1
    engine : pandas Excel engine; defaults to odf for .ods and openpyxl for .xlsx
        (or the TAMARKET_EXCEL_ENGINE environment variable, for example 'calamine')
    include_aggregates : keep coded rows that are not housing authorities
        (England E92, regions E12); LA rows only by default

    Returns a long table with columns TA_HOUSEHOLDS_COLUMNS. Missing values
    ('..') are NaN. ``attrs`` holds the layout and column mapping used.
    """
    path = Path(path)
    xl = _open_workbook(path, engine)
    sheet_name = sheet if sheet is not None else _find_sheet(xl.sheet_names, "TA1")
    raw = _parse(xl, sheet_name)
    layout = locate_table(raw, sheet_name)
    if layout is None:
        raise ValueError(f"{path.name}: no ONS local authority codes found in sheet {sheet_name!r}")
    q = quarter or quarter_from_text(path.name) or quarter_from_text(_title_text(raw, layout))
    if q is None:
        raise ValueError(f"{path.name}: cannot tell the quarter; pass quarter='YYYY-Qn'")

    found: dict[str, list] = {}
    for c, label in layout.labels.items():
        key = _classify_household_label(label)
        if key:
            found.setdefault(key, []).append(c)
    if not any(k in found for k in ACCOMMODATION_TYPES):
        raise ValueError(
            f"{path.name}: no accommodation type columns recognised in {layout.describe()}; "
            f"header labels were: {list(layout.labels.values())[:20]}")
    column_map = {}
    for key in TA1_TYPES:
        cols = found.get(key, [])
        if not cols:
            warnings.warn(f"{path.name}: no column found for {key!r}", TaMarketWarning, stacklevel=2)
            continue
        if len(cols) > 1:
            warnings.warn(
                f"{path.name}: {len(cols)} columns look like {key!r}; using the first "
                f"({layout.labels[cols[0]]!r}), not {[layout.labels[c] for c in cols[1:]]}",
                TaMarketWarning, stacklevel=2)
        column_map[key] = cols[0]

    rows = []
    tokens: Counter = Counter()
    for r in layout.data_rows:
        code = _code_of(_text(raw.at[r, layout.code_col]))
        if not _keep_code(code, include_aggregates):
            continue
        name = _clean_name(_text(raw.at[r, layout.name_col])) if layout.name_col is not None else ""
        for key, c in column_map.items():
            value = raw.at[r, c]
            tokens.update(_token_counts([value]))
            rows.append((code, name, q, key, _to_number(value)))
    out = pd.DataFrame(rows, columns=TA_HOUSEHOLDS_COLUMNS[:-1])
    out["source_file"] = path.name
    out = out.drop_duplicates().reset_index(drop=True)
    repeated = out[out.duplicated(["la_code", "accommodation_type"], keep=False)]["la_code"].unique()
    if len(repeated):
        warnings.warn(f"{path.name}: councils listed more than once with different values: "
                      f"{list(repeated)[:10]}", TaMarketWarning, stacklevel=2)
    out.attrs.update({
        "source_file": path.name,
        "layout": layout.describe(),
        "column_map": {k: layout.labels[c] for k, c in column_map.items()},
        "non_numeric_values": dict(tokens),
    })
    return out


def validate_ta_households(ta_households: pd.DataFrame, tolerance: float = 0.0) -> pd.DataFrame:
    """Check that the six accommodation types add up to the total, per council and quarter.

    A mismatch usually means a column was mapped wrongly, or that the total
    includes households the types do not cover. Returns one row per council and
    quarter with total, sum_of_types, difference and ok (NaN rows are not ok).
    """
    wide = (ta_households.groupby(["la_code", "quarter", "accommodation_type"])["households"]
            .first().unstack())
    types = [t for t in ACCOMMODATION_TYPES if t in wide.columns]
    total = wide["total"] if "total" in wide.columns else pd.Series(np.nan, index=wide.index)
    out = pd.DataFrame({
        "total": total,
        "sum_of_types": wide[types].sum(axis=1, min_count=len(types)) if types else np.nan,
    })
    out["difference"] = out["total"] - out["sum_of_types"]
    out["ok"] = out["difference"].abs() <= tolerance
    return out.reset_index()


# ---------------------------------------------------------------------------
# TA spend (revenue outturn RO4, one file per financial year)
# ---------------------------------------------------------------------------

def read_ta_spend(path, year: str | None = None, measure: str = "total_expenditure",
                  sheet: str | None = None, engine: str | None = None,
                  include_aggregates: bool = False, units_gbp: float = 1000.0) -> pd.DataFrame:
    """TA spend by council and RO4 line from one revenue outturn RO4 'data by LA' file.

    Parameters
    ----------
    path : file such as RO4_LA_Data_2024-25_data_by_LA.ods
    year : financial year such as '2024-25'; read from the file name if omitted
    measure : one of RO_MEASURES; 'total_expenditure' (gross, the measure behind
        Shelter's GBP 2.842bn) or 'net_current_expenditure' (after income such as
        housing benefit and rents)
    sheet : sheet to read; by default every sheet is tried and the one with the
        most coded rows and recognisable TA columns is used
    include_aggregates : keep coded rows that are not housing authorities
        (counties, England and class totals where coded)
    units_gbp : pounds per unit in the file (RO values are in GBP thousand)

    Returns a long table with columns TA_SPEND_COLUMNS, gbp in pounds. Lines
    are SPEND_LINES (accommodation types plus 'ta_admin'). Where several old
    lines map to one line (up to 2019-20) they are added together.
    """
    path = Path(path)
    if measure not in RO_MEASURES:
        raise ValueError(f"measure must be one of {RO_MEASURES}")
    xl = _open_workbook(path, engine)
    sheets = [sheet] if sheet is not None else list(xl.sheet_names)
    best = None
    for s in sheets:
        raw = _parse(xl, s)
        for kind in ("ons", "lgf"):
            layout = locate_table(raw, s, code_kind=kind)
            if layout is None:
                continue
            mapping: dict[tuple[str, str | None], list] = {}
            for c, label in layout.labels.items():
                line, meas = _classify_ro4_label(label)
                if line:
                    mapping.setdefault((line, meas), []).append(c)
            if mapping:
                score = (kind == "ons", len(layout.data_rows), len(mapping))
                if best is None or score > best[0]:
                    best = (score, raw, layout, mapping)
                break
    if best is None:
        raise ValueError(f"{path.name}: no sheet with council codes and RO4 TA lines found")
    _, raw, layout, mapping = best
    if layout.code_kind == "lgf":
        warnings.warn(f"{path.name}: no ONS codes found; la_code holds MHCLG finance codes (E0701 style)",
                      TaMarketWarning, stacklevel=2)

    fy = year or year_from_text(path.name) or year_from_text(_title_text(raw, layout))
    if fy is None:
        raise ValueError(f"{path.name}: cannot tell the financial year; pass year='YYYY-YY'")

    chosen = {line: cols for (line, meas), cols in mapping.items() if meas == measure}
    if not chosen:
        available = sorted({m for (_, m) in mapping if m})
        raise ValueError(f"{path.name}: no {measure!r} columns for the TA lines; found {available or 'none'}")
    for line, cols in chosen.items():
        if len(cols) > 1:
            if fy >= "2020-21":
                warnings.warn(f"{path.name}: {len(cols)} columns for {line!r} {measure}; adding them: "
                              f"{[layout.labels[c] for c in cols]}", TaMarketWarning, stacklevel=2)
    missing = [k for k in SPEND_LINES if k not in chosen]
    if missing:
        warnings.warn(f"{path.name}: no {measure} column for {missing}", TaMarketWarning, stacklevel=2)

    rows = []
    tokens: Counter = Counter()
    for r in layout.data_rows:
        code = _code_of(_text(raw.at[r, layout.code_col]))
        keep = (_keep_code(code, include_aggregates) if layout.code_kind == "ons"
                else bool(code))
        if not keep:
            continue
        name = _clean_name(_text(raw.at[r, layout.name_col])) if layout.name_col is not None else ""
        for line, cols in chosen.items():
            values = [raw.at[r, c] for c in cols]
            tokens.update(_token_counts(values))
            numbers = [_to_number(v) for v in values]
            total = np.nan if all(np.isnan(numbers)) else float(np.nansum(numbers))
            rows.append((code, name, fy, line, total * units_gbp, measure))
    out = pd.DataFrame(rows, columns=TA_SPEND_COLUMNS[:-1])
    out["source_file"] = path.name
    out.attrs.update({
        "source_file": path.name,
        "layout": layout.describe(),
        "column_map": {line: [layout.labels[c] for c in cols] for line, cols in chosen.items()},
        "non_numeric_values": dict(tokens),
    })
    return out


def total_ta_spend(ta_spend: pd.DataFrame, include_admin: bool = True) -> pd.DataFrame:
    """Total TA spend per council and year (RO4 lines 80 to 86, or 80 to 85 without admin)."""
    lines = SPEND_LINES if include_admin else ACCOMMODATION_TYPES
    sub = ta_spend[ta_spend["line"].isin(lines)]
    keys = ["la_code", "la_name", "year"] + (["measure"] if "measure" in sub.columns else [])
    return sub.groupby(keys, as_index=False, dropna=False)["gbp"].sum(min_count=1)


# ---------------------------------------------------------------------------
# Revenue outturn multi-year data set (CSV plus metadata ODS)
# ---------------------------------------------------------------------------

RO_TIMESERIES_ID_COLUMNS = ["year_ending", "ONS_code", "LA_LGF_code", "LA_name"]


def read_ro_metadata(path, engine: str | None = None) -> pd.DataFrame:
    """Data dictionary from Revenue_Outturn_metadata.ods.

    Returns columns item, form, row, column, description (and start, end, notes
    where present). The sheet and header row are found by looking for a
    'data item name' header, so the sheet order does not matter.
    """
    path = Path(path)
    xl = _open_workbook(path, engine)
    wanted = {
        "item": r"item name|^data item$|^item$",
        "form": r"\bform\b",
        "row": r"\brow\b",
        "column": r"\bcolumn\b",
        "description": r"description",
        "start": r"\bstart\b",
        "end": r"\bend\b",
        "notes": r"\bnotes?\b",
    }
    for s in xl.sheet_names:
        raw = _parse(xl, s)
        text = raw.map(_text)
        for r in text.index[:60]:
            row = text.loc[r].map(lambda v: v.lower())
            if not row.str.contains(r"item name|^data item$", regex=True).any():
                continue
            cols = {}
            for key, rx in wanted.items():
                hits = [c for c, v in row.items() if v and re.search(rx, v) and c not in cols.values()]
                if hits:
                    cols[key] = hits[0]
            if "item" not in cols or "description" not in cols:
                continue
            body = text.loc[r + 1:, list(cols.values())]
            body.columns = list(cols.keys())
            body = body[body["item"] != ""].reset_index(drop=True)
            body.attrs["sheet"] = s
            return body
    raise ValueError(f"{path.name}: no data dictionary with a 'data item name' header found")


def _select_ro4_items(meta: pd.DataFrame, measure: str) -> dict[str, str]:
    items: dict[str, str] = {}
    is_ro4 = meta["form"].str.contains(r"ro\s*4|housing", case=False, regex=True) if "form" in meta else True
    for _, rec in meta[is_ro4].iterrows():
        description = rec.get("description", "")
        line, meas = _classify_ro4_label(description)
        if line is None and "row" in meta:
            row_no = _to_number(rec.get("row"))
            if row_no in RO4_TA_LINES and re.search(r"homeless|temporary", description, re.I):
                line = RO4_TA_LINES[int(row_no)][0]
                meas = next((k for k, p in _RO_MEASURE_PATTERNS if p.search(_norm(description))), None)
        if line and meas == measure:
            items[rec["item"]] = line
    return items


def read_ro_timeseries(csv_path, metadata_path=None, measure: str = "total_expenditure",
                       items: Mapping[str, str] | None = None,
                       include_aggregates: bool = False) -> pd.DataFrame:
    """TA spend for every year in the Revenue Outturn multi-year CSV (2017-18 onwards).

    The CSV is wide (one row per authority and year, one column per data item,
    GBP thousand). The TA items are picked from the metadata data dictionary by
    their descriptions, or given directly as ``items`` ({csv column: line}).
    Returns TA_SPEND_COLUMNS with gbp in pounds.
    """
    csv_path = Path(csv_path)
    if measure not in RO_MEASURES:
        raise ValueError(f"measure must be one of {RO_MEASURES}")
    if items is None:
        if metadata_path is None:
            raise ValueError("pass metadata_path (Revenue_Outturn_metadata.ods) or items")
        items = _select_ro4_items(read_ro_metadata(metadata_path), measure)
        if not items:
            raise ValueError(f"no RO4 TA items for {measure!r} found in the metadata; pass items explicitly")
    header = pd.read_csv(csv_path, nrows=0).columns.tolist()
    absent = [i for i in items if i not in header]
    if absent:
        warnings.warn(f"{csv_path.name}: items not in the CSV: {absent}", TaMarketWarning, stacklevel=2)
    use = [i for i in items if i in header]
    ids = [c for c in RO_TIMESERIES_ID_COLUMNS if c in header]
    df = pd.read_csv(csv_path, usecols=ids + use, dtype=str, keep_default_na=False)
    long = df.melt(id_vars=ids, value_vars=use, var_name="item", value_name="value")
    long["line"] = long["item"].map(dict(items))
    long["gbp"] = long["value"].map(_to_number) * 1000.0
    long["year"] = long["year_ending"].map(_fy_from_year_ending)
    code = long.get("ONS_code", pd.Series("", index=long.index)).fillna("").str.strip()
    if "LA_LGF_code" in long:
        code = code.where(code != "", long["LA_LGF_code"].fillna("").str.strip())
    long["la_code"] = code
    long["la_name"] = long.get("LA_name", "")
    keep = long["la_code"].map(lambda c: _keep_code(c, include_aggregates))
    long = long[keep]
    out = (long.groupby(["la_code", "la_name", "year", "line"], as_index=False, dropna=False)["gbp"]
           .sum(min_count=1))
    out["measure"] = measure
    out["source_file"] = csv_path.name
    out = out[TA_SPEND_COLUMNS]
    out.attrs.update({"source_file": csv_path.name, "items": dict(items)})
    return out


# ---------------------------------------------------------------------------
# Council code changes (mergers and recoding)
# ---------------------------------------------------------------------------

def read_code_changes(path) -> pd.DataFrame:
    """config/code_changes.csv: effective, old_code, old_name, new_code, new_name, ..."""
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def harmonise_codes(df: pd.DataFrame, code_changes: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Move rows for predecessor councils onto their successor's code and add them up.

    Changes are followed through (Taunton Deane to Somerset West and Taunton to
    Somerset). A successor's value is NaN if any predecessor's value is missing,
    so a gap is never hidden as a smaller number. Rows are kept, not dropped.
    """
    step = dict(zip(code_changes["old_code"], code_changes["new_code"]))
    names = dict(zip(code_changes["new_code"], code_changes["new_name"]))

    def final(code: str) -> str:
        seen = set()
        while code in step and code not in seen:
            seen.add(code)
            code = step[code]
        return code

    out = df.copy()
    out["la_code"] = out["la_code"].map(final)
    # One name per code: the successor's name from the table, else the first name seen.
    out["la_name"] = out["la_code"].map(names).fillna(out.groupby("la_code")["la_name"].transform("first"))
    keys = [c for c in out.columns if c not in (value_col, "source_file")]
    agg = {value_col: lambda s: s.sum() if s.notna().all() else np.nan}
    if "source_file" in out.columns:
        agg["source_file"] = lambda s: ";".join(sorted(set(s)))
    return out.groupby(keys, as_index=False, dropna=False).agg(agg)[list(df.columns)]


# ---------------------------------------------------------------------------
# Many files
# ---------------------------------------------------------------------------

def discover_raw_files(raw_dir) -> dict[str, list[Path]]:
    """Sort the files in data/raw into households, spend, ro_timeseries, ro_metadata, lookup, other."""
    groups: dict[str, list[Path]] = {k: [] for k in
                                     ("households", "spend", "ro_timeseries", "ro_metadata", "lookup", "other")}
    for p in sorted(Path(raw_dir).glob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        n = p.name.lower()
        if "mdis" in n:
            groups["other"].append(p)
        elif re.search(r"detailed_?la|detailed_local_authority", n) and p.suffix.lower() in {".ods", ".xlsx"}:
            groups["households"].append(p)
        elif n.startswith("ro4") and p.suffix.lower() in {".ods", ".xlsx"}:
            groups["spend"].append(p)
        elif "revenue_outturn_time_series" in n:
            groups["ro_timeseries"].append(p)
        elif "revenue_outturn_metadata" in n:
            groups["ro_metadata"].append(p)
        elif "lookup" in n or re.search(r"lad\d{2}.*rgn\d{2}", n):
            groups["lookup"].append(p)
        else:
            groups["other"].append(p)
    return groups


def _preference(path: Path) -> tuple:
    n = path.name.lower()
    quarterly = _YYYYMM.search(n) is not None and year_from_text(n) is None
    return (quarterly, "revised" in n or "corrected" in n, "accessible" not in n, n)


def pick_household_files(paths: Iterable) -> dict[str, Path]:
    """One detailed LA file per snapshot quarter: {'YYYY-Qn': path}.

    Where two files cover the same snapshot (for example the January to March
    file and the financial year file), the quarterly, revised or corrected,
    non-prototype file wins and the others are skipped with a warning.
    """
    by_quarter: dict[str, list[Path]] = {}
    for p in map(Path, paths):
        by_quarter.setdefault(quarter_from_text(p.name) or p.name, []).append(p)
    chosen = {}
    for q, files in sorted(by_quarter.items()):
        files = sorted(files, key=_preference)
        if len(files) > 1:
            warnings.warn(f"{q}: using {files[-1].name}; skipping {[f.name for f in files[:-1]]}",
                          TaMarketWarning, stacklevel=2)
        chosen[q] = files[-1]
    return chosen


def load_ta_households(paths: Iterable, **kwargs) -> pd.DataFrame:
    """Read several detailed LA files, one per quarter (see pick_household_files)."""
    frames = [read_ta_households(p, **kwargs) for p in pick_household_files(paths).values()]
    if not frames:
        return pd.DataFrame(columns=TA_HOUSEHOLDS_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def load_ta_spend(paths: Iterable, **kwargs) -> pd.DataFrame:
    """Read several RO4 files; one file per financial year (the last listed wins)."""
    by_year: dict[str, Path] = {}
    for p in map(Path, paths):
        by_year[year_from_text(p.name) or p.name] = p
    frames = [read_ta_spend(p, **kwargs) for _, p in sorted(by_year.items())]
    if not frames:
        return pd.DataFrame(columns=TA_SPEND_COLUMNS)
    return pd.concat(frames, ignore_index=True)


__all__ = [
    "ACCOMMODATION_TYPES",
    "ENGINE_ENV",
    "GSS_CODE",
    "HOUSING_AUTHORITY_CODE",
    "RO4_TA_LINES",
    "RO4_TA_LINES_TO_2019_20",
    "RO_MEASURES",
    "SPEND_LINES",
    "TA1_TYPES",
    "TA_HOUSEHOLDS_COLUMNS",
    "TA_SPEND_COLUMNS",
    "TableLayout",
    "TaMarketWarning",
    "discover_raw_files",
    "financial_year_of_quarter",
    "harmonise_codes",
    "load_ta_households",
    "load_ta_spend",
    "locate_table",
    "pick_household_files",
    "quarter_from_text",
    "read_code_changes",
    "read_ro_metadata",
    "read_ro_timeseries",
    "read_ta_households",
    "read_ta_spend",
    "total_ta_spend",
    "validate_ta_households",
    "year_from_text",
]
