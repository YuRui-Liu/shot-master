"""Test fixtures and path setup."""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOT_MASTER = ROOT.parent.parent / "shot-master"
if SHOT_MASTER.exists() and str(SHOT_MASTER) not in sys.path:
    sys.path.insert(0, str(SHOT_MASTER))

# ---------------------------------------------------------------------------
# Stub missing third-party packages that are not installed in the test
# environment (no network access).  Only the names imported by
# drama_shot_master/providers/__init__.py and its siblings need to be present.
# We use a permissive stub module whose attribute access always succeeds so
# that `from openai import OpenAI` and similar imports don't raise.
# ---------------------------------------------------------------------------
class _PermissiveModule(types.ModuleType):
    """A module stub that returns a new _PermissiveModule for any attribute."""
    def __getattr__(self, name: str):  # type: ignore[override]
        child = _PermissiveModule(f"{self.__name__}.{name}")
        setattr(self, name, child)
        return child

    def __call__(self, *args, **kwargs):  # allow use as a class/function
        return self


def _stub(*names: str) -> None:
    for name in names:
        parts = name.split(".")
        for i in range(1, len(parts) + 1):
            pkg = ".".join(parts[:i])
            if pkg not in sys.modules:
                sys.modules[pkg] = _PermissiveModule(pkg)

_stub(
    "openai",
    "anthropic",
    "google",
    "google.genai",
    "dashscope",
)

# PySide6 is a heavy C-extension GUI library that is not available in the
# headless test environment.  Pure helpers in ui/widgets (e.g.
# _pick_tick_interval) are intentionally Qt-free and can be unit-tested if the
# surrounding module imports succeed.  Only stub PySide6 when it cannot be
# imported for real, so a developer machine with PySide6 installed still
# exercises the real Qt classes.
#
# Unlike the simple package stubs above, Qt names are used as base classes
# (``class SegmentItem(QGraphicsItem)``) and as descriptors (``Signal(...)``)
# at import time, so attribute access must yield a real ``type`` that is also
# callable.  ``_QtModule`` lazily fabricates such dummy classes on demand.
class _QtDummy:
    """Usable as a base class, instance, signal, and constant placeholder."""

    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return self

    def __getattr__(self, name):  # constants like Qt.LeftButton, etc.
        return _QtDummy()


class _QtModule(types.ModuleType):
    """Module stub whose attribute access returns dummy *classes*."""

    def __getattr__(self, name):  # type: ignore[override]
        cls = type(name, (_QtDummy,), {})
        setattr(self, name, cls)
        return cls


try:  # pragma: no cover - depends on environment
    import PySide6  # noqa: F401
except Exception:  # pragma: no cover - headless CI / sandbox
    for _qt_name in (
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    ):
        if _qt_name not in sys.modules:
            sys.modules[_qt_name] = _QtModule(_qt_name)
