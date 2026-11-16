"""Template memo (editor writes, work program reads) and PDF overwrite."""

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from imposing import store  # noqa: E402
from imposing.engine import generate  # noqa: E402
from imposing.gui.editor import EditorWindow  # noqa: E402
from imposing.gui.work import WorkWindow  # noqa: E402
from imposing.model import template_errors  # noqa: E402
from imposing.session import Session, SessionError, output_files  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "samples/input/base-front-blank.pdf"
DATA = ROOT / "samples/test03-2/data"


def definition(name="small", memo=None):
    data = json.loads((ROOT / "samples/manual/T31-front-3x8.json").read_text("utf-8"))
    data["name"] = name
    data["grid"]["count"] = [3, 3]
    data["text_fields"] = []
    if memo is not None:
        data["memo"] = memo
    return data


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "templates"
    store.save_template(definition(), root, BASE)
    return root


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialogs(monkeypatch):
    shown = []

    def record(kind, answer):
        def call(parent, title, text, *args, **kwargs):
            shown.append((kind, title, text))
            return answer

        return call

    for kind, answer in (
        ("question", QMessageBox.Yes),
        ("warning", QMessageBox.Ok),
        ("critical", QMessageBox.Ok),
        ("information", QMessageBox.Ok),
    ):
        monkeypatch.setattr(QMessageBox, kind, record(kind, answer))
    monkeypatch.setattr(
        QMessageBox, "exec", lambda self: shown.append(("box", self.windowTitle(), self.text()))
    )
    return shown


# -- memo -------------------------------------------------------------------


def test_memo_is_optional_string():
    assert template_errors(definition()) == []
    assert template_errors(definition(memo="A4 · 전면")) == []
    errors = template_errors(definition(memo=3))
    assert [e["field"] for e in errors] == ["memo"]


def test_memo_does_not_change_the_pdf(root, tmp_path):
    store.save_template(definition("memo", memo="주의"), root, BASE)
    reports = []
    for name in ("small", "memo"):
        session = Session.new(root, name)
        session.assign(1, DATA / "c-1.pdf")
        reports.append(session.save(tmp_path / name / "out.pdf"))
    assert all(r["status"] == "PASS" for r in reports)
    assert reports[0]["placements"] == reports[1]["placements"]


def test_editor_edits_memo(app, dialogs, root):
    editor = EditorWindow(root)
    editor.open_template("small")
    assert editor.memo_edit.toPlainText() == "" and not editor.is_dirty()
    assert "memo" not in editor.definition()
    editor.memo_edit.setPlainText("  A3 용지\n재단 주의  ")
    assert editor.is_dirty()
    assert editor.save() is True
    assert store.load_template(root, "small")["memo"] == "A3 용지\n재단 주의"
    editor.open_template("small")
    assert editor.memo_edit.toPlainText() == "A3 용지\n재단 주의"
    assert not editor.is_dirty()
    # Clearing the memo removes the key again.
    editor.memo_edit.setPlainText("")
    assert editor.save() is True
    assert "memo" not in store.load_template(root, "small")
    editor.close()


def test_work_program_shows_memo_read_only(app, dialogs, root):
    store.save_template(definition("memo", memo="A3 용지"), root, BASE)
    window = WorkWindow(root)
    window.refresh_templates()
    assert window.start_session("memo")
    assert window.memo_view.isReadOnly()
    assert window.memo_view.toPlainText() == "A3 용지"
    assert not window.memo_view.isHidden()
    # A template without a memo hides the box.
    window.session.dirty = False
    assert window.start_session("small")
    assert window.memo_view.isHidden() and window.memo_label.isHidden()
    # An edit in the template editor is followed while the job is open.
    window.session.dirty = False
    assert window.start_session("memo")
    store.save_template(definition("memo", memo="바뀐 메모"), root)
    window._reload_changed_template()
    assert window.memo_view.toPlainText() == "바뀐 메모"
    window.session.dirty = False
    window.close()


# -- overwrite --------------------------------------------------------------


def built_session(root, *cards):
    session = Session.new(root, "small")
    for cell, number in enumerate(cards, 1):
        session.assign(cell, DATA / f"c-{number}.pdf")
    return session


def test_save_refuses_existing_without_overwrite(root, tmp_path):
    target = tmp_path / "out" / "x.pdf"
    assert built_session(root, 1).save(target)["status"] == "PASS"
    with pytest.raises(SessionError) as error:
        built_session(root, 2).save(target)
    assert error.value.code == "OUTPUT_EXISTS"


def test_overwrite_replaces_all_four_files(root, tmp_path):
    target = tmp_path / "out" / "x.pdf"
    built_session(root, 1).save(target)
    before = {path.name: path.read_bytes() for path in output_files(target)}
    report = built_session(root, 2, 3).save(target, overwrite=True)
    assert report["status"] == "PASS"
    after = {path.name: path.read_bytes() for path in output_files(target)}
    assert set(after) == set(before)
    assert all(after[name] != before[name] for name in before)
    project = json.loads(target.with_suffix(".qiproj.json").read_text("utf-8"))
    assert [Path(item["file"]).name for item in project["placements"]] == ["c-2.pdf", "c-3.pdf"]
    saved = json.loads(target.with_suffix(".report.json").read_text("utf-8"))
    assert saved == report
    # Nothing else is left in the folder (no staging files).
    assert sorted(p.name for p in target.parent.iterdir()) == sorted(before)


