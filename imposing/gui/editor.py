"""Template editor: create and change templates (sheet structure only)."""

import copy
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import store
from ..model import cells, name_valid, overlap_pairs
from .common import (
    SheetView,
    create_application,
    number_text,
    open_folder,
    plain_number,
    tools_ready,
)

ROTATIONS = [
    (0, "0° — 그대로"),
    (90, "90° — 카드 위쪽이 판 왼쪽으로"),
    (-90, "−90° — 카드 위쪽이 판 오른쪽으로"),
    (180, "180° — 거꾸로"),
]
DIRECTIONS = [
    ("forward", "정방향 — 각 줄을 왼쪽 → 오른쪽"),
    ("reverse", "역방향 — 각 줄을 오른쪽 → 왼쪽"),
]
PREFERRED_FONTS = ("Malgun Gothic", "맑은 고딕", "Noto Sans CJK KR", "Noto Sans KR")


def blank_definition():
    return {
        "schema": "quick-imposing/template@2",
        "name": "",
        "base": "base.pdf",
        "cell": {"size_mm": [85, 50], "rotation_deg": -90},
        "grid": {"origin_mm": [24, 49.5], "count": [3, 8], "pitch_mm": [86, 51]},
        "fill_direction": "forward",
        "text_fields": [],
    }


def mm_box(minimum, maximum, value):
    box = QDoubleSpinBox()
    box.setDecimals(3)
    box.setRange(minimum, maximum)
    box.setSingleStep(1)
    box.setSuffix(" mm")
    box.setValue(value)
    box.setKeyboardTracking(False)
    return box


def pair_row(first, second, first_label, second_label):
    row = QHBoxLayout()
    row.addWidget(QLabel(first_label))
    row.addWidget(first, 1)
    row.addSpacing(8)
    row.addWidget(QLabel(second_label))
    row.addWidget(second, 1)
    return row


