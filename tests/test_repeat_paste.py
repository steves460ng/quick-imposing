"""Repeated paste (Ctrl+Shift+V): TEMPLATE-REQUIREMENTS §6.5."""

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

from imposing import store  # noqa: E402
from imposing.gui.work import WorkWindow  # noqa: E402
from imposing.session import Session  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "samples/input/base-front-blank.pdf"
DATA = ROOT / "samples/test03-2/data"
A, B = DATA / "c-1.pdf", DATA / "c-2.pdf"


def make(root, direction="forward", name="small"):
    data = json.loads((ROOT / "samples/manual/T31-front-3x8.json").read_text("utf-8"))
    data["name"] = name
    data["grid"]["count"] = [3, 3]
    data["fill_direction"] = direction
    data["text_fields"] = []
    store.save_template(data, root, BASE)
    return Session.new(root, name)


@pytest.fixture
def root(tmp_path):
    return tmp_path / "templates"


def placed(session):
    return {cell: item["path"].name for cell, item in sorted(session.placements.items())}


# -- planning (no GUI) -------------------------------------------------------


def test_count_is_repetitions_of_the_whole_copy(root):
    session = make(root)
    plan = session.plan_repeat_paste(2, [A, B], 3)
    assert [cell for cell, _ in plan["targets"]] == [2, 3, 4, 5, 6, 7]
    assert plan["reason"] is None and plan["repeats"] == 3 and plan["extra"] == 0
    session.apply_paste(plan)
    assert placed(session) == {2: "c-1.pdf", 3: "c-2.pdf", 4: "c-1.pdf",
                               5: "c-2.pdf", 6: "c-1.pdf", 7: "c-2.pdf"}


def test_reverse_direction_follows_the_template(root):
    session = make(root, "reverse")
    plan = session.plan_repeat_paste(3, [A], 4)
    # Reverse fill order of a 3x3 grid: 3 2 1 / 6 5 4 / 9 8 7.
    assert [cell for cell, _ in plan["targets"]] == [3, 2, 1, 6]


def test_empty_copied_cells_take_a_cell(root):
    session = make(root)
    plan = session.plan_repeat_paste(1, [A, None], 3)
    session.apply_paste(plan)
    assert placed(session) == {1: "c-1.pdf", 3: "c-1.pdf", 5: "c-1.pdf"}
    assert [cell for cell, _ in plan["targets"]] == [1, 2, 3, 4, 5, 6]


def test_stops_in_front_of_occupied_cell_with_partial_repetition(root):
    session = make(root)
    session.assign(6, B)
    plan = session.plan_repeat_paste(1, [A, A], 5)
    assert [cell for cell, _ in plan["targets"]] == [1, 2, 3, 4, 5]
    assert plan["reason"] == "occupied" and plan["blocked_cell"] == 6
    assert plan["repeats"] == 2 and plan["extra"] == 1 and plan["wanted"] == 10
    session.apply_paste(plan)
    assert placed(session)[6] == "c-2.pdf"  # never replaced


def test_stops_after_last_cell(root):
    session = make(root)
    plan = session.plan_repeat_paste(8, [A, B, A], 2)
    assert [cell for cell, _ in plan["targets"]] == [8, 9]
    assert plan["reason"] == "end_of_cells" and plan["repeats"] == 0 and plan["extra"] == 2


def test_occupied_start_cell_places_nothing(root):
    session = make(root)
    session.assign(4, B)
    plan = session.plan_repeat_paste(4, [A], 3)
    assert plan["targets"] == [] and plan["reason"] == "occupied" and plan["blocked_cell"] == 4


def test_new_cells_are_drawn_on_top(root):
    session = make(root)
    session.assign(9, B)
    session.apply_paste(session.plan_repeat_paste(1, [A], 2))
    orders = {cell: item["order"] for cell, item in session.placements.items()}
    assert orders[9] < orders[1] < orders[2]


def test_remaining_cells(root):
    session = make(root, "reverse")
    assert session.remaining_cells(3) == 9 and session.remaining_cells(7) == 1


# -- work program ------------------------------------------------------------


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, root, monkeypatch):
    make(root)
    shown = []
    for kind in ("question", "warning", "critical", "information"):
        monkeypatch.setattr(
            QMessageBox, kind, lambda *a, _k=kind, **kw: shown.append(_k) or QMessageBox.Ok
        )
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append("box"))
    win = WorkWindow(root)
    win.refresh_templates()
    assert win.start_session("small")
    win.dialogs = shown
    yield win
    win.session.dirty = False
    win.close()


def copy_first_cell(win, path=A):
    win.place_files(1, [str(path)])
    win.view.select(1)
    win.copy_cells()


def test_menu_shortcut_and_state(window):
    action = window.repeat_paste_action
    assert action.shortcut() == QKeySequence("Ctrl+Shift+V")
    assert not action.isEnabled()  # nothing copied yet
    copy_first_cell(window)
    assert action.isEnabled()


def test_dialog_count_pastes_and_logs(window, monkeypatch):
    copy_first_cell(window)
    asked = {}

    def get_int(parent, title, label, value, minimum, maximum, step):
        asked.update(title=title, label=label, value=value, minimum=minimum, maximum=maximum)
        return 3, True

    monkeypatch.setattr(QInputDialog, "getInt", get_int)
    window.view.select(4)
    window.repeat_paste_cells()
    assert asked["value"] == 1 and asked["minimum"] == 1
    assert asked["maximum"] == 6  # cells 4..9
    assert "셀 4부터" in asked["label"]
    assert sorted(window.session.placements) == [1, 4, 5, 6]
    log = window.log.toPlainText()
    assert "연속 붙여넣기: 셀 4~6, 데이터 3개 (반복 3회)" in log
    assert "경고" not in log


def test_cancel_changes_nothing(window, monkeypatch):
    copy_first_cell(window)
    monkeypatch.setattr(QInputDialog, "getInt", lambda *a: (5, False))
    window.view.select(2)
    window.repeat_paste_cells()
    assert sorted(window.session.placements) == [1]


def test_stops_without_dialog_and_warns_in_log(window):
    copy_first_cell(window)
    window.place_files(5, [str(B)])
    window.view.select(2)
    window.repeat_paste_cells(times=6)
    assert sorted(window.session.placements) == [1, 2, 3, 4, 5]
    assert window.session.placements[5]["path"].name == "c-2.pdf"
    assert window.dialogs == []  # no dialog when stopping
    assert "경고 — 연속 붙여넣기가 멈췄습니다. 셀 5에 데이터가 있습니다. 요청 6칸 중 3칸" in (
        window.log.toPlainText()
    )
    window.view.select(8)
    window.repeat_paste_cells(times=4)
    assert "마지막 셀까지 찼습니다. 요청 4칸 중 2칸" in window.log.toPlainText()
    assert window.dialogs == []
