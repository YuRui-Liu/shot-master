from drama_shot_master.core import voice_presets as V


def test_defaults_structure():
    cats, note = V.load_presets()
    names = [n for n, _ in cats]
    assert names == ["方言", "人物身份", "场合", "情感语调"]
    counts = {n: len(items) for n, items in cats}
    assert counts == {"方言": 9, "人物身份": 8, "场合": 6, "情感语调": 8}
    # 每条 (label,text) 且非空
    for _n, items in cats:
        for label, text in items:
            assert label and text
    # 方言含湖南话
    dialects = dict(dict(cats)["方言"])
    assert "湖南话" in dialects and "长沙话" in dialects["湖南话"]
    assert note  # 方言提示非空


def test_load_custom_yaml(tmp_path):
    y = tmp_path / "p.yaml"
    y.write_text(
        "dialect_note: 自定义提示\n"
        "categories:\n"
        "  - name: 测试组\n"
        "    items:\n"
        "      - {label: A, text: 'aaa，'}\n"
        "      - {label: B, text: 'bbb，'}\n", encoding="utf-8")
    cats, note = V.load_presets(y)
    assert cats == [("测试组", [("A", "aaa，"), ("B", "bbb，")])]
    assert note == "自定义提示"


def test_missing_or_bad_yaml_falls_back(tmp_path):
    missing = tmp_path / "nope.yaml"
    assert V.load_presets(missing)[0] == V._DEFAULTS
    bad = tmp_path / "bad.yaml"
    bad.write_text("::: not valid yaml :::\n- [", encoding="utf-8")
    assert V.load_presets(bad)[0] == V._DEFAULTS


def test_skips_empty_items(tmp_path):
    y = tmp_path / "p.yaml"
    y.write_text(
        "categories:\n"
        "  - name: G\n"
        "    items:\n"
        "      - {label: ok, text: 'x，'}\n"
        "      - {label: '', text: 'y，'}\n"      # 跳过(label空)
        "      - {label: nostxt}\n", encoding="utf-8")           # 跳过(无text)
    cats, _ = V.load_presets(y)
    assert cats == [("G", [("ok", "x，")])]
