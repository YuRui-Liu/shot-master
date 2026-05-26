"""管理端签发：把机器码 + 有效期 → 签名激活码。复用客户端 token 格式。"""
from __future__ import annotations

import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from drama_shot_master.licensing import token, fingerprint


def issue(machine_code: str, expiry_days_from_now: int, license_id: int,
          private_key: Ed25519PrivateKey) -> str:
    mid = fingerprint.decode_machine_code(machine_code)
    expiry_days = int(time.time() // 86400) + expiry_days_from_now
    return token.sign_token(mid, expiry_days, license_id, private_key)
