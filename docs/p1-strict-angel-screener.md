# P1 Strict Angel Screener

Use this tool after sourcing raw angel candidates. It applies the same strict P1 filter used by the team:

- Europe/UK only, no Cyprus.
- Must have personal angel/check-writer/scout/micro-fund evidence.
- Must have B2C, consumer marketplace, gaming, viral fintech, or PLG operator experience.
- Reject VC-only, advisor-only, mentor-only, B2B SaaS-only, consulting-only, medical/biotech, real estate, corporate finance, heavy industry, and US-only profiles.
- Output includes only `gateway_eligible` rows.

## Candidate File

Create JSON, CSV, or TSV with these fields:

- `name`
- `linkedin_url`
- `city`
- `country`
- `headline`
- `evidence`

See `examples/p1-strict-angel-candidates.example.json`.

## Run

```sh
uv run python scripts/p1-strict-angel-screener.py \
  --candidates examples/p1-strict-angel-candidates.example.json \
  --env-file .env \
  --seen-csv-url "https://docs.google.com/spreadsheets/d/<sheet-id>/export?format=csv&gid=<gid>" \
  --output /tmp/p1_strict_approved_angels.tsv \
  --audit-output /tmp/p1_strict_angel_audit.json \
  --limit 50
```

The script writes:

- approved TSV for pasting into Google Sheets;
- audit JSON with rejects, `needs_enrichment`, errors, scores, gates, and reasons.

## Clipboard

On macOS:

```sh
pbcopy < /tmp/p1_strict_approved_angels.tsv
```

## Notes

If fewer than the requested limit pass, do not pad the file. The rejected candidates are the exact profiles that previously became red rows in the sheet.
