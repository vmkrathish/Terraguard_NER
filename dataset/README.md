# dataset/

This folder contains a bundled copy of `SIH26001_Master_Dataset.xlsx` — the
Census of India 2001 Village Directory dataset for 7 of the 8 North-Eastern
states (8,722 villages), used by `scripts/ingest_village_census.py`.

It is checked into this project folder (not just handed over separately)
specifically so that:

- `python scripts/ingest_village_census.py` works immediately with no
  `--file` argument and no path to guess or fix.
- Anyone you share this project's `.zip` with can run the exact same
  ingestion command themselves, without needing you to separately send them
  the Excel file or explain where to put it.

See `docs/DATASET_SCHEMA_DIFF.md` for the full inspection of what this
dataset actually contains, what it does NOT contain (no coordinates, no
geotechnical/hazard data — see that doc before wiring it into anything
ML-related), and the column-by-column schema diff.

**If you're re-running the ingestion with a newer/different version of this
workbook**, replace this file with the new one (keep the same filename,
`SIH26001_Master_Dataset.xlsx`) or pass your own path explicitly:

```bash
python scripts/ingest_village_census.py --file /path/to/your/copy.xlsx
```
