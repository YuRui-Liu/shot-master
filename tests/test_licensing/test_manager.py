import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest
from drama_shot_master.licensing import manager, token, fingerprint


@pytest.fixture
def env(tmp_path, monkeypatch):
    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()
    monkeypatch.setattr("drama_shot_master.licensing.paths.user_data_dir",
                        lambda: tmp_path)
    monkeypatch.setattr(manager, "_public_key", lambda: pk)
    return sk, pk, tmp_path


def _today_days():
    return int(time.time() // 86400)


def _code(sk, days_from_now, mid=None, license_id=1):
    mid = mid or fingerprint.machine_id()
    return token.sign_token(mid, _today_days() + days_from_now, license_id, sk)


def test_unactivated_when_no_file(env):
    assert manager.status().state == manager.LicenseState.UNACTIVATED


def test_activate_valid_writes_file_and_reports_valid(env):
    sk, _, tmp = env
    st = manager.activate(_code(sk, 90))
    assert st.state == manager.LicenseState.VALID
    assert st.days_left >= 89
    assert (tmp / "license.txt").exists()
    assert manager.status().state == manager.LicenseState.VALID


def test_expired(env):
    sk, _, _ = env
    st = manager.activate(_code(sk, -1))
    assert st.state == manager.LicenseState.EXPIRED


def test_wrong_machine(env):
    sk, _, _ = env
    st = manager.activate(_code(sk, 90, mid=b"DIFFERENT!"))
    assert st.state == manager.LicenseState.WRONG_MACHINE


def test_tampered_or_bad_code_not_written(env):
    sk, _, tmp = env
    st = manager.activate("AAAA-BBBB-CCCC")
    assert st.state == manager.LicenseState.TAMPERED
    assert not (tmp / "license.txt").exists()


def test_gate_allows_only_valid():
    assert manager.gate_allows(manager.LicenseState.VALID) is True
    for s in (manager.LicenseState.UNACTIVATED, manager.LicenseState.EXPIRED,
              manager.LicenseState.WRONG_MACHINE, manager.LicenseState.TAMPERED):
        assert manager.gate_allows(s) is False
