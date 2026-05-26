"""Save PIL images respecting format constraints (JPG cannot have alpha)."""
from pathlib import Path
from PIL import Image


def save_image(
    img: Image.Image,
    path: Path,
    output_format: str,
    bg: tuple[int, int, int] = (255, 255, 255),
) -> None:
    """Save `img` to `path`. Flatten alpha when output_format is JPG.

    Args:
        img: PIL image (any mode).
        path: Output path.
        output_format: 'PNG' or 'JPG' (case-insensitive).
        bg: RGB tuple used to flatten alpha when saving JPG.
    """
    fmt = output_format.upper()

    if fmt == "JPG":
        if img.mode in ("RGBA", "LA"):
            background = Image.new("RGB", img.size, bg)
            mask = img.split()[-1]
            rgb = img.convert("RGBA").convert("RGB") if img.mode == "LA" else img
            background.paste(rgb, mask=mask)
            background.save(path, "JPEG", quality=95)
        else:
            img.convert("RGB").save(path, "JPEG", quality=95)
    else:
        img.save(path, "PNG")
