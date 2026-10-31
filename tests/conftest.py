import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Every test gets its own data folder so nothing touches %APPDATA%."""
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setenv("PO_DATA_DIR", str(d))
    # Keep the real 1.x data on this machine out of the tests.
    from project_opener import constants as C
    monkeypatch.setattr(C, "legacy_v1_dir", lambda: tmp_path / "no-legacy")
    yield d


@pytest.fixture
def store(isolated_data_dir):
    from project_opener.core.store import WorkspaceStore
    return WorkspaceStore(isolated_data_dir)


@pytest.fixture
def hub_root(tmp_path):
    root = tmp_path / "hub"
    root.mkdir()
    return root
