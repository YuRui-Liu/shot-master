"""sfx/generator: 单 SFX job 完整生命周期（create_task → poll → download）。"""
import pytest
from unittest.mock import MagicMock
from sound_track_agent.sfx.generator import _wait_success, generate_sfx


def test_wait_success_returns_url_when_success():
    client = MagicMock()
    client.get_task_status.return_value = {"status": "SUCCESS"}
    client.get_task_outputs.return_value = [
        {"fileType": "mp3", "fileUrl": "https://x/y.mp3"}
    ]
    url = _wait_success(client, "tid", timeout=10.0,
                        poll_interval=0.1, sleep=lambda _s: None)
    assert url == "https://x/y.mp3"


def test_wait_success_raises_on_failure():
    client = MagicMock()
    client.get_task_status.return_value = {"status": "FAILED", "msg": "oom"}
    with pytest.raises(RuntimeError, match="failed"):
        _wait_success(client, "tid", timeout=10.0,
                      poll_interval=0.1, sleep=lambda _s: None)


def test_wait_success_raises_on_timeout(monkeypatch):
    client = MagicMock()
    client.get_task_status.return_value = {"status": "RUNNING"}
    import time as _t
    t = [0.0]
    monkeypatch.setattr(_t, "time", lambda: t[0])
    def _sleep(_s):
        t[0] += 100
    with pytest.raises(TimeoutError):
        _wait_success(client, "tid", timeout=1.0,
                      poll_interval=0.5, sleep=_sleep)


def test_generate_sfx_e2e_with_mock(tmp_path):
    client = MagicMock()
    client.create_task.return_value = "tid-123"
    client.get_task_status.return_value = {"status": "SUCCESS"}
    client.get_task_outputs.return_value = [
        {"fileType": "mp3", "fileUrl": "https://x/y.mp3"}
    ]
    def fake_download(url, dest):
        from pathlib import Path
        Path(dest).write_bytes(b"audio-bytes")
    client.download_file.side_effect = fake_download
    out = tmp_path / "out.mp3"
    result = generate_sfx(client, "wf-sfx", prompt="门吱呀", duration=3.0,
                          seed=1, out_path=out, poll_interval=0.1,
                          sleep=lambda _s: None)
    assert result.exists()
    assert result.read_bytes() == b"audio-bytes"
    # 验证 create_task 收到了 4 个节点
    args = client.create_task.call_args
    assert args.kwargs["workflow_id"] == "wf-sfx"
    nodes = args.kwargs["node_info_list"]
    assert len(nodes) == 4
    assert any(n["nodeId"] == "92" and n["fieldValue"] == "门吱呀" for n in nodes)