class EditorWindow(QMainWindow):
    def __init__(self, root=None):
        super().__init__()
        self.root = Path(root) if root else store.default_templates_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.fonts = None
        self.current = None  # name of the stored template being edited
        self.saved = None  # definition as stored (or blank for a new one)
        self.new_base = None  # base chosen but not saved yet
        self.loading = False
        self.setWindowTitle("퀵 임포징 — 템플릿 편집기")
        self.resize(1320, 880)
        self._build_ui()
        self.refresh_list()
        self.new_template(ask=False)

    # -- construction -----------------------------------------------------

    def _build_ui(self):
        self.list = QListWidget()
        self.list.itemClicked.connect(self._list_clicked)
        new_button = QPushButton("새 템플릿")
        new_button.clicked.connect(lambda: self.new_template())
        self.copy_button = QPushButton("복제…")
        self.copy_button.clicked.connect(self.duplicate_template)
        self.delete_button = QPushButton("삭제…")
        self.delete_button.clicked.connect(self.delete_template)
        folder_button = QPushButton("템플릿 폴더 열기")
        folder_button.clicked.connect(lambda: open_folder(self.root))
        left = QWidget()
        column = QVBoxLayout(left)
        column.addWidget(QLabel("템플릿"))
        column.addWidget(self.list, 1)
        column.addWidget(new_button)
        row = QHBoxLayout()
        row.addWidget(self.copy_button)
        row.addWidget(self.delete_button)
        column.addLayout(row)
        column.addWidget(folder_button)
        left.setMinimumWidth(190)
        left.setMaximumWidth(280)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("예: BC-COMBI-전면")
        self.name_edit.textChanged.connect(self._changed)
        self.base_label = QLabel("")
        self.base_label.setWordWrap(True)
        self.base_button = QPushButton("베이스 PDF 선택…")
        self.base_button.clicked.connect(self.choose_base)
        basic = QGroupBox("기본")
        form = QFormLayout(basic)
        form.addRow("이름", self.name_edit)
        form.addRow("베이스", self.base_label)
        form.addRow("", self.base_button)

        self.cell_w = mm_box(0.001, 5000, 85)
        self.cell_h = mm_box(0.001, 5000, 50)
        self.rotation = QComboBox()
        for value, text in ROTATIONS:
            self.rotation.addItem(text, value)
        self.origin_x = mm_box(-5000, 5000, 24)
        self.origin_y = mm_box(-5000, 5000, 49.5)
        self.count_x = QSpinBox()
        self.count_y = QSpinBox()
        for box in (self.count_x, self.count_y):
            box.setRange(1, 200)
            box.setKeyboardTracking(False)
        self.pitch_x = mm_box(0, 5000, 86)
        self.pitch_y = mm_box(0, 5000, 51)
        self.direction = QComboBox()
        for value, text in DIRECTIONS:
            self.direction.addItem(text, value)
        self.grid_note = QLabel("")
        self.grid_note.setObjectName("hint")
        self.grid_note.setWordWrap(True)
        self.warning = QLabel("")
        self.warning.setObjectName("banner")
        self.warning.setWordWrap(True)
        self.warning.hide()
        grid = QGroupBox("셀 배열 (판 좌상단이 원점, 아래쪽이 +Y)")
        form = QFormLayout(grid)
        form.addRow("셀 크기", pair_row(self.cell_w, self.cell_h, "가로", "세로"))
        form.addRow("시작 위치", pair_row(self.origin_x, self.origin_y, "X", "Y"))
        form.addRow("셀 개수", pair_row(self.count_x, self.count_y, "가로", "세로"))
        form.addRow("피치", pair_row(self.pitch_x, self.pitch_y, "가로", "세로"))
        form.addRow("", self.grid_note)
        form.addRow("카드 회전", self.rotation)
        form.addRow("채움 방향", self.direction)
        form.addRow(self.warning)
        for box in (
            self.cell_w, self.cell_h, self.origin_x, self.origin_y,
            self.count_x, self.count_y, self.pitch_x, self.pitch_y,
        ):
            box.valueChanged.connect(self._changed)
        self.rotation.currentIndexChanged.connect(self._changed)
        self.direction.currentIndexChanged.connect(self._changed)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["이름", "X (mm)", "Y (mm)", "글꼴", "크기 (pt)"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for column, width in ((0, 86), (1, 84), (2, 84), (4, 70)):
            self.table.setColumnWidth(column, width)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(150)
        self.table.itemChanged.connect(self._changed)
        add_button = QPushButton("항목 추가")
        add_button.clicked.connect(lambda: self.add_field())
        remove_button = QPushButton("선택한 항목 삭제")
        remove_button.clicked.connect(self.remove_field)
        text_note = QLabel(
            "이름은 작업 화면의 입력칸 이름표로 쓰입니다(예: 제품명, 날짜). "
            "위치는 첫 글자의 왼쪽 아래(기준선)입니다. 글자색은 K100 고정입니다."
        )
        text_note.setObjectName("hint")
        text_note.setWordWrap(True)
        texts = QGroupBox("텍스트 항목")
        column = QVBoxLayout(texts)
        column.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(add_button)
        row.addWidget(remove_button)
        row.addStretch(1)
        column.addLayout(row)
        column.addWidget(text_note)

        self.save_button = QPushButton("템플릿 저장")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save)
        self.revert_button = QPushButton("되돌리기")
        self.revert_button.clicked.connect(self.revert)
        buttons = QHBoxLayout()
        buttons.addWidget(self.revert_button)
        buttons.addStretch(1)
        buttons.addWidget(self.save_button)

        form_panel = QWidget()
        column = QVBoxLayout(form_panel)
        column.addWidget(basic)
        column.addWidget(grid)
        column.addWidget(texts, 1)
        column.addLayout(buttons)
        scroll = QScrollArea()
        scroll.setWidget(form_panel)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(470)

        self.view = SheetView()
        self.view.item.show_orientation = True
        self.view.item.show_field_names = True
        fit_button = QPushButton("화면에 맞춤")
        fit_button.clicked.connect(self.view.fit)
        zoom_hint = QLabel("▲ 표시는 카드 위쪽이 향하는 방향입니다. Ctrl + 휠: 확대·축소")
        zoom_hint.setObjectName("hint")
        row = QHBoxLayout()
        row.addWidget(zoom_hint)
        row.addStretch(1)
        row.addWidget(fit_button)
        self.cell_label = QLabel("")
        self.cell_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.view.cellSelected.connect(lambda _: self._show_cell())
        right = QWidget()
        column = QVBoxLayout(right)
        column.addWidget(self.view, 1)
        column.addWidget(self.cell_label)
        column.addLayout(row)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(2, 1)
        self.setCentralWidget(splitter)
        self.statusBar().showMessage(f"템플릿 폴더: {self.root}")

    # -- fonts ------------------------------------------------------------

    def font_names(self):
        if self.fonts is None:
            self.setCursor(Qt.WaitCursor)
            try:
                self.fonts = store.usable_fonts()
            finally:
                self.unsetCursor()
        return self.fonts

    def default_font(self):
        names = self.font_names()
        folded = {name.casefold(): name for name in names}
        for name in PREFERRED_FONTS:
            if name.casefold() in folded:
                return folded[name.casefold()]
        return names[0] if names else ""

    def _font_combo(self, current):
        combo = QComboBox()
        names = self.font_names()
        combo.addItems(names)
        folded = [name.casefold() for name in names]
        if current.casefold() in folded:
            combo.setCurrentIndex(folded.index(current.casefold()))
        elif current:
            combo.addItem(f"{current} (이 PC에 없음)", current)
            combo.setCurrentIndex(combo.count() - 1)
        combo.currentIndexChanged.connect(self._changed)
        return combo

    @staticmethod
    def _font_value(combo):
        return combo.currentData() or combo.currentText()

    # -- form <-> definition ----------------------------------------------

    def add_field(self, field=None):
        if field is None:
            used = {self.table.item(r, 0).text() for r in range(self.table.rowCount())}
            number = 1
            while f"항목{number}" in used:
                number += 1
            field = dict(
                id=f"항목{number}", x_mm=35, y_mm=14, font=self.default_font(), size_pt=9
            )
        was_loading, self.loading = self.loading, True
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(field["id"]))
        for column, key in ((1, "x_mm"), (2, "y_mm")):
            box = mm_box(-5000, 5000, field[key])
            box.setSuffix("")
            box.valueChanged.connect(self._changed)
            self.table.setCellWidget(row, column, box)
        self.table.setCellWidget(row, 3, self._font_combo(field["font"]))
        size = QDoubleSpinBox()
        size.setDecimals(2)
        size.setRange(0.1, 1000)
        size.setValue(field["size_pt"])
        size.setKeyboardTracking(False)
        size.valueChanged.connect(self._changed)
        self.table.setCellWidget(row, 4, size)
        self.loading = was_loading
        self._changed()

    def remove_field(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not rows and self.table.currentRow() >= 0:
            rows = [self.table.currentRow()]
        for row in rows:
            self.table.removeRow(row)
        self._changed()

    def definition(self):
        fields = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            fields.append(
                {
                    "id": item.text().strip() if item else "",
                    "x_mm": plain_number(self.table.cellWidget(row, 1).value()),
                    "y_mm": plain_number(self.table.cellWidget(row, 2).value()),
                    "font": self._font_value(self.table.cellWidget(row, 3)),
                    "size_pt": plain_number(self.table.cellWidget(row, 4).value()),
                }
            )
        return {
            "schema": "quick-imposing/template@2",
            "name": self.name_edit.text().strip(),
            "base": "base.pdf",
            "cell": {
                "size_mm": [plain_number(self.cell_w.value()), plain_number(self.cell_h.value())],
                "rotation_deg": self.rotation.currentData(),
            },
            "grid": {
                "origin_mm": [plain_number(self.origin_x.value()), plain_number(self.origin_y.value())],
                "count": [self.count_x.value(), self.count_y.value()],
                "pitch_mm": [plain_number(self.pitch_x.value()), plain_number(self.pitch_y.value())],
            },
            "fill_direction": self.direction.currentData(),
            "text_fields": fields,
        }

    def _fill_form(self, definition):
        self.loading = True
        self.name_edit.setText(definition["name"])
        self.cell_w.setValue(definition["cell"]["size_mm"][0])
        self.cell_h.setValue(definition["cell"]["size_mm"][1])
        self.rotation.setCurrentIndex(self.rotation.findData(definition["cell"]["rotation_deg"]))
        self.origin_x.setValue(definition["grid"]["origin_mm"][0])
        self.origin_y.setValue(definition["grid"]["origin_mm"][1])
        self.count_x.setValue(definition["grid"]["count"][0])
        self.count_y.setValue(definition["grid"]["count"][1])
        self.pitch_x.setValue(definition["grid"]["pitch_mm"][0])
        self.pitch_y.setValue(definition["grid"]["pitch_mm"][1])
        self.direction.setCurrentIndex(self.direction.findData(definition["fill_direction"]))
        self.table.setRowCount(0)
        for field in definition["text_fields"]:
            self.add_field(field)
        self.loading = False
        self._changed()

    def base_file(self):
        if self.new_base:
            return self.new_base
        if self.current:
            return store.base_path(self.root, self.current)
        return None

    def is_dirty(self):
        return self.new_base is not None or self.definition() != self.saved

    # -- live feedback ----------------------------------------------------

    def cell_position(self, cell):
        """(row, column, left, top, right, bottom) of a cell in mm, or None."""
        definition = self.view.item.definition
        positions = self.view.item.positions
        if not definition or cell not in positions:
            return None
        columns = definition["grid"]["count"][0]
        width, height = definition["cell"]["size_mm"]
        left, top = positions[cell]
        return (
            (cell - 1) // columns + 1,
            (cell - 1) % columns + 1,
            left,
            top,
            left + width,
            top + height,
        )

    def _show_cell(self):
        """Coordinates of the clicked cell, to check the layout against the spec."""
        found = self.cell_position(self.view.selected)
        if found is None:
            self.cell_label.setText("셀을 누르면 그 셀의 좌표(mm)가 여기에 표시됩니다.")
            return
        row, column, left, top, right, bottom = found
        self.cell_label.setText(
            f"<b>셀 {self.view.selected}</b> ({row}행 {column}열) — "
            f"좌상단 <b>X {number_text(left)}, Y {number_text(top)}</b> mm"
            f" · 우하단 X {number_text(right)}, Y {number_text(bottom)} mm"
        )

    def _changed(self, *_):
        if self.loading:
            return
        definition = self.definition()
        base = self.base_file()
        self.view.set_sheet(base, definition)
        self.view.set_texts({})
        self._show_cell()
        width, height = self.view.item.size
        if base:
            origin = "새로 선택함: " + Path(base).name if self.new_base else "템플릿에 저장된 사본"
            self.base_label.setText(f"{origin}\n판 크기 {number_text(width)} × {number_text(height)} mm")
        else:
            self.base_label.setText("아직 선택하지 않았습니다. (빈 베이스 PDF, 1페이지)")
        gap_x = definition["grid"]["pitch_mm"][0] - definition["cell"]["size_mm"][0]
        gap_y = definition["grid"]["pitch_mm"][1] - definition["cell"]["size_mm"][1]
        def gap(value):
            return f"겹침 {number_text(-value)} mm" if value < 0 else f"{number_text(value)} mm"

        self.grid_note.setText(
            "피치는 셀 시작점에서 다음 셀 시작점까지의 거리입니다. "
            f"지금 셀 사이 간격: 가로 {gap(gap_x)}, 세로 {gap(gap_y)}"
        )
        notes = []
        positions = cells(definition)
        size = definition["cell"]["size_mm"]
        overlaps = overlap_pairs(positions, size)
        if overlaps:
            notes.append(
                f"셀이 서로 겹칩니다({len(overlaps)}곳). 의도한 배열이면 그대로 저장해도 됩니다. "
                "겹친 부분은 나중에 넣은 데이터가 위에 그려집니다."
            )
        outside = [
            cell
            for cell, (x, y) in positions.items()
            if x < 0 or y < 0 or x + size[0] > width + 1e-9 or y + size[1] > height + 1e-9
        ]
        if outside:
            notes.append(
                f"판 바깥으로 나가는 셀이 있습니다({len(outside)}칸, 점선). "
                "바깥 부분은 잘려서 나오지 않습니다."
            )
        self.warning.setText("\n".join(notes))
        self.warning.setVisible(bool(notes))
        self.name_edit.setReadOnly(self.current is not None)
        self.copy_button.setEnabled(self.current is not None)
        self.delete_button.setEnabled(self.current is not None)
        dirty = self.is_dirty()
        self.revert_button.setEnabled(dirty)
        title = self.current or "새 템플릿"
        self.setWindowTitle(f"퀵 임포징 — 템플릿 편집기 [{title}]{' *' if dirty else ''}")

    # -- list -------------------------------------------------------------

    def refresh_list(self):
        self.list.blockSignals(True)
        self.list.clear()
        self.list.addItems(store.list_templates(self.root))
        self._mark_current()
        self.list.blockSignals(False)

    def _mark_current(self):
        matches = self.list.findItems(self.current or "", Qt.MatchExactly) if self.current else []
        self.list.setCurrentItem(matches[0] if matches else None)

    def _list_clicked(self, item):
        if item.text() == self.current:
            return
        if not self._confirm_discard():
            self._mark_current()
            return
        self.open_template(item.text())

    def _confirm_discard(self):
        if not self.is_dirty() or (self.current is None and self.definition() == blank_definition() and not self.new_base):
            return True
        answer = QMessageBox.question(
            self,
            "저장하지 않은 변경",
            "저장하지 않은 변경이 있습니다. 버리고 계속할까요?",
            QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        return answer == QMessageBox.Discard

    # -- actions ----------------------------------------------------------

    def new_template(self, ask=True):
        if ask and not self._confirm_discard():
            return
        self.current = None
        self.new_base = None
        self.saved = blank_definition()
        self.view.fitted = True
        self._fill_form(self.saved)
        self._mark_current()
        self.name_edit.setFocus()

    def open_template(self, name):
        try:
            definition = store.load_template(self.root, name)
        except store.TemplateError as exc:
            QMessageBox.critical(self, "템플릿을 열 수 없습니다", str(exc))
            self._mark_current()
            return False
        self.current = name
        self.new_base = None
        self.saved = copy.deepcopy(definition)
        self.view.fitted = True
        self._fill_form(definition)
        # Compare against what the form produces so number formatting
        # (85 vs 85.0) never counts as an unsaved change.
        self.saved = self.definition()
        self._changed()
        self._mark_current()
        return True

    def choose_base(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "베이스 PDF 선택", str(Path.home()), "PDF 파일 (*.pdf)"
            )
        if not path:
            return
        try:
            store.page_size_mm(path)
        except store.TemplateError as exc:
            QMessageBox.warning(self, "베이스로 쓸 수 없습니다", str(exc))
            return
        if self.current:
            answer = QMessageBox.question(
                self,
                "베이스 바꾸기",
                "저장하면 이 템플릿의 베이스 사본이 새 파일로 바뀝니다. 계속할까요?",
            )
            if answer != QMessageBox.Yes:
                return
        self.new_base = str(path)
        self._changed()

    def _problems(self, definition):
        problems = []
        if not name_valid(definition["name"]):
            problems.append(
                '이름을 입력하세요. \\ / : * ? " < > | 문자는 쓸 수 없고, 마침표나 공백으로 끝날 수 없습니다.'
            )
        if self.base_file() is None:
            problems.append("베이스 PDF를 선택하세요.")
        ids = [field["id"] for field in definition["text_fields"]]
        if any(not id for id in ids):
            problems.append("이름이 빈 텍스트 항목이 있습니다.")
        if len(set(ids)) != len(ids):
            problems.append("텍스트 항목 이름이 겹칩니다. 서로 다른 이름을 쓰세요.")
        if any(not field["font"] for field in definition["text_fields"]):
            problems.append("글꼴을 고르지 않은 텍스트 항목이 있습니다.")
        return problems

    def save(self):
        definition = self.definition()
        problems = self._problems(definition)
        if problems:
            QMessageBox.warning(self, "저장할 수 없습니다", "\n".join(f"· {p}" for p in problems))
            return False
        creating = self.current is None
        if creating and (self.root / definition["name"]).exists():
            QMessageBox.warning(
                self,
                "저장할 수 없습니다",
                f"'{definition['name']}' 이름의 템플릿이 이미 있습니다. 다른 이름을 쓰세요.",
            )
            return False
        if not creating:
            old = self.saved["grid"]["count"]
            new = definition["grid"]["count"]
            if new[0] * new[1] < old[0] * old[1] or new[0] != old[0]:
                answer = QMessageBox.question(
                    self,
                    "셀 배열 변경",
                    "셀 개수가 바뀝니다. 이 템플릿으로 저장한 기존 프로젝트를 다시 열면 "
                    "셀 위치가 달라지거나, 없는 셀 때문에 열리지 않을 수 있습니다.\n\n계속 저장할까요?",
                )
                if answer != QMessageBox.Yes:
                    return False
        try:
            store.save_template(definition, self.root, self.new_base)
        except store.TemplateError as exc:
            QMessageBox.critical(self, "저장하지 못했습니다", str(exc))
            return False
        self.refresh_list()
        self.open_template(definition["name"])
        self.statusBar().showMessage(f"저장했습니다: {definition['name']}", 5000)
        return True

    def revert(self):
        if self.current:
            self.open_template(self.current)
        else:
            self.new_template(ask=False)

    def duplicate_template(self, name=None):
        if not self.current or not self._confirm_discard():
            return
        if not name:
            name, ok = QInputDialog.getText(
                self, "템플릿 복제", "새 템플릿 이름", text=f"{self.current}-복사"
            )
            if not ok:
                return
        name = name.strip()
        if not name_valid(name) or (self.root / name).exists():
            QMessageBox.warning(
                self, "복제할 수 없습니다", "쓸 수 없는 이름이거나 이미 있는 이름입니다."
            )
            return
        try:
            definition = store.load_template(self.root, self.current)
            definition["name"] = name
            store.save_template(definition, self.root, store.base_path(self.root, self.current))
        except store.TemplateError as exc:
            QMessageBox.critical(self, "복제하지 못했습니다", str(exc))
            return
        self.refresh_list()
        self.open_template(name)

    def delete_template(self):
        if not self.current:
            return
        answer = QMessageBox.question(
            self,
            "템플릿 삭제",
            f"템플릿 '{self.current}'을(를) 삭제할까요?\n"
            "템플릿 폴더와 베이스 사본이 지워지며 되돌릴 수 없습니다. "
            "이 템플릿으로 저장한 프로젝트는 다시 열 수 없게 됩니다.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            store.delete_template(self.root, self.current)
        except store.TemplateError as exc:
            QMessageBox.critical(self, "삭제하지 못했습니다", str(exc))
            return
        self.refresh_list()
        self.new_template(ask=False)

    def closeEvent(self, event):
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()


def main():
    if "--selftest" in sys.argv:
        from .common import self_test

        return self_test(EditorWindow)
    app = create_application("QuickImposingEditor", "editor")
    if not tools_ready():
        return 1
    window = EditorWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
