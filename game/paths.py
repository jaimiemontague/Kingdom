"""Centralized path resolution for source and frozen (PyInstaller) modes."""
import os
import sys
from pathlib import Path


def get_project_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


PROJECT_ROOT = get_project_root()
ASSETS_DIR = PROJECT_ROOT / "assets"


def get_save_dir() -> Path:
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    else:
        base = Path.home() / '.local' / 'share'
    save_dir = base / 'KingdomSim' / 'saves'
    save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir
