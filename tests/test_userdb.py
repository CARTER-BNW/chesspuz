from pathlib import Path

import chess
import pytest

from chesspuz.run import RampSettings
from chesspuz.userdb import (
    ABANDONED,
    FINISHED,
    PRACTICE,
    QUIT,
    SCHEMA_VERSION,
    SURVIVAL,
    UserDB,
)
from tests import puzzles
from tests.test_run import FakeClock, FakePool


@pytest.fixture
def db(tmp_path: Path):
    with UserDB(tmp_path / "user.sqlite") as user_db:
        yield user_db


def play(run, uci: str) -> None:
    run.try_move(chess.Move.from_uci(uci))


def finished_run(db: UserDB, player_id: int, solves: int, clock: FakeClock, types=("Mate in 1",)):
    """Solve ``solves`` back-rank puzzles then fail three times; returns the run id."""
    run_id, run = db.new_run(player_id, types, FakePool([puzzles.BACK_RANK]).pick, clock=clock)
    for _ in range(solves):
        run.next_puzzle()
        clock.now += 1
        play(run, "e1e8")
    while not run.finished:
        run.next_puzzle()
        clock.now += 1
        play(run, "e1e7")
    db.finish_run(run_id, run)
    return run_id


def test_players_and_settings(db: UserDB) -> None:
    alice = db.get_or_create_player("  Alice ")
    assert alice.name == "Alice"
    assert db.get_or_create_player("Alice").id == alice.id
    bob = db.get_or_create_player("bob")
    assert [p.name for p in db.players()] == ["Alice", "bob"]
    assert db.player(bob.id) == bob and db.player(999) is None
    with pytest.raises(ValueError):
        db.get_or_create_player("   ")
    assert db.get_setting("start_rating") is None
    assert db.get_setting("start_rating", "600") == "600"
    db.set_setting("start_rating", "800")
    db.set_setting("start_rating", "900")
    assert db.get_setting("start_rating") == "900"


def test_a_full_run_is_persisted_as_it_happens(db: UserDB) -> None:
    clock = FakeClock()
    player = db.get_or_create_player("Alice")
    run_id, run = db.new_run(
        player.id, ["Mate in 1", "Fork"], FakePool([puzzles.BACK_RANK]).pick, clock=clock
    )
    assert db.run(run_id).status == "active"

    run.next_puzzle()
    clock.now += 2
    play(run, "e1e8")
    record = db.run(run_id)
    assert record.score == 1 and record.puzzles_played == 1 and record.total_ms == 2000
    assert record.max_rating_solved == 800
    assert db.seen_puzzle_ids(player.id) == {"backrank"}

    for _ in range(3):
        run.next_puzzle()
        clock.now += 1
        play(run, "e1e7")
    assert run.finished
    db.finish_run(run_id, run)

    record = db.run(run_id)
    assert record.status == FINISHED and record.scored
    assert record.score == 1 and record.lives_lost == 3 and record.puzzles_played == 4
    assert record.types == ("Fork", "Mate in 1") and record.player_name == "Alice"
    assert record.start_rating == 600 and record.step == 40 and record.ended_at is not None

    rows = db.run_puzzles(run_id)
    assert [r.seq for r in rows] == [1, 2, 3, 4]
    assert [r.solved for r in rows] == [True, False, False, False]
    assert rows[0].player_moves == ("e1e8",) and rows[1].player_moves == ("e1e7",)
    assert rows[0].puzzle.moves == puzzles.BACK_RANK.moves
    assert rows[0].puzzle.solver is chess.WHITE
    assert rows[0].types == {"Back Rank Mate", "Mate in 1"}
    assert [r.target_rating for r in rows] == [600, 640, 640, 640]

    stats = {s.type: s for s in db.type_stats(player.id)}
    assert (stats["Mate in 1"].attempts, stats["Mate in 1"].solved) == (4, 1)
    assert stats["Back Rank Mate"].accuracy == 0.25
    assert stats["Fork"].attempts == 0 and stats["Fork"].accuracy is None


def test_active_runs_become_abandoned_on_reopen(tmp_path: Path) -> None:
    path = tmp_path / "user.sqlite"
    with UserDB(path) as db:
        player = db.get_or_create_player("Alice")
        run_id, run = db.new_run(player.id, ["Mate in 1"], FakePool([puzzles.BACK_RANK]).pick)
        run.next_puzzle()
        play(run, "e1e8")
        # the app dies here: no finish_run
    with UserDB(path) as db:
        record = db.run(run_id)
        assert record.status == ABANDONED and not record.scored
        assert record.score == 1 and record.ended_at is not None
        assert db.leaderboard() == []
        assert [r.id for r in db.history(player.id)] == [run_id]
        assert db.seen_puzzle_ids(player.id) == {"backrank"}


def test_leaderboard_orders_by_score_then_time_and_filters_by_type_set(db: UserDB) -> None:
    clock = FakeClock()
    alice = db.get_or_create_player("Alice")
    bob = db.get_or_create_player("Bob")
    slow = finished_run(db, alice.id, solves=2, clock=clock)
    fast_clock = FakeClock()
    fast = finished_run(db, bob.id, solves=2, clock=fast_clock)
    # make Bob's run faster by shrinking its stored time
    db._db.execute("UPDATE runs SET total_ms = 1000 WHERE id = ?", (fast,))
    best = finished_run(db, alice.id, solves=3, clock=clock)
    other_types = finished_run(db, alice.id, solves=5, clock=clock, types=("Fork",))

    board = db.leaderboard(types=["Mate in 1"])
    assert [r.id for r in board] == [best, fast, slow]
    assert db.leaderboard(types=["Mate in 1"], player_id=bob.id)[0].id == fast
    assert [r.id for r in db.leaderboard()][0] == other_types  # no filter: all type sets
    assert db.leaderboard(types=["Mate in 1"], limit=1)[0].id == best
    assert db.best_score(alice.id, ["Mate in 1"]) == 3
    assert db.best_score(bob.id, ["Fork"]) == 0
    assert [r.id for r in db.history(alice.id)] == [other_types, best, slow]
    assert len(db.history()) == 4


