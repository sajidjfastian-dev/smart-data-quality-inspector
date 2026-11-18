"""Replit OIDC code + PKCE authentication and revocable opaque sessions.

No identity comes from browser headers, query parameters, or chat names.
Only verified ID-token claims are persisted; provider tokens are not retained.
"""
import asyncio
import hashlib
import logging
import os
import secrets
import time
from urllib.parse import urlsplit

from httpx import AsyncClient
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.jose import JsonWebToken
from authlib.oidc.core import CodeIDToken
from psycopg.types.json import Jsonb
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from demo_store import connection, DemoStoreError

ISSUER = "https://replit.com/oidc"
COOKIE = "__Host-dq-account"
FLOW_COOKIE = "__Host-dq-login"
SESSION_SECONDS = 3600
LOGGER = logging.getLogger(__name__)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def put_record(token, kind, payload, seconds):
    with connection() as conn:
        conn.execute("DELETE FROM dq_auth_records WHERE expires_at <= now()")
        conn.execute(
            "INSERT INTO dq_auth_records(token_hash,kind,payload,expires_at) VALUES (%s,%s,%s,now()+(%s * interval '1 second'))",
            (digest(token), kind, Jsonb(payload), seconds),
        )


def get_record(token, kind, consume=False):
    if not isinstance(token, str) or not 30 <= len(token) <= 200:
        return None
    with connection() as conn:
        if consume:
            row = conn.execute(
                "DELETE FROM dq_auth_records WHERE token_hash=%s AND kind=%s AND expires_at>now() RETURNING payload",
                (digest(token), kind),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT payload FROM dq_auth_records WHERE token_hash=%s AND kind=%s AND expires_at>now()",
                (digest(token), kind),
            ).fetchone()
    return row["payload"] if row else None


def revoke(token):
    if token:
        with connection() as conn:
            conn.execute("DELETE FROM dq_auth_records WHERE token_hash=%s", (digest(token),))


def session_identity(token):
    try:
        return get_record(token, "session")
    except DemoStoreError:
        LOGGER.warning("Account session validation unavailable; access denied")
        return None  # Fail closed; never keep a cached identity during outages.


def allowed_origin(request):
    origins = set()
    domain = os.environ.get("REPLIT_DEV_DOMAIN", "")
    if domain:
        origins.add("https://" + domain.lower())
    public = os.environ.get("AUTH_PUBLIC_ORIGIN", "").rstrip("/").lower()
    if public.startswith("https://") and urlsplit(public).path == "":
        origins.add(public)
    # Ignore forwarded-host and return-to inputs. Only configured HTTPS hosts.
    host = request.headers.get("host", "").lower()
    origin = "https://" + host
    if origin not in origins:
        raise ValueError("Unregistered authentication host")
    return origin


def client_id():
    value = os.environ.get("REPLIT_AUTH_CLIENT_ID") or os.environ.get("REPL_ID")
    if not value:
        raise ValueError("Replit client ID unavailable")
    return value


async def metadata():
    async with AsyncClient(timeout=15, follow_redirects=False) as client:
        response = await client.get(ISSUER + "/.well-known/openid-configuration")
        response.raise_for_status()
        config = response.json()
    if config.get("issuer") != ISSUER:
        raise ValueError("Unexpected issuer")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not config.get(key, "").startswith(ISSUER + "/"):
            raise ValueError("Unexpected OIDC endpoint")
    return config


