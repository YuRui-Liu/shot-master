# 腾讯云翻译 Provider · 设计稿

**日期**：2026-05-28
**代号**：`tencent_translator`
**版本**：v0.1.0 (设计稿)
**状态**：待用户复审

---

## 0. 摘要

引入腾讯云机器翻译（TMT）作为默认翻译后端，逐步替代当前 DeepLX 本地部署方案。
方案的核心是抽出 `TranslationProvider` ABC，把现有"模块函数 + 单一 DeepLX"重构为"抽象层 + Tencent + DeepLX 双实现 + 用户可切换"。
DeepLX 路径完整保留（自部署 / 离线场景），凭证存 `settings.json`，环境变量可覆盖。
翻译失败走结构化错误（`TranslationError`，含语义化 code + 中文 hint + retryable 标志），UI 据 code 给差异化操作（去设置 / 打开腾讯控制台 / 重试 / 关闭）。
进程内 LRU(64) 缓存防止重复点"译预览"按钮浪费 quota。

---

## 1. 背景与约束

### 1.1 现有 translator 集成点

```
drama_shot_master/providers/translator.py
  └─ translate_en_to_zh(text) -> str | None     # 单一模块函数
     · 读 os.environ["DEEPLX_URL"]
     · POST JSON 到 DeepLX
     · 任何失败返回 None（silent）

drama_shot_master/config.py
  └─ deeplx_url: str = ""                       # 单字段

drama_shot_master/ui/widgets/settings_sections/translation_section.py
  └─ 单 QLineEdit "DeepLX URL"

drama_shot_master/ui/widgets/translate_button.py
  └─ "译"按钮 + 非模态译文弹窗
  └─ 失败时硬编码显示 DEEPLX_URL 字符串

tests/test_providers/test_translator.py
  └─ 7 个 mock urlopen 用例
```

**问题**：DeepLX 需要用户**自部署**或依赖公共实例（不稳定/常宕）。零基础视频创作者难以搭。

### 1.2 腾讯云 TMT API 调研结论