def test_quitting_early_still_scores(db: UserDB) -> None:
    player = db.get_or_create_player("Alice")
    run_id, run = db.new_run(player.id, ["Mate in 1"], FakePool([puzzles.BACK_RANK]).pick)
    run.next_puzzle()
    play(run, "e1e8")
    run.next_puzzle()  # unfinished puzzle when quitting: not counted
    run.quit()
    db.finish_run(run_id, run)
    record = db.run(run_id)
    assert record.status == QUIT and record.scored and record.score == 1
    assert record.puzzles_played == 1 and record.lives_lost == 0
    assert db.leaderboard()[0].id == run_id


def test_alternate_mate_is_recorded(db: UserDB) -> None:
    player = db.get_or_create_player("Alice")
    run_id, run = db.new_run(player.id, ["Mate in 2"], FakePool([puzzles.TWO_ROOKS]).pick)
    run.next_puzzle()
    play(run, "h2h3")
    play(run, "b1b8")
    rows = db.run_puzzles(run_id)
    assert rows[0].solved and rows[0].alternate_mate
    assert rows[0].player_moves == ("h2h3", "g4e5", "b1b8")


def test_closed_database_raises(tmp_path: Path) -> None:
    db = UserDB(tmp_path / "x.sqlite")
    with pytest.raises(RuntimeError):
        db.players()
    db.open()
    db.open()  # idempotent
    db.close()
    db.close()
    assert RampSettings().start == 600


V1_SCHEMA = """
CREATE TABLE schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version VALUES (1);
CREATE TABLE players (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
CREATE TABLE runs (
    id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id),
    started_at TEXT NOT NULL, ended_at TEXT, status TEXT NOT NULL,
    score INTEGER NOT NULL DEFAULT 0, lives_lost INTEGER NOT NULL DEFAULT 0,
    types_json TEXT NOT NULL, start_rating INTEGER NOT NULL, step INTEGER NOT NULL,
    max_rating_solved INTEGER NOT NULL DEFAULT 0, total_ms INTEGER NOT NULL DEFAULT 0
);
INSERT INTO players VALUES (1, 'Old', '2026-09-01T10:00:00');
INSERT INTO runs (id, player_id, started_at, status, score, types_json, start_rating, step)
    VALUES (7, 1, '2026-09-01T10:00:00', 'finished', 4, '["Fork"]', 600, 40);
"""


def test_schema_v1_databases_are_migrated(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(V1_SCHEMA)
    conn.close()
    with UserDB(path) as db:
        assert db._db.execute("SELECT version FROM schema_version").fetchone()[0] == SCHEMA_VERSION
        record = db.run(7)
        assert record.mode == SURVIVAL and record.score == 4 and record.lives == 3
        assert db.leaderboard()[0].id == 7
    with UserDB(path) as db:  # opening again must not migrate twice
        assert db.run(7).mode == SURVIVAL and db.run(7).lives == 3


def test_practice_runs_stay_off_the_leaderboard_and_feed_the_mistakes_list(db: UserDB) -> None:
    clock = FakeClock()
    player = db.get_or_create_player("Alice")
    finished_run(db, player.id, solves=1, clock=clock)  # backrank failed three times
    mistakes = db.mistakes(player.id)
    assert [m.puzzle.id for m in mistakes] == ["backrank"]
    assert mistakes[0].times_failed == 3 and mistakes[0].still_wrong
    assert mistakes[0].last_practice is None and mistakes[0].puzzle.types == {
        "Back Rank Mate",
        "Mate in 1",
    }
    assert db.mistakes(999) == []

    run_id, run = db.new_practice(player.id, [m.puzzle for m in mistakes], clock=clock)
    assert run.practice and run.lives == 0
    run.next_puzzle()
    play(run, "e1e8")
    assert run.next_puzzle() is None and run.finished
    db.finish_run(run_id, run)
    record = db.run(run_id)
    assert record.mode == PRACTICE and record.status == FINISHED and not record.scored
    assert record.types == ("Back Rank Mate", "Mate in 1")
    assert [r.mode for r in db.history(player.id)] == [PRACTICE, SURVIVAL]
    assert all(r.mode == SURVIVAL for r in db.leaderboard())
    assert db.summary(player.id)["runs"] == 1 and db.type_sets() == [("Mate in 1",)]
    assert db.best_score(player.id, ["Back Rank Mate", "Mate in 1"]) == 0

    fixed = db.mistakes(player.id)
    assert fixed[0].last_practice == "solved" and not fixed[0].still_wrong

    run_id, run = db.new_practice(player.id, [fixed[0].puzzle])
    run.next_puzzle()
    play(run, "e1e7")
    run.reveal_solution()
    run.next_puzzle()
    db.finish_run(run_id, run)
    again = db.mistakes(player.id)
    assert again[0].last_practice == "failed" and again[0].still_wrong
