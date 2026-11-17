"""Streamlit controls for importing and sending data through public APIs."""

import hashlib
import json

import pandas as pd
from localization import st, translate, language

from api_connections import ApiConnectionError, SAMPLE_API_URL, fetch_api_data, push_api_data
from security_guardrails import mask_dataframe


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
    if st.button(
        "Try sample API", key="sample_external_api", icon=":material/science:",
        help="Fetch ten public sample users from JSONPlaceholder.",
        width="stretch",
    ):
        _queue_import(SAMPLE_API_URL, "JSON", "", "None", "", "", "API sample")

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

    st.divider()
    st.markdown("**Push data to an API**")
    st.caption(
        "Send the active file or its fixed copy using POST or PUT. "
        "Protected columns are masked before sending."
    )
    destination_url = st.text_input(
        "Destination API URL", placeholder="https://api.example.com/records",
        key="destination_api_url",
    )
    method = st.selectbox("Send method", ["POST", "PUT"], key="destination_api_method")
    output_format = st.selectbox("Send format", ["JSON", "CSV"], key="destination_api_format")
    dest_auth, dest_secret, dest_header = _auth_controls("destination_api")
    if data is None:
        st.info("Load a file or API source before pushing data.")
    else:
        copies = ["Original data"] + (["Fixed copy"] if fixed_data is not None else [])
        choice = st.selectbox("Data to send", copies, format_func=lambda value, locale=language(): translate(value, locale), key=f"api_export_copy_{active_dataset}")
        send_data = fixed_data if choice == "Fixed copy" else data
        if choice == "Original data":
            st.caption("This sends a masked copy of the original data without applying fixes.")
        else:
            st.caption("This sends a masked copy produced by the selected fixes.")
        if not privacy_reviewed:
            st.warning("Review sensitive columns in Data privacy before sending data.")
        st.caption(f"Selected: {active_dataset} · {len(send_data):,} rows · {len(send_data.columns):,} columns")
        # Bind consent to both the destination and the exact selected data.
        try:
            data_digest = hashlib.sha256(
                pd.util.hash_pandas_object(send_data, index=True).values.tobytes()
                + repr(tuple(send_data.columns)).encode()
            ).hexdigest()
        except TypeError:
            data_digest = hashlib.sha256(send_data.to_json(orient="split", date_format="iso").encode()).hexdigest()
        consent_key = "approve_api_push_" + hashlib.sha256(
            json.dumps(
                [destination_url, method, output_format, active_dataset, choice, data_digest,
                 dest_auth, dest_header, sorted(map(str, sensitive_columns or ()))], ensure_ascii=False
            ).encode()
        ).hexdigest()
        approved = st.checkbox(
            "I approve sending the selected data to this destination",
            key=consent_key,
        )
        if st.button(
            "Push data to API", key="push_external_api", type="primary",
            width="stretch", disabled=not approved or not privacy_reviewed,
        ):
            if not destination_url.strip():
                st.error("Enter a destination API URL.")
            else:
                with st.spinner("Sending the selected data..."):
                    try:
                        status = push_api_data(
                            destination_url, mask_dataframe(send_data, sensitive_columns or ()), method, output_format,
                            dest_auth, dest_secret, dest_header,
                        )
                    except ApiConnectionError as error:
                        st.error(
                            translate("{0} The destination may have received the request; check it before retrying.").format(translate(str(error)))
                        )
                    else:
                        st.success(f"The destination accepted the request (HTTP {status}).")
    st.caption(
        "API settings and credentials are kept only in this session. Only public HTTPS "
        "addresses are supported; redirects and private network addresses are blocked."
    )
