"""Reproduce the pinned snapshot from an ECB archive; never refresh implicitly."""
import argparse
import csv
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from public_sample import ROOT, SOURCE_ID, SOURCE_URL, ATTRIBUTION, NOTICE, write_workspace


def snapshot(archive):
    with zipfile.ZipFile(archive) as z:
        records = list(csv.DictReader(io.StringIO(z.read("eurofxref-hist.csv").decode("utf-8-sig"))))
    selected = sorted((r for r in records if r["Date"] >= "2023-01-01"), key=lambda r: r["Date"])[:600]
    if len(selected) != 600:
        raise ValueError("Expected 600 published observations.")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["observation_date", "base_currency", "USD", "GBP", "JPY", "CHF"])
    for row in selected:
        rates = [row[c].strip() for c in ("USD", "GBP", "JPY", "CHF")]
        if not all(float(r) > 0 for r in rates):
            raise ValueError("Invalid reference rate.")
        writer.writerow([row["Date"], "EUR", *rates])
    content = output.getvalue().encode()
    target = ROOT / "ecb_fx_original.csv"
    if target.exists() and target.read_bytes() != content:
        raise ValueError("Snapshot differs: create a new source version rather than overwrite history.")
    target.write_bytes(content)
    manifest = dict(source_id=SOURCE_ID, source_url=SOURCE_URL, attribution=ATTRIBUTION,
                    modification_notice=NOTICE, original_count=600, demo_count=620,
                    start_date=selected[0]["Date"], end_date=selected[-1]["Date"],
                    currencies=["USD", "GBP", "JPY", "CHF"], base_currency="EUR",
                    sha256=hashlib.sha256(content).hexdigest(),
                    copyright_url="https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html",
                    retrieved_on="2026-11-18",
                    selection="First 600 published dates from 2023-01-01, chronological; four currency columns, no interpolation.")
    (ROOT / "ecb_fx_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    write_workspace()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    snapshot(parser.parse_args().archive)
