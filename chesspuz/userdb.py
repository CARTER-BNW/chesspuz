"""Player data: players, runs, puzzles played, settings. SQLite in WAL mode; headless.

Crash safety: a run row is inserted with status ``active`` when the run starts, every finished
puzzle is committed immediately, and the run is finalised at the end. Any ``active`` run found on
the next open is marked ``abandoned`` (kept in history, excluded from leaderboards).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from chesspuz import themes
from chesspuz.puzzle import Puzzle
from chesspuz.run import (
    DEFAULT_LIVES,
    PickFn,
    PuzzleResult,
    RampSettings,
    SurvivalRun,
    queue_pick,
)

SCHEMA_VERSION = 3
SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES players(id),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    lives_lost INTEGER NOT NULL DEFAULT 0,
    types_json TEXT NOT NULL,
    start_rating INTEGER NOT NULL,
    step INTEGER NOT NULL,
    max_rating_solved INTEGER NOT NULL DEFAULT 0,
    total_ms INTEGER NOT NULL DEFAULT 0,
    mode TEXT NOT NULL DEFAULT 'survival',
    lives INTEGER NOT NULL DEFAULT 3
);
CREATE INDEX IF NOT EXISTS idx_runs_player ON runs(player_id, status);
CREATE TABLE IF NOT EXISTS run_puzzles (
    run_id INTEGER NOT NULL REFERENCES runs(id),
    seq INTEGER NOT NULL,
    puzzle_id TEXT NOT NULL,
    fen TEXT NOT NULL,
    moves TEXT NOT NULL,
    rating INTEGER NOT NULL,
    types_json TEXT NOT NULL,
    result TEXT NOT NULL,
    target_rating INTEGER NOT NULL,
    solve_ms INTEGER NOT NULL,
    player_moves TEXT NOT NULL,
    alternate_mate INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_run_puzzles_puzzle ON run_puzzles(puzzle_id);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

ACTIVE = "active"
FINISHED = "finished"  # ended by the third lost life
QUIT = "quit"  # ended early by the player; the score still counts
ABANDONED = "abandoned"  # app closed or crashed mid-run
SCORED_STATUSES = (FINISHED, QUIT)
SURVIVAL = "survival"
PRACTICE = "practice"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _types_json(types: Collection[str]) -> str:
    return json.dumps(sorted(set(types)))


@dataclass(frozen=True)
class Player:
    id: int
    name: str
    created_at: str


@dataclass(frozen=True)
class RunRecord:
    id: int
    player_id: int
    player_name: str
    started_at: str
    ended_at: str | None
    status: str
    score: int
    lives_lost: int
    types: tuple[str, ...]
    start_rating: int
    step: int
    max_rating_solved: int
    total_ms: int
    puzzles_played: int
    mode: str = SURVIVAL
    lives: int = DEFAULT_LIVES  # 0 for practice

    @property
    def scored(self) -> bool:
        return self.status in SCORED_STATUSES and self.mode == SURVIVAL


@dataclass(frozen=True)
class RunPuzzleRecord:
    run_id: int
    seq: int
    puzzle_id: str
    fen: str
    moves: tuple[str, ...]
    rating: int
    types: frozenset[str]
    result: str  # solved | failed
    target_rating: int
    solve_ms: int
    player_moves: tuple[str, ...]
    alternate_mate: bool

    @property
    def solved(self) -> bool:
        return self.result == "solved"

    @property
    def puzzle(self) -> Puzzle:
        return Puzzle(self.puzzle_id, self.fen, self.moves, self.rating, types=self.types)


@dataclass(frozen=True)
class Mistake:
    """A puzzle failed in Survival, with how practice went since."""

    puzzle: Puzzle
    times_failed: int
    last_failed_at: str
    last_practice: str | None  # "solved", "failed" or None when never practised

    @property
    def still_wrong(self) -> bool:
        return self.last_practice != "solved"


@dataclass(frozen=True)
class PlayedRecord:
    """One attempt at a puzzle, with the run it belonged to."""

    record: RunPuzzleRecord
    played_at: str
    mode: str

    @property
    def puzzle(self) -> Puzzle:
        return self.record.puzzle


@dataclass(frozen=True)
class TypeStats:
    type: str
    attempts: int
    solved: int

    @property
    def accuracy(self) -> float | None:
        return None if self.attempts == 0 else self.solved / self.attempts


class UserDB:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.conn: sqlite3.Connection | None = None

    # -- lifecycle -----------------------------------------------------------------------------

    def open(self) -> UserDB:
        if self.conn is not None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        with conn:
            conn.executescript(SCHEMA)
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
            elif row[0] < SCHEMA_VERSION:
                if row[0] < 2:
                    conn.execute(
                        "ALTER TABLE runs ADD COLUMN mode TEXT NOT NULL DEFAULT 'survival'"
                    )
                if row[0] < 3:  # every earlier run was played with three lives
                    conn.execute("ALTER TABLE runs ADD COLUMN lives INTEGER NOT NULL DEFAULT 3")
                conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
        self.conn = conn
        self.abandon_active_runs()
        return self

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self) -> UserDB:
        return self.open()

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def _db(self) -> sqlite3.Connection:
        if self.conn is None:
            raise RuntimeError("user database is not open")
        return self.conn

    # -- players and settings ------------------------------------------------------------------

    def players(self) -> list[Player]:
        rows = self._db.execute("SELECT * FROM players ORDER BY name COLLATE NOCASE").fetchall()
        return [Player(row["id"], row["name"], row["created_at"]) for row in rows]

    def player(self, player_id: int) -> Player | None:
        row = self._db.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
        return Player(row["id"], row["name"], row["created_at"]) if row else None

    def get_or_create_player(self, name: str) -> Player:
        name = name.strip()
        if not name:
            raise ValueError("player name must not be empty")
        row = self._db.execute("SELECT * FROM players WHERE name = ?", (name,)).fetchone()
        if row is None:
            with self._db:
                self._db.execute(
                    "INSERT INTO players (name, created_at) VALUES (?, ?)", (name, _now())
                )
            row = self._db.execute("SELECT * FROM players WHERE name = ?", (name,)).fetchone()
        return Player(row["id"], row["name"], row["created_at"])

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    # -- run lifecycle -------------------------------------------------------------------------

    def start_run(
        self,
        player_id: int,
        types: Collection[str],
        ramp: RampSettings,
        mode: str = SURVIVAL,
        lives: int = DEFAULT_LIVES,
    ) -> int:
        with self._db:
            cursor = self._db.execute(
                "INSERT INTO runs (player_id, started_at, status, types_json, start_rating, step,"
                " mode, lives) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    player_id,
                    _now(),
                    ACTIVE,
                    _types_json(types),
                    ramp.start,
                    ramp.step,
                    mode,
                    lives,
                ),
            )
        return int(cursor.lastrowid or 0)

    def record_puzzle(self, run_id: int, result: PuzzleResult) -> None:
        """Persist one finished puzzle and keep the run's running totals current."""
        puzzle = result.puzzle
        with self._db:
            self._db.execute(
                "INSERT INTO run_puzzles (run_id, seq, puzzle_id, fen, moves, rating, types_json,"
                " result, target_rating, solve_ms, player_moves, alternate_mate)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    result.seq,
                    puzzle.id,
                    puzzle.fen,
                    " ".join(puzzle.moves),
                    puzzle.rating,
                    _types_json(puzzle.types),
                    "solved" if result.solved else "failed",
                    result.target_rating,
                    result.solve_ms,
                    " ".join(result.player_moves),
                    int(result.alternate_mate),
                ),
            )
            self._db.execute(
                "UPDATE runs SET score = score + ?, lives_lost = lives_lost + ?,"
                " max_rating_solved = MAX(max_rating_solved, ?), total_ms = total_ms + ?"
                " WHERE id = ?",
                (
                    int(result.solved),
                    int(not result.solved),
                    puzzle.rating if result.solved else 0,
                    result.solve_ms,
                    run_id,
                ),
            )

    def finish_run(self, run_id: int, run: SurvivalRun) -> None:
        status = QUIT if run.ended_by == "quit" else FINISHED
        with self._db:
            self._db.execute(
                "UPDATE runs SET status = ?, ended_at = ?, score = ?, lives_lost = ?,"
                " max_rating_solved = ?, total_ms = ? WHERE id = ?",
                (
                    status,
                    _now(),
                    run.score,
                    run.lives - run.lives_left,
                    run.max_rating_solved,
                    run.total_ms,
                    run_id,
                ),
            )

    def abandon_active_runs(self) -> int:
        with self._db:
            cursor = self._db.execute(
                "UPDATE runs SET status = ?, ended_at = ? WHERE status = ?",
                (ABANDONED, _now(), ACTIVE),
            )
        return cursor.rowcount

    def new_run(
        self,
        player_id: int,
        types: Collection[str],
        pick: PickFn,
        ramp: RampSettings | None = None,
        clock: Callable[[], float] | None = None,
        mode: str = SURVIVAL,
        lives: int = DEFAULT_LIVES,
    ) -> tuple[int, SurvivalRun]:
        """Start a persisted run: unseen puzzles are preferred and every result is saved."""
        ramp = ramp or RampSettings()
        practice = mode == PRACTICE
        run_id = self.start_run(player_id, types, ramp, mode, lives=0 if practice else lives)
        kwargs = {} if clock is None else {"clock": clock}
        run = SurvivalRun(
            types,
            pick,
            ramp=ramp,
            lives=lives,
            seen=self.seen_puzzle_ids(player_id),
            on_result=lambda result: self.record_puzzle(run_id, result),
            practice=practice,
            **kwargs,
        )
        return run_id, run

    def new_practice(
        self,
        player_id: int,
        puzzles: Collection[Puzzle],
        clock: Callable[[], float] | None = None,
    ) -> tuple[int, SurvivalRun]:
        """A practice session over ``puzzles`` in order: no lives, saved with mode 'practice'."""
        types = sorted({t for puzzle in puzzles for t in puzzle.types})
        return self.new_run(player_id, types, queue_pick(puzzles), clock=clock, mode=PRACTICE)

    # -- queries -------------------------------------------------------------------------------

    _RUN_SELECT = (
        "SELECT r.*, p.name AS player_name,"
        " (SELECT COUNT(*) FROM run_puzzles rp WHERE rp.run_id = r.id) AS puzzles_played"
        " FROM runs r JOIN players p ON p.id = r.player_id"
    )
    # The same rows, scored as a run with fewer lives would have been: ``score_at`` is the
    # number of puzzles solved before the k-th mistake and ``time_at`` the time spent up to and
    # including it (first parameter: k - 1). A run that never lost k lives keeps its final
    # score. A 3-life run therefore also stands on the 1- and 2-life boards.
    _RUN_AT_SELECT = (
        "WITH cut AS (SELECT r.id AS run_id, (SELECT f.seq FROM run_puzzles f"
        " WHERE f.run_id = r.id AND f.result = 'failed' ORDER BY f.seq LIMIT 1 OFFSET ?)"
        " AS seq FROM runs r)"
        " SELECT r.*, p.name AS player_name,"
        " (SELECT COUNT(*) FROM run_puzzles rp WHERE rp.run_id = r.id) AS puzzles_played,"
        " (SELECT COUNT(*) FROM run_puzzles rp WHERE rp.run_id = r.id AND rp.result = 'solved'"
        " AND (cut.seq IS NULL OR rp.seq < cut.seq)) AS score_at,"
        " (SELECT COALESCE(SUM(rp.solve_ms), 0) FROM run_puzzles rp WHERE rp.run_id = r.id"
        " AND (cut.seq IS NULL OR rp.seq <= cut.seq)) AS time_at"
        " FROM runs r JOIN players p ON p.id = r.player_id JOIN cut ON cut.run_id = r.id"
    )

    @staticmethod
    def _scored_where(types: Collection[str] | None, player_id: int | None, lives: int | None):
        """WHERE clauses for scored Survival runs; ``lives`` keeps runs with at least that many."""
        where = [f"r.status IN ({','.join('?' * len(SCORED_STATUSES))})", "r.mode = ?"]
        params: list[object] = [*SCORED_STATUSES, SURVIVAL]
        if types is not None:
            where.append("r.types_json = ?")
            params.append(_types_json(types))
        if player_id is not None:
            where.append("r.player_id = ?")
            params.append(player_id)
        if lives is not None:
            where.append("r.lives >= ?")
            params.append(lives)
        return " WHERE " + " AND ".join(where), params

    def run(self, run_id: int) -> RunRecord | None:
        row = self._db.execute(self._RUN_SELECT + " WHERE r.id = ?", (run_id,)).fetchone()
        return _to_run(row) if row else None

    def run_puzzles(self, run_id: int) -> list[RunPuzzleRecord]:
        rows = self._db.execute(
            "SELECT * FROM run_puzzles WHERE run_id = ? ORDER BY seq", (run_id,)
        ).fetchall()
        return [_to_run_puzzle(row) for row in rows]

    def leaderboard(
        self,
        types: Collection[str] | None = None,
        player_id: int | None = None,
        limit: int = 20,
        lives: int | None = None,
    ) -> list[RunRecord]:
        """Best scored Survival runs: score desc, then less time. ``types`` = exact type set.

        With ``lives`` the board is the one for runs of that many lives: every run played with
        at least that many counts with the score it had when it lost its ``lives``-th life
        (see ``_RUN_AT_SELECT``); the records come back with that score and time.
        """
        where, params = self._scored_where(types, player_id, lives)
        if lives is None:
            sql = self._RUN_SELECT + where + " ORDER BY r.score DESC, r.total_ms ASC, r.id ASC"
        else:
            sql = self._RUN_AT_SELECT + where + " ORDER BY score_at DESC, time_at ASC, r.id ASC"
            params.insert(0, lives - 1)
        rows = self._db.execute(sql + " LIMIT ?", [*params, limit]).fetchall()
        return [_to_run(row) for row in rows]

    def best_score(self, player_id: int, types: Collection[str], lives: int | None = None) -> int:
        """Best score with exactly ``types``; with ``lives``, on the board for that many lives."""
        where, params = self._scored_where(types, player_id, lives)
        if lives is None:
            sql = "SELECT MAX(r.score) FROM runs r" + where
        else:
            sql = f"SELECT MAX(score_at) FROM ({self._RUN_AT_SELECT}{where})"
            params.insert(0, lives - 1)
        row = self._db.execute(sql, params).fetchone()
        return int(row[0] or 0)

    def history(self, player_id: int | None = None, limit: int = 100) -> list[RunRecord]:
        """Every run except active ones, newest first."""
        where = ["r.status != ?"]
        params: list[object] = [ACTIVE]
        if player_id is not None:
            where.append("r.player_id = ?")
            params.append(player_id)
        params.append(limit)
        rows = self._db.execute(
            self._RUN_SELECT + " WHERE " + " AND ".join(where) + " ORDER BY r.id DESC LIMIT ?",
            params,
        ).fetchall()
        return [_to_run(row) for row in rows]

    def type_sets(self) -> list[tuple[str, ...]]:
        """Distinct type selections used by scored runs, most used first."""
        rows = self._db.execute(
            "SELECT types_json, COUNT(*) AS n FROM runs"
            f" WHERE status IN ({','.join('?' * len(SCORED_STATUSES))}) AND mode = ?"
            " GROUP BY types_json ORDER BY n DESC, types_json",
            (*SCORED_STATUSES, SURVIVAL),
        ).fetchall()
        return [tuple(json.loads(row["types_json"])) for row in rows]

    def summary(self, player_id: int | None = None, lives: int | None = None) -> dict[str, float]:
        """Runs played, best and average score, puzzles attempted and solved.

        With ``lives`` the runs, best and average are those of the board for that many lives
        (runs with at least that many lives, scored at their ``lives``-th mistake); the puzzle
        counts cover every Survival puzzle regardless.
        """
        where, params = self._scored_where(None, player_id, lives)
        if lives is None:
            sql = (
                "SELECT COUNT(*) AS runs, COALESCE(MAX(r.score), 0) AS best,"
                " COALESCE(AVG(r.score), 0) AS avg FROM runs r" + where
            )
        else:
            sql = (
                "SELECT COUNT(*) AS runs, COALESCE(MAX(score_at), 0) AS best,"
                f" COALESCE(AVG(score_at), 0) AS avg FROM ({self._RUN_AT_SELECT}{where})"
            )
            params.insert(0, lives - 1)
        row = self._db.execute(sql, params).fetchone()
        puzzle_where = "r.mode = ?"
        puzzle_params: list[object] = [SURVIVAL]
        if player_id is not None:
            puzzle_where += " AND r.player_id = ?"
            puzzle_params.append(player_id)
        puzzles = self._db.execute(
            "SELECT COUNT(*) AS attempted,"
            " COALESCE(SUM(rp.result = 'solved'), 0) AS solved"
            f" FROM run_puzzles rp JOIN runs r ON r.id = rp.run_id WHERE {puzzle_where}",
            puzzle_params,
        ).fetchone()
        return {
            "runs": int(row["runs"]),
            "best_score": int(row["best"]),
            "average_score": float(row["avg"]),
            "attempted": int(puzzles["attempted"]),
            "solved": int(puzzles["solved"]),
        }

    def mistakes(self, player_id: int) -> list[Mistake]:
        """Puzzles failed in Survival: still-wrong ones first, then most recent failure first."""
        failed = self._db.execute(
            "SELECT rp.puzzle_id, rp.fen, rp.moves, rp.rating, rp.types_json,"
            " COUNT(*) AS times_failed, MAX(r.started_at) AS last_failed_at"
            " FROM run_puzzles rp JOIN runs r ON r.id = rp.run_id"
            " WHERE r.player_id = ? AND r.mode = ? AND rp.result = 'failed'"
            " GROUP BY rp.puzzle_id",
            (player_id, SURVIVAL),
        ).fetchall()
        practised = self._db.execute(
            "SELECT rp.puzzle_id, rp.result FROM run_puzzles rp JOIN runs r ON r.id = rp.run_id"
            " WHERE r.player_id = ? AND r.mode = ? ORDER BY r.id, rp.seq",
            (player_id, PRACTICE),
        ).fetchall()
        last_practice = {row["puzzle_id"]: row["result"] for row in practised}
        out = [
            Mistake(
                puzzle=Puzzle(
                    row["puzzle_id"],
                    row["fen"],
                    tuple(row["moves"].split()),
                    row["rating"],
                    types=frozenset(json.loads(row["types_json"])),
                ),
                times_failed=int(row["times_failed"]),
                last_failed_at=row["last_failed_at"],
                last_practice=last_practice.get(row["puzzle_id"]),
            )
            for row in failed
        ]
        out.sort(key=lambda m: m.last_failed_at, reverse=True)
        out.sort(key=lambda m: not m.still_wrong)  # stable: still-wrong first, newest first
        return out

    def best_streak(self, player_id: int | None = None) -> int:
        """Longest run of consecutive clean solves inside one Survival run, ever."""
        sql = (
            "SELECT rp.run_id, rp.result FROM run_puzzles rp JOIN runs r ON r.id = rp.run_id"
            " WHERE r.mode = ?"
        )
        params: list[object] = [SURVIVAL]
        if player_id is not None:
            sql += " AND r.player_id = ?"
            params.append(player_id)
        sql += " ORDER BY rp.run_id, rp.seq"
        best = current = 0
        last_run = None
        for row in self._db.execute(sql, params):
            if row["run_id"] != last_run:
                current = 0
                last_run = row["run_id"]
            current = current + 1 if row["result"] == "solved" else 0
            best = max(best, current)
        return best

    def played_puzzles(self, player_id: int, limit: int = 500) -> list[PlayedRecord]:
        """Every attempt by a player, newest first."""
        rows = self._db.execute(
            "SELECT rp.*, r.started_at AS played_at, r.mode AS mode"
            " FROM run_puzzles rp JOIN runs r ON r.id = rp.run_id"
            " WHERE r.player_id = ? ORDER BY r.id DESC, rp.seq DESC LIMIT ?",
            (player_id, limit),
        ).fetchall()
        return [PlayedRecord(_to_run_puzzle(row), row["played_at"], row["mode"]) for row in rows]

    # -- export / import (chesspuz/backup.py) ----------------------------------------------------

    def run_rows(self, player_id: int) -> list[dict]:
        """Every run of a player with its puzzles as plain dicts, oldest first."""
        runs = self._db.execute(
            "SELECT * FROM runs WHERE player_id = ? ORDER BY id", (player_id,)
        ).fetchall()
        out = []
        for row in runs:
            puzzles = self._db.execute(
                "SELECT * FROM run_puzzles WHERE run_id = ? ORDER BY seq", (row["id"],)
            ).fetchall()
            out.append(
                {
                    "started_at": row["started_at"],
                    "ended_at": row["ended_at"],
                    "status": row["status"],
                    "score": row["score"],
                    "lives_lost": row["lives_lost"],
                    "types": json.loads(row["types_json"]),
                    "start_rating": row["start_rating"],
                    "step": row["step"],
                    "max_rating_solved": row["max_rating_solved"],
                    "total_ms": row["total_ms"],
                    "mode": row["mode"],
                    "lives": row["lives"],
                    "puzzles": [
                        {
                            "seq": p["seq"],
                            "puzzle_id": p["puzzle_id"],
                            "fen": p["fen"],
                            "moves": p["moves"],
                            "rating": p["rating"],
                            "types": json.loads(p["types_json"]),
                            "result": p["result"],
                            "target_rating": p["target_rating"],
                            "solve_ms": p["solve_ms"],
                            "player_moves": p["player_moves"],
                            "alternate_mate": bool(p["alternate_mate"]),
                        }
                        for p in puzzles
                    ],
                }
            )
        return out

    def run_keys(self, player_id: int) -> set[tuple[str, str, int]]:
        """(start time, mode, puzzles played) of a player's runs: the duplicate test on import."""
        rows = self._db.execute(
            "SELECT r.started_at, r.mode,"
            " (SELECT COUNT(*) FROM run_puzzles rp WHERE rp.run_id = r.id) AS n"
            " FROM runs r WHERE r.player_id = ?",
            (player_id,),
        ).fetchall()
        return {(row["started_at"], row["mode"], int(row["n"])) for row in rows}

    def insert_run(
        self, player_id: int, run: Mapping[str, object], puzzles: Sequence[Mapping[str, object]]
    ) -> int:
        """Insert an ended run (dicts shaped like ``run_rows``) under a new id; returns it."""
        with self._db:
            cursor = self._db.execute(
                "INSERT INTO runs (player_id, started_at, ended_at, status, score, lives_lost,"
                " types_json, start_rating, step, max_rating_solved, total_ms, mode, lives)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    player_id,
                    run["started_at"],
                    run["ended_at"],
                    run["status"],
                    run["score"],
                    run["lives_lost"],
                    _types_json(run["types"]),  # type: ignore[arg-type]
                    run["start_rating"],
                    run["step"],
                    run["max_rating_solved"],
                    run["total_ms"],
                    run["mode"],
                    run["lives"],
                ),
            )
            run_id = int(cursor.lastrowid or 0)
            self._db.executemany(
                "INSERT INTO run_puzzles (run_id, seq, puzzle_id, fen, moves, rating, types_json,"
                " result, target_rating, solve_ms, player_moves, alternate_mate)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id,
                        p["seq"],
                        p["puzzle_id"],
                        p["fen"],
                        p["moves"],
                        p["rating"],
                        _types_json(p["types"]),  # type: ignore[arg-type]
                        p["result"],
                        p["target_rating"],
                        p["solve_ms"],
                        p["player_moves"],
                        int(bool(p["alternate_mate"])),
                    )
                    for p in puzzles
                ],
            )
        return run_id

    def settings_dict(self) -> dict[str, str]:
        rows = self._db.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def row_counts(self) -> tuple[int, int]:
        """(runs, puzzles played): a cheap way to notice that something was recorded."""
        runs = self._db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        puzzles = self._db.execute("SELECT COUNT(*) FROM run_puzzles").fetchone()[0]
        return int(runs), int(puzzles)

    def clear_runs(self, player_id: int | None = None) -> int:
        """Delete every run (and its puzzles) of a player, or of everyone; returns runs removed."""
        with self._db:
            if player_id is None:
                self._db.execute("DELETE FROM run_puzzles")
                cursor = self._db.execute("DELETE FROM runs")
            else:
                self._db.execute(
                    "DELETE FROM run_puzzles WHERE run_id IN"
                    " (SELECT id FROM runs WHERE player_id = ?)",
                    (player_id,),
                )
                cursor = self._db.execute("DELETE FROM runs WHERE player_id = ?", (player_id,))
        return cursor.rowcount

    def discard_run_if_empty(self, run_id: int) -> bool:
        """Remove a run that recorded no puzzles (e.g. a puzzle window closed untouched)."""
        with self._db:
            cursor = self._db.execute(
                "DELETE FROM runs WHERE id = ?"
                " AND NOT EXISTS (SELECT 1 FROM run_puzzles WHERE run_id = ?)",
                (run_id, run_id),
            )
        return cursor.rowcount > 0

    def seen_puzzle_ids(self, player_id: int) -> set[str]:
        rows = self._db.execute(
            "SELECT DISTINCT rp.puzzle_id FROM run_puzzles rp JOIN runs r ON r.id = rp.run_id"
            " WHERE r.player_id = ?",
            (player_id,),
        ).fetchall()
        return {row[0] for row in rows}

    def type_stats(self, player_id: int | None = None) -> list[TypeStats]:
        """Attempts and solves per chess.com type, in canonical order (like info.txt)."""
        sql = "SELECT rp.types_json, rp.result FROM run_puzzles rp"
        params: tuple[object, ...] = ()
        if player_id is not None:
            sql += " JOIN runs r ON r.id = rp.run_id WHERE r.player_id = ?"
            params = (player_id,)
        attempts = dict.fromkeys(themes.TYPES, 0)
        solved = dict.fromkeys(themes.TYPES, 0)
        for row in self._db.execute(sql, params):
            for name in json.loads(row["types_json"]):
                if name in attempts:
                    attempts[name] += 1
                    solved[name] += row["result"] == "solved"
        return [TypeStats(name, attempts[name], solved[name]) for name in themes.TYPES]


