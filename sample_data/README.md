# Public financial demo snapshot

Source: European Central Bank (ECB), euro foreign exchange reference rates.
USD, GBP, JPY and CHF are currency units per EUR, not transaction prices.
600 published dates: 2023-01-02 through 2025-05-09. No invented rate values,
interpolation or forward filling.

`ecb_fx_original.csv` preserves the selected source strings and numeric values.
Its SHA-256, source URL, selection and reuse terms are in `ecb_fx_manifest.json`.
The XLSX original contains the same observations.

The current catalog version includes numeric validation among its six default
inspection checks. Older catalog versions are retained for historical reviews,
never overwritten when the inspection contract changes.

Files explicitly named `demo_errors` are modified for demonstration: every tenth
date uses slashes, every twelfth base-currency string has surrounding spaces,
and rows 2–21 are appended as exact duplicates. No rate values are changed.
The built-in fixes can reverse these modifications to the original 600 rows.
Outlier findings may reflect genuine market movements; do not change published
rates merely to eliminate them.

Reproduce from the official historical ZIP:
`python scripts/snapshot_public_sample.py /path/to/eurofxref-hist.zip`.
The script refuses a changed snapshot; use a new source/version for revisions.
Then `python -c "from public_sample import write_workspace; write_workspace()"`
regenerates the Excel and demonstration copies without any network access.

ECB permits reuse with attribution and explicit disclosure of modifications:
https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html
Original download: https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip
Retrieved 2026-11-18. The ECB does not endorse this application.

Older synthetic files/catalogs remain only for compatibility with historical
requests. They are not exposed by the current sample workspace or sample API.
Public samples do not change the session-only policy for private uploads.
