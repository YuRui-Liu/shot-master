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
