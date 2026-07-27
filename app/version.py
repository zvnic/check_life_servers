from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
__version__ = VERSION_FILE.read_text(encoding="utf-8").strip()

if not __version__:
    raise RuntimeError("VERSION file is empty")

