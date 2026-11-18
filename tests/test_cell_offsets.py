"""Per-cell position correction (cell_offsets): SPEC §6.1, requirements §5."""

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from imposing import store  # noqa: E402
from imposing.gui.editor import EditorWindow  # noqa: E402
from imposing.model import base_cells, cells, overlap_pairs, template_errors  # noqa: E402
from imposing.pdf import MM  # noqa: E402
from imposing.session import Session  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "samples/input/base-front-blank.pdf"
DATA = ROOT / "samples/test03-2/data"


def definition(name="small", offsets=None):
    data = json.loads((ROOT / "samples/manual/T31-front-3x8.json").read_text("utf-8"))
    data["name"] = name
    data["grid"]["count"] = [3, 3]
    data["text_fields"] = []
    if offsets is not None:
        data["cell_offsets"] = offsets
    return data


# -- model -------------------------------------------------------------------


def test_offset_is_added_to_the_grid_position():
    plain = definition()
    corrected = definition(offsets={"1": [2, 3], "5": [-0.5, 0]})
    base = base_cells(corrected)
    assert base == cells(plain)
    actual = cells(corrected)
    assert actual[1] == (base[1][0] + 2, base[1][1] + 3)
    assert actual[5] == (base[5][0] - 0.5, base[5][1])
    assert all(actual[c] == base[c] for c in base if c not in (1, 5))


def test_no_offsets_means_unchanged_positions():
    assert cells(definition(offsets={})) == cells(definition())


@pytest.mark.parametrize(
    "offsets",
    [
        {"1": [2]},  # not a pair
        {"1": ["a", 1]},
        {"0": [1, 1]},  # no cell 0
        {"10": [1, 1]},  # 3x3 has 9 cells
        {"x": [1, 1]},
        [[1, 1]],  # not an object
    ],
)
def test_invalid_offsets_are_schema_errors(offsets):
    errors = template_errors(definition(offsets=offsets))
    assert [e["field"] for e in errors] == ["cell_offsets"]


def test_valid_offsets_pass_and_have_no_limit():
    assert template_errors(definition(offsets={"9": [-1000, 2500.25]})) == []


def test_offset_can_cause_overlap():
    corrected = definition(offsets={"2": [-60, 0]})
    assert [1, 2] in overlap_pairs(cells(corrected), corrected["cell"]["size_mm"])


# -- PDF and report ---------------------------------------------------------


def build(root, tmp_path, name):
    session = Session.new(root, name)
    session.assign(1, DATA / "c-1.pdf")
    session.assign(2, DATA / "c-2.pdf")
    report = session.save(tmp_path / name / "out.pdf")
    assert report["status"] == "PASS", report["errors"]
    return {entry["cell"]: entry for entry in report["placements"]}


def test_pdf_and_report_use_the_corrected_position(tmp_path):
    root = tmp_path / "templates"
    store.save_template(definition("plain"), root, BASE)
    store.save_template(definition("shifted", offsets={"1": [2, 3]}), root, BASE)
    plain = build(root, tmp_path, "plain")
    shifted = build(root, tmp_path, "shifted")
    # Cell 1 moves 2 mm right and 3 mm down; PDF y grows upward.
    assert shifted[1]["xy_mm"] == [plain[1]["xy_mm"][0] + 2, plain[1]["xy_mm"][1] + 3]
    assert shifted[1]["offset_mm"] == [2.0, 3.0]
    assert shifted[1]["cm"][4] == pytest.approx(plain[1]["cm"][4] + 2 * MM)
    assert shifted[1]["cm"][5] == pytest.approx(plain[1]["cm"][5] - 3 * MM)
    assert shifted[1]["cm"][:4] == plain[1]["cm"][:4]
    # Uncorrected cells are unchanged and carry no offset entry.
    assert shifted[2]["cm"] == plain[2]["cm"]
    assert "offset_mm" not in shifted[2] and "offset_mm" not in plain[1]


def test_report_without_offsets_is_unchanged(tmp_path):
    root = tmp_path / "templates"
    store.save_template(definition("plain"), root, BASE)
    assert all("offset_mm" not in entry for entry in build(root, tmp_path, "plain").values())


