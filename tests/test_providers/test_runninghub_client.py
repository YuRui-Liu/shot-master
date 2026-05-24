"""RunningHubClient 单测（mock httpx）。"""
from __future__ import annotations

import pytest

from app.providers.runninghub import (
    RunningHubUnavailable, RunningHubTaskFailed,
    RunningHubUploadError, RunningHubInvalidSpec,
)


def test_exception_classes_are_distinct():
    assert issubclass(RunningHubUnavailable, Exception)
    assert issubclass(RunningHubTaskFailed, Exception)
    assert issubclass(RunningHubUploadError, Exception)
    assert issubclass(RunningHubInvalidSpec, Exception)
    # 都是独立类，互不继承
    for a, b in [
        (RunningHubUnavailable, RunningHubTaskFailed),
        (RunningHubUploadError, RunningHubTaskFailed),
        (RunningHubInvalidSpec, RunningHubUnavailable),
    ]:
        assert not issubclass(a, b) and not issubclass(b, a)
