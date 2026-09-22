"""Sound volumes, piece and square colours, played list and clearing stats (headless parts)."""

from pathlib import Path

import chess
import pytest

from chesspuz import sounds
from chesspuz.ui.board import BoardWidget
from chesspuz.ui.pieces import PieceCache, normalize_color
from chesspuz.userdb import PRACTICE, SURVIVAL, UserDB
from tests import puzzles
from tests.test_run import FakeClock
from tests.test_userdb import finished_run, play


def peak(data: bytes) -> int:
    return max(
        abs(int.from_bytes(data[i : i + 2], "little", signed=True))
        for i in range(44, len(data) - 1, 2)
    )


def test_clip_volume_scales_the_amplitude() -> None:
    full, half, silent = sounds.clip("move"), sounds.clip("move", 50), sounds.clip("move", 0)
    assert len(full) == len(half) == len(silent)
    assert abs(peak(half) - peak(full) / 2) <= 2
    assert peak(silent) == 0
    assert sounds.clip("move", 150) is full and sounds.clip("move", -5) is silent


def test_player_volumes_reach_the_backend_and_zero_is_skipped() -> None:
    played: list[tuple[str, int]] = []
    player = sounds.SoundPlayer(backend=lambda name, data: played.append((name, peak(data))))
    player.set_volume("click", 40)
    player.set_volume("wrong", 0)
    player.play("click")
    player.play("wrong")
    assert [name for name, _ in played] == ["click"]
    assert played[0][1] == peak(sounds.clip("click", 40))
    assert player.volumes["wrong"] == 0 and player.volumes["move"] == 100


def test_file_backend_rewrites_the_file_when_the_clip_changes(tmp_path: Path) -> None:
    backend = sounds.default_backend(tmp_path)
    backend("move", sounds.clip("move", 100))
    backend("move", sounds.clip("move", 30))
    if (tmp_path / "move.wav").exists():  # Windows only
        assert (tmp_path / "move.wav").read_bytes() == sounds.clip("move", 30)


def test_normalize_color() -> None:
    assert normalize_color("#ABCDEF", "#000000") == "#abcdef"
    assert normalize_color("#fa0", "#000000") == "#ffaa00"
    assert normalize_color("nonsense", "#123456") == "#123456"
    assert normalize_color("", "#123456") == "#123456"


def test_piece_colours_change_the_svg_and_the_pixmap(qapp) -> None:
    cache = PieceCache()
    king, knight = chess.Piece(chess.KING, chess.WHITE), chess.Piece(chess.KNIGHT, chess.BLACK)
    before = cache.pixmap(king, 48).toImage()
    black_before = cache.pixmap(knight, 48).toImage()
    assert cache.set_piece_colors("#ff0000", "#0000ff")
    assert not cache.set_piece_colors("#f00", "#00f")  # same colours, different spelling
    assert "#ff0000" in cache.svg(king) and "#fff" not in cache.svg(king)
    assert "#000" in cache.svg(king)  # outlines stay black on white pieces
    assert "#0000ff" in cache.svg(knight) and "#ececec" in cache.svg(knight)  # details stay
    assert cache.pixmap(king, 48).toImage() != before
    assert cache.pixmap(knight, 48).toImage() != black_before
    assert cache.set_piece_colors("#ffffff", "#000000")
    assert cache.pixmap(king, 48).toImage() == before


def test_board_square_colours(qtbot) -> None:
    board = BoardWidget(animation_ms=0, pieces=PieceCache())
    qtbot.addWidget(board)
    board.resize(400, 400)
    board.set_colors("#112233", "#445566")
    image = board.grab().toImage()
    e4 = board.square_rect(chess.E4).center().toPoint()
    d4 = board.square_rect(chess.D4).center().toPoint()
    assert image.pixelColor(e4).name() == "#112233"
    assert image.pixelColor(d4).name() == "#445566"


@pytest.fixture
def db(tmp_path: Path):
    with UserDB(tmp_path / "user.sqlite") as user_db:
        yield user_db


def test_played_puzzles_lists_every_attempt_newest_first(db: UserDB) -> None:
    clock = FakeClock()
    alice = db.get_or_create_player("Alice")
    bob = db.get_or_create_player("Bob")
    finished_run(db, alice.id, solves=1, clock=clock)  # 1 solved + 3 failed
    finished_run(db, bob.id, solves=2, clock=clock)
    run_id, run = db.new_practice(alice.id, [puzzles.BACK_RANK])
    run.next_puzzle()
    play(run, "e1e8")
    db.finish_run(run_id, run)

    played = db.played_puzzles(alice.id)
    assert len(played) == 5
    assert played[0].mode == PRACTICE and played[0].record.solved
    assert [p.record.solved for p in played[1:]] == [False, False, False, True]
    assert all(p.mode == SURVIVAL for p in played[1:])
    assert played[0].puzzle.id == "backrank" and played[0].played_at
    assert len(db.played_puzzles(alice.id, limit=2)) == 2
    assert db.played_puzzles(999) == []


def test_clear_runs_per_player_and_for_everyone(db: UserDB) -> None:
    clock = FakeClock()
    alice = db.get_or_create_player("Alice")
    bob = db.get_or_create_player("Bob")
    finished_run(db, alice.id, solves=1, clock=clock)
    finished_run(db, bob.id, solves=1, clock=clock)
    db.set_setting("sounds", "0")
    assert db.clear_runs(alice.id) == 1
    assert db.history(alice.id) == [] and db.mistakes(alice.id) == []
    assert len(db.history(bob.id)) == 1 and db.leaderboard()[0].player_name == "Bob"
    assert db.clear_runs() == 1
    assert db.history() == [] and db.summary()["runs"] == 0
    assert [p.name for p in db.players()] == ["Alice", "Bob"]  # players stay
    assert db.get_setting("sounds") == "0"  # settings stay
    assert db.clear_runs() == 0


def test_discard_run_if_empty(db: UserDB) -> None:
    alice = db.get_or_create_player("Alice")
    empty_id, _run = db.new_practice(alice.id, [puzzles.BACK_RANK])
    full_id, run = db.new_practice(alice.id, [puzzles.BACK_RANK])
    run.next_puzzle()
    play(run, "e1e8")
    assert db.discard_run_if_empty(empty_id) and db.run(empty_id) is None
    assert not db.discard_run_if_empty(full_id) and db.run(full_id) is not None
