"""Read-only guard.

This project verifies connectivity. It must never place, modify, or cancel an order.
Every authenticated request passes through `assert_allowed`, which permits only the
read endpoints below, plus the order *preview* endpoint, which validates an order
without submitting it, and only when the caller opts in explicitly.
"""

from __future__ import annotations

ALLOWED_AUTH_REQUESTS: frozenset[tuple[str, str]] = frozenset({
    ("GET", "/v1/account/balances"),
    ("GET", "/v1/portfolio/positions"),
    ("GET", "/v1/orders/open"),
    ("GET", "/v1/ws/markets"),     # websocket handshake
    ("GET", "/v1/ws/private"),     # websocket handshake
})

PREVIEW_REQUEST = ("POST", "/v1/order/preview")


class BlockedRequestError(PermissionError):
    """Raised when code attempts a request outside the read-only allowlist."""


def assert_allowed(method: str, path: str, *, allow_preview: bool = False) -> None:
    key = (method.upper(), path.split("?", 1)[0])
    if key in ALLOWED_AUTH_REQUESTS:
        return
    if allow_preview and key == PREVIEW_REQUEST:
        return
    raise BlockedRequestError(
        f"{key[0]} {key[1]} is blocked: this tool is read-only and never trades")
