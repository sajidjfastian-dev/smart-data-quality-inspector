# Replit build prompts (low-token)

## Paste once

Build **Smart Data Quality Inspector**, a polished Streamlit app for inspecting and safely cleaning CSV/XLSX data.

- Keep app logic in `app.py`; use Python, Streamlit, pandas, NumPy, openpyxl, and Plotly. Use the latest stable Python and mutually compatible stable releases available in Replit. Avoid stale pins, prereleases, and unnecessary packages.
- Use a responsive, cool-neutral canvas with a deep-teal branded header, a contrasting pale-teal band behind its exposed top edge, and restrained gold, turquoise, and coral accents. Use the original product mark: rising chart bars with a gold quality-check badge. Keep Streamlit's sidebar collapse control, but use a compact neutral header area rather than a separate dark banner. Hide Streamlit's Deploy control; deployment is local/Docker-managed. Don't use the CBUAE logo or imply endorsement.
- No database, login, mandatory paid API, or default external AI service. Keep uploads and optional model credentials in session memory. If adding a user-configured OpenAI-compatible model endpoint, require explicit opt-in before sending the full active dataset, disclose provider data handling, and retain the local assistant when sharing is off.
- Implement only the requested phase. Inspect and preserve existing work; don't rewrite working features or start later phases. Run the app, fix errors, briefly report changes/tests, then stop. Keep the bundled demo and project documentation consistent with material UI, privacy, and deployment changes.
- Use clear errors. Loaders must end when work ends; don't build exports during ordinary reruns. Prepare downloads only on request. Cache scans where practical and refresh when file/rules change. Never alter the original when cleaning.

## Send one follow-up at a time

**Phase 1 — Upload:** Build a wide, clean page to upload one CSV/XLSX, show filename, dimensions, and preview, and load a generated 50-row messy sample. Keep data in memory.

**Phase 2 — Scan:** Detect null/NaN/blank/whitespace-only cells, exact duplicate rows (flag repeats after the first; row numbers start at 1), invalid emails, inconsistent/invalid dates, and numeric IQR outliers (default 1.5×IQR). Let users select Email/Date/Numeric columns and set the IQR multiplier (1.5–3); infer sensible defaults. Sample data must exercise every check.

**Phase 3 — Dashboard:** Show health score `max(0, round(100 × (1 − issues / cells)))`, row count, issue count, and duplicate count; Plotly issue counts by column/type; concise recommendations; and an Issue Logs tab with an issue-type filter and exactly these columns: `Row Number`, `Column Name`, `Issue Type`, `Current Value`, `Suggested Fix`. Update results when file or rules change.

**Phase 4 — Review/export:** Add tabs: Overview Dashboard, Issue Logs, Data Quality Review, Data Preview & Export. Highlight findings in rows; support search and show-only-affected. Offer opt-in fixes on a copy: remove duplicates, trim whitespace, median-fill selected numeric columns, and standardize valid dates. Leave invalid emails/dates and outliers for review. Report changes; download cleaned CSV/XLSX. Preserve original data and results.

**Phase 5 — Finish:** Support multiple independent files and an Active file selector that updates all views/rules/exports. Show file journey (loaded → inspected → findings → review → export) with operation-scoped loaders. Keep the 50-row sample; if practical, add five related synthetic CSV/XLSX files, shared IDs, and ZIP download. Add a local, rule-based data-quality assistant for current scan results, plus optional user-configured OpenAI-compatible Chat Completions URL/model/key settings; keep credentials session-only, require explicit dataset-sharing opt-in, preserve local mode, and disclose exactly what is sent. Polish responsive UI with accessible contrast and CBUAE-site accent colors (`#DAAA00`, `#00C7B1`, `#F87C56`); don't use its logo or imply endorsement. On the no-data landing page, replace blank space with a useful welcome panel that explains the upload → inspect → improve workflow and previews the four quality checks; preserve the sidebar upload and sample controls. Add a bundled short demo video only if time permits.

## Use for each phase

`Implement Phase N only from my original prompt. Test it, summarize briefly, and stop.`
