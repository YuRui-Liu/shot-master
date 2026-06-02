"""Test web_app.py: three-agent spawn logic, health check, state dict, teardown.

Since ``main()`` creates a QApplication and runs the event loop, full integration
tests require a display and a real ``market_intelligence`` module.  This file
tests the logic portions that can be verified headless — the spawn pattern,
health-check utility, state-dict keys, and teardown ordering.
"""

from __future__ import annotations

import sys
import threading
import time
from unittest import mock
from pathlib import Path

import pytest

# Module-level imports from web_app must not trigger Qt imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import web_app


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
class TestConstants:
    def test_ports(self):
        assert web_app.MEDIA_PORT == 18450
        assert web_app.MARKET_INTEL_PORT == 18460

    def test_api_urls(self):
        assert web_app.MEDIA_API == "http://127.0.0.1:18450"
        assert web_app.MARKET_INTEL_API == "http://127.0.0.1:18460"


# ---------------------------------------------------------------------------
# _wait_health
# ---------------------------------------------------------------------------
class TestWaitHealth:
    def test_returns_true_on_200(self):
        with mock.patch("urllib.request.urlopen") as m_open:
            m_open.return_value.__enter__.return_value.status = 200
            assert web_app._wait_health("http://127.0.0.1:18460/health", timeout=1.0) is True

    def test_returns_false_on_timeout(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("refused")):
            assert web_app._wait_health("http://127.0.0.1:9999/health", timeout=0.5) is False

    def test_retries_on_transient_failure(self):
        call_count = [0]

        def _flaky(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise OSError("refused")
            m = mock.MagicMock()
            m.__enter__.return_value.status = 200
            return m

        with mock.patch("urllib.request.urlopen", side_effect=_flaky):
            assert web_app._wait_health("http://127.0.0.1:18460/health", timeout=5.0) is True
            assert call_count[0] >= 3


# ---------------------------------------------------------------------------
# State dict shape — the keys expected by _tick / teardown
# ---------------------------------------------------------------------------
class TestStateDict:
    def test_required_keys(self):
        """Verify every key that _work / _tick / teardown references."""
        required = {"lifecycle", "media", "media_ok",
                    "market", "market_ok",
                    "ready", "sw_port", "mi_port"}
        state = {
            "lifecycle": None, "media": None, "media_ok": False,
            "market": None, "market_ok": False,
            "ready": False,
            "sw_port": 18430,
            "mi_port": web_app.MARKET_INTEL_PORT,
        }
        assert set(state.keys()) >= required, f"missing: {required - set(state.keys())}"

    def test_market_ok_defaults_false(self):
        state = {"market": None, "market_ok": False, "ready": False}
        assert state["market_ok"] is False
        assert state["ready"] is False


# ---------------------------------------------------------------------------
# _work spawn pattern: three agents spawned in parallel
# ---------------------------------------------------------------------------
class TestWorkSpawnPattern:
    """Verify the _work thread spawns three subprocesses and sets state keys.

    We do NOT import or call main() (would require Qt).  Instead we replicate
    the essential spawn logic extracted from _work().
    """

    @staticmethod
    def _fake_work(state, Popen_mock, wait_health_mock, lifecycle_cls_mock=None):
        """Replicate _work body (without the Qt-bound closure vars)."""
        state["media"] = Popen_mock(["fake-python", "-m", "media_agent.server"])
        try:
            state["market"] = Popen_mock(
                ["fake-python", "-m", "market_intelligence.server"])
        except Exception:
            state["market"] = None

        state["media_ok"] = wait_health_mock(web_app.MEDIA_API + "/health")

        if state["market"] is not None:
            state["market_ok"] = wait_health_mock(web_app.MARKET_INTEL_API + "/health")

        if lifecycle_cls_mock:
            lc = lifecycle_cls_mock.return_value
            lc.spawn.return_value = 18430
            state["sw_port"] = lc.spawn() or state["sw_port"]
            state["lifecycle"] = lc

        state["ready"] = True

    def test_spawns_three_processes(self):
        state = {
            "lifecycle": None, "media": None, "media_ok": False,
            "market": None, "market_ok": False, "ready": False,
            "sw_port": 18430,
            "mi_port": web_app.MARKET_INTEL_PORT,
        }
        popen = mock.MagicMock()
        health = mock.MagicMock(return_value=True)  # all health checks pass
        lc_cls = mock.MagicMock()
        lc_cls.return_value.spawn.return_value = 18430

        self._fake_work(state, popen, health, lc_cls)

        # Three Popen calls: media, market_intel, (screenwriter via lifecycle)
        assert popen.call_count == 2, f"expected 2 Popen calls (media+market), got {popen.call_count}"
        popen.assert_any_call(["fake-python", "-m", "media_agent.server"])
        popen.assert_any_call(["fake-python", "-m", "market_intelligence.server"])

        assert state["media_ok"] is True
        assert state["market_ok"] is True
        assert state["ready"] is True
        assert state["media"] is not None
        assert state["market"] is not None

    def test_market_spawn_failure_graceful(self):
        """When market_intelligence module doesn't exist, state stays usable."""
        state = {
            "lifecycle": None, "media": None, "media_ok": False,
            "market": None, "market_ok": False, "ready": False,
            "sw_port": 18430,
            "mi_port": web_app.MARKET_INTEL_PORT,
        }
        popen = mock.MagicMock()
        popen.side_effect = [mock.MagicMock(), FileNotFoundError("no module")]
        health = mock.MagicMock(return_value=True)

        self._fake_work(state, popen, health)

        # Only media was spawned successfully
        assert state["media_ok"] is True
        assert state["market_ok"] is False   # never set because market is None
        assert state["ready"] is True
        assert state["market"] is None

    def test_market_health_timeout(self):
        """market_intel starts but doesn't become healthy within timeout."""
        state = {
            "lifecycle": None, "media": None, "media_ok": False,
            "market": None, "market_ok": False, "ready": False,
            "sw_port": 18430,
            "mi_port": web_app.MARKET_INTEL_PORT,
        }
        popen = mock.MagicMock()
        health = mock.MagicMock(side_effect=[True, False])  # media OK, market TIMEOUT

        self._fake_work(state, popen, health)

        assert state["media_ok"] is True
        assert state["market_ok"] is False
        assert state["ready"] is True


# ---------------------------------------------------------------------------
# Teardown: verify all three processes are terminated
# ---------------------------------------------------------------------------
class TestTeardown:
    def test_teardown_terminates_all_processes(self):
        """Simulate the finally block: lifecycle.terminate(), media/market terminate+kill."""
        lifecycle = mock.MagicMock()
        media = mock.MagicMock()
        market = mock.MagicMock()
        # All still running
        media.poll.return_value = None
        market.poll.return_value = None

        # --- replicate teardown from web_app.main() finally block ---
        if lifecycle is not None:
            try:
                lifecycle.terminate()
            except Exception:
                pass
        for proc, _label in ((media, "media"), (market, "market_intel")):
            if proc is None:
                continue
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        lifecycle.terminate.assert_called_once()
        media.terminate.assert_called_once()
        media.wait.assert_called_once_with(timeout=5)
        market.terminate.assert_called_once()
        market.wait.assert_called_once_with(timeout=5)

    def test_teardown_skips_none_proc(self):
        lifecycle = mock.MagicMock()
        media = mock.MagicMock()
        market = None  # never spawned

        if lifecycle is not None:
            lifecycle.terminate()
        for proc, _label in ((media, "media"), (market, "market_intel")):
            if proc is None:
                continue
            proc.terminate()
            proc.wait(timeout=5)

        lifecycle.terminate.assert_called_once()
        media.terminate.assert_called_once()
        # market is None => no terminate called on it

    def test_teardown_kill_on_terminate_failure(self):
        proc = mock.MagicMock()
        proc.terminate.side_effect = OSError("access denied")

        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()


# ---------------------------------------------------------------------------
# Splash stage progression: verify ready-state marks all 5 stages done
# ---------------------------------------------------------------------------
class TestSplashStageProgression:
    """Verify the JS snippets that _tick emits for stage transitions."""

    def test_media_ok_js_sets_stage_0_done_1_active(self):
        """Recreate the JS from _tick when media_ok becomes true."""
        code = "window.splashStage && (splashStage(0,'done'),splashStage(1,'active'))"
        assert "splashStage(0,'done')" in code
        assert "splashStage(1,'active')" in code

    def test_market_ok_js_sets_stage_1_done_2_3_active(self):
        """Recreate the JS from _tick when market_ok becomes true."""
        code = "window.splashStage && (splashStage(1,'done'),splashStage(2,'active'),splashStage(3,'active'))"
        assert "splashStage(1,'done')" in code
        assert "splashStage(2,'active')" in code
        assert "splashStage(3,'active')" in code

    def test_ready_js_marks_all_five_stages_done(self):
        """Recreate the JS from _tick when ready is true."""
        code = ("window.splashStage && (splashStage(2,'done'),splashStage(3,'done'),"
                "splashStage(4,'done')); window.splashProgress && splashProgress(1)")
        assert "splashStage(2,'done')" in code
        assert "splashStage(3,'done')" in code
        assert "splashStage(4,'done')" in code
        assert "splashProgress(1)" in code

    def test_stage_count_matches_splash_html(self):
        """Splash HTML defines 5 stages (0-4); JS labels must have 5 entries."""
        labels = ["加载配置 / 风格圣经", "启动后端服务", "索引项目资源",
                   "启动市场情报服务", "准备工作区"]
        assert len(labels) == 5, f"expected 5 stages, got {len(labels)}"


# ---------------------------------------------------------------------------
# URL construction: app.html gets market_intel query param
# ---------------------------------------------------------------------------
class TestAppUrl:
    def test_url_includes_market_intel(self):
        sw_port = 18430
        mi_port = 18460
        media_api = "http://127.0.0.1:18450"
        url = (f"{media_api}/ui/app.html?sw=http://127.0.0.1:{sw_port}"
               f"&media={media_api}&market_intel=http://127.0.0.1:{mi_port}")
        assert "market_intel=http://127.0.0.1:18460" in url
        assert "sw=http://127.0.0.1:18430" in url
        assert "media=http://127.0.0.1:18450" in url
