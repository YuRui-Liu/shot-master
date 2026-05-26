from pathlib import Path
from sound_track_agent.emotion_tagger import tag_emotion, _parse_emotion
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
