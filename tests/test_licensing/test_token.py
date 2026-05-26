from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest
from drama_shot_master.licensing import token


def _kp():
    sk = Ed25519PrivateKey.generate()
    return sk, sk.public_key()


def test_sign_verify_roundtrip():
    sk, pk = _kp()
    mid = b"0123456789"                       # 10 bytes
    code = token.sign_token(mid, expiry_days=20000, license_id=42, private_key=sk)
    p = token.verify_token(code, pk)
    assert p.machine_id == mid
    assert p.expiry_days == 20000
    assert p.license_id == 42
    assert p.version == token.VERSION


def test_code_is_grouped_and_pasteable():
    sk, pk = _kp()
    code = token.sign_token(b"0123456789", 20000, 1, sk)
    assert "-" in code                        # 分组便于粘贴
    # 去掉分组/大小写/空白后仍可验签
    assert token.verify_token(code.lower().replace("-", " "), pk).license_id == 1


def test_tampered_payload_rejected():
    sk, pk = _kp()
    code = token.sign_token(b"0123456789", 20000, 1, sk)
    # 翻转一个字符（仍是合法 base32 字母）制造篡改
    chars = list(code.replace("-", ""))
    chars[0] = "A" if chars[0] != "A" else "B"
    with pytest.raises(token.InvalidToken):
        token.verify_token("".join(chars), pk)


def test_wrong_key_rejected():
    sk, _ = _kp()
    _, pk2 = _kp()
    code = token.sign_token(b"0123456789", 20000, 1, sk)
    with pytest.raises(token.InvalidToken):
        token.verify_token(code, pk2)


def test_garbage_rejected():
    _, pk = _kp()
    with pytest.raises(token.InvalidToken):
        token.verify_token("not-a-valid-code", pk)
