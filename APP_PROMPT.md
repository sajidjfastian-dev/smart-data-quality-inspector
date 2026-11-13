# Smart Data Quality Inspector — Complete Application Prompt

Build a polished, single-file Python web application called **Smart Data Quality Inspector** using Streamlit. Keep all application logic in `app.py`. Use `pandas`, `numpy`, `openpyxl`, and `plotly`. Do not add a database, user authentication, third-party analytics, or an AI/LLM API.

## Purpose and visual design

Create a wide, responsive data-quality workspace that lets a user load one or more tabular files, inspect common quality problems, explore issue details and analytics, and download cleaned copies. Use an elegant modern visual theme with a soft cool-neutral canvas, white cards, teal accents, legible typography, restrained shadows, rounded corners, and an original custom brand mark combining a small chart with a quality-check symbol. Show the brand in the page header and sidebar. Make the interface keyboard-accessible and provide descriptive labels and button help text.

## Input and sample data

- Allow users to drag and drop or browse multiple CSV and `.xlsx` files from the sidebar. Read CSV files with UTF-8 BOM support and Excel files with `openpyxl`. Show file-batch loading progress and a clear, actionable error for every file that cannot be read; continue processing other valid files in the batch.
- Add a **Load Sample Messy Dataset** button. Generate a deterministic, 50-row sample dataframe with numeric identifiers and measurements, text fields, and email/date fields. Intentionally include missing values, blank/whitespace-only strings, an exact duplicate row, malformed email addresses, valid dates in inconsistent formats, an invalid date, and an obvious numeric outlier.
- Also include a deterministic, downloadable multi-file demo pack of around five sizeable CSV/XLSX tables with synthetic records. Make the tables relationally connected with shared customer, order, and product keys; describe the relationships and offer both a ZIP download and a one-click option to load all files as a workspace.
- Retain the selected dataset across Streamlit reruns. If the sample is loaded while an upload is still selected, keep the sample selected instead of immediately replacing it with the previously uploaded file.
- Let users select which file in the loaded batch to analyze. Re-run checks independently for each selected file, show a batch overview of file count and total rows, and clearly show the active dataset name, row count, and column count. Gracefully handle empty datasets and files that cannot be parsed.
- Keep an always-visible, clearly labeled `Active file` dropdown in the workspace so any loaded file can be selected for inspection.
- Keep the quick sample available alongside the connected multi-file sample so users can try either a fast walkthrough or larger batch analysis.

## Automated quality scanner

Scan each non-empty dataset and detect:

1. **Missing values:** native null/NaN values and strings containing only whitespace. Report them in the issue log.
2. **Exact duplicate rows:** compare all columns and report every duplicate occurrence after the first. Display one-based row numbers.
3. **Email formats:** use a practical regular expression to flag non-empty invalid email values in columns configured as Email.
4. **Date formats:** parse common real-world date string formats. Report unparseable non-empty values and valid strings whose format differs from the most common valid format in the selected Date column.
5. **Numeric outliers:** compute Q1, Q3, and IQR on numeric values. Flag values outside `Q1 - multiplier * IQR` and `Q3 + multiplier * IQR`.

Each issue must include its one-based `Row Number`, `Column Name`, `Issue Type`, readable `Current Value`, and actionable `Suggested Fix`. Keep the issue table and its column names consistent.

## Sidebar column rules

Provide a **Column Rules** expander in the sidebar with separate multiselect controls for columns treated as Email, Date, and Numeric. Set useful initial selections from column names and data types, but allow users to override them. Manually selected numeric text columns should be parsed numerically for outlier detection.

Include an IQR multiplier slider ranging from **1.5 to 3.0**, with a sensible step. Any changes to selected columns or the multiplier must immediately rerun the analysis and update the overview chart, recommendations, health score, total issue count, and issue log. Reset rules appropriately when a different dataset schema is selected.

## Overview and KPI drill-down

Show four prominent dashboard KPI cards:

- **Data Health Score** from 0% to 100%.
- **Total Rows**.
- **Total Issues Found**.
- **Duplicate Rows**.

Make every KPI card keyboard-accessible and clickable, with clear hover/focus treatment and a short “click to explore” affordance. A selected card opens a detailed panel:

