"""Image splitting: locate cell boxes via white-band detection, then stitch sub_blocks.

主路：find_cell_boxes() 用 numpy 白带定位（与 scripts/split_16_to_4.py 一致），
fallback：uniform 等分（用 spec.margins.top + spec.gap 作为 outer/border 参数）。

切出 src_rows × src_cols 个 cell 后，按 sub_rows × sub_cols 把相邻 cell 紧贴拼接成
sub_block——拼接处无白边（每个 cell 都已经从白带间精确切出）。
"""
from PIL import Image
from .aspect_ops import center_crop_to_aspect, trim_white_edges
from .border_detector import find_cell_boxes
from .exceptions import (
    AspectCropError, CellTooSmallError, MarginsTooLargeError, SplitGridError,
)
from .specs import GridSpec


def split_image(src: Image.Image, spec: GridSpec) -> list[Image.Image]:
    """Split `src` according to `spec` and return a list of sub-images.

    Order: left-to-right then top-to-bottom (per sub_block 索引).

    Raises:
        SplitGridError:        sub_grid doesn't divide src_grid evenly.
        MarginsTooLargeError:  fallback uniform mode + margins consume entire image.
        CellTooSmallError:     computed cell dimension < 1 pixel.
        AspectCropError:       target_aspect crop yields an empty image.
    """
    if spec.src_rows % spec.sub_rows != 0 or spec.src_cols % spec.sub_cols != 0:
        raise SplitGridError(
            f"sub_grid {spec.sub_rows}x{spec.sub_cols} doesn't evenly divide "
            f"src_grid {spec.src_rows}x{spec.src_cols}"
        )

    # uniform fallback 用的 outer/border：取 margins.top / gap 作为代表
    # （bands 主路命中时这两个值不会被用到；fallback 命中时它们就是用户填的等分参数）
    uniform_outer = spec.margins.top
    uniform_border = spec.gap

    # 校验 uniform fallback 的极端情况
    if (uniform_outer * 2 + (spec.src_cols - 1) * uniform_border >= src.width
            or uniform_outer * 2 + (spec.src_rows - 1) * uniform_border >= src.height):
        # 注：此检查只防止极端不合理输入；bands 主路通常会命中
        if src.width - 2 * uniform_outer <= 0 or src.height - 2 * uniform_outer <= 0:
            raise MarginsTooLargeError(
                f"uniform fallback outer={uniform_outer} consumes entire image"
            )

    cell_boxes, _mode = find_cell_boxes(
        src, spec.src_rows, spec.src_cols,
        uniform_outer=uniform_outer,
        uniform_border=uniform_border,
    )

    # cell 尺寸合法性：<2px 的 cell 一定是噪声白带导致的退化结果，
    # 直接报清晰错误，避免下游 trim/resize 抛 "height and width must be > 0"
    for (l, t, r, b) in cell_boxes:
        if r - l < 2 or b - t < 2:
            raise CellTooSmallError(
                f"cell box invalid: ({l},{t},{r},{b})"
            )

    # 按 sub_rows × sub_cols 重组为 sub_blocks
    blocks_per_col = spec.src_rows // spec.sub_rows
    blocks_per_row = spec.src_cols // spec.sub_cols

    results: list[Image.Image] = []
    for br in range(blocks_per_col):
        for bc in range(blocks_per_row):
            cells_in_block: list[Image.Image] = []
            for ir in range(spec.sub_rows):
                for ic in range(spec.sub_cols):
                    r = br * spec.sub_rows + ir
                    c = bc * spec.sub_cols + ic
                    cells_in_block.append(src.crop(cell_boxes[r * spec.src_cols + c]))

            sub_block = _stitch_cells_tight(cells_in_block,
                                             spec.sub_rows, spec.sub_cols)

            # 兜底：去除任何残留白边（±1~2px rounding artifacts，或 cell box 不精确）
            sub_block = trim_white_edges(sub_block)

            if not spec.target_aspect.is_auto():
                sub_block = center_crop_to_aspect(sub_block, spec.target_aspect)
                if sub_block.width < 1 or sub_block.height < 1:
                    raise AspectCropError(
                        f"aspect crop yielded empty image: {sub_block.size}"
                    )
            results.append(sub_block)

    return results


def _stitch_cells_tight(cells: list[Image.Image],
                        n_rows: int, n_cols: int) -> Image.Image:
    """紧贴拼接 cells 成 n_rows×n_cols 网格。

    所有 cell 统一到第一个 cell 的尺寸（不一致时 LANCZOS resize）。
    输出无任何 gap/外边距，相邻 cell 像素紧贴。
    """
    target_w, target_h = cells[0].size
    norm: list[Image.Image] = []
    for c in cells:
        if c.size != (target_w, target_h):
            c = c.resize((target_w, target_h), Image.LANCZOS)
        norm.append(c)

    canvas = Image.new("RGB" if norm[0].mode == "RGB" else "RGBA",
                       (target_w * n_cols, target_h * n_rows))
    for i, c in enumerate(norm):
        r, col = divmod(i, n_cols)
        canvas.paste(c, (col * target_w, r * target_h))
    return canvas
