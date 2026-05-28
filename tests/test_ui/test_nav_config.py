from drama_shot_master.ui.nav_config import FUNCS, PHASES, ICONS


def test_funcs_has_eight_functions():
    # 不硬编码顺序（用户可重排）；只校验数量与键集合，顺序一致性由
    # test_phases_cover_all_func_keys_in_order 保证（FUNCS↔PHASES 同序）。
    keys = [key for _label, key in FUNCS]
    assert len(keys) == 8
    assert set(keys) == {"screenwriter", "split", "combine", "trim", "imggen",
                         "video_gen", "soundtrack", "dubbing"}


def test_phases_cover_all_func_keys_in_order():
    # 阶段内 key 顺序拼起来必须等于 FUNCS 的 key 顺序（流程式侧栏顺序契约）
    flat = [k for _title, keys in PHASES for k in keys]
    assert flat == [key for _label, key in FUNCS]


def test_phases_are_four_numbered_stages():
    titles = [title for title, _keys in PHASES]
    assert titles == ["⓪ 剧本创作", "① 素材准备", "② 分镜创作", "③ 视频出片"]


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
    ps = icon_path(ICON_SETTINGS)
    ph = icon_path(ICON_HELP)
    assert ps is not None and ps.exists()
    assert ph is not None and ph.exists()
