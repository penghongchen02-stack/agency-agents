"""Ed25519 request signing for the Polymarket US API.

Per https://docs.polymarket.us/api-reference/authentication and the official
`polymarket-us` SDK: message = f"{timestamp_ms}{METHOD}{path}" (path WITHOUT the
query string), signed with the Ed25519 seed = first 32 bytes of the base64 secret.
"""

from __future__ import annotations

import base64
import binascii
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class SecretKeyError(ValueError):
    """The secret key is not valid base64 Ed25519 key material."""


def load_private_key(secret_key_b64: str) -> Ed25519PrivateKey:
    try:
        raw = base64.b64decode(secret_key_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SecretKeyError("secret key is not valid base64") from exc
    if len(raw) not in (32, 64):
        raise SecretKeyError(f"secret key decodes to {len(raw)} bytes; expected 32 or 64")
    return Ed25519PrivateKey.from_private_bytes(raw[:32])


def sign_headers(key_id: str, private_key: Ed25519PrivateKey, method: str, path: str,
                 now_ms: int | None = None) -> dict[str, str]:
    if "?" in path:
        raise ValueError("sign the path only; the query string is not part of the message")
    ts = str(now_ms if now_ms is not None else int(time.time() * 1000))
    message = f"{ts}{method.upper()}{path}".encode()
    signature = base64.b64encode(private_key.sign(message)).decode()
    return {
        "X-PM-Access-Key": key_id,
        "X-PM-Timestamp": ts,
        "X-PM-Signature": signature,
    }
