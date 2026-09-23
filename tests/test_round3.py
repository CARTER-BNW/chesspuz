"""Round 3: the lives setting (1-10), the pause screen, boards and stats per number of lives."""

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from chesspuz.run import SurvivalRun, clamp_lives
from chesspuz.session import Outcome
from chesspuz.ui.app import AppContext, MainWindow
from chesspuz.ui.leaderboard_page import LeaderboardPage, lives_label
from chesspuz.ui.run_page import GameOverDialog, RunPage
from chesspuz.ui.settings_page import DEFAULTS
from chesspuz.ui.stats_page import StatsPage
from chesspuz.userdb import UserDB
from tests import puzzles
from tests.test_pages import ctx  # noqa: F401 (fixture: tiny puzzle DB + user DB)
from tests.test_retry_flow import idle, right_move, wrong_move
from tests.test_run import FakeClock, FakePool, mate
from tests.test_userdb import play

# -- headless ------------------------------------------------------------------------------------


def test_pause_freezes_the_solve_clock() -> None:
    clock = FakeClock()
    run = SurvivalRun(["Mate in 1"], FakePool([puzzles.BACK_RANK]).pick, clock=clock)
    run.next_puzzle()
    clock.now += 5
    run.pause()
    assert run.paused
    run.pause()  # a second pause changes nothing
    clock.now += 100
    assert run.resume() == 100
    assert not run.paused and run.resume() == 0
    clock.now += 2
    assert mate(run, "e1e8") is Outcome.COMPLETE
    assert run.results[-1].solve_ms == 7000

    run.next_puzzle()
    clock.now += 3
    run.pause()
    clock.now += 50
    run.reveal_solution()  # settled while paused: only the time before the pause counts
    assert run.results[-1].solve_ms == 3000 and run.total_ms == 10000
    run.next_puzzle()  # a new puzzle starts unpaused
    assert not run.paused


def test_lives_setting_bounds_and_run_length() -> None:
    assert clamp_lives(0) == 1 and clamp_lives(99) == 10 and clamp_lives(7) == 7
    one = SurvivalRun(["Mate in 1"], FakePool([puzzles.BACK_RANK]).pick, lives=1)
    one.next_puzzle()
    assert mate(one, "e1e7") is Outcome.WRONG
    assert one.finished and one.ended_by == "lives" and one.lives == 1
    ten = SurvivalRun(["Mate in 1"], FakePool([puzzles.BACK_RANK]).pick, lives=10)
    for _ in range(9):
        ten.next_puzzle()
        mate(ten, "e1e7")
    assert not ten.finished and ten.lives_left == 1
    ten.next_puzzle()
    mate(ten, "e1e7")
    assert ten.finished and ten.lives_left == 0


def scripted_run(db: UserDB, player_id: int, script: str, clock: FakeClock, lives: int = 3):
    """Back-rank puzzles in order: 'S' solves one, 'F' fails one; quits if lives remain."""
    run_id, run = db.new_run(
        player_id, ["Mate in 1"], FakePool([puzzles.BACK_RANK]).pick, clock=clock, lives=lives
    )
    for step in script:
        run.next_puzzle()
        clock.now += 1
        play(run, "e1e8" if step == "S" else "e1e7")
    if not run.finished:
        run.quit()
    db.finish_run(run_id, run)
    return run_id


def test_runs_count_on_the_boards_for_fewer_lives(tmp_path: Path) -> None:
    with UserDB(tmp_path / "u.sqlite") as db:
        clock = FakeClock()
        alice = db.get_or_create_player("Alice")
        three = scripted_run(db, alice.id, "SSFSFF", clock)  # 3 lives: 2 before the 1st miss
        one = scripted_run(db, alice.id, "SSSSF", clock, lives=1)  # 1 life: score 4
        five = scripted_run(db, alice.id, "SF", clock, lives=5)  # quit with 4 lives left
        practice_id, practice = db.new_practice(alice.id, [puzzles.BACK_RANK])
        practice.next_puzzle()
        play(practice, "e1e8")
        practice.next_puzzle()
        db.finish_run(practice_id, practice)
        assert db.run(three).lives == 3 and db.run(one).lives == 1 and db.run(five).lives == 5
        assert db.run(practice_id).lives == 0

        def board(lives=None):
            return [(r.id, r.score, r.total_ms) for r in db.leaderboard(lives=lives)]

        assert board() == [(one, 4, 5000), (three, 3, 6000), (five, 1, 2000)]
        assert board(1) == [(one, 4, 5000), (three, 2, 3000), (five, 1, 2000)]
        assert board(2) == [(three, 3, 5000), (five, 1, 2000)]  # a 1-life run has no 2-life score
        assert board(3) == [(three, 3, 6000), (five, 1, 2000)]
        assert board(4) == [(five, 1, 2000)] and board(6) == []
        assert db.leaderboard(lives=1, player_id=alice.id, types=["Mate in 1"])[0].id == one

        types = ["Mate in 1"]
        assert db.best_score(alice.id, types) == 4
        assert [db.best_score(alice.id, types, lives=k) for k in (1, 2, 3, 5, 6)] == [4, 3, 3, 1, 0]
        totals = db.summary(alice.id, lives=2)
        assert totals["runs"] == 2 and totals["best_score"] == 3
        assert totals["average_score"] == pytest.approx(2.0)
        assert totals["attempted"] == 13 and totals["solved"] == 8  # every Survival puzzle
        assert db.summary(alice.id, lives=1)["average_score"] == pytest.approx(7 / 3)
        assert db.summary(alice.id)["runs"] == 3 and db.summary(lives=9)["runs"] == 0


