"""Pinned ECB observations and deterministic, explicitly modified practice copies."""
from pathlib import Path
import hashlib
import json
import pandas as pd

SOURCE_ID = "ecb-fx-2023-600-v3"
LABEL = "ECB exchange rates — labelled demo errors"
ROOT = Path(__file__).resolve().parent / "sample_data"
SOURCE_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
ATTRIBUTION = "Source: European Central Bank. Reference rates: currency units per EUR; informational, not transaction rates."
NOTICE = "Modified for demonstration: alternate date formatting, surrounding whitespace and 20 duplicate rows. Published rate values are unchanged."
FILES = ("ecb_fx_demo_errors.csv", "ecb_fx_demo_errors.xlsx", "ecb_fx_original.csv", "ecb_fx_original.xlsx")


def metadata():
    return json.loads((ROOT / "ecb_fx_manifest.json").read_text())


def original():
    manifest = metadata()
    content = (ROOT / "ecb_fx_original.csv").read_bytes()
    if hashlib.sha256(content).hexdigest() != manifest["sha256"]:
        raise ValueError("Public sample checksum mismatch.")
    return pd.read_csv(ROOT / "ecb_fx_original.csv")


def demo_frame():
    frame = original()
    frame.loc[::10, "observation_date"] = frame.loc[::10, "observation_date"].str.replace("-", "/", regex=False)
    frame.loc[::12, "base_currency"] = "  EUR  "
    return pd.concat([frame, frame.iloc[1:21]], ignore_index=True)


def write_workspace():
    clean, demo = original(), demo_frame()
    demo.to_csv(ROOT / FILES[0], index=False)
    demo.to_excel(ROOT / FILES[1], index=False)
    clean.to_excel(ROOT / FILES[3], index=False)
