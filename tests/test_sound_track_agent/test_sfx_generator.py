"""sfx/generator: 单 SFX job 完整生命周期（create_task → poll → download）。"""
import pytest
from unittest.mock import MagicMock
from sound_track_agent.sfx.generator import _wait_success, generate_sfx


class _RealContractClient:
    """模拟真实 RunningHubClient 契约：仅暴露 query_task/create_task/download_file。

    刻意 **不** 提供 get_task_status/get_task_outputs —— 调用不存在的方法会
    AttributeError，从而复现 generator 用错 API 的真实 bug（MagicMock 会
    自动伪造任何方法，掩盖该 bug）。
    """

    def __init__(self, query_results):
        self._query_results = list(query_results)
        self._i = 0
        self.created = []
        self.downloaded = []

    def create_task(self, *, workflow_id, node_info_list):
        self.created.append((workflow_id, node_info_list))
        return "tid-123"

    def query_task(self, task_id):
        r = self._query_results[min(self._i, len(self._query_results) - 1)]
        self._i += 1
        return r

    def download_file(self, url, dest):
        from pathlib import Path
        Path(dest).write_bytes(b"audio-bytes")
        self.downloaded.append((url, str(dest)))
        return dest


def test_wait_success_uses_query_task_real_contract():
    """_wait_success 必须用 query_task（真实 client 契约），SUCCESS 时取 results[0].url。"""
    client = _RealContractClient([
        {"status": "RUNNING", "results": None},
        {"status": "SUCCESS",
         "results": [{"url": "https://x/y.mp3", "outputType": "mp3"}]},
    ])
    url = _wait_success(client, "tid", timeout=10.0,
                        poll_interval=0.1, sleep=lambda _s: None)
    assert url == "https://x/y.mp3"


def test_wait_success_raises_on_failed_real_contract():
    client = _RealContractClient([
        {"status": "FAILED", "errorMessage": "oom", "results": None},
    ])
    with pytest.raises(RuntimeError):
        _wait_success(client, "tid", timeout=10.0,
                      poll_interval=0.1, sleep=lambda _s: None)


def test_generate_sfx_e2e_real_contract(tmp_path):
    client = _RealContractClient([
        {"status": "SUCCESS",
         "results": [{"url": "https://x/y.mp3", "outputType": "mp3"}]},
    ])
    out = tmp_path / "out.mp3"
    result = generate_sfx(client, "wf-sfx", prompt="门吱呀", duration=3.0,
                          seed=1, out_path=out, poll_interval=0.1,
                          sleep=lambda _s: None)
    assert result.exists()
    assert result.read_bytes() == b"audio-bytes"
    wf, nodes = client.created[0]
    assert wf == "wf-sfx"
    assert len(nodes) == 4


def test_wait_success_raises_on_timeout():
    """RUNNING 永不结束 → TimeoutError。"""
    client = _RealContractClient([{"status": "RUNNING", "results": None}])
    with pytest.raises(TimeoutError):
        _wait_success(client, "tid", timeout=1.0,
                      poll_interval=0.5, sleep=lambda _s: None)


def test_generate_sfx_passes_prompt_node():
    """create_task node_info 含 prompt 节点（92）。"""
    client = _RealContractClient([
        {"status": "SUCCESS",
         "results": [{"url": "https://x/y.mp3", "outputType": "mp3"}]},
    ])
    import tempfile, os
    out = os.path.join(tempfile.mkdtemp(), "out.mp3")
    generate_sfx(client, "wf-sfx", prompt="门吱呀", duration=3.0,
                 seed=1, out_path=out, poll_interval=0.1,
                 sleep=lambda _s: None)
    _wf, nodes = client.created[0]
    assert any(n["nodeId"] == "92" and n["fieldValue"] == "门吱呀" for n in nodes)
