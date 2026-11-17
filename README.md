# Smart Data Quality Inspector

A standalone Streamlit workspace for reviewing and cleaning common data-quality issues in CSV and XLSX files.

The visual theme uses accent colors offered by the [Central Bank of the UAE's official website](https://centralbank.ae/en/)—gold `#DAAA00`, turquoise `#00C7B1`, and coral `#F87C56`—with a darker teal for readable controls. The app keeps its own product logo and does not reproduce the CBUAE logo.

The product mark combines a data grid, inspection lens, and analytics signal, shown in the page header, sidebar, and browser tab. The sidebar retains Streamlit's collapse control without a separate colored header banner; Streamlit's Deploy control is hidden because deployments are managed locally.

## Features

- Drag and drop multiple CSV and XLSX files together, with per-file analysis and a batch workspace summary.
- Load a connected five-file synthetic dataset pack with 57,200 rows across customers, orders, products, support tickets, and web events.
- The five sample tables share customer, order, and product keys for join and relationship testing.
- Scan for missing values, exact duplicate rows, invalid email addresses, inconsistent/invalid dates, and numeric outliers.
- Use the settings icon at the bottom of the sidebar to turn built-in checks on or off, adjust Email, Date, and Numeric column rules, and tune the IQR outlier multiplier from 1.5 to 3.0.
- Add, edit, or delete custom per-file rules: required text, allowed values, or minimum and maximum numeric limits. Custom findings are included in scans and issue logs for manual review; empty values are covered separately by the missing-values check. Rules remain in the current session.
- Explore clickable KPI details, issue and completeness charts, numeric distributions, column profiles, issue filters, and recommendations.
- Launch a built-in silent video demo from the **Watch demo** button; it works offline and shows the current landing page and connected sample workspace.
- Ask the built-in Data Quality Copilot about findings locally, or optionally connect an OpenAI-compatible Chat Completions endpoint for broader natural-language analysis.
- Use the settings icon in the sidebar to configure an OpenAI-compatible endpoint URL, model ID, and password-masked API key. Credentials stay in the current app session and are not written to configuration files.
- In settings → **Data APIs**, load data from a public HTTPS GET endpoint as JSON, CSV, or Excel. JSON can be a top-level array of objects or an array under a dot-separated object path; nested objects are flattened. **Try sample API** reads ten public sample users from JSONPlaceholder.
- Configure a destination API and explicitly approve sending the active original or fixed copy as JSON or CSV via POST or PUT. A successful HTTP response means the endpoint accepted the request, not necessarily that it completed downstream processing. Confirm the destination's expected payload before sending.
- API connections support no authentication, bearer tokens, and API keys in a custom header. Credentials and settings remain in the current session. API requests are limited to public HTTPS on port 443, with redirects and private/local addresses blocked and a 10 MB request/response limit. Pagination, OAuth flows, and custom request-body schemas are not automatic.
- Dataset sharing with the configured model is off by default. Once the active file has been reviewed and sharing explicitly enabled, each assistant request sends a masked copy of the active dataset and recent conversation to that endpoint. Only public HTTPS endpoints on port 443 are allowed; redirects and private addresses are blocked. Requests larger than 10 MB are rejected rather than truncated.
- **Data privacy** in settings detects common sensitive column names and recognizable email addresses, phone numbers, IDs, account identifiers, and long card-like numbers. Users can add confidential columns and must review each file before downloading or sharing it. Before review, all data values are hidden. Protected values are replaced with `••••` in previews, findings, downloads, API pushes, and model requests; quality checks still use the unchanged original data.
- Select any loaded file from the **Active file** workspace dropdown.
- Follow a live file journey that confirms loading, scan completion, detected findings, and the next review/export steps, with progress indicators during file loading, scanning, and fixes.
- See a branded animated inspection loader with row-level progress while quality checks run; safe fixes, preview validation, file loading, assistant responses, and explicitly requested exports also show activity states. Loaders are removed when work completes, and cleaned exports are prepared only when requested.
- Review every row in a dedicated screen with issue cells and duplicate rows highlighted; search across values or show only affected rows.
- Apply selected safe fixes, inspect resolved and remaining issue counts, and download the corrected CSV or XLSX. Invalid emails, dates, and statistical outliers remain for manual review.
- Search/filter issue logs by text and column, then download the matching issue report as CSV.
- Download a cleaned CSV for the active file or a ZIP containing cleaned CSVs for the batch.
- Keep uploaded data in the current app session only. A PostgreSQL inspection-history foundation is prepared, but history saving and access are disabled until organisation SSO and scheduled retention cleanup are configured. No external LLM is contacted unless a user configures an endpoint and explicitly enables dataset sharing.

## Inspection history preparation

Open **Inspection history** in the sidebar to see the setup status. After an approved SSO integration is implemented, the prepared controls will let signed-in users explicitly save aggregate inspection summaries, view their own summaries, and delete them with confirmation. There is no file recovery: uploaded files, filenames, column names, cell values, custom-rule contents, and model conversations are excluded.

The retention policy is **30 days**. Reads exclude expired summaries, and database operations remove expired rows. `scripts/purge_inspection_history.py` is prepared for a scheduled cleanup job; **it is not scheduled yet**. Before activating history, configure and verify recurring cleanup independently of user traffic, and review hosting backup retention with the security owner. Application expiry does not erase provider backups.

The production identity adapter is intentionally disabled in `current_history_owner()`. Connecting an IdP alone is insufficient: implement and test server-verified issuer/subject identity, approved-tenant access, logout/session expiry, and private query isolation before enabling it. Never use user-entered email addresses or browser/session-state claims as an identity.

`db/inspection_history.sql` is the schema source and has been applied to development. There is no runtime schema creation. Managed production schema changes use the normal Publish flow. The app has not been published as part of this work.

See [APP_PROMPT.md](./APP_PROMPT.md) for the complete application prompt and acceptance criteria.
For a credit-conscious, two-day Replit build plan, use [REPLIT_PHASED_PROMPT.md](./REPLIT_PHASED_PROMPT.md) and submit one phase at a time.
For implementation details, scan and cleaning behavior, data handling, deployment, and verification guidance, see the [Technical Documentation](./TECHNICAL_DOCUMENTATION.md).

## Technical demo presentation

The concise presentation covers the user workflow, quality checks, dashboards, safe fixes, architecture, technology stack, session-only data handling, privacy notes, and Docker/GitHub deployment:

- [Smart Data Quality Inspector technical demo (PowerPoint)](./Smart_Data_Quality_Inspector_Technical_Demo.pptx)
- The web app also includes a short, silent MP4 walkthrough with play/pause controls for judge demonstrations.
- [Open the web demo video directly](./demo_media/smart_data_quality_demo.mp4)

## Large synthetic test data

The five generated sample files are available individually:

| File | Format | Rows | Relationships |
|---|---:|---:|---|
| [customers.csv](./sample_data/customers.csv) | CSV | 5,000 | Customer keys used by orders, support tickets, and web events |
| [orders.xlsx](./sample_data/orders.xlsx) | Excel | 20,000 | References customers and products; order keys used by tickets |
| [products.csv](./sample_data/products.csv) | CSV | 1,200 | Product keys used by orders and web events |
| [support_tickets.xlsx](./sample_data/support_tickets.xlsx) | Excel | 6,000 | References customers and orders |
| [web_events.csv](./sample_data/web_events.csv) | CSV | 25,000 | References customers and products |

All records are deterministic synthetic test data. The files include a small number of intentional missing values, duplicates, malformed emails/dates, whitespace-only fields, and numeric outliers so the inspector has issues to find. In the app, select **Explore sample workspace** to load all five related files together. The files can also be downloaded individually above.

## Run locally

Python 3.15.2 or later in the 3.15 series is recommended for local development.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501`.

## Regression tests

Install the test dependencies and a Chromium browser, then run:

```sh
python -m pip install -r requirements-test.txt
python -m playwright install chromium
python -m unittest discover -s tests -v
```

The Streamlit AppTest tests run `app.py` directly without a browser or running
server. They cover the empty workspace, deterministic 50-row sample findings,
default and individually selected safe fixes, original-data integrity, reruns,
sample reloads, and isolation between sessions. Each test uses a fresh session;
no database, credentials, or external assistant is required. Separate browser
tests start an isolated server, click the fixed CSV/Excel and batch ZIP download
buttons, and check their filenames and contents. Set
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` to use an existing Chromium executable instead
of the browser installed by Playwright.

## Run with Docker

```powershell
docker build -t smart-data-quality-inspector .
docker run -d --name smart-data-quality-inspector --restart unless-stopped -p 127.0.0.1:8501:8501 smart-data-quality-inspector
```

Open `http://localhost:8501`. The application binds to port 8501 in the container, while the host port is restricted to localhost by default. To update an existing local container, stop and remove it before running the new image. Before sharing the app over a network, add authentication and an HTTPS reverse proxy.

## Deployment workflow

Deployment is managed on the local server with Docker. The Streamlit Deploy
control is intentionally hidden, and pushing to GitHub updates source code
only; it does not trigger a cloud deployment. Keep the Docker host binding on
`127.0.0.1` unless a separately secured network-access setup is in place.

## Data and privacy

This application does not intentionally save uploaded files or model credentials to disk or a database. Files are processed by the running Streamlit session, which means uploads are sent to the server hosting the app. Anyone who can access a public deployment may use the app and submit data to its hosting provider.

The assistant uses local rules by default. A configured model receives a masked copy only after the user reviews sensitive columns and explicitly opts in. Model requests may also contain questions, recent conversation, column names, and aggregate profiles. The masking detector cannot identify every name, identifier, unstructured value, or confidential field: users must select additional columns and must not type sensitive data into questions. Filenames and column names are not generally anonymized. Providers receive requests under their own processing and retention terms; use only approved endpoints.

The original data remains in server memory for inspection. Masking is not encryption, authentication, access control, anonymization, or a compliance certification. This app has no built-in login; do not use real sensitive or regulated data until the deployment, access, retention, and processing arrangements have been approved by the organisation's security and legal owners. Regulatory obligations depend on the organisation and data involved.
