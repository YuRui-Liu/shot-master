"""一次性生成 Ed25519 密钥对：私钥写文件(你保管)，公钥打印(填进客户端)。"""
from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PRIVATE_KEY_PATH = Path(__file__).resolve().parent / "private_key.pem"


def generate() -> str:
    sk = Ed25519PrivateKey.generate()
    pem = sk.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    PRIVATE_KEY_PATH.write_bytes(pem)
    raw_pub = sk.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pub_b64 = base64.b64encode(raw_pub).decode("ascii")
    print(f"私钥已写入: {PRIVATE_KEY_PATH}")
    print(f"把下面这行公钥填进 drama_shot_master/licensing/public_key.py:")
    print(f'PUBLIC_KEY_B64 = "{pub_b64}"')
    return pub_b64


def load_private_key() -> Ed25519PrivateKey:
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    return load_pem_private_key(PRIVATE_KEY_PATH.read_bytes(), password=None)


if __name__ == "__main__":
    generate()
