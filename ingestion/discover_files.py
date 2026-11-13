"""Discover which Award Data Archive files exist for our target agencies.

Purpose: confirm file names, snapshot dates, and (optionally) sizes before committing to a
fiscal-year range. Writes a de-duplicated summary CSV, plus raw API responses with --dump-raw.

Findings from the first live run:
- Each (agency, fiscal year, type) query returns one Full file for that year plus the same
  "FY(All)" Delta file, so results are de-duplicated by URL.
- File names follow FY{year|(All)}_{agency}_{Contracts|Assistance}_{Full|Delta}_{YYYYMMDD}.zip
- The API reports no file sizes; use --with-sizes to issue HEAD requests instead.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from ingestion.usaspending_client import USAspendingClient

# toptier agency codes (CGAC): DHS = 070, Treasury = 020
TARGET_AGENCIES = {
    "070": "Department of Homeland Security",
    "020": "Department of the Treasury",
}
FILE_TYPES = ("contracts", "assistance")

ARCHIVE_NAME_RE = re.compile(
    r"^FY(?P<fy>\d{4}|\(All\))_(?P<agency>\d{3})_(?P<award_type>Contracts|Assistance)"
    r"_(?P<kind>Full|Delta)_(?P<snapshot>\d{8})\.zip$"
)

FIELDNAMES = [
    "agency_code",
    "agency",
    "fiscal_year",
    "award_type",
    "file_kind",
    "snapshot_date",
    "file_name",
    "updated_date",
    "size_mb",
    "url",
]


def current_fiscal_year(today: date | None = None) -> int:
    """US federal fiscal year starts Oct 1 (FY2027 began 2026-10-01)."""
    today = today or date.today()
    return today.year + 1 if today.month >= 10 else today.year


def flatten_agencies(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the list_agencies response (grouped lists) into one list of agency dicts."""
    agencies = response.get("agencies", response)
    flat: list[dict[str, Any]] = []
    if isinstance(agencies, dict):
        for value in agencies.values():
            if isinstance(value, list):
                flat.extend(a for a in value if isinstance(a, dict))
    elif isinstance(agencies, list):
        flat.extend(a for a in agencies if isinstance(a, dict))
    return flat


def match_agencies(agencies: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return {toptier_code: agency_dict} for our targets, matching by code, then by name."""
    matched: dict[str, dict[str, Any]] = {}
    for code, name in TARGET_AGENCIES.items():
        for agency in agencies:
            agency_code = str(agency.get("toptier_code", ""))
            agency_name = str(agency.get("name", "")).strip().lower()
            if agency_code == code or agency_name == name.lower():
                matched[code] = agency
                break
    return matched


def parse_fiscal_years(value: str) -> list[int]:
    """'2021-2026' -> [2021..2026]; '2024' -> [2024]."""
    if "-" in value:
        start, end = (int(part) for part in value.split("-", 1))
        return list(range(start, end + 1))
    return [int(value)]


def parse_archive_name(file_name: str) -> dict[str, str] | None:
    """Parse an archive file name into its parts, or None if it doesn't match the pattern.

    fiscal_year is "All" for Delta files; snapshot_date is ISO formatted (YYYY-MM-DD).
    """
    match = ARCHIVE_NAME_RE.match(file_name or "")
    if not match:
        return None
    snapshot = match["snapshot"]
    fiscal_year = "All" if match["fy"] == "(All)" else match["fy"]
    return {
        "agency_code": match["agency"],
        "fiscal_year": fiscal_year,
        "award_type": match["award_type"].lower(),
        "file_kind": match["kind"].lower(),
        "snapshot_date": f"{snapshot[:4]}-{snapshot[4:6]}-{snapshot[6:]}",
    }


def build_row(code: str, item: dict[str, Any]) -> dict[str, Any]:
    """Build one output row from an API monthly_files item, using the parsed file name."""
    file_name = item.get("file_name") or ""
    parsed = parse_archive_name(file_name) or {}
    return {
        "agency_code": code,
        "agency": TARGET_AGENCIES[code],
        "fiscal_year": parsed.get("fiscal_year", ""),
        "award_type": parsed.get("award_type", ""),
        "file_kind": parsed.get("file_kind", ""),
        "snapshot_date": parsed.get("snapshot_date", ""),
        "file_name": file_name,
        "updated_date": item.get("updated_date"),
        "size_mb": "",
        "url": item.get("url"),
    }


def dedupe_by_url(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop repeated rows (the Delta file is returned for every fiscal year queried)."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        url = row.get("url")
        if url in seen:
            continue
        seen.add(url)
        unique.append(row)
    return unique


def _sort_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    # Full files first (by year), then the Delta file, within each agency and award type.
    return (row["agency_code"], row["award_type"], row["file_kind"] == "delta", row["fiscal_year"])


def bytes_to_mb(size_bytes: int | None) -> str:
    return "" if size_bytes is None else f"{size_bytes / 1_000_000:.1f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_end = current_fiscal_year()
    parser.add_argument("--fiscal-years", default=f"{default_end - 5}-{default_end}")
    parser.add_argument("--out", type=Path, default=Path("data/discovery"))
    parser.add_argument("--dump-raw", action="store_true", help="Write raw JSON responses")
    parser.add_argument(
        "--with-sizes",
        action="store_true",
        help="HEAD each file URL to record its size (no files are downloaded)",
    )
    args = parser.parse_args()

    client = USAspendingClient()
    args.out.mkdir(parents=True, exist_ok=True)

    agencies_response = client.list_agencies()
    if args.dump_raw:
        (args.out / "list_agencies.raw.json").write_text(json.dumps(agencies_response, indent=2))

    matched = match_agencies(flatten_agencies(agencies_response))
    missing = set(TARGET_AGENCIES) - set(matched)
    if missing:
        raise SystemExit(
            f"Could not match agencies {sorted(missing)}. "
            "Re-run with --dump-raw and inspect list_agencies.raw.json."
        )

    rows: list[dict[str, Any]] = []
    for code, agency in matched.items():
        agency_id = agency.get("toptier_agency_id", agency.get("id"))
        for fiscal_year in parse_fiscal_years(args.fiscal_years):
            for file_type in FILE_TYPES:
                response = client.list_monthly_files(agency_id, fiscal_year, file_type)
                if args.dump_raw:
                    name = f"monthly_{code}_{fiscal_year}_{file_type}.raw.json"
                    (args.out / name).write_text(json.dumps(response, indent=2))
                rows.extend(build_row(code, item) for item in response.get("monthly_files", []))

    rows = sorted(dedupe_by_url(rows), key=_sort_key)

    if args.with_sizes:
        total_bytes = 0
        for row in rows:
            size = client.head_content_length(row["url"])
            row["size_mb"] = bytes_to_mb(size)
            total_bytes += size or 0
            print(f"{row['file_name']}: {row['size_mb'] or 'size unavailable'} MB")
        print(f"Total compressed size: {total_bytes / 1_000_000_000:.2f} GB")

    summary = args.out / "archive_files.csv"
    with summary.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} unique file records to {summary}")


if __name__ == "__main__":
    main()
