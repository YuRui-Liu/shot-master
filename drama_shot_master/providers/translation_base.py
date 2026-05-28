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
