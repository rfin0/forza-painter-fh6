from __future__ import annotations

from pathlib import Path
import sys


SOURCE_DIR = Path(__file__).resolve().parent

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
    RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT)).resolve()
else:
    ROOT = SOURCE_DIR.parent
    RESOURCE_ROOT = ROOT
