import json
from pathlib import Path
from unittest.mock import MagicMock

from ingestion.download_files import (
    already_downloaded,
    append_manifest,
    download_selected,
    select_rows,
)


def make_row(agency, award_type, kind, fiscal_year, url):
    year = "(All)" if kind == "delta" else fiscal_year
    return {
        "agency_code": agency,
        "award_type": award_type,
        "file_kind": kind,
        "fiscal_year": fiscal_year,
        "file_name": f"FY{year}_{agency}_{award_type.title()}_{kind.title()}_20261106.zip",
        "url": url,
        "snapshot_date": "2026-11-06",
    }


ROWS = [
    make_row("070", "contracts", "full", "2024", "u1"),
    make_row("070", "contracts", "full", "2019", "u2"),
    make_row("070", "contracts", "delta", "All", "u3"),
    make_row("020", "assistance", "full", "2024", "u4"),
]


def test_select_rows_filters_by_year_but_keeps_delta():
    picked = select_rows(ROWS, {"070"}, {2024}, {"contracts"}, {"full", "delta"})
    assert [r["url"] for r in picked] == ["u1", "u3"]


def test_select_rows_filters_by_agency_and_type():
    picked = select_rows(ROWS, {"020"}, {2024}, {"assistance"}, {"full"})
    assert [r["url"] for r in picked] == ["u4"]


def test_already_downloaded(tmp_path: Path):
    f = tmp_path / "x.zip"
    assert not already_downloaded(f, 5)
    f.write_bytes(b"12345")
    assert already_downloaded(f, 5)
    assert not already_downloaded(f, 6)
    assert already_downloaded(f, None)


def test_append_manifest_writes_json_lines(tmp_path: Path):
    manifest = tmp_path / "m" / "manifest.jsonl"
    append_manifest(manifest, {"a": 1})
    append_manifest(manifest, {"a": 2})
    lines = manifest.read_text().splitlines()
    assert [json.loads(line)["a"] for line in lines] == [1, 2]


def test_download_selected_downloads_then_skips(tmp_path: Path):
    client = MagicMock()
    client.remote_size.return_value = (10, "")

    def fake_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"0123456789")
        return 10, "abc123"

    client.download_to.side_effect = fake_download
    rows = select_rows(ROWS, {"070"}, {2024}, {"contracts"}, {"full"})

    first = download_selected(client, rows, tmp_path, delay=0)
    assert first == {"downloaded": 1, "skipped": 0, "failed": 0}
    manifest = [json.loads(x) for x in (tmp_path / "manifest.jsonl").read_text().splitlines()]
    assert manifest[0]["sha256"] == "abc123" and manifest[0]["bytes"] == 10

    second = download_selected(client, rows, tmp_path, delay=0)
    assert second == {"downloaded": 0, "skipped": 1, "failed": 0}


def test_download_selected_counts_failures(tmp_path: Path):
    client = MagicMock()
    client.remote_size.return_value = (10, "")
    client.download_to.side_effect = OSError("boom")
    rows = select_rows(ROWS, {"070"}, {2024}, {"contracts"}, {"full"})
    counts = download_selected(client, rows, tmp_path, delay=0)
    assert counts["failed"] == 1 and not (tmp_path / "manifest.jsonl").exists()
