# 离线授权系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 drama-shot-master 加一套全离线、机器绑定、到期刷新的非对称签名授权系统 + 关于/激活 UI + 启动门禁 + 独立管理端工具，并用 Nuitka 打包不泄露源码。

**Architecture:** 管理端（持私钥，不发布）为「机器码 + 有效期」签发 Ed25519 激活码；客户端内置公钥离线验签 + 校验机器匹配 + 校验未过期。核心逻辑在纯模块 `drama_shot_master/licensing/`（headless 可单测），UI 与门禁是其薄封装。

**Tech Stack:** Python, `cryptography`（Ed25519）, base32 编码, PySide6（UI + 管理端 GUI）, Nuitka（打包）。

设计依据：`docs/superpowers/specs/2026-05-26-offline-licensing-design.md`。

## 文件结构

客户端 license 核心（新包 `drama_shot_master/licensing/`）：
- `__init__.py` — 空。
- `paths.py` — `user_data_dir()`：每用户可写目录（Win `%LOCALAPPDATA%/DramaShotMaster`，否则 `~/.drama_shot_master`）。
- `token.py` — 激活码编解码 + Ed25519 签发/验签（**不含任何密钥**），`InvalidToken` 异常，base32 分组助手。
- `fingerprint.py` — `machine_id()`/`machine_code()`/`decode_machine_code()`。
- `public_key.py` — 内置公钥常量 + `load_public_key()`。
- `manager.py` — `LicenseState`、`LicenseStatus`、`status()`、`activate()`、`gate_allows()`、license 文件读写。

管理端（新顶层目录 `license_admin/`，**不进客户端构建、不进 git 的私钥**）：
- `keygen.py` — 生成 Ed25519 密钥对。
- `issuer.py` — 用私钥按 `token.py` 同格式签发激活码（复用 `token.py`）。
- `admin_gui.py` — 迷你 PySide6 签发界面。

UI / 集成：
- `drama_shot_master/ui/dialogs/about_dialog.py` — 关于 + 激活对话框。
- `drama_shot_master/ui/main_window.py` — 新增「关于」菜单。
- `drama_shot_master/main.py` — 启动门禁。

测试：`tests/test_licensing/`。

依赖：`pyproject.toml` 加 `cryptography>=42`。

---

### Task 1: 激活码编解码 + 签发/验签核心（token.py）

**Files:**
- Create: `drama_shot_master/licensing/__init__.py`（空）
- Create: `drama_shot_master/licensing/token.py`
- Test: `tests/test_licensing/__init__.py`（空）, `tests/test_licensing/test_token.py`
- Modify: `pyproject.toml`（dependencies 加 `"cryptography>=42",`）

- [ ] **Step 1: 加依赖声明**

`pyproject.toml` 的 `dependencies` 列表末尾（`"httpx>=0.27",` 后）加一行：

```toml
    "cryptography>=42",
```

- [ ] **Step 2: 写失败测试**

`tests/test_licensing/__init__.py` 留空。`tests/test_licensing/test_token.py`：

```python
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
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest tests/test_licensing/test_token.py -q`
Expected: FAIL（`ModuleNotFoundError: drama_shot_master.licensing.token`）

- [ ] **Step 4: 实现 token.py**

```python
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
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_licensing/test_token.py -q`
Expected: PASS（5 passed）

- [ ] **Step 6: 提交**

```bash
git add pyproject.toml drama_shot_master/licensing/__init__.py drama_shot_master/licensing/token.py tests/test_licensing/__init__.py tests/test_licensing/test_token.py
git commit -m "feat(licensing): Ed25519 激活码编解码+签发/验签核心"
```

---

### Task 2: 机器指纹（fingerprint.py + paths.py）

**Files:**
- Create: `drama_shot_master/licensing/paths.py`
- Create: `drama_shot_master/licensing/fingerprint.py`
- Test: `tests/test_licensing/test_fingerprint.py`

- [ ] **Step 1: 写失败测试**

`tests/test_licensing/test_fingerprint.py`：

