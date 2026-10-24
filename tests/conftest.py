"""Builders for tiny synthetic spreadsheets in the shapes MHCLG publishes.

All council names and numbers here are made up. Codes follow the ONS format so
the parsers can find them; they are not meant to match the real councils.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def write_book(path: Path, sheets: dict[str, list[list]]) -> Path:
    """Write {sheet name: rows} to .ods (odf) or .xlsx (openpyxl) with no header or index."""
    engine = "odf" if path.suffix == ".ods" else "openpyxl"
    width = max((len(r) for rows in sheets.values() for r in rows), default=1)
    with pd.ExcelWriter(path, engine=engine) as writer:
        for name, rows in sheets.items():
            padded = [list(r) + [None] * (width - len(r)) for r in rows] or [[None]]
            pd.DataFrame(padded, dtype=object).to_excel(writer, sheet_name=name, header=False, index=False)
    return path


# --- TA1, legacy layout: two header rows, merged groups, uncoded England row ---------------

TA1_GROUP_ROW = [
    None, None, "Total number of households in TA [note 1]",
    "Bed and breakfast hotels (including shared annexes)", None, None,
    "Nightly paid, privately managed accommodation, self-contained", None,
    "Hostels (including reception centres, emergency units and refuges)", None,
    "Private sector accommodation leased by your authority or leased or managed by a registered provider", None,
    "Local authority or Housing association (LA/HA) stock", None,
    "Any other type of accommodation", None,
    "In another local authority district",
    "Number of households in TA per 1,000 households",
]
TA1_SUB_ROW = [
    "ONS code", "Local authority", None,
    "Total", "of which: households with children",
    "of which: households with children in B&B over 6 weeks (including those pending appeal)",
    "Total", "of which: households with children",
    "Total", "of which: households with children",
    "Total", "of which: households with children",
    "Total", "of which: households with children",
    "Total", "of which: households with children",
    None, None,
]


def ta1_row(code, name, bnb, np_, hostels, psl, laha, other, another=0, rate=1.5):
    total = None
    if all(isinstance(v, (int, float)) for v in (bnb, np_, hostels, psl, laha, other)):
        total = bnb + np_ + hostels + psl + laha + other
    return [code, name, total, bnb, 1, 0, np_, 2, hostels, 0, psl, 3, laha, 4, other, 0, another, rate]


@pytest.fixture
def legacy_ta1(tmp_path) -> Path:
    ta1 = [
        ["Table TA1: Households in temporary accommodation by type of accommodation, England, 31 March 2026"],
        ["Back to contents"],
        [],
        TA1_GROUP_ROW,
        TA1_SUB_ROW,
        [None, "ENGLAND", 5000, 300, 10, 1, 2500, 20, 100, 1, 900, 9, 700, 7, 500, 5, 400, 2.1],
        ta1_row("E12000007", "Region L", 160, 1300, 55, 520, 315, 110),
        ta1_row("E09000001", "Borough A", 10, 40, 5, 20, 15, 10),
        ta1_row("E09000002", "Borough B [note 3]", 150, 900, 50, 500, 300, 100),
        ["E07000223", "District C", "..", "..", "..", "..", "..", "..", "..", "..", "..", "..",
         "..", "..", "..", "..", "..", ".."],
        ["E06000001", "Unitary D", "1,050", "50", 0, 0, "600", 0, "100", 0, "200", 0, "50", 0, "50", 0, 0, 0.9],
        [],
        ["Notes"],
        ["1. Snapshot of households in temporary accommodation on the last day of the quarter."],
    ]
    ta2 = [
        ["Table TA2: Households in TA by household type"],
        ["ONS code", "Local authority", "Couple with dependent children", "Single parent"],
        ["E09000001", "Borough A", 7, 8],
    ]
    path = tmp_path / "Statutory_Homelessness_Detailed_Local_Authority_Data_202603.ods"
    return write_book(path, {"Cover": [["Statutory homelessness: detailed local authority tables"]],
                             "TA1": ta1, "TA2": ta2})


# --- RO4 'data by LA', wide layout --------------------------------------------------------

RO4_LINES = [
    (80, "Nightly paid, privately managed accommodation, self-contained"),
    (81, "Private sector accommodation leased by authority or by a registered provider"),
    (82, "Hostels (including reception centres, emergency units and refuges)"),
    (83, "Bed and breakfast hotels (including shared annexes)"),
    (84, "Local authority or housing association (LA/HA) stock"),
    (85, "Any other type of temporary accommodation (including private landlord and not known)"),
    (86, "Temporary accommodation administration"),
    (87, "Homeless Reduction Act: Administration, Prevention, Relief & Support"),
    (30, "Other council property (non-HRA)"),
]
RO4_MEASURES = ["Total expenditure", "Total income", "Net current expenditure"]


def ro4_values(scale: float) -> list:
    """(TE, TI, NCE) for each line in RO4_LINES, in GBP thousand."""
    base = {80: (1000, 400), 81: (500, 200), 82: (100, 50), 83: (200, 120), 84: (50, 20),
            85: (25, 5), 86: (75, 0), 87: (300, 0), 30: (40, 10)}
    out = []
    for line, _ in RO4_LINES:
        te, ti = base[line]
        out += [te * scale, ti * scale, (te - ti) * scale]
    return out


@pytest.fixture
def ro4_wide(tmp_path) -> Path:
    numbers_row, names_row, measures_row = [None] * 4, [None] * 4, ["E-code", "ONS code", "Local authority", "Class"]
    for line, name in RO4_LINES:
        numbers_row += [line, None, None]
        names_row += [name, None, None]
        measures_row += RO4_MEASURES
    data = [
        ["RO4 Housing services 2024-25: data by local authority"],
        ["GBP thousand"],
        [],
        numbers_row,
        names_row,
        measures_row,
        ["E9999", "E92000001", "England", "Eng"] + ro4_values(100),
        ["E5010", "E09000002", "Borough B", "L"] + ro4_values(1),
        ["E0701", "E06000001", "Unitary D", "UA"] + ro4_values(2),
        ["E1001", "E10000099", "County E", "SC"] + [0] * (3 * len(RO4_LINES)),
        ["E4401", "E07000223", "District C", "SD"] + ["Not set"] * (3 * len(RO4_LINES)),
    ]
    dropdown = [
        ["Select a local authority:", "Borough B"],
        ["Line", "Description", "Total expenditure"],
        [80, "Nightly paid, privately managed accommodation, self-contained", 1000],
        [],
        ["ONS code", "Local authority"],
        ["E09000002", "Borough B"],
        ["E06000001", "Unitary D"],
    ]
    path = tmp_path / "RO4_LA_Data_2024-25_data_by_LA.ods"
    return write_book(path, {"RO4 LA drop-down": dropdown, "RO4 LA Data": data})
