"""Google OAuth2 login and session-cookie helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .config import (
    ALLOWED_GOOGLE_EMAIL,
    BASE_URL,
    GOOGLE_CALENDAR_CREDENTIALS,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    WEB_SECRET,
)

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials

_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.readonly",
]

_SESSION_COOKIE = "pa_session"
_STATE_COOKIE = "pa_oauth_state"
_VERIFIER_COOKIE = "pa_oauth_verifier"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
_STATE_MAX_AGE = 60 * 10  # 10 minutes


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

def _flow(state: str | None = None):
    """Build a google_auth_oauthlib Flow."""
    from google_auth_oauthlib.flow import Flow

    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": (
                "https://accounts.google.com/o/oauth2/auth"
            ),
            "token_uri": (
                "https://oauth2.googleapis.com/token"
            ),
            "redirect_uris": [
                f"{BASE_URL}/oauth/callback"
            ],
        }
    }
    kwargs = {}
    if state is not None:
        kwargs["state"] = state
    return Flow.from_client_config(
        client_config,
        scopes=_SCOPES,
        redirect_uri=f"{BASE_URL}/oauth/callback",
        **kwargs,
    )


def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE."""
    verifier = (
        base64.urlsafe_b64encode(os.urandom(32))
        .rstrip(b"=")
        .decode("ascii")
    )
    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    return verifier, challenge


def build_auth_url() -> tuple[str, str, str]:
    """Return (auth_url, state, code_verifier)."""
    verifier, challenge = _pkce_pair()
    flow = _flow()
    url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account",
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    return url, state, verifier


def exchange_code(
    code: str, state: str, code_verifier: str = "",
) -> "Credentials":
    """Exchange an auth code for credentials."""
    flow = _flow(state=state)
    flow.fetch_token(
        code=code,
        code_verifier=code_verifier or None,
    )
    return flow.credentials


def verify_email(creds: "Credentials") -> str:
    """Return the authenticated email address."""
    import requests as _requests

    resp = _requests.get(
        "https://www.googleapis.com/oauth2/v1/userinfo",
        headers={
            "Authorization": f"Bearer {creds.token}"
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["email"]


def save_credentials(creds: "Credentials") -> None:
    """Persist credentials to the Calendar credentials file."""
    data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or []),
    }
    GOOGLE_CALENDAR_CREDENTIALS.parent.mkdir(
        parents=True, exist_ok=True
    )
    GOOGLE_CALENDAR_CREDENTIALS.write_text(
        json.dumps(data), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Session cookies
# ---------------------------------------------------------------------------

def _signer() -> URLSafeTimedSerializer:
    if not WEB_SECRET:
        raise RuntimeError("WEB_SECRET env var is not set")
    return URLSafeTimedSerializer(WEB_SECRET)


def set_session(response: Response, email: str) -> None:
    token = _signer().dumps(email)
    response.set_cookie(
        _SESSION_COOKIE,
        token,
        httponly=True,
        secure=BASE_URL.startswith("https"),
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
    )


def get_session(request: Request) -> str | None:
    """Return the signed-in email, or None."""
    token = request.cookies.get(_SESSION_COOKIE, "")
    if not token:
        return None
    try:
        return _signer().loads(
            token, max_age=_COOKIE_MAX_AGE
        )
    except BadSignature:
        return None


def require_session(request: Request) -> str:
    """FastAPI Depends — redirects to /login if not authenticated."""
    email = get_session(request)
    if not email:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"},
        )
    return email


# ---------------------------------------------------------------------------
# OAuth state cookie (short-lived CSRF protection)
# ---------------------------------------------------------------------------

def set_state_cookie(
    response: Response, state: str
) -> None:
    token = _signer().dumps(state)
    response.set_cookie(
        _STATE_COOKIE,
        token,
        httponly=True,
        secure=BASE_URL.startswith("https"),
        samesite="lax",
        max_age=_STATE_MAX_AGE,
    )


def verify_state_cookie(
    request: Request, state: str
) -> None:
    """Raise 400 if state doesn't match the cookie."""
    token = request.cookies.get(_STATE_COOKIE, "")
    try:
        expected = _signer().loads(
            token, max_age=_STATE_MAX_AGE
        )
    except BadSignature:
        raise HTTPException(
            status_code=400, detail="Invalid OAuth state"
        )
    if expected != state:
        raise HTTPException(
            status_code=400, detail="OAuth state mismatch"
        )


def set_verifier_cookie(
    response: Response, verifier: str
) -> None:
    token = _signer().dumps(verifier)
    response.set_cookie(
        _VERIFIER_COOKIE,
        token,
        httponly=True,
        secure=BASE_URL.startswith("https"),
        samesite="lax",
        max_age=_STATE_MAX_AGE,
    )


def get_verifier_cookie(request: Request) -> str:
    """Return the PKCE code verifier, or empty string."""
    token = request.cookies.get(_VERIFIER_COOKIE, "")
    if not token:
        return ""
    try:
        return _signer().loads(
            token, max_age=_STATE_MAX_AGE
        )
    except BadSignature:
        return ""


def check_allowed_email(email: str) -> None:
    """Raise 403 if email is not the allowed owner."""
    if (
        ALLOWED_GOOGLE_EMAIL
        and email.lower() != ALLOWED_GOOGLE_EMAIL.lower()
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Account {email!r} is not authorised"
            ),
        )
