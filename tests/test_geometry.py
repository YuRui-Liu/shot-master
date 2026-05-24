import pytest
from drama_shot_master.ui.geometry import compute_grid_lines, GridLine


def test_simple_2x2_no_sub_no_margin():
    lines = compute_grid_lines(
        img_w=400, img_h=400,
        src_rows=2, src_cols=2, sub_rows=1, sub_cols=1,
        margin_top=0, margin_right=0, margin_bottom=0, margin_left=0,
        gap=0, display_w=400, display_h=400,
    )
    solids = [l for l in lines if l.style == "solid"]
    assert any(l.orientation == "v" and abs(l.pos - 200) < 1 for l in solids)
    assert any(l.orientation == "h" and abs(l.pos - 200) < 1 for l in solids)


def test_scaled_display_halves_positions():
    lines = compute_grid_lines(
        img_w=400, img_h=400,
        src_rows=2, src_cols=2, sub_rows=1, sub_cols=1,
        margin_top=0, margin_right=0, margin_bottom=0, margin_left=0,
        gap=0, display_w=200, display_h=200,
    )
    solids = [l for l in lines if l.style == "solid"]
    assert any(l.orientation == "v" and abs(l.pos - 100) < 1 for l in solids)


def test_margins_offset_grid():
    lines = compute_grid_lines(
        img_w=420, img_h=400,
        src_rows=1, src_cols=2, sub_rows=1, sub_cols=1,
        margin_top=0, margin_right=0, margin_bottom=0, margin_left=20,
        gap=0, display_w=420, display_h=400,
    )
    solids = [l for l in lines if l.style == "solid" and l.orientation == "v"]
    assert any(abs(l.pos - 220) < 2 for l in solids)


def test_sub_grid_produces_dashed_lines():
    lines = compute_grid_lines(
        img_w=400, img_h=400,
        src_rows=4, src_cols=4, sub_rows=2, sub_cols=2,
        margin_top=0, margin_right=0, margin_bottom=0, margin_left=0,
        gap=0, display_w=400, display_h=400,
    )
    dashed = [l for l in lines if l.style == "dashed"]
    assert any(l.orientation == "v" and abs(l.pos - 200) < 1 for l in dashed)
    assert any(l.orientation == "h" and abs(l.pos - 200) < 1 for l in dashed)


def test_tile_count_helper():
    from drama_shot_master.ui.geometry import tile_count
    assert tile_count(4, 4, 2, 2) == 4
    assert tile_count(2, 2, 1, 1) == 4
    assert tile_count(1, 3, 1, 1) == 3


def test_invalid_grid_raises():
    with pytest.raises(ValueError):
        compute_grid_lines(
            img_w=400, img_h=400,
            src_rows=3, src_cols=3, sub_rows=2, sub_cols=2,
            margin_top=0, margin_right=0, margin_bottom=0, margin_left=0,
            gap=0, display_w=400, display_h=400,
        )
