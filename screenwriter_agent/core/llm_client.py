"""LLM 调用 wrapper（OpenAI 兼容协议）。流式：yield StreamChunk。

api_key/base_url/model 都由调用方按阶段从 cfg 传入；本类是无状态的。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass
class StreamChunk:
    kind: str       # "delta" | "done"
    text: str = ""
    raw: str = ""   # 累计全文（done 时填）


class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str,
                 reasoning_effort: str = "high",
                 response_format: dict | None = None,
                 timeout: float = 300.0):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.response_format = response_format
        self.timeout = timeout

    def _raw_stream(self, *, messages: list[dict]) -> Iterator:
        """调底层 OpenAI SDK；测试时被 monkeypatch。"""
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key, base_url=self.base_url,
                        timeout=self.timeout)
        kwargs = {"model": self.model, "messages": messages, "stream": True}
        if self.response_format:
            kwargs["response_format"] = self.response_format
        return client.chat.completions.create(**kwargs)

    def stream_chat(self, messages: list[dict]) -> Iterator[StreamChunk]:
        """流式调 LLM；逐 chunk yield delta；最后 yield 一个 done 含完整 raw。"""
        acc: list[str] = []
        for ch in self._raw_stream(messages=messages):
            try:
                delta = ch.choices[0].delta
                txt = getattr(delta, "content", "") or ""
            except Exception:
                txt = ""
            if txt:
                acc.append(txt)
                yield StreamChunk(kind="delta", text=txt)
        yield StreamChunk(kind="done", raw="".join(acc))