来源：[API 总览](https://cloud.tencent.com/document/product/551/15612) · [TextTranslate 接口](https://cloud.tencent.com/document/api/551/15619) · [tencentcloud-sdk-python-tmt PyPI](https://pypi.org/project/tencentcloud-sdk-python-tmt/) · [SDK GitHub](https://github.com/TencentCloud/tencentcloud-sdk-python) · [入门教程](https://cloud.tencent.com/developer/article/1623177)

| 维度 | 数据 |
|---|---|
| Endpoint | `tmt.tencentcloudapi.com` |
| Action | `TextTranslate`，Version `2018-03-21` |
| 鉴权 | TC3-HMAC-SHA256 v3 签名（用官方 SDK 处理） |
| 必填参数 | `SourceText` (≤6000 UTF-8 字节) / `Source` / `Target` / `ProjectId` (默认 0) |
| 返回 | `TargetText` / `Source` / `Target` / `UsedAmount` / `RequestId` |
| QPS 限频 | 5 req/s（API + region + 子账号 维度） |
| 支持语言 | auto / zh / zh-TW / en / ja / ko / fr / es / it / de / tr / ru / pt / vi / id / th / ms / ar / hi |
| Region | ap-beijing / ap-shanghai / ap-guangzhou / ap-chengdu / ap-hongkong / ap-singapore / ap-tokyo / ap-seoul / 等 |
| 计费 | 5 万字符/月免费，超出约 0.058 元/千字符 |
| Python SDK | `tencentcloud-sdk-python-tmt` (Apache-2.0, ~120KB wheel) |

### 1.3 4 项关键决策（已与用户确认）

| 决策点 | 选择 |
|---|---|
| Tencent vs DeepLX 关系 | 腾讯默认 + DeepLX 可选（用户在 settings 切换） |
| 凭证存储 | `settings.json` 明文 + `.env` 环境变量可覆盖（与 `refine_api_key` 一致） |
| 失败 UX | 结构化错误（code + 中文 hint + retryable），UI 据 code 给差异化按钮 |
| 缓存 | 进程内 LRU(maxsize=64)，按 (provider, src, tgt, text-hash) 去重 |

### 1.4 硬性约束

- **不引入 GPL 依赖**（`feedback_no_gpl_deps`）：tencentcloud-sdk-python-tmt 是 Apache-2.0 ✓
- **保留旧 `translate_en_to_zh(text) -> str | None` 签名**（向后兼容现有 translate_button 等调用方）
- **DeepLX 路径不删**：自部署 / 离线场景仍可用
- **凭证不进 git**：settings.json 已在 .gitignore 中（既有约定）

---

## 2. 架构总览

```
┌────────────────────────────────────────────────────────────────┐
│  调用方                                                          │
│  · UI 翻译按钮 (translate_button.py)                            │
│  · 未来：批量字幕翻译 / 项目导出翻译 / ...                          │
└────────────────────────────────────────────────────────────────┘
                          │
                          ▼  translate_en_to_zh(text)  OR  translate(text, src, tgt)
┌────────────────────────────────────────────────────────────────┐
│  drama_shot_master/providers/translator.py (重写为 facade)      │
│                                                                  │
│  · translate_en_to_zh(text) ── 保留旧签名（委派 + 提取 .text）     │
│  · translate(text, source, target) -> TranslationResult         │
│  · build_translation_provider(cfg) -> TranslationProvider|None  │
│  · 进程内 LRU(64)，key=(provider, src, tgt, sha256(text)[:16])  │
│  · clear_cache() / get_cache_stats()                            │
└────────────────────────────────────────────────────────────────┘
                          │
                          ▼ provider.translate(...)
┌────────────────────────────────────────────────────────────────┐
│  drama_shot_master/providers/translation_base.py (新增)         │
│                                                                  │
│  class TranslationProvider(ABC):                                │
│      name: ClassVar[str]                                        │
│      def translate(text, source, target) -> TranslationResult   │
│      def health_check() -> tuple[bool, str]                     │
│                                                                  │
│  @dataclass(frozen=True) TranslationResult: ok/text/error/...   │
│  @dataclass(frozen=True) TranslationError:  code/message/hint/  │
│                                              retryable/provider  │
│                                                                  │
│  class TranslationErrorCode: AUTH_FAILED / QUOTA_EXHAUSTED /     │
│      RATE_LIMITED / INVALID_INPUT / LANGUAGE_UNSUPPORTED /       │
│      NETWORK / SERVICE_DISABLED / UNKNOWN                        │
└────────────────────────────────────────────────────────────────┘
            │                                          │
            ▼                                          ▼
┌──────────────────────────────────┐  ┌───────────────────────────────┐
│  tencent_translator.py (新增)    │  │  deeplx_translator.py (新增)  │
│                                  │  │  （从现 translator.py 拆出）   │
│  · 用 tencentcloud-sdk-python-tmt│  │  · urllib.request POST JSON   │
│  · TC3-HMAC-SHA256 由 SDK 处理   │  │  · 错误映射到 TranslationError │
│  · 读 cfg.tencent_translator_*   │  │  · 读 cfg.deeplx_url           │
│  · _map_tencent_error(e) → code  │  │  · _map_http_status(code) → … │
└──────────────────────────────────┘  └───────────────────────────────┘
```

### 2.1 关键设计点

| 维度 | 选择 | 理由 |
|---|---|---|
| 抽象风格 | ABC + dataclass | 对齐既有 `VisionProvider` 模式（`providers/base.py`） |
| 默认 provider | Tencent | 云端开箱，无需用户搭部署 |
| Tencent 签名 | 官方 SDK | TC3-HMAC-SHA256 v3 自己写约 50 行 crypto，易出 bug；SDK Apache-2.0 |
| 旧 API 兼容 | `translate_en_to_zh(text)` 保留 | 不破坏 translate_button 等调用方 |
| 包结构 | 平铺 3 个新文件到 `providers/` | 与 `openai_compat.py` / `gemini.py` 等并列；不新建子目录 |
| 缓存 | 进程内 LRU(64) 手写 OrderedDict | 失败结果不进缓存（`functools.lru_cache` 做不到） |
| 凭证字段 | `tencent_translator_*` 前缀 | 与 `refine_*` / `runninghub_*` 命名风格一致 |

### 2.2 文件变更清单

**新增**：

| 文件 | 行数估计 | 说明 |
|---|---|---|
| `drama_shot_master/providers/translation_base.py` | ~80 | ABC + dataclass + error code 常量 |
| `drama_shot_master/providers/tencent_translator.py` | ~120 | Tencent 实现 + 错误映射 |
| `drama_shot_master/providers/deeplx_translator.py` | ~60 | DeepLX 实现（从现 translator.py 切过来） |
| `tests/test_providers/test_translation_base.py` | ~60 | ABC 行为测试 |
| `tests/test_providers/test_tencent_translator.py` | ~180 | mock SDK，12 用例 |
| `tests/test_providers/test_deeplx_translator.py` | ~120 | mock urlopen，10 用例（从旧 test_translator.py 改写） |
| `tests/test_providers/test_translator_facade.py` | ~100 | factory + 委派 |
| `tests/test_providers/test_translator_cache.py` | ~80 | LRU 行为 |
| `tests/test_ui/test_translation_section_smoke.py` | ~80 | section 分页 + save/load |
| `tests/test_ui/test_translate_button_smoke.py` | ~100 | 弹窗 + 差异化按钮 |
| `tests/manual/test_tencent_real.py` | ~30 | opt-in 真 API smoke |

**改动**：

| 文件 | 改动 |
|---|---|
| `drama_shot_master/providers/translator.py` | 重写为 facade：`translate_en_to_zh` + `translate` + factory + LRU |
| `drama_shot_master/config.py` | 加 5 个字段：`current_translator`/`tencent_translator_secret_id`/`_secret_key`/`_region`/`_project_id`；序列化 + 加载 + .env 覆盖 + `_post_load_migrate` 启发式补全 |
| `drama_shot_master/ui/widgets/settings_sections/translation_section.py` | 重做为 provider 分页布局（radio + QStackedWidget + 测试连接） |
| `drama_shot_master/ui/widgets/translate_button.py` | `_TranslateDialog` 接收 `TranslationResult`；按 error.code 显示差异化按钮 |
| `pyproject.toml` | 加 `tencentcloud-sdk-python-tmt>=3.0.1207,<4.0.0` |
| `tests/test_providers/test_translator.py` | 改写为 3 个"旧 API 向后兼容"门禁用例 |
| `tests/test_config.py` | 追加 4 个新字段 + .env + migrate 用例 |

**保持不变**：

- `translate_button.py` 调用 `translate_en_to_zh(text)` 的旧签名（P1 阶段；P2 升级到结构化错误）

### 2.3 不在范围（YAGNI）

- 不做 batch translation（`TextTranslateBatch` 接口） —— 单 prompt 翻译场景
- 不做语言自动检测 UI —— 现用例只 en→zh
- 不做落盘缓存 —— 进程内 LRU 够
- 不做"翻译失败自动切到另一 provider 重试" —— 失败明示，用户手动切
- 不做 i18n 提示文案 —— `TranslationError.hint` 硬中文；锚点已留
- 不做计费/quota dashboard —— 翻译弹窗显示 `used_chars` 即可

---

## 3. TranslationProvider ABC + 两个实现

### 3.1 `translation_base.py`

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar


class TranslationErrorCode:
    """错误码常量。SCREAMING_SNAKE_CASE 便于 UI/日志匹配。"""
    AUTH_FAILED          = "AUTH_FAILED"          # 凭证/签名错
    QUOTA_EXHAUSTED      = "QUOTA_EXHAUSTED"      # 余额/免费额度耗尽
    SERVICE_DISABLED     = "SERVICE_DISABLED"     # 未开通服务
    RATE_LIMITED         = "RATE_LIMITED"         # QPS 触顶
    INVALID_INPUT        = "INVALID_INPUT"        # 空文本 / 超长 / 非法参数
    LANGUAGE_UNSUPPORTED = "LANGUAGE_UNSUPPORTED" # 该 provider 不支持该 src/tgt
    NETWORK              = "NETWORK"              # 连接失败 / 超时
    UNKNOWN              = "UNKNOWN"              # 兜底


@dataclass(frozen=True)
class TranslationError:
    code: str                # TranslationErrorCode.*
    message: str             # provider 原始 message（英文为主，便于 grep 日志）
    hint: str                # 中文用户人话
    retryable: bool          # 是否值得"重试"
    provider: str            # "tencent" / "deeplx"


@dataclass(frozen=True)
class TranslationResult:
    ok: bool
    text: str | None         # ok=True 时是译文
    error: TranslationError | None  # ok=False 时非空
    provider: str
    used_chars: int = 0      # 腾讯返回 UsedAmount；DeepLX 取 len(text)

    @classmethod
    def success(cls, text: str, provider: str, used_chars: int = 0):
        return cls(ok=True, text=text, error=None, provider=provider,
                   used_chars=used_chars)

    @classmethod
    def fail(cls, error: TranslationError):
        return cls(ok=False, text=None, error=error,
                   provider=error.provider, used_chars=0)


class TranslationProvider(ABC):
    """所有翻译 provider 的统一契约。"""
    name: ClassVar[str]  # 子类必须覆盖，"tencent" / "deeplx"

    @abstractmethod
    def translate(self, text: str, source: str = "auto",
                  target: str = "zh") -> TranslationResult:
        """翻译一段文本。

        语言代码用小写 ISO-639-1 + "auto"；实现负责映射到自家代码体系。
        任何异常都不应抛出 —— 返回 TranslationResult(ok=False, error=...)。
        """
        ...

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """快速探活：(ok, message)。settings UI "测试连接"按钮用。
        可发一次微小请求或仅验证凭证字段非空。"""
        ...
```

### 3.2 `tencent_translator.py`

```python
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.common.exception.tencent_cloud_sdk_exception \
    import TencentCloudSDKException
from tencentcloud.tmt.v20180321 import tmt_client, models

# 腾讯支持的 target 语种（含 source "auto"）
_TENCENT_LANGS = {"zh", "zh-TW", "en", "ja", "ko", "fr", "es", "it", "de",
                  "tr", "ru", "pt", "vi", "id", "th", "ms", "ar", "hi"}
# 统一码 → 腾讯码（基本一致，显式表加防御性）
_LANG_MAP = {"auto": "auto", "zh": "zh", "en": "en", "ja": "ja", "ko": "ko"}


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
        self._project_id = project_id

    def translate(self, text, source="auto", target="zh"):
        # 1. 入参校验
        if not text or not text.strip():
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.INVALID_INPUT,
                message="empty text", hint="输入是空的，没什么可翻译的",
                retryable=False, provider=self.name))
        if len(text.encode("utf-8")) > 6000:
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.INVALID_INPUT,
                message=f"text length {len(text.encode('utf-8'))} > 6000 bytes",
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
            return TranslationResult.fail(_map_tencent_error(e))
        except (OSError, ConnectionError, TimeoutError) as e:
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.NETWORK,
                message=str(e),
                hint="网络问题连不上腾讯，检查网络/代理后重试",
                retryable=True, provider=self.name))

        # 3. 包结果
        return TranslationResult.success(
            text=resp.TargetText, provider=self.name,
            used_chars=getattr(resp, "UsedAmount", len(text)))

    def health_check(self):
        # 不发请求（避免无谓计费），仅校验凭证字段
        if (not self._client._credential.secretId
                or not self._client._credential.secretKey):
            return False, "凭证为空"
        return True, "凭证已配置"


