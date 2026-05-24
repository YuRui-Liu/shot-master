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
# app/providers/__init__.py and its siblings need to be present.
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
