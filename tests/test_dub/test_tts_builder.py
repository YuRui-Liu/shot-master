from drama_shot_master.core import tts_profiles as P
from drama_shot_master.providers import tts_builder as B


def _kv(items):
    return {(i["nodeId"], i["fieldName"]): i["fieldValue"] for i in items}


def _no_bypasser(items):
    # 不再向 rgthree Fast Groups Bypasser(节点26)发任何项
    return all(i["nodeId"] != "26" for i in items)


def test_design_node_info():
    m = _kv(B.build_design_node_info("你好世界", "慵懒御姐音", "Auto", P.VOICE_DESIGN))
    assert m[("14", "text")] == "你好世界"
    assert m[("15", "text")] == "慵懒御姐音"
    assert m[("22", "language")] == "Auto"


def test_clone_mode1_default():
    items = B.build_clone_node_info(text="台词", mode=1, emo_alpha=1.0,
                                    speaker_file="openapi/spk.flac", prof=P.VOICE_CLONE)
    m = _kv(items)
    assert m[("4", "prompt")] == "台词"
    assert m[("10", "audio")] == "openapi/spk.flac"
    # 用 Switch 选分支：select=1（默认）；不再发 bypasser
    assert m[("27", "select")] == 1
    assert _no_bypasser(items)
    assert m[("1", "emo_alpha")] == 1.0
    # 模式1 无额外情感字段
    assert ("16", "prompt") not in m and ("19", "audio") not in m and ("21", "prompt") not in m


def test_clone_mode2_emo_text():
    items = B.build_clone_node_info(text="台词", mode=2, emo_alpha=0.8,
                                    emo_text="愤怒急促", speaker_file="openapi/spk.flac",
                                    prof=P.VOICE_CLONE)
    m = _kv(items)
    assert m[("27", "select")] == 2
    assert _no_bypasser(items)
    assert m[("16", "prompt")] == "愤怒急促"
    assert m[("14", "emo_alpha")] == 0.8


def test_clone_mode3_emo_audio():
    items = B.build_clone_node_info(text="台词", mode=3, emo_alpha=1.0,
                                    speaker_file="openapi/spk.flac",
                                    emo_audio_file="openapi/emo.flac", prof=P.VOICE_CLONE)
    m = _kv(items)
    assert m[("27", "select")] == 3
    assert _no_bypasser(items)
    assert m[("19", "audio")] == "openapi/emo.flac"
    assert m[("17", "emo_alpha")] == 1.0


def test_clone_mode4_emo_vector():
    items = B.build_clone_node_info(text="台词", mode=4, emo_alpha=1.0,
                                    emo_vector=[0, 0, 0, 0, 0, 0, 0.7, 0],
                                    speaker_file="openapi/spk.flac", prof=P.VOICE_CLONE)
    m = _kv(items)
    assert m[("27", "select")] == 4
    assert _no_bypasser(items)
    assert m[("21", "prompt")] == "[0, 0, 0, 0, 0, 0, 0.7, 0]"
    assert m[("20", "emo_alpha")] == 1.0


def test_clone_sampling_written_to_active_branch():
    items = B.build_clone_node_info(text="t", mode=1, emo_alpha=1.0,
                                    speaker_file="openapi/spk.flac",
                                    sampling={"temperature": 0.9, "top_k": 30},
                                    prof=P.VOICE_CLONE)
    m = _kv(items)
    assert m[("1", "temperature")] == 0.9
    assert m[("1", "top_k")] == 30
