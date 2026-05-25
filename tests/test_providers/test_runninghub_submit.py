"""submit_ltx_task + LTXTaskHandle 单测（mock RunningHubClient）。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from drama_shot_master.providers.runninghub import (
    LTXSegment, LTXDirectorSpec, LTXTaskBuilder,
    RunningHubClient, RunningHubInvalidSpec,
    RunningHubTaskFailed, RunningHubUnavailable, RunningHubUploadError,
    submit_ltx_task, LTXTaskHandle,
)


# ---------- fixtures ----------

@pytest.fixture
def template_path():
    p = (Path(__file__).resolve().parent.parent.parent
         / "drama_shot_master" / "templates" / "ltx_director_v23.json")
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

def test_submit_requires_workflow_id(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    with pytest.raises(RunningHubInvalidSpec):
        submit_ltx_task(mock_client, spec, builder, workflow_id="")


def test_submit_uploads_unique_files_only(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    submit_ltx_task(mock_client, spec, builder, workflow_id="wf-1")
    # 3 段但只 2 个唯一文件
    assert mock_client.upload_file.call_count == 2


def test_submit_passes_workflow_id_and_node_info_list(
        mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    submit_ltx_task(mock_client, spec, builder, workflow_id="wf-123")
    call = mock_client.create_task.call_args
    assert call.kwargs.get("workflow_id") == "wf-123"
    assert isinstance(call.kwargs.get("node_info_list"), list)
    assert "workflow" not in call.kwargs


def test_submit_passes_webhook_url(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    submit_ltx_task(mock_client, spec, builder, workflow_id="wf-1",
                     webhook_url="https://cb.x")
    call = mock_client.create_task.call_args
    assert call.kwargs.get("webhook_url") == "https://cb.x"


def test_submit_upload_progress_callback(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    calls = []
    submit_ltx_task(mock_client, spec, builder, workflow_id="wf-1",
                     upload_progress_cb=lambda d, t, p: calls.append((d, t, p.name)))
    assert calls == [(1, 2, "a.png"), (2, 2, "b.png")]


def test_submit_returns_handle_with_correct_task_id(
        mock_client, builder, tmp_path):
    mock_client.create_task.return_value = "tid-42"
    spec = _spec_with_3_segments(tmp_path)
    handle = submit_ltx_task(mock_client, spec, builder, workflow_id="wf-1")
    assert isinstance(handle, LTXTaskHandle)
    assert handle.task_id == "tid-42"
    assert handle.spec is spec


# ---------- LTXTaskHandle.status ----------

def test_handle_status_proxies_query_task(mock_client, builder, tmp_path):
    spec = _spec_with_3_segments(tmp_path)
    handle = submit_ltx_task(mock_client, spec, builder, workflow_id="wf-1")
    mock_client.query_task.return_value = {"status": "RUNNING",
                                            "results": None}
    assert handle.status() == "RUNNING"
    mock_client.query_task.assert_called_with("tid-1")


# ---------- LTXTaskHandle.wait_for_result ----------

@pytest.fixture(autouse=False)
def fast_sleep(monkeypatch):
    """禁掉 time.sleep 加速轮询测试。"""
    monkeypatch.setattr("drama_shot_master.providers.runninghub.time.sleep",
                        lambda _: None)


def _make_handle(mock_client, builder, tmp_path,
                 download_fn=None) -> LTXTaskHandle:
    spec = _spec_with_3_segments(tmp_path)
    handle = submit_ltx_task(mock_client, spec, builder, workflow_id="wf-1")
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


# ---------- resolve_ helpers ----------

from drama_shot_master.providers.runninghub import (
    resolve_api_key, resolve_template_path, resolve_video_output_dir,
)


class _FakeCfg:
    def __init__(self, **kwargs):
        defaults = {
            "runninghub_api_key": "",
            "runninghub_template_path": "",
            "video_output_dir": "",
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


def test_resolve_api_key_from_cfg():
    cfg = _FakeCfg(runninghub_api_key="from-cfg")
    assert resolve_api_key(cfg) == "from-cfg"


def test_resolve_api_key_raises_when_missing():
    cfg = _FakeCfg(runninghub_api_key="")
    with pytest.raises(RunningHubUnavailable, match="RUNNINGHUB_API_KEY"):
        resolve_api_key(cfg)


def test_resolve_template_path_uses_builtin_when_cfg_empty():
    cfg = _FakeCfg(runninghub_template_path="")
    p = resolve_template_path(cfg)
    assert p.name == "ltx_director_v23.json"
    assert p.exists()


def test_resolve_template_path_uses_cfg_override(tmp_path):
    custom = tmp_path / "my.json"
    custom.write_text('{"46": {"class_type": "X"}}')
    cfg = _FakeCfg(runninghub_template_path=str(custom))
    assert resolve_template_path(cfg) == custom


def test_resolve_template_path_raises_when_cfg_path_missing(tmp_path):
    cfg = _FakeCfg(runninghub_template_path=str(tmp_path / "absent.json"))
    with pytest.raises(RunningHubInvalidSpec, match="不存在"):
        resolve_template_path(cfg)


def test_resolve_video_output_dir_uses_cfg(tmp_path):
    cfg = _FakeCfg(video_output_dir=str(tmp_path / "v"))
    assert resolve_video_output_dir(cfg, None) == tmp_path / "v"


def test_resolve_video_output_dir_falls_back_to_state(tmp_path):
    cfg = _FakeCfg(video_output_dir="")
    assert resolve_video_output_dir(cfg, tmp_path) == tmp_path


def test_resolve_video_output_dir_raises_when_both_missing():
    cfg = _FakeCfg(video_output_dir="")
    with pytest.raises(RunningHubInvalidSpec, match="视频输出目录"):
        resolve_video_output_dir(cfg, None)