def _map_tencent_error(e: TencentCloudSDKException) -> TranslationError:
    """把腾讯 SDK 异常 code 映射为统一 TranslationError。
    code 详见 https://cloud.tencent.com/document/api/551/15619 错误码段。"""
    code = (e.code or "").strip()
    msg = e.message or ""
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

**SDK 关键注意**：

- `credential.Credential(...)` 仅包装，不校验有效性；真校验在首次 API 调用
- region 填错（如 `ap-mars`）SDK 不会立即报错，首次调用抛 `AuthFailure`
- SDK 默认行为是 5xx 自动重试 1 次 —— **本设计不依赖该行为**，但也不主动关闭（重试是 SDK 内部，与我们的"用户手动重试"不冲突）
- `resp.UsedAmount` 是计费基准（按字符）

### 3.3 `deeplx_translator.py`

```python
import json, logging
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

log = logging.getLogger(__name__)
_DEEPLX_TARGET_MAP = {"zh": "ZH", "en": "EN", "ja": "JA", "ko": "KO"}


class DeepLXTranslator(TranslationProvider):
    name = "deeplx"

    def __init__(self, url: str, timeout: float = 3.0):
        if not url or not url.strip():
            raise ValueError("DeepLX URL 为空")
        self._url = url.strip()
        self._timeout = timeout

    def translate(self, text, source="auto", target="zh"):
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
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
        except HTTPError as e:
            if e.code in (401, 403):
                return TranslationResult.fail(TranslationError(
                    code=TranslationErrorCode.AUTH_FAILED,
                    message=f"HTTP {e.code}",
                    hint="DeepLX 拒绝访问，检查 URL 或鉴权",
                    retryable=False, provider=self.name))
            if e.code == 429:
                return TranslationResult.fail(TranslationError(
                    code=TranslationErrorCode.RATE_LIMITED,
                    message="HTTP 429",
                    hint="DeepLX 频控触顶，稍等再试",
                    retryable=True, provider=self.name))
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.UNKNOWN,
                message=f"HTTP {e.code}",
                hint=f"DeepLX 返回 HTTP {e.code}",
                retryable=True, provider=self.name))
        except (URLError, OSError) as e:
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.NETWORK,
                message=str(e),
                hint=f"连不上 DeepLX（{self._url}），检查网络/部署",
                retryable=True, provider=self.name))

        try:
            obj = json.loads(raw.decode("utf-8"))
            data = obj.get("data") if isinstance(obj, dict) else None
            if not isinstance(data, str) or not data:
                return TranslationResult.fail(TranslationError(
                    code=TranslationErrorCode.UNKNOWN,
                    message=f"missing data in {obj!r}",
                    hint="DeepLX 返回格式异常",
                    retryable=True, provider=self.name))
            return TranslationResult.success(text=data, provider=self.name,
                                              used_chars=len(text))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return TranslationResult.fail(TranslationError(
                code=TranslationErrorCode.UNKNOWN,
                message="bad JSON",
                hint="DeepLX 返回非 JSON",
                retryable=True, provider=self.name))

    def health_check(self):
        return bool(self._url), self._url or "URL 未配置"
```

