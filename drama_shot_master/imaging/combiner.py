"""Image combining: arrange a list of images into a target grid with aspect/scale control."""
from PIL import Image
from .aspect_ops import fit_to_cell
from .exceptions import CombineCountError
from .specs import CombineSpec, ScaleMode


def combine_images(imgs: list[Image.Image], spec: CombineSpec,
                   bg: tuple[int, int, int, int]) -> Image.Image:
    """Combine `imgs` into a canvas described by `spec`.

    Raises:
        CombineCountError: When `len(imgs) != spec.target_rows * spec.target_cols`.
    """
    R, C = spec.target_rows, spec.target_cols
    if len(imgs) != R * C:
        raise CombineCountError(expected=R * C, actual=len(imgs))

    max_w = max(img.width for img in imgs)
    max_h = max(img.height for img in imgs)

    if spec.target_aspect.is_auto():
        cell_w, cell_h = max_w, max_h
    else:
        ratio = spec.target_aspect.value
        if max_w / max_h > ratio:
            cell_w = max_w
            cell_h = int(max_w / ratio)
        else:
            cell_h = max_h
            cell_w = int(max_h * ratio)

    canvas_w = C * cell_w + (C - 1) * spec.gap
    canvas_h = R * cell_h + (R - 1) * spec.gap
    canvas = Image.new("RGBA", (canvas_w, canvas_h), bg)

    for i, img in enumerate(imgs):
        r, c = divmod(i, C)
        if spec.target_aspect.is_auto():
            fitted = fit_to_cell(img, cell_w, cell_h, ScaleMode.LETTERBOX)
        else:
            fitted = fit_to_cell(img, cell_w, cell_h, spec.scale_mode)

        cell_x = c * (cell_w + spec.gap)
        cell_y = r * (cell_h + spec.gap)
        x = cell_x + (cell_w - fitted.width) // 2
        y = cell_y + (cell_h - fitted.height) // 2

        if fitted.mode == "RGBA":
            canvas.paste(fitted, (x, y), fitted)
        else:
            canvas.paste(fitted, (x, y))

    return canvas
