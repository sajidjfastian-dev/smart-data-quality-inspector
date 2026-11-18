# Smart Data Quality Inspector

## Run on Replit

- Runtime: Python 3.12 (the existing app and pinned dependencies work with it).
- Dependencies: `requirements.txt`, installed into Replit's managed Python environment.
- Explicit transitive security pins in `requirements.txt` keep fresh installs on patched versions. Reserve unit-test runs for pre-publish verification; check dependency consistency after dependency changes.
- Use the **Run** button to start the **Start application** workflow.
- Command: `python -m streamlit run serve.py --server.corsAllowedOrigins "https://${REPLIT_DEV_DOMAIN}"`
- Streamlit binds to `0.0.0.0:5000` through `.streamlit/config.toml`.
- The workflow explicitly permits the Replit preview origin while preserving Streamlit's CORS and XSRF protections.

## Project constraints

- Display application dates as YYYY-MM-DD; include HH:mm where useful, such as submission dates and timeline events, using Asia/Dubai. Do not reformat original uploaded data merely for UI consistency.

- Keep the existing standalone Streamlit structure and dependency pins.
- Private-file inspection remains session-only. Shared synthetic examples use the existing PostgreSQL database; real SSO and production writes remain disabled.
- Uploaded datasets and optional AI credentials stay in the active Streamlit session.
- The optional AI assistant endpoint is configured by the user in the sidebar; do not add invented credentials or enable dataset sharing automatically.
- Do not use Docker or a virtual environment on Replit. The Docker instructions in the original README are for external local hosting.

## Quick verification

- Open Preview and confirm the upload workspace renders.
- Select **Explore sample workspace** to exercise analysis without uploading data.
- The Streamlit health endpoint is `/_stcore/health`.

## Publishing

- Production command: `python -m streamlit run serve.py --server.address=0.0.0.0 --server.port=5000 --server.headless=true`.
- Do not use `python app.py`: it executes outside the Streamlit server and fails publishing health checks.
- Publishing command changes take effect only when the user republishes.

## Shared synthetic demo

- The ASGI entrypoint adds the read-only `/api/demo/sample` endpoint to the existing Streamlit service.
- `python scripts/seed_demo.py --development-schema` explicitly prepares the development schema and idempotent 520-row/20-request seed. The post-merge script runs it. Never use this flag against production.
- On a future Publish, Replit introspects and applies the development schema to its managed production database. Do not add custom production migrations or deploy-build DDL.
- Before the ASGI service accepts requests, its lifespan runs the **data-only** seed (equivalent to `python scripts/seed_demo.py` without the development flag). This enables a fresh database after Publish has applied its schema. A transaction/advisory lock protects concurrent starts; an existing catalog returns without overwriting records. No schema changes occur during startup or HTTP requests.
- No production database or published app was changed during development. Initialization will run against that environment only when the user publishes.
- Only the server-owned sample import is eligible for database persistence. Private uploads, arbitrary API imports, credentials, custom-rule text, and assistant conversations remain session-only.
- Shared samples use catalog-validated standard checks and safe fixes. For custom rules, the UI offers a private session-only copy rather than persisting free text.
- Shared requests are accessible to all demo sessions. They are not real customer records or authenticated history.
- `inspection_history` and its fail-closed SSO ownership gate are separate and unchanged.
- User instruction: do unit testing at publish time; do not spend time running unnecessary unit tests during routine changes. Use proportionate browser/manual checks while editing.
