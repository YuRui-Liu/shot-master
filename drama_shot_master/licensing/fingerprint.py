"""机器指纹：Windows 用注册表 MachineGuid；其它平台用每用户 dev 回退文件。"""
from __future__ import annotations

import hashlib
import secrets

from drama_shot_master.licensing import token
from drama_shot_master.licensing import paths

_ID_LEN = 10


def _seed_source() -> str | None:
    """返回稳定的机器种子字符串；取不到返回 None（走 dev 回退）。"""
    try:
        import winreg  # type: ignore
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Cryptography") as k:
            guid, _ = winreg.QueryValueEx(k, "MachineGuid")
        return str(guid)
    except OSError:
        return None


def _dev_seed() -> str:
    f = paths.user_data_dir() / "dev_machine_id"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    seed = secrets.token_hex(16)
    f.write_text(seed, encoding="utf-8")
    return seed


def machine_id() -> bytes:
    seed = _seed_source() or _dev_seed()
    return hashlib.sha256(seed.encode("utf-8")).digest()[:_ID_LEN]


def machine_code() -> str:
    import base64
    b32 = base64.b32encode(machine_id()).decode("ascii").rstrip("=")
    return token._group(b32)


def decode_machine_code(code: str) -> bytes:
    import base64
    raw = token._ungroup(code)
    pad = "=" * (-len(raw) % 8)
    return base64.b32decode(raw + pad)[:_ID_LEN]
