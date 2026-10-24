"""tamarket: a temporary accommodation (TA) market picture for England.

Aggregate statistics only. The package reads MHCLG statutory homelessness
tables (households in TA by council and accommodation type) and MHCLG revenue
outturn RO4 returns (TA spend by council) into tidy tables. It holds no
personal data and is not a case management tool.
"""

from tamarket.mhclg import (
    ACCOMMODATION_TYPES,
    RO4_TA_LINES,
    RO4_TA_LINES_TO_2019_20,
    SPEND_LINES,
    TA_HOUSEHOLDS_COLUMNS,
    TA_SPEND_COLUMNS,
    TaMarketWarning,
    discover_raw_files,
    financial_year_of_quarter,
    harmonise_codes,
    load_ta_households,
    load_ta_spend,
    quarter_from_text,
    read_code_changes,
    read_ro_metadata,
    read_ro_timeseries,
    read_ta_households,
    read_ta_spend,
    total_ta_spend,
    validate_ta_households,
    year_from_text,
)

__version__ = "0.1.0"

ATTRIBUTION = (
    "Contains public sector information licensed under the Open Government Licence v3.0."
)

__all__ = [
    "ACCOMMODATION_TYPES",
    "ATTRIBUTION",
    "RO4_TA_LINES",
    "RO4_TA_LINES_TO_2019_20",
    "SPEND_LINES",
    "TA_HOUSEHOLDS_COLUMNS",
    "TA_SPEND_COLUMNS",
    "TaMarketWarning",
    "__version__",
    "discover_raw_files",
    "financial_year_of_quarter",
    "harmonise_codes",
    "load_ta_households",
    "load_ta_spend",
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
