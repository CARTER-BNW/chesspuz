"""Player data: players, runs, puzzles played, settings. SQLite in WAL mode; headless.

Crash safety: a run row is inserted with status ``active`` when the run starts, every finished
puzzle is committed immediately, and the run is finalised at the end. Any ``active`` run found on
the next open is marked ``abandoned`` (kept in history, excluded from leaderboards).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from chesspuz import themes
from chesspuz.puzzle import Puzzle
from chesspuz.run import PickFn, PuzzleResult, RampSettings, SurvivalRun

SCHEMA_VERSION = 1
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
    total_ms INTEGER NOT NULL DEFAULT 0
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

    @property
    def scored(self) -> bool:
        return self.status in SCORED_STATUSES


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

    def start_run(self, player_id: int, types: Collection[str], ramp: RampSettings) -> int:
        with self._db:
            cursor = self._db.execute(
                "INSERT INTO runs (player_id, started_at, status, types_json, start_rating, step)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (player_id, _now(), ACTIVE, _types_json(types), ramp.start, ramp.step),
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
        status = FINISHED if run.ended_by == "lives" else QUIT
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
    ) -> tuple[int, SurvivalRun]:
        """Start a persisted run: unseen puzzles are preferred and every result is saved."""
        ramp = ramp or RampSettings()
        run_id = self.start_run(player_id, types, ramp)
        kwargs = {} if clock is None else {"clock": clock}
        run = SurvivalRun(
            types,
            pick,
            ramp=ramp,
            seen=self.seen_puzzle_ids(player_id),
            on_result=lambda result: self.record_puzzle(run_id, result),
            **kwargs,
        )
        return run_id, run

    # -- queries -------------------------------------------------------------------------------

    _RUN_SELECT = (
        "SELECT r.*, p.name AS player_name,"
        " (SELECT COUNT(*) FROM run_puzzles rp WHERE rp.run_id = r.id) AS puzzles_played"
        " FROM runs r JOIN players p ON p.id = r.player_id"
    )

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
    ) -> list[RunRecord]:
        """Best scored runs: score desc, then less total time. ``types`` = exact type set."""
        where = [f"r.status IN ({','.join('?' * len(SCORED_STATUSES))})"]
        params: list[object] = list(SCORED_STATUSES)
        if types is not None:
            where.append("r.types_json = ?")
            params.append(_types_json(types))
        if player_id is not None:
            where.append("r.player_id = ?")
            params.append(player_id)
        params.append(limit)
        rows = self._db.execute(
            self._RUN_SELECT
            + " WHERE "
            + " AND ".join(where)
            + " ORDER BY r.score DESC, r.total_ms ASC, r.id ASC LIMIT ?",
            params,
        ).fetchall()
        return [_to_run(row) for row in rows]

    def best_score(self, player_id: int, types: Collection[str]) -> int:
        row = self._db.execute(
            "SELECT MAX(score) FROM runs WHERE player_id = ? AND types_json = ?"
            f" AND status IN ({','.join('?' * len(SCORED_STATUSES))})",
            (player_id, _types_json(types), *SCORED_STATUSES),
        ).fetchone()
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
    return RunRecord(
        id=row["id"],
        player_id=row["player_id"],
        player_name=row["player_name"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        status=row["status"],
        score=row["score"],
        lives_lost=row["lives_lost"],
        types=tuple(json.loads(row["types_json"])),
        start_rating=row["start_rating"],
        step=row["step"],
        max_rating_solved=row["max_rating_solved"],
        total_ms=row["total_ms"],
        puzzles_played=row["puzzles_played"],
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
