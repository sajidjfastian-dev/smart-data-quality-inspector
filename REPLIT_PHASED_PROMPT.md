# Replit Prompt: Smart Data Quality Inspector

Use the prompts below **one phase at a time**. Do not paste all phases into Replit at once. After each phase, run the app, check the acceptance points, and save a working version before continuing.

## Project goal

Build a simple, polished Python web app called **Smart Data Quality Inspector** using Streamlit. Users should be able to upload CSV or Excel files, find data-quality problems, understand them, safely clean a copy, and download the result.

Use the latest Python version already available in Replit. Keep the application code in `app.py`. Use Streamlit, pandas, NumPy, openpyxl, and Plotly. Keep the app simple and avoid unnecessary packages. Do not add a database, user login, external AI service, or paid API. Keep uploaded data in the current app session and explain that the hosting service receives files users upload.

## Instructions for every phase

- First inspect the current project. Keep working features; do not rewrite the whole app.
- Implement **only the phase below**. Do not start a later phase.
- Reuse installed packages. Install only packages needed for this phase.
- Keep code clear and put app behavior in `app.py`.
- Run the app and fix errors before finishing.
- Loading indicators must only be visible while work is running. Remove animated loader markup and mark/collapse status when work completes; never leave a spinner running on the finished screen.
- Do not create cleaned files or batch ZIPs automatically during normal page rendering. Prepare larger exports only after the user requests them, show progress while preparing, then stop the loader.
- Cache completed scan/export results in the current session when practical so changing tabs does not repeat expensive work. Recalculate when the active file or its rules change.
- Report briefly what changed, how it was tested, and any remaining problem.
- Stop after the phase is complete and wait for me to request the next phase.

---

## Phase 1 — A working app

Create the first small version of Smart Data Quality Inspector.

- Set up a wide Streamlit page with a clear title and clean layout.
- Let a user upload one CSV or `.xlsx` file.
- Read CSV with pandas and Excel with pandas/openpyxl. Show a clear message if reading fails.
- Show the file name, row count, column count, and a preview of the data.
- Add a button to load a small, generated 50-row sample dataset.
- Keep everything in memory during the session. Do not add a database or login.

**Done when:** `streamlit run app.py` works; both the sample and a CSV/Excel file can be viewed without an error.

---

## Phase 2 — Data-quality scanner and rules

Add a scanner for the currently selected file. Show each finding with row number, column name, issue type, current value, and suggested fix.

Check for:

- Missing values, including nulls, NaNs, empty strings, and strings containing only spaces.
- Exact duplicate rows. Report repeated rows after the first and use row numbers starting at 1.
- Invalid email addresses in columns selected as Email.
- Invalid and inconsistent date strings in columns selected as Date.
- Numeric outliers using the IQR method: below Q1 − 1.5 × IQR or above Q3 + 1.5 × IQR.

Add a sidebar **Column Rules** section. Let users choose Email, Date, and Numeric columns. Add an IQR slider from 1.5 to 3.0. Infer sensible starting selections from column names and data types, but allow users to change them.

**Done when:** the 50-row sample intentionally has missing values, a duplicate, bad emails, mixed/invalid dates, and a numeric outlier, and the scanner finds them with correct row numbers.

---

## Phase 3 — Dashboard and issue log

Add these dashboard metrics:

- Data Health Score from 0 to 100. Use `max(0, round(100 * (1 - findings / total_cells)))`.
- Total rows.
- Total issues.
- Duplicate rows.

Make each metric clickable to show a short detail panel. Add Plotly charts for issue counts by column and issue type. Show a short list of useful recommendations.

Add an **Issue Logs** tab with an Issue Type dropdown and a table containing exactly:

`Row Number`, `Column Name`, `Issue Type`, `Current Value`, `Suggested Fix`.

**Done when:** the counts, charts, recommendations, and issue log update when the selected file or Column Rules change. Keep the dashboard readable on small screens.

