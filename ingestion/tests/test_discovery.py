from datetime import date

from ingestion.discover_files import (
    build_row,
    bytes_to_mb,
    current_fiscal_year,
    dedupe_by_url,
    flatten_agencies,
    match_agencies,
    parse_archive_name,
    parse_fiscal_years,
)


def test_current_fiscal_year_rolls_over_in_october():
    assert current_fiscal_year(date(2026, 9, 30)) == 2026
    assert current_fiscal_year(date(2026, 10, 1)) == 2027
    assert current_fiscal_year(date(2026, 11, 12)) == 2027


def test_parse_fiscal_years():
    assert parse_fiscal_years("2024") == [2024]
    assert parse_fiscal_years("2022-2024") == [2022, 2023, 2024]


def test_flatten_and_match_agencies_by_code_and_name():
    response = {
        "agencies": {
            "cfo_agencies": [
                {
                    "name": "Department of Homeland Security",
                    "toptier_agency_id": 1,
                    "toptier_code": "070",
                },
            ],
            "other_agencies": [
                {"name": "Department of the Treasury", "toptier_agency_id": 2},
                {"name": "Some Other Agency", "toptier_agency_id": 3, "toptier_code": "999"},
            ],
        }
    }
    matched = match_agencies(flatten_agencies(response))
    assert matched["070"]["toptier_agency_id"] == 1
    assert matched["020"]["toptier_agency_id"] == 2


def test_parse_archive_name_full_file():
    parsed = parse_archive_name("FY2022_070_Contracts_Full_20261106.zip")
    assert parsed == {
        "agency_code": "070",
        "fiscal_year": "2022",
        "award_type": "contracts",
        "file_kind": "full",
        "snapshot_date": "2026-11-06",
    }


def test_parse_archive_name_delta_file_has_all_years():
    parsed = parse_archive_name("FY(All)_020_Assistance_Delta_20261106.zip")
    assert parsed["fiscal_year"] == "All"
    assert parsed["file_kind"] == "delta"
    assert parsed["award_type"] == "assistance"


def test_parse_archive_name_rejects_unexpected_names():
    assert parse_archive_name("something_else.zip") is None
    assert parse_archive_name("") is None
    assert parse_archive_name(None) is None


def test_build_row_uses_parsed_name_not_query_year():
    item = {
        "file_name": "FY(All)_070_Contracts_Delta_20261106.zip",
        "updated_date": "2026-11-06",
        "url": "https://files.usaspending.gov/award_data_archive/x.zip",
    }
    row = build_row("070", item)
    assert row["fiscal_year"] == "All"
    assert row["file_kind"] == "delta"
    assert row["agency"] == "Department of Homeland Security"


def test_dedupe_by_url_keeps_first_occurrence():
    rows = [{"url": "a", "n": 1}, {"url": "b", "n": 2}, {"url": "a", "n": 3}]
    assert dedupe_by_url(rows) == [{"url": "a", "n": 1}, {"url": "b", "n": 2}]


def test_bytes_to_mb():
    assert bytes_to_mb(None) == ""
    assert bytes_to_mb(2_500_000) == "2.5"
