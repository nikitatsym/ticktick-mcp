from __future__ import annotations

import json
import os
import sys
import time
from base64 import b64encode
from pathlib import Path

import httpx

TICKTICK_TOKEN_URL = "https://ticktick.com/oauth/token"
REDIRECT_URI = "https://nikitatsym.github.io/ticktick-mcp/"
SCOPES = "tasks:read tasks:write"
TOKEN_DIR = Path.home() / ".ticktick-mcp"
TOKEN_FILE = TOKEN_DIR / "tokens.json"


def save_tokens(tokens: dict) -> None:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))


def load_tokens() -> dict | None:
    try:
        return json.loads(TOKEN_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


async def exchange_code(code: str, client_id: str, client_secret: str) -> dict:
    basic_auth = b64encode(f"{client_id}:{client_secret}".encode()).decode()

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
    }

    async with httpx.AsyncClient() as client:
        res = await client.post(
            TICKTICK_TOKEN_URL,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic_auth}",
            },
        )

    if res.status_code >= 400:
        raise Exception(f"Token exchange failed ({res.status_code}): {res.text}")

    body = res.json()
    return {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token"),
        "token_type": body.get("token_type"),
        "expires_at": _now_ms() + (body.get("expires_in", 3600)) * 1000,
        "scope": body.get("scope"),
    }


async def refresh_access_token(refresh_token: str, client_id: str, client_secret: str) -> dict:
    basic_auth = b64encode(f"{client_id}:{client_secret}".encode()).decode()

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    async with httpx.AsyncClient() as client:
        res = await client.post(
            TICKTICK_TOKEN_URL,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic_auth}",
            },
        )

    if res.status_code >= 400:
        raise Exception(f"Token refresh failed ({res.status_code}): {res.text}")

    body = res.json()
    return {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token") or refresh_token,
        "token_type": body.get("token_type"),
        "expires_at": _now_ms() + (body.get("expires_in", 3600)) * 1000,
        "scope": body.get("scope"),
    }


async def get_access_token(client_id: str | None, client_secret: str | None) -> str:
    """Get a valid access token. Priority: env → disk → auth code exchange."""

    # Priority 1: env var access token
    if os.environ.get("TICKTICK_ACCESS_TOKEN"):
        tokens = {
            "access_token": os.environ["TICKTICK_ACCESS_TOKEN"],
            "refresh_token": os.environ.get("TICKTICK_REFRESH_TOKEN"),
            "expires_at": None,
        }
        save_tokens(tokens)
        return tokens["access_token"]

    # Priority 2: saved tokens from disk
    tokens = load_tokens()

    if tokens:
        # Check expiry (with 60s buffer) — expires_at is in milliseconds
        if tokens.get("expires_at") and _now_ms() > tokens["expires_at"] - 60_000:
            if tokens.get("refresh_token") and client_id and client_secret:
                _log("Access token expired, refreshing...")
                try:
                    tokens = await refresh_access_token(tokens["refresh_token"], client_id, client_secret)
                    save_tokens(tokens)
                    _log("Token refreshed successfully.")
                except Exception as e:
                    _log(f"Token refresh failed: {e}")
                    tokens = None
            else:
                tokens = None

    if tokens:
        return tokens["access_token"]

    # Priority 3: one-time auth code exchange
    auth_code = os.environ.get("TICKTICK_AUTH_CODE")
    if auth_code and client_id and client_secret:
        _log("Exchanging auth code for tokens...")
        try:
            tokens = await exchange_code(auth_code, client_id, client_secret)
            save_tokens(tokens)
            _log(f"Tokens saved to {TOKEN_FILE}")
            return tokens["access_token"]
        except Exception as e:
            _log(f"Auth code exchange failed: {e}")

    raise Exception(
        "No authentication tokens found.\n"
        "Visit https://nikitatsym.github.io/ticktick-mcp/ to set up authorization.\n"
        "See README.md for details."
    )


def _now_ms() -> int:
    return int(time.time() * 1000)


def _log(msg: str) -> None:
    print(f"[ticktick-mcp] {msg}", file=sys.stderr)
