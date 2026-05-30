"""directive_composer：对话 → 文本 LLM → 结构化配乐方向。"""
from sound_track_agent.session import SoundtrackDirective
from sound_track_agent.directive_composer import synthesize_directive


class _FakeProvider:
    """模拟 OpenAICompatProvider.generate(images, system_prompt, user_supplement)。"""
    def __init__(self, reply_text):
        self._reply = reply_text
        self.calls = []
    def generate(self, images, system_prompt, user_supplement):
        self.calls.append((list(images), system_prompt, user_supplement))
        return self._reply


def test_first_turn_produces_global_and_appends_conversation():
    p = _FakeProvider('{"global": "史诗管弦, 中速", "segments": {}, "reply": "已更新为史诗管弦"}')
    cur = SoundtrackDirective()
    out = synthesize_directive(p, cur, "史诗感电影配乐", n_segments=5)
    assert out.global_directive == "史诗管弦, 中速"
    assert out.conversation[-2] == {"role": "user", "text": "史诗感电影配乐"}
    assert out.conversation[-1] == {"role": "assistant", "text": "已更新为史诗管弦"}
    assert p.calls[0][0] == []


def test_correction_overrides_previous():
    p = _FakeProvider('{"global": "史诗管弦, 快速, 竹笛", "reply": "已加快并加竹笛"}')
    cur = SoundtrackDirective(global_directive="史诗管弦, 舒缓",
                              conversation=[{"role": "user", "text": "史诗感"},
                                            {"role": "assistant", "text": "ok"}])
    out = synthesize_directive(p, cur, "节奏再快点，加竹笛", n_segments=5)
    assert "快" in out.global_directive and "竹笛" in out.global_directive
    assert len(out.conversation) == 4


def test_segment_directives_parsed_as_int_keys():
    p = _FakeProvider('{"global": "管弦", "segments": {"1": "钢琴前奏"}, "reply": "ok"}')
    out = synthesize_directive(p, SoundtrackDirective(), "分段", n_segments=3)
    assert out.segment_directives == {1: "钢琴前奏"}


def test_invalid_json_keeps_old_global_no_crash():
    p = _FakeProvider("抱歉我无法生成 JSON")
    cur = SoundtrackDirective(global_directive="原有方向")
    out = synthesize_directive(p, cur, "随便说点", n_segments=2)
    assert out.global_directive == "原有方向"
    assert out.conversation[-2]["text"] == "随便说点"
    assert out.conversation[-1]["role"] == "assistant"


def test_json_embedded_in_text_is_extracted():
    p = _FakeProvider('好的~ {"global": "钢琴", "reply": "done"} 以上')
    out = synthesize_directive(p, SoundtrackDirective(), "钢琴风", n_segments=1)
    assert out.global_directive == "钢琴"