- Health score: explain its calculation and summarize findings by issue type.
- Total rows: show row count, column count, post-deduplication row count, and duplicate percentage.
- Total issues: show breakdowns by issue type and column, plus the full issue list.
- Duplicate rows: show the exact duplicate rows with their original one-based row numbers.

The cards and their detail panels must always reflect the active dataset and current sidebar rules.

Display a Plotly bar chart of issue count per column and a concise, accurate bulleted list of recommendations based on detected issues. Provide a useful success state when no issues are found.

Add a Plotly issue-type chart and missing-value completeness chart, a column profile with inferred type, storage type, missing count/percentage, and unique count, and an interactive numeric distribution histogram with summary statistics. All analytics must update with the active file and current rules. Keep charts legible at narrow/mobile viewport widths.

Add a dedicated data-quality review screen that displays every row in the active file and visually highlights cells with detected issues and exact duplicate rows. Provide selectable safe fixes for exact duplicates, whitespace trimming, missing numeric values (column median), and valid date-format standardization. Apply fixes to a copy, show remaining findings in the fixed preview, preserve the original dataset, and let users download a fixed CSV or XLSX matching the active file type. Keep malformed emails, invalid dates, and statistical outliers highlighted for manual review rather than inventing corrections.

Make review convenient for larger files with a cross-column text search and an opt-in **Show rows with findings only** filter while keeping all rows visible by default. Show rows removed, findings resolved, and findings needing manual review after applying fixes. In Issue Logs, support text search and column filtering, and allow downloading the currently filtered issue report as CSV.

## Navigation and issue log

Use these tabs:

1. `Overview Dashboard`
2. `Issue Logs`
3. `Data Quality Review`
4. `Data Preview & Export`

In the Issue Logs tab, provide a dropdown filter for Issue Type, a useful showing/total count, and a readable table with exactly these issue columns:

- `Row Number`
- `Column Name`
- `Issue Type`
- `Current Value`
- `Suggested Fix`

Handle the empty-issue state cleanly.

## Cleaning and export

In Data Preview & Export:

- Preview the uploaded or sample data.
- Offer a **Download Cleaned CSV** action.
- For a multi-file workspace, also offer a ZIP download containing a cleaned CSV for every loaded file.
- Create the downloaded data by removing exact duplicate rows, trimming leading/trailing whitespace from text, and filling missing numeric values with each numeric column’s median where available.
- Do not silently coerce or “fix” malformed email/date values or numeric outliers; present those as review recommendations instead.
- Preserve the original uploaded data for issue reporting and preview. Clean a copy for export.

## Implementation and delivery constraints

- Keep all app behavior and UI code inside `app.py`; keep only dependency declarations and project/deployment documentation in their respective files.
- Pin dependencies in `requirements.txt` for a reproducible Streamlit Community Cloud or container deployment.
- Include a Dockerfile that installs dependencies, runs as a non-root user, binds Streamlit to `0.0.0.0:8501`, and exposes a health check.
- Include a README with local run instructions, Docker build/run instructions, GitHub repository setup steps, and Streamlit Community Cloud deployment steps. Explain that public hosting exposes data uploaded to the app to the hosting provider and that this app intentionally does not retain files in a database.
- Do not include credentials, secrets, sample customer data files, or unrelated monorepo contents in the standalone deployment repository.

## Validation checklist

1. Compile `app.py` and run the Streamlit app in a test harness without exceptions.
2. Verify that the sample contains exactly 50 rows and the expected intentional data defects.
3. Verify that missing values, malformed emails, inconsistent and invalid dates, numeric outliers, and exact duplicates appear with correct row numbers.
4. Verify that changing the Email/Date/Numeric selections or IQR multiplier updates KPIs, chart, recommendations, and issue log.
5. Verify that all four KPI buttons open the correct details, including actual duplicate rows.
6. Verify that issue filtering works and that cleaned CSV removes duplicates, trims text, and fills missing numeric values with the median without modifying source data.
7. Verify that all four named tabs render and that multiple CSV and XLSX uploads are handled gracefully, including mixed valid and invalid files.
8. Verify that the connected sample pack contains five CSV/XLSX files, has shared relational keys without broken references, can be downloaded as a ZIP, and loads all files into the workspace.
9. Verify that the Active file dropdown switches among all loaded files, the review screen shows all rows with issue styling, selected fixes update a copy, and fixed CSV/XLSX downloads open correctly without modifying source data.
10. Build and run the Docker image, then check the Streamlit health endpoint.
