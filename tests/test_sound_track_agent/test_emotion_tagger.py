from pathlib import Path
from unittest.mock import MagicMock
from sound_track_agent.emotion_tagger import tag_emotion, tag_emotion_multi, _parse_emotion
from sound_track_agent.session import EmotionTag


class _FakeProvider:
    def __init__(self, reply): self._reply = reply; self.calls = []
    def generate(self, images, system_prompt, user_supplement):
        self.calls.append((list(images), system_prompt, user_supplement))
        return self._reply


def test_parse_emotion_plain_json():
    raw = '{"labels":["tense","eerie"],"valence":-0.7,"arousal":0.8}'
    e = _parse_emotion(raw)
    assert e.labels == ["tense", "eerie"]
    assert e.valence == -0.7
    assert e.arousal == 0.8


def test_parse_emotion_strips_code_fence():
    raw = '```json\n{"labels":["calm"],"valence":0.3,"arousal":0.2}\n```'
    e = _parse_emotion(raw)
    assert e.labels == ["calm"]
    assert e.arousal == 0.2


def test_parse_emotion_bad_json_returns_neutral():
    e = _parse_emotion("sorry I cannot")
    assert e.labels == []
    assert e.valence == 0.0
    assert e.arousal == 0.3


def test_tag_emotion_calls_provider_and_parses(tmp_path):
    img = tmp_path / "f.png"; img.write_bytes(b"x")
    prov = _FakeProvider('{"labels":["sad"],"valence":-0.5,"arousal":0.3}')
    e = tag_emotion(prov, img, global_style="末日废土")
    assert isinstance(e, EmotionTag)
    assert e.labels == ["sad"]
    images, sys_p, usr = prov.calls[0]
    assert images == [img]
    assert "末日废土" in (sys_p + usr)


def test_tag_emotion_multi_passes_image_list_to_provider():
    """多帧调用应把 list[Path] 完整传给 provider.generate。"""
    prov = MagicMock()
    prov.generate.return_value = (
        '{"labels":["tense","focused"],"valence":-0.3,"arousal":0.7,"intensity":0.6}')
    paths = [Path("/a.png"), Path("/b.png"), Path("/c.png")]
    emo = tag_emotion_multi(prov, paths, "末日废土")
    args, _kwargs = prov.generate.call_args
    images_arg = args[0]
    assert list(images_arg) == paths
    assert "末日废土" in args[2]
    assert emo.labels == ["tense", "focused"]
    assert emo.valence == -0.3


def test_tag_emotion_multi_empty_returns_neutral():
    """空帧列表 → _NEUTRAL，不调 provider。"""
    prov = MagicMock()
    emo = tag_emotion_multi(prov, [], "any")
    prov.generate.assert_not_called()
    assert emo.labels == []
    assert emo.valence == 0.0


def test_tag_emotion_multi_parse_failure_degrades_to_neutral():
    """模型返非 JSON → 降级 _NEUTRAL。"""
    prov = MagicMock()
    prov.generate.return_value = "not a json"
    emo = tag_emotion_multi(prov, [Path("/a.png")], "x")
    assert emo.labels == []