```python
from drama_shot_master.licensing import fingerprint


def test_machine_id_is_10_bytes_and_stable():
    a = fingerprint.machine_id()
    b = fingerprint.machine_id()
    assert isinstance(a, bytes) and len(a) == 10
    assert a == b                              # 同机多次一致


def test_machine_code_roundtrips_to_machine_id():
    mid = fingerprint.machine_id()
    code = fingerprint.machine_code()
    assert "-" in code
    assert fingerprint.decode_machine_code(code) == mid


def test_decode_tolerates_lower_and_spaces():
    code = fingerprint.machine_code()
    assert fingerprint.decode_machine_code(code.lower().replace("-", " ")) \
        == fingerprint.machine_id()


def test_dev_fallback_file_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(fingerprint, "_seed_source", lambda: None)  # 强制走 dev 回退
    monkeypatch.setattr("drama_shot_master.licensing.paths.user_data_dir",
                        lambda: tmp_path)
    a = fingerprint.machine_id()
    b = fingerprint.machine_id()
    assert a == b
    assert (tmp_path / "dev_machine_id").exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_licensing/test_fingerprint.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 paths.py**

```python
"""每用户可写目录（license 文件、dev 机器码回退）。"""
from __future__ import annotations

import os
from pathlib import Path


def user_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:                                   # Windows
        d = Path(base) / "DramaShotMaster"
    else:
        d = Path.home() / ".drama_shot_master"
    d.mkdir(parents=True, exist_ok=True)
    return d
```

- [ ] **Step 4: 实现 fingerprint.py**

```python
"""机器指纹：Windows 用注册表 MachineGuid；其它平台用每用户 dev 回退文件。"""
from __future__ import annotations

import hashlib
import secrets

from drama_shot_master.licensing import token
from drama_shot_master.licensing.paths import user_data_dir

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
    f = user_data_dir() / "dev_machine_id"
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
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_licensing/test_fingerprint.py -q`
Expected: PASS（4 passed）

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/licensing/paths.py drama_shot_master/licensing/fingerprint.py tests/test_licensing/test_fingerprint.py
git commit -m "feat(licensing): 机器指纹(MachineGuid/dev 回退)+机器码编解码"
```

---

### Task 3: 授权状态机 + 持久化（public_key.py + manager.py）

**Files:**
- Create: `drama_shot_master/licensing/public_key.py`
- Create: `drama_shot_master/licensing/manager.py`
- Test: `tests/test_licensing/test_manager.py`

- [ ] **Step 1: 写失败测试**

`tests/test_licensing/test_manager.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_licensing/test_manager.py -q`
Expected: FAIL（`ModuleNotFoundError: drama_shot_master.licensing.manager`）

- [ ] **Step 3: 实现 public_key.py**

```python
"""内置 Ed25519 公钥（Task 6 用真实 keygen 输出替换占位）。"""
from __future__ import annotations

import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Task 6 用 license_admin/keygen.py 的输出替换这一行（32 字节裸公钥的 base64）
PUBLIC_KEY_B64 = "REPLACE_WITH_REAL_PUBLIC_KEY_BASE64"


def load_public_key() -> Ed25519PublicKey:
    raw = base64.b64decode(PUBLIC_KEY_B64)
    return Ed25519PublicKey.from_public_bytes(raw)
```

- [ ] **Step 4: 实现 manager.py**

```python
"""授权状态机 + 持久化。状态判定纯函数化，便于单测。"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from drama_shot_master.licensing import token
from drama_shot_master.licensing.fingerprint import machine_id
from drama_shot_master.licensing.paths import user_data_dir
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
    return user_data_dir() / "license.txt"


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
```

> 说明：测试用 `monkeypatch.setattr(manager, "_public_key", lambda: pk)` 注入测试公钥，因此 `manager` 内部一律通过 `_public_key()` 取公钥（不要直接调 `load_public_key`）。

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_licensing/test_manager.py -q`
Expected: PASS（6 passed）

- [ ] **Step 6: 提交**

```bash
git add drama_shot_master/licensing/public_key.py drama_shot_master/licensing/manager.py tests/test_licensing/test_manager.py
git commit -m "feat(licensing): 授权状态机+持久化(VALID/EXPIRED/WRONG_MACHINE/TAMPERED)"
```

---

### Task 4: 管理端签发核心（license_admin/issuer.py + keygen.py）

**Files:**
- Create: `license_admin/__init__.py`（空）
- Create: `license_admin/keygen.py`
- Create: `license_admin/issuer.py`
- Test: `tests/test_licensing/test_issuer.py`

- [ ] **Step 1: 写失败测试**

`tests/test_licensing/test_issuer.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_licensing/test_issuer.py -q`
Expected: FAIL（`ModuleNotFoundError: license_admin`）

- [ ] **Step 3: 实现 issuer.py + keygen.py + __init__.py**

`license_admin/__init__.py` 留空。

`license_admin/issuer.py`：

```python
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
```

`license_admin/keygen.py`：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_licensing/test_issuer.py -q`
Expected: PASS（1 passed）

