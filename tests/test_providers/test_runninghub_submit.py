"""submit_ltx_task + LTXTaskHandle 单测（mock RunningHubClient）。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.providers.runninghub import (
    LTXSegment, LTXDirectorSpec, LTXTaskBuilder,
    RunningHubClient, RunningHubInvalidSpec,
    RunningHubTaskFailed, RunningHubUnavailable, RunningHubUploadError,
    submit_ltx_task, LTXTaskHandle,
)


# ---------- fixtures ----------

@pytest.fixture
def template_path():
    p = (Path(__file__).resolve().parent.parent.parent
         / "app" / "templates" / "ltx_director_v23.json")
    return p


@pytest.fixture
def builder(template_path):
    return LTXTaskBuilder(template_path)


@pytest.fixture
def mock_client():
    c = MagicMock(spec=RunningHubClient)
    c.create_task.return_value = "tid-1"
    c.upload_file.side_effect = lambda p: f"openapi/{p.name}"
    return c


def _spec_with_3_segments(tmp_path) -> LTXDirectorSpec:
    img1 = tmp_path / "a.png"; img1.write_bytes(b"a")
    img2 = tmp_path / "b.png"; img2.write_bytes(b"b")
    return LTXDirectorSpec(
        segments=(
            LTXSegment(local_prompt="s1", length=10, image_path=img1),
            LTXSegment(local_prompt="s2", length=10, image_path=img1),  # 复用
            LTXSegment(local_prompt="s3", length=10, image_path=img2),
        ),
        frame_rate=24,
        filename_prefix="testvid",
        output_dir=tmp_path / "out",
    )


# ---------- submit_ltx_task ----------

def test_submit_rejects_unknown_mode(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    with pytest.raises(RunningHubInvalidSpec):
        submit_ltx_task(mock_client, spec, builder, mode="weird")


def test_submit_id_mode_requires_workflow_id(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    with pytest.raises(RunningHubInvalidSpec):
        submit_ltx_task(mock_client, spec, builder, mode="id")


def test_submit_uploads_unique_files_only(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    submit_ltx_task(mock_client, spec, builder, mode="inline")
    # 3 段但只 2 个唯一文件
    assert mock_client.upload_file.call_count == 2


def test_submit_inline_passes_workflow_dict(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    submit_ltx_task(mock_client, spec, builder, mode="inline")
    call = mock_client.create_task.call_args
    assert "workflow" in call.kwargs
    assert isinstance(call.kwargs["workflow"], dict)
    assert "workflow_id" not in call.kwargs or not call.kwargs.get("workflow_id")


def test_submit_id_mode_passes_workflow_id_and_node_info_list(
        mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    submit_ltx_task(mock_client, spec, builder, mode="id",
                     workflow_id="wf-123")
    call = mock_client.create_task.call_args
    assert call.kwargs.get("workflow_id") == "wf-123"
    assert isinstance(call.kwargs.get("node_info_list"), list)
    assert "workflow" not in call.kwargs or not call.kwargs.get("workflow")


def test_submit_passes_webhook_url(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    submit_ltx_task(mock_client, spec, builder, mode="inline",
                     webhook_url="https://cb.x")
    call = mock_client.create_task.call_args
    assert call.kwargs.get("webhook_url") == "https://cb.x"


def test_submit_upload_progress_callback(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    calls = []
    submit_ltx_task(mock_client, spec, builder, mode="inline",
                     upload_progress_cb=lambda d, t, p: calls.append((d, t, p.name)))
    assert calls == [(1, 2, "a.png"), (2, 2, "b.png")]


def test_submit_returns_handle_with_correct_task_id(
        mock_client, builder, tmp_path):
    mock_client.create_task.return_value = "tid-42"
    spec = _spec_with_3_segments(tmp_path)
    handle = submit_ltx_task(mock_client, spec, builder, mode="inline")
    assert isinstance(handle, LTXTaskHandle)
    assert handle.task_id == "tid-42"
    assert handle.spec is spec


# ---------- LTXTaskHandle.status ----------

def test_handle_status_proxies_query_task(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    handle = submit_ltx_task(mock_client, spec, builder, mode="inline")
    mock_client.query_task.return_value = {"status": "RUNNING",
                                            "results": None}
    assert handle.status() == "RUNNING"
    mock_client.query_task.assert_called_with("tid-1")


# ---------- LTXTaskHandle.wait_for_result ----------

@pytest.fixture(autouse=False)
def fast_sleep(monkeypatch):
    """禁掉 time.sleep 加速轮询测试。"""
    monkeypatch.setattr("app.providers.runninghub.time.sleep",
                        lambda _: None)


def _make_handle(mock_client, builder, tmp_path,
                 download_fn=None) -> LTXTaskHandle:
    spec = _spec_with_3_segments(tmp_path)
    handle = submit_ltx_task(mock_client, spec, builder, mode="inline")
    if download_fn is not None:
        mock_client.download_file.side_effect = download_fn
    else:
        mock_client.download_file.side_effect = lambda url, dest: dest
    return handle


def test_wait_success_downloads_mp4(mock_client, builder, tmp_path, fast_sleep):
    mock_client.query_task.return_value = {
        "status": "SUCCESS",
        "results": [{"url": "https://x/v.mp4", "outputType": "mp4"}],
    }
    handle = _make_handle(mock_client, builder, tmp_path)
    result = handle.wait_for_result(timeout=10, poll_interval=0.1)
    assert result.name == "testvid_tid-1.mp4"
    assert result.parent == tmp_path / "out"
    mock_client.download_file.assert_called_once_with(
        "https://x/v.mp4", result)


def test_wait_failed_raises(mock_client, builder, tmp_path, fast_sleep):
    mock_client.query_task.return_value = {
        "status": "FAILED",
        "errorCode": "E_OOM",
        "errorMessage": "out of memory",
    }
    handle = _make_handle(mock_client, builder, tmp_path)
    with pytest.raises(RunningHubTaskFailed) as exc_info:
        handle.wait_for_result(timeout=10, poll_interval=0.1)
    assert "out of memory" in str(exc_info.value)


def test_wait_timeout_cancels_and_raises(mock_client, builder, tmp_path, fast_sleep):
    mock_client.query_task.return_value = {"status": "RUNNING",
                                            "results": None}
    handle = _make_handle(mock_client, builder, tmp_path)
    with pytest.raises(RunningHubTaskFailed) as exc_info:
        handle.wait_for_result(timeout=0.5, poll_interval=0.1)
    assert "timeout" in str(exc_info.value).lower()
    mock_client.cancel_task.assert_called_with("tid-1")


def test_wait_progress_emitted_on_status_change(
        mock_client, builder, tmp_path, fast_sleep):
    states = iter([
        {"status": "QUEUED"},
        {"status": "RUNNING"},
        {"status": "RUNNING"},   # 不变，不回调
        {"status": "SUCCESS",
         "results": [{"url": "https://x/v.mp4", "outputType": "mp4"}]},
    ])
    mock_client.query_task.side_effect = lambda _: next(states)
    handle = _make_handle(mock_client, builder, tmp_path)

    seen = []
    handle.wait_for_result(timeout=10, poll_interval=0.1,
                            progress_cb=seen.append)
    # 状态变化 2 次（QUEUED → RUNNING），SUCCESS 是终态不计 progress
    assert seen == ["QUEUED", "RUNNING"]


def test_wait_cancel_check_aborts(mock_client, builder, tmp_path, fast_sleep):
    mock_client.query_task.return_value = {"status": "RUNNING"}
    handle = _make_handle(mock_client, builder, tmp_path)
    counter = {"n": 0}

    def cancel_check():
        counter["n"] += 1
        return counter["n"] >= 2  # 第 2 轮触发取消

    with pytest.raises(RunningHubTaskFailed, match="cancelled"):
        handle.wait_for_result(timeout=10, poll_interval=0.1,
                                cancel_check=cancel_check)
    mock_client.cancel_task.assert_called_with("tid-1")


def test_wait_tolerates_transient_network_error(
        mock_client, builder, tmp_path, fast_sleep):
    responses = iter([
        RunningHubUnavailable("net1"),
        RunningHubUnavailable("net2"),
        {"status": "SUCCESS",
         "results": [{"url": "https://x/v.mp4", "outputType": "mp4"}]},
    ])

    def query(_):
        r = next(responses)
        if isinstance(r, Exception):
            raise r
        return r

    mock_client.query_task.side_effect = query
    handle = _make_handle(mock_client, builder, tmp_path)
    result = handle.wait_for_result(timeout=10, poll_interval=0.1)
    assert result.name == "testvid_tid-1.mp4"


def test_wait_3_consecutive_network_errors_raises(
        mock_client, builder, tmp_path, fast_sleep):
    mock_client.query_task.side_effect = RunningHubUnavailable("down")
    handle = _make_handle(mock_client, builder, tmp_path)
    with pytest.raises(RunningHubUnavailable, match="3"):
        handle.wait_for_result(timeout=10, poll_interval=0.1)


def test_wait_empty_results_raises(mock_client, builder, tmp_path, fast_sleep):
    mock_client.query_task.return_value = {"status": "SUCCESS",
                                            "results": []}
    handle = _make_handle(mock_client, builder, tmp_path)
    with pytest.raises(RunningHubTaskFailed, match="results"):
        handle.wait_for_result(timeout=10, poll_interval=0.1)


def test_wait_uses_outputType_for_extension(
        mock_client, builder, tmp_path, fast_sleep):
    mock_client.query_task.return_value = {
        "status": "SUCCESS",
        "results": [{"url": "https://x/v.webm", "outputType": "webm"}],
    }
    handle = _make_handle(mock_client, builder, tmp_path)
    result = handle.wait_for_result(timeout=10, poll_interval=0.1)
    assert result.suffix == ".webm"


# ---------- handle.cancel ----------

def test_handle_cancel_calls_client(mock_client, builder, tmp_path):
    handle = _make_handle(mock_client, builder, tmp_path)
    handle.cancel()
    mock_client.cancel_task.assert_called_with("tid-1")
