"""Management portal password (cookie session)."""

from __future__ import annotations

import os

from fastapi import Cookie, HTTPException

ADMIN_COOKIE = "rv_admin"
ADMIN_PASSWORD = os.environ.get("RESUMEVERIFY_ADMIN_PASSWORD", "")


def admin_configured() -> bool:
    return bool(ADMIN_PASSWORD)


def require_admin(
    rv_admin: str | None = Cookie(default=None, alias=ADMIN_COOKIE),
) -> None:
    if not admin_configured():
        return
    if rv_admin != "ok":
        raise HTTPException(status_code=401, detail="Admin login required")
