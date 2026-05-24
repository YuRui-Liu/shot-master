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
