import csv
from pathlib import Path

import pytest

import main as cli
from chesspuz import themes
from chesspuz.importer import (
    CSV_COLUMNS,
    ImportSettings,
    download,
    import_puzzles,
    make_sample,
)
from chesspuz.puzzle import Puzzle
from chesspuz.puzzledb import PuzzleRepository
from tests import puzzles


def row(p: Puzzle, **overrides) -> dict[str, str]:
    values = {
        "PuzzleId": p.id,
        "FEN": p.fen,
        "Moves": " ".join(p.moves),
        "Rating": str(p.rating),
        "RatingDeviation": "75",
        "Popularity": "90",
        "NbPlays": "1000",
        "Themes": " ".join(sorted(p.themes)),
        "GameUrl": "https://lichess.org/abc",
        "OpeningTags": "",
    }
    values.update({k: str(v) for k, v in overrides.items()})
    return values


def write_csv(path: Path, rows: list[dict[str, str]], extra_column: bool = False) -> Path:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([*CSV_COLUMNS, "DailyDate"] if extra_column else CSV_COLUMNS)
        for r in rows:
            values = [r[c] for c in CSV_COLUMNS]
            writer.writerow([*values, ""] if extra_column else values)
    return path


@pytest.fixture
def handmade_csv(tmp_path: Path) -> Path:
    rows = [row(p) for p in puzzles.ALL]
    rows += [
        row(puzzles.BACK_RANK, PuzzleId="lowplays", NbPlays="5"),
        row(puzzles.BACK_RANK, PuzzleId="unpopular", Popularity="10"),
        row(puzzles.BACK_RANK, PuzzleId="vague", RatingDeviation="300"),
        row(puzzles.BACK_RANK, PuzzleId="toohard", Rating="3200"),
        row(puzzles.BACK_RANK, PuzzleId="broken", Moves="a5a4 e1d2"),
        row(puzzles.BACK_RANK, PuzzleId="notype", Themes="crushing long"),
    ]
    return write_csv(tmp_path / "handmade.csv", rows, extra_column=True)


def test_import_filters_derives_types_and_reports(handmade_csv: Path, tmp_path: Path) -> None:
    db = tmp_path / "puzzles.sqlite"
    stages: list[str] = []
    report = import_puzzles(handmade_csv, db, progress=lambda p: stages.append(p.stage))
    assert report.rows_read == len(puzzles.ALL) + 6
    # EN_PASSANT and CASTLE carry no chess.com type and are dropped
    assert report.rows_kept == len(puzzles.ALL) - 2
    assert report.rows_rejected == 1  # "broken"
    assert report.rows_filtered == report.rows_kept
    assert stages[-1] == "done" and "write" in stages and "index" in stages
    assert report.type_counts["Queen Sacrifice"] == 1
    assert report.type_counts["Scholar's Mate"] == 1
    assert report.type_counts["Opposition"] == 1

    with PuzzleRepository(db) as repo:
        assert repo.count() == report.rows_kept
        assert repo.counts_by_type()["Mate in 1"] == 2  # BACK_RANK and SCHOLAR
        assert repo.counts_by_type()["Fork"] == 0
        assert repo.theme_counts()["mateIn1"] == 2
        assert repo.meta()["rows_read"] == str(report.rows_read)
        smothered = repo.get("smothered")
        assert smothered is not None
        assert smothered.types == {"Sacrifice", "Mating Net", "Mate in 2", "Queen Sacrifice"}
        assert smothered.moves == puzzles.SMOTHERED.moves
        assert smothered.solver == puzzles.SMOTHERED.solver
        assert repo.get("lowplays") is None and repo.get("broken") is None
        assert repo.get("enpassant") is None


def test_cap_keeps_the_most_popular_per_bucket_and_type_but_all_rare_types(tmp_path) -> None:
    rows = [
        row(puzzles.BACK_RANK, PuzzleId=f"br{i}", Rating=str(800 + i), Popularity=str(60 + i))
        for i in range(6)
    ]
    rows.append(row(puzzles.UNDER_PROMOTION, PuzzleId="up1", Rating="810", Popularity="55"))
    rows.append(row(puzzles.UNDER_PROMOTION, PuzzleId="up2", Rating="812", Popularity="56"))
    rows.append(row(puzzles.SCHOLAR, PuzzleId="sch", Rating="805", Popularity="50"))
    csv_path = write_csv(tmp_path / "cap.csv", rows)
    db = tmp_path / "cap.sqlite"
    settings = ImportSettings(per_bucket_type=2)
    report = import_puzzles(csv_path, db, settings)
    with PuzzleRepository(db) as repo:
        ids = {repo.get(f"br{i}") is not None for i in range(6)}
        kept_backrank = [f"br{i}" for i in range(6) if repo.get(f"br{i}") is not None]
        assert kept_backrank == ["br4", "br5"], ids  # two most popular in the 800 bucket
        assert repo.get("up1") is not None and repo.get("up2") is not None
        assert repo.get("sch") is not None  # alone in its own (bucket, type) heap
        assert repo.count() == 5
    assert report.rows_kept == 5

    everything = import_puzzles(
        csv_path, tmp_path / "all.sqlite", ImportSettings(per_bucket_type=0)
    )
    assert everything.rows_kept == 9