# -- settings and the run page -------------------------------------------------------------------


def test_settings_lives_spin_feeds_new_runs_and_the_home_page(ctx: AppContext, qtbot) -> None:  # noqa: F811
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    window.run_page.tempo = 0
    window.run_page.board.animation_ms = 0
    page = window.settings
    window.show_settings()
    assert page.lives_spin.value() == DEFAULTS["lives"] == 3
    assert (page.lives_spin.minimum(), page.lives_spin.maximum()) == (1, 10)
    with qtbot.waitSignal(page.changed, timeout=1000):
        page.lives_spin.setValue(5)
    assert ctx.lives() == 5
    window.show_home()
    assert "5 lives" in window.home.subtitle.text()
    assert "and 5 lives: 0" in window.home.best_label.text()
    window.start_run("Alice", ["Mate in 1"])
    run = window.run_page.run
    assert run is not None and run.lives == 5 and run.lives_left == 5
    assert ctx.users.run(window.run_page.run_id).lives == 5
    assert window.run_page.lives_label.text().count("♥") == 5
    window.run_page.abort()

    ctx.set_setting("lives", "42")  # a hand-edited value is clamped
    assert ctx.lives() == 10
    page.refresh()
    assert page.lives_spin.value() == 10
    page._reset()
    assert ctx.lives() == 3 and page.lives_spin.value() == 3
    ctx.set_setting("lives", "1")
    window.show_home()
    assert "Survival: 1 life," in window.home.subtitle.text()


def test_pause_covers_the_page_and_freezes_the_clock(ctx: AppContext, qtbot) -> None:  # noqa: F811
    page = RunPage(ctx, animation_ms=0, tempo=0)
    qtbot.addWidget(page)
    page.show()
    page.resize(900, 600)
    QApplication.processEvents()
    player = ctx.users.get_or_create_player("Alice")
    run_id, run = ctx.users.new_run(player.id, ["Mate in 1"], ctx.puzzles.pick)
    assert not page.pause_button.isEnabled() and not page.overlay.isVisible()
    page.start(run_id, run, player)
    idle(qtbot, page)  # the opponent has moved: solving
    assert page.pause_button.isEnabled() and page.can_pause
    qtbot.waitUntil(lambda: page.time_label.text() != "0:00.0", timeout=2000)

    page.pause_button.click()
    assert page.paused and run.paused and page.overlay.isVisible()
    assert page.overlay.geometry() == page.rect()
    assert not page.board.interactive and not page._ticker.isActive()
    assert not page.pause_button.isEnabled() and not page.solution_button.isEnabled()
    assert not page.next_button.isEnabled()
    summary = page.overlay.summary.text()
    assert "Puzzle 1" in summary and "3 of 3 lives left" in summary
    frozen = page.time_label.text()
    qtbot.wait(250)
    assert page.time_label.text() == frozen
    page.resize(700, 900)  # the overlay follows the page (portrait too)
    QApplication.processEvents()
    assert page.overlay.geometry() == page.rect()
    page._next_clicked()  # Next is refused while paused
    assert page.session is run.session and page.paused
    page.pause()  # a second pause changes nothing
    assert page.paused

    page.overlay.resume_button.click()
    assert not page.paused and not run.paused and not page.overlay.isVisible()
    assert page.board.interactive and page._ticker.isActive() and page.pause_button.isEnabled()
    qtbot.waitUntil(lambda: page.time_label.text() != frozen, timeout=2000)

    page.board.move_played.emit(wrong_move(page))  # after a mistake the puzzle stays open
    assert page.can_pause
    page.pause()
    assert "2 of 3 lives left" in page.overlay.summary.text()
    page.resume()
    page.board.move_played.emit(right_move(page))  # solved: nothing to pause any more
    assert not page.pause_button.isEnabled() and not page.can_pause
    page.pause()
    assert not page.paused
    page.abort()


