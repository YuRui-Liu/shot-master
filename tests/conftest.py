"""Test fixtures and path setup."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOT_MASTER = ROOT.parent.parent / "shot-master"
if SHOT_MASTER.exists() and str(SHOT_MASTER) not in sys.path:
    sys.path.insert(0, str(SHOT_MASTER))
