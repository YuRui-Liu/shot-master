from drama_shot_master.ui.nav_config import FUNCS, PHASES, ICONS


def test_funcs_has_eight_functions():
    # 不硬编码顺序（用户可重排）；只校验数量与键集合，顺序一致性由
    # test_phases_cover_all_func_keys_in_order 保证（FUNCS↔PHASES 同序）。
    keys = [key for _label, key in FUNCS]
    assert len(keys) == 9
    assert set(keys) == {"screenwriter", "split", "combine", "trim", "imggen",
                         "video_gen", "soundtrack", "dubbing", "compose"}


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


def test_screenwriter_in_funcs():
    from drama_shot_master.ui.nav_config import FUNCS
    keys = [k for _, k in FUNCS]
    assert "screenwriter" in keys
    # 应该是第一项（"剧本筹备"在前）
    assert keys[0] == "screenwriter"


def test_screenwriter_in_phases_drama_prep():
    # 扁平重构后：剧本创作 是 NAV_ITEMS 里 screenwriter 对应的显示名。
    from drama_shot_master.ui.nav_config import NAV_ITEMS
    labels = {key: label for label, key in NAV_ITEMS}
    assert labels.get("screenwriter") == "剧本创作"


def test_compose_tab_in_videopost_first():
    from drama_shot_master.ui import nav_config as nc
    keys = [k for k, _ in nc.VIDEOPOST_TABS]
    assert keys[0] == "compose"
    assert "compose" in [k for _l, k in nc.FUNCS]
    assert "compose" in nc.TASK_KEYS
    # compose 归入 production 门禁（与 video_gen 同阶段）
    assert "compose" in nc.PHASE_GATES and nc.PHASE_GATES["compose"] == "production"
