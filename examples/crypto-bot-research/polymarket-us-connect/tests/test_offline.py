"""Offline tests: signing and the read-only guard. No network needed."""

import base64
import os
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pmus_connect.auth import SecretKeyError, load_private_key, sign_headers  # noqa: E402
from pmus_connect.safety import BlockedRequestError, assert_allowed  # noqa: E402


def _secret_b64(length: int = 32) -> tuple[str, Ed25519PrivateKey]:
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    raw = seed if length == 32 else seed + key.public_key().public_bytes(
        Encoding.Raw, __import__("cryptography").hazmat.primitives.serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode(), key


@pytest.mark.parametrize("length", [32, 64])
def test_signature_verifies_with_public_key(length):
    secret, original = _secret_b64(length)
    priv = load_private_key(secret)
    h = sign_headers("key-id", priv, "get", "/v1/account/balances", now_ms=1_700_000_000_000)
    assert h["X-PM-Timestamp"] == "1700000000000"
    message = b"1700000000000GET/v1/account/balances"
    original.public_key().verify(base64.b64decode(h["X-PM-Signature"]), message)  # raises if bad


def test_query_string_not_signed():
    secret, _ = _secret_b64()
    with pytest.raises(ValueError):
        sign_headers("k", load_private_key(secret), "GET", "/v1/orders/open?x=1")


def test_bad_secret_rejected():
    with pytest.raises(SecretKeyError):
        load_private_key("not base64!!")
    with pytest.raises(SecretKeyError):
        load_private_key(base64.b64encode(b"short").decode())


@pytest.mark.parametrize("method,path", [
    ("GET", "/v1/account/balances"), ("GET", "/v1/portfolio/positions"),
    ("GET", "/v1/orders/open"), ("GET", "/v1/ws/markets"), ("GET", "/v1/ws/private")])
def test_read_endpoints_allowed(method, path):
    assert_allowed(method, path)


@pytest.mark.parametrize("method,path", [
    ("POST", "/v1/orders"), ("POST", "/v1/orders/batch"), ("DELETE", "/v1/order/123"),
    ("POST", "/v1/order/123/cancel"), ("POST", "/v1/orders/open/cancel"),
    ("POST", "/v1/order/close-position"), ("POST", "/v1/rfqs"), ("POST", "/v1/order/preview")])
def test_trading_endpoints_blocked(method, path):
    with pytest.raises(BlockedRequestError):
        assert_allowed(method, path)


def test_preview_only_with_opt_in():
    assert_allowed("POST", "/v1/order/preview", allow_preview=True)
