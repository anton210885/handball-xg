"""Login für den Betrieb im Internet.

Aktiv nur, wenn APP_PASSWORD gesetzt ist (backend/.env). Lokal ohne Passwort bleibt alles offen wie bisher.
Nach dem Login trägt der Browser ein signiertes Cookie (30 Tage). Zu viele Fehlversuche von einer Adresse → kurze Sperre.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import DATA_DIR

COOKIE = "hxg_session"
MAX_AGE = 30 * 24 * 3600
MAX_FAILS, FAIL_WINDOW = 5, 15 * 60          # 5 Fehlversuche in 15 Minuten → gesperrt bis das Fenster abläuft
OPEN_API = {"/api/auth", "/api/login", "/api/logout", "/api/version"}

_fails: dict[str, deque] = defaultdict(deque)


def password() -> str:
    return os.getenv("APP_PASSWORD", "")


def enabled() -> bool:
    return bool(password())


def _secret() -> bytes:
    env = os.getenv("APP_SECRET")
    if env:
        return env.encode()
    path = DATA_DIR / "secret.key"
    if not path.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip().encode()


def _sign(expires: int) -> str:
    # Passwort fließt mit ein: neues Passwort → alle alten Logins ungültig
    key = _secret() + hashlib.sha256(password().encode()).digest()
    return hmac.new(key, str(expires).encode(), hashlib.sha256).hexdigest()


def make_token(now: float | None = None) -> str:
    expires = int((now or time.time()) + MAX_AGE)
    return f"{expires}.{_sign(expires)}"


def valid_token(token: str | None, now: float | None = None) -> bool:
    if not token or "." not in token:
        return False
    exp, sig = token.split(".", 1)
    if not exp.isdigit() or int(exp) < (now or time.time()):
        return False
    return hmac.compare_digest(sig, _sign(int(exp)))


def logged_in(request: Request) -> bool:
    return not enabled() or valid_token(request.cookies.get(COOKIE))


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def blocked(ip: str, now: float | None = None) -> bool:
    now = now or time.time()
    q = _fails[ip]
    while q and q[0] < now - FAIL_WINDOW:
        q.popleft()
    return len(q) >= MAX_FAILS


def check_password(ip: str, given: str) -> bool:
    ok = hmac.compare_digest(given.encode(), password().encode())
    if not ok:
        _fails[ip].append(time.time())
    else:
        _fails.pop(ip, None)
    return ok


def set_cookie(response, request: Request):
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(COOKIE, make_token(), max_age=MAX_AGE, httponly=True, samesite="lax", secure=secure)


async def middleware(request: Request, call_next):
    """Alle /api-Aufrufe brauchen ein gültiges Login. Die Oberfläche selbst lädt immer (sie zeigt dann die Login-Seite)."""
    path = request.url.path
    if enabled() and path.startswith("/api/") and path not in OPEN_API and not logged_in(request):
        return JSONResponse({"detail": "Bitte anmelden"}, status_code=401)
    return await call_next(request)