### 3.4 `translator.py` Facade + LRU 缓存

**配置来源**：项目里没有 `_CFG` 全局单例（refine/runninghub 显式传 cfg；DeepLX 走 os.environ）。本设计采取**混合模式**：

- 调用方有 cfg 就传（测试 / settings 测试连接 / 未来强类型调用方）
- 调用方没 cfg 就退回 `os.environ`（旧签名 `translate_en_to_zh(text)` 必须无参，因此必须有这条路径）
- `config.py` 启动时 + `translation_section.save_to()` 都把腾讯凭证同步到 `os.environ`（与 DeepLX 既有 `os.environ["DEEPLX_URL"]` 同步模式完全对齐）

```python
from __future__ import annotations
import hashlib, logging, os, threading
from collections import OrderedDict

from drama_shot_master.providers.translation_base import (
    TranslationProvider, TranslationResult, TranslationError,
    TranslationErrorCode,
)

log = logging.getLogger(__name__)


# ── 公共 API ──
def translate_en_to_zh(text: str) -> str | None:
    """旧签名保留；委派到当前 provider，失败返回 None。

    cfg 由调用方传入则用之，否则全走 os.environ。
    新代码应改用 translate(text, source, target, cfg=...) 拿 TranslationResult。
    """
    result = translate(text, source="en", target="zh")
    return result.text if result.ok else None


def translate(text: str, source: str = "auto",
              target: str = "zh",
              cfg=None) -> TranslationResult:
    """统一翻译入口；走 LRU 缓存。

    cfg=None 时全部从 os.environ 取（_CURRENT_TRANSLATOR /
    TENCENTCLOUD_SECRET_ID 等）。
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


# ── factory ──
def build_translation_provider(cfg=None) -> TranslationProvider | None:
    """据 cfg.current_translator 或 os.environ["_CURRENT_TRANSLATOR"] 构造
    provider；凭证不全返回 None。"""
    def _get(field: str, env_key: str, default: str = "") -> str:
        if cfg is not None:
            val = getattr(cfg, field, "") or ""
            if val:
                return val
        return os.environ.get(env_key, default)

    name = (_get("current_translator", "_CURRENT_TRANSLATOR", "tencent")).lower()
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
            project_id = int(getattr(cfg, "tencent_translator_project_id", 0)
                             or 0)
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


# ── LRU（线程安全） ──
_LRU_MAX = 64
_lru: "OrderedDict[tuple, TranslationResult]" = OrderedDict()
_lru_lock = threading.Lock()


def _cache_key(provider_name, source, target, text):
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return (provider_name, source, target, digest)


def _cache_get(key):
    with _lru_lock:
        if key in _lru:
            _lru.move_to_end(key)
            return _lru[key]
    return None


def _cache_set(key, value):
    with _lru_lock:
        _lru[key] = value
        _lru.move_to_end(key)
        while len(_lru) > _LRU_MAX:
            _lru.popitem(last=False)


def clear_cache():
    """provider 切换 / 凭证改了时主动清。"""
    with _lru_lock:
        _lru.clear()


def get_cache_stats() -> dict:
    """调试/测试用。"""
    with _lru_lock:
        return {"size": len(_lru), "max": _LRU_MAX}
```

**为什么不用 `functools.lru_cache`**：它会缓存所有调用结果（含失败的 `TranslationResult(ok=False)`），失败也命中缓存就糟糕了。手写 OrderedDict 只在 `ok=True` 时 set，更可控。

---

## 4. settings 配置 + UI 改造

### 4.1 `config.py` 字段变更

**新增 5 个字段**（位置紧贴现有 `deeplx_url`）：

```python
# 翻译
deeplx_url: str = ""                              # 现有，保留
current_translator: str = "tencent"               # "tencent" | "deeplx"
tencent_translator_secret_id: str = ""
tencent_translator_secret_key: str = ""
tencent_translator_region: str = "ap-beijing"
tencent_translator_project_id: int = 0
```

**`update_settings` 序列化**：5 个新字段加进 `data = {...}` 块。

**`load_from_disk` 反序列化**：4 个字符串字段加进既有"翻译/refine 字段"批量循环；`tencent_translator_project_id` (int) 单独处理。

