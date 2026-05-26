from pathlib import Path
from unittest.mock import MagicMock
import pytest

from sound_track_agent.music_generator import generate_bgm, NODE_TAGS, NODE_BPM, NODE_DUR, NODE_SEED
from sound_track_agent.session import BGMCandidate


def _client(success_url="https://x/bgm.mp3"):
    c = MagicMock()
    c.create_task.return_value = "tid-1"
    c.query_task.return_value = {"status": "SUCCESS",
                                 "results": [{"url": success_url, "outputType": "mp3"}]}
    c.download_file.side_effect = lambda url, dest: Path(dest)
    return c


def test_generate_bgm_injects_correct_node_info(tmp_path):
    c = _client()
    out = generate_bgm(c, "wf-9", tags="Instrumental, calm",
                       bpm=98, duration=12.5, out_dir=tmp_path, seeds=[7])
    assert len(out) == 1
    assert isinstance(out[0], BGMCandidate)
    assert out[0].seed == 7
    call = c.create_task.call_args
    assert call.kwargs["workflow_id"] == "wf-9"
    nil = {(it["nodeId"], it["fieldName"]): it["fieldValue"]
           for it in call.kwargs["node_info_list"]}
    assert nil[(NODE_TAGS, "tags")] == "Instrumental, calm"
    assert nil[(NODE_BPM, "value")] == 98
    assert nil[(NODE_DUR, "value")] == 12.5
    assert nil[(NODE_SEED, "value")] == 7


def test_generate_bgm_multiple_candidates_distinct_seeds(tmp_path):
    c = _client()
    out = generate_bgm(c, "wf-9", tags="t", bpm=90, duration=5.0,
                       out_dir=tmp_path, seeds=[1, 2, 3])
    assert [b.seed for b in out] == [1, 2, 3]
    assert c.create_task.call_count == 3


def test_generate_bgm_raises_on_failed_status(tmp_path):
    c = _client()
    c.query_task.return_value = {"status": "FAILED",
                                 "errorMessage": "oom", "results": None}
    with pytest.raises(RuntimeError, match="FAILED"):
        generate_bgm(c, "wf-9", tags="t", bpm=90, duration=5.0,
                     out_dir=tmp_path, seeds=[1])
