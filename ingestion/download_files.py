"""Download Award Data Archive zip files listed in data/discovery/archive_files.csv.

Idempotent and restartable: files already on disk with the expected size are skipped, and
new downloads are written atomically (.part file renamed after the size check). Each new
download is recorded in a JSON-lines manifest with its size and SHA-256 checksum.

Examples:
    python -m ingestion.download_files --dry-run
    python -m ingestion.download_files --fiscal-years 2024-2026
    python -m ingestion.download_files --fiscal-years 2017-2027 --kinds full delta
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ingestion.discover_files import parse_fiscal_years
from ingestion.usaspending_client import USAspendingClient


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"{path} not found. Run `make discover-sizes` first.")
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def select_rows(
    rows: list[dict[str, str]],
    agencies: set[str],
    fiscal_years: set[int],
    award_types: set[str],
    kinds: set[str],
) -> list[dict[str, str]]:
    """Filter discovery rows. Delta files cover all years, so the year filter applies to
    Full files only."""
    selected = []
    for row in rows:
        if row["agency_code"] not in agencies:
            continue
        if row["award_type"] not in award_types or row["file_kind"] not in kinds:
            continue
        if row["file_kind"] == "full" and int(row["fiscal_year"]) not in fiscal_years:
            continue
        selected.append(row)
    return selected


def destination(raw_dir: Path, row: dict[str, str]) -> Path:
    return raw_dir / "zips" / row["file_name"]


def already_downloaded(dest: Path, expected_size: int | None) -> bool:
    """True if dest exists and (when we know the expected size) matches it."""
    if not dest.exists():
        return False
    return expected_size is None or dest.stat().st_size == expected_size


def append_manifest(manifest: Path, entry: dict[str, Any]) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a") as handle:
        handle.write(json.dumps(entry) + "\n")


def download_selected(
    client: USAspendingClient,
    rows: list[dict[str, str]],
    raw_dir: Path,
    delay: float = 1.0,
) -> dict[str, int]:
    """Download each selected file; returns counts of downloaded / skipped / failed."""
    counts = {"downloaded": 0, "skipped": 0, "failed": 0}
    manifest = raw_dir / "manifest.jsonl"
    for index, row in enumerate(rows, start=1):
        dest = destination(raw_dir, row)
        label = f"[{index}/{len(rows)}] {row['file_name']}"
        expected_size, note = client.remote_size(row["url"])
        if already_downloaded(dest, expected_size):
            print(f"{label}: already present, skipping")
            counts["skipped"] += 1
            continue
        try:
            size, sha256 = client.download_to(row["url"], dest)
        except Exception as exc:  # keep going; report at the end
            print(f"{label}: FAILED ({type(exc).__name__}: {str(exc)[:100]}) {note}")
            counts["failed"] += 1
            continue
        append_manifest(
            manifest,
            {
                "file_name": row["file_name"],
                "url": row["url"],
                "agency_code": row["agency_code"],
                "award_type": row["award_type"],
                "file_kind": row["file_kind"],
                "fiscal_year": row["fiscal_year"],
                "snapshot_date": row["snapshot_date"],
                "bytes": size,
                "sha256": sha256,
                "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            },
        )
        print(f"{label}: downloaded {size / 1_000_000:.1f} MB")
        counts["downloaded"] += 1
        time.sleep(delay)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--discovery-csv", type=Path, default=Path("data/discovery/archive_files.csv")
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--agencies", nargs="+", default=["070", "020"])
    parser.add_argument("--fiscal-years", default="2024-2026")
    parser.add_argument("--types", nargs="+", default=["contracts", "assistance"])
    parser.add_argument("--kinds", nargs="+", default=["full", "delta"])
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between files")
    parser.add_argument("--dry-run", action="store_true", help="Show the plan; download nothing")
    args = parser.parse_args()

    rows = select_rows(
        load_rows(args.discovery_csv),
        agencies=set(args.agencies),
        fiscal_years=set(parse_fiscal_years(args.fiscal_years)),
        award_types=set(args.types),
        kinds=set(args.kinds),
    )
    known_mb = sum(float(r["size_mb"]) for r in rows if r.get("size_mb"))
    print(f"Selected {len(rows)} files (about {known_mb:.0f} MB compressed)")

    if args.dry_run:
        for row in rows:
            print(f"  {row['file_name']}  {row.get('size_mb') or '?'} MB")
        return

    counts = download_selected(USAspendingClient(), rows, args.raw_dir, delay=args.delay)
    print(
        f"Done: {counts['downloaded']} downloaded, {counts['skipped']} skipped, "
        f"{counts['failed']} failed"
    )
    if counts["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
