"""Read-only attributed public-data sample API; uploaded data is never exposed."""
from starlette.responses import JSONResponse
from demo_store import connection, DemoStoreError
from public_sample import SOURCE_ID, metadata


def sample_rows(request):
    try:
        with connection() as conn:
            rows = conn.execute("""SELECT payload FROM dq_demo_rows
                WHERE source_id=%s ORDER BY row_number""", (SOURCE_ID,)).fetchall()
        if not rows:
            raise DemoStoreError("Public sample has not been seeded.")
        return JSONResponse({"source":SOURCE_ID, "synthetic":False, "demo_errors":True, "metadata":metadata(), "count":len(rows),
                             "rows":[row["payload"] for row in rows]},
                            headers={"Cache-Control":"no-store"})
    except DemoStoreError:
        return JSONResponse({"error":"Public sample database unavailable."}, status_code=503)
