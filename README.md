# Smart Data Quality Inspector

A standalone Streamlit workspace for reviewing and cleaning common data-quality issues in CSV and XLSX files.

## Features

- Drag and drop multiple CSV and XLSX files together, with per-file analysis and a batch workspace summary.
- Load a deterministic 50-row sample with intentional missing values, duplicates, malformed emails, inconsistent dates, and numeric outliers.
- Scan for missing values, exact duplicate rows, invalid email addresses, inconsistent/invalid dates, and numeric outliers.
- Adjust Email, Date, and Numeric column rules and tune the IQR outlier multiplier from 1.5 to 3.0.
- Explore clickable KPI details, issue and completeness charts, numeric distributions, column profiles, issue filters, and recommendations.
- Download a cleaned CSV for the active file or a ZIP containing cleaned CSVs for the batch.
- Keep uploaded data in the current app session only. The app does not use a database, authentication, or an AI/LLM API.

See [APP_PROMPT.md](./APP_PROMPT.md) for the complete application prompt and acceptance criteria.

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
docker run --rm -p 8501:8501 smart-data-quality-inspector
```

Open `http://localhost:8501`. The application binds to port 8501 in the container. For a public server, use an HTTPS reverse proxy and review access controls before sharing the app.

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

This application does not intentionally save uploaded files to disk or a database. Files are processed by the running Streamlit session, which means uploads are sent to the server hosting the app. Anyone who can access a public deployment may use the app and submit data to its hosting provider. Do not upload sensitive or regulated data to a public app; keep the repository and deployment private if the hosting plan supports private apps.