def _back_key() -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Back, Qt.KeyboardModifier.NoModifier)


def test_back_key_resumes_a_paused_run(ctx: AppContext, qtbot, monkeypatch) -> None:  # noqa: F811
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    page = window.run_page
    page.tempo = 0
    page.board.animation_ms = 0
    window.start_run("Alice", ["Mate in 1"])
    idle(qtbot, page)
    page.pause()
    assert page.paused
    asked: list[int] = []

    def question(*_args, **_kwargs):
        asked.append(1)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", question)
    QApplication.sendEvent(window, _back_key())
    assert not page.paused and asked == []  # Back on the pause screen: back to the puzzle
    assert window.stack.currentWidget() is page
    QApplication.sendEvent(window, _back_key())
    assert asked == [1]  # not paused: the usual "end this run?" question

    page.pause()
    monkeypatch.setattr(GameOverDialog, "exec", lambda self: GameOverDialog.HOME)
    page.run.quit()
    page._game_over()  # a run ending while paused takes the pause screen down
    assert not page.paused and not page.overlay.isVisible()
    window.start_run("Alice", ["Mate in 1"])
    idle(qtbot, page)
    page.pause()
    page.abort()  # the window closing while paused
    assert not page.paused and not page.overlay.isVisible()


# -- home page links -----------------------------------------------------------------------------


def test_home_links_open_in_the_browser(ctx: AppContext, qtbot, monkeypatch) -> None:  # noqa: F811
    from chesspuz import RELEASES_URL, SUPPORT_URL, __version__
    from chesspuz.ui import home_page
    from chesspuz.ui.home_page import HomePage

    opened: list[str] = []
    monkeypatch.setattr(home_page, "open_link", lambda url: opened.append(url) or True)
    page = HomePage(ctx)
    qtbot.addWidget(page)
    page.support_button.click()
    page.updates_button.click()
    assert opened == [SUPPORT_URL, RELEASES_URL]
    assert SUPPORT_URL == "https://buymeacoffee.com/carter.bnw"
    assert RELEASES_URL == "https://github.com/CARTER-BNW/chesspuz/releases"
    assert __version__ in page.updates_button.toolTip() and __version__ in page.status_label.text()
    # at the top of the menu: the links row sits right above the page buttons
    assert page.page_layout.indexOf(page.links_row) == page.page_layout.indexOf(page.nav_row) - 1
    assert page.links_grid.itemAtPosition(0, 1).widget() is page.updates_button


# -- leaderboard and stats -----------------------------------------------------------------------


def test_leaderboard_and_stats_filter_by_lives(tmp_path: Path, qtbot) -> None:
    ctx = AppContext(tmp_path / "missing.sqlite", tmp_path / "user.sqlite")  # noqa: F811
    clock = FakeClock()
    alice = ctx.users.get_or_create_player("Alice")
    scripted_run(ctx.users, alice.id, "SSFSFF", clock)
    scripted_run(ctx.users, alice.id, "SSSSF", clock, lives=1)
    page = LeaderboardPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    assert page.selected_lives() == 3 and page.lives_box.currentText() == "3 lives"
    assert page.board_table.rowCount() == 1  # a 1-life run is not on the 3-life board
    assert page.board_table.item(0, 2).text() == "3" and page.board_table.item(0, 3).text() == "3"

    page.lives_box.setCurrentIndex(page.lives_box.findData(1))
    assert page.board_table.rowCount() == 2
    assert [page.board_table.item(r, 2).text() for r in range(2)] == ["4", "2"]
    assert [page.board_table.item(r, 3).text() for r in range(2)] == ["1", "3"]
    assert page.history_table.rowCount() == 2  # history keeps every run's final score
    assert page.history_table.item(0, 3).text() == "4"  # newest first
    assert page.history_table.item(1, 3).text() == "3"
    assert page.history_table.item(1, 4).text() == "3"
    page.lives_box.setCurrentIndex(0)  # any lives: final scores side by side
    assert page.board_table.rowCount() == 2 and page.board_table.item(1, 2).text() == "3"
    page.refresh()
    assert page.selected_lives() is None  # the choice survives a refresh
    assert lives_label(1) == "1 life" and lives_label(2) == "2 lives"

    stats = StatsPage(ctx)
    qtbot.addWidget(stats)
    stats.refresh()
    assert stats.selected_lives() == 3
    assert stats.summary.text().startswith("1 runs  -  best score 3")
    stats.lives_box.setCurrentIndex(stats.lives_box.findData(1))
    assert stats.summary.text().startswith("2 runs  -  best score 4  -  average 3.0")
    assert "7 of 11 puzzles solved" in stats.summary.text()
    ctx.close()
