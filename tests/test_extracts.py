"""Tests for the browser-extract reader (synthetic blocks only)."""

import hashlib
import math

import pytest

from tamarket.extracts import (
    BROWSER_NUMBER, ExtractMismatch, read_extract, ro4_wide, ta1_type_check, ta1_wide,
    ta_households_long, ta_spend_long, to_number,
)

TA1_KEYS = ["code", "name", "total", "area_households_thousands", "with_children", "children",
            "bed_and_breakfast", "nightly_paid_self_contained", "hostels", "private_sector_leased",
            "la_ha_stock", "other", "in_ta_in_another_la", "no_accommodation_secured"]


def block(rows, keys=TA1_KEYS, sheet="TA1", sums=None, nrows=None):
    width = len(keys)
    s = [0.0] * width
    for r in rows:
        for j, v in enumerate(r):
            if j >= 2 and BROWSER_NUMBER.match(v):
                s[j] += float(v)
    sums = sums or ["" if j < 2 else str(round(x * 1000) / 1000) for j, x in enumerate(s)]
    lines = [f"#FILE t|test.ods|bytes 10|sha256 {'a' * 64}|sheet {sheet}", "#TITLE|Test", "#KEYS|" + "|".join(keys),
             "#HEADERS|" + "|".join(keys)]
    lines += ["|".join(r) for r in rows]
    lines += [f"#ROWS|{nrows if nrows is not None else len(rows)}", "#SUMS|" + "|".join(sums)]
    return "\n".join(lines)


ROWS = [
    ["E92000001", "ENGLAND", "100", "50.5", "60", "90", "10", "40", "5", "20", "20", "5", "30", "2"],
    ["E12000007", "London", "60", "3.5", "40", "70", "5", "30", "2", "15", "6", "2", "25", "1"],
    ["E12000007", "London", "60", "3.5", "40", "70", "5", "30", "2", "15", "6", "2", "25", "1"],
    ["E09000001", "Alpha", "30", "1.25", "20", "30", "3", "15", "1", "5", "5", "1", "[c]", "0"],
    ["E08000016", "Beta (up to 202503)", "..", "2", "..", "..", "..", "..", "..", "..", "..", "..", "..", ".."],
    ["E07000001", "Gamma", "12", "0.75", "4", "6", "2", "4", "0", "3", "2", "1", "-", "0"],
]


def write(tmp_path, text, name="x.txt"):
    p = tmp_path / name
    p.write_text(text)
    return p, hashlib.sha256(text.encode()).hexdigest()


def test_valid_block_reads(tmp_path):
    p, h = write(tmp_path, block(ROWS))
    ex = read_extract(p, h)
    assert len(ex.rows) == 6 and ex.sheet == "TA1" and ex.source_bytes == 10


def test_changed_cell_fails_the_sums(tmp_path):
    good = block(ROWS)
    bad = good.replace("E09000001|Alpha|30|", "E09000001|Alpha|31|")
    p, _ = write(tmp_path, bad)
    with pytest.raises(ExtractMismatch, match="column sums"):
        read_extract(p)


def test_wrong_hash_row_count_and_width_fail(tmp_path):
    p, h = write(tmp_path, block(ROWS))
    with pytest.raises(ExtractMismatch, match="sha256"):
        read_extract(p, "0" * 64)
    p2, _ = write(tmp_path, block(ROWS, nrows=7), "y.txt")
    with pytest.raises(ExtractMismatch, match="#ROWS"):
        read_extract(p2)
    short = [r[:] for r in ROWS]
    short[3] = short[3][:-1]
    p3, _ = write(tmp_path, block(short), "z.txt")
    with pytest.raises(ExtractMismatch, match="cells wide"):
        read_extract(p3)


def test_markers_are_never_zero():
    for m in ["..", "[x]", "[c]", "-", ""]:
        assert math.isnan(to_number(m))
    assert to_number("-3.5") == -3.5
    with pytest.raises(ExtractMismatch):
        to_number("n.k.")


def test_ta1_wide_dedupes_london_and_cleans_names(tmp_path):
    p, h = write(tmp_path, block(ROWS))
    w = ta1_wide(read_extract(p, h), "2025-Q1", "2025-03-31")
    assert (w["code"] == "E12000007").sum() == 1
    assert w.loc[w["code"] == "E08000016", "name"].item() == "Beta"
    assert w.loc[w["code"] == "E08000016", "total_marker"].item() == ".."
    assert w.set_index("code").loc["E09000001", "level"] == "council"
    check = ta1_type_check(w)
    assert check["councils"] == 3 and check["types_sum_to_total"] == 2 and check["councils_with_total"] == 2
    long = ta_households_long(w)
    assert set(long["la_code"]) == {"E09000001", "E08000016", "E07000001"} and len(long) == 3 * 7


def test_ta1_wide_refuses_differing_london_rows(tmp_path):
    rows = [r[:] for r in ROWS]
    rows[2][2] = "61"
    p, _ = write(tmp_path, block(rows))
    with pytest.raises(ExtractMismatch, match="London rows differ"):
        ta1_wide(read_extract(p), "2025-Q1", "2025-03-31")


RO4_KEYS = ["ons_code", "la_name", "e_code", "class", "certification"] + [
    f"{line}_{m}" for line in ["nightly_paid_self_contained", "private_sector_leased", "hostels",
                               "bed_and_breakfast", "la_ha_stock", "other", "ta_admin", "total_homelessness"]
    for m in ("te", "nce")]


def test_ro4_wide_units_and_housing_flag(tmp_path):
    vals = ["1"] * 16
    rows = [
        ["E09000001", "Alpha", "E5010", "LB", "Y", *vals],
        ["E10000016", "County", "E2221", "SC", "Y", *["0"] * 16],
        ["E12000007", "Greater London Authority", "E5100", "O", "N", *["0"] * 16],
        ["E92000001", "ENGLAND", "Eng", "Eng", "[Y]", *["1"] * 16],
        ["E12000007", "Greater London Authority", "E5100", "O", "0", *["0"] * 16],
    ]
    p, _ = write(tmp_path, block(rows, keys=RO4_KEYS, sheet="RO4"))
    w = ro4_wide(read_extract(p), "2024-25")
    assert len(w) == 4
    assert w.loc[w["ons_code"] == "E09000001", "nightly_paid_self_contained_te"].item() == 1000.0
    assert w["housing_authority"].tolist() == [True, False, False, False]
    long = ta_spend_long(w)
    assert set(long["la_code"]) == {"E09000001"} and len(long) == 7 * 2
