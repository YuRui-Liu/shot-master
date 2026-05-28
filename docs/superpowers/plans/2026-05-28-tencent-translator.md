# Tencent Translator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce Tencent Cloud Machine Translation (TMT) as the default translation provider, refactoring the current single-function `translator.py` into a `TranslationProvider` ABC with two implementations (Tencent + DeepLX) that the user can switch between in settings.

**Architecture:** ABC with two thin implementations (`TencentTranslator`, `DeepLXTranslator`). Facade module preserves the legacy `translate_en_to_zh(text) -> str | None` signature for backward compat. Process-internal LRU(64) cache keyed by `(provider, source, target, sha256(text)[:16])`, storing only successful results. Tencent uses the official `tencentcloud-sdk-python-tmt` (Apache-2.0) which handles TC3-HMAC-SHA256 v3 signing. Configuration goes through `cfg` parameter when available, falls back to `os.environ` for the legacy no-arg path. Failures bubble up as `TranslationResult.error: TranslationError(code, hint, retryable)` with eight semantic codes that the UI dialog maps to differentiated action buttons.

**Tech Stack:** Python 3.11+, PySide6 (settings UI + button), `tencentcloud-sdk-python-tmt>=3.0.1207,<4.0.0`, `urllib.request` for DeepLX. Tests use `pytest` + `monkeypatch`; UI smoke runs under `QT_QPA_PLATFORM=offscreen`.

**Spec reference:** [`docs/superpowers/specs/2026-05-28-tencent-translator-design.md`](../specs/2026-05-28-tencent-translator-design.md)

---

## File Structure

**Create (11 files):**

| Path | Responsibility |
|---|---|
| `drama_shot_master/providers/translation_base.py` | `TranslationProvider` ABC, `TranslationResult`/`TranslationError` dataclasses, `TranslationErrorCode` constants |
| `drama_shot_master/providers/tencent_translator.py` | Tencent TMT implementation + `_map_tencent_error()` |
| `drama_shot_master/providers/deeplx_translator.py` | DeepLX implementation (migrated logic from current `translator.py`) |
| `tests/test_providers/test_translation_base.py` | ABC + dataclass behavior tests |
| `tests/test_providers/test_tencent_translator.py` | Mock SDK; ~12 cases |
| `tests/test_providers/test_deeplx_translator.py` | Mock urlopen; ~10 cases |
| `tests/test_providers/test_translator_facade.py` | Factory + delegation tests |
| `tests/test_providers/test_translator_cache.py` | LRU behavior tests |
| `tests/test_ui/test_translation_section_smoke.py` | Settings section offscreen smoke |
| `tests/test_ui/test_translate_button_smoke.py` | (P2) Translate button + dialog smoke with structured errors |
| `tests/manual/test_tencent_real.py` | Opt-in real-API smoke (`@pytest.mark.requires_tencent_creds`) |

**Modify (7 files):**

| Path | Change |
|---|---|
| `pyproject.toml` | Add `tencentcloud-sdk-python-tmt>=3.0.1207,<4.0.0` dependency |
| `drama_shot_master/config.py` | +5 fields (`current_translator`, `tencent_translator_secret_id/_secret_key/_region/_project_id`); serialize/load; `.env` mapping; env writeback; `_post_load_migrate` helper |
| `drama_shot_master/providers/translator.py` | Rewrite as facade: `translate_en_to_zh` (legacy) + `translate(text, src, tgt, cfg=None)` (new) + `build_translation_provider(cfg=None)` + LRU helpers (`clear_cache`, `get_cache_stats`) |
| `drama_shot_master/ui/widgets/settings_sections/translation_section.py` | Redesign: radio + `QStackedWidget` for Tencent/DeepLX panes + "测试连接" button |
| `drama_shot_master/ui/widgets/translate_button.py` | (P2) Switch from `translate_en_to_zh` to `translate(...)`; `_TranslateDialog` accepts `TranslationResult`; differentiated buttons by `error.code` + 5s countdown on `RATE_LIMITED` |
| `tests/test_providers/test_translator.py` | Rewrite to 3 backward-compat sentinel cases |
| `tests/test_config.py` | +4 cases (round-trip new fields, `.env` overlay, migrate variants) |

---

## Task 0: Add Tencent SDK dependency (non-TDD)

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read current dependencies**

Run: `grep -nA 5 'dependencies' pyproject.toml | head -40`
Expected: Find the `[project] dependencies` array.

- [ ] **Step 2: Add the dependency line**

Edit `pyproject.toml`, append inside the `[project] dependencies` array:

```toml
"tencentcloud-sdk-python-tmt>=3.0.1207,<4.0.0",
```

Place it alphabetically next to existing `tencent*` or generic SDK entries; otherwise at the end of the array (before the closing `]`).

- [ ] **Step 3: Install in editable mode**

Run: `pip install -e .`
Expected: `tencentcloud-sdk-python-tmt` and its transitive `tencentcloud-sdk-python-common` installed.

- [ ] **Step 4: Verify import works**

Run:
```bash
python -c "from tencentcloud.tmt.v20180321 import tmt_client, models; print(tmt_client.TmtClient.__module__)"
```
Expected: `tencentcloud.tmt.v20180321.tmt_client`

- [ ] **Step 5: Verify wheel license mentions Apache**

Run:
```bash
python -c "import importlib.metadata as m; meta = m.metadata('tencentcloud-sdk-python-tmt'); print('License:', meta.get('License', '')); print('Classifiers:', [c for c in meta.get_all('Classifier') or [] if 'License' in c])"
```
Expected: the output mentions `Apache` somewhere (e.g. `Apache License Version 2.0`, `Apache-2.0`, or `License :: OSI Approved :: Apache Software License`). If `GPL` / `AGPL` / `LGPL` appears anywhere, **halt the plan and surface to user** — the project's `feedback_no_gpl_deps` rule forbids GPL-family licenses.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml
git commit -m "build: 加 tencentcloud-sdk-python-tmt 依赖（腾讯翻译 provider 用）"
```

---

## Task 1: TranslationProvider ABC + dataclasses (TDD)

**Files:**
- Create: `drama_shot_master/providers/translation_base.py`
- Test: `tests/test_providers/test_translation_base.py`

**Dependencies:** Task 0 (so installer runs once early).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_providers/test_translation_base.py`:

```python
"""Tests for translation_base ABC + dataclasses."""
from __future__ import annotations

import pytest

from drama_shot_master.providers.translation_base import (
    TranslationError, TranslationErrorCode, TranslationProvider,
    TranslationResult,
)


def test_result_success_factory():
    r = TranslationResult.success("你好", "tencent", used_chars=5)
    assert r.ok is True
    assert r.text == "你好"
    assert r.error is None
    assert r.provider == "tencent"
    assert r.used_chars == 5


def test_result_fail_factory_propagates_provider():
    err = TranslationError(
        code=TranslationErrorCode.AUTH_FAILED,
        message="bad cred", hint="去设置",
        retryable=False, provider="deeplx")
    r = TranslationResult.fail(err)
    assert r.ok is False
    assert r.text is None
    assert r.error is err
    assert r.provider == "deeplx"
    assert r.used_chars == 0


def test_error_codes_are_unique_strings():
    codes = {
        TranslationErrorCode.AUTH_FAILED,
        TranslationErrorCode.QUOTA_EXHAUSTED,
        TranslationErrorCode.SERVICE_DISABLED,
        TranslationErrorCode.RATE_LIMITED,
        TranslationErrorCode.INVALID_INPUT,
        TranslationErrorCode.LANGUAGE_UNSUPPORTED,
        TranslationErrorCode.NETWORK,
        TranslationErrorCode.UNKNOWN,
    }
    assert len(codes) == 8
    assert all(isinstance(c, str) and c == c.upper() for c in codes)


def test_result_is_frozen():
    r = TranslationResult.success("hi", "x")
    with pytest.raises((AttributeError, Exception)):
        r.ok = False  # type: ignore[misc]


def test_error_is_frozen():
    err = TranslationError(
        code="X", message="m", hint="h", retryable=True, provider="p")
    with pytest.raises((AttributeError, Exception)):
        err.code = "Y"  # type: ignore[misc]


def test_subclass_must_implement_translate_and_health_check():
    class Incomplete(TranslationProvider):
        name = "incomplete"
    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_providers/test_translation_base.py -v`
Expected: All 6 tests fail with `ModuleNotFoundError: drama_shot_master.providers.translation_base`.

- [ ] **Step 3: Implement `translation_base.py`**

Create `drama_shot_master/providers/translation_base.py`:

```python
"""翻译 provider 的统一抽象基类 + 结构化结果/错误数据类。

设计原则：
- 所有 provider 的 translate() 不抛异常，统一返回 TranslationResult。
- 错误用 TranslationError(code, message, hint, retryable, provider) 描述：
  - code 是 SCREAMING_SNAKE_CASE 字符串常量，UI/日志匹配用；
  - hint 是面向用户的中文人话；
  - retryable 决定 UI 要不要给"重试"按钮。
- TranslationResult / TranslationError 都是 frozen dataclass，便于缓存/日志。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar


class TranslationErrorCode:
    """错误码常量。值故意用 SCREAMING_SNAKE_CASE 便于 UI 文案/日志匹配。"""
    AUTH_FAILED          = "AUTH_FAILED"          # 凭证/签名错
    QUOTA_EXHAUSTED      = "QUOTA_EXHAUSTED"      # 余额/免费额度耗尽
    SERVICE_DISABLED     = "SERVICE_DISABLED"     # 未开通服务（如腾讯账号未开 TMT）
    RATE_LIMITED         = "RATE_LIMITED"         # QPS 触顶
    INVALID_INPUT        = "INVALID_INPUT"        # 空文本 / 超长 / 非法参数
    LANGUAGE_UNSUPPORTED = "LANGUAGE_UNSUPPORTED" # provider 不支持该 src/tgt 组合
    NETWORK              = "NETWORK"              # 连接失败 / 超时
    UNKNOWN              = "UNKNOWN"              # 兜底


@dataclass(frozen=True)
class TranslationError:
    code: str                # TranslationErrorCode.*
    message: str             # provider 原始 message（英文为主，便于 grep 日志）
    hint: str                # 中文用户人话
    retryable: bool          # 是否值得让用户点"重试"
    provider: str            # "tencent" / "deeplx" / "none"


@dataclass(frozen=True)
class TranslationResult:
    ok: bool
    text: str | None         # ok=True 时是译文
    error: TranslationError | None  # ok=False 时非空
    provider: str
    used_chars: int = 0      # 腾讯返回 UsedAmount；DeepLX 取 len(text)

    @classmethod
    def success(cls, text: str, provider: str,
                used_chars: int = 0) -> "TranslationResult":
        return cls(ok=True, text=text, error=None, provider=provider,
                   used_chars=used_chars)

    @classmethod
    def fail(cls, error: TranslationError) -> "TranslationResult":
        return cls(ok=False, text=None, error=error,
                   provider=error.provider, used_chars=0)


class TranslationProvider(ABC):
    """所有翻译 provider 的统一契约。

    语言代码用小写 ISO-639-1 + "auto"；各实现负责映射到自家代码体系。
    任何异常都不应抛出 —— 应返回 TranslationResult(ok=False, error=...)。
    """
    name: ClassVar[str]  # 子类必须覆盖，如 "tencent" / "deeplx"

    @abstractmethod
    def translate(self, text: str, source: str = "auto",
                  target: str = "zh") -> TranslationResult:
        ...

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """快速探活：(ok, message)。settings UI 的"测试连接"按钮用。
        实现可发一次微小请求或仅验证凭证字段非空。"""
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_providers/test_translation_base.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/providers/translation_base.py tests/test_providers/test_translation_base.py
git commit -m "feat(providers): TranslationProvider ABC + Result/Error 数据类 + 8 错误码"
```

