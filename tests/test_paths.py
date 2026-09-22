from pathlib import Path

from chesspuz import paths


def test_env_override_wins(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "custom"
    monkeypatch.setenv(paths.ENV_VAR, str(target))
    assert paths.data_dir() == target
    assert target.is_dir()
    assert paths.puzzle_db_path() == target / paths.PUZZLE_DB_NAME
    assert paths.user_db_path() == target / paths.USER_DB_NAME


def test_default_is_under_local_appdata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(paths.ENV_VAR, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(paths.os, "name", "nt")
    assert paths.data_dir(create=False) == tmp_path / "chesspuz"
