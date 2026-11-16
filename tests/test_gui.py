import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from imposing import store  # noqa: E402
from imposing.gui.common import create_application  # noqa: E402
from imposing.gui.editor import EditorWindow  # noqa: E402
from imposing.gui.work import WorkWindow, describe_error  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "samples/input/base-front-blank.pdf"
DATA = ROOT / "samples/test03-2/data"


@pytest.fixture(scope="module")
def app():
    return create_application("test")


@pytest.fixture
def dialogs(monkeypatch):
    """Answer every dialog with Yes/Discard and record what was shown."""
    shown = []

    def record(kind, answer):
        def call(parent, title, text, *args, **kwargs):
            shown.append((kind, title, text))
            return answer

        return staticmethod(call)

    monkeypatch.setattr(QMessageBox, "question", record("question", QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "warning", record("warning", QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "critical", record("critical", QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "information", record("information", QMessageBox.Ok))
    monkeypatch.setattr(
        QMessageBox, "exec", lambda self: shown.append(("box", self.windowTitle(), self.text()))
    )
    return shown


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "templates"
    data = json.loads((ROOT / "samples/manual/T31-front-3x8.json").read_text("utf-8"))
    store.save_template(data, root, BASE)
    return root


def test_editor_creates_and_edits_template(app, dialogs, tmp_path):
    root = tmp_path / "templates"
    editor = EditorWindow(root)
    editor.show()
    assert not editor.is_dirty()
    assert editor.save() is False  # no name, no base
    assert dialogs[-1][0] == "warning"
    editor.name_edit.setText("BC-COMBI-전면")
    editor.choose_base(str(BASE))
    editor.add_field()
    editor.table.item(0, 0).setText("제품명")
    assert editor.is_dirty()
    assert editor.save() is True
    assert not editor.is_dirty()
    stored = store.load_template(root, "BC-COMBI-전면")
    assert stored["cell"] == {"size_mm": [85, 50], "rotation_deg": -90}
    assert stored["grid"] == {"origin_mm": [24, 49.5], "count": [3, 8], "pitch_mm": [86, 51]}
    assert stored["text_fields"][0]["id"] == "제품명"
    assert editor.name_edit.isReadOnly()

    # Overlap is a non-blocking note while editing.
    editor.pitch_x.setValue(60)
    assert not editor.warning.isHidden() and "겹칩니다" in editor.warning.text()
    editor.revert()
    assert editor.warning.isHidden() and not editor.is_dirty()

    editor.rotation.setCurrentIndex(editor.rotation.findData(180))
    editor.direction.setCurrentIndex(editor.direction.findData("reverse"))
    editor.count_y.setValue(9)
    assert editor.save() is True
    stored = store.load_template(root, "BC-COMBI-전면")
    assert stored["cell"]["rotation_deg"] == 180
    assert stored["fill_direction"] == "reverse" and stored["grid"]["count"] == [3, 9]

    editor.duplicate_template("BC-COMBI-후면")
    assert store.list_templates(root) == ["BC-COMBI-전면", "BC-COMBI-후면"]
    assert editor.current == "BC-COMBI-후면"
    editor.delete_template()
    assert store.list_templates(root) == ["BC-COMBI-전면"]
    assert editor.current is None
    assert not editor.grab().isNull()
    editor.close()


def test_editor_rejects_duplicate_names(app, dialogs, root):
    editor = EditorWindow(root)
    editor.name_edit.setText("T31-front-3x8")
    editor.choose_base(str(BASE))
    assert editor.save() is False
    assert "이미 있습니다" in dialogs[-1][2]
    editor.name_edit.setText("새 이름")
    editor.add_field()
    editor.add_field()
    editor.table.item(1, 0).setText(editor.table.item(0, 0).text())
    assert editor.save() is False
    assert "겹칩니다" in dialogs[-1][2]
    editor.new_base = None
    editor.new_template(ask=False)
    editor.close()


def test_work_program_flow(app, dialogs, root, tmp_path):
    window = WorkWindow(root)
    window.show()
    assert window.session is None and not window.save_button.isEnabled()
    assert window.start_session("T31-front-3x8")
    assert list(window.text_edits) == ["product", "team", "date"]
    window.text_edits["product"].setText("BC-COMBI")
    assert window.session.texts["product"] == "BC-COMBI"

    files = [str(DATA / f"c-{n}.pdf") for n in (10, 3, 11, 1, 2)]
    window.place_files(22, files)
    assert {c: i["path"].name for c, i in window.session.placements.items()} == {
        22: "c-1.pdf", 23: "c-2.pdf", 24: "c-3.pdf",
    }
    kind, title, text = dialogs[-1]
    assert kind == "warning" and "c-10.pdf" in text and "c-11.pdf" in text

    # One file on an occupied cell replaces it and keeps the order.
    window.place_files(23, [str(DATA / "c-11.pdf")])
    assert dialogs[-1][0] == "question"
    assert window.session.placements[23]["path"].name == "c-11.pdf"
    assert window.session.placements[23]["order"] == 2

    # A file that is not a usable PDF blocks the whole request.
    bad = tmp_path / "bad.pdf"
    bad.write_text("not a pdf", encoding="utf-8")
    window.place_files(1, [str(DATA / "c-1.pdf"), str(bad)])
    assert dialogs[-1][0] == "warning" and 1 not in window.session.placements

    window.view.select(22)
    window.remove_selected()
    assert 22 not in window.session.placements

    # Clicking the preview selects the cell under the pointer.
    centre = window.view.item.cell_rect(5).center()
    assert window.view.item.cell_at(QPointF(centre)) == 5
    assert window.view.item.cell_at(QPointF(1, 1)) == 0

    target = tmp_path / "작업" / "전면-01.pdf"
    window.save_pdf(str(target))
    assert target.is_file() and dialogs[-1][0] == "box"
    assert not window.session.dirty
    # Same name again: the user chooses. "rename" keeps the existing files and
    # uses the next free name; cancel writes nothing.
    window._ask_existing = lambda target, existing: "rename"
    window.save_pdf(str(target))
    assert (tmp_path / "작업" / "전면-01-2.pdf").is_file()
    window._ask_existing = lambda target, existing: None
    window.save_pdf(str(target))
    assert not (tmp_path / "작업" / "전면-01-3.pdf").exists()

    other = WorkWindow(root)
    other.open_project(str(target.with_suffix(".qiproj.json")))
    assert other.session.texts["product"] == "BC-COMBI"
    assert set(other.session.placements) == {23, 24}
    assert other.text_edits["product"].text() == "BC-COMBI"
    assert not other.grab().isNull()
    other.close()
    window.close()


def test_work_program_reports_errors(app, dialogs, root, tmp_path):
    window = WorkWindow(root)
    broken = tmp_path / "x.qiproj.json"
    broken.write_text("{}", encoding="utf-8")
    window.open_project(str(broken))
    assert dialogs[-1][0] == "critical" and window.session is None

    data = store.load_template(root, "T31-front-3x8")
    data["name"] = "overlap"
    data["grid"]["pitch_mm"] = [60, 51]
    data["text_fields"][0]["font"] = "No Such Font 123"
    store.save_template(data, root, BASE)
    window.refresh_templates()
    assert window.start_session("overlap")
    assert not window.banner.isHidden() and "겹칩니다" in window.banner.text()
    window.place_files(1, [str(DATA / "c-1.pdf")])
    window.save_pdf(str(tmp_path / "out" / "x.pdf"))
    assert dialogs[-1][0] == "critical" and "글꼴" in dialogs[-1][2]
    assert not (tmp_path / "out" / "x.pdf").exists()
    window.session.dirty = False
    window.close()


def test_error_text():
    assert "셀 25" in describe_error(dict(code="CELL_NOT_IN_TEMPLATE", cell=25))
    assert "글꼴" in describe_error(dict(code="FONT_GLYPH_MISSING", reason="x", font="F"))
    assert "X" in describe_error(dict(code="SCHEMA_INVALID", reason="X"))


def test_program_icons(app):
    from PIL import Image
    from PySide6.QtGui import QIcon

    assets = ROOT / "imposing/gui/assets"
    for name in ("work", "editor"):
        with Image.open(assets / f"{name}.ico") as icon:
            assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(icon.info["sizes"])
        assert not QIcon(str(assets / f"{name}.png")).isNull()
    application = create_application("test", "editor")
    assert not application.windowIcon().isNull()


def test_text_position_does_not_move_the_sheet(app):
    """Moving a text field must not shift the sheet inside the preview."""
    from imposing.gui.common import SheetView

    definition = json.loads((ROOT / "samples/manual/T31-front-3x8.json").read_text("utf-8"))
    view = SheetView()
    view.resize(520, 800)
    view.show()

    def margins(x, y=14):
        definition["text_fields"][2]["x_mm"] = x
        definition["text_fields"][2]["y_mm"] = y
        view.set_sheet(BASE, definition)
        app.processEvents()
        left = view.mapFromScene(QPointF(0, 0))
        right = view.mapFromScene(QPointF(305, 506))
        return left.x(), view.viewport().width() - right.x(), left.y()

    reference = margins(35)
    assert abs(reference[0] - reference[1]) <= 1
    for x, y in ((190, 14), (200, 14), (235, 14), (300, 14), (1, 14), (-20, 14), (35, 2), (400, -30)):
        assert margins(x, y) == reference, (x, y)

    # Cells that leave the sheet still widen the view so they stay visible.
    definition["grid"]["origin_mm"] = [150, 49.5]
    assert margins(35) != reference
    view.close()


def test_multi_selection(app, root):
    from PySide6.QtCore import Qt

    window = WorkWindow(root)
    window.show()
    window.start_session("T31-front-3x8")
    view = window.view
    view.click(2)
    assert view.selected == 2 and view.selected_cells == [2]
    view.click(5, Qt.ShiftModifier)  # range in fill order, pivot stays on 2
    assert view.selected_cells == [2, 3, 4, 5] and view.selected == 2
    view.click(9, Qt.ControlModifier)
    assert view.selected_cells == [2, 3, 4, 5, 9] and view.selected == 9
    view.click(3, Qt.ControlModifier)  # Ctrl+click again takes a cell out
    assert view.selected_cells == [2, 4, 5, 9]
    view.click(7)
    assert view.selected_cells == [7]
    view.select_all()
    assert len(view.selected_cells) == 24
    view.click(0)
    assert view.selected == 0 and view.selected_cells == []
    assert not window.grab().isNull()
    window.close()


def test_copy_and_paste_cells(app, dialogs, root):
    from PySide6.QtCore import Qt

    window = WorkWindow(root)
    window.show()
    window.start_session("T31-front-3x8")
    view, session = window.view, None
    window.place_files(1, [str(DATA / f"c-{n}.pdf") for n in (1, 2)])  # cells 1, 2
    session = window.session
    assert not window.paste_action.isEnabled()  # nothing copied yet

    view.click(1)
    view.click(3, Qt.ShiftModifier)  # cells 1 2 3 (3 is empty)
    assert window.copy_action.isEnabled()
    window.copy_cells()
    assert [p.name if p else None for p in window.clipboard] == ["c-1.pdf", "c-2.pdf", None]

    # Paste onto empty cells: no question is asked.
    before = len(dialogs)
    view.click(10)
    assert window.paste_action.isEnabled()
    window.paste_cells()
    assert len(dialogs) == before
    assert {c: i["path"].name for c, i in session.placements.items()} == {
        1: "c-1.pdf", 2: "c-2.pdf", 10: "c-1.pdf", 11: "c-2.pdf",
    }

    # Paste over existing data: one question; replaced keeps order, empty clears.
    window.place_files(12, [str(DATA / "c-3.pdf")])
    order_11 = session.placements[11]["order"]
    view.click(11)
    window.paste_cells()
    kind, title, text = dialogs[-1]
    assert kind == "question" and "2개" in text
    assert session.placements[11]["path"].name == "c-1.pdf"
    assert session.placements[11]["order"] == order_11
    assert session.placements[12]["path"].name == "c-2.pdf"
    assert 13 not in session.placements

    # Past the last cell: paste what fits, then warn.
    view.click(24)
    window.paste_cells()
    assert session.placements[24]["path"].name == "c-1.pdf"
    kind, title, text = dialogs[-1]
    assert kind == "warning" and "c-2.pdf" in text

    # Delete empties every selected cell.
    view.click(10)
    view.click(12, Qt.ShiftModifier)
    window.remove_selected()
    assert not {10, 11, 12} & set(session.placements)

    # The copied cells survive a new job.
    window.session.dirty = False
    window.new_job()
    window.view.click(1)
    window.paste_cells()
    assert window.session.placements[2]["path"].name == "c-2.pdf"
    window.session.dirty = False
    window.close()


def test_paste_can_be_declined(app, root, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
    window = WorkWindow(root)
    window.start_session("T31-front-3x8")
    window.place_files(1, [str(DATA / "c-1.pdf")])
    window.place_files(2, [str(DATA / "c-2.pdf")])
    window.view.click(1)
    window.copy_cells()
    window.view.click(2)
    window.paste_cells()
    assert window.session.placements[2]["path"].name == "c-2.pdf"
    window.session.dirty = False
    window.close()


def test_text_field_keeps_its_own_copy_and_paste(app, dialogs, root):
    """Ctrl+C / Ctrl+V typed in a text box edit the text, not the cells."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    window = WorkWindow(root)
    window.show()
    window.activateWindow()
    window.start_session("T31-front-3x8")
    window.place_files(1, [str(DATA / "c-1.pdf")])
    window.view.click(1)
    window.copy_cells()
    edit = window.text_edits["product"]
    edit.setFocus()
    app.processEvents()
    QGuiApplication.clipboard().setText("제품A")
    QTest.keyClick(edit, Qt.Key_V, Qt.ControlModifier)
    app.processEvents()
    if edit.hasFocus():  # focus needs an active window; skip the check otherwise
        assert edit.text() == "제품A"
        assert set(window.session.placements) == {1}
    window.session.dirty = False
    window.close()


def test_editor_shows_cell_coordinates(app, dialogs, root):
    """Clicking a cell shows its top-left corner in mm (grid: origin 24, 49.5; pitch 86, 51)."""
    editor = EditorWindow(root)
    editor.show()
    assert "누르면" in editor.cell_label.text()
    editor.open_template("T31-front-3x8")
    editor.view.click(1)
    assert editor.cell_position(1) == (1, 1, 24, 49.5, 109, 99.5)
    assert editor.cell_label.text() == "X24, Y49.5 mm 85x50mm"
    editor.view.click(24)  # row 8, column 3
    assert editor.cell_position(24) == (8, 3, 24 + 2 * 86, 49.5 + 7 * 51, 281, 456.5)
    assert editor.cell_label.text() == "X196, Y406.5 mm 85x50mm"
    # The readout follows edits to the grid.
    editor.origin_x.setValue(30)
    editor.pitch_y.setValue(52.25)
    assert editor.cell_label.text() == "X202, Y415.25 mm 85x50mm"
    editor.cell_w.setValue(56)
    editor.cell_h.setValue(80)
    assert editor.cell_label.text() == "X202, Y415.25 mm 56x80mm"
    editor.view.click(0)
    assert "누르면" in editor.cell_label.text()
    editor.revert()
    editor.close()
