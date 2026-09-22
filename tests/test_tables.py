"""Leaderboard, history and stats pages (offscreen) plus the queries behind them."""

from pathlib import Path

import pytest

from chesspuz import themes
from chesspuz.ui.app import AppContext, MainWindow
from chesspuz.ui.leaderboard_page import LeaderboardPage, format_ms, type_set_label
from chesspuz.ui.stats_page import StatsPage
from chesspuz.userdb import UserDB
from tests.test_run import FakeClock
from tests.test_userdb import finished_run


@pytest.fixture
def ctx(tmp_path: Path):
    context = AppContext(tmp_path / "missing.sqlite", tmp_path / "user.sqlite")
    clock = FakeClock()
    alice = context.users.get_or_create_player("Alice")
    bob = context.users.get_or_create_player("Bob")
    finished_run(context.users, alice.id, solves=3, clock=clock)
    finished_run(context.users, bob.id, solves=5, clock=clock)
    finished_run(context.users, alice.id, solves=1, clock=clock, types=tuple(themes.TYPES))
    yield context
    context.close()


def test_type_sets_and_summary(ctx: AppContext) -> None:
    users: UserDB = ctx.users
    assert users.type_sets() == [("Mate in 1",), tuple(sorted(themes.TYPES))]
    totals = users.summary()
    assert totals["runs"] == 3 and totals["best_score"] == 5
    assert totals["average_score"] == pytest.approx(3.0)
    assert totals["attempted"] == 3 + 3 + 5 + 3 + 1 + 3 and totals["solved"] == 9
    alice = users.get_or_create_player("Alice")
    mine = users.summary(alice.id)
    assert mine["runs"] == 2 and mine["best_score"] == 3 and mine["solved"] == 4
    assert users.summary(999) == {
        "runs": 0,
        "best_score": 0,
        "average_score": 0.0,
        "attempted": 0,
        "solved": 0,
    }


def test_labels() -> None:
    assert type_set_label(tuple(themes.TYPES)) == "All types"
    assert type_set_label(("Fork",)) == "1 types: Fork"
    assert type_set_label(("A", "B", "C", "D")) == "4 types: A, B, C, ..."
    assert format_ms(0) == "0:00" and format_ms(65_000) == "1:05"
    assert format_ms(3_600_000) == "60:00"


def test_leaderboard_page_filters_and_opens_runs(ctx: AppContext, qtbot) -> None:
    page = LeaderboardPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    assert page.board_table.rowCount() == 3
    assert page.board_table.item(0, 1).text() == "Bob"  # score 5 first
    assert page.board_table.item(0, 2).text() == "5"
    assert page.history_table.rowCount() == 3

    page.types_box.setCurrentIndex(1)  # ("Mate in 1",)
    assert page.board_table.rowCount() == 2 and page.history_table.rowCount() == 2
    page.player_box.setCurrentText("Alice")
    assert page.board_table.rowCount() == 1
    assert page.board_table.item(0, 1).text() == "Alice"
    page.types_box.setCurrentIndex(0)
    assert page.board_table.rowCount() == 2

    alice = ctx.users.get_or_create_player("Alice")
    with qtbot.waitSignal(page.review_requested, timeout=1000) as blocker:
        page.board_table.itemDoubleClicked.emit(page.board_table.item(0, 0))
    assert blocker.args == [ctx.users.leaderboard(player_id=alice.id)[0].id]
    page.refresh()  # keeps the filters
    assert page.player_box.currentText() == "Alice"


def test_stats_page_lists_every_type(ctx: AppContext, qtbot) -> None:
    page = StatsPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    assert page.table.rowCount() == 19
    assert page.table.item(0, 0).text() == "Back Rank Mate"
    assert page.table.item(0, 3).text() == "50%"  # 9 solved of 18 back-rank attempts
    assert "3 runs" in page.summary.text() and "best score 5" in page.summary.text()
    page.player_box.setCurrentText("Bob")
    assert "1 runs" in page.summary.text()
    row = [page.table.item(5, c).text() for c in range(4)]
    assert row == ["Mate in 1", "8", "5", "62%"]
    fork_row = [page.table.item(3, c).text() for c in range(4)]
    assert fork_row == ["Fork", "0", "0", "-"]


def test_main_window_navigates_to_the_new_pages(ctx: AppContext, qtbot) -> None:
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    window.home.leaderboard_requested.emit()
    assert window.stack.currentWidget() is window.leaderboard
    window.leaderboard.review_requested.emit(1)
    assert window.stack.currentWidget() is window.review
    assert window.review.puzzle_list.count() > 0
    window.review.home_requested.emit()
    assert window.stack.currentWidget() is window.home
    window.home.stats_requested.emit()
    assert window.stack.currentWidget() is window.stats
    window.show_review(999)  # unknown run: back home
    assert window.stack.currentWidget() is window.home