def _to_run(row: sqlite3.Row) -> RunRecord:
    keys = row.keys()
    at_board = "score_at" in keys  # scored as on the board for fewer lives
    return RunRecord(
        id=row["id"],
        player_id=row["player_id"],
        player_name=row["player_name"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        status=row["status"],
        score=row["score_at"] if at_board else row["score"],
        lives_lost=row["lives_lost"],
        types=tuple(json.loads(row["types_json"])),
        start_rating=row["start_rating"],
        step=row["step"],
        max_rating_solved=row["max_rating_solved"],
        total_ms=row["time_at"] if at_board else row["total_ms"],
        puzzles_played=row["puzzles_played"],
        mode=row["mode"],
        lives=row["lives"],
    )


def _to_run_puzzle(row: sqlite3.Row) -> RunPuzzleRecord:
    return RunPuzzleRecord(
        run_id=row["run_id"],
        seq=row["seq"],
        puzzle_id=row["puzzle_id"],
        fen=row["fen"],
        moves=tuple(row["moves"].split()),
        rating=row["rating"],
        types=frozenset(json.loads(row["types_json"])),
        result=row["result"],
        target_rating=row["target_rating"],
        solve_ms=row["solve_ms"],
        player_moves=tuple(row["player_moves"].split()),
        alternate_mate=bool(row["alternate_mate"]),
    )
