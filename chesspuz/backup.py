"""Profile export and import: every player's runs and puzzles (and the settings) as JSON.

The file is what a player keeps outside the app: a copy on a cloud drive, a phone's Download
folder, a hand-over to a new machine. Import merges rather than replaces: players are matched
by name, a run already present (same start time, mode and puzzle count) is skipped, so a file
can be imported twice or into someone else's app without damage. Settings travel with the file
but are only applied to a database nobody has used yet (no players, no runs: a fresh
install), never over a used one. Headless: no Qt here.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from chesspuz import __version__
from chesspuz.userdb import ACTIVE, UserDB

FORMAT = "chesspuz-profiles"
FORMAT_VERSION = 1
PRIVATE_SETTINGS = frozenset({"geometry"})  # tied to one machine's screen
RUN_FIELDS = (
    "started_at",
    "ended_at",
    "status",
    "score",
    "lives_lost",
    "types",
    "start_rating",
    "step",
    "max_rating_solved",
    "total_ms",
    "mode",
    "lives",
)
PUZZLE_FIELDS = (
    "seq",
    "puzzle_id",
    "fen",
    "moves",
    "rating",
    "types",
    "result",
    "target_rating",
    "solve_ms",
    "player_moves",
    "alternate_mate",
)


@dataclass(frozen=True)
class ImportReport:
    players_added: int
    runs_added: int
    runs_skipped: int
    settings_applied: bool

    def summary(self) -> str:
        parts = [f"{self.runs_added} runs imported"]
        if self.runs_skipped:
            parts.append(f"{self.runs_skipped} already present")
        if self.players_added:
            parts.append(f"{self.players_added} new players")
        if self.settings_applied:
            parts.append("settings restored")
        return ", ".join(parts) + "."


def export_profiles(db: UserDB, player_ids: Collection[int] | None = None) -> dict:
    """The profiles of ``player_ids`` (everyone when None) as a JSON-ready dict."""
    players = db.players()
    if player_ids is not None:
        wanted = set(player_ids)
        players = [p for p in players if p.id in wanted]
    settings = {k: v for k, v in db.settings_dict().items() if k not in PRIVATE_SETTINGS}
    return {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "app_version": __version__,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "players": [
            {
                "name": player.name,
                "created_at": player.created_at,
                "runs": [run for run in db.run_rows(player.id) if run["status"] != ACTIVE],
            }
            for player in players
        ],
        "settings": settings,
    }


def to_json(data: Mapping) -> str:
    return json.dumps(data, indent=1)


def from_json(text: str) -> dict:
    """Parse a profiles file; ValueError when it is not one."""
    try:
        # raw_decode tolerates trailing bytes (a phone's content provider may not truncate)
        data, _end = json.JSONDecoder().raw_decode(text.lstrip("\ufeff \r\n\t"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"not a chesspuz profiles file ({exc.msg})") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("not a chesspuz profiles file")
    if not isinstance(data.get("players"), list):
        raise ValueError("profiles file has no players")
    return data


def import_profiles(db: UserDB, data: Mapping) -> ImportReport:
    """Merge ``data`` (from :func:`from_json`) into ``db``; see the module note for the rules."""
    if data.get("format") != FORMAT:
        raise ValueError("not a chesspuz profiles file")
    fresh = not db.players() and db.row_counts()[0] == 0  # a database nobody has used yet
    known = {p.name for p in db.players()}
    players_added = 0
    pending: list[tuple[str, int, dict, list[dict]]] = []
    for raw_player in data.get("players", ()):
        name = str(raw_player.get("name", "")).strip() if isinstance(raw_player, dict) else ""
        if not name:
            raise ValueError("a player in the file has no name")
        player = db.get_or_create_player(name)
        if name not in known:
            players_added += 1
            known.add(name)
        for raw_run in raw_player.get("runs", ()):
            run, puzzles = _clean_run(raw_run)
            pending.append((run["started_at"], player.id, run, puzzles))
    pending.sort(key=lambda item: item[0])  # oldest first, so ids follow the history
    keys = {player_id: db.run_keys(player_id) for _s, player_id, _r, _p in pending}
    runs_added = runs_skipped = 0
    for started_at, player_id, run, puzzles in pending:
        key = (started_at, run["mode"], len(puzzles))
        if key in keys[player_id]:
            runs_skipped += 1
            continue
        try:
            db.insert_run(player_id, run, puzzles)
        except sqlite3.IntegrityError as exc:  # e.g. two puzzles with the same seq
            raise ValueError(f"a run in the file is inconsistent ({exc})") from None
        keys[player_id].add(key)
        runs_added += 1
    settings = data.get("settings")
    settings_applied = False
    if fresh and isinstance(settings, dict) and settings:
        for key, value in settings.items():
            if key not in PRIVATE_SETTINGS and isinstance(key, str) and isinstance(value, str):
                db.set_setting(key, value)
        settings_applied = True
    return ImportReport(players_added, runs_added, runs_skipped, settings_applied)


def write_backup(db: UserDB, path: Path) -> Path:
    """Write everyone's profiles to ``path`` (temp file then replace, so a crash leaves the
    old copy intact); the folder is created. Raises OSError when the place is not writable."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(to_json(export_profiles(db)), encoding="utf-8")
    tmp.replace(path)
    return path


def default_file_name(player_name: str | None = None) -> str:
    """``chesspuz-<player>-<date>.json`` (or ``chesspuz-profiles-<date>.json`` for everyone)."""
    who = re.sub(r"[^A-Za-z0-9_-]+", "-", player_name or "").strip("-") or "profiles"
    return f"chesspuz-{who}-{datetime.now():%Y-%m-%d}.json"


def _clean_run(raw: object) -> tuple[dict, list[dict]]:
    """Validate one run of the file; ValueError when a required field is missing or wrong."""
    if not isinstance(raw, dict):
        raise ValueError("a run in the file is not an object")
    try:
        run = {
            "started_at": str(raw["started_at"]),
            "ended_at": None if raw.get("ended_at") is None else str(raw["ended_at"]),
            "status": str(raw["status"]),
            "score": int(raw.get("score", 0)),
            "lives_lost": int(raw.get("lives_lost", 0)),
            "types": [str(t) for t in raw.get("types", [])],
            "start_rating": int(raw["start_rating"]),
            "step": int(raw["step"]),
            "max_rating_solved": int(raw.get("max_rating_solved", 0)),
            "total_ms": int(raw.get("total_ms", 0)),
            "mode": str(raw.get("mode", "survival")),
            "lives": int(raw.get("lives", 3)),
        }
        puzzles = [
            {
                "seq": int(p["seq"]),
                "puzzle_id": str(p["puzzle_id"]),
                "fen": str(p["fen"]),
                "moves": str(p["moves"]),
                "rating": int(p["rating"]),
                "types": [str(t) for t in p.get("types", [])],
                "result": str(p["result"]),
                "target_rating": int(p.get("target_rating", 0)),
                "solve_ms": int(p.get("solve_ms", 0)),
                "player_moves": str(p.get("player_moves", "")),
                "alternate_mate": bool(p.get("alternate_mate", False)),
            }
            for p in raw.get("puzzles", [])
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"a run in the file is incomplete ({exc!r})") from None
    if run["status"] == ACTIVE:
        run["status"] = "abandoned"
    return run, puzzles