- [ ] **Step 5: 提交**

```bash
git add license_admin/__init__.py license_admin/issuer.py license_admin/keygen.py tests/test_licensing/test_issuer.py
git commit -m "feat(license_admin): 签发核心 issuer + keygen"
```

---

### Task 5: 生成真实密钥对 + 内置公钥 + .gitignore（操作性任务）

**Files:**
- Modify: `drama_shot_master/licensing/public_key.py:11`（替换 `PUBLIC_KEY_B64`）
- Create/Modify: `.gitignore`
- 产物: `license_admin/private_key.pem`（**不提交**）

- [ ] **Step 1: 生成密钥对**

Run: `python -m license_admin.keygen`
Expected: 打印 `私钥已写入: .../private_key.pem` 与一行 `PUBLIC_KEY_B64 = "<44 字符 base64>"`；`license_admin/private_key.pem` 生成。

- [ ] **Step 2: 内置公钥**

把上一步打印的整行替换 `drama_shot_master/licensing/public_key.py` 中
`PUBLIC_KEY_B64 = "REPLACE_WITH_REAL_PUBLIC_KEY_BASE64"`。

- [ ] **Step 3: gitignore 私钥与签发台账**

`.gitignore` 追加：

```gitignore
# 授权管理端私钥与台账——绝不提交
license_admin/private_key.pem
license_admin/issued.csv
```

- [ ] **Step 4: 端到端验证（手动）**

```bash
python -c "
from license_admin import issuer, keygen
from drama_shot_master.licensing import manager, fingerprint, paths
import tempfile, pathlib
# 用真实私钥为本机签一张 90 天码，确认客户端能激活通过
sk = keygen.load_private_key()
code = issuer.issue(fingerprint.machine_code(), 90, 1, sk)
print('issued:', code[:24], '...')
st = manager.activate(code)
print('activate ->', st.state, 'days_left', st.days_left)
assert st.state.value == 'valid'
print('E2E OK')
"
```
Expected: `activate -> LicenseState.VALID ... / E2E OK`

- [ ] **Step 5: 提交（仅公钥与 gitignore，绝不含私钥）**

```bash
git status --short                 # 确认 private_key.pem 未被 git 跟踪
git add drama_shot_master/licensing/public_key.py .gitignore
git commit -m "chore(licensing): 内置真实公钥 + 忽略私钥/签发台账"
```

---

### Task 6: 管理端迷你 GUI（admin_gui.py）

**Files:**
- Create: `license_admin/admin_gui.py`

UI 任务，靠手动验证（签发核心已在 Task 4 单测）。

- [ ] **Step 1: 实现 admin_gui.py**

