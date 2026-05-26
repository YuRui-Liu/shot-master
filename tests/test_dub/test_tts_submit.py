from pathlib import Path
from drama_shot_master.providers import tts_submit


class FakeClient:
    def __init__(self):
        self.uploaded = []
        self.created = None
        self._polls = 0

    def upload_file(self, path):
        self.uploaded.append(Path(path).name)
        return f"openapi/{Path(path).name}"

    def create_task(self, *, workflow_id, node_info_list, webhook_url=None):
        self.created = (workflow_id, node_info_list)
        return "task-1"

    def query_task(self, task_id):
        self._polls += 1
        if self._polls >= 2:
            return {"status": "SUCCESS", "results": [{"url": "http://x/o.flac"}]}
        return {"status": "RUNNING", "results": None}

    def download_file(self, url, dest):
        Path(dest).write_bytes(b"flac")
        return Path(dest)


def test_submit_uploads_and_downloads(tmp_path):
    c = FakeClient()
    node_info = [{"nodeId": "4", "fieldName": "prompt", "fieldValue": "hi"}]
    out = tts_submit.submit_and_wait(
        c, workflow_id="WF", node_info_list=node_info,
        upload_paths=[tmp_path / "spk.flac"], out_path=tmp_path / "result.flac",
        poll_interval=0)
    assert out == tmp_path / "result.flac" and out.read_bytes() == b"flac"
    assert c.created[0] == "WF"
    assert "spk.flac" in c.uploaded


def test_submit_returns_upload_map(tmp_path):
    # 上传应返回 path->fileName，便于调用方把 fileName 填进 nodeInfoList
    c = FakeClient()
    mp = tts_submit.upload_all(c, [tmp_path / "a.flac", tmp_path / "b.flac"])
    assert mp[tmp_path / "a.flac"] == "openapi/a.flac"
