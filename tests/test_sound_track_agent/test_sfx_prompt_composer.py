"""sfx/prompt_composer._node_info：Stable Audio 3 workflow 4 节点参数映射。"""
from sound_track_agent.sfx.prompt_composer import _node_info


def test_node_info_returns_4_entries():
    info = _node_info("门吱呀", 3.0, 42)
    assert isinstance(info, list)
    assert len(info) == 4


def test_node_info_node_92_is_prompt():
    info = _node_info("门吱呀打开", 3.0, 1)
    n92 = [n for n in info if n["nodeId"] == "92"][0]
    assert n92["fieldName"] == "value"
    assert n92["fieldValue"] == "门吱呀打开"


def test_node_info_node_98_is_duration_float():
    info = _node_info("x", 5.5, 1)
    n98 = [n for n in info if n["nodeId"] == "98"][0]
    assert n98["fieldName"] == "value"
    assert isinstance(n98["fieldValue"], float)
    assert abs(n98["fieldValue"] - 5.5) < 1e-6


def test_node_info_node_108_is_sfx_mode_index_2():
    """SFX 模式：easy anythingIndexSwitch.index 固定 2。"""
    info = _node_info("x", 3.0, 1)
    n108 = [n for n in info if n["nodeId"] == "108"][0]
    assert n108["fieldName"] == "index"
    assert n108["fieldValue"] == 2


def test_node_info_node_84_is_seed_int():
    info = _node_info("x", 3.0, 42)
    n84 = [n for n in info if n["nodeId"] == "84"][0]
    assert n84["fieldName"] == "seed"
    assert isinstance(n84["fieldValue"], int)
    assert n84["fieldValue"] == 42
