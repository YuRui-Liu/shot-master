from drama_shot_master.ui.nav_config import FUNCS, PHASES, ICONS


def test_funcs_has_seven_functions():
    keys = [key for _label, key in FUNCS]
    assert keys == ["split", "combine", "trim", "imggen",
                    "video_gen", "soundtrack", "dubbing"]


def test_phases_cover_all_func_keys_in_order():
    # 阶段内 key 顺序拼起来必须等于 FUNCS 的 key 顺序（流程式侧栏顺序契约）
    flat = [k for _title, keys in PHASES for k in keys]
    assert flat == [key for _label, key in FUNCS]


def test_phases_are_three_numbered_stages():
    titles = [title for title, _keys in PHASES]
    assert titles == ["① 素材准备", "② 分镜创作", "③ 视频出片"]


def test_funcs_keys_are_unique():
    keys = [key for _label, key in FUNCS]
    assert len(set(keys)) == len(keys)


def test_every_func_key_has_icon():
    assert set(ICONS) == {key for _label, key in FUNCS}


def test_icons_are_svg_filenames():
    assert all(v.endswith(".svg") for v in ICONS.values())


def test_icon_path_resolves_existing_files():
    from drama_shot_master.ui.nav_config import icon_path, ICON_SETTINGS, ICON_HELP
    for key in ICONS:
        p = icon_path(ICONS[key])
        assert p is not None and p.exists(), f"missing icon for {key}"
    assert icon_path(ICON_SETTINGS).exists()
    assert icon_path(ICON_HELP).exists()