# -- template editor --------------------------------------------------------


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(app, tmp_path, monkeypatch):
    shown = []
    for kind in ("question", "warning", "critical", "information"):
        monkeypatch.setattr(
            QMessageBox, kind, lambda *a, _k=kind, **kw: shown.append(_k) or QMessageBox.Yes
        )
    root = tmp_path / "templates"
    store.save_template(definition(), root, BASE)
    win = EditorWindow(root)
    win.open_template("small")
    win.dialogs = shown
    yield win
    win.saved = win.definition()
    win.close()


def test_editor_sets_offset_for_selected_cell(editor):
    base = cells(editor.definition())
    editor.view.select(1)
    assert editor.offset_x.isEnabled() and editor.offset_x.value() == 0
    assert "보정" not in editor.cell_label.text()
    editor.offset_x.setValue(2)
    editor.offset_y.setValue(3)
    assert editor.definition()["cell_offsets"] == {"1": [2, 3]}
    assert editor.view.item.positions[1] == (base[1][0] + 2, base[1][1] + 3)
    assert "(보정 X+2, Y+3)" in editor.cell_label.text()
    assert "위치를 보정한 셀: 1" in editor.grid_note.text()
    assert editor.is_dirty()
    assert editor.save() is True
    assert store.load_template(editor.root, "small")["cell_offsets"] == {"1": [2, 3]}
    # Reopening shows the stored correction for the selected cell.
    editor.open_template("small")
    editor.view.select(1)
    assert (editor.offset_x.value(), editor.offset_y.value()) == (2, 3)
    editor.view.select(2)
    assert (editor.offset_x.value(), editor.offset_y.value()) == (0, 0)


def test_zero_offset_removes_the_entry(editor):
    editor.view.select(4)
    editor.offset_y.setValue(-1.5)
    assert editor.definition()["cell_offsets"] == {"4": [0, -1.5]}
    editor.offset_y.setValue(0)
    assert "cell_offsets" not in editor.definition()


def test_clear_buttons(editor):
    for cell, value in ((1, 1), (2, 2), (3, 3)):
        editor.view.select(cell)
        editor.offset_x.setValue(value)
    editor.view.select(2)
    editor.offset_clear.click()
    assert sorted(editor.definition()["cell_offsets"]) == ["1", "3"]
    editor.offset_clear_all.click()
    assert "cell_offsets" not in editor.definition()
    assert editor.offset_x.value() == 0


def test_fewer_cells_drop_offsets_silently(editor):
    editor.view.select(9)
    editor.offset_x.setValue(5)
    editor.view.select(1)
    editor.offset_x.setValue(1)
    editor.count_y.setValue(2)  # 9 cells -> 6
    assert editor.definition()["cell_offsets"] == {"1": [1, 0]}
    editor.count_y.setValue(3)  # growing back does not restore it
    assert editor.definition()["cell_offsets"] == {"1": [1, 0]}
    assert editor.dialogs == []


def test_grid_change_keeps_offsets(editor):
    editor.view.select(5)
    editor.offset_x.setValue(2)
    editor.pitch_x.setValue(editor.pitch_x.value() + 10)
    base = base_cells(editor.definition())
    assert editor.definition()["cell_offsets"] == {"5": [2, 0]}
    assert editor.view.item.positions[5] == (base[5][0] + 2, base[5][1])


def test_new_template_has_no_offsets(editor):
    editor.view.select(1)
    editor.offset_x.setValue(3)
    editor.saved = editor.definition()  # avoid the discard question
    editor.new_template(ask=False)
    assert editor.offsets == {} and "cell_offsets" not in editor.definition()


def test_corrected_cells_are_marked_in_editor_only(editor):
    editor.view.select(1)
    editor.offset_x.setValue(2)
    assert editor.view.item.show_offsets is True
    assert not editor.view.grab().isNull()


def test_work_session_uses_corrected_positions(tmp_path):
    root = tmp_path / "templates"
    store.save_template(definition("shifted", offsets={"3": [0, 4]}), root, BASE)
    session = Session.new(root, "shifted")
    base = base_cells(session.template)
    assert session.cell_positions()[3] == (base[3][0], base[3][1] + 4)
