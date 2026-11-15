# Smart Data Quality Inspector — Technical Documentation

## 1. Purpose and scope

Smart Data Quality Inspector is a single-page Python web application built with
Streamlit. It lets a user load CSV or Excel workbooks, inspect common data
quality signals, review affected rows, apply selected conservative fixes to a
copy, and download report or cleaned-file outputs.

The application is intended for interactive profiling and human-guided
correction. Its findings are signals, not proof that a value violates a
business rule. It does not infer domain-specific truth, validate relationships
between uploaded files, or automatically repair invalid email addresses,
invalid dates, or statistical outliers.

## 2. At a glance

| Area | Implementation |
|---|---|
| Application | One Streamlit application module: `app.py` |
| Runtime | Python 3.15.2 recommended |
| Data handling | pandas DataFrames and in-memory byte buffers |
| Numeric and sample calculations | NumPy |
| CSV handling | pandas CSV reader/writer |
| Excel handling | pandas with openpyxl |
| Charts | Plotly Express |
| State | Streamlit session state |
| Persistence | No application database or intentional upload-file persistence |
| Authentication | None |
| External AI | Optional user-configured OpenAI-compatible endpoint; disabled by default |
| Inputs | CSV and XLSX |
| Outputs | CSV, XLSX, issue-report CSV, and ZIP archives |

Dependency versions are pinned in [`requirements.txt`](./requirements.txt).

### Visual theme and brand relationship

