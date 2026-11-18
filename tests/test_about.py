"""Tools → 프로그램 정보: version and repository link."""

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from imposing.gui import common  # noqa: E402
from imposing.gui.common import REPOSITORY_URL, about_box, app_version  # noqa: E402
from imposing.gui.work import WorkWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def project_version():
    import tomllib

    return tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]


def test_source_run_reads_pyproject():
    assert app_version() == project_version()


def test_packaged_build_reads_version_file(tmp_path, monkeypatch):
    (tmp_path / "VERSION.txt").write_text("9.8.7\r\n", encoding="ascii")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "QuickImposing.exe"))
    assert app_version() == "9.8.7"


def test_unknown_version_is_shown_as_such(app, monkeypatch):
    monkeypatch.setattr(common, "app_version", lambda: None)
    assert "알 수 없음" in about_box(None).text()


def test_about_box_has_version_and_link(app):
    box = about_box(None)
    assert box.windowTitle() == "프로그램 정보"
    assert box.text().startswith("<b>퀵 임포징</b><br><br>")  # no "— 작업"
    assert "작업" not in box.text()
    assert f"버전 {project_version()}" in box.text()
    assert f'<a href="{REPOSITORY_URL}">' in box.text()
    assert box.textFormat() == Qt.RichText
    assert box.textInteractionFlags() & Qt.LinksAccessibleByMouse
    assert REPOSITORY_URL == "https://github.com/steves460ng/quick-imposing"


def test_tools_menu_opens_about(app, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(
        QMessageBox, "exec", lambda self: shown.append((self.windowTitle(), self.text()))
    )
    window = WorkWindow(tmp_path)
    from PySide6.QtGui import QAction

    about = [a for a in window.findChildren(QAction) if a.text() == "프로그램 정보(&A)…"]
    assert len(about) == 1
    about[0].trigger()
    assert shown and shown[-1][0] == "프로그램 정보"
    assert REPOSITORY_URL in shown[-1][1]
    window.close()
