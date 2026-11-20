"""Load data shortcut (Ctrl+E, GitHub issue #37)."""

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu  # noqa: E402

from imposing import store  # noqa: E402
from imposing.gui.work import WorkWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "samples/input/base-front-blank.pdf"
DATA = ROOT / "samples/test03-2/data"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    root = tmp_path / "templates"
    data = json.loads((ROOT / "samples/manual/T31-front-3x8.json").read_text("utf-8"))
    data["name"] = "small"
    data["grid"]["count"] = [3, 3]
    data["text_fields"] = []
    store.save_template(data, root, BASE)
    win = WorkWindow(root)
    yield win
    if win.session:
        win.session.dirty = False
    win.close()


def test_menu_action_has_ctrl_e_and_follows_the_button(window):
    action = window.load_action
    assert action.shortcut() == QKeySequence("Ctrl+E")
    menus = {menu.title(): menu for menu in window.menuBar().findChildren(QMenu)}
    assert action in menus["파일(&F)"].actions()
    assert not action.isEnabled()  # no template yet
    window.start_session("small")
    assert window.view.selected == 1  # a new job starts on the first cell
    assert action.isEnabled() and window.load_button.isEnabled()
    window.view.click(0)
    assert not action.isEnabled() and not window.load_button.isEnabled()
    window.view.click(2)
    assert action.isEnabled()


def test_action_loads_from_the_selected_cell(window, monkeypatch):
    calls = []

    def choose(parent, title, *args, **kwargs):
        calls.append(title)
        return [str(DATA / "c-1.pdf")], ""

    monkeypatch.setattr(QFileDialog, "getOpenFileNames", choose)
    window.start_session("small")
    window.view.click(4)
    window.load_action.trigger()
    assert len(calls) == 1
    assert set(window.session.placements) == {4}