def failure():
    return HTMLResponse(
        '<h1>Sign-in could not be completed</h1><p>Retry from the application. '
        'If this continues, check the Replit Auth client and callback configuration.</p>'
        '<a href="/">Return to application</a>',
        status_code=400, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


def set_cookie(response, name, value, seconds):
    response.set_cookie(name, value, max_age=seconds, httponly=True, secure=True, samesite="lax", path="/")


async def login(request):
    try:
        origin = allowed_origin(request)
        config = await metadata()
        token, nonce, verifier = (secrets.token_urlsafe(48) for _ in range(3))
        async with AsyncOAuth2Client(client_id(), redirect_uri=origin + "/auth/callback",
                                     scope="openid profile", code_challenge_method="S256") as client:
            url, state = client.create_authorization_url(
                config["authorization_endpoint"], nonce=nonce, code_verifier=verifier,
            )
        await asyncio.to_thread(put_record, token, "login",
                                {"state": state, "nonce": nonce, "verifier": verifier, "origin": origin}, 600)
        await asyncio.to_thread(revoke, request.cookies.get(COOKIE))
        response = RedirectResponse(url, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
        set_cookie(response, FLOW_COOKIE, token, 600)
        return response
    except Exception as error:
        # No OAuth codes, credentials, tokens or remote error bodies in logs/UI.
        LOGGER.warning("Replit authorization start failed (%s)", type(error).__name__)
        return failure()


async def callback(request):
    try:
        origin = allowed_origin(request)
        flow = await asyncio.to_thread(get_record, request.cookies.get(FLOW_COOKIE), "login", True)
        state = request.query_params.get("state", "")
        if not flow or flow["origin"] != origin or not secrets.compare_digest(flow["state"], state):
            raise ValueError("Invalid login state")
        if request.query_params.get("iss", ISSUER) != ISSUER or request.query_params.get("error"):
            raise ValueError("Invalid authorization response")
        code = request.query_params.get("code")
        if not code:
            raise ValueError("Missing code")
        config = await metadata()
        async with AsyncOAuth2Client(client_id(), token_endpoint_auth_method="none", timeout=15) as client:
            token = await client.fetch_token(
                config["token_endpoint"], code=code, redirect_uri=origin + "/auth/callback",
                code_verifier=flow["verifier"], grant_type="authorization_code",
            )
        async with AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get(config["jwks_uri"])
            response.raise_for_status()
            keys = response.json()
        claims = JsonWebToken(["RS256", "PS256"]).decode(
            token["id_token"], keys, claims_cls=CodeIDToken,
            claims_options={"iss": {"essential": True, "value": ISSUER},
                            "aud": {"essential": True, "value": client_id()},
                            "sub": {"essential": True}, "exp": {"essential": True},
                            "iat": {"essential": True}},
            claims_params={"nonce": flow["nonce"], "client_id": client_id(),
                           "access_token": token.get("access_token")},
        )
        claims.validate(leeway=30)
        identity = profile(claims)
        lifetime = min(SESSION_SECONDS, int(claims["exp"] - time.time()))
        if lifetime <= 0:
            raise ValueError("Expired login")
        sid = secrets.token_urlsafe(48)
        await asyncio.to_thread(put_record, sid, "session", identity, lifetime)
        response = RedirectResponse("/", status_code=303, headers={"Cache-Control": "no-store",
                                                                   "Referrer-Policy": "no-referrer"})
        set_cookie(response, COOKIE, sid, lifetime)
        response.delete_cookie(FLOW_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        return response
    except Exception as error:
        LOGGER.warning("Replit authorization callback rejected (%s)", type(error).__name__)
        return failure()


def profile(claims):
    subject = claims.get("sub")
    username = claims.get("username")
    if not isinstance(subject, str) or not subject or not isinstance(username, str) or not username:
        raise ValueError("Verified account profile unavailable")
    name = " ".join(str(claims.get(k) or "").strip() for k in ("first_name", "last_name")).strip()
    return {"subject": subject, "username": username, "name": name or username}


ROUTES = [Route("/auth/login", login, methods=["GET"]),
          Route("/auth/callback", callback, methods=["GET"])]


class AccountResourceGuard:
    """Never serve private Streamlit resources with a revoked/absent account."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith(("/media/", "/_stcore/upload_file/")):
            from starlette.requests import Request
            from starlette.responses import Response
            from account_resources import is_public, allowed, allow_redirect
            request = Request(scope)
            if is_public(scope["path"]):
                await self.app(scope, receive, send)
                return
            cookie = request.cookies.get(COOKIE)
            identity = await asyncio.to_thread(session_identity, cookie)
            if not identity:
                await Response(status_code=401, headers={"Cache-Control": "no-store"})(scope, receive, send)
                return
            if not allowed(scope["path"], cookie):
                await Response(status_code=403, headers={"Cache-Control": "no-store"})(scope, receive, send)
                return
            async def private_send(message):
                if message["type"] == "http.response.start":
                    headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"]
                    headers.append((b"cache-control", b"no-store"))
                    message["headers"] = headers
                    if message["status"] in (302, 303, 307):
                        location = dict(headers).get(b"location", b"").decode()
                        allow_redirect(cookie, location)
                await send(message)
            await self.app(scope, receive, private_send)
            return
        await self.app(scope, receive, send)