---

## Phase 4 — Review, safe fixes, and download

Add tabs for **Overview Dashboard**, **Issue Logs**, **Data Quality Review**, and **Data Preview & Export**.

- In Data Quality Review, show all rows and highlight cells with findings. Highlight exact duplicate rows.
- Add search and an option to show only rows with findings.
- Let users choose safe fixes: remove exact duplicates, trim text whitespace, fill missing values in selected numeric columns with the median, and standardize valid dates.
- Apply fixes to a **copy**, never overwrite the original data. Keep invalid emails, invalid dates, and outliers for human review.
- Show rows removed, findings resolved, and findings still needing review.
- Let users download the fixed CSV or Excel file.
- Add a one-click cleaned CSV download that removes exact duplicates, trims text, and fills missing numeric values with the median.

**Done when:** downloaded files contain the selected safe fixes, and the original preview and issue results remain unchanged.

---

## Phase 5 — Multiple files and ready-to-test data

Only add this phase after Phases 1–4 work reliably.

- Allow multiple CSV and Excel uploads, processed as separate files.
- Add an **Active file** dropdown. Changing it updates the dashboard, rules, issue log, review, and downloads.
- Show file-loading progress and a simple journey: file loaded → inspection complete → findings → review → export.
- Keep each loading indicator scoped to its operation; when file loading ends, collapse its status and remove its animation before starting inspection.
- Keep a quick 50-row messy sample.
- If time allows, generate five related synthetic CSV/XLSX demo files with shared IDs and offer a ZIP download and a button to load the sample workspace.
- Let users download cleaned versions of all loaded files as one ZIP.

Avoid huge data generation that makes Replit slow. Keep sample data synthetic; never include real customer information.

**Done when:** users can switch between files and the current file’s results never get mixed with another file’s results.

---

## Phase 6 — Final polish and optional assistant

Do this only if the core app is complete and tested.

- Improve the theme, spacing, typography, labels, and mobile layout. Use a simple professional analytics style.
- Show one clear animated inspection loader with progress during file loading, scanning, applying fixes, and user-requested export preparation. Do not load animation files from external websites. Respect reduced-motion settings where possible.
- At completion, remove the loader and collapse/complete the status panel. Test that there are no active spinners after each operation, including sample loading, scans, fixes, and exports.
- Do not prepare cleaned single-file exports or batch ZIPs during ordinary page loads or tab changes. Prepare them only after an explicit user action; cache the result so it is not rebuilt unnecessarily.
- Add an optional **Data Quality Assistant** tab with quick questions about duplicates, missing values, findings, health score, and recommendations. Answer from the current scan results using local Python logic. Do not connect an external AI service; do not pretend it is a general AI chatbot.
- Add a short privacy note explaining that uploaded data is held in the running session and goes to the server hosting Replit.
- If a container is useful, add a simple Dockerfile. Do not spend time on Docker unless the main app already works.

**Done when:** the interface is understandable without instructions, loaders stop and disappear after work completes, downloads are prepared only on demand, the loader and assistant do not break file switching, and the app still runs successfully.

---

## Optional demo presentation

Only after the app works, create a brief 6–9 slide technical-demo presentation. Explain the user workflow, quality checks, technologies (Python, Streamlit, pandas, NumPy, Plotly, openpyxl), safe fixes, deployment, and where uploaded data is held. Do not add customer data or secrets to the slides.

## Two-day plan to save credits

- **Day 1:** Complete Phases 1–3. Save a working version after each phase.
- **Day 2:** Complete Phase 4, test the full flow, then do Phase 5 only if time allows.
- **Final stretch:** Phase 6 and the presentation are optional. A reliable core app is better than many unfinished features.

## Short instruction to start each phase

Copy this before the phase you want Replit to implement:

> Implement only this phase in my existing project. First inspect the files and keep working features. Make the smallest complete change, run the app, fix errors, tell me what you tested, and stop without starting the next phase.
