"""授权状态机 + 持久化。状态判定纯函数化，便于单测。"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from drama_shot_master.licensing import token
from drama_shot_master.licensing import paths
from drama_shot_master.licensing.fingerprint import machine_id
from drama_shot_master.licensing.public_key import load_public_key


class LicenseState(str, Enum):
    UNACTIVATED = "unactivated"
    VALID = "valid"
    EXPIRED = "expired"
    WRONG_MACHINE = "wrong_machine"
    TAMPERED = "tampered"


@dataclass(frozen=True)
class LicenseStatus:
    state: LicenseState
    expiry_date: date | None = None
    days_left: int = 0
    license_id: int | None = None


def _license_path():
    return paths.user_data_dir() / "license.txt"


def _public_key():
    return load_public_key()


def _today_days() -> int:
    return int(time.time() // 86400)


def gate_allows(state: LicenseState) -> bool:
    return state is LicenseState.VALID


def _evaluate(code: str) -> LicenseStatus:
    try:
        payload = token.verify_token(code, _public_key())
    except token.InvalidToken:
        return LicenseStatus(LicenseState.TAMPERED)
    if payload.machine_id != machine_id():
        return LicenseStatus(LicenseState.WRONG_MACHINE, license_id=payload.license_id)
    days_left = payload.expiry_days - _today_days()
    exp = date.today() + timedelta(days=days_left)
    if days_left < 0:
        return LicenseStatus(LicenseState.EXPIRED, exp, days_left, payload.license_id)
    return LicenseStatus(LicenseState.VALID, exp, days_left, payload.license_id)


def status() -> LicenseStatus:
    p = _license_path()
    if not p.exists():
        return LicenseStatus(LicenseState.UNACTIVATED)
    return _evaluate(p.read_text(encoding="utf-8").strip())


def activate(code: str) -> LicenseStatus:
    st = _evaluate(code)
    if st.state in (LicenseState.VALID, LicenseState.EXPIRED):
        # 验签通过（含已过期的真码）才落盘；非法/非本机不写
        _license_path().write_text(code.strip(), encoding="utf-8")
    return st


def requires_activation(state: LicenseState) -> bool:
    return not gate_allows(state)
