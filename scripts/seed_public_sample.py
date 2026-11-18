"""Add a versioned public-data catalog without altering existing request history."""
from copy import deepcopy
from psycopg.types.json import Jsonb
from demo_store import connection
from demo_codec import encode
from public_sample import SOURCE_ID, LABEL, demo_frame, metadata
from scripts.seed_demo import build_catalog
import request_workflow as flow


def seed_public():
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(460046)")
        if conn.execute("SELECT 1 FROM dq_demo_catalog WHERE id=%s", (SOURCE_ID,)).fetchone():
            return
        frame = demo_frame()
        catalog = build_catalog(frame.to_dict("records"), public_source=SOURCE_ID)
        catalog["metadata"] = metadata()
        for variant in catalog["variants"].values():
            variant["file"] = LABEL
            variant["protected"] = set()
        conn.execute("INSERT INTO dq_demo_catalog VALUES (%s,%s)", (SOURCE_ID, Jsonb(encode(catalog))))
        for i, row in enumerate(frame.to_dict("records"), 1):
            conn.execute("INSERT INTO dq_demo_rows VALUES (%s,%s,%s)", (SOURCE_ID, i, Jsonb(row)))
        for i in range(4):
            session = f"{SOURCE_ID.upper()}-{i+1:02}"
            conn.execute("INSERT INTO dq_demo_sessions(id,synthetic_history) VALUES (%s,true)", (session,))
            state = {"demo_user":"Sajid", "demo_role":"Submitter"}
            # Do not collide with either existing history or live request references.
            while True:
                ref = flow.new_request(state)
                if not conn.execute("SELECT 1 FROM dq_demo_requests WHERE reference=%s", (ref,)).fetchone():
                    break
            record = state["demo_requests"][ref]
            record.update(file=LABEL, source_id=SOURCE_ID, synthetic=True, session_id=session)
            variant = "original" if i == 0 else "fix-1111"
            flow.save_draft(state, ref, deepcopy(catalog["variants"][variant]))
            if i:
                flow.submit(state, ref)
            if i >= 2:
                state["demo_role"] = "Approver"
                flow.owner_decision(state, ref, True)
            if i == 3:
                flow.advance(state, ref, "ticket")
                flow.advance(state, ref, "cab")
            record["revisions"][-1]["variant"] = variant
            conn.execute("INSERT INTO dq_demo_requests(reference,session_id,payload) VALUES (%s,%s,%s)",
                         (ref, session, Jsonb(encode(record))))
        print(f"Added {len(frame)} ECB observations and four public-data example requests; prior history preserved.")
