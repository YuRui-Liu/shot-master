"""激活码编解码 + Ed25519 签发/验签。不含任何密钥——密钥由调用方传入。"""
from __future__ import annotations

import base64
import struct
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

VERSION = 1
# version(B) + machine_id(10s) + expiry_days(I) + license_id(I) = 19 bytes
_PAYLOAD_FMT = ">B10sII"
_PAYLOAD_LEN = struct.calcsize(_PAYLOAD_FMT)   # 19
_SIG_LEN = 64


class InvalidToken(Exception):
    """激活码格式非法、验签失败或被篡改。"""


@dataclass(frozen=True)
class Payload:
    version: int
    machine_id: bytes
    expiry_days: int
    license_id: int


def _group(s: str) -> str:
    return "-".join(s[i:i + 4] for i in range(0, len(s), 4))


def _ungroup(s: str) -> str:
    return "".join(s.split()).replace("-", "").upper()


def encode_payload(machine_id: bytes, expiry_days: int, license_id: int) -> bytes:
    if len(machine_id) != 10:
        raise ValueError("machine_id must be 10 bytes")
    return struct.pack(_PAYLOAD_FMT, VERSION, machine_id, expiry_days, license_id)


def decode_payload(raw: bytes) -> Payload:
    version, mid, expiry, lid = struct.unpack(_PAYLOAD_FMT, raw)
    return Payload(version=version, machine_id=mid, expiry_days=expiry, license_id=lid)


def sign_token(machine_id: bytes, expiry_days: int, license_id: int,
               private_key: Ed25519PrivateKey) -> str:
    payload = encode_payload(machine_id, expiry_days, license_id)
    sig = private_key.sign(payload)
    blob = payload + sig
    b32 = base64.b32encode(blob).decode("ascii").rstrip("=")
    return _group(b32)


def verify_token(code: str, public_key: Ed25519PublicKey) -> Payload:
    raw = _ungroup(code)
    pad = "=" * (-len(raw) % 8)
    try:
        blob = base64.b32decode(raw + pad)
    except (ValueError, base64.binascii.Error) as e:
        raise InvalidToken(f"无法解码: {e}") from e
    if len(blob) != _PAYLOAD_LEN + _SIG_LEN:
        raise InvalidToken("长度不符")
    payload, sig = blob[:_PAYLOAD_LEN], blob[_PAYLOAD_LEN:]
    try:
        public_key.verify(sig, payload)
    except InvalidSignature as e:
        raise InvalidToken("验签失败") from e
    return decode_payload(payload)