**`.env` 加载**（紧贴 `deeplx_url=env.get("DEEPLX_URL")`）：

```python
tencent_translator_secret_id=env.get("TENCENTCLOUD_SECRET_ID") or "",
tencent_translator_secret_key=env.get("TENCENTCLOUD_SECRET_KEY") or "",
tencent_translator_region=env.get("TENCENTCLOUD_REGION") or "ap-beijing",
```

**环境变量回写**（紧贴 `if cfg.deeplx_url: os.environ["DEEPLX_URL"] = ...`）。这一步**必须做**——translator 的 facade 在无 cfg 调用方（旧 `translate_en_to_zh(text)` 签名）时全靠 `os.environ` 找凭证：

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

`translation_section.save_to()` 也要做同样的环境变量同步（修改 settings 后实时生效）。

**安全注意**：腾讯 SecretKey 进入 `os.environ` 意味着子进程可见。当前项目其它敏感凭证（refine_api_key / runninghub_api_key）都**没**进 os.environ——只有 DEEPLX_URL 进了。本设计把腾讯凭证进 environ 是为了支持旧 `translate_en_to_zh(text)` 无参签名；未来如果迁移所有调用方到显式传 cfg，可以拿掉 environ 回写（不破坏其它路径）。

**`_post_load_migrate` 启发式补全**（在 load_from_disk 末段调用）：

```python
def _post_load_migrate(cfg):
    """旧用户升级兼容：若用户只配过 DeepLX 没配腾讯，沿用 DeepLX。"""
    if not cfg.current_translator:
        if cfg.deeplx_url and not cfg.tencent_translator_secret_id:
            cfg.current_translator = "deeplx"
        else:
            cfg.current_translator = "tencent"
```

### 4.2 `translation_section.py` 重做

**布局**：provider radio 行 + QStackedWidget 分页（腾讯 / DeepLX）+ 测试连接行。风格对齐现有 `refine_section.py` 的 QFormLayout + theme token 提示文案。

```
┌─ 翻译 ──────────────────────────────────────────────────┐
│  翻译服务：  ○ 腾讯云机器翻译（推荐）  ○ DeepLX (自部署)  │
│  ┌─ QStackedWidget ──────────────────────────────────┐   │
│  │  [腾讯云分页]                                       │   │
│  │    SecretId    [ ___________________ ]            │   │
│  │    SecretKey   [ ************* ]  [👁]            │   │
│  │    Region      [ ap-beijing       ▼ ]              │   │
│  │    ProjectId   [ 0 ]                                │   │
│  │    去 [腾讯云控制台] 创建访问密钥，免费 5 万字符/月。 │   │
│  │  [DeepLX 分页]                                      │   │
│  │    DeepLX URL  [ http://localhost:1188/translate ] │   │
│  │    公共实例不稳定，建议自部署或切到腾讯云。           │   │
│  └───────────────────────────────────────────────────┘   │
│  [测试连接]   <状态：✓ 通过 / ✗ 错误信息>                 │
└──────────────────────────────────────────────────────────┘
```

**核心控件**：

- `QRadioButton` × 2 + `QButtonGroup` 联动 `QStackedWidget.setCurrentIndex`
- 腾讯分页：`QLineEdit` (SecretId) / `QLineEdit(EchoMode.Password)` + 眼睛切换 (SecretKey) / `QComboBox` 13 个 region / `QSpinBox` (ProjectId)
- DeepLX 分页：单 `QLineEdit` (URL)
- "测试连接"：`FunctionWorker(translate, "hello", "en", "zh")` 异步跑，状态栏显示结果
- `save_to(cfg)` 末尾必调 `clear_cache()` —— 切 provider 或改凭证后旧缓存失效
- `validate()` 据当前 radio 校验对应字段非空

**关键代码片段**：见第 3 节呈现稿（§3.2 完整实现）。

### 4.3 `translate_button.py` 升级到结构化错误

#### 替换 worker payload

```python
# OLD
worker = FunctionWorker(translate_en_to_zh, text)

# NEW
worker = FunctionWorker(translate, text, "en", "zh")
```

worker 回调拿 `TranslationResult` 而非 `str | None`。

#### `_TranslateDialog` 据 error.code 显示差异化按钮

```python
class _TranslateDialog(QDialog):
    def __init__(self, source, result: TranslationResult,
                 parent=None, on_retry=None, on_open_settings=None):
        super().__init__(parent)
        self.setWindowTitle("Prompt 中译预览")
        self.setMinimumSize(420, 320)
        self.setWindowFlag(Qt.WindowType.Window, True)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("原文"))
        src = QPlainTextEdit(source); src.setReadOnly(True)
        root.addWidget(src, 1)

        if result.ok:
            root.addWidget(QLabel(
                f"中译 · {result.provider} · {result.used_chars} 字符"))
            dst = QPlainTextEdit(result.text or "")
            dst.setReadOnly(True); root.addWidget(dst, 1)
            btn_row = self._build_success_buttons(result.text or "")
        else:
            err = result.error
            root.addWidget(QLabel(f"失败 · {err.provider} · {err.code}"))
            dst = QPlainTextEdit(f"{err.hint}\n\n详情：{err.message}")
            dst.setReadOnly(True); root.addWidget(dst, 1)
            btn_row = self._build_error_buttons(err, on_retry,
                                                 on_open_settings)
        root.addLayout(btn_row)

    def _build_error_buttons(self, err, on_retry, on_open_settings):
        row = QHBoxLayout()
        if err.code == TranslationErrorCode.AUTH_FAILED and on_open_settings:
            row.addWidget(_make_btn("去设置",
                                    lambda: (self.close(), on_open_settings())))
        elif err.code in (TranslationErrorCode.QUOTA_EXHAUSTED,
                          TranslationErrorCode.SERVICE_DISABLED):
            row.addWidget(_make_btn("打开腾讯控制台",
                                    self._open_tencent_console))
        if err.retryable and on_retry:
            btn_retry = _make_btn("重试",
                                  lambda: (self.close(), on_retry()))
            # RATE_LIMITED 加 5s 倒计时 disable
            if err.code == TranslationErrorCode.RATE_LIMITED:
                self._start_countdown(btn_retry, 5)
            row.addWidget(btn_retry)
        row.addStretch(1)
        row.addWidget(_make_btn("关闭", self.close))
        return row

    @staticmethod
    def _open_tencent_console():
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl("https://console.cloud.tencent.com/tmt"))
```