---

## Task 2: TencentTranslator implementation (TDD)

**Files:**
- Create: `drama_shot_master/providers/tencent_translator.py`
- Create: `tests/test_providers/conftest.py` (SDK isolation fixture)
- Test: `tests/test_providers/test_tencent_translator.py`

**Dependencies:** Task 0 (SDK installed), Task 1 (ABC available).

- [ ] **Step 1: Create SDK-isolating conftest**

Create `tests/test_providers/conftest.py`:

```python
"""Shared fixtures for providers tests.

The Tencent SDK gets monkeypatched at module level so individual tests can
override TextTranslate behavior cheaply, and no test ever performs a real
network call to Tencent.
"""
from __future__ import annotations

import pytest


class _StubTmtClient:
    """Drop-in for tencentcloud.tmt.v20180321.tmt_client.TmtClient.

    Individual tests override `TextTranslate` per-instance or class-wide.
    """
    def __init__(self, cred, region, profile):
        self._credential = cred
        self._region = region
        self._profile = profile

    def TextTranslate(self, req):  # noqa: N802 — matches SDK casing
        raise NotImplementedError("test must override TextTranslate")


@pytest.fixture
def stub_tmt_client(monkeypatch):
    """Patch the SDK's TmtClient with our stub for this test only."""
    monkeypatch.setattr(
        "tencentcloud.tmt.v20180321.tmt_client.TmtClient", _StubTmtClient)
    return _StubTmtClient
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_providers/test_tencent_translator.py`:

```python
"""Tests for TencentTranslator."""
from __future__ import annotations

import pytest

from drama_shot_master.providers.translation_base import (
    TranslationErrorCode,
)

# Import lazily inside tests to ensure the stub is patched before
# real construction; but for type checks we need the class.


def _make_translator(stub_tmt_client, **kwargs):
    from drama_shot_master.providers.tencent_translator import TencentTranslator
    defaults = dict(secret_id="fake_id", secret_key="fake_key",
                    region="ap-beijing", project_id=0)
    defaults.update(kwargs)
    return TencentTranslator(**defaults)


def _fake_response(target_text="你好", used_amount=5,
                   source="en", target="zh", request_id="fake-req"):
    """Build a TextTranslateResponse-shaped object."""
    return type("R", (), {
        "TargetText": target_text, "UsedAmount": used_amount,
        "Source": source, "Target": target, "RequestId": request_id})()


def _raise(exc):
    """Return a method that raises the given exception."""
    def _method(self, req):
        raise exc
    return _method


def test_init_rejects_empty_secret_id(stub_tmt_client):
    from drama_shot_master.providers.tencent_translator import TencentTranslator
    with pytest.raises(ValueError, match="凭证"):
        TencentTranslator(secret_id="", secret_key="x")


def test_translate_success(stub_tmt_client):
    stub_tmt_client.TextTranslate = lambda self, req: _fake_response("你好", 5)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.ok is True
    assert r.text == "你好"
    assert r.used_chars == 5
    assert r.provider == "tencent"


def test_translate_empty_text_returns_invalid_input(stub_tmt_client):
    t = _make_translator(stub_tmt_client)
    r = t.translate("", "en", "zh")
    assert r.ok is False
    assert r.error.code == TranslationErrorCode.INVALID_INPUT
    assert r.error.retryable is False


def test_translate_oversize_text_returns_invalid_input(stub_tmt_client):
    t = _make_translator(stub_tmt_client)
    text = "a" * 6001  # 6001 UTF-8 bytes (ASCII), exceeds 6000-byte limit
    r = t.translate(text, "en", "zh")
    assert r.ok is False
    assert r.error.code == TranslationErrorCode.INVALID_INPUT
    assert "6000" in r.error.hint


def test_translate_unsupported_target_returns_language_unsupported(stub_tmt_client):
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "xx")
    assert r.ok is False
    assert r.error.code == TranslationErrorCode.LANGUAGE_UNSUPPORTED


def test_translate_auth_failure_signature_failure(stub_tmt_client):
    from tencentcloud.common.exception.tencent_cloud_sdk_exception \
        import TencentCloudSDKException
    exc = TencentCloudSDKException(
        code="AuthFailure.SignatureFailure",
        message="credentials invalid", requestId="r1")
    stub_tmt_client.TextTranslate = _raise(exc)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.ok is False
    assert r.error.code == TranslationErrorCode.AUTH_FAILED
    assert r.error.retryable is False


def test_translate_auth_failure_signature_expire_also_maps(stub_tmt_client):
    """Prefix match: any AuthFailure.* → AUTH_FAILED."""
    from tencentcloud.common.exception.tencent_cloud_sdk_exception \
        import TencentCloudSDKException
    exc = TencentCloudSDKException(
        code="AuthFailure.SignatureExpire",
        message="signature expired", requestId="r2")
    stub_tmt_client.TextTranslate = _raise(exc)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.AUTH_FAILED


def test_translate_no_free_amount_maps_to_quota(stub_tmt_client):
    from tencentcloud.common.exception.tencent_cloud_sdk_exception \
        import TencentCloudSDKException
    exc = TencentCloudSDKException(
        code="FailedOperation.NoFreeAmount",
        message="quota exhausted", requestId="r3")
    stub_tmt_client.TextTranslate = _raise(exc)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.QUOTA_EXHAUSTED


def test_translate_service_isolate_maps_to_service_disabled(stub_tmt_client):
    from tencentcloud.common.exception.tencent_cloud_sdk_exception \
        import TencentCloudSDKException
    exc = TencentCloudSDKException(
        code="FailedOperation.ServiceIsolate",
        message="service disabled", requestId="r4")
    stub_tmt_client.TextTranslate = _raise(exc)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.SERVICE_DISABLED


def test_translate_rate_limit_is_retryable(stub_tmt_client):
    from tencentcloud.common.exception.tencent_cloud_sdk_exception \
        import TencentCloudSDKException
    exc = TencentCloudSDKException(
        code="RequestLimitExceeded",
        message="qps limit", requestId="r5")
    stub_tmt_client.TextTranslate = _raise(exc)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.RATE_LIMITED
    assert r.error.retryable is True


def test_translate_invalid_parameter_maps_to_invalid_input(stub_tmt_client):
    from tencentcloud.common.exception.tencent_cloud_sdk_exception \
        import TencentCloudSDKException
    exc = TencentCloudSDKException(
        code="InvalidParameter.SomeField",
        message="bad field", requestId="r6")
    stub_tmt_client.TextTranslate = _raise(exc)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.INVALID_INPUT


def test_translate_unknown_code_is_retryable(stub_tmt_client):
    from tencentcloud.common.exception.tencent_cloud_sdk_exception \
        import TencentCloudSDKException
    exc = TencentCloudSDKException(
        code="SomethingNew.WeDoNotKnow",
        message="???", requestId="r7")
    stub_tmt_client.TextTranslate = _raise(exc)
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.UNKNOWN
    assert r.error.retryable is True


def test_translate_network_error_maps_to_network(stub_tmt_client):
    stub_tmt_client.TextTranslate = _raise(OSError("connection refused"))
    t = _make_translator(stub_tmt_client)
    r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.NETWORK
    assert r.error.retryable is True


def test_health_check_with_credentials(stub_tmt_client):
    t = _make_translator(stub_tmt_client)
    ok, _msg = t.health_check()
    assert ok is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_providers/test_tencent_translator.py -v`
Expected: All ~14 tests fail with `ModuleNotFoundError: drama_shot_master.providers.tencent_translator`.

- [ ] **Step 4: Implement `tencent_translator.py`**

Create `drama_shot_master/providers/tencent_translator.py`:

```python
"""Tencent Cloud Machine Translation (TMT) provider。

通过官方 tencentcloud-sdk-python-tmt 调 TextTranslate 接口。
SDK 自己处理 TC3-HMAC-SHA256 v3 签名 / 重试 / endpoint resolution。
我们只负责：参数校验 + SDK 异常 → TranslationError 映射 + 网络异常兜底。
"""
from __future__ import annotations

import logging

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception \
    import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.tmt.v20180321 import models, tmt_client

from drama_shot_master.providers.translation_base import (
    TranslationError, TranslationErrorCode, TranslationProvider,
    TranslationResult,
)

log = logging.getLogger(__name__)

# 腾讯支持的 target 语种（含 source "auto" 已隐含）
_TENCENT_LANGS = {
    "zh", "zh-TW", "en", "ja", "ko", "fr", "es", "it", "de",
    "tr", "ru", "pt", "vi", "id", "th", "ms", "ar", "hi",
}

# 统一码 → 腾讯码（基本一致；显式表加防御性）
_LANG_MAP = {"auto": "auto", "zh": "zh", "en": "en",
             "ja": "ja", "ko": "ko"}


class TencentTranslator(TranslationProvider):
    name = "tencent"

    def __init__(self, secret_id: str, secret_key: str,
                 region: str = "ap-beijing", project_id: int = 0,
                 timeout: float = 10.0):
        if not secret_id or not secret_key:
            raise ValueError("Tencent 凭证不完整")
        cred = credential.Credential(secret_id, secret_key)
        http_profile = HttpProfile(reqTimeout=int(timeout))
        client_profile = ClientProfile(httpProfile=http_profile)
        self._client = tmt_client.TmtClient(cred, region, client_profile)
        self._project_id = int(project_id or 0)

    def translate(self, text: str, source: str = "auto",
                  target: str = "zh") -> TranslationResult:
        # 1. 入参校验
        if not text or not text.strip():
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.INVALID_INPUT,
                message="empty text",
                hint="输入是空的，没什么可翻译的",
                retryable=False, provider=self.name))
        byte_len = len(text.encode("utf-8"))
        if byte_len > 6000:
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.INVALID_INPUT,
                message=f"text length {byte_len} > 6000 bytes",
                hint="腾讯单次最多 6000 字符（UTF-8 字节），文本太长，分段后再试",
                retryable=False, provider=self.name))
        src = _LANG_MAP.get(source, source)
        tgt = _LANG_MAP.get(target, target)
        if tgt not in _TENCENT_LANGS:
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.LANGUAGE_UNSUPPORTED,
                message=f"target {target} not supported",
                hint=f"腾讯翻译不支持目标语种 {target}",
                retryable=False, provider=self.name))

        # 2. 调 SDK
        req = models.TextTranslateRequest()
        req.SourceText = text
        req.Source = src
        req.Target = tgt
        req.ProjectId = self._project_id
        try:
            resp = self._client.TextTranslate(req)
        except TencentCloudSDKException as e:
            err = _map_tencent_error(e)
            self._log_error(err)
            return TranslationResult.fail(err)
        except (OSError, ConnectionError, TimeoutError) as e:
            err = TranslationError(
                code=TranslationErrorCode.NETWORK,
                message=str(e),
                hint="网络问题连不上腾讯，检查网络/代理后重试",
                retryable=True, provider=self.name)
            self._log_error(err)
            return TranslationResult.fail(err)

        # 3. 包结果
        used = getattr(resp, "UsedAmount", None)
        used = int(used) if used is not None else len(text)
        log.info("translate ok: tencent %s→%s, %d chars", src, tgt, used)
        return TranslationResult.success(
            text=resp.TargetText, provider=self.name, used_chars=used)

    def health_check(self) -> tuple[bool, str]:
        # 不发请求（避免无谓计费），仅校验凭证字段
        cred = self._client._credential  # noqa: SLF001 — SDK 暴露的内部属性
        if not getattr(cred, "secretId", "") or not getattr(cred, "secretKey", ""):
            return False, "凭证为空"
        return True, "凭证已配置"

    def _log_error(self, err: TranslationError) -> None:
        level = logging.WARNING if err.retryable else logging.ERROR
        log.log(level, "tencent %s: %s", err.code, err.message)


def _map_tencent_error(e: TencentCloudSDKException) -> TranslationError:
    """把腾讯 SDK 异常 code 映射为统一 TranslationError。
    code 详见 https://cloud.tencent.com/document/api/551/15619 错误码段。"""
    code = (getattr(e, "code", "") or "").strip()
    msg = getattr(e, "message", "") or ""
    if code.startswith("AuthFailure"):
        return TranslationError(
            code=TranslationErrorCode.AUTH_FAILED,
            message=f"{code}: {msg}",
            hint="腾讯凭证错误，去设置里检查 SecretId/SecretKey/Region",
            retryable=False, provider="tencent")
    if code in {"FailedOperation.NoFreeAmount",
                "FailedOperation.UserNotRegistered"}:
        return TranslationError(
            code=TranslationErrorCode.QUOTA_EXHAUSTED,
            message=f"{code}: {msg}",
            hint="腾讯翻译额度用完了，去控制台充值或开通付费服务",
            retryable=False, provider="tencent")
    if code == "FailedOperation.ServiceIsolate":
        return TranslationError(
            code=TranslationErrorCode.SERVICE_DISABLED,
            message=f"{code}: {msg}",
            hint="腾讯账号下 TMT 服务未开通或已停用，去控制台开通",
            retryable=False, provider="tencent")
    if code.startswith("RequestLimitExceeded"):
        return TranslationError(
            code=TranslationErrorCode.RATE_LIMITED,
            message=f"{code}: {msg}",
            hint="请求太快了（5 QPS 上限），稍等几秒再试",
            retryable=True, provider="tencent")
    if (code.startswith("InvalidParameter")
            or code.startswith("UnsupportedOperation")):
        return TranslationError(
            code=TranslationErrorCode.INVALID_INPUT,
            message=f"{code}: {msg}",
            hint=f"腾讯说参数有问题：{msg}",
            retryable=False, provider="tencent")
    return TranslationError(
        code=TranslationErrorCode.UNKNOWN,
        message=f"{code}: {msg}",
        hint=f"腾讯返回未知错误：{code}，详情查日志",
        retryable=True, provider="tencent")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_providers/test_tencent_translator.py -v`
Expected: All ~14 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add drama_shot_master/providers/tencent_translator.py \
        tests/test_providers/test_tencent_translator.py \
        tests/test_providers/conftest.py
git commit -m "feat(providers): TencentTranslator 实现 + 错误码映射 + 14 单元用例"
```

---

## Task 3: DeepLXTranslator implementation (TDD)

**Files:**
- Create: `drama_shot_master/providers/deeplx_translator.py`
- Test: `tests/test_providers/test_deeplx_translator.py`

**Dependencies:** Task 1.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_providers/test_deeplx_translator.py`:

```python
"""Tests for DeepLXTranslator."""
from __future__ import annotations

import io
import json
import socket
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from drama_shot_master.providers.deeplx_translator import DeepLXTranslator
from drama_shot_master.providers.translation_base import TranslationErrorCode


_URL = "https://example.test/translate"


def _fake_response(body: bytes):
    class _FakeResp:
        def __enter__(self_inner):
            return io.BytesIO(body)
        def __exit__(self_inner, *exc):
            return False
    return _FakeResp()


def _http_error(code: int):
    return HTTPError(_URL, code, f"http {code}", {}, None)


def test_init_rejects_empty_url():
    with pytest.raises(ValueError):
        DeepLXTranslator(url="")


def test_translate_success_returns_text():
    t = DeepLXTranslator(url=_URL)
    body = json.dumps({"code": 200, "data": "你好"}).encode("utf-8")
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               return_value=_fake_response(body)):
        r = t.translate("hello", "en", "zh")
    assert r.ok is True
    assert r.text == "你好"
    assert r.used_chars == len("hello")
    assert r.provider == "deeplx"


def test_empty_text_returns_invalid_input():
    t = DeepLXTranslator(url=_URL)
    r = t.translate("", "en", "zh")
    assert r.ok is False
    assert r.error.code == TranslationErrorCode.INVALID_INPUT


def test_unsupported_target_returns_language_unsupported():
    t = DeepLXTranslator(url=_URL)
    r = t.translate("hello", "en", "xy")
    assert r.error.code == TranslationErrorCode.LANGUAGE_UNSUPPORTED


def test_http_401_maps_to_auth_failed():
    t = DeepLXTranslator(url=_URL)
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               side_effect=_http_error(401)):
        r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.AUTH_FAILED
    assert r.error.retryable is False


def test_http_429_maps_to_rate_limited():
    t = DeepLXTranslator(url=_URL)
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               side_effect=_http_error(429)):
        r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.RATE_LIMITED
    assert r.error.retryable is True


def test_http_500_maps_to_unknown_retryable():
    t = DeepLXTranslator(url=_URL)
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               side_effect=_http_error(500)):
        r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.UNKNOWN
    assert r.error.retryable is True


def test_url_error_maps_to_network():
    t = DeepLXTranslator(url=_URL)
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               side_effect=URLError("connection refused")):
        r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.NETWORK
    assert r.error.retryable is True


def test_socket_timeout_maps_to_network():
    t = DeepLXTranslator(url=_URL)
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               side_effect=socket.timeout("timed out")):
        r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.NETWORK


def test_non_json_response_maps_to_unknown():
    t = DeepLXTranslator(url=_URL)
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               return_value=_fake_response(b"not json at all")):
        r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.UNKNOWN


def test_empty_data_field_maps_to_unknown():
    t = DeepLXTranslator(url=_URL)
    body = json.dumps({"code": 200, "data": ""}).encode("utf-8")
    with patch("drama_shot_master.providers.deeplx_translator.urlopen",
               return_value=_fake_response(body)):
        r = t.translate("hello", "en", "zh")
    assert r.error.code == TranslationErrorCode.UNKNOWN


def test_health_check_returns_true_when_url_set():
    t = DeepLXTranslator(url=_URL)
    ok, _ = t.health_check()
    assert ok is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_providers/test_deeplx_translator.py -v`
Expected: All tests fail with `ModuleNotFoundError: drama_shot_master.providers.deeplx_translator`.

- [ ] **Step 3: Implement `deeplx_translator.py`**

Create `drama_shot_master/providers/deeplx_translator.py`:

```python
"""DeepLX 翻译 provider（自部署或公共 DeepLX 实例）。

从原 drama_shot_master/providers/translator.py 拆出来，逻辑基本不变；
区别是返回 TranslationResult 而非 str | None，并把 HTTP/网络错误映射为
统一 TranslationError code。
"""
from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from drama_shot_master.providers.translation_base import (
    TranslationError, TranslationErrorCode, TranslationProvider,
    TranslationResult,
)

log = logging.getLogger(__name__)

# DeepLX 的 target_lang 用大写短码
_DEEPLX_TARGET_MAP = {"zh": "ZH", "en": "EN", "ja": "JA", "ko": "KO"}

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "drama-shot-master/translator",
}


class DeepLXTranslator(TranslationProvider):
    name = "deeplx"

    def __init__(self, url: str, timeout: float = 3.0):
        if not url or not url.strip():
            raise ValueError("DeepLX URL 为空")
        self._url = url.strip()
        self._timeout = float(timeout)

    def translate(self, text: str, source: str = "auto",
                  target: str = "zh") -> TranslationResult:
        if not text or not text.strip():
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.INVALID_INPUT,
                message="empty text", hint="输入是空的",
                retryable=False, provider=self.name))
        tgt = _DEEPLX_TARGET_MAP.get(target)
        if tgt is None:
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.LANGUAGE_UNSUPPORTED,
                message=f"target {target} unsupported",
                hint=f"DeepLX 不支持 {target}",
                retryable=False, provider=self.name))

        payload = json.dumps({"text": text, "source_lang": "auto",
                              "target_lang": tgt}).encode("utf-8")
        req = Request(self._url, data=payload, method="POST",
                      headers=_HEADERS)
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
        except HTTPError as e:
            err = self._map_http_error(e)
            self._log_error(err)
            return TranslationResult.fail(err)
        except (URLError, OSError) as e:
            err = TranslationError(
                code=TranslationErrorCode.NETWORK,
                message=str(e),
                hint=f"连不上 DeepLX（{self._url}），检查网络/部署",
                retryable=True, provider=self.name)
            self._log_error(err)
            return TranslationResult.fail(err)

        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            err = TranslationError(
                code=TranslationErrorCode.UNKNOWN,
                message="bad JSON",
                hint="DeepLX 返回非 JSON",
                retryable=True, provider=self.name)
            self._log_error(err)
            return TranslationResult.fail(err)

        data = obj.get("data") if isinstance(obj, dict) else None
        if not isinstance(data, str) or not data:
            err = TranslationError(
                code=TranslationErrorCode.UNKNOWN,
                message=f"missing data in {obj!r}",
                hint="DeepLX 返回格式异常",
                retryable=True, provider=self.name)
            self._log_error(err)
            return TranslationResult.fail(err)

        log.info("translate ok: deeplx auto→%s, %d chars", target, len(text))
        return TranslationResult.success(
            text=data, provider=self.name, used_chars=len(text))

    def health_check(self) -> tuple[bool, str]:
        return bool(self._url), self._url or "URL 未配置"

    def _map_http_error(self, e: HTTPError) -> TranslationError:
        if e.code in (401, 403):
            return TranslationError(
                code=TranslationErrorCode.AUTH_FAILED,
                message=f"HTTP {e.code}",
                hint="DeepLX 拒绝访问，检查 URL 或鉴权",
                retryable=False, provider=self.name)
        if e.code == 429:
            return TranslationError(
                code=TranslationErrorCode.RATE_LIMITED,
                message="HTTP 429",
                hint="DeepLX 频控触顶，稍等再试",
                retryable=True, provider=self.name)
        return TranslationError(
            code=TranslationErrorCode.UNKNOWN,
            message=f"HTTP {e.code}",
            hint=f"DeepLX 返回 HTTP {e.code}",
            retryable=True, provider=self.name)

    def _log_error(self, err: TranslationError) -> None:
        level = logging.WARNING if err.retryable else logging.ERROR
        log.log(level, "deeplx %s: %s", err.code, err.message)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_providers/test_deeplx_translator.py -v`
