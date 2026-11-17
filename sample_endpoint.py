"""Public read-only synthetic fixture API; no uploaded data is accessible here."""
from starlette.responses import JSONResponse
from demo_store import connection, DemoStoreError


def sample_rows(request):
    try:
        with connection() as conn:
            rows = conn.execute("""SELECT payload FROM dq_demo_rows
                WHERE source_id=%s ORDER BY row_number""", ("quality-v1",)).fetchall()
        if not rows:
            raise DemoStoreError("Synthetic sample has not been seeded.")
        return JSONResponse({"source":"quality-v1", "synthetic":True, "count":len(rows),
                             "rows":[row["payload"] for row in rows]},
                            headers={"Cache-Control":"no-store"})
    except DemoStoreError:
        return JSONResponse({"error":"Synthetic sample database unavailable."}, status_code=503)
