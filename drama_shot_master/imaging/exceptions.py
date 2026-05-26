"""Custom exceptions for image core operations."""


class SplitGridError(ValueError):
    """Raised when sub_grid doesn't evenly divide src_grid."""
    pass


class CombineCountError(ValueError):
    """Raised when image count doesn't match target grid R*C."""

    def __init__(self, expected: int, actual: int):
        self.expected = expected
        self.actual = actual
        super().__init__(f"Need {expected} images for grid, got {actual}")


class ImageLoadError(IOError):
    """Raised when an image file fails to load."""

    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to load {path}: {reason}")


class MarginsTooLargeError(ValueError):
    """Raised when margins consume the entire source image."""
    pass


class CellTooSmallError(ValueError):
    """Raised when computed cell dimension < 1 pixel."""
    pass


class AspectCropError(ValueError):
    """Raised when target_aspect crop yields an empty image."""
    pass
