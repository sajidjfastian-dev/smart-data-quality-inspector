"""Session-configured public HTTPS API import and export helpers."""

import http.client
import ipaddress
import json
import re
import socket
import ssl
from io import BytesIO, StringIO
from urllib.parse import urlsplit
from zipfile import BadZipFile

import pandas as pd

MAX_API_BYTES = 10 * 1024 * 1024


class ApiConnectionError(ValueError):
    """A safe, user-facing API configuration or request error."""


def _resolve_target(url):
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        port = parts.port or 443
        if (
            parts.scheme.lower() != "https" or not host or parts.username
            or parts.password or parts.fragment or port != 443
            or any(c in url for c in "\r\n")
        ):
            raise ValueError
        host = host.encode("idna").decode("ascii")
    except (ValueError, UnicodeError):
        raise ApiConnectionError(
            "Enter a valid public HTTPS URL on port 443 without embedded credentials or a fragment."
        ) from None
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(
            host, port, type=socket.SOCK_STREAM
        )}
    except (socket.gaierror, ValueError):
        raise ApiConnectionError("Could not resolve the API host to a public address.") from None
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ApiConnectionError(
            "Only public internet addresses are allowed; private and local addresses are blocked."
        )
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return host, port, sorted(addresses), path


def _auth_headers(mode, secret, header_name):
    headers = {"Accept": "application/json, text/csv, application/octet-stream"}
    if mode == "None":
        return headers
    if not secret or "\r" in secret or "\n" in secret:
        raise ApiConnectionError("Enter a valid API credential without line breaks.")
    if mode == "Bearer token":
        headers["Authorization"] = "Bearer " + secret
    elif mode == "API key header":
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", header_name or ""):
            raise ApiConnectionError("Enter a valid API key header name.")
        if header_name.lower() in {
            "host", "content-length", "transfer-encoding", "connection", "content-type"
        }:
            raise ApiConnectionError("That header name is reserved.")
        headers[header_name] = secret
    else:
        raise ApiConnectionError("Unsupported authentication method.")
    return headers


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to a previously verified IP while verifying TLS for the hostname."""

    def __init__(self, host, address, port):
        super().__init__(host, port=port, timeout=20, context=ssl.create_default_context())
        self._verified_address = address

    def connect(self):
        raw = socket.create_connection((self._verified_address, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def request_public_api(url, method="GET", auth_mode="None", secret="", header_name="", body=None, content_type=None):
    if method not in {"GET", "POST", "PUT"}:
        raise ApiConnectionError("Unsupported API method.")
    if body is not None and len(body) > MAX_API_BYTES:
        raise ApiConnectionError("Data exceeds the 10 MB API request limit.")
    host, port, addresses, path = _resolve_target(url)
    headers = _auth_headers(auth_mode, secret, header_name)
    if content_type:
        headers["Content-Type"] = content_type
    response = None
    connection = None
    try:
        # No redirects or retries: retries could duplicate a successful push, and
        # redirects could send credentials or data to an unapproved destination.
        connection = _PinnedHTTPSConnection(host, addresses[0], port)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise ApiConnectionError("The API returned a redirect. Use its final HTTPS URL directly.")
        if not 200 <= response.status < 300:
            raise ApiConnectionError(f"The API returned HTTP {response.status}. Check your settings and access.")
        content = response.read(MAX_API_BYTES + 1)
        if len(content) > MAX_API_BYTES:
            raise ApiConnectionError("The API response exceeds the 10 MB limit.")
        return content, response.status
    except ApiConnectionError:
        raise
    except (OSError, ssl.SSLError, http.client.HTTPException, ValueError):
        raise ApiConnectionError(
            "Could not connect securely to the API. Check its URL, network access, and certificate."
        ) from None
    finally:
        if response is not None:
            response.close()
        if connection is not None:
            connection.close()


def parse_api_data(content, data_format, json_path=""):
    try:
        if data_format == "JSON":
            value = json.loads(content.decode("utf-8-sig"))
            for segment in filter(None, (part.strip() for part in json_path.split("."))):
                if not isinstance(value, dict) or segment not in value:
                    raise ApiConnectionError("The JSON data path does not exist in the response.")
                value = value[segment]
            if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
                raise ApiConnectionError("JSON must contain an array of objects at the selected data path.")
            frame = pd.json_normalize(value, sep=".")
            # Nested lists remain usable as text instead of unhashable objects.
            for column in frame.columns:
                frame[column] = frame[column].map(
                    lambda item: json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                    if isinstance(item, (list, dict)) else item
                )
        elif data_format == "CSV":
            frame = pd.read_csv(StringIO(content.decode("utf-8-sig")))
        elif data_format == "Excel":
            frame = pd.read_excel(BytesIO(content), engine="openpyxl")
        else:
            raise ApiConnectionError("Choose JSON, CSV, or Excel as the response format.")
    except ApiConnectionError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError,
            pd.errors.ParserError, BadZipFile, ImportError):
        raise ApiConnectionError("The API response could not be read in the selected format.") from None
    if frame.empty or not len(frame.columns):
        raise ApiConnectionError("The API response contains no rows or columns.")
    if frame.columns.duplicated().any():
        raise ApiConnectionError("The API response has duplicate column names after flattening.")
    return frame


def fetch_api_data(url, data_format="JSON", json_path="", auth_mode="None", secret="", header_name=""):
    content, _ = request_public_api(url, "GET", auth_mode, secret, header_name)
    return parse_api_data(content, data_format, json_path)


def push_api_data(url, data, method="POST", data_format="JSON", auth_mode="None", secret="", header_name=""):
    try:
        if data_format == "JSON":
            body = data.to_json(orient="records", date_format="iso", force_ascii=False).encode("utf-8")
            content_type = "application/json"
        elif data_format == "CSV":
            body = data.to_csv(index=False).encode("utf-8")
            content_type = "text/csv; charset=utf-8"
        else:
            raise ApiConnectionError("Choose JSON or CSV as the output format.")
    except (ValueError, TypeError, OverflowError) as error:
        if isinstance(error, ApiConnectionError):
            raise
        raise ApiConnectionError("The selected data could not be serialized for the API.") from None
    _, status = request_public_api(url, method, auth_mode, secret, header_name, body, content_type)
    return status
