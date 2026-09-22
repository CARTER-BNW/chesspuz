"""Build the local puzzle database from the Lichess puzzle CSV. Headless; no Qt.

Pipeline: (optionally download the ``.zst``) -> stream rows -> quality filter -> chess.com types
(direct + derived) -> keep the most popular ``per_bucket_type`` puzzles per (50-point rating
bucket, type) using bounded heaps, plus every puzzle of a rare type -> validate the kept lines by
replaying them -> write a fresh SQLite file in one transaction -> build indexes -> atomically
replace the old database.

Progress is reported through a callback and the work can be cancelled through another, so a GUI
worker thread can drive it without this module knowing anything about Qt.
"""

from __future__ import annotations

import csv
import heapq
import io
import itertools
import json
import os
import sqlite3
import time
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

from chesspuz import themes
from chesspuz.puzzle import InvalidPuzzle, Puzzle, split_themes

LICHESS_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
CSV_COLUMNS = (
    "PuzzleId",
    "FEN",
    "Moves",
    "Rating",
    "RatingDeviation",
    "Popularity",
    "NbPlays",
    "Themes",
    "GameUrl",
    "OpeningTags",
)
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE puzzles (
    id TEXT PRIMARY KEY,
    fen TEXT NOT NULL,
    moves TEXT NOT NULL,
    rating INTEGER NOT NULL,
    deviation INTEGER NOT NULL,
    popularity INTEGER NOT NULL,
    nb_plays INTEGER NOT NULL,
    themes TEXT NOT NULL,
    types TEXT NOT NULL
);
CREATE TABLE puzzle_types (puzzle_id TEXT NOT NULL, type TEXT NOT NULL);
CREATE TABLE theme_counts (
    kind TEXT NOT NULL, name TEXT NOT NULL, count INTEGER NOT NULL, PRIMARY KEY (kind, name)
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
INDEXES = """
CREATE INDEX idx_puzzles_rating ON puzzles(rating);
CREATE INDEX idx_types_type ON puzzle_types(type, puzzle_id);
CREATE INDEX idx_types_puzzle ON puzzle_types(puzzle_id, type);
"""


class Cancelled(Exception):
    """Raised when the cancel callback asked the import to stop."""


@dataclass(frozen=True)
class ImportSettings:
    min_plays: int = 30
    min_popularity: int = 50
    max_deviation: int = 100
    min_rating: int = 400
    max_rating: int = 3000
    bucket_size: int = 50
    per_bucket_type: int = 500  # 0 keeps every puzzle that passes the quality filter


@dataclass
class Progress:
    stage: str  # download | scan | validate | write | index | done
    done: int
    total: int | None = None
    message: str = ""


@dataclass
class ImportReport:
    source: str = ""
    rows_read: int = 0
    rows_filtered: int = 0  # passed the quality filter and have at least one type
    rows_kept: int = 0  # written to the database
    rows_rejected: int = 0  # illegal or unparsable lines
    seconds: float = 0.0
    type_counts: dict[str, int] = field(default_factory=dict)
    db_path: str = ""


ProgressFn = Callable[[Progress], None]
CancelFn = Callable[[], bool]


@dataclass(slots=True)
class Candidate:
    id: str
    fen: str
    moves: str
    rating: int
    deviation: int
    popularity: int
    nb_plays: int
    themes: str
    types: frozenset[str]


# -- download ------------------------------------------------------------------------------------


def download(
    url: str,
    dest: Path,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
    timeout: float = 60,
) -> Path:
    """Stream ``url`` to ``dest`` via a ``.part`` file so a broken download never looks complete."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "chesspuz/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response, open(part, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0) or None
        done = 0
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress is not None:
                progress(Progress("download", done, total))
            if should_cancel is not None and should_cancel():
                raise Cancelled("download cancelled")
    os.replace(part, dest)
    return dest


# -- reading -------------------------------------------------------------------------------------


def open_text(path: Path) -> io.TextIOBase:
    """Open a ``.csv`` or a zstd-compressed ``.csv.zst`` as text."""
    if path.suffix == ".zst":
        import zstandard

        handle = open(path, "rb")
        reader = zstandard.ZstdDecompressor().stream_reader(handle, read_across_frames=True)
        return io.TextIOWrapper(reader, encoding="utf-8", newline="")
    return open(path, encoding="utf-8", newline="")


def iter_rows(text: io.TextIOBase) -> Iterator[dict[str, str]]:
    """Yield rows keyed by the Lichess column names; extra columns (DailyDate) are ignored."""
    reader = csv.reader(text)
    header = next(reader, None)
    if header is None or header[: len(CSV_COLUMNS)] != list(CSV_COLUMNS):
        raise ValueError(f"unexpected CSV header: {header!r}")
    width = len(CSV_COLUMNS)
    for row in reader:
        if len(row) < width:
            continue
        yield dict(zip(CSV_COLUMNS, row, strict=False))


# -- selection -----------------------------------------------------------------------------------


def _int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def scan(
    source: Path,
    settings: ImportSettings,
    report: ImportReport,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> dict[str, Candidate]:
    """Read every row once and return the puzzles to keep, keyed by id."""
    heaps: dict[tuple[int, str], list[tuple[int, int, int, Candidate]]] = {}
    keep_all: dict[str, Candidate] = {}
    rare: dict[str, Candidate] = {}
    order = itertools.count()
    cap = settings.per_bucket_type
    with open_text(source) as text:
        for row in iter_rows(text):
            report.rows_read += 1
            if report.rows_read % 100_000 == 0:
                if progress is not None:
                    progress(Progress("scan", report.rows_read, None, f"{len(rare)} rare kept"))
                if should_cancel is not None and should_cancel():
                    raise Cancelled("import cancelled")
            rating = _int(row["Rating"])
            if not settings.min_rating <= rating <= settings.max_rating:
                continue
            nb_plays = _int(row["NbPlays"])
            popularity = _int(row["Popularity"])
            deviation = _int(row["RatingDeviation"])
            if (
                nb_plays < settings.min_plays
                or popularity < settings.min_popularity
                or deviation > settings.max_deviation
            ):
                continue
            theme_set = split_themes(row["Themes"])
            moves = row["Moves"].split()
            try:
                types = themes.types_for(row["FEN"], moves, theme_set)
            except ValueError:
                report.rows_rejected += 1
                continue
            if not types:
                continue
            report.rows_filtered += 1
            candidate = Candidate(
                id=row["PuzzleId"],
                fen=row["FEN"],
                moves=" ".join(moves),
                rating=rating,
                deviation=deviation,
                popularity=popularity,
                nb_plays=nb_plays,
                themes=" ".join(sorted(theme_set)),
                types=types,
            )
            if cap <= 0:
                keep_all[candidate.id] = candidate
                continue
            if types & themes.RARE_TYPES:
                rare[candidate.id] = candidate
            bucket = rating // settings.bucket_size
            entry = (popularity, nb_plays, next(order), candidate)
            for type_name in types:
                heap = heaps.setdefault((bucket, type_name), [])
                if len(heap) < cap:
                    heapq.heappush(heap, entry)
                elif entry[:2] > heap[0][:2]:
                    heapq.heapreplace(heap, entry)
    if cap <= 0:
        return keep_all
    kept: dict[str, Candidate] = {}
    for heap in heaps.values():
        for entry in heap:
            kept[entry[3].id] = entry[3]
    kept.update(rare)
    return kept


# -- writing -------------------------------------------------------------------------------------


def write_db(
    kept: dict[str, Candidate],
    db_path: Path,
    settings: ImportSettings,
    report: ImportReport,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> None:
    """Validate the kept lines and write a fresh database, then swap it into place."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_name(db_path.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(tmp)
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.executescript(SCHEMA)
        theme_counter: Counter[str] = Counter()
        type_counter: Counter[str] = Counter()
        rows: list[tuple] = []
        type_rows: list[tuple[str, str]] = []
        total = len(kept)
        for index, cand in enumerate(kept.values(), start=1):
            try:
                Puzzle(cand.id, cand.fen, tuple(cand.moves.split()), cand.rating).validate()
            except InvalidPuzzle:
                report.rows_rejected += 1
                continue
            types_sorted = sorted(cand.types)
            rows.append(
                (
                    cand.id,
                    cand.fen,
                    cand.moves,
                    cand.rating,
                    cand.deviation,
                    cand.popularity,
                    cand.nb_plays,
                    cand.themes,
                    "|".join(types_sorted),
                )
            )
            type_rows.extend((cand.id, t) for t in types_sorted)
            theme_counter.update(cand.themes.split())
            type_counter.update(types_sorted)
            report.rows_kept += 1
            if len(rows) >= 5000 or index == total:
                conn.executemany("INSERT INTO puzzles VALUES (?,?,?,?,?,?,?,?,?)", rows)
                conn.executemany("INSERT INTO puzzle_types VALUES (?,?)", type_rows)
                rows.clear()
                type_rows.clear()
                if progress is not None:
                    progress(Progress("write", index, total))
                if should_cancel is not None and should_cancel():
                    raise Cancelled("import cancelled")
        conn.executemany(
            "INSERT INTO theme_counts VALUES ('theme', ?, ?)", sorted(theme_counter.items())
        )
        conn.executemany(
            "INSERT INTO theme_counts VALUES ('type', ?, ?)", sorted(type_counter.items())
        )
        report.type_counts = {name: type_counter.get(name, 0) for name in themes.TYPES}
        meta = {
            "schema_version": str(SCHEMA_VERSION),
            "source": report.source,
            "imported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "settings": json.dumps(asdict(settings)),
            "rows_read": str(report.rows_read),
            "rows_filtered": str(report.rows_filtered),
            "rows_kept": str(report.rows_kept),
            "rows_rejected": str(report.rows_rejected),
        }
        conn.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
        conn.commit()
        if progress is not None:
            progress(Progress("index", 0, None))
        conn.executescript(INDEXES)
        conn.commit()
    except BaseException:
        conn.close()
        tmp.unlink(missing_ok=True)
        raise
    conn.close()
    os.replace(tmp, db_path)


# -- entry points --------------------------------------------------------------------------------


def import_puzzles(
    source: Path,
    db_path: Path,
    settings: ImportSettings | None = None,
    progress: ProgressFn | None = None,
    should_cancel: CancelFn | None = None,
) -> ImportReport:
    """Build ``db_path`` from a Lichess ``.csv`` or ``.csv.zst`` file."""
    settings = settings or ImportSettings()
    started = time.monotonic()
    report = ImportReport(source=str(source), db_path=str(db_path))
    kept = scan(source, settings, report, progress, should_cancel)
    write_db(kept, db_path, settings, report, progress, should_cancel)
    report.seconds = time.monotonic() - started
    if progress is not None:
        progress(Progress("done", report.rows_kept, report.rows_kept))
    return report


def make_sample(db_path: Path, out_path: Path, per_type: int = 10) -> int:
    """Write a small Lichess-format CSV with up to ``per_type`` random puzzles of every type."""
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    chosen: dict[str, sqlite3.Row] = {}
    try:
        conn.row_factory = sqlite3.Row
        for type_name in themes.TYPES:
            rows = conn.execute(
                "SELECT p.* FROM puzzles p JOIN puzzle_types t ON t.puzzle_id = p.id "
                "WHERE t.type = ? ORDER BY random() LIMIT ?",
                (type_name, per_type),
            ).fetchall()
            for row in rows:
                chosen[row["id"]] = row
    finally:
        conn.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for row in sorted(chosen.values(), key=lambda r: r["id"]):
            writer.writerow(
                [
                    row["id"],
                    row["fen"],
                    row["moves"],
                    row["rating"],
                    row["deviation"],
                    row["popularity"],
                    row["nb_plays"],
                    row["themes"],
                    "",
                    "",
                ]
            )
    return len(chosen)