def test_failed_overwrite_keeps_existing_files(root, tmp_path):
    target = tmp_path / "out" / "x.pdf"
    built_session(root, 1).save(target)
    before = {path.name: path.read_bytes() for path in output_files(target)}
    data = definition("nofont")
    data["text_fields"] = [
        dict(id="t", x_mm=10, y_mm=10, size_pt=10, font="No Such Font 135")
    ]
    store.save_template(data, root, BASE)
    session = Session.new(root, "nofont")
    report = session.save(target, overwrite=True)
    assert report["status"] == "FAIL"
    assert report["errors"][0]["code"] == "FONT_NOT_FOUND"
    assert {path.name: path.read_bytes() for path in output_files(target)} == before


def test_overwrite_of_locked_file_is_explained(root, tmp_path, monkeypatch):
    target = tmp_path / "out" / "x.pdf"
    built_session(root, 1).save(target)
    before = target.read_bytes()

    def locked(*args):
        raise PermissionError("[WinError 32] used by another process")

    monkeypatch.setattr(os, "replace", locked)
    with pytest.raises(SessionError) as error:
        built_session(root, 2).save(target, overwrite=True)
    assert error.value.code == "OUTPUT_LOCKED"
    assert "열려 있으면" in str(error.value)
    assert target.read_bytes() == before


def test_engine_overwrite(root, tmp_path):
    session = built_session(root, 1)
    project = tmp_path / "p.qiproj.json"
    project.write_text(json.dumps(session.to_project(tmp_path)), encoding="utf-8")
    output = tmp_path / "out" / "r.pdf"
    assert generate(project, root, output)["status"] == "PASS"
    with pytest.raises(FileExistsError):
        generate(project, root, output)
    assert generate(project, root, output, overwrite=True)["status"] == "PASS"
    # A directory in the way is never overwritten.
    blocked = tmp_path / "out" / "d.pdf"
    blocked.mkdir()
    with pytest.raises(FileExistsError):
        generate(project, root, blocked, overwrite=True)


def test_work_program_overwrite_choice(app, dialogs, root, tmp_path):
    window = WorkWindow(root)
    window.refresh_templates()
    assert window.start_session("small")
    window.place_files(1, [str(DATA / "c-1.pdf")])
    target = tmp_path / "out" / "x.pdf"
    window.save_pdf(str(target))
    first = target.read_bytes()
    asked = []

    def choose(answer):
        def ask(target, existing):
            asked.append(sorted(path.name for path in existing))
            return answer

        return ask

    window.place_files(2, [str(DATA / "c-2.pdf")])
    window._ask_existing = choose("overwrite")
    window.save_pdf(str(target))
    assert asked[-1] == sorted(path.name for path in output_files(target))
    assert target.read_bytes() != first
    assert not (tmp_path / "out" / "x-2.pdf").exists()
    assert not window.session.dirty
    window.close()


def test_existing_dialog_buttons(app, root, tmp_path, monkeypatch):
    window = WorkWindow(root)
    target = tmp_path / "x.pdf"
    target.write_bytes(b"old")
    seen = {}

    def exec_(box):
        seen["buttons"] = [button.text() for button in box.buttons()]
        seen["default"] = box.defaultButton().text()
        box.buttons()[0].click()  # first added: 덮어쓰기

    monkeypatch.setattr(QMessageBox, "exec", exec_)
    window._ask_existing(target, [target])
    assert "덮어쓰기" in seen["buttons"] and "취소" in seen["buttons"]
    assert seen["default"] == "'x-2.pdf'(으)로 저장"  # the safe choice is default
    window.close()


def run_cli(*args):
    import subprocess
    import sys

    return subprocess.run(
        [sys.executable, "-m", "imposing", *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_cli_overwrite(root, tmp_path):
    session = built_session(root, 1)
    project = tmp_path / "p.qiproj.json"
    project.write_text(json.dumps(session.to_project(tmp_path)), encoding="utf-8")
    output = tmp_path / "out" / "r.pdf"
    build = ("build", project, "--templates-root", root, "--output", output)
    assert run_cli(*build).returncode == 0
    first = output.read_bytes()
    refused = run_cli(*build)
    assert refused.returncode == 1 and "Refusing to overwrite" in refused.stderr
    assert output.read_bytes() == first
    replaced = run_cli(*build, "--overwrite")
    assert replaced.returncode == 0, replaced.stderr
    assert '"status": "PASS"' in replaced.stdout


def test_cli_rebuilds_saved_project_in_place(root, tmp_path):
    # Typical use: fix a template, then rebuild a saved job onto its own name.
    target = tmp_path / "out" / "x.pdf"
    built_session(root, 1, 2).save(target)
    saved = target.with_suffix(".qiproj.json")
    before = json.loads(saved.read_text("utf-8"))
    result = run_cli(
        "build", saved, "--templates-root", root, "--output", target, "--overwrite"
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(saved.read_text("utf-8")) == before
    # Without --overwrite the existing files are refused as before.
    assert run_cli("build", saved, "--templates-root", root, "--output", target).returncode == 1
