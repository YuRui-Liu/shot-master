"""Load images from a directory (non-recursive, supported formats only)."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from PIL import Image, UnidentifiedImageError


SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@dataclass
class ImageInfo:
    """Metadata for a loaded image (thumbnail generated lazily by UI)."""
    path: Path
    width: int
    height: int
    pixmap_thumbnail: Any = None  # QPixmap, lazy, set by UI layer


def load_directory(directory: Path) -> list[ImageInfo]:
    """Scan `directory` (non-recursive) for supported images.

    Returns ImageInfo list sorted by filename. Corrupt files are silently skipped.
    """
    if not directory.is_dir():
        return []

    results: list[ImageInfo] = []
    for entry in sorted(directory.iterdir(), key=lambda p: p.name):
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        try:
            with Image.open(entry) as img:
                img.verify()
            with Image.open(entry) as img:
                w, h = img.size
            results.append(ImageInfo(path=entry, width=w, height=h))
        except (UnidentifiedImageError, OSError):
            continue

    return results