The interface takes visual inspiration from the accent colors surfaced by the
[official CBUAE website](https://centralbank.ae/en/): gold `#DAAA00`, turquoise
`#00C7B1`, and coral `#F87C56`. Darker teal tones are used for buttons and
small text to preserve contrast and readability. This is a color-theme
adaptation, not a reproduction of CBUAE's full identity system; the app retains
its own product logo and should not be treated as carrying an official CBUAE
logo or endorsement mark.

The original product mark is a rising three-bar chart with a gold quality-check
badge. It appears in the main header and sidebar; the sidebar keeps Streamlit's
collapse control in a compact, neutral header area rather than adding a second
colored banner. The app hides Streamlit's Deploy control because deployment is
managed through the local server/container workflow.

## 3. Repository layout

```text
SmartDataQualityInspector/
├── app.py
├── requirements.txt
├── Dockerfile
├── README.md
├── APP_PROMPT.md
├── REPLIT_PHASED_PROMPT.md
├── TECHNICAL_DOCUMENTATION.md
├── Smart_Data_Quality_Inspector_Technical_Demo.pptx
├── demo_media/
│   ├── smart_data_quality_demo.mp4
│   └── smart_data_quality_demo.gif
└── sample_data/
    ├── customers.csv
    ├── orders.xlsx
    ├── products.csv
    ├── support_tickets.xlsx
    └── web_events.csv
```

`app.py` contains the UI, data loading, scanning, cleaning, serialization, and
local assistant logic. The `sample_data/` directory contains deterministic
synthetic datasets for demonstration. The prompt documents and presentation
explain product requirements and demo material; they are not required at
runtime.

### Main code responsibilities

| Responsibility | Main functions in `app.py` |
|---|---|
| Quick sample generation | `make_sample_data` |
| Missing-value, date, and numeric parsing helpers | `is_missing`, `parse_date`, `date_shape`, `parse_numeric_series` |
| Type inference and profiling | `infer_column_rules`, `build_column_profile` |
| Finding generation | `scan_data` |
| Safe transformations | `clean_data`, `standardize_date_value` |
| Input/output conversion | `read_data_file`, `read_uploaded_file`, `serialize_data_file` |
| Synthetic workspace and archives | `load_sample_data`, `load_connected_sample_data`, `connected_sample_archive`, `build_cleaned_batch_archive` |
| Local question answering | `answer_data_quality_question` |
| UI, session-state coordination, and Streamlit callbacks | Remaining top-level Streamlit rendering code |

## 4. Application architecture

The application uses a straightforward, single-process Streamlit architecture:

1. **User interaction:** Streamlit renders the sidebar, workspace controls,
   tabs, metrics, tables, charts, and download buttons.
2. **File ingestion:** Uploaded file bytes are read into pandas DataFrames.
   The generated quick sample and bundled sample workspace also become
   DataFrames.
3. **Rule selection:** Column types are inferred as a starting point. Users
   can override Email, Date, and Numeric selections and adjust the outlier
   multiplier.
4. **Inspection:** The scanner evaluates the active DataFrame and returns an
   issue DataFrame plus an exact-duplicate count.
5. **Presentation:** The current scan feeds the dashboard, column profile,
   recommendations, issue explorer, highlighted row review, and assistant.
6. **Optional correction and export:** Selected changes are applied to a copy.
   Serialization happens in memory when the user requests an output.

There is no API server or separate worker service. Streamlit reruns the script
in response to user interactions. DataFrames, rule selections, scan results,
fixed copies, and export-cache entries are associated with the current
Streamlit session.

## 5. User workflow and screens

### Sidebar and workspace

- Upload one or more `.csv` or `.xlsx` files using Streamlit's uploader.
- Load a deterministic 50-row messy sample, or load the five related synthetic
  files bundled with the project.
- Select the active file from the workspace dropdown. The dashboard, rules,
  findings, review, and per-file exports follow the active file.
- Change automatically inferred Email, Date, or Numeric column rules.
- Adjust the IQR multiplier from 1.5 through 3.0.
- Follow status and progress updates during file loading, scanning, fixes, and
  explicitly requested exports.

Files in a multi-file workspace are inspected independently. The bundled
sample files share synthetic keys for users to explore, but the scanner does
not perform cross-file referential-integrity checks or joins.

### Tabs

1. **Overview Dashboard** — clickable KPI details, findings by column and type,
   completeness, recommendations, numeric distributions, and a column profile.
2. **Issue Logs** — filter and search findings, narrow by column, and download
   the visible issue report.
3. **Data Quality Review** — inspect rows with issue cells and duplicate rows
   highlighted; choose safe fixes and compare the fixed copy with the original.
4. **Data Preview & Export** — preview the active dataset and explicitly
   prepare/download cleaned CSV or a multi-file cleaned ZIP.
5. **Data Quality Assistant** — ask supported questions about the active
   dataset and its current inspection results.

The **Watch demo** button in the page header opens a locally bundled, silent
12-second MP4 walkthrough of the upload, scan, dashboard, review, and export
flow. The walkthrough's product mark matches the current rising-chart and
gold-check logo. It includes native playback controls and does not require an
internet connection. The source GIF is also included for direct preview.

## 6. Input handling and type inference

### Supported files

- CSV files are decoded as UTF-8 with an optional UTF-8 byte-order mark and
  loaded with `pandas.read_csv`.
- XLSX files are loaded with `pandas.read_excel` and the openpyxl engine. The
  default pandas behavior reads the first worksheet.
- Empty data and common decoding, parsing, workbook, and file-access errors are
  surfaced to the user rather than treated as valid datasets.
- The upload signature includes the name, byte length, and SHA-256 digest. A
  changed upload batch replaces the session workspace and clears related
  quality and export caches.

### Column-rule inference

Inference provides editable defaults; it is not a permanent schema contract:

- A column name containing `email` is selected as an Email column. Other
  columns can be inferred as Email when at least two non-missing values exist
  and at least 60% match the configured email pattern.
- A name containing `date`, `time`, or `timestamp` is selected as a Date
  column. Otherwise, a column can be inferred as Date when at least two
  non-missing strings exist and at least 70% parse using supported date
  formats.
- Non-boolean numeric dtypes are selected as Numeric. Text columns can also be
  inferred as Numeric when at least two values parse and at least 80% of
  non-missing values parse successfully.
- Date columns are excluded from the Numeric selection.

Users should verify inferred rules, especially for ambiguous or domain-specific
columns. Numeric text parsing removes common currency symbols, commas, and
whitespace; accounting-style parentheses are interpreted as negative values.

## 7. Automated inspection

The scanner returns a table with these columns:

| Field | Meaning |
|---|---|
| `Row Number` | One-based position in the displayed data order |
| `Column Name` | A data column, or `Entire row` for a duplicate |
| `Issue Type` | The category of finding |
| `Current Value` | Display form of the affected value |
| `Suggested Fix` | A conservative next step for the user |

One row in the issue log represents one detected finding. A cell can contribute
more than one finding if it violates different active checks. Duplicate
findings refer to the repeated occurrence after the first copy.

### Missing values

The scanner treats null/NaN values and strings that are empty or contain only
whitespace as missing. It reports each affected cell as `Missing Value`.

### Exact duplicate rows

`DataFrame.duplicated(keep="first")` identifies rows identical across every
column. The first occurrence is retained; every later occurrence is reported
as `Duplicate Row` against `Entire row`. The duplicate KPI is the number of
repeated occurrences, not the number of distinct duplicate groups.

### Email formats

Selected Email columns are checked with a compiled regular expression requiring
a local part, an `@`, and one or more domain labels. Values are stripped for
validation. This is format screening only; it does not confirm that an address
exists, can receive mail, or meets a specific organization's policy.

### Date validity and consistency

Selected Date columns are checked against an explicit list of date and
date-time formats. Non-missing values that do not parse are reported as
`Invalid Date`.

For valid string dates, the scanner identifies the most common recognized
shape in that column. Valid strings with a different shape are reported as
`Inconsistent Date Format`. Existing date/datetime objects are treated as
valid, but are not part of the string-shape comparison. Shape detection is
syntactic and does not resolve business-specific ambiguity such as whether
`03/04/2024` means March 4 or April 3.

### Numeric outliers

Selected Numeric columns are parsed to numeric values where possible. For the
finite parsed values, the scanner calculates the first quartile (`Q1`), third
quartile (`Q3`), and interquartile range (`IQR = Q3 - Q1`). A value is reported
as `Numeric Outlier` when it is strictly below or above:

```text
lower bound = Q1 - multiplier × IQR
upper bound = Q3 + multiplier × IQR
```

The default multiplier is 1.5; the sidebar allows a value from 1.5 to 3.0.
Outlier status is statistical and must not be interpreted as proof of an
incorrect value.

### Findings, recommendations, and score

The dashboard's total issue count is the number of issue-log rows, including
duplicate-row findings. The health score is calculated as:

```text
max(0, round(100 × (1 - findings / total_cells)))
```

where `total_cells` is rows multiplied by columns (using a minimum denominator
of one). It is a simple normalized finding-count indicator, not a weighted
quality standard: multiple checks can flag a cell, and every finding has equal
weight. It should be compared only with these caveats in mind.

Recommendations are generated locally from the current findings. They point
the user toward duplicates, missingness, email/date review, and outlier
verification; they do not prove that a recommended action is appropriate for
the user's business context.

## 8. Safe fixes and cleaning behavior

The Data Quality Review tab applies selected operations to `data.copy()` and
stores the resulting fixed DataFrame separately. The source DataFrame and
original scan remain available.

Available review fixes:

- **Remove exact duplicates:** keep the first identical row and reset the
  resulting row index.
- **Trim whitespace:** strip leading/trailing whitespace from string values.
- **Fill missing selected Numeric values:** calculate the median of parseable
  values in each selected column; fill actual missing values when a median
  exists. Numeric text may be populated with a string representation of the
  median, preserving the existing text-oriented column representation.
- **Standardize valid dates:** convert supported, unambiguous date strings to
  `YYYY-MM-DD` (or `YYYY-MM-DD HH:MM:SS` for recognized date-time strings).
  Invalid values and ambiguous slash/hyphen dates where both first fields can
  be month/day values remain unchanged.

Invalid email values, invalid dates, and statistical outliers are deliberately
not automatically altered. After fixes are applied, the app scans the fixed
copy using the active rules and shows remaining findings. A user can download
the fixed copy in the active file's format (CSV or XLSX).

The **Download a clean copy** control is a one-click, on-demand CSV export. Its
download callback removes exact duplicates, trims string whitespace, and fills
missing values in the selected Numeric columns with the median. It does not
enable date-standardization by default. The original workspace data is not
modified. The multi-file cleaned ZIP applies the basic cleaning defaults to
each file and writes cleaned CSVs into the archive.

## 9. Dashboard, issue report, and assistant

### Dashboard

- **Data Health Score:** formula documented above.
- **Total Rows:** active file row count.
- **Total Issues Found:** issue-log row count.
- **Duplicate Rows:** repeated exact-row occurrences after their first copy.
- Plotly charts show findings by column and issue type, missing percentages,
  and a selected numeric distribution with a box-plot marginal.
- Column profiling reports inferred type, storage dtype, missing count and
  percentage, and unique-value count.

### Issue report

The Issue Logs tab supports issue-type selection, text search, and column
filtering. The download contains the visible, filtered rows of the issue table
as CSV.

### Data Quality Assistant

The assistant uses deterministic local Python logic by default. Users may
optionally configure an OpenAI-compatible Chat Completions endpoint, model ID,
and password-masked API key in the sidebar's **LLM assistant settings**. The
endpoint and key are held in Streamlit session state only and are not written
to files.

Dataset sharing is a separate, explicit opt-in and defaults off. When enabled,
each request sends the complete active dataset, column profile, current
quality-finding counts, recent conversation, and question to the configured
endpoint. This allows broader natural-language analysis, but the provider
receives the uploaded data and applies its own privacy and retention terms. The
app limits the serialized request to 10 MB and rejects oversized requests
rather than silently truncating data. Use only a trusted endpoint and avoid
sending sensitive data without approval. Local mode remains available when
sharing is off or no endpoint is configured.

The app sends a non-streaming OpenAI-compatible Chat Completions request with
a 60-second timeout and does not expose the API key in the UI or assistant
conversation. Provider/network/response errors are surfaced to the user. The
model is instructed to treat dataset cell contents as untrusted data and not
as instructions; its answers are informational and do not alter the dataset.

## 10. State, caching, and loader lifecycle

The app stores its working state in `st.session_state`, including:

- Loaded DataFrames and the active filename.
- Upload signatures used to detect a changed upload batch.
- User-selected rule settings through Streamlit widget state.
- Optional LLM endpoint, model, key, and dataset-sharing consent for the current session.
- Scan results and column profiles for the active file and rule signature.
- Fixed-copy DataFrames and their validation scan results.
- Cleaned single-file and batch export payloads after preparation.

Changing the active file or quality rules selects a matching scan result or
triggers a new scan. Replacing uploaded files resets scan and batch-export
caches. A single-file cleaned CSV is generated by its download callback only
after the user clicks its download button; it is not prepared during ordinary
page rendering.

Progress bars, status containers, and loader placeholders are scoped to active
operations. The application clears loader placeholders and marks status
containers complete or in error at the end of those operations.

Session state is temporary application memory, not durable storage. A server
restart, session expiration, or new session can discard the workspace and
generated files.

## 11. Data handling, privacy, and deployment considerations

The application does not intentionally write uploaded data or model credentials
to disk or a database. It reads uploaded bytes into memory and works with
in-memory DataFrames and buffers. Download artifacts are generated in memory.
No external model is contacted unless a user configures an endpoint and opts in
to dataset sharing. In that case, the complete active dataset and recent
conversation are sent to the configured provider for each assistant request;
review that provider's data-handling terms before enabling the option.

An upload is nevertheless sent to the server hosting Streamlit. Hosting
providers may have their own infrastructure, logging, backups, retention, or
access policies. The app has no user authentication or authorization layer.
Consequently:

- Do not upload sensitive, regulated, or confidential data to an untrusted or
  public deployment.
- Use a private, controlled deployment for sensitive workflows and configure
  hosting/network access controls separately.
- Apply HTTPS when exposing the app over a network.
- Review the deployment provider's privacy and data-retention terms.

### Local run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501`.

### Docker run

```powershell
docker build -t smart-data-quality-inspector .
docker run --rm -p 127.0.0.1:8501:8501 smart-data-quality-inspector
```

The Docker image uses `python:3.15-slim`, installs pinned requirements, copies
the app, synthetic sample data, and local demo media, runs as a non-root
user, exposes port 8501, and defines a Streamlit health check. The example
binds the host port to localhost; add authentication and HTTPS before sharing
the app over a network.

### Replit development

For Replit-based development, use the phased instructions in
[`REPLIT_PHASED_PROMPT.md`](./REPLIT_PHASED_PROMPT.md) and keep the sample data
files available at the relative `sample_data/` directory. Production
deployment is managed on the local server with Docker; the Streamlit Deploy
control is hidden and GitHub is used for source control, not cloud deployment.

## 12. Performance and operational limits

Inspection is performed in the Streamlit process over pandas objects. Work
increases with dataset rows, columns, and the number of enabled checks. The
sample workspace contains 57,200 synthetic rows in total, but performance and
maximum practical dataset size depend on the host's available memory, CPU,
Streamlit configuration, and concurrent sessions.

The application is intended for interactive datasets that fit comfortably in
memory. It is not a distributed processing engine, streaming ingestion
service, data warehouse, or background job system. Large exports are generated
only when requested, but the export payload still occupies server memory for
the session.

## 13. Testing and manual verification

There is no dedicated test suite in the current repository. Before a demo or
deployment, perform these smoke checks:

1. Start the app and confirm the empty state loads.
2. Load the 50-row sample and verify missing values, duplicate rows, invalid
   emails, mixed/invalid dates, and a numeric outlier are reported.
3. Upload representative CSV and XLSX files and confirm the displayed row and
   column counts.
4. Change an Email, Date, or Numeric rule and the IQR multiplier; confirm the
   scan and dashboard values update.
5. Switch the active file in a multi-file workspace and confirm findings are
   isolated per file.
6. Search and filter the issue log, download an issue report, and compare the
   contents to the visible findings.
7. Apply a safe fix, verify the original remains unchanged, and review the
   remaining findings in the fixed copy.
8. Prepare and download the cleaned CSV, fixed XLSX/CSV, and multi-file ZIP
   where applicable.
9. Confirm progress indicators disappear and status panels complete after
   loading, scanning, fixing, and export work.
10. Ask the assistant about duplicate and missing-value counts and compare its
    answers with the current scan.

## 14. Known limitations

- Inferred column types and regex rules are heuristic and may need manual
  adjustment.
- Date strings can be ambiguous across regional conventions.
- The health score is a simple issue-per-cell calculation, not a certified
  quality metric.
- IQR outliers are distribution-based and may be valid values.
- The scanner checks each file independently and does not enforce foreign keys,
  uniqueness rules beyond whole-row duplicates, or domain-specific constraints.
- XLSX ingestion reads the first worksheet by default; macros, formulas,
  workbook formatting, and multi-sheet relationships are not part of the
  cleaning workflow.
- Fixed XLSX output is a data export, not a fidelity-preserving workbook edit.
- There is no authentication, durable storage, audit log, or multi-user
  collaboration feature.
- The local assistant answers supported questions using current scan results.
  An optional configured OpenAI-compatible endpoint can answer broader
  questions only when dataset sharing is explicitly enabled; that request sends
  the complete active dataset and recent conversation to the chosen provider.

## 15. Related project documentation

- [README and project setup](./README.md)
- [Full application prompt and acceptance criteria](./APP_PROMPT.md)
- [Phased Replit build prompt](./REPLIT_PHASED_PROMPT.md)
- [Technical demo presentation](./Smart_Data_Quality_Inspector_Technical_Demo.pptx)
