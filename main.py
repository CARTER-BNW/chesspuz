"""Entry point for chesspuz.

``python main.py``                 launch the GUI
``python main.py import --download`` download the Lichess puzzle file and build the database
``python main.py import FILE``     build the database from a local .csv or .csv.zst
``python main.py stats``           show puzzle counts per type
``python main.py sample``          write tests/data/sample.csv from the database
``python main.py board-demo``      open a free-play board to try the widget
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from chesspuz import paths


def _progress_printer():
    last = [0.0]

    def show(progress) -> None:
        now = time.monotonic()
        if progress.stage not in ("done", "index") and now - last[0] < 1.0:
            return
        last[0] = now
        total = f"/{progress.total:,}" if progress.total else ""
        print(f"  {progress.stage}: {progress.done:,}{total} {progress.message}", file=sys.stderr)

    return show


def cmd_import(args: argparse.Namespace) -> int:
    from chesspuz.importer import LICHESS_URL, ImportSettings, download, import_puzzles

    db_path = Path(args.db) if args.db else paths.puzzle_db_path()
    if args.download:
        source = paths.lichess_archive_path()
        if source.exists() and not args.force:
            print(f"using existing download {source}")
        else:
            print(f"downloading {LICHESS_URL} -> {source}")
            download(LICHESS_URL, source, progress=_progress_printer())
    elif args.source:
        source = Path(args.source)
    else:
        print("give a source file or --download", file=sys.stderr)
        return 2
    settings = ImportSettings(per_bucket_type=0 if args.all else args.per_type)
    print(f"importing {source} -> {db_path}")
    report = import_puzzles(source, db_path, settings, progress=_progress_printer())
    print(
        f"read {report.rows_read:,} rows, {report.rows_filtered:,} passed the filter, "
        f"kept {report.rows_kept:,}, rejected {report.rows_rejected:,} "
        f"in {report.seconds:.0f}s"
    )
    _print_counts(report.type_counts)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    from chesspuz.puzzledb import PuzzleRepository

    db_path = Path(args.db) if args.db else paths.puzzle_db_path()
    if not PuzzleRepository.is_available(db_path):
        print(f"no puzzle database at {db_path}; run: python main.py import --download")
        return 1
    with PuzzleRepository(db_path) as repo:
        meta = repo.meta()
        print(f"{db_path}: {repo.count():,} puzzles, imported {meta.get('imported_at', '?')}")
        _print_counts(repo.counts_by_type())
        if args.themes:
            for name, count in repo.theme_counts().items():
                print(f"  {name:<28}{count:>9,}")
    if args.runs:
        from chesspuz.userdb import UserDB

        with UserDB(paths.user_db_path()) as users:
            print("recent runs:")
            for record in users.history(limit=args.runs):
                print(
                    f"  #{record.id} {record.started_at} {record.player_name:<12} "
                    f"{record.status:<9} score {record.score:<3} "
                    f"puzzles {record.puzzles_played:<3} max {record.max_rating_solved}"
                )
    return 0


def cmd_sample(args: argparse.Namespace) -> int:
    from chesspuz.importer import make_sample

    db_path = Path(args.db) if args.db else paths.puzzle_db_path()
    out = Path(args.out)
    written = make_sample(db_path, out, per_type=args.per_type)
    print(f"wrote {written} puzzles to {out}")
    return 0


def cmd_board_demo(_args: argparse.Namespace) -> int:
    from chesspuz.ui.demo import run_board_demo

    return run_board_demo()


def _print_counts(counts: dict[str, int]) -> None:
    for name, count in counts.items():
        print(f"  {name:<18}{count:>9,}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chesspuz", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    imp = sub.add_parser("import", help="build the puzzle database")
    imp.add_argument("source", nargs="?", help="local .csv or .csv.zst file")
    imp.add_argument("--download", action="store_true", help="fetch the Lichess file first")
    imp.add_argument("--force", action="store_true", help="re-download even if present")
    imp.add_argument("--db", help="database path (default: app data dir)")
    imp.add_argument("--per-type", type=int, default=500, help="cap per rating bucket and type")
    imp.add_argument("--all", action="store_true", help="keep everything that passes the filter")
    imp.set_defaults(func=cmd_import)

    stats = sub.add_parser("stats", help="show puzzle counts")
    stats.add_argument("--db")
    stats.add_argument("--themes", action="store_true", help="also list Lichess theme counts")
    stats.add_argument("--runs", type=int, nargs="?", const=20, help="list recent runs")
    stats.set_defaults(func=cmd_stats)

    sample = sub.add_parser("sample", help="write a small sample CSV for the tests")
    sample.add_argument("--db")
    sample.add_argument("--out", default="tests/data/sample.csv")
    sample.add_argument("--per-type", type=int, default=10)
    sample.set_defaults(func=cmd_sample)

    demo = sub.add_parser("board-demo", help="open a free-play board")
    demo.set_defaults(func=cmd_board_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command is None:
        try:
            from chesspuz.ui.app import run
        except ImportError as exc:
            print(f"the GUI is not available yet ({exc})", file=sys.stderr)
            return 1
        return run()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