Expected: All ~12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/providers/deeplx_translator.py \
        tests/test_providers/test_deeplx_translator.py
git commit -m "feat(providers): DeepLXTranslator 实现（从 translator.py 拆出）+ 12 单元用例"
```

---

## Task 4: Config fields + .env loading + post-load migration (TDD)

**Files:**
- Modify: `drama_shot_master/config.py`
- Test: `tests/test_config.py` (append)

**Dependencies:** None (config is self-contained).

- [ ] **Step 1: Read the existing config to locate insertion points**

Run:
```bash
grep -nE 'deeplx_url|refine_api_key|update_settings|load_from_disk|_post_load|api_key_env|os\.environ\["DEEPLX_URL"\]' drama_shot_master/config.py | head -30
```
Expected: Find existing `deeplx_url: str = ""`, the `update_settings` dict, the `load_from_disk` field-batch loop, the `.env` mapping section, and the `os.environ["DEEPLX_URL"] = ...` line near config load.

- [ ] **Step 2: Write failing tests for new fields**

Append to `tests/test_config.py`:

```python
# ── Tencent translator fields & migration ─────────────────────────────────

def test_save_load_tencent_translator_fields(tmp_path, monkeypatch):
    from drama_shot_master.config import load_config
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=tmp_path / "settings.json")
    cfg.update_settings(
        current_translator="tencent",
        tencent_translator_secret_id="sid-x",
        tencent_translator_secret_key="skey-y",
        tencent_translator_region="ap-shanghai",
        tencent_translator_project_id=42,
    )
    cfg2 = load_config(env_path=tmp_path / ".env",
                        settings_path=tmp_path / "settings.json")
    assert cfg2.current_translator == "tencent"
    assert cfg2.tencent_translator_secret_id == "sid-x"
    assert cfg2.tencent_translator_secret_key == "skey-y"
    assert cfg2.tencent_translator_region == "ap-shanghai"
    assert cfg2.tencent_translator_project_id == 42


def test_tencent_env_overlay_fills_missing_secret_id(tmp_path, monkeypatch):
    from drama_shot_master.config import load_config
    monkeypatch.setenv("TENCENTCLOUD_SECRET_ID", "env-sid")
    monkeypatch.setenv("TENCENTCLOUD_SECRET_KEY", "env-skey")
    monkeypatch.setenv("TENCENTCLOUD_REGION", "ap-guangzhou")
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=tmp_path / "settings.json")
    assert cfg.tencent_translator_secret_id == "env-sid"
    assert cfg.tencent_translator_secret_key == "env-skey"
    assert cfg.tencent_translator_region == "ap-guangzhou"


def test_post_load_migrate_keeps_deeplx_when_only_deeplx_configured(
        tmp_path, monkeypatch):
    """旧用户仅配过 deeplx_url → current_translator 自动设为 deeplx。"""
    import json
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "deeplx_url": "http://localhost:1188/translate",
    }), encoding="utf-8")
    from drama_shot_master.config import load_config
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=settings_path)
    assert cfg.current_translator == "deeplx"
    assert cfg.deeplx_url == "http://localhost:1188/translate"


def test_post_load_migrate_defaults_to_tencent_when_empty(tmp_path):
    from drama_shot_master.config import load_config
    cfg = load_config(env_path=tmp_path / ".env",
                       settings_path=tmp_path / "settings.json")
    assert cfg.current_translator == "tencent"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v -k 'tencent or post_load_migrate'`
Expected: All 4 new tests fail with `AttributeError` (field missing) or `assert "" == "tencent"`.

- [ ] **Step 4: Add fields to the dataclass**

Edit `drama_shot_master/config.py`. Find the existing `deeplx_url: str = ""` line in the `@dataclass class Config:` block; add directly below it:

```python
    current_translator: str = ""                         # "tencent" | "deeplx" (empty = post-load 决定)
    tencent_translator_secret_id: str = ""
    tencent_translator_secret_key: str = ""
    tencent_translator_region: str = "ap-beijing"
    tencent_translator_project_id: int = 0
```

- [ ] **Step 5: Add fields to `update_settings` serialization**

Find the `data = {...}` block inside `update_settings`. Add the 5 new keys (place them right after `"deeplx_url": self.deeplx_url,`):

```python
                "current_translator": self.current_translator,
                "tencent_translator_secret_id": self.tencent_translator_secret_id,
                "tencent_translator_secret_key": self.tencent_translator_secret_key,
                "tencent_translator_region": self.tencent_translator_region,
                "tencent_translator_project_id": self.tencent_translator_project_id,
```

- [ ] **Step 6: Add fields to `load_from_disk` batch loop**

Find the existing field-batch loop (around line 236 — `for key in ("deeplx_url", ...)`). Extend the tuple with the 4 string fields:

```python
                for key in ("deeplx_url", "refine_base_url", "refine_api_key",
                            "refine_model", "refine_provider_preset",
                            "refine_meta_prompt_path",
                            "current_translator",
                            "tencent_translator_secret_id",
                            "tencent_translator_secret_key",
                            "tencent_translator_region"):
                    if key in data and isinstance(data[key], str):
                        setattr(cfg, key, data[key])
```

Then immediately after the loop, handle the int field separately:

```python
                if "tencent_translator_project_id" in data:
                    try:
                        cfg.tencent_translator_project_id = int(
                            data["tencent_translator_project_id"] or 0)
                    except (TypeError, ValueError):
                        cfg.tencent_translator_project_id = 0
```

- [ ] **Step 7: Add `.env` mapping**

Find `deeplx_url=env.get("DEEPLX_URL") or "",` in the `Config(...)` constructor inside `load_config`. Add directly below:

```python
        tencent_translator_secret_id=env.get("TENCENTCLOUD_SECRET_ID") or "",
        tencent_translator_secret_key=env.get("TENCENTCLOUD_SECRET_KEY") or "",
        tencent_translator_region=env.get("TENCENTCLOUD_REGION") or "ap-beijing",
```

- [ ] **Step 8: Add env writeback**

Find the existing `if cfg.deeplx_url: os.environ["DEEPLX_URL"] = cfg.deeplx_url` (around line 312). Append below it:

```python
    if cfg.current_translator:
        os.environ["_CURRENT_TRANSLATOR"] = cfg.current_translator
    if cfg.tencent_translator_secret_id:
        os.environ["TENCENTCLOUD_SECRET_ID"] = cfg.tencent_translator_secret_id
    if cfg.tencent_translator_secret_key:
        os.environ["TENCENTCLOUD_SECRET_KEY"] = cfg.tencent_translator_secret_key
    if cfg.tencent_translator_region:
        os.environ["TENCENTCLOUD_REGION"] = cfg.tencent_translator_region
```

- [ ] **Step 9: Add `_post_load_migrate` helper and call it**

At the bottom of `config.py` (after `load_config` definition), add:

```python
def _post_load_migrate(cfg) -> None:
    """旧用户升级兼容：若只配过 DeepLX 没配腾讯，沿用 DeepLX。"""
    if not cfg.current_translator:
        if cfg.deeplx_url and not cfg.tencent_translator_secret_id:
            cfg.current_translator = "deeplx"
        else:
            cfg.current_translator = "tencent"
```

Then call it inside `load_config` immediately before returning `cfg`. Search for the `return cfg` line at the end of `load_config`; add directly above:

```python
    _post_load_migrate(cfg)
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v -k 'tencent or post_load_migrate'`
Expected: All 4 new tests PASS.

Run also the full config test file to confirm no regression:
```bash
pytest tests/test_config.py -v
```
Expected: All cases pass.

- [ ] **Step 11: Commit**

```bash
git add drama_shot_master/config.py tests/test_config.py
git commit -m "feat(config): 加 tencent_translator_* 字段 + .env 覆盖 + 启发式迁移"
```

---

## Task 5: Rewrite translator.py as facade with LRU (TDD)

**Files:**
- Modify: `drama_shot_master/providers/translator.py` (full rewrite)
- Create: `tests/test_providers/test_translator_facade.py`
- Create: `tests/test_providers/test_translator_cache.py`
- Modify: `tests/test_providers/test_translator.py` (rewrite to 3 backward-compat sentinels)

**Dependencies:** Tasks 1, 2, 3, 4.

- [ ] **Step 1: Write failing facade tests**

Create `tests/test_providers/test_translator_facade.py`:

```python
"""Tests for translator.py facade: build_translation_provider + translate."""
from __future__ import annotations

import types
from unittest.mock import patch

import pytest

from drama_shot_master.providers.translation_base import (
    TranslationErrorCode, TranslationResult,
)


def _cfg(**kwargs):
    """Build a minimal cfg-like object."""
    defaults = dict(
        current_translator="",
        tencent_translator_secret_id="",
        tencent_translator_secret_key="",
        tencent_translator_region="ap-beijing",
        tencent_translator_project_id=0,
        deeplx_url="",
    )
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def test_build_returns_tencent_when_creds_present(stub_tmt_client):
    from drama_shot_master.providers.translator import build_translation_provider
    from drama_shot_master.providers.tencent_translator import TencentTranslator
    cfg = _cfg(current_translator="tencent",
               tencent_translator_secret_id="sid",
               tencent_translator_secret_key="skey")
    p = build_translation_provider(cfg)
    assert isinstance(p, TencentTranslator)


def test_build_returns_none_when_tencent_creds_missing():
    from drama_shot_master.providers.translator import build_translation_provider
    cfg = _cfg(current_translator="tencent",
               tencent_translator_secret_id="",
               tencent_translator_secret_key="")
    assert build_translation_provider(cfg) is None


def test_build_returns_deeplx_when_url_set():
    from drama_shot_master.providers.translator import build_translation_provider
    from drama_shot_master.providers.deeplx_translator import DeepLXTranslator
    cfg = _cfg(current_translator="deeplx",
               deeplx_url="http://example/translate")
    p = build_translation_provider(cfg)
    assert isinstance(p, DeepLXTranslator)


