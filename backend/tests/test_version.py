import json
from pathlib import Path

from app import __version__

ROOT = Path(__file__).resolve().parents[2]


def test_backend_and_frontend_versions_match():
    frontend = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))["version"]
    assert frontend == __version__


def test_changelog_has_current_version():
    assert f"## {__version__}" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
