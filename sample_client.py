"""Only this fixed, verified server-owned sample grants shared-source provenance."""
import http.client
import json
import pandas as pd
from api_connections import ApiConnectionError, MAX_API_BYTES
from public_sample import SOURCE_ID, demo_frame


def fetch_sample():
    conn = http.client.HTTPConnection("127.0.0.1", 5000, timeout=15)
    try:
        conn.request("GET", "/api/demo/sample")
        response = conn.getresponse()
        body = response.read(MAX_API_BYTES+1)
        if response.status != 200 or len(body)>MAX_API_BYTES:
            raise ValueError
        payload = json.loads(body)
        if payload["source"] != SOURCE_ID or payload["demo_errors"] is not True or payload["count"] != 620 or len(payload["rows"]) != 620:
            raise ValueError
        expected = demo_frame()
        frame = pd.DataFrame(payload["rows"], columns=expected.columns)
        if not frame.equals(expected):
            raise ValueError
        frame.attrs["public_sample_source"] = SOURCE_ID
        return frame
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
        raise ApiConnectionError("The database-backed sample API is unavailable. Please retry.") from None
    finally:
        conn.close()
