# FedSpend

An end-to-end data platform over federal spending data (USAspending.gov), scoped to DHS and
Treasury, with an AI layer (spending forecasts and a natural-language analyst assistant).

**Status:** Phase 1 (foundations and data discovery). See `docs/` for architecture as it develops.

## Quick start

```bash
python3.12 -m venv .venv && source .venv/bin/activate
make install            # dev dependencies + pre-commit hooks
cp .env.example .env    # then edit the passwords
make test
make discover           # lists DHS/Treasury archive files from USAspending
make up                 # MinIO (S3-compatible) + Postgres
```

## Data

All data comes from the public USAspending.gov API and bulk files (no authentication, public
domain). No employer or non-public data is used. Data files are never committed.

This is a test change.
Another test.
