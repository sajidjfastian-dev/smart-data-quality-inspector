"""Only this fixed server-owned URL can grant a synthetic-source capability."""
import http.client
import json
import pandas as pd
from api_connections import ApiConnectionError, MAX_API_BYTES


def fetch_sample():
    conn = http.client.HTTPConnection("127.0.0.1", 5000, timeout=15)
    try:
        conn.request("GET", "/api/demo/sample")
        response = conn.getresponse()
        body = response.read(MAX_API_BYTES+1)
        if response.status != 200 or len(body)>MAX_API_BYTES:
            raise ValueError
        payload = json.loads(body)
        if payload["source"] != "quality-v1" or payload["synthetic"] is not True or len(payload["rows"]) < 500:
            raise ValueError
        return pd.DataFrame(payload["rows"], columns=[
            "customer_id","name","email","signup_date","age","annual_spend","region"
        ])
    except (OSError, ValueError, KeyError, http.client.HTTPException):
        raise ApiConnectionError("The database-backed sample API is unavailable. Please retry.") from None
    finally:
        conn.close()
