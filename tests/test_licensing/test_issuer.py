from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from license_admin import issuer
from drama_shot_master.licensing import token, fingerprint


def test_issue_verifies_with_matching_public_key():
    sk = Ed25519PrivateKey.generate()
    code = fingerprint.machine_code()
    out = issuer.issue(code, expiry_days_from_now=90, license_id=7, private_key=sk)
    p = token.verify_token(out, sk.public_key())
    assert p.machine_id == fingerprint.decode_machine_code(code)
    assert p.license_id == 7
    assert p.expiry_days > 0
