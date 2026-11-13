"""Work program: pick a template, put B files into cells, save the PDF."""

from datetime import datetime
from pathlib import Path
import sys

from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import store
from ..session import Session, SessionError, free_output_path, output_files
from .common import (
    SheetView,
    Thumbs,
    create_application,
    number_text,
    open_folder,
    tools_ready,
)

ROTATION_TEXT = {0: "0°", 90: "90°", -90: "−90°", 180: "180°"}
DIRECTION_TEXT = {"forward": "정방향", "reverse": "역방향"}

ERROR_TEXT = {
    "CELL_NOT_IN_TEMPLATE": "현재 템플릿에 없는 셀이 있습니다: 셀 {cell}",
    "TEMPLATE_NOT_FOUND": "템플릿을 찾을 수 없습니다: {template}",
    "FONT_NOT_FOUND": "글꼴을 찾을 수 없습니다: {font}\n이 PC에 글꼴을 설치하거나 템플릿의 글꼴을 바꾸세요.",
    "PDF_VALIDATION_FAILED": "만든 PDF가 검사를 통과하지 못했습니다.\n{reason}",
    "INPUT_CHANGED": "저장하는 동안 입력 파일이 바뀌었습니다. 다시 저장하세요.",
}


def describe_error(entry):
    """One Korean sentence for a build report error entry."""
    code = entry.get("code", "")
    if code == "SCHEMA_INVALID":
        reason = entry.get("reason") or entry.get("field") or ""
        if "lacks characters" in reason:
            return "선택한 글꼴에 없는 글자가 있습니다. 입력한 텍스트나 템플릿의 글꼴을 확인하세요."
        if "prohibits embedding" in reason:
            return "PDF에 넣을 수 없는(임베드 금지) 글꼴입니다. 템플릿의 글꼴을 바꾸세요."
        return f"입력을 처리할 수 없습니다.\n{reason}"
    template = ERROR_TEXT.get(code)
    if template is None:
        return f"{code} {entry}"
    values = {key: entry.get(key, "") for key in ("cell", "template", "font", "reason")}
    return template.format(**values)


