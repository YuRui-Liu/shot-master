"""内置 Ed25519 公钥（Task 6 用真实 keygen 输出替换占位）。"""
from __future__ import annotations

import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Task 6 用 license_admin/keygen.py 的输出替换这一行（32 字节裸公钥的 base64）
PUBLIC_KEY_B64 = "zs81N/FRaNG+FzTdCNWyNq8T3d4e6d8kdc1fAX/c/Z8="


def load_public_key() -> Ed25519PublicKey:
    raw = base64.b64decode(PUBLIC_KEY_B64)
    return Ed25519PublicKey.from_public_bytes(raw)
