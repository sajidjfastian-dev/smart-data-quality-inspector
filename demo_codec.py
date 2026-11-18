"""JSON-only serialization for trusted synthetic records (never pickle)."""
import json
from io import StringIO
import pandas as pd


def encode(value):
    if isinstance(value, pd.DataFrame):
        if value.attrs.get("public_sample_source"):
            return {"__frame_exact__": value.to_json(orient="table", index=False, double_precision=15),
                    "public_sample_source": value.attrs["public_sample_source"]}
        return {"__frame__": value.to_json(orient="table", index=False)}
    if isinstance(value, set):
        return {"__set__": sorted(value)}
    if isinstance(value, dict):
        return {key: encode(item) for key, item in value.items() if key != "_db_version"}
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    return value


def decode(value):
    if isinstance(value, dict):
        if "__frame_exact__" in value:
            frame = pd.read_json(StringIO(value["__frame_exact__"]), orient="table", precise_float=True)
            frame.attrs["public_sample_source"] = value["public_sample_source"]
            return frame
        if "__frame__" in value:
            return pd.read_json(StringIO(value["__frame__"]), orient="table")
        if "__set__" in value:
            return set(value["__set__"])
        return {key: decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode(item) for item in value]
    return value


def stable_roundtrip(value):
    return decode(json.loads(json.dumps(encode(value))))
