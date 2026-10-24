"""Browser extracts of MHCLG spreadsheets (data/raw/browser).

This workspace cannot reach gov.uk, so each spreadsheet was opened in a browser,
the sheet the build needs was read there, and its cells were written out as a
pipe-delimited text block together with checks computed in the browser:

* the source file's size in bytes and its SHA-256;
* the number of data rows;
* the sum of every numeric cell in each column from the third column on.

The block was then copied into this repo and its own SHA-256 compared with the
one the browser computed (data/raw/browser/MANIFEST.csv). The reader below
refuses to return anything unless the file hash, the row count, the width of
every row and every column sum match. A transcription error therefore cannot
reach the analysis.

Block layout::

    #FILE id|source file name|bytes N|sha256 H|sheet S
    #TITLE|title of the sheet
    #KEYS|key|key|...        column keys used by the build
    #HEADERS|...             the sheet's own header text for each column
    #CHECK|...               optional note written by the browser
    one line per spreadsheet row, cells joined with |
    #ROWS|n
    #SUMS|...                per column: sum of numeric cells, rounded to 3 dp

Markers such as ``..``, ``[x]``, ``[c]`` and ``-`` are never read as zero.

Contains public sector information licensed under the Open Government Licence v3.0.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from tamarket.mhclg import ACCOMMODATION_TYPES, TA_HOUSEHOLDS_COLUMNS, TA_SPEND_COLUMNS


class ExtractMismatch(ValueError):
    """An extract failed one of its checks. Nothing from it may be used."""


#: The browser's numeric test, copied exactly so that the sums are computed the same way.
BROWSER_NUMBER = re.compile(r"^-?\d+(\.\d+)?(e-?\d+)?$", re.I)

#: Markers found in these sheets and how the build reads them. None becomes zero.
MARKERS = {
    "..": "not available: the council did not submit data for the quarter (2024-25 layout)",
    "[x]": "not available (2025-26 layout; also RO4 where a council's return is missing)",
    "[c]": "suppressed to protect confidentiality (2025-26 layout)",
    "-": "suppressed [Likely: appears only in the placed-in-another-council column, "
         "about as often as [c] in the 2025-26 layout]",
    "": "blank",
}

HOUSING_AUTHORITY = re.compile(r"^E0[6-9]\d{6}$")
REGION = re.compile(r"^E12\d{6}$")
ENGLAND = "E92000001"
LONDON = "E12000007"
#: RO4 classes of the housing authorities (shire district, unitary, metropolitan
#: district, London borough). The rest are county councils, police, fire and others.
HOUSING_CLASSES = ("SD", "UA", "MD", "LB")


@dataclass
class Extract:
    id: str
    source_file: str
    source_bytes: int
    source_sha256: str
    sheet: str
    title: str
    keys: list[str]
    headers: list[str]
    check: str | None
    rows: pd.DataFrame          # every cell as text, columns = keys
    extract_sha256: str
    path: Path
    notes: list[str] = field(default_factory=list)


def _round3(x: float) -> float:
    """Round like the browser's Math.round(x * 1000) / 1000 (half away from zero is
    not needed: the sums here never sit on a half)."""
    return round(x * 1000) / 1000


def read_extract(path: str | Path, expect_sha256: str | None = None) -> Extract:
    """Read and verify one extract. Raises ExtractMismatch on any failed check."""
    path = Path(path)
    raw = path.read_bytes()
    got_sha = hashlib.sha256(raw).hexdigest()
    if expect_sha256 is not None and got_sha != expect_sha256:
        raise ExtractMismatch(f"{path.name}: sha256 {got_sha} against manifest {expect_sha256}")
    lines = raw.decode("utf-8").splitlines()
    meta: dict[str, list[str]] = {}
    body: list[list[str]] = []
    for line in lines:
        if not line:
            continue
        if line.startswith("#"):
            tag, _, rest = line.partition("|") if not line.startswith("#FILE ") else ("#FILE", "", line[6:])
            meta[tag] = rest.split("|")
        else:
            body.append(line.split("|"))
    for tag in ("#FILE", "#TITLE", "#KEYS", "#HEADERS", "#ROWS", "#SUMS"):
        if tag not in meta:
            raise ExtractMismatch(f"{path.name}: missing {tag} line")

    file_parts = meta["#FILE"]
    m_bytes = re.fullmatch(r"bytes (\d+)", file_parts[2])
    m_sha = re.fullmatch(r"sha256 ([0-9a-f]{64})", file_parts[3])
    m_sheet = re.fullmatch(r"sheet (.+)", file_parts[4])
    if not (m_bytes and m_sha and m_sheet):
        raise ExtractMismatch(f"{path.name}: cannot read the #FILE line")

    keys = meta["#KEYS"]
    width = len(keys)
    bad_width = [i for i, r in enumerate(body) if len(r) != width]
    if bad_width:
        raise ExtractMismatch(f"{path.name}: {len(bad_width)} rows are not {width} cells wide "
                              f"(first at data row {bad_width[0] + 1})")
    want_rows = int(meta["#ROWS"][0])
    if len(body) != want_rows:
        raise ExtractMismatch(f"{path.name}: {len(body)} data rows against #ROWS {want_rows}")

    want_sums = meta["#SUMS"]
    if len(want_sums) != width:
        raise ExtractMismatch(f"{path.name}: #SUMS has {len(want_sums)} cells, want {width}")
    problems = []
    for j in range(2, width):
        s = 0.0
        for r in body:
            v = r[j]
            if BROWSER_NUMBER.match(v):
                s += float(v)
        if abs(_round3(s) - float(want_sums[j])) > 0.0015:
            problems.append(f"{keys[j]}: {_round3(s)} against {want_sums[j]}")
    if problems:
        raise ExtractMismatch(f"{path.name}: column sums differ: " + "; ".join(problems))

    return Extract(
        id=file_parts[0],
        source_file=file_parts[1],
        source_bytes=int(m_bytes.group(1)),
        source_sha256=m_sha.group(1),
        sheet=m_sheet.group(1),
        title=meta["#TITLE"][0] if meta["#TITLE"] else "",
        keys=keys,
        headers=meta["#HEADERS"],
        check=meta.get("#CHECK", [None])[0],
        rows=pd.DataFrame(body, columns=keys, dtype=str),
        extract_sha256=got_sha,
        path=path,
    )


def to_number(value: str) -> float:
    """A cell as a number; markers and blanks become NaN, never zero."""
    v = str(value).strip()
    if BROWSER_NUMBER.match(v):
        return float(v)
    if v in MARKERS:
        return np.nan
    raise ExtractMismatch(f"unexpected cell value {v!r}")


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

MANIFEST_COLUMNS = [
    "extract_file", "extract_sha256", "chars", "kind", "period", "source_id", "source_file",
    "source_bytes", "source_sha256", "source_url", "sheet", "read_in_browser", "method",
]


def read_manifest(path: str | Path) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def verify_against_manifest(ex: Extract, entry: dict) -> None:
    """The extract's own #FILE line must agree with the manifest's record of the source."""
    problems = []
    if ex.source_file != entry["source_file"]:
        problems.append(f"source file {ex.source_file} against {entry['source_file']}")
    if ex.source_bytes != int(entry["source_bytes"]):
        problems.append(f"source bytes {ex.source_bytes} against {entry['source_bytes']}")
    if ex.source_sha256 != entry["source_sha256"]:
        problems.append("source sha256 differs")
    if problems:
        raise ExtractMismatch(f"{ex.path.name}: " + "; ".join(problems))


# ---------------------------------------------------------------------------
# TA1: households in TA at quarter end, by type
# ---------------------------------------------------------------------------

TA1_NUMERIC = [
    "total", "area_households_thousands", "with_children", "children", *ACCOMMODATION_TYPES,
    "in_ta_in_another_la", "no_accommodation_secured",
]


def ta1_wide(ex: Extract, quarter: str, snapshot_date: str) -> pd.DataFrame:
    """One row per area (England, region, council) with every TA1 column as a number.

    The London region row appears twice in the sheet; the second copy is dropped
    after checking that it matches the first. A 'level' column says what each row is.
    """
    df = ex.rows.copy()
    missing = [k for k in ["code", "name", *TA1_NUMERIC] if k not in df.columns]
    if missing:
        raise ExtractMismatch(f"{ex.path.name}: TA1 keys missing: {missing}")
    df["code"] = df["code"].str.strip()
    df["name"] = df["name"].str.strip()
    raw_total = df["total"].str.strip()
    for k in TA1_NUMERIC:
        df[k] = df[k].map(to_number)
    df["total_marker"] = np.where(df["total"].isna(), raw_total, "")
    df["level"] = np.select(
        [df["code"] == ENGLAND, df["code"].str.match(REGION.pattern), df["code"].str.match(HOUSING_AUTHORITY.pattern)],
        ["england", "region", "council"], default="other",
    )
    if (df["level"] == "other").any():
        raise ExtractMismatch(f"{ex.path.name}: rows with unexpected codes: "
                              f"{df.loc[df.level == 'other', 'code'].tolist()}")
    dup = df[df.duplicated("code", keep=False)]
    if not dup.empty:
        if set(dup["code"]) != {LONDON}:
            raise ExtractMismatch(f"{ex.path.name}: duplicated codes {sorted(set(dup['code']))}")
        a, b = dup.iloc[0][TA1_NUMERIC], dup.iloc[1][TA1_NUMERIC]
        if not ((a == b) | (a.isna() & b.isna())).all():
            raise ExtractMismatch(f"{ex.path.name}: the two London rows differ")
        df = df.drop_duplicates("code", keep="first")
    df.insert(0, "quarter", quarter)
    df.insert(1, "snapshot_date", snapshot_date)
    df["source_file"] = ex.source_file
    # Council names in some files carry a note such as "Barnsley (up to 202503)".
    df["name"] = df["name"].str.replace(r"\s*\(up to \d{6}\)$", "", regex=True)
    return df.reset_index(drop=True)


def ta_households_long(wide: pd.DataFrame) -> pd.DataFrame:
    """Councils only, in the agreed schema: la_code, la_name, quarter,
    accommodation_type, households, source_file."""
    c = wide[wide["level"] == "council"]
    long = c.melt(id_vars=["code", "name", "quarter", "source_file"],
                  value_vars=[*ACCOMMODATION_TYPES, "total"],
                  var_name="accommodation_type", value_name="households")
    long = long.rename(columns={"code": "la_code", "name": "la_name"})
    return long[TA_HOUSEHOLDS_COLUMNS].sort_values(["quarter", "la_code", "accommodation_type"]).reset_index(drop=True)


def ta1_type_check(wide: pd.DataFrame) -> dict:
    """How often the six types add up to the total, for councils with every value present."""
    c = wide[wide["level"] == "council"]
    full = c.dropna(subset=["total", *ACCOMMODATION_TYPES])
    diff = full["total"] - full[list(ACCOMMODATION_TYPES)].sum(axis=1)
    off = full.loc[diff != 0, ["code", "name"]].assign(difference=diff[diff != 0])
    return {
        "councils": int(len(c)),
        "councils_with_total": int(c["total"].notna().sum()),
        "councils_fully_numeric": int(len(full)),
        "types_sum_to_total": int((diff == 0).sum()),
        "largest_gap": float(diff.abs().max()) if len(diff) else 0.0,
        "mismatches": off.assign(difference=off["difference"].astype(float)).to_dict("records"),
    }


# ---------------------------------------------------------------------------
# RO4: TA spend by council, financial year
# ---------------------------------------------------------------------------

RO4_LINES = [*ACCOMMODATION_TYPES, "ta_admin", "total_homelessness"]
RO4_MEASURES = {"te": "total_expenditure", "nce": "net_current_expenditure"}


def ro4_wide(ex: Extract, year: str) -> pd.DataFrame:
    """One row per authority with each RO4 TA line in pounds (the file is in GBP thousand).

    Keeps every authority with its RO4 class so that totals can be checked; the
    hidden duplicate Greater London Authority row is dropped after checking it
    matches the first copy.
    """
    df = ex.rows.copy()
    value_keys = [f"{line}_{m}" for line in RO4_LINES for m in RO4_MEASURES]
    missing = [k for k in ["ons_code", "la_name", "e_code", "class", "certification", *value_keys]
               if k not in df.columns]
    if missing:
        raise ExtractMismatch(f"{ex.path.name}: RO4 keys missing: {missing}")
    for k in ["ons_code", "la_name", "e_code", "class", "certification"]:
        df[k] = df[k].str.strip()
    for k in value_keys:
        df[k] = df[k].map(to_number) * 1000.0
    dup = df[df.duplicated("ons_code", keep=False)]
    if not dup.empty:
        if set(dup["ons_code"]) != {LONDON}:
            raise ExtractMismatch(f"{ex.path.name}: duplicated codes {sorted(set(dup['ons_code']))}")
        a, b = dup.iloc[0][value_keys], dup.iloc[1][value_keys]
        if not ((a == b) | (a.isna() & b.isna())).all():
            raise ExtractMismatch(f"{ex.path.name}: the two Greater London Authority rows differ")
        df = df.drop_duplicates("ons_code", keep="first")
    df.insert(0, "year", year)
    df["housing_authority"] = df["class"].isin(HOUSING_CLASSES)
    df["source_file"] = ex.source_file
    return df.reset_index(drop=True)


def ta_spend_long(wide: pd.DataFrame) -> pd.DataFrame:
    """Housing authorities only, in the agreed schema: la_code, la_name, year, line,
    gbp, measure, source_file. Lines are the six accommodation types and ta_admin."""
    h = wide[wide["housing_authority"]]
    parts = []
    for line in [*ACCOMMODATION_TYPES, "ta_admin"]:
        for short, measure in RO4_MEASURES.items():
            parts.append(pd.DataFrame({
                "la_code": h["ons_code"], "la_name": h["la_name"], "year": h["year"],
                "line": line, "gbp": h[f"{line}_{short}"], "measure": measure,
                "source_file": h["source_file"],
            }))
    out = pd.concat(parts, ignore_index=True)
    return out[TA_SPEND_COLUMNS].sort_values(["year", "la_code", "measure", "line"]).reset_index(drop=True)


def ro4_england_check(wide: pd.DataFrame) -> dict:
    """Compare MHCLG's England row with the sum of the housing authorities."""
    eng = wide[wide["ons_code"] == ENGLAND]
    if eng.empty:
        return {"england_row": False}
    eng = eng.iloc[0]
    h = wide[wide["housing_authority"]]
    other = wide[~wide["housing_authority"] & (wide["ons_code"] != ENGLAND)]
    out = {"england_row": True, "lines": {}}
    for line in RO4_LINES:
        for short in RO4_MEASURES:
            k = f"{line}_{short}"
            out["lines"][k] = {
                "england_row": float(eng[k]),
                "housing_authorities": float(h[k].sum()),
                "other_authorities": float(other[k].sum()),
            }
    out["housing_authorities"] = int(len(h))
    out["housing_authorities_missing"] = h.loc[h["nightly_paid_self_contained_te"].isna(),
                                               ["ons_code", "la_name"]].to_dict("records")
    out["other_authorities_with_ta_spend"] = (
        other.loc[other[[f"{l}_te" for l in [*ACCOMMODATION_TYPES, "ta_admin"]]].fillna(0).abs().sum(axis=1) > 0,
                  ["ons_code", "la_name", "class"]].to_dict("records"))
    return out
