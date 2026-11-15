# Smart Data Quality Inspector

A standalone Streamlit workspace for reviewing and cleaning common data-quality issues in CSV and XLSX files.

The visual theme uses accent colors offered by the [Central Bank of the UAE's official website](https://centralbank.ae/en/)—gold `#DAAA00`, turquoise `#00C7B1`, and coral `#F87C56`—with a darker teal for readable controls. The app keeps its own product logo and does not reproduce the CBUAE logo.

## Features

- Drag and drop multiple CSV and XLSX files together, with per-file analysis and a batch workspace summary.
- Load a deterministic 50-row quick sample, or a connected five-file synthetic dataset pack with 57,200 rows across customers, orders, products, support tickets, and web events.
- Download the five-file CSV/XLSX demo pack directly from the sidebar. Its tables share customer, order, and product keys for join and relationship testing.
- Scan for missing values, exact duplicate rows, invalid email addresses, inconsistent/invalid dates, and numeric outliers.
- Adjust Email, Date, and Numeric column rules and tune the IQR outlier multiplier from 1.5 to 3.0.
- Explore clickable KPI details, issue and completeness charts, numeric distributions, column profiles, issue filters, and recommendations.
- Launch a built-in 12-second video demo from the **Watch demo** button; it works offline and needs no external video link.
- Ask the built-in Data Quality Copilot about findings locally, or optionally connect an OpenAI-compatible Chat Completions endpoint for broader natural-language analysis.
- Configure the endpoint URL, model ID, and password-masked API key in sidebar settings. Credentials stay in the current app session and are not written to configuration files.
- Dataset sharing with the configured model is off by default. When explicitly enabled, each assistant request sends the complete active dataset and recent conversation to that endpoint; requests larger than 10 MB are rejected rather than truncated.
- Select any loaded file from the **Active file** workspace dropdown.
- Follow a live file journey that confirms loading, scan completion, detected findings, and the next review/export steps, with progress indicators during file loading, scanning, and fixes.
- See a branded animated inspection loader with row-level progress while quality checks run; safe fixes, preview validation, file loading, assistant responses, and explicitly requested exports also show activity states. Loaders are removed when work completes, and cleaned exports are prepared only when requested.
- Review every row in a dedicated screen with issue cells and duplicate rows highlighted; search across values or show only affected rows.
- Apply selected safe fixes, inspect resolved and remaining issue counts, and download the corrected CSV or XLSX. Invalid emails, dates, and statistical outliers remain for manual review.
- Search/filter issue logs by text and column, then download the matching issue report as CSV.
- Download a cleaned CSV for the active file or a ZIP containing cleaned CSVs for the batch.
- Keep uploaded data in the current app session only. The app does not use a database or authentication, and does not contact an LLM unless a user configures an endpoint and explicitly enables dataset sharing.

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

All records are deterministic synthetic test data. The files include a small number of intentional missing values, duplicates, malformed emails/dates, whitespace-only fields, and numeric outliers so the inspector has issues to find. In the app, select **Load connected big-data sample** to load all five related files together, or **Download 5-file sample pack** to download a ZIP.

## Run locally

Python 3.12 or later is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501`.

## Run with Docker

```powershell
docker build -t smart-data-quality-inspector .
docker run --rm -p 127.0.0.1:8501:8501 smart-data-quality-inspector
```

Open `http://localhost:8501`. The application binds to port 8501 in the container. The host port is restricted to localhost by default; before sharing the app over a network, add authentication and an HTTPS reverse proxy.

## Deploy from GitHub to Streamlit Community Cloud

1. Push this standalone project to its own GitHub repository.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) with the GitHub account that can access the repository.
3. Choose **Create app**, select this repository and its `main` branch, and set the app file to `app.py`.
4. Deploy the application. Community Cloud installs the pinned packages from `requirements.txt`.

For a ready-to-use link to create this application after the repository is pushed, use:

```text
https://share.streamlit.io/deploy?repository=sajidjfastian-dev/smart-data-quality-inspector&branch=main&mainModule=app.py
```

## Data and privacy

This application does not intentionally save uploaded files or model credentials to disk or a database. Files are processed by the running Streamlit session, which means uploads are sent to the server hosting the app. Anyone who can access a public deployment may use the app and submit data to its hosting provider.

The assistant uses local rules by default. If you enter an OpenAI-compatible Chat Completions URL, model ID, and API key under **LLM assistant settings**, the key remains in that app session and is sent only to the configured endpoint. The active dataset is not sent until you explicitly enable **Allow sending the active dataset to this endpoint**. Once enabled, each model request includes every row of the active file and recent conversation; the provider receives that data under its own processing and retention terms. Requests above 10 MB are rejected. Only use a trusted endpoint, and do not send sensitive or regulated data unless you have approval. Keep public deployments access-controlled.
