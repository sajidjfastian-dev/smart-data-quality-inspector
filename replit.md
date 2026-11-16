# Smart Data Quality Inspector

## Run on Replit

- Runtime: Python 3.12 (the existing app and pinned dependencies work with it).
- Dependencies: `requirements.txt`, installed into Replit's managed Python environment.
- Explicit transitive security pins in `requirements.txt` keep fresh installs on patched versions. Run `python -m unittest discover -s tests -v` and `python -m pip check` after dependency changes, then rerun the dependency audit.
- Use the **Run** button to start the **Start application** workflow.
- Command: `python -m streamlit run app.py --server.corsAllowedOrigins "https://${REPLIT_DEV_DOMAIN}"`
- Streamlit binds to `0.0.0.0:5000` through `.streamlit/config.toml`.
- The workflow explicitly permits the Replit preview origin while preserving Streamlit's CORS and XSRF protections.

## Project constraints

- Keep the existing standalone Streamlit structure and dependency pins.
- No database, authentication service, or secrets are needed for the core app.
- Uploaded datasets and optional AI credentials stay in the active Streamlit session.
- The optional AI assistant endpoint is configured by the user in the sidebar; do not add invented credentials or enable dataset sharing automatically.
- Do not use Docker or a virtual environment on Replit. The Docker instructions in the original README are for external local hosting.

## Quick verification

- Open Preview and confirm the upload workspace renders.
- Select **Explore with 50-row quick sample** to exercise analysis without uploading data.
- The Streamlit health endpoint is `/_stcore/health`.
