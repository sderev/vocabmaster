import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
# Ensure the local package sources are used when running tests.
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def fake_home(monkeypatch, tmp_path):
    """Provide an isolated HOME directory for tests that touch user storage."""
    home = tmp_path / "home"
    home.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)

    return home