def test_zst_input_gives_the_same_database(handmade_csv: Path, tmp_path: Path) -> None:
    zstandard = pytest.importorskip("zstandard")
    zst = tmp_path / "handmade.csv.zst"
    zst.write_bytes(zstandard.ZstdCompressor().compress(handmade_csv.read_bytes()))
    plain = import_puzzles(handmade_csv, tmp_path / "a.sqlite")
    packed = import_puzzles(zst, tmp_path / "b.sqlite")
    assert packed.rows_kept == plain.rows_kept == len(puzzles.ALL) - 2


def test_pick_respects_window_types_and_exclusions(handmade_csv: Path, tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    import_puzzles(handmade_csv, db)
    with PuzzleRepository(db) as repo:
        found = repo.pick(700, 900, ["Mate in 1"])
        assert found is not None and found.id == "backrank"
        assert repo.pick(700, 900, ["Mate in 1"], exclude=frozenset({"backrank"})) is None
        assert repo.pick(0, 9999, ["Mate in 1"], exclude=frozenset({"backrank"})).id == "scholar"
        assert repo.pick(700, 900, ["Fork"]) is None
        assert repo.pick(700, 900, []) is None
        assert repo.pick(700, 900, ["Not A Type"]) is None
        ids = {repo.pick(0, 9999, themes.TYPES).id for _ in range(40)}
        assert len(ids) > 1  # random choice over the whole set


def test_import_replaces_an_existing_database_atomically(handmade_csv: Path, tmp_path) -> None:
    db = tmp_path / "puzzles.sqlite"
    import_puzzles(handmade_csv, db)
    with PuzzleRepository(db) as repo:
        before = repo.count()
    small = write_csv(tmp_path / "one.csv", [row(puzzles.BACK_RANK)])
    import_puzzles(small, db)
    with PuzzleRepository(db) as repo:
        assert repo.count() == 1 < before
    assert not (tmp_path / "puzzles.sqlite.tmp").exists()


def test_make_sample_roundtrips_through_the_importer(handmade_csv: Path, tmp_path) -> None:
    db = tmp_path / "puzzles.sqlite"
    import_puzzles(handmade_csv, db)
    out = tmp_path / "sample.csv"
    written = make_sample(db, out, per_type=1)
    assert 1 <= written <= len(puzzles.ALL)
    again = import_puzzles(out, tmp_path / "again.sqlite")
    assert again.rows_kept == written


def test_download_streams_through_a_part_file(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"x" * 3_000_000)
    dest = tmp_path / "out" / "file.bin"
    seen: list[int] = []
    download(src.as_uri(), dest, progress=lambda p: seen.append(p.done))
    assert dest.read_bytes() == src.read_bytes()
    assert not dest.with_name("file.bin.part").exists()
    assert seen and seen[-1] == 3_000_000


def test_cli_import_stats_and_sample(handmade_csv: Path, tmp_path: Path, capsys) -> None:
    db = tmp_path / "cli.sqlite"
    assert cli.main(["import", str(handmade_csv), "--db", str(db)]) == 0
    assert cli.main(["stats", "--db", str(db), "--themes"]) == 0
    out = capsys.readouterr().out
    assert "Mate in 1" in out and "mateIn1" in out
    assert cli.main(["sample", "--db", str(db), "--out", str(tmp_path / "s.csv")]) == 0
    assert (tmp_path / "s.csv").exists()
    assert cli.main(["stats", "--db", str(tmp_path / "missing.sqlite")]) == 1
    assert cli.main(["import", "--db", str(db)]) == 2


def test_repository_errors_when_the_file_is_missing(tmp_path: Path) -> None:
    repo = PuzzleRepository(tmp_path / "nope.sqlite")
    assert not PuzzleRepository.is_available(repo.path)
    with pytest.raises(FileNotFoundError):
        repo.open()
    with pytest.raises(RuntimeError):
        repo.count()