```python
"""迷你签发界面：粘贴机器码 + 选有效期 → 出激活码 + 记台账。"""
from __future__ import annotations

import csv
import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QFormLayout, QLineEdit, QSpinBox,
    QPushButton, QPlainTextEdit, QLabel, QMessageBox,
)

from license_admin import issuer, keygen

ISSUED_CSV = Path(__file__).resolve().parent / "issued.csv"


class AdminWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drama-Shot-Master 授权签发台")
        self.resize(560, 360)
        self._sk = keygen.load_private_key()
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.machine = QLineEdit(); self.machine.setPlaceholderText("粘贴用户的机器码")
        self.days = QSpinBox(); self.days.setRange(1, 3650); self.days.setValue(90)
        self.lid = QSpinBox(); self.lid.setRange(1, 2_000_000_000)
        self.lid.setValue(self._next_license_id())
        form.addRow("机器码", self.machine)
        form.addRow("有效期(天)", self.days)
        form.addRow("授权流水号", self.lid)
        root.addLayout(form)
        gen = QPushButton("生成激活码"); gen.clicked.connect(self._generate)
        root.addWidget(gen)
        self.out = QPlainTextEdit(); self.out.setReadOnly(True)
        root.addWidget(self.out, 1)
        cp = QPushButton("复制激活码"); cp.clicked.connect(self._copy)
        root.addWidget(cp)
        self.hint = QLabel(""); self.hint.setStyleSheet("color:#888")
        root.addWidget(self.hint)

    def _next_license_id(self) -> int:
        if not ISSUED_CSV.exists():
            return 1
        try:
            rows = list(csv.reader(ISSUED_CSV.open(encoding="utf-8")))
            return max((int(r[0]) for r in rows[1:] if r), default=0) + 1
        except (OSError, ValueError):
            return 1

    def _generate(self):
        code = self.machine.text().strip()
        if not code:
            QMessageBox.warning(self, "缺少机器码", "请先粘贴用户的机器码")
            return
        try:
            out = issuer.issue(code, self.days.value(), self.lid.value(), self._sk)
        except Exception as e:                          # 机器码格式错误等
            QMessageBox.critical(self, "签发失败", str(e))
            return
        self.out.setPlainText(out)
        self._record(code, out)
        self.hint.setText(f"已签发 流水号 {self.lid.value()}，有效期 {self.days.value()} 天")
        self.lid.setValue(self.lid.value() + 1)

    def _record(self, machine_code: str, code: str):
        new = not ISSUED_CSV.exists()
        with ISSUED_CSV.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["license_id", "machine_code", "days", "issued_at"])
            w.writerow([self.lid.value(), machine_code, self.days.value(),
                        datetime.datetime.now().isoformat(timespec="seconds")])

    def _copy(self):
        QApplication.clipboard().setText(self.out.toPlainText())
        self.hint.setText("已复制到剪贴板")


def main():
    app = QApplication([])
    w = AdminWindow(); w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 手动验证**

Run: `python -m license_admin.admin_gui`
Expected: 窗口打开；粘贴 `python -c "from drama_shot_master.licensing import fingerprint; print(fingerprint.machine_code())"` 的输出 → 生成激活码、可复制、`license_admin/issued.csv` 追加一行。

- [ ] **Step 3: 提交**

```bash
git add license_admin/admin_gui.py
git commit -m "feat(license_admin): 迷你签发 GUI"
```

---

### Task 7: 关于 / 激活对话框 + 菜单（about_dialog.py）

**Files:**
- Create: `drama_shot_master/ui/dialogs/about_dialog.py`
- Modify: `drama_shot_master/ui/main_window.py`（菜单加「关于」）

UI 任务，手动验证。

- [ ] **Step 1: 实现 about_dialog.py**

```python
"""关于 + 激活对话框：开发者信息 / 授权状态 / 机器码 / 激活码输入。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QGroupBox, QMessageBox,
)

from drama_shot_master.config import Config
from drama_shot_master.licensing import manager
from drama_shot_master.licensing.fingerprint import machine_code

_APP_NAME = "Drama-Shot-Master"
_COPYRIGHT = "© 2026"          # 作者按需补全署名/联系方式


def _app_version() -> str:
    try:
        from importlib.metadata import version
        return version("drama-shot-master")
    except Exception:
        return "dev"


def _status_text(st: manager.LicenseStatus) -> tuple[str, str]:
    S = manager.LicenseState
    if st.state is S.VALID:
        return (f"已激活，有效期至 {st.expiry_date}（剩 {st.days_left} 天）", "#2BAA4A")
    if st.state is S.EXPIRED:
        return (f"已过期（{st.expiry_date}），请输入新激活码", "#D9544D")
    if st.state is S.WRONG_MACHINE:
        return ("此激活码非本机，请用本机机器码重新申请", "#D9544D")
    if st.state is S.TAMPERED:
        return ("激活码无效或已损坏", "#D9544D")
    return ("未激活", "#D9544D")


class AboutDialog(QDialog):
    def __init__(self, cfg: Config, parent=None, activation_focus: bool = False):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("关于")
        self.setModal(True)
        self.resize(520, 460)
        self._build_ui()
        self._refresh_status()

    def _build_ui(self):
        root = QVBoxLayout(self)

        info = QGroupBox("开发者信息")
        iv = QVBoxLayout(info)
        iv.addWidget(QLabel(f"{_APP_NAME}  v{_app_version()}"))
        iv.addWidget(QLabel(_COPYRIGHT))
        root.addWidget(info)

        lic = QGroupBox("授权")
        lv = QVBoxLayout(lic)
        self.status_label = QLabel("…")
        self.status_label.setWordWrap(True)
        lv.addWidget(self.status_label)

        mc = QHBoxLayout()
        self.machine_label = QLabel(machine_code())
        self.machine_label.setTextInteractionFlags(
            self.machine_label.textInteractionFlags() | 0x1)  # TextSelectableByMouse
        mc.addWidget(QLabel("机器码:"))
        mc.addWidget(self.machine_label, 1)
        copy = QPushButton("复制机器码"); copy.clicked.connect(self._copy_machine)
        mc.addWidget(copy)
        lv.addLayout(mc)

        lv.addWidget(QLabel("激活码（粘贴后点激活）:"))
        self.code_input = QPlainTextEdit(); self.code_input.setFixedHeight(90)
        lv.addWidget(self.code_input)
        act = QPushButton("激活"); act.setObjectName("AccentButton")
        act.clicked.connect(self._activate)
        lv.addWidget(act)
        root.addWidget(lic)

    def _refresh_status(self):
        text, color = _status_text(manager.status())
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color:{color}; font-weight:bold;")

    def _copy_machine(self):
        QApplication.clipboard().setText(self.machine_label.text())

    def _activate(self):
        code = self.code_input.toPlainText().strip()
        if not code:
            return
        st = manager.activate(code)
        self._refresh_status()
        if manager.gate_allows(st.state):
            QMessageBox.information(self, "激活成功", "授权已生效。")
            self.accept()
        else:
            text, _ = _status_text(st)
            QMessageBox.warning(self, "激活失败", text)
```

- [ ] **Step 2: main_window 加「关于」菜单**

`drama_shot_master/ui/main_window.py` 的 `_build_ui` 中，紧接「设置」菜单块（即 `sm.addAction(a_st)` 之后、`sp = QSplitter(...)` 之前）插入：

```python
        am = menu.addMenu("关于")
        a_about = QAction("关于…", self)
        a_about.triggered.connect(self._open_about)
        am.addAction(a_about)
```

并在类中（如 `_open_soundtrack_settings` 附近）加方法：

```python
    def _open_about(self):
        from drama_shot_master.ui.dialogs.about_dialog import AboutDialog
        AboutDialog(self.cfg, parent=self).exec()
```

- [ ] **Step 3: 手动验证**

启动应用 → 菜单「关于 → 关于…」打开对话框：显示版本/版权、授权状态（未激活红字）、本机机器码 + 复制、激活码输入框。用 Task 6 GUI 为本机机器码签一张码，粘贴 → 点激活 → 状态变绿「已激活，有效期至 …」。

- [ ] **Step 4: 提交**

```bash
git add drama_shot_master/ui/dialogs/about_dialog.py drama_shot_master/ui/main_window.py
git commit -m "feat(ui): 关于/激活对话框 + 关于菜单"
```

---

### Task 8: 启动门禁 + 到期预警 + 分散校验

**Files:**
- Modify: `drama_shot_master/main.py`
- Modify: `drama_shot_master/ui/main_window.py`
- Test: `tests/test_licensing/test_gate.py`

- [ ] **Step 1: 写门禁判定的失败测试**

`gate_allows` 已在 Task 3 测过；这里测「门禁对话框是否应弹出 + 是否放行」的纯判定，避免逻辑散落。在 `manager.py` 增一个纯函数 `requires_activation(state) -> bool`（= `not gate_allows`）。`tests/test_licensing/test_gate.py`：

```python
from drama_shot_master import licensing
from drama_shot_master.licensing import manager


def test_requires_activation():
    S = manager.LicenseState
    assert manager.requires_activation(S.UNACTIVATED) is True
    assert manager.requires_activation(S.EXPIRED) is True
    assert manager.requires_activation(S.WRONG_MACHINE) is True
    assert manager.requires_activation(S.TAMPERED) is True
    assert manager.requires_activation(S.VALID) is False
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_licensing/test_gate.py -q`
Expected: FAIL（`AttributeError: requires_activation`）

- [ ] **Step 3: 加 requires_activation**

`drama_shot_master/licensing/manager.py` 末尾加：

```python
def requires_activation(state: LicenseState) -> bool:
    return not gate_allows(state)
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_licensing/test_gate.py -q`
Expected: PASS（1 passed）

- [ ] **Step 5: main.py 启动门禁**

`drama_shot_master/main.py` 的 `main()` 中，`apply_app_icon(app)` 之后、`w = MainWindow()` 之前插入：

```python
    from drama_shot_master.licensing import manager
    from drama_shot_master.config import load_config as _lc
    if manager.requires_activation(manager.status().state):
        from drama_shot_master.ui.dialogs.about_dialog import AboutDialog
        gate = AboutDialog(_lc(), activation_focus=True)
        gate.setWindowTitle("激活 Drama-Shot-Master")
        gate.exec()
        if manager.requires_activation(manager.status().state):
            return 0          # 仍未激活 → 退出，不进主界面
```

- [ ] **Step 6: 主界面到期预警 + 运行期复查**

`drama_shot_master/ui/main_window.py` 的 `__init__` 末尾（`self._on_func_changed(start_idx)` 之后）加：

```python
        self._install_license_watch()
```

并加方法（放在 `_open_about` 附近）：

```python
    def _install_license_watch(self):
        from drama_shot_master.licensing import manager
        st = manager.status()
        if st.state is manager.LicenseState.VALID and st.days_left <= 7:
            self.status.setText(f"授权将于 {st.days_left} 天后到期，请及时续期")
        from PySide6.QtCore import QTimer
        self._lic_timer = QTimer(self)
        self._lic_timer.setInterval(24 * 3600 * 1000)   # 每天复查
        self._lic_timer.timeout.connect(self._check_license_runtime)
        self._lic_timer.start()

    def _check_license_runtime(self):
        from drama_shot_master.licensing import manager
        if manager.requires_activation(manager.status().state):
            self._open_about()
            if manager.requires_activation(manager.status().state):
                self.close()
```

- [ ] **Step 7: 分散校验（≥2 处关键入口）**

在 `_do_execute`（`main_window.py`）开头加一处轻量校验：

```python
    def _do_execute(self):
        from drama_shot_master.licensing import manager
        if manager.requires_activation(manager.status().state):
            QMessageBox.warning(self, "需要激活", "请先在「关于」中激活。")
            self._open_about(); return
        panel = self.panels[self.stack.currentIndex()]
        ...
```

第二处加在视频生成提交入口 `drama_shot_master/ui/panels/video_panel.py` 的 `_on_submit` 开头（紧接方法定义，取 cfg 之前）：

```python
        from drama_shot_master.licensing import manager
        if manager.requires_activation(manager.status().state):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "需要激活", "授权无效或已过期，无法提交。")
            return
```

- [ ] **Step 8: 手动验证**

- 删除 license 文件（`%LOCALAPPDATA%/DramaShotMaster/license.txt` 或 `~/.drama_shot_master/license.txt`）→ 启动应用应先弹激活门，不激活点关闭则退出。
- 激活后正常进入。
- 用管理端签一张"明天到期"的码（`expiry_days=1`）激活 → 状态栏出现到期预警文案（`days_left<=7`）。

- [ ] **Step 9: 提交**

```bash
git add drama_shot_master/main.py drama_shot_master/ui/main_window.py drama_shot_master/ui/panels/video_panel.py drama_shot_master/licensing/manager.py tests/test_licensing/test_gate.py
git commit -m "feat(licensing): 启动门禁 + 到期预警 + 关键入口分散校验"
```

---

### Task 9: Nuitka 打包脚本 + 文档

**Files:**
- Create: `build/build_client.sh`（或 `build/build_client.bat`，Windows 实操用 .bat）
- Create: `build/README.md`

无单测，产出可复用构建命令 + 说明。

- [ ] **Step 1: 写 Windows 构建脚本 build/build_client.bat**

```bat
@echo off
REM Drama-Shot-Master 客户端 Nuitka 打包（原生编译，不泄露源码）
REM 前置: pip install nuitka ；建议装 MSVC 或 clang
python -m nuitka ^
  --standalone ^
  --enable-plugin=pyside6 ^
  --include-package=drama_shot_master ^
  --nofollow-import-to=license_admin ^
  --nofollow-import-to=tests ^
  --include-data-dir=drama_shot_master/templates=drama_shot_master/templates ^
  --include-data-dir=drama_shot_master/assets=drama_shot_master/assets ^
  --windows-icon-from-ico=drama_shot_master/assets/app_icon.ico ^
  --windows-console-mode=disable ^
  --output-dir=build/dist ^
  drama_shot_master/main.py
echo 完成。产物在 build/dist/main.dist/
```

- [ ] **Step 2: 写 build/README.md**

````markdown
# 打包客户端（Nuitka）

## 为什么 Nuitka
PyInstaller 打的 .pyc 可被解包反编译；Nuitka 编译成原生二进制，源码不可直接还原。

## 步骤
1. `pip install nuitka`（Windows 需 MSVC/clang）。
2. 确认 `drama_shot_master/licensing/public_key.py` 已是真实公钥（见授权 plan Task 5）。
3. 运行 `build\build_client.bat`。
4. 产物在 `build/dist/main.dist/`，分发整个 `main.dist` 文件夹（多文件模式比 --onefile 杀软误报少）。

## 务必排除
- `license_admin/`（含私钥逻辑）已用 `--nofollow-import-to=license_admin` 排除。
- `license_admin/private_key.pem` 绝不进任何构建/仓库。

## 减少杀软误报（建议，非必须）
- 用代码签名证书签 `main.dist/*.exe`。
- 保持多文件模式（不要 --onefile）。

## 安全边界（务必知悉）
非对称签名杜绝 keygen/伪造、机器绑定防转发；但挡不住有人反汇编 patch 掉验签。
已做：原生编译 + 多处分散校验。目标是抬高门槛而非绝对不可破。
````

- [ ] **Step 3: 提交**

```bash
git add build/build_client.bat build/README.md
git commit -m "build: Nuitka 客户端打包脚本 + 说明"
```

---

## Self-Review

**Spec 覆盖**：
- 离线非对称签名 → Task 1（token）、Task 4（issuer）、Task 5（真实密钥）。✅
- 机器绑定 → Task 2（fingerprint）+ manager 的 WRONG_MACHINE 判定（Task 3）。✅
- 90 天默认有效期 → admin_gui `days` 默认 90（Task 6）。✅
- 到期前 7 天预警 + 过期硬阻断 → Task 8 Step 6/7。✅
- 关于对话框（开发者信息 + 状态 + 机器码 + 激活码输入）→ Task 7。✅
- 管理端迷你 GUI → Task 6；keygen → Task 4/5。✅
- 分散校验 ≥2 入口 → Task 8 Step 7（`_do_execute` + `video_panel._on_submit`）。✅
- Nuitka 打包、排除 license_admin、私钥不外泄 → Task 9 + Task 5 gitignore。✅
- 诚实安全边界 → 写入 build/README.md（Task 9）。✅
- 单测（往返/篡改/过期/非本机/落盘）→ Task 1/3/4/8。✅

**占位扫描**：`public_key.py` 的 `PUBLIC_KEY_B64` 占位是**有意**的，Task 5 用真实值替换并端到端验证——非计划缺口。`_COPYRIGHT` 署名留给作者补全（已注明）。无其它 TBD。

**类型/签名一致性**：`token.sign_token(machine_id, expiry_days, license_id, private_key)` 与 `issuer.issue(... expiry_days_from_now ...)` 区分清楚（issuer 内部把"天数差"转成绝对 epoch 天再调 sign_token）；`machine_id` 全程 10 字节 bytes；`LicenseState`/`LicenseStatus` 字段在 Task 3 定义、Task 7/8 一致引用；`manager._public_key()` 间接取公钥以便测试注入——前后一致。

**已知小坑提示给执行者**：`about_dialog.py` 里用 `0x1`（TextSelectableByMouse）是为省 import；执行时若想更规范可改 `from PySide6.QtCore import Qt; Qt.TextSelectableByMouse`。
