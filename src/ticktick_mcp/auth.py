import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from pathlib import Path

TICKTICK_TOKEN_URL = "https://ticktick.com/oauth/token"
REDIRECT_URI = "https://nikitatsym.github.io/ticktick-mcp/"
SCOPES = "tasks:read tasks:write"
TOKEN_DIR = Path.home() / ".ticktick-mcp"
TOKEN_FILE = TOKEN_DIR / "tokens.json"

_log = lambda msg: print(f"[ticktick-mcp] {msg}", file=sys.stderr)
_now_ms = lambda: int(time.time() * 1000)


def save_tokens(tokens):
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))


def load_tokens():
    try:
        return json.loads(TOKEN_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _token_request(data, client_id, client_secret):
    basic_auth = b64encode(f"{client_id}:{client_secret}".encode()).decode()
    encoded = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(TICKTICK_TOKEN_URL, data=encoded, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Authorization", f"Basic {basic_auth}")
    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        raise Exception(f"Token request failed ({e.code}): {e.read().decode('utf-8', errors='replace')}")


def exchange_code(code, client_id, client_secret):
    body = _token_request(
        {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI, "scope": SCOPES},
        client_id, client_secret,
    )
    return {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token"),
        "token_type": body.get("token_type"),
        "expires_at": _now_ms() + body.get("expires_in", 3600) * 1000,
        "scope": body.get("scope"),
    }


def refresh_access_token(refresh_token, client_id, client_secret):
    body = _token_request(
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
        client_id, client_secret,
    )
    return {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token") or refresh_token,
        "token_type": body.get("token_type"),
        "expires_at": _now_ms() + body.get("expires_in", 3600) * 1000,
        "scope": body.get("scope"),
    }


def get_access_token(client_id, client_secret):
    # Priority 1: env var
    if os.environ.get("TICKTICK_ACCESS_TOKEN"):
        tokens = {
            "access_token": os.environ["TICKTICK_ACCESS_TOKEN"],
            "refresh_token": os.environ.get("TICKTICK_REFRESH_TOKEN"),
            "expires_at": None,
        }
        save_tokens(tokens)
        return tokens["access_token"]

    # Priority 2: disk
    tokens = load_tokens()
    if tokens:
        if tokens.get("expires_at") and _now_ms() > tokens["expires_at"] - 60_000:
            if tokens.get("refresh_token") and client_id and client_secret:
                _log("Access token expired, refreshing...")
                try:
                    tokens = refresh_access_token(tokens["refresh_token"], client_id, client_secret)
                    save_tokens(tokens)
                    _log("Token refreshed successfully.")
                except Exception as e:
                    _log(f"Token refresh failed: {e}")
                    tokens = None
            else:
                tokens = None
    if tokens:
        return tokens["access_token"]

    # Priority 3: auth code
    auth_code = os.environ.get("TICKTICK_AUTH_CODE")
    if auth_code and client_id and client_secret:
        _log("Exchanging auth code for tokens...")
        try:
            tokens = exchange_code(auth_code, client_id, client_secret)
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
