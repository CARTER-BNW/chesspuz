"""Screenshots of every page for the README and the release page.

    python tools\\release_shots.py docs\\screenshots desktop
    python tools\\release_shots.py docs\\screenshots phone

Runs offscreen at QT_SCALE_FACTOR 1.5 (SHOT_SCALE to change) against the app's real puzzle
database and a throwaway user database seeded with runs for three players, so the leaderboard,
stats, mistakes and review pages have content. A live run is driven to its fourth puzzle with a
fake clock (believable solve times in "This run"), a candidate-move arrow is drawn, then the run
is paused for the pause-screen shot. The release page and the README load these files from
docs/screenshots on main, so keep the names.
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
shape = sys.argv[2] if len(sys.argv) > 2 else "desktop"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ["QT_SCALE_FACTOR"] = os.environ.get("SHOT_SCALE", "1.5")
if shape == "phone":
    os.environ["CHESSPUZ_MOBILE"] = "1"
sys.path.insert(0, str(ROOT))

from chesspuz import paths, sounds, themes  # noqa: E402
from chesspuz.session import Outcome, Status  # noqa: E402
from chesspuz.ui.annotations import Brush  # noqa: E402
from chesspuz.ui.app import build  # noqa: E402
from chesspuz.ui.board import InputState  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs" / "screenshots")
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
app, ctx, window = build(
    [sys.argv[0]], puzzle_db=paths.puzzle_db_path(), user_db=tmp / "user.sqlite"
)
assert ctx.puzzles is not None, "no puzzle database: python main.py import --download"
sounds.player.enabled = False


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


clock = Clock()
rng = random.Random(7)
ALL = list(themes.TYPES)
TACTICS = ["Fork", "Pin", "Skewer", "Discovery", "Hanging Piece"]
MATES = ["Mate in 1", "Mate in 2", "Mate in 3+", "Back Rank Mate", "Mating Net"]


def wrong_move(session):
    board = session.board
    for move in board.legal_moves:
        if move == session.expected:
            continue
        board.push(move)
        mates = board.is_checkmate()
        board.pop()
        if not mates:
            return move
    return None


def solve(run, session) -> None:
    while session.status is Status.PLAYING:
        outcome = run.try_move(session.expected)
        if outcome is Outcome.COMPLETE:
            break
        if outcome is not Outcome.CORRECT:
            raise RuntimeError(outcome)


def play_run(name: str, types, script: str, lives: int = 3) -> int:
    """Sample data: 'S' solves the next puzzle, 'F' fails it; quits if lives remain."""
    player = ctx.users.get_or_create_player(name)
    run_id, run = ctx.users.new_run(
        player.id, types, ctx.puzzles.pick, ramp=ctx.ramp(), clock=clock, lives=lives
    )
    for step in script:
        session = run.next_puzzle()
        clock.now += rng.uniform(6, 40)
        move = wrong_move(session) if step == "F" else None
        if step == "F" and move is not None:
            run.try_move(move)
        else:
            solve(run, session)
        if run.finished:
            break
    if not run.finished:
        run.quit()
    ctx.users.finish_run(run_id, run)
    clock.now += 600
    return run_id


john_all = play_run("John", ALL, "SSSSSSFSSSFSSF")
play_run("John", TACTICS, "SSSFSFF")
play_run("John", MATES, "SSSSSSSSFSFF")
play_run("John", ALL, "SSSFSSFSFSSFF", lives=5)
play_run("Alice", ALL, "SSSSFSFF")
play_run("Alice", MATES, "SSFSSSFSF")
play_run("Bob", ALL, "SFSFF")
ctx.set_setting("last_player", "John")


def pump(seconds: float = 0.3) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def shot(name: str) -> None:
    pump()
    pixmap = window.grab()
    pixmap.save(str(out / f"{shape}-{name}.png"))
    print("saved", shape, name, pixmap.size().toTuple())


window.show()
size = (412, 915) if shape == "phone" else (1100, 760)
for _ in range(2):
    window.resize(*size)
    app.processEvents()

window.show_home()
shot("home")
window.show_leaderboard()
shot("leaderboard")
window.show_stats()
shot("stats")
window.show_mistakes()
shot("mistakes")
window.show_settings()
shot("settings")

# review: a finished run, a few moves into a puzzle, with an arrow drawn on the board
window.show_review(john_all)
pump(0.5)
review = window.review
review.board.animation_ms = 0
review.puzzle_list.setCurrentRow(2)
pump(0.3)
review._forward()
pump(0.3)
if review.model.puzzles and review.board.board.move_stack:
    last = review.board.board.move_stack[-1]
    review.board.annotations.toggle_arrow(last.from_square, last.to_square, Brush.GREEN)
    review.board.update()
shot("review")

# a live run: three puzzles solved, the fourth on the board with a candidate-move arrow
page = window.run_page
page.tempo = 0
page.board.animation_ms = 0


def wait_solving(timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pump(0.05)
        if page._phase == "solving" and page.board.state is InputState.IDLE:
            return True
    return False


# the run's own clock is the fake one, so the solve times in "This run" look real
john = ctx.users.get_or_create_player("John")
ctx.remember_selection("John", ALL)
run_id, live_run = ctx.users.new_run(
    john.id, ALL, ctx.puzzles.pick, ramp=ctx.ramp(), clock=clock, lives=ctx.lives()
)
window.stack.setCurrentWidget(page)
page.start(run_id, live_run, john)
for _ in range(3):
    assert wait_solving()
    session = page.session
    clock.now += rng.uniform(9, 31)
    while session.status is Status.PLAYING:
        assert wait_solving()
        page.board.move_played.emit(session.expected)
        pump(0.05)
assert wait_solving()
page._started = time.monotonic() - 23.4  # a believable clock
pump(0.3)
expected = page.session.expected
page.board.annotations.toggle_arrow(expected.from_square, expected.to_square, Brush.GREEN)
page.board.update()
shot("run")
page.pause()
shot("paused")
page.resume()
page.abort()
window.close()
ctx.close()