class WorkWindow(QMainWindow):
    def __init__(self, root=None):
        super().__init__()
        self.root = Path(root) if root else store.default_templates_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.session = None
        self.thumbs = Thumbs()
        self.text_edits = {}
        self.last_folder = str(Path.home())
        self.setWindowTitle("퀵 임포징 — 작업")
        self.resize(1180, 860)
        self._build_ui()
        self._build_menu()
        self.refresh_templates()
        self._update_state()

    # -- construction -----------------------------------------------------

    def _build_ui(self):
        self.template_combo = QComboBox()
        self.template_combo.setPlaceholderText("템플릿을 선택하세요")
        self.template_combo.activated.connect(self._template_chosen)
        self.template_info = QLabel("")
        self.template_info.setObjectName("hint")
        self.template_info.setWordWrap(True)
        template_box = QGroupBox("1. 템플릿")
        layout = QVBoxLayout(template_box)
        layout.addWidget(self.template_combo)
        layout.addWidget(self.template_info)

        self.text_box = QGroupBox("2. 텍스트")
        self.text_form = QFormLayout(self.text_box)
        self.no_text_label = QLabel("이 템플릿에는 텍스트 항목이 없습니다.")
        self.no_text_label.setObjectName("hint")
        self.text_form.addRow(self.no_text_label)

        self.cell_info = QLabel("")
        self.cell_info.setWordWrap(True)
        self.load_button = QPushButton("B 불러오기…")
        self.load_button.clicked.connect(self.load_files)
        self.remove_button = QPushButton("셀 비우기")
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button = QPushButton("모두 비우기")
        self.clear_button.clicked.connect(self.clear_all)
        hint = QLabel(
            "셀을 누르고 B를 불러옵니다. 파일을 여러 개 고르면 선택한 셀부터 "
            "파일 이름 순서로 채웁니다. 탐색기에서 셀로 끌어다 놓아도 됩니다."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        data_box = QGroupBox("3. B 데이터")
        layout = QVBoxLayout(data_box)
        layout.addWidget(self.cell_info)
        layout.addWidget(self.load_button)
        row = QHBoxLayout()
        row.addWidget(self.remove_button)
        row.addWidget(self.clear_button)
        layout.addLayout(row)
        layout.addWidget(hint)

        self.save_button = QPushButton("PDF 저장…")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_pdf)
        self.count_label = QLabel("")
        self.count_label.setObjectName("hint")
        save_box = QGroupBox("4. 저장")
        layout = QVBoxLayout(save_box)
        layout.addWidget(self.count_label)
        layout.addWidget(self.save_button)

        panel = QWidget()
        column = QVBoxLayout(panel)
        column.addWidget(template_box)
        column.addWidget(self.text_box)
        column.addWidget(data_box)
        column.addWidget(save_box)
        column.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(310)
        scroll.setMaximumWidth(380)

        self.banner = QLabel("")
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        self.view = SheetView(self.thumbs)
        self.view.item.show_field_names = True
        self.view.cellSelected.connect(lambda _: self._update_state())
        self.view.cellActivated.connect(lambda _: self.load_files())
        self.view.filesDropped.connect(self.place_files)
        self.empty_label = QLabel("")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(96)
        self.log.setPlaceholderText("알림이 여기에 표시됩니다.")
        zoom_row = QHBoxLayout()
        zoom_hint = QLabel("Ctrl + 휠: 확대·축소")
        zoom_hint.setObjectName("hint")
        fit_button = QPushButton("화면에 맞춤")
        fit_button.clicked.connect(self.view.fit)
        zoom_row.addWidget(zoom_hint)
        zoom_row.addStretch(1)
        zoom_row.addWidget(fit_button)

        right = QWidget()
        column = QVBoxLayout(right)
        column.addWidget(self.banner)
        column.addWidget(self.empty_label, 1)
        column.addWidget(self.view, 1)
        column.addLayout(zoom_row)
        column.addWidget(self.log)

        splitter = QSplitter()
        splitter.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)
        self.statusBar().showMessage(f"템플릿 폴더: {self.root}")

    def _build_menu(self):
        menu = self.menuBar().addMenu("파일(&F)")
        action = QAction("새 작업(&N)", self, shortcut=QKeySequence.New)
        action.triggered.connect(self.new_job)
        menu.addAction(action)
        action = QAction("프로젝트 열기(&O)…", self, shortcut=QKeySequence.Open)
        action.triggered.connect(self.open_project)
        menu.addAction(action)
        action = QAction("PDF 저장(&S)…", self, shortcut=QKeySequence.Save)
        action.triggered.connect(self.save_pdf)
        menu.addAction(action)
        menu.addSeparator()
        action = QAction("끝내기(&X)", self)
        action.triggered.connect(self.close)
        menu.addAction(action)

        menu = self.menuBar().addMenu("도구(&T)")
        action = QAction("템플릿 편집기 열기", self)
        action.triggered.connect(self.launch_editor)
        menu.addAction(action)
        action = QAction("템플릿 폴더 열기", self)
        action.triggered.connect(lambda: open_folder(self.root))
        menu.addAction(action)
        action = QAction("템플릿 목록 새로 고침", self, shortcut=QKeySequence.Refresh)
        action.triggered.connect(self.refresh_templates)
        menu.addAction(action)

        delete = QAction(self, shortcut=QKeySequence.Delete)
        delete.triggered.connect(self.remove_selected)
        self.addAction(delete)

    # -- templates --------------------------------------------------------

    def refresh_templates(self):
        current = self.session.template_name if self.session else None
        names = store.list_templates(self.root)
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        self.template_combo.addItems(names)
        self.template_combo.setCurrentIndex(names.index(current) if current in names else -1)
        self.template_combo.blockSignals(False)
        self._update_state()

    def _template_chosen(self, index):
        name = self.template_combo.itemText(index)
        if self.session and name == self.session.template_name:
            return
        if not self._confirm_discard():
            self.refresh_templates()
            return
        self.start_session(name)

    def start_session(self, name):
        try:
            session = Session.new(self.root, name)
        except store.TemplateError as exc:
            QMessageBox.critical(self, "템플릿을 열 수 없습니다", str(exc))
            self.refresh_templates()
            return False
        self._adopt(session)
        self.notify(f"템플릿 '{name}'을(를) 불러왔습니다.")
        return True

    def _adopt(self, session):
        self.session = session
        definition = session.template
        self.view.fitted = True
        self.view.item.selected = 0
        self.view.set_sheet(store.base_path(self.root, session.template_name), definition)
        self.view.set_placements(session.placements)
        self.view.set_texts(session.texts)
        index = self.template_combo.findText(session.template_name)
        self.template_combo.blockSignals(True)
        self.template_combo.setCurrentIndex(index)
        self.template_combo.blockSignals(False)
        w, h = definition["cell"]["size_mm"]
        nx, ny = definition["grid"]["count"]
        self.template_info.setText(
            f"셀 {number_text(w)} × {number_text(h)}mm · {nx} × {ny}칸 · "
            f"회전 {ROTATION_TEXT[definition['cell']['rotation_deg']]} · "
            f"{DIRECTION_TEXT[definition['fill_direction']]} 채움"
        )
        self._rebuild_text_fields()
        overlaps = session.overlaps()
        if overlaps:
            self.banner.setText(
                f"이 템플릿은 셀이 서로 겹칩니다({len(overlaps)}곳). "
                "겹친 부분은 나중에 넣은 데이터가 위에 그려집니다."
            )
            self.banner.show()
        else:
            self.banner.hide()
        first = next(iter(session.cell_positions()), 0)
        self.view.select(first)
        self._update_state()

    def _rebuild_text_fields(self):
        while self.text_form.rowCount():
            self.text_form.removeRow(0)
        self.text_edits = {}
        fields = self.session.field_ids() if self.session else []
        if not fields:
            self.no_text_label = QLabel("이 템플릿에는 텍스트 항목이 없습니다.")
            self.no_text_label.setObjectName("hint")
            self.text_form.addRow(self.no_text_label)
            return
        for id in fields:
            edit = QLineEdit(self.session.texts.get(id, ""))
            edit.setPlaceholderText("비워 두면 넣지 않습니다")
            edit.textChanged.connect(lambda value, id=id: self._text_changed(id, value))
            self.text_form.addRow(id, edit)
            self.text_edits[id] = edit

    def _text_changed(self, id, value):
        self.session.set_text(id, value)
        self.view.set_texts(self.session.texts)
        self._update_state()

    # -- B data -----------------------------------------------------------

    def load_files(self):
        if not self.session:
            return
        cell = self.view.selected
        if not cell:
            QMessageBox.information(self, "셀을 선택하세요", "먼저 B를 넣을 셀을 누르세요.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, f"셀 {cell}부터 넣을 B 데이터 선택", self.last_folder, "PDF 파일 (*.pdf)"
        )
        if paths:
            self.place_files(cell, paths)

    def place_files(self, cell, paths):
        """Put one file into ``cell`` or auto-fill several from it."""
        if not self.session or not paths:
            return
        self.last_folder = str(Path(paths[0]).parent)
        self.setCursor(Qt.WaitCursor)
        try:
            bad = [
                (Path(path).name, self.thumbs.get(path)["error"])
                for path in paths
                if self.thumbs.get(path)["error"]
            ]
        finally:
            self.unsetCursor()
        if bad:
            QMessageBox.warning(
                self,
                "넣을 수 없는 파일이 있습니다",
                "아래 파일 때문에 아무것도 넣지 않았습니다.\n\n"
                + "\n".join(f"· {name}: {reason}" for name, reason in bad),
            )
            return
        if len(paths) == 1:
            if cell in self.session.placements:
                current = self.session.placements[cell]["path"].name
                answer = QMessageBox.question(
                    self,
                    "데이터 바꾸기",
                    f"셀 {cell}에는 이미 '{current}'이(가) 있습니다.\n"
                    f"'{Path(paths[0]).name}'(으)로 바꿀까요? 겹침 순서는 그대로 유지됩니다.",
                )
                if answer != QMessageBox.Yes:
                    return
            self.session.assign(cell, paths[0])
            self.notify(f"셀 {cell}: {Path(paths[0]).name}")
        else:
            result = self.session.fill(cell, paths)
            added = result["added"]
            if added:
                self.notify(
                    f"자동 배열: 셀 {added[0][0]}부터 {len(added)}개를 넣었습니다 "
                    f"({added[0][1].name} … {added[-1][1].name})."
                )
            if result["reason"]:
                self._warn_blocked(result)
        self.view.set_placements(self.session.placements)
        self._update_state()

    def _warn_blocked(self, result):
        if result["reason"] == "occupied":
            cause = f"셀 {result['blocked_cell']}에 이미 데이터가 있어 그 앞에서 멈췄습니다."
        else:
            cause = "마지막 셀까지 채워 더 넣을 자리가 없습니다."
        names = [path.name for path in result["unplaced"]]
        shown = names[:15] + ([f"… 외 {len(names) - 15}개"] if len(names) > 15 else [])
        self.notify(f"경고 — 자동 배열이 막혔습니다. {cause} 넣지 못한 파일 {len(names)}개: {', '.join(names)}")
        QMessageBox.warning(
            self,
            "자동 배열이 막혔습니다",
            f"{cause}\n\n넣지 못한 파일 {len(names)}개:\n" + "\n".join(f"· {n}" for n in shown),
        )

    def remove_selected(self):
        cell = self.view.selected
        if self.session and cell in self.session.placements:
            name = self.session.placements[cell]["path"].name
            self.session.remove(cell)
            self.view.set_placements(self.session.placements)
            self.notify(f"셀 {cell}을(를) 비웠습니다 ({name}).")
            self._update_state()

    def clear_all(self):
        if not self.session or not self.session.placements:
            return
        answer = QMessageBox.question(
            self, "모두 비우기", "모든 셀의 B 데이터를 비울까요? 텍스트는 그대로 둡니다."
        )
        if answer == QMessageBox.Yes:
            self.session.clear()
            self.view.set_placements(self.session.placements)
            self.notify("모든 셀을 비웠습니다.")
            self._update_state()

    # -- jobs -------------------------------------------------------------

    def _confirm_discard(self):
        if not self.session or not self.session.dirty:
            return True
        answer = QMessageBox.question(
            self,
            "저장하지 않은 작업",
            "저장하지 않은 작업이 있습니다. 버리고 계속할까요?",
            QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        return answer == QMessageBox.Discard

    def new_job(self):
        if self.session and self._confirm_discard():
            self.start_session(self.session.template_name)

    def open_project(self, path=None):
        if not self._confirm_discard():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "프로젝트 열기", self.last_folder, "퀵 임포징 프로젝트 (*.qiproj.json)"
            )
        if not path:
            return
        try:
            session = Session.open(self.root, path)
        except SessionError as exc:
            QMessageBox.critical(self, "프로젝트를 열 수 없습니다", str(exc))
            return
        self.last_folder = str(Path(path).parent)
        self._adopt(session)
        self.notify(f"프로젝트를 열었습니다: {Path(path).name}")

    def save_pdf(self, path=None):
        if not self.session:
            return
        if not self.session.placements:
            answer = QMessageBox.question(
                self, "빈 판 저장", "B 데이터가 하나도 없습니다. 그대로 저장할까요?"
            )
            if answer != QMessageBox.Yes:
                return
        if not path:
            folder = self._default_folder()
            suggestion = free_output_path(Path(folder) / f"{self.session.template_name}.pdf")
            path, _ = QFileDialog.getSaveFileName(
                self,
                "임포징 PDF 저장",
                str(suggestion),
                "PDF 파일 (*.pdf)",
                options=QFileDialog.DontConfirmOverwrite,
            )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".pdf":
            target = target.with_name(target.name + ".pdf")
        if any(file.exists() for file in output_files(target)):
            free = free_output_path(target)
            answer = QMessageBox.question(
                self,
                "같은 이름의 파일이 있습니다",
                f"'{target.stem}' 이름의 결과 파일이 이미 있습니다. 기존 파일은 덮어쓰지 않습니다.\n\n"
                f"'{free.name}'(으)로 저장할까요?",
            )
            if answer != QMessageBox.Yes:
                return
            target = free
        self.setCursor(Qt.WaitCursor)
        try:
            report = self.session.save(target)
        except SessionError as exc:
            QMessageBox.critical(self, "저장하지 못했습니다", str(exc))
            return
        finally:
            self.unsetCursor()
        if report["status"] != "PASS":
            message = "\n\n".join(describe_error(entry) for entry in report["errors"])
            self.notify(f"오류 — 저장하지 못했습니다. {message}")
            QMessageBox.critical(self, "저장하지 못했습니다", message)
            return
        self.last_folder = str(target.parent)
        self.notify(f"저장했습니다: {target}")
        self._update_state()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("저장했습니다")
        box.setText(
            f"{target.name}\n\n같은 폴더에 프로젝트(.qiproj.json), 미리보기(.png), "
            "리포트(.report.json)도 저장했습니다."
        )
        folder_button = box.addButton("폴더 열기", QMessageBox.ActionRole)
        box.addButton("확인", QMessageBox.AcceptRole)
        box.exec()
        if box.clickedButton() is folder_button:
            open_folder(target.parent)

    def _default_folder(self):
        if self.session.project_path:
            return str(self.session.project_path.parent)
        if self.session.placements:
            first = min(self.session.placements.values(), key=lambda item: item["order"])
            return str(first["path"].parent)
        return self.last_folder

    def launch_editor(self):
        if getattr(sys, "frozen", False):
            program = str(Path(sys.executable).with_name("QuickImposingEditor.exe"))
            started = QProcess.startDetached(program, [])
        else:
            started = QProcess.startDetached(sys.executable, ["-m", "imposing.gui.editor"])
        if not started:
            QMessageBox.warning(self, "템플릿 편집기", "템플릿 편집기를 실행하지 못했습니다.")

    # -- state ------------------------------------------------------------

    def notify(self, message):
        self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")

    def _update_state(self):
        active = self.session is not None
        has_templates = self.template_combo.count() > 0
        self.view.setVisible(active)
        self.empty_label.setVisible(not active)
        if not active:
            self.empty_label.setText(
                "왼쪽에서 템플릿을 선택하면 판이 여기에 보입니다."
                if has_templates
                else "템플릿이 없습니다.\n\n[도구 → 템플릿 편집기 열기]에서 먼저 템플릿을 만드세요."
            )
        cell = self.view.selected if active else 0
        placed = active and cell in self.session.placements
        self.load_button.setEnabled(active and bool(cell))
        self.remove_button.setEnabled(bool(placed))
        self.clear_button.setEnabled(active and bool(self.session.placements))
        self.save_button.setEnabled(active)
        if not active:
            self.cell_info.setText("템플릿을 먼저 선택하세요.")
            self.count_label.setText("")
        elif not cell:
            self.cell_info.setText("선택한 셀이 없습니다. 미리보기에서 셀을 누르세요.")
        elif placed:
            item = self.session.placements[cell]
            state = "" if item["path"].is_file() else " (파일 없음)"
            self.cell_info.setText(
                f"<b>셀 {cell}</b> — {item['path'].name}{state}<br>넣은 순서 {item['order']}"
            )
        else:
            self.cell_info.setText(f"<b>셀 {cell}</b> — 비어 있음")
        if active:
            total = len(self.session.cell_positions())
            self.count_label.setText(f"B 데이터 {len(self.session.placements)} / {total}칸")
            title = self.session.project_path.name if self.session.project_path else "새 작업"
            mark = " *" if self.session.dirty else ""
            self.setWindowTitle(f"퀵 임포징 — 작업 [{self.session.template_name}] {title}{mark}")

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.ActivationChange and self.isActiveWindow():
            names = store.list_templates(self.root)
            shown = [self.template_combo.itemText(i) for i in range(self.template_combo.count())]
            if names != shown:
                self.refresh_templates()
            self._reload_changed_template()

    def _reload_changed_template(self):
        """Follow edits made in the template editor while a job is open."""
        if not self.session:
            return
        try:
            stored = store.load_template(self.root, self.session.template_name)
        except store.TemplateError:
            return
        if stored == self.session.template:
            return
        from ..model import cells

        missing = sorted(set(self.session.placements) - set(cells(stored)))
        if missing:
            self.notify(
                "경고 — 템플릿이 바뀌어 지금 작업의 셀 "
                f"{', '.join(map(str, missing))}이(가) 없어졌습니다. 이대로는 저장할 수 없습니다."
            )
            return
        selected = self.view.selected
        texts = dict(self.session.texts)
        self.session.template = stored
        for id in self.session.field_ids():
            self.session.texts.setdefault(id, texts.get(id, ""))
        self._adopt(self.session)
        self.view.select(selected)
        self.notify("템플릿이 바뀌어 새 내용으로 다시 불러왔습니다.")

    def closeEvent(self, event):
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()


def main():
    if "--selftest" in sys.argv:
        from .common import self_test

        return self_test(WorkWindow)
    app = create_application("QuickImposing", "work")
    if not tools_ready():
        return 1
    window = WorkWindow()
    window.show()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".json"):
        window.open_project(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