#### "去设置"路由

`attach_translate_button(text_widget, parent, on_open_settings=None)` 加可选参数；调用方（app_shell）传一个能"打开设置对话框 + 滚到翻译 section"的回调。没传则按钮不显示，柔性降级。

### 4.4 兼容性矩阵

| 场景 | 旧（DeepLX-only） | 新（Tencent 默认 + 兼容） |
|---|---|---|
| settings.json 无 `current_translator`（升级老用户） | n/a | `_post_load_migrate` 启发式补全：有 deeplx_url 沿用 DeepLX；否则默认 Tencent |
| 只设了 `DEEPLX_URL` 环境变量，没动 settings | 可用 | 启发式 → 仍走 DeepLX |
| 设了腾讯凭证、`current_translator=tencent` | n/a | 走腾讯 |
| 设腾讯凭证、`current_translator=deeplx` 但无 deeplx_url | n/a | factory 返 None；UI 弹窗 hint 引导切回腾讯或填 URL |
| 全空（全新装） | DeepLX 不可用 | 默认 Tencent；factory 返 None；UI hint "去设置 → 翻译 填凭证" |

---

## 5. 错误码总表 + UI 文案 + 重试策略

### 5.1 错误码 ↔ Provider 错误 ↔ UI 行为 主表

| TranslationErrorCode | 腾讯 SDK error.code | DeepLX 触发条件 | retryable | UI 按钮 | 中文 hint |
|---|---|---|:-:|---|---|
| `AUTH_FAILED` | `AuthFailure.*` | HTTP 401/403 | ✗ | **去设置** + 关闭 | "腾讯凭证错误，去设置里检查 SecretId/SecretKey/Region" / "DeepLX 拒绝访问，检查 URL 或鉴权" |
| `QUOTA_EXHAUSTED` | `FailedOperation.NoFreeAmount`, `FailedOperation.UserNotRegistered` | — | ✗ | **打开腾讯控制台** + 关闭 | "腾讯翻译额度用完了，去控制台充值或开通付费服务" |
| `SERVICE_DISABLED` | `FailedOperation.ServiceIsolate` | — | ✗ | **打开腾讯控制台** + 关闭 | "腾讯账号下 TMT 服务未开通或已停用" |
| `RATE_LIMITED` | `RequestLimitExceeded.*` | HTTP 429 | ✓ | **重试**（5s 倒计时）+ 关闭 | "请求太快了（5 QPS），稍等几秒再试" |
| `INVALID_INPUT` | `InvalidParameter.*`, `InvalidParameterValue.*` | 空 / >6000 字节 | ✗ | 关闭 | "腾讯说参数有问题：{message}" / "输入是空的" |
| `LANGUAGE_UNSUPPORTED` | `UnsupportedOperation.UnsupportedSourceLang/TargetLang` | target 不在 `_DEEPLX_TARGET_MAP` | ✗ | 关闭 | "{provider} 不支持目标语种 {target}" |
| `NETWORK` | (SDK 抛 OSError/TimeoutError) | URLError / OSError / 超时 | ✓ | **重试** + 关闭 | "网络问题连不上 {provider}，检查网络/代理" |
| `UNKNOWN` | 任何未匹配 code | 非 JSON / 缺 data 字段 | ✓ | **重试** + 关闭 | "{provider} 返回未知错误：{code}，详情查日志" |

### 5.2 重试策略

| code | 重试时机 | 自动倒计时 | 备注 |
|---|---|---|---|
| `RATE_LIMITED` | 用户点 + 5s 后允许 | ✓ 5s QTimer disable | 倒计时仅 UX 提示，非强制 |
| `NETWORK` / `UNKNOWN` | 用户点击即时 | ✗ | 无自动重试 |
| 其它 retryable=False | 不显示重试按钮 | n/a | |

**为什么不做指数退避 / 自动重试**：当前用例是"用户手动点译预览"，不是后台批量任务。失败弹窗本身就是天然退避。自动重试 = 用户没点也偷偷调腾讯 = 计费风险。

### 5.3 日志策略

| level | 内容 | 例 |
|---|---|---|
| `INFO` | 翻译成功 | `"translate ok: tencent en→zh, 42 chars"` |
| `WARNING` | retryable=True 错误 | `"tencent RATE_LIMITED: RequestLimitExceeded"` |
| `ERROR` | retryable=False 错误 | `"tencent AUTH_FAILED: AuthFailure.SignatureFailure"` |

**敏感字段过滤**：不打 SecretKey；不打 `TranslationResult.text`（避免 prompt 内容进日志）。

### 5.4 测试可观察性

测试断言 `TranslationResult.error.code` —— stable contract，不随中文文案改动失败：

```python
assert result.error.code == TranslationErrorCode.AUTH_FAILED
assert result.error.retryable is False
```

---

## 6. 测试策略

### 6.1 测试矩阵

