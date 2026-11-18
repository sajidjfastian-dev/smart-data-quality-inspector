"""Streamlit controls for importing and sending data through public APIs."""

from localization import st, translate, language

from api_connections import ApiConnectionError, fetch_api_data, push_api_data
from security_guardrails import mask_dataframe
from demo_session import is_signed_in
from review_approval import is_approved, guarded_push, ApprovalRequired


def _auth_controls(prefix):
    mode = st.selectbox(
        "Authentication", ["None", "Bearer token", "API key header"], key=f"{prefix}_auth"
    )
    header_name = ""
    secret = ""
    if mode == "API key header":
        header_name = st.text_input(
            "API key header name", value="X-API-Key", key=f"{prefix}_header"
        ).strip()
    if mode != "None":
        secret = st.text_input(
            "API credential", type="password", key=f"{prefix}_secret",
            help="Kept in this session and sent only to the specified endpoint.",
        )
    return mode, secret, header_name


def _queue_import(url, data_format, json_path, auth_mode, secret, header_name, label):
    with st.spinner("Reading data from the API..."):
        try:
            data = fetch_api_data(url, data_format, json_path, auth_mode, secret, header_name)
        except ApiConnectionError as error:
            st.error(translate(str(error)))
            return
    st.session_state["pending_api_dataset"] = (label, data)
    st.rerun()


def render_api_settings(active_dataset=None, data=None, fixed_data=None,
                        sensitive_columns=None, privacy_reviewed=False):
    st.markdown("**Read data from an API**")
    st.caption(
        "GET a public HTTPS endpoint returning JSON, CSV, or Excel. For JSON, "
        "choose the object path that contains an array of rows."
    )
    if not is_signed_in():
        st.info("Log in to read data from an API.", icon=":material/lock:")
    elif st.session_state.get("demo_role", "Submitter") == "Submitter":
        _render_api_reader()

    _render_api_push(active_dataset, data, fixed_data, sensitive_columns, privacy_reviewed)


def _render_api_reader():
    if st.button(
        "Try sample API", key="sample_external_api", icon=":material/science:",
        help="Load 620 ECB exchange-rate observations with labelled demonstration errors.",
        width="stretch",
        disabled=not st.session_state.get("_persistent_demo_ready"),
    ):
        from sample_client import fetch_sample
        from persistent_demo import register_source
        try:
            data = fetch_sample()
            register_source(st.session_state, data)
            from public_sample import LABEL
            st.session_state["pending_api_dataset"] = (LABEL, data)
            st.rerun()
        except ApiConnectionError as error:
            st.error(translate(str(error)))
    from public_sample import ATTRIBUTION, NOTICE
    st.caption(ATTRIBUTION + " " + NOTICE)

    source_url = st.text_input(
        "Source API URL", placeholder="https://api.example.com/records", key="source_api_url",
    )
    source_format = st.selectbox("Response format", ["JSON", "CSV", "Excel"], key="source_api_format")
    json_path = ""
    if source_format == "JSON":
        json_path = st.text_input(
            "JSON data path", key="source_json_path", placeholder="data.items",
            help="Leave blank for a top-level array; use dot-separated keys for nested arrays.",
        ).strip()
    source_auth, source_secret, source_header = _auth_controls("source_api")
    if st.button("Load data from API", key="load_external_api", width="stretch"):
        if not source_url.strip():
            st.error("Enter a source API URL.")
        else:
            _queue_import(
                source_url, source_format, json_path, source_auth, source_secret,
                source_header, "API data",
            )


def _render_api_push(active_dataset, data, fixed_data, sensitive_columns, privacy_reviewed):
    st.divider()
    st.markdown("**Production changes — demo only**")
    st.info("Live destination writes are disabled in the demo request workflow.")
    st.caption("Submit a request, complete data-owner, service-desk and CAB approvals, then simulate production application from Request list.")
    st.button("Push data to API", key="push_external_api", disabled=True)