def test_build_returns_none_when_deeplx_url_missing():
    from drama_shot_master.providers.translator import build_translation_provider
    cfg = _cfg(current_translator="deeplx", deeplx_url="")
    assert build_translation_provider(cfg) is None


def test_build_returns_none_for_unknown_provider():
    from drama_shot_master.providers.translator import build_translation_provider
    cfg = _cfg(current_translator="bogus_xyz",
               tencent_translator_secret_id="x",
               tencent_translator_secret_key="y")
    assert build_translation_provider(cfg) is None


def test_build_uses_env_when_cfg_field_empty(monkeypatch, stub_tmt_client):
    from drama_shot_master.providers.translator import build_translation_provider
    from drama_shot_master.providers.tencent_translator import TencentTranslator
    monkeypatch.setenv("_CURRENT_TRANSLATOR", "tencent")
    monkeypatch.setenv("TENCENTCLOUD_SECRET_ID", "env-sid")
    monkeypatch.setenv("TENCENTCLOUD_SECRET_KEY", "env-skey")
    p = build_translation_provider(cfg=None)
    assert isinstance(p, TencentTranslator)


def test_translate_returns_fail_when_no_provider_configured():
    from drama_shot_master.providers.translator import translate
    cfg = _cfg()  # All empty
    r = translate("hello", "en", "zh", cfg=cfg)
    assert r.ok is False
    assert r.error.code == TranslationErrorCode.AUTH_FAILED
    assert "设置" in r.error.hint


def test_translate_en_to_zh_returns_str_on_success(stub_tmt_client):
    from drama_shot_master.providers.translator import (
        translate_en_to_zh, clear_cache,
    )
    clear_cache()
    stub_tmt_client.TextTranslate = lambda self, req: type("R", (), {
        "TargetText": "你好", "UsedAmount": 5})()
    import os
    os.environ["_CURRENT_TRANSLATOR"] = "tencent"
    os.environ["TENCENTCLOUD_SECRET_ID"] = "sid"
    os.environ["TENCENTCLOUD_SECRET_KEY"] = "skey"
    try:
        assert translate_en_to_zh("hello") == "你好"
    finally:
        os.environ.pop("_CURRENT_TRANSLATOR", None)
        os.environ.pop("TENCENTCLOUD_SECRET_ID", None)
        os.environ.pop("TENCENTCLOUD_SECRET_KEY", None)


def test_translate_en_to_zh_returns_none_when_no_provider(monkeypatch):
    from drama_shot_master.providers.translator import translate_en_to_zh
    monkeypatch.delenv("_CURRENT_TRANSLATOR", raising=False)
    monkeypatch.delenv("TENCENTCLOUD_SECRET_ID", raising=False)
    monkeypatch.delenv("TENCENTCLOUD_SECRET_KEY", raising=False)
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    assert translate_en_to_zh("hello") is None
```

- [ ] **Step 2: Write failing cache tests**

Create `tests/test_providers/test_translator_cache.py`:

```python
"""Tests for LRU cache in translator.py facade."""
from __future__ import annotations

import threading

import pytest