| 测试文件 | 类型 | 用例数 | mock 对象 |
|---|---|:-:|---|
| `test_translation_base.py` | 单元 | ~6 | — |
| `test_tencent_translator.py` | 单元 | ~12 | `TmtClient` |
| `test_deeplx_translator.py` | 单元 | ~10 | `urllib.request.urlopen` |
| `test_translator_facade.py` | 单元 | ~8 | provider, cfg |
| `test_translator_cache.py` | 单元 | ~5 + 1 并发 | — |
| `test_translator.py`（旧改写） | 单元 | ~3 | `translate()` |
| `test_config.py`（追加） | 单元 | +4 | — |
| `test_translation_section_smoke.py` | UI smoke | ~6 | offscreen Qt |
| `test_translate_button_smoke.py` | UI smoke | ~5 | mock provider |
| `tests/manual/test_tencent_real.py` | 手动 | 1 | 真 API（opt-in） |

**总计**：~55 自动化用例 + 1 手动 opt-in。

### 6.2 关键单元用例

**`test_tencent_translator.py`** —— mock SDK：

- `__init__` 无 secret_id 抛 ValueError
- 成功翻译 `"hello"` → `result.ok=True, text="你好", used_chars=5`
- 空文本 → `INVALID_INPUT`，不调 SDK
- 超 6000 字节 → `INVALID_INPUT`
- target=`"jp"` 不在 `_TENCENT_LANGS` → `LANGUAGE_UNSUPPORTED`
- SDK 抛 `AuthFailure.SignatureFailure` → `AUTH_FAILED, retryable=False`
- SDK 抛 `AuthFailure.SignatureExpire` → 同样 `AUTH_FAILED`（前缀匹配验证）
- SDK 抛 `FailedOperation.NoFreeAmount` → `QUOTA_EXHAUSTED`
- SDK 抛 `FailedOperation.ServiceIsolate` → `SERVICE_DISABLED`
- SDK 抛 `RequestLimitExceeded` → `RATE_LIMITED, retryable=True`
- SDK 抛 `InvalidParameter.SomeField` → `INVALID_INPUT`
- SDK 抛未知 code → `UNKNOWN, retryable=True`
- SDK 抛 `OSError("connection refused")` → `NETWORK, retryable=True`
- `health_check()` 凭证非空 → `(True, ...)`

**`test_deeplx_translator.py`** —— mock urlopen：

- 成功响应 → ok=True
- HTTP 401/403 → `AUTH_FAILED`
- HTTP 429 → `RATE_LIMITED`
- HTTP 5xx → `UNKNOWN, retryable=True`
- URLError / socket.timeout → `NETWORK`
- 非 JSON / 缺 data → `UNKNOWN`
- 空 / 超长 / target 不支持 → `INVALID_INPUT` / `LANGUAGE_UNSUPPORTED`

**`test_translator_facade.py`** —— factory + 委派：

- cfg.current_translator="tencent" 凭证全 → `TencentTranslator`
- 同上 secret_id 空 → None
- cfg.current_translator="deeplx" deeplx_url 空 → None
- cfg.current_translator="unknown_xyz" → None + log warning
- 环境变量在 cfg 字段空时被采用
- `translate_en_to_zh("hello")` provider 成功 → 返回 str
- `translate_en_to_zh("hello")` provider 失败 → 返回 None（向后兼容）
- `translate(...)` provider=None → `ok=False, code=AUTH_FAILED`

**`test_translator_cache.py`** —— LRU 行为：

- 相同 key 第二次走缓存，不调 provider
- 失败结果不进缓存
- 不同 provider name → 不命中
- LRU 容量 64：插第 65 个 → 第 1 个被驱逐
- `clear_cache()` 后重调
- 8 线程并发 get/set 不崩

**`test_config.py` 追加 4 个**：

- 新字段落盘 → load 还原
- `.env` 在 settings 空时被回填
- `_post_load_migrate`：只有 deeplx_url → `current_translator="deeplx"`
- `_post_load_migrate`：全空 → `current_translator="tencent"`

### 6.3 UI smoke（offscreen Qt）

**`test_translation_section_smoke.py`**：默认加载 / radio 切换 / save_to 落盘 / validate 校验 / save_to 调 clear_cache（spy）。

**`test_translate_button_smoke.py`**：空文本 disabled / 非空 enabled / 点击弹 `_TranslateDialog` / mock 各 code → 弹窗显示对应按钮 / RATE_LIMITED 倒计时。

### 6.4 手动 smoke

```python
@pytest.mark.requires_tencent_creds
def test_real_tencent_translate():
    sid = os.environ.get("TENCENTCLOUD_SECRET_ID")
    skey = os.environ.get("TENCENTCLOUD_SECRET_KEY")
    if not sid or not skey:
        pytest.skip("无腾讯凭证")
    t = TencentTranslator(sid, skey, region="ap-beijing")
    r = t.translate("hello world", "en", "zh")
    assert r.ok and r.text and r.used_chars > 0
```

CI 不跑（账单 / 凭证泄露）。

### 6.5 mock 模式约定

`conftest.py` 的 autouse fixture 拦截 `TmtClient` 构造：

```python
@pytest.fixture(autouse=True)
def _isolate_sdk(monkeypatch):
    class _StubClient:
        def __init__(self, cred, region, profile):
            self._credential = cred
            self._region = region
        def TextTranslate(self, req):
            raise NotImplementedError("test should override")
    monkeypatch.setattr(
        "tencentcloud.tmt.v20180321.tmt_client.TmtClient", _StubClient)
```

单个用例用 `monkeypatch.setattr(_StubClient, "TextTranslate", ...)` 覆盖。

### 6.6 CI 矩阵

| 维度 | 取值 |
|---|---|
| OS | Linux + Windows |
| Python | 3.11+ |
| 默认命令 | `pytest tests/test_providers/test_translation_base.py tests/test_providers/test_tencent_translator.py tests/test_providers/test_deeplx_translator.py tests/test_providers/test_translator*.py tests/test_config.py -q` |
| UI smoke | `QT_QPA_PLATFORM=offscreen pytest tests/test_ui/test_translation_section_smoke.py tests/test_ui/test_translate_button_smoke.py -q` |
| 手动 smoke | 不在 CI |

