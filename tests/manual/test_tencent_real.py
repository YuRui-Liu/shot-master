"""Opt-in real-API smoke for TencentTranslator.

Run:
    TENCENTCLOUD_SECRET_ID=… TENCENTCLOUD_SECRET_KEY=… \
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