from drama_shot_master.providers.translation_base import (
    TranslationError, TranslationErrorCode, TranslationResult,
)
from drama_shot_master.providers.translator import (
    _cache_get, _cache_key, _cache_set, clear_cache, get_cache_stats,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


def test_cache_hit_returns_stored_value():
    key = _cache_key("tencent", "en", "zh", "hello")
    r = TranslationResult.success("你好", "tencent", 5)
    _cache_set(key, r)
    assert _cache_get(key) is r


def test_cache_miss_returns_none():
    key = _cache_key("tencent", "en", "zh", "never-set")
    assert _cache_get(key) is None


def test_different_provider_does_not_collide():
    k1 = _cache_key("tencent", "en", "zh", "hello")
    k2 = _cache_key("deeplx", "en", "zh", "hello")
    assert k1 != k2
    _cache_set(k1, TranslationResult.success("你好-tx", "tencent", 5))
    assert _cache_get(k2) is None


def test_lru_evicts_oldest_when_full():
    # 65 entries; first must be evicted (max=64).
    for i in range(65):
        key = _cache_key("tencent", "en", "zh", f"text-{i}")
        _cache_set(key, TranslationResult.success(f"r-{i}", "tencent", 1))
    stats = get_cache_stats()
    assert stats["size"] == 64
    # First key (i=0) should be gone
    first = _cache_key("tencent", "en", "zh", "text-0")
    assert _cache_get(first) is None
    # Last key (i=64) should still be present
    last = _cache_key("tencent", "en", "zh", "text-64")
    assert _cache_get(last) is not None


def test_clear_cache_removes_all():
    key = _cache_key("tencent", "en", "zh", "x")
    _cache_set(key, TranslationResult.success("y", "tencent", 1))
    clear_cache()
    assert _cache_get(key) is None
    assert get_cache_stats()["size"] == 0


def test_failed_results_must_not_be_cached_by_translate(stub_tmt_client):
    """translate() 自己只在 ok=True 时调 _cache_set。
    这里直接断言：cache_set 收到失败结果时不抛错（行为本身由 translate 主导）。
    """
    err = TranslationError(
        code=TranslationErrorCode.AUTH_FAILED,
        message="m", hint="h", retryable=False, provider="tencent")
    fail = TranslationResult.fail(err)
    key = _cache_key("tencent", "en", "zh", "hello")
    _cache_set(key, fail)  # 直接写入失败结果是允许的（API 不主动拒）
    assert _cache_get(key) is fail


def test_concurrent_set_and_get_does_not_crash():
    """简易并发：8 个线程做 get/set 不应抛锁/数据结构异常。"""
    def worker(i):
        for j in range(50):
            key = _cache_key("tencent", "en", "zh", f"t{i}-{j}")
            _cache_set(key, TranslationResult.success(
                f"r{i}-{j}", "tencent", 1))
            _cache_get(key)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
    assert get_cache_stats()["size"] <= 64
```

- [ ] **Step 3: Rewrite the legacy translator.py test as 3 backward-compat sentinels**

Replace the entire contents of `tests/test_providers/test_translator.py` with:

```python
"""Backward-compatibility sentinels for the legacy translate_en_to_zh(text) API.

This file used to host all DeepLX tests; those moved to test_deeplx_translator.py.
What's kept here proves the public no-arg signature still works as the rest of
the codebase expects.
"""
from __future__ import annotations

import os

import pytest

from drama_shot_master.providers.translator import (
    clear_cache, translate_en_to_zh,
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.delenv("_CURRENT_TRANSLATOR", raising=False)
    monkeypatch.delenv("TENCENTCLOUD_SECRET_ID", raising=False)
    monkeypatch.delenv("TENCENTCLOUD_SECRET_KEY", raising=False)
    monkeypatch.delenv("DEEPLX_URL", raising=False)
    clear_cache()
    yield
    clear_cache()


def test_empty_text_returns_none_without_provider():
    assert translate_en_to_zh("") is None
    assert translate_en_to_zh("   ") is None


def test_no_provider_configured_returns_none():
    assert translate_en_to_zh("hello") is None


def test_signature_is_str_to_optional_str():
    """Type stability check: signature shape preserved for legacy callers."""
    import inspect
    sig = inspect.signature(translate_en_to_zh)
    params = list(sig.parameters)
    assert params == ["text"]
```

- [ ] **Step 4: Run tests to verify they all fail**

Run:
```bash
pytest tests/test_providers/test_translator_facade.py \
       tests/test_providers/test_translator_cache.py \
       tests/test_providers/test_translator.py -v
```
Expected: All tests fail. The cache tests fail with `ImportError: cannot import name '_cache_key'`; the facade tests fail with stale function signatures.

- [ ] **Step 5: Rewrite `translator.py`**

Fully replace `drama_shot_master/providers/translator.py` with:

```python
"""翻译 facade：保留旧 translate_en_to_zh 签名；暴露新 translate / factory / 缓存控制。

配置来源：调用方传 cfg 则用 cfg 字段；不传则全走 os.environ。
config.py 启动时与 settings UI save_to() 都把字段同步到 os.environ，
让旧 translate_en_to_zh(text) 无参签名仍能找到当前 provider。

进程内 LRU(64) 缓存按 (provider_name, source, target, sha256(text)[:16]) 去重；
只缓存 ok=True 的结果，失败不进缓存。
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from collections import OrderedDict

from drama_shot_master.providers.translation_base import (
    TranslationError, TranslationErrorCode, TranslationProvider,
    TranslationResult,
)

log = logging.getLogger(__name__)


# ── Public API ──────────────────────────────────────────────────────────────

def translate_en_to_zh(text: str) -> str | None:
    """旧签名保留；委派到当前 provider，失败返回 None。

    cfg 由 os.environ 隐式提供（config.py 启动时回写）。
    新代码应改用 translate(text, source, target, cfg=...) 拿 TranslationResult。
    """
    result = translate(text, source="en", target="zh")
    return result.text if result.ok else None


def translate(text: str, source: str = "auto",
              target: str = "zh", cfg=None) -> TranslationResult:
    """统一翻译入口；走 LRU 缓存。

    cfg=None 时全从 os.environ 取（_CURRENT_TRANSLATOR / TENCENTCLOUD_*）。
    """
    provider = build_translation_provider(cfg)
    if provider is None:
        return TranslationResult.fail(TranslationError(
            code=TranslationErrorCode.AUTH_FAILED,
            message="no provider configured",
            hint="还没配翻译服务，去设置 → 翻译 选 provider 并填凭证",
            retryable=False, provider="none"))
    key = _cache_key(provider.name, source, target, text)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    result = provider.translate(text, source, target)
    if result.ok:
        _cache_set(key, result)
    return result


# ── Factory ────────────────────────────────────────────────────────────────

def build_translation_provider(cfg=None) -> TranslationProvider | None:
    """据 cfg.current_translator 或 os.environ['_CURRENT_TRANSLATOR'] 构造 provider；
    凭证不全返回 None。"""
    def _get(field: str, env_key: str, default: str = "") -> str:
        if cfg is not None:
            val = getattr(cfg, field, "") or ""
            if val:
                return val
        return os.environ.get(env_key, default)

    name = _get("current_translator", "_CURRENT_TRANSLATOR", "tencent").lower()
    if name == "tencent":
        sid = _get("tencent_translator_secret_id", "TENCENTCLOUD_SECRET_ID")
        skey = _get("tencent_translator_secret_key", "TENCENTCLOUD_SECRET_KEY")
        region = _get("tencent_translator_region",
                       "TENCENTCLOUD_REGION", "ap-beijing")
        if not sid or not skey:
            return None
        from drama_shot_master.providers.tencent_translator \
            import TencentTranslator
        project_id = 0
        if cfg is not None:
            project_id = int(
                getattr(cfg, "tencent_translator_project_id", 0) or 0)
        return TencentTranslator(
            sid, skey, region=region, project_id=project_id)
    if name == "deeplx":
        url = _get("deeplx_url", "DEEPLX_URL")
        if not url:
            return None
        from drama_shot_master.providers.deeplx_translator \
            import DeepLXTranslator
        return DeepLXTranslator(url)
    log.warning("Unknown translator provider: %s", name)
    return None


# ── LRU (thread-safe) ──────────────────────────────────────────────────────

_LRU_MAX = 64
_lru: "OrderedDict[tuple, TranslationResult]" = OrderedDict()
_lru_lock = threading.Lock()


def _cache_key(provider_name: str, source: str, target: str,
               text: str) -> tuple:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return (provider_name, source, target, digest)


def _cache_get(key: tuple) -> TranslationResult | None:
    with _lru_lock:
        if key in _lru:
            _lru.move_to_end(key)
            return _lru[key]
    return None


def _cache_set(key: tuple, value: TranslationResult) -> None:
    with _lru_lock:
        _lru[key] = value
        _lru.move_to_end(key)
        while len(_lru) > _LRU_MAX:
            _lru.popitem(last=False)


def clear_cache() -> None:
    """provider 切换 / settings 改了凭证 时主动清。"""
    with _lru_lock:
        _lru.clear()


def get_cache_stats() -> dict:
    """调试 / 测试用。"""
    with _lru_lock:
        return {"size": len(_lru), "max": _LRU_MAX}
```

- [ ] **Step 6: Run all facade + cache + sentinel tests**

Run:
```bash
pytest tests/test_providers/test_translator_facade.py \
       tests/test_providers/test_translator_cache.py \
       tests/test_providers/test_translator.py -v
```
Expected: All tests PASS.

- [ ] **Step 7: Run the full providers test suite to catch regressions**

Run: `pytest tests/test_providers/ -v`
Expected: All translation_base / tencent / deeplx / facade / cache / sentinel tests pass.

- [ ] **Step 8: Commit**

```bash
git add drama_shot_master/providers/translator.py \
        tests/test_providers/test_translator_facade.py \
        tests/test_providers/test_translator_cache.py \
        tests/test_providers/test_translator.py
git commit -m "feat(providers): translator 重写为 facade + 进程内 LRU(64) + 9 facade 用例 + 7 缓存用例"
```

---

## Task 6: Settings UI — `translation_section.py` redesign (semi-TDD)

**Files:**
- Modify: `drama_shot_master/ui/widgets/settings_sections/translation_section.py`
- Test: `tests/test_ui/test_translation_section_smoke.py`

**Dependencies:** Tasks 4 (config fields), 5 (clear_cache available).

UI smoke tests verify end behavior (load / radio toggle / save) — too verbose to TDD per widget. We implement first then validate with offscreen smoke.

- [ ] **Step 1: Read existing section conventions for visual alignment**

Run:
```bash
grep -nE 'category|title|_tokens|current_theme|class .+Section' \
     drama_shot_master/ui/widgets/settings_sections/refine_section.py \
     drama_shot_master/ui/widgets/settings_sections/dub_section.py | head -30
```
Expected: Find the `class … Section(QWidget)` pattern with `title` / `category` class attrs and the standard `_build_ui` / `load_from` / `save_to` / `validate` / `cancel_workers` API.

- [ ] **Step 2: Rewrite the section**

Fully replace `drama_shot_master/ui/widgets/settings_sections/translation_section.py` with:

```python
"""TranslationSection: provider 分页（腾讯/DeepLX）+ 凭证编辑 + 测试连接。

风格对齐现有 refine_section / dub_section：QFormLayout + theme tokens 提示。
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from drama_shot_master.ui.theme import _tokens, current_theme


_REGIONS = [
    "ap-beijing", "ap-shanghai", "ap-guangzhou", "ap-chengdu",
    "ap-hongkong", "ap-singapore", "ap-tokyo", "ap-seoul",
    "ap-bangkok", "ap-mumbai", "na-siliconvalley", "na-ashburn",
    "eu-frankfurt",
]


class TranslationSection(QWidget):
    title = "翻译"
    category = "平台核心"

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._test_worker = None  # FunctionWorker handle to prevent GC
        self._build_ui()
        self.load_from(cfg)

    # ───────── UI ─────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Provider selector row
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("翻译服务："))
        self.rb_tencent = QRadioButton("腾讯云机器翻译（推荐）")
        self.rb_deeplx = QRadioButton("DeepLX (自部署)")
        self.provider_group = QButtonGroup(self)
        self.provider_group.addButton(self.rb_tencent, 0)
        self.provider_group.addButton(self.rb_deeplx, 1)
        sel_row.addWidget(self.rb_tencent)
        sel_row.addWidget(self.rb_deeplx)
        sel_row.addStretch(1)
        root.addLayout(sel_row)

        # Stack with two panes
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_tencent_pane())
        self.stack.addWidget(self._build_deeplx_pane())
        root.addWidget(self.stack)

        # Test connection row
        test_row = QHBoxLayout()
        self.btn_test = QPushButton("测试连接")
        self.btn_test.clicked.connect(self._on_test)
        self.lbl_test = QLabel("")
        self.lbl_test.setWordWrap(True)
        test_row.addWidget(self.btn_test)
        test_row.addWidget(self.lbl_test, 1)
        root.addLayout(test_row)
        root.addStretch(1)

        self.provider_group.idClicked.connect(self.stack.setCurrentIndex)

    def _build_tencent_pane(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.tc_sid = QLineEdit()
        self.tc_skey = QLineEdit()
        self.tc_skey.setEchoMode(QLineEdit.EchoMode.Password)
        self.tc_region = QComboBox()
        self.tc_region.addItems(_REGIONS)
        self.tc_pid = QSpinBox()
        self.tc_pid.setRange(0, 999999)
        f.addRow("SecretId", self.tc_sid)
        f.addRow("SecretKey", self.tc_skey)
        f.addRow("Region", self.tc_region)
        f.addRow("ProjectId", self.tc_pid)
        tip = QLabel(
            '去 <a href="https://console.cloud.tencent.com/cam/capi">'
            '腾讯云控制台</a> 创建访问密钥，免费 5 万字符/月。')
        tip.setOpenExternalLinks(True)
        tip.setWordWrap(True)
        self._style_muted(tip)
        f.addRow(tip)
        return w

    def _build_deeplx_pane(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.dl_url = QLineEdit()
        self.dl_url.setPlaceholderText(
            "https://api.deeplx.org/translate（或自部署 http://localhost:1188/translate）")
        f.addRow("DeepLX URL", self.dl_url)
        tip = QLabel("公共实例不稳定，建议自部署或切到腾讯云。")
        tip.setWordWrap(True)
        self._style_muted(tip)
        f.addRow(tip)
        return w

    def _style_muted(self, lbl: QLabel) -> None:
        try:
            t = _tokens(current_theme(self._cfg))
            lbl.setStyleSheet(f"color:{t['fg_muted']}")
        except Exception:
            pass

    # ───────── load / save / validate ─────────

    def load_from(self, cfg) -> None:
        provider = (getattr(cfg, "current_translator", "") or "tencent").lower()
        if provider == "deeplx":
            self.rb_deeplx.setChecked(True)
            self.stack.setCurrentIndex(1)
        else:
            self.rb_tencent.setChecked(True)
            self.stack.setCurrentIndex(0)
        self.tc_sid.setText(getattr(cfg, "tencent_translator_secret_id", "") or "")
        self.tc_skey.setText(getattr(cfg, "tencent_translator_secret_key", "") or "")
        region = getattr(cfg, "tencent_translator_region", "ap-beijing") \
            or "ap-beijing"
        idx = self.tc_region.findText(region)
        self.tc_region.setCurrentIndex(idx if idx >= 0 else 0)
        self.tc_pid.setValue(int(getattr(cfg, "tencent_translator_project_id", 0) or 0))
        self.dl_url.setText(getattr(cfg, "deeplx_url", "") or "")

    def save_to(self, cfg) -> None:
        provider = "tencent" if self.rb_tencent.isChecked() else "deeplx"
        cfg.update_settings(
            current_translator=provider,
            tencent_translator_secret_id=self.tc_sid.text().strip(),
            tencent_translator_secret_key=self.tc_skey.text().strip(),
            tencent_translator_region=self.tc_region.currentText(),
            tencent_translator_project_id=self.tc_pid.value(),
            deeplx_url=self.dl_url.text().strip(),
        )
        # 同步到 os.environ（让旧 translate_en_to_zh 立刻看到新值）
        os.environ["_CURRENT_TRANSLATOR"] = provider
        if cfg.tencent_translator_secret_id:
            os.environ["TENCENTCLOUD_SECRET_ID"] = cfg.tencent_translator_secret_id
        if cfg.tencent_translator_secret_key:
            os.environ["TENCENTCLOUD_SECRET_KEY"] = cfg.tencent_translator_secret_key
        if cfg.tencent_translator_region:
            os.environ["TENCENTCLOUD_REGION"] = cfg.tencent_translator_region
        if cfg.deeplx_url:
            os.environ["DEEPLX_URL"] = cfg.deeplx_url
        # 清缓存（provider/凭证 已变）
        from drama_shot_master.providers.translator import clear_cache
        clear_cache()

    def validate(self) -> tuple[bool, str]:
        if self.rb_tencent.isChecked():
            if not self.tc_sid.text().strip() or not self.tc_skey.text().strip():
                return False, "腾讯云需要填 SecretId 和 SecretKey"
        else:
            if not self.dl_url.text().strip():
                return False, "DeepLX 需要填 URL"
        return True, ""

    def cancel_workers(self) -> None:
        # FunctionWorker terminates when dialog closes; we just drop the handle.
        self._test_worker = None

    # ───────── test connection ─────────

    def _on_test(self) -> None:
        from drama_shot_master.providers.translator import translate
        from drama_shot_master.ui.worker import FunctionWorker
        # 先保存当前表单（用户点测试 = 同意落盘）
        self.save_to(self._cfg)
        self.lbl_test.setText("测试中…")
        self.lbl_test.setStyleSheet("")
        self.btn_test.setEnabled(False)
        worker = FunctionWorker(translate, "hello", "en", "zh", self._cfg)
        worker.finished_with_result.connect(self._on_test_done)
        worker.failed.connect(self._on_test_failed)
        worker.finished.connect(lambda: self.btn_test.setEnabled(True))
        self._test_worker = worker  # prevent GC
        worker.start()

    def _on_test_done(self, result) -> None:
        if result.ok:
            self.lbl_test.setText(f"✓ 通过：hello → {result.text}")
            self.lbl_test.setStyleSheet("color:#4ec98f")
        else:
            self.lbl_test.setText(f"✗ {result.error.hint}")
            self.lbl_test.setStyleSheet("color:#ff5c5c")
        self._test_worker = None

    def _on_test_failed(self, msg: str) -> None:
        self.lbl_test.setText(f"✗ {msg}")
        self.lbl_test.setStyleSheet("color:#ff5c5c")
        self._test_worker = None
```

- [ ] **Step 3: Write the UI smoke test**

Create `tests/test_ui/test_translation_section_smoke.py`:

```python
"""Offscreen smoke for TranslationSection (provider radio + stack + save/load)."""
from __future__ import annotations

import os
import types

import pytest
from PySide6.QtWidgets import QApplication

from drama_shot_master.ui.widgets.settings_sections.translation_section \
    import TranslationSection


@pytest.fixture(scope="module")
def app():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    a = QApplication.instance() or QApplication([])
    yield a


def _cfg(**kwargs):
    defaults = dict(
        current_translator="",
        tencent_translator_secret_id="",
        tencent_translator_secret_key="",
        tencent_translator_region="ap-beijing",
        tencent_translator_project_id=0,
        deeplx_url="",
        # update_settings spy
        _updates=[],
    )
    defaults.update(kwargs)
    ns = types.SimpleNamespace(**defaults)
    def _update(**fields):
        ns._updates.append(fields)
        for k, v in fields.items():
            setattr(ns, k, v)
    ns.update_settings = _update
    return ns


def test_default_loads_tencent_radio(app):
    cfg = _cfg()
    sec = TranslationSection(cfg)
    # _post_load_migrate not run here (using bare _cfg); empty current_translator
    # falls through to "tencent" in load_from's default branch.
    assert sec.rb_tencent.isChecked()
    assert sec.stack.currentIndex() == 0


def test_loads_deeplx_when_cfg_says_deeplx(app):
    cfg = _cfg(current_translator="deeplx",
               deeplx_url="http://example/translate")
    sec = TranslationSection(cfg)
    assert sec.rb_deeplx.isChecked()
    assert sec.stack.currentIndex() == 1
    assert sec.dl_url.text() == "http://example/translate"


def test_clicking_deeplx_switches_stack(app):
    cfg = _cfg(current_translator="tencent")
    sec = TranslationSection(cfg)
    sec.rb_deeplx.setChecked(True)
    assert sec.stack.currentIndex() == 1


def test_save_to_updates_cfg_and_clears_cache(app, monkeypatch):
    cleared = []
    monkeypatch.setattr(
        "drama_shot_master.providers.translator.clear_cache",
        lambda: cleared.append(True))
    cfg = _cfg(current_translator="tencent")
    sec = TranslationSection(cfg)
    sec.tc_sid.setText("new-sid")
    sec.tc_skey.setText("new-skey")
    sec.tc_region.setCurrentText("ap-shanghai")
    sec.tc_pid.setValue(7)
    sec.save_to(cfg)
    assert cfg.tencent_translator_secret_id == "new-sid"
    assert cfg.tencent_translator_secret_key == "new-skey"
    assert cfg.tencent_translator_region == "ap-shanghai"
    assert cfg.tencent_translator_project_id == 7
    assert cleared == [True]


def test_validate_tencent_missing_creds_fails(app):
    cfg = _cfg(current_translator="tencent")
    sec = TranslationSection(cfg)
    sec.tc_sid.setText("")
    sec.tc_skey.setText("")
    ok, msg = sec.validate()
    assert ok is False
    assert "Secret" in msg


def test_validate_deeplx_missing_url_fails(app):
    cfg = _cfg(current_translator="deeplx", deeplx_url="")
    sec = TranslationSection(cfg)
    sec.rb_deeplx.setChecked(True)
    sec.dl_url.setText("")
    ok, msg = sec.validate()
    assert ok is False
    assert "URL" in msg
```

- [ ] **Step 4: Run the smoke test**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/test_ui/test_translation_section_smoke.py -v`
Expected: All 6 cases PASS.

- [ ] **Step 5: Verify pre-existing settings dialog smoke still passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/test_ui/test_settings_sections_smoke.py tests/test_ui/test_unified_settings_dialog_smoke.py -v`
Expected: All existing UI smoke pass (the section was rewritten with same public API: `title` / `category` / `load_from` / `save_to` / `validate` / `cancel_workers`).

- [ ] **Step 6: Commit**

```bash
git add drama_shot_master/ui/widgets/settings_sections/translation_section.py \
        tests/test_ui/test_translation_section_smoke.py
git commit -m "feat(ui): translation_section 重做（provider 分页 + 测试连接 + 6 smoke 用例）"
```

---

## Task 7: P2 — `translate_button.py` upgrade to structured errors (semi-TDD)

**Files:**
- Modify: `drama_shot_master/ui/widgets/translate_button.py`
- Test: `tests/test_ui/test_translate_button_smoke.py`

**Dependencies:** Tasks 1, 5 (so `translate` returns `TranslationResult`).

- [ ] **Step 1: Rewrite `translate_button.py`**

Replace `drama_shot_master/ui/widgets/translate_button.py` with:

```python
"""可复用的"译"按钮 + 弹窗（升级到结构化错误）。

用法：
    attach_translate_button(self.prompt_edit, parent=self,
                            on_open_settings=lambda: …)

按钮在 text 为空时自动 disable；点击触发后台线程调
drama_shot_master.providers.translator.translate(text, "en", "zh")，
完成后弹一个非模态 QDialog。

成功：上半原文、下半译文 + 复制按钮。
失败：原文 + error.hint + 按 error.code 给的差异化按钮：
  - AUTH_FAILED → 去设置
  - QUOTA_EXHAUSTED / SERVICE_DISABLED → 打开腾讯控制台
  - RATE_LIMITED → 重试（5s 倒计时后启用）
  - retryable=True → 重试（即时）
  - 其它 → 仅关闭
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QToolButton,
    QVBoxLayout, QWidget,
)

from drama_shot_master.providers.translation_base import (
    TranslationErrorCode, TranslationResult,
)
from drama_shot_master.providers.translator import translate
from drama_shot_master.ui.worker import FunctionWorker

_TENCENT_CONSOLE = "https://console.cloud.tencent.com/tmt"


class _TranslateDialog(QDialog):
    """非模态弹窗：原文 + 译文/错误 + 按 error.code 分发按钮。"""

    def __init__(self, source: str, result: TranslationResult,
                 parent: Optional[QWidget] = None,
                 on_retry: Optional[Callable[[], None]] = None,
                 on_open_settings: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.setWindowTitle("Prompt 中译预览")
        self.setMinimumSize(420, 320)
        self.setWindowFlag(Qt.WindowType.Window, True)

        root = QVBoxLayout(self)
        root.setSpacing(6)

        root.addWidget(QLabel("原文"))
        src_edit = QPlainTextEdit(source)
        src_edit.setReadOnly(True)
        root.addWidget(src_edit, 1)

        if result.ok:
            root.addWidget(QLabel(
                f"中译 · {result.provider} · {result.used_chars} 字符"))
            dst = QPlainTextEdit(result.text or "")
            dst.setReadOnly(True)
            root.addWidget(dst, 1)
            root.addLayout(self._build_success_buttons(result.text or ""))
        else:
            err = result.error
            assert err is not None
            root.addWidget(QLabel(f"失败 · {err.provider} · {err.code}"))
            dst = QPlainTextEdit(f"{err.hint}\n\n详情：{err.message}")
            dst.setReadOnly(True)
            root.addWidget(dst, 1)
            root.addLayout(self._build_error_buttons(
                err, on_retry, on_open_settings))

    def _build_success_buttons(self, translated: str) -> QHBoxLayout:
        row = QHBoxLayout()
        copy_btn = QPushButton("复制译文")
        copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(translated))
        row.addWidget(copy_btn)
        row.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        row.addWidget(close_btn)
        return row

    def _build_error_buttons(self, err, on_retry, on_open_settings):
        row = QHBoxLayout()
        # Differentiated action button (by code)
        if (err.code == TranslationErrorCode.AUTH_FAILED
                and on_open_settings is not None):
            btn = QPushButton("去设置")
            btn.clicked.connect(lambda: (self.close(), on_open_settings()))
            row.addWidget(btn)
        elif err.code in (TranslationErrorCode.QUOTA_EXHAUSTED,
                          TranslationErrorCode.SERVICE_DISABLED):
            btn = QPushButton("打开腾讯控制台")
            btn.clicked.connect(self._open_tencent_console)
            row.addWidget(btn)

        # Retry button (if retryable + callback provided)
        if err.retryable and on_retry is not None:
            self._retry_btn = QPushButton("重试")
            self._retry_btn.clicked.connect(
                lambda: (self.close(), on_retry()))
            if err.code == TranslationErrorCode.RATE_LIMITED:
                self._start_countdown(self._retry_btn, 5)
            row.addWidget(self._retry_btn)

        row.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        row.addWidget(close_btn)
        return row

    def _start_countdown(self, btn: QPushButton, seconds: int) -> None:
        """RATE_LIMITED 时给重试按钮 N 秒 disable 倒计时。"""
        self._countdown_remaining = int(seconds)
        original_text = btn.text()
        btn.setEnabled(False)
        btn.setText(f"{original_text} ({self._countdown_remaining}s)")
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        def _tick():
            self._countdown_remaining -= 1
            if self._countdown_remaining <= 0:
                btn.setEnabled(True)
                btn.setText(original_text)
                self._countdown_timer.stop()
            else:
                btn.setText(f"{original_text} ({self._countdown_remaining}s)")
        self._countdown_timer.timeout.connect(_tick)
        self._countdown_timer.start()

    @staticmethod
    def _open_tencent_console() -> None:
        QDesktopServices.openUrl(QUrl(_TENCENT_CONSOLE))


class _TranslateController(QObject):
    """承接 FunctionWorker 信号 → 弹 _TranslateDialog（始终在 GUI 线程）。"""

    def __init__(self, btn: QToolButton, text_widget: QPlainTextEdit,
                 parent: QWidget,
                 on_open_settings: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self._btn = btn
        self._text_widget = text_widget
        self._parent_widget = parent
        self._on_open_settings = on_open_settings
        self._worker: Optional[FunctionWorker] = None
        self._source_text: str = ""

        text_widget.textChanged.connect(self._sync_enabled)
        btn.clicked.connect(self._on_clicked)
        self._sync_enabled()

    def _sync_enabled(self) -> None:
        running = self._worker is not None
        text = self._text_widget.toPlainText().strip()
        self._btn.setEnabled(bool(text) and not running)

    def _on_clicked(self) -> None:
        if self._worker is not None:
            return
        text = self._text_widget.toPlainText()
        if not text.strip():
            return
        self._source_text = text

        worker = FunctionWorker(translate, text, "en", "zh")
        worker.finished_with_result.connect(self._on_result)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._on_thread_done)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        self._sync_enabled()
        worker.start()

    def _on_result(self, result) -> None:
        # Always TranslationResult now (success or fail)
        self._show_dialog(result if isinstance(result, TranslationResult)
                          else self._synthetic_fail("unexpected result"))

    def _on_worker_failed(self, msg: str) -> None:
        self._show_dialog(self._synthetic_fail(msg))

    def _synthetic_fail(self, msg: str) -> TranslationResult:
        from drama_shot_master.providers.translation_base import (
            TranslationError,
        )
        return TranslationResult.fail(TranslationError(
            code=TranslationErrorCode.UNKNOWN,
            message=msg,
            hint="后台任务异常，重试或重启软件",
            retryable=True, provider="none"))

    def _show_dialog(self, result: TranslationResult) -> None:
        dlg = _TranslateDialog(
            self._source_text, result,
            parent=self._parent_widget,
            on_retry=self._on_clicked,
            on_open_settings=self._on_open_settings)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dlg.show()

    def _on_thread_done(self) -> None:
        self._worker = None
        self._sync_enabled()


def attach_translate_button(
        text_widget: QPlainTextEdit, parent: QWidget,
        on_open_settings: Optional[Callable[[], None]] = None
) -> QToolButton:
    """创建一个"译"按钮，挂到 parent，但与 text_widget 联动。

    on_open_settings：被点击"去设置"时调（用于路由打开设置对话框 + 滚到翻译 section）；
    传 None 则弹窗不显示该按钮（柔性降级）。
    """
    btn = QToolButton(parent)
    btn.setText("译")
    btn.setToolTip("翻译当前 prompt 为中文")
    btn.setFixedSize(28, 22)
    _TranslateController(btn, text_widget, parent, on_open_settings)
    return btn
```

- [ ] **Step 2: Write the UI smoke test**

Create `tests/test_ui/test_translate_button_smoke.py`:

```python
"""Offscreen smoke for translate button + _TranslateDialog."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QWidget

from drama_shot_master.providers.translation_base import (
    TranslationError, TranslationErrorCode, TranslationResult,
)
from drama_shot_master.ui.widgets.translate_button import (
    _TranslateDialog, attach_translate_button,
)


@pytest.fixture(scope="module")
def app():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    a = QApplication.instance() or QApplication([])
    yield a


def _fail(code, retryable=False, hint="hint", provider="tencent",
          message="m"):
    return TranslationResult.fail(TranslationError(
        code=code, message=message, hint=hint, retryable=retryable,
        provider=provider))


def test_button_disabled_when_text_empty(app):
    parent = QWidget()
    edit = QPlainTextEdit(parent)
    btn = attach_translate_button(edit, parent)
    assert btn.isEnabled() is False


def test_button_enabled_when_text_present(app):
    parent = QWidget()
    edit = QPlainTextEdit(parent)
    btn = attach_translate_button(edit, parent)
    edit.setPlainText("hello")
    assert btn.isEnabled() is True


def test_success_dialog_has_copy_button(app):
    result = TranslationResult.success("你好", "tencent", 5)
    dlg = _TranslateDialog("hello", result, parent=None)
    btn_texts = _all_button_texts(dlg)
    assert "复制译文" in btn_texts
    assert "关闭" in btn_texts


def test_auth_failed_dialog_offers_settings_button_when_callback_provided(app):
    called = []
    dlg = _TranslateDialog(
        "hello",
        _fail(TranslationErrorCode.AUTH_FAILED),
        parent=None,
        on_open_settings=lambda: called.append(True))
    assert "去设置" in _all_button_texts(dlg)


def test_auth_failed_no_settings_button_when_callback_missing(app):
    dlg = _TranslateDialog(
        "hello",
        _fail(TranslationErrorCode.AUTH_FAILED),
        parent=None, on_open_settings=None)
    assert "去设置" not in _all_button_texts(dlg)


def test_quota_exhausted_offers_console_button(app):
    dlg = _TranslateDialog(
        "hello",
        _fail(TranslationErrorCode.QUOTA_EXHAUSTED),
        parent=None)
    assert "打开腾讯控制台" in _all_button_texts(dlg)


def test_rate_limited_retry_button_starts_disabled(app):
    from PySide6.QtWidgets import QPushButton
    dlg = _TranslateDialog(
        "hello",
        _fail(TranslationErrorCode.RATE_LIMITED, retryable=True),
        parent=None, on_retry=lambda: None)
    retry_btn = next(
        (b for b in dlg.findChildren(QPushButton) if "重试" in b.text()), None)
    assert retry_btn is not None
    assert retry_btn.isEnabled() is False
    # Countdown text: "重试 (5s)" initially; (4s) acceptable if first tick fired
    assert "(5s)" in retry_btn.text() or "(4s)" in retry_btn.text()


def test_network_retryable_shows_immediate_retry(app):
    dlg = _TranslateDialog(
        "hello",
        _fail(TranslationErrorCode.NETWORK, retryable=True),
        parent=None, on_retry=lambda: None)
    from PySide6.QtWidgets import QPushButton
    retry_btn = next(
        (b for b in dlg.findChildren(QPushButton) if "重试" in b.text()), None)
    assert retry_btn is not None
    assert retry_btn.isEnabled() is True


def _all_button_texts(dlg):
    from PySide6.QtWidgets import QPushButton
    return [b.text() for b in dlg.findChildren(QPushButton)]
```

- [ ] **Step 3: Run the smoke test**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/test_ui/test_translate_button_smoke.py -v`
Expected: All 8 cases PASS.

- [ ] **Step 4: Verify legacy callers of `attach_translate_button` still work**

Run:
```bash
grep -rn 'attach_translate_button' drama_shot_master/ tests/ | grep -v __pycache__
```
Expected: All call sites use the 2-arg form `attach_translate_button(text_widget, parent)` — the new 3rd `on_open_settings` param is optional (default None), so they keep working.

- [ ] **Step 5: Commit**

```bash
git add drama_shot_master/ui/widgets/translate_button.py \
        tests/test_ui/test_translate_button_smoke.py
git commit -m "feat(ui): translate_button 升级到结构化错误（按 code 差异化按钮 + 5s 倒计时）"
```

---

## Task 8: Manual real-API smoke (non-TDD)

**Files:**
- Create: `tests/manual/__init__.py` (empty)
- Create: `tests/manual/test_tencent_real.py`
- Modify: `pyproject.toml` (register pytest marker)

**Dependencies:** Task 2 (TencentTranslator).

- [ ] **Step 1: Register the pytest marker**

Edit `pyproject.toml`. Find `[tool.pytest.ini_options]` (or `[pytest]` if older); under `markers = [...]`, add:

```toml
"requires_tencent_creds: needs TENCENTCLOUD_SECRET_ID/SECRET_KEY env vars to run real API",
```

If no marker section exists, add the whole block at the end of the file:

```toml
[tool.pytest.ini_options]
markers = [
    "requires_tencent_creds: needs TENCENTCLOUD_SECRET_ID/SECRET_KEY env vars to run real API",
]
```

- [ ] **Step 2: Create manual test package marker**

Create `tests/manual/__init__.py` with single line:

```python
"""Manual / opt-in tests not run in CI."""
```

- [ ] **Step 3: Write the manual test**

Create `tests/manual/test_tencent_real.py`:

```python
"""Opt-in real-API smoke for TencentTranslator.

Run:
    TENCENTCLOUD_SECRET_ID=… TENCENTCLOUD_SECRET_KEY=… \\
        pytest -m requires_tencent_creds tests/manual/test_tencent_real.py -v

CI does NOT run this (avoids charges and credential leakage).
"""
from __future__ import annotations

import os

import pytest

from drama_shot_master.providers.tencent_translator import TencentTranslator


@pytest.mark.requires_tencent_creds
def test_real_tencent_translate_en_to_zh():
    sid = os.environ.get("TENCENTCLOUD_SECRET_ID", "")
    skey = os.environ.get("TENCENTCLOUD_SECRET_KEY", "")
    region = os.environ.get("TENCENTCLOUD_REGION", "ap-beijing")
    if not sid or not skey:
        pytest.skip("无腾讯凭证（TENCENTCLOUD_SECRET_ID/SECRET_KEY 未设）")
    t = TencentTranslator(sid, skey, region=region)
    r = t.translate("hello world", "en", "zh")
    assert r.ok is True, f"failed: {r.error}"
    assert r.text  # non-empty
    assert r.used_chars > 0
    print(f"\nTranslated: {r.text!r}, used {r.used_chars} chars, region={region}")
```

- [ ] **Step 4: Verify the marker filters correctly without creds**

Run: `pytest tests/manual/test_tencent_real.py -v`
Expected: Test runs but skips with message "无腾讯凭证".

- [ ] **Step 5: Verify CI exclude works**

Run: `pytest tests/manual/test_tencent_real.py -v -m "not requires_tencent_creds"`
Expected: 1 deselected, 0 selected.

- [ ] **Step 6: Commit**

```bash
git add tests/manual/__init__.py tests/manual/test_tencent_real.py pyproject.toml
git commit -m "test(providers): 加 requires_tencent_creds 标记的手动真 API smoke（CI 不跑）"
```

---

## Final Verification

After all tasks complete, run the full regression suite.

- [ ] **Step 1: Run all provider tests**

Run: `pytest tests/test_providers/ -v`
Expected: ~55 passing (translation_base + tencent + deeplx + facade + cache + sentinel).

- [ ] **Step 2: Run all UI smoke**

Run:
```bash
QT_QPA_PLATFORM=offscreen pytest tests/test_ui/test_translation_section_smoke.py tests/test_ui/test_translate_button_smoke.py tests/test_ui/test_settings_sections_smoke.py tests/test_ui/test_unified_settings_dialog_smoke.py -v
```
Expected: All pass.

- [ ] **Step 3: Run config tests**

Run: `pytest tests/test_config.py -v`
Expected: All pass (existing + 4 new tencent cases).

- [ ] **Step 4: Run the manual smoke skip path**

Run: `pytest tests/manual/test_tencent_real.py -v`
Expected: Skipped with credential message.

- [ ] **Step 5: Smoke-launch the app to verify nothing is wired wrong**

Run: `python -c "from drama_shot_master.config import load_config; cfg = load_config(); print(cfg.current_translator)"`
Expected: Prints `tencent` (default for empty settings).

Run also: `python -c "from drama_shot_master.providers.translator import build_translation_provider; print(build_translation_provider(None))"`
Expected: Prints `None` (no creds in env / cfg).

- [ ] **Step 6: Update README / CHANGELOG (optional, low-risk doc commit)**

Append the migration doc snippet from spec §7.4 to the project's CHANGELOG.md (or README's release notes section). Skip if such file isn't conventional in this repo.

- [ ] **Step 7: Final consolidation commit (if any doc / changelog changed)**

```bash
git add CHANGELOG.md   # or README.md
git commit -m "docs: 腾讯翻译 provider 升级说明（CHANGELOG）"
```

---

## Done criteria

- All ~75 automated tests pass on Linux + Windows
- Manual `requires_tencent_creds` test passes locally with real keys
- `drama_shot_master/providers/translator.py` legacy `translate_en_to_zh(text) -> str | None` signature preserved
- `translation_section.py` UI shows provider radio + Tencent/DeepLX panes + working "测试连接"
- Old DeepLX users get auto-fallback (`_post_load_migrate` keeps them on DeepLX)
- New users get Tencent as default and clear error messages on missing creds
