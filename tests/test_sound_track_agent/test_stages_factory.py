from pathlib import Path
from unittest.mock import MagicMock
from sound_track_agent.stages_factory import build_stages
from sound_track_agent.session import (
    ScoringSession, SegmentScore, EmotionTag, BGMCandidate)
from sound_track_agent.scorer import CandidateScore


def _sess():
    return ScoringSession(
        source_mp4="/x/ep.mp4", source_hash="h", global_style="末日废土",
        frame_rate=24.0,
        segments=[SegmentScore(index=0, t_start=0.0, t_end=4.0)])


def test_tag_emotion_stage_uses_provider(tmp_path):
    prov = MagicMock()
    prov.generate.return_value = '{"labels":["tense"],"valence":-0.5,"arousal":0.7}'
    stages = build_stages(provider=prov, client=MagicMock(), workflow_id="wf",
                          work_dir=tmp_path, global_style="末日废土", seeds=[1],
                          frame_provider=lambda seg: tmp_path / "f.png")
    sess = _sess()
    emo = stages.tag_emotion(sess.segments[0], sess)
    assert emo.labels == ["tense"]
    assert prov.generate.called


def test_generate_stage_calls_music_generator(tmp_path):
    client = MagicMock()
    client.create_task.return_value = "tid"
    client.query_task.return_value = {"status": "SUCCESS",
                                      "results": [{"url": "https://x/b.mp3"}]}
    client.download_file.side_effect = lambda url, dest: Path(dest)
    stages = build_stages(provider=MagicMock(), client=client, workflow_id="wf-9",
                          work_dir=tmp_path, global_style="末日废土", seeds=[1, 2],
                          frame_provider=lambda seg: tmp_path / "f.png")
    sess = _sess()
    seg = sess.segments[0]
    seg.emotion = EmotionTag(labels=["tense"], arousal=0.8)
    seg.music_prompt = "Instrumental, tense"
    cands = stages.generate(seg, sess)
    assert all(isinstance(c, BGMCandidate) for c in cands)
    assert [c.seed for c in cands] == [1, 2]
    assert client.create_task.call_args.kwargs["workflow_id"] == "wf-9"


def test_compose_prompt_stage_sets_tags(tmp_path):
    stages = build_stages(provider=MagicMock(), client=MagicMock(), workflow_id="wf",
                          work_dir=tmp_path, global_style="古风", seeds=[1],
                          frame_provider=lambda seg: tmp_path / "f.png")
    sess = _sess()
    seg = sess.segments[0]
    seg.emotion = EmotionTag(labels=["calm"], arousal=0.2)
    tags = stages.compose_prompt(seg, sess)
    assert "古风" in tags and "calm" in tags


def test_build_stages_wires_generate_all(tmp_path):
    # 复用 test_batch_generator 的 FakeClient 思路：内联一个最小 fake
    import threading

    class FakeClient:
        def __init__(self):
            self.created = []
            self._lock = threading.Lock()

        def create_task(self, *, workflow_id, node_info_list=None):
            seed = next(n["fieldValue"] for n in node_info_list if n["nodeId"] == "109")
            with self._lock:
                self.created.append(seed)
            return f"t{seed}"

        def query_task(self, task_id):
            return {"status": "SUCCESS", "results": [{"url": "http://x/a.mp3"}]}

        def download_file(self, url, dest):
            from pathlib import Path
            dest = Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"A")
            return dest

    client = FakeClient()
    stages = build_stages(
        provider=None, client=client, workflow_id="wf", work_dir=tmp_path,
        global_style="style", seeds=[1, 2],
        frame_provider=lambda seg: tmp_path / "f.png",
        score_fn=lambda p, expected_dur=0.0: CandidateScore(0.5, 1.0, 0.5, 0.5),
        max_concurrency=2)
    assert stages.generate_all is not None

    sess = ScoringSession(source_mp4="x", source_hash="h", global_style="style",
                          frame_rate=24.0,
                          segments=[SegmentScore(index=0, t_start=0.0, t_end=1.0,
                                                 status="prompted")])
    stages.generate_all(sess)
    assert sorted(client.created) == [1, 2]
    assert len(sess.segments[0].candidates) == 2
    assert sess.segments[0].chosen_candidate is not None
