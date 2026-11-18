"""Native, localized entry point for the data-quality assistant.

The caller supplies counts for the active copy and handles the returned prompt.
This module does not access data, conversation state, or model settings.
"""

from localization import native as st, translate


_STYLES = """
<style>
.st-key-data_assistant_header {
    --da-ink: #194e45;
    --da-muted: #49675f;
    --da-teal: #146b5c;
    --da-line: #ccdcd2;
    padding: clamp(16px, 1.5vw, 22px);
    border: 1px solid var(--da-line);
    border-block-start: 3px solid var(--da-teal);
    border-radius: 14px;
    background: #fcfaf2;
    color: var(--da-ink);
}
.st-key-data_assistant_header h3 {
    color: var(--da-ink);
    font-family: inherit;
    font-size: clamp(24px, 1.8vw, 32px);
    line-height: 1.35;
    letter-spacing: -.015em;
    padding-block: 0;
    margin-block: 0;
}
.st-key-data_assistant_header [data-testid="stMarkdownContainer"] p {
    color: var(--da-ink);
    font-size: clamp(16px, 1vw, 20px);
    line-height: 1.65;
}
.st-key-data_assistant_header [data-testid="stCaptionContainer"] p {
    color: var(--da-muted);
    font-size: clamp(15px, .95vw, 18px);
    line-height: 1.65;
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
}
.st-key-data_assistant_header .stButton > button {
    width: 100%;
    min-height: 48px;
    height: auto;
    justify-content: flex-start;
    padding: 10px 14px;
    border: 1px solid #b9d0c1;
    border-radius: 8px;
    background: #eef6f0;
    color: var(--da-ink);
    box-shadow: none;
    transform: none;
    transition: none;
}
.st-key-data_assistant_header .stButton > button p {
    color: inherit;
    font-size: clamp(16px, 1vw, 19px);
    font-weight: 650;
    line-height: 1.5;
    text-align: start;
    white-space: normal;
    overflow-wrap: anywhere;
}
.st-key-data_assistant_header .stButton > button:hover:not(:disabled) {
    background: #e1eee4;
    border-color: var(--da-teal);
    color: #105749;
    transform: none;
}
.st-key-data_assistant_header :is(button, summary):focus-visible {
    outline: 3px solid #96721d;
    outline-offset: 3px;
}
.st-key-data_assistant_header [data-testid="stExpander"] {
    border: 1px solid #d8c58b;
    border-radius: 8px;
    background: #fcfaf2;
    box-shadow: none;
}
.st-key-data_assistant_header [data-testid="stExpander"] summary {
    min-height: 48px;
    color: var(--da-ink);
}
.st-key-data_assistant_header [data-testid="stExpander"] summary p {
    color: inherit;
    font-size: 16px;
    font-weight: 600;
}
.st-key-data_assistant_header [data-testid="stColumn"] {
    min-width: 0;
}
@media (max-width: 767px) {
    .st-key-data_assistant_header [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap;
        gap: 12px;
    }
    .st-key-data_assistant_header [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        flex: 1 1 100% !important;
        width: 100% !important;
    }
}
@media (forced-colors: active) {
    .st-key-data_assistant_header :is(button, summary):focus-visible {
        outline-color: Highlight;
    }
}
</style>
"""

_PROMPTS = (
    "Summarize my data",
    "What should I fix first?",
    "What changed after fixes?",
    "Which quality rules are active?",
    "Is this ready for review?",
    "What can I ask?",
)


def render_assistant_header(
    has_fixed: bool, rows: int, findings: int, remote: bool
) -> str | None:
    """Render once per page; return the clicked, translated question, if any.

    ``rows`` and ``findings`` are counts for the original or corrected copy
    selected by the caller. ``remote`` means connected-model mode is active,
    not merely configured. Prompt keys stay stable across copy/mode changes.
    """
    selected_prompt = None
    with st.container(key="data_assistant_header"):
        st.markdown(_STYLES, unsafe_allow_html=True)
        st.subheader(translate("Your data assistant"))
        st.markdown(
            translate(
                "Chat about your data, findings, and possible next steps."
            )
        )
        copy_label = translate("Corrected copy" if has_fixed else "Original file")
        mode_label = translate("Connected AI" if remote else "Local data assistant")
        st.caption(
            translate("{0} · {1} rows · {2} findings · {3}").format(
                copy_label, f"{rows:,}", f"{findings:,}", mode_label
            )
        )
        st.caption(
            translate(
                "Connected mode uses your configured model. Responses need review; "
                "the assistant does not approve your file."
            )
            if remote
            else translate(
                "Local answers use your file, scan results, and enabled rules—not "
                "an external AI model. The assistant does not approve your file."
            )
        )
        for row_start in (0, 3):
            columns = st.columns(3)
            for offset, column in enumerate(columns):
                index = row_start + offset
                with column:
                    question = translate(_PROMPTS[index])
                    if st.button(
                        question,
                        key=f"data_assistant_suggestion_{index}",
                        width="stretch",
                    ):
                        selected_prompt = question
        with st.expander(translate("Tips for questions about columns"), expanded=False):
            st.markdown(
                translate(
                    "Use the exact column names from your file. Ask for a numerical "
                    "summary of a named column, or an average grouped by a named "
                    "category. For example, if those columns exist: "
                    "“Summarize Revenue” or “Average Revenue by Region”. "
                    "Answers depend on the available data and active mode."
                )
            )
    return selected_prompt
