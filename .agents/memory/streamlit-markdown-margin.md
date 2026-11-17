---
name: Streamlit markdown negative margin
description: Why custom HTML blocks rendered with st.markdown can collapse to ~1px height.
---
Streamlit gives markdown containers a -1rem bottom margin to offset paragraph margins. HTML blocks without a `<p>` (divs/spans) then collapse to ~1px and overlap the next element.

**Why:** cost several debugging rounds on the sidebar account panel.

**How to apply:** for custom HTML blocks, set `margin-bottom: 0` on that `[data-testid="stMarkdownContainer"]` (scoped by the parent key class). Also: an f-string/constant first argument is required for the Arabic auto-translation of app markup — passing `"...".replace(...)` silently skips translation.