---

## 7. 依赖、风险、上线分阶段

### 7.1 依赖变更

**新增（`pyproject.toml`）**：

```toml
"tencentcloud-sdk-python-tmt>=3.0.1207,<4.0.0",
```

- License：Apache-2.0 ✓
- 体积：~120KB wheel，纯 Python
- 间接依赖：`tencentcloud-sdk-python-common`（同社发布，~80KB）
- **不引** `tencentcloud-sdk-python` 全功能包（~50MB）

### 7.2 风险与缓解

| 风险 | 缓解 |
|---|---|
| 腾讯 SDK 突然 break API（v20180321 改版） | SDK 版本 pin `<4.0.0`；CI mock 测不依赖外部 |
| SDK 内部带遥测 / 日志泄露 SecretKey | ClientProfile 关 debug；翻译模块自己 logging 不打 SecretKey |
| 用户填错 region → 首次调用才报 AuthFailure | settings "测试连接"按钮真发请求；错误码 hint 提到 Region |
| 免费额度耗尽用户不知 | 弹窗显示 `used_chars`；QUOTA_EXHAUSTED → "打开腾讯控制台"按钮 |
| 旧 DeepLX 用户升级断崖 | `_post_load_migrate` 启发式补全沿用 DeepLX |
| LRU 不感知凭证切换 | `TranslationSection.save_to()` 显式 `clear_cache()` |
| 5 QPS 限频被反复点重试 | RATE_LIMITED 重试按钮 5s 倒计时 disable |
| 测试依赖网络 | 全 mock；手动 smoke 单独 mark 不进 CI |
| 凭证写错落 git | `settings.json` 已在 .gitignore |
| 腾讯账号未开通 TMT 服务 | SERVICE_DISABLED → "打开腾讯控制台"按钮 |

### 7.3 上线分阶段

| Phase | 范围 | 标志 |
|---|---|---|
| **P1 (MVP)** | translation_base + tencent_translator + deeplx_translator + facade + config 字段 + translation_section 重做 + 单元测试 + UI smoke | 用户能在设置切 provider，UI 翻译按钮跑通；老用户无缝过渡 |
| **P2** | translate_button 升级结构化错误 + 差异化按钮（去设置 / 控制台 / 重试 + 5s 倒计时） | 弹窗按 error.code 分发 |
| **P3 (YAGNI)** | 落盘缓存 / 批量翻译 / 语言下拉 / i18n hint / Web App 入口 | 实际需求触发再做 |

P1 完成即可发版本（drama_shot_master 小版本号约定）。

### 7.4 迁移文档（README / CHANGELOG）

```markdown
## 翻译服务升级

新增腾讯云机器翻译（TMT）支持，作为默认翻译后端。
旧的 DeepLX 仍可用，在 设置 → 翻译 切到 "DeepLX (自部署)" 即可。

### 全新用户
1. 在 https://console.cloud.tencent.com/cam/capi 创建访问密钥
2. 打开 设置 → 翻译，填入 SecretId / SecretKey
3. 点"测试连接"确认通过

### 老用户（之前用 DeepLX）
- 你的 deeplx_url 配置不会丢
- 启动时如果检测到只配过 DeepLX，会自动沿用 DeepLX
- 想切到腾讯：见"全新用户"流程

### 免费额度
腾讯云每月 5 万字符免费。超出按字符计费（约 0.058 元/千字符）。
UI 翻译弹窗会显示本次消耗字符数。
```

### 7.5 未来扩展锚点

| 扩展 | 锚点 |
|---|---|
| 接入百度 / 火山 / Google 翻译 | `TranslationProvider` ABC + factory 已为多 provider 准备 |
| 批量翻译 | ABC 加 `translate_batch(texts) -> list[Result]` 默认实现 = for 循环；腾讯实现可覆盖为 `TextTranslateBatch` |
| 落盘缓存 | `_cache_get/_cache_set` 已是函数封装，未来换实现不动调用方 |
| i18n hint | `TranslationError.hint` 已独立于 code |
| 翻译按钮目标语言下拉 | `translate(text, src, tgt)` 通用签名已支持 |

---

## 8. 参考资料

- 项目内：`drama_shot_master/providers/translator.py`（当前 DeepLX 实现）
- 项目内：`drama_shot_master/providers/base.py`（VisionProvider ABC，对齐对象）
- 项目内：`drama_shot_master/providers/openai_compat.py`（多 provider 范例）
- 项目内：`drama_shot_master/config.py`（凭证存储约定）
- 项目内：`drama_shot_master/ui/widgets/settings_sections/refine_section.py`（section 风格对齐）
- 项目内：`drama_shot_master/ui/widgets/translate_button.py`（UI 按钮 + 弹窗对齐）
- 外部：[腾讯云 TMT 接口总览](https://cloud.tencent.com/document/product/551/15612)
- 外部：[TextTranslate API 详细文档](https://cloud.tencent.com/document/api/551/15619)
- 外部：[tencentcloud-sdk-python-tmt PyPI](https://pypi.org/project/tencentcloud-sdk-python-tmt/)
- 外部：[tencentcloud-sdk-python GitHub](https://github.com/TencentCloud/tencentcloud-sdk-python)
- 外部：[腾讯云 TMT 入门教程](https://cloud.tencent.com/developer/article/1623177)
- 外部：[CAM 访问密钥控制台](https://console.cloud.tencent.com/cam/capi)
- 外部：[TMT 服务控制台](https://console.cloud.tencent.com/tmt)

---

**完。**
