"""Shared GUI parts: runtime setup, PDF thumbnails and the sheet preview."""

import os
from pathlib import Path
import shutil
import sys

import pikepdf as p
from PySide6.QtCore import QPointF, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QImage,
    QPainter,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QMessageBox,
)

from .. import fonts
from ..model import cells
from ..pdf import MM, render_bytes

SKY = QColor("#1e9be0")
FILLED = QColor("#5b6470")
SELECT = QColor("#ff7a00")
MISSING = QColor("#b9bec6")
REQUIRED_TOOLS = ("qpdf", "pdftoppm")

STYLE = """
QPushButton#primary {
    background: #1769c4; color: white; border: 0; border-radius: 4px;
    padding: 9px 14px; font-weight: bold;
}
QPushButton#primary:hover { background: #1f7ae0; }
QPushButton#primary:disabled { background: #a9b6c6; }
QLabel#banner {
    background: #fff4ce; color: #5c4400; border: 1px solid #e6c964;
    border-radius: 4px; padding: 6px 8px;
}
QLabel#hint { color: #5b6470; }
QGroupBox { font-weight: bold; }
"""


def setup_runtime():
    """Put tools bundled next to the program in front of PATH.

    ``bin/`` and its direct subfolders (``bin/qpdf``, ``bin/poppler``) are
    searched, next to the program when packaged or at the repository root.
    """
    if getattr(sys, "frozen", False):
        home = Path(sys.executable).resolve().parent
    else:
        home = Path(__file__).resolve().parents[2]
    bin_folder = home / "bin"
    if not bin_folder.is_dir():
        return
    folders = [bin_folder, *sorted(f for f in bin_folder.iterdir() if f.is_dir())]
    os.environ["PATH"] = os.pathsep.join(
        [*map(str, folders), os.environ.get("PATH", "")]
    )


def self_test(window_class):
    """Start-up check for packaged builds: exit code 0 when the window builds."""
    import tempfile

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    create_application("selftest")
    if [name for name in REQUIRED_TOOLS if not shutil.which(name)]:
        return 2
    with tempfile.TemporaryDirectory() as folder:
        window = window_class(folder)
        window.show()
        QApplication.processEvents()
        window.close()
    return 0


def create_application(name):
    setup_runtime()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(name)
    app.setStyleSheet(STYLE)
    return app


def tools_ready(parent=None):
    """Tell the user when qpdf or Poppler is missing. Returns True if ready."""
    missing = [name for name in REQUIRED_TOOLS if not shutil.which(name)]
    if not missing:
        return True
    QMessageBox.critical(
        parent,
        "필요한 도구가 없습니다",
        "다음 도구를 찾을 수 없어 프로그램을 실행할 수 없습니다.\n\n"
        + "\n".join(f"  · {name}" for name in missing)
        + "\n\n프로그램 폴더의 bin 폴더가 지워지지 않았는지 확인하거나, "
        "qpdf와 Poppler를 설치해 PATH에 추가하세요.",
    )
    return False


def open_folder(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def number_text(value):
    """85.0 -> '85', 49.5 -> '49.5' (at most three decimals)."""
    return f"{value:.3f}".rstrip("0").rstrip(".")


def plain_number(value):
    """Store whole numbers as int so saved JSON stays tidy."""
    value = round(float(value), 3)
    return int(value) if value == int(value) else value


class Thumbs:
    """Low-resolution page images for preview, cached per file version."""

    def __init__(self, dpi=100):
        self.dpi = dpi
        self.cache = {}

    def get(self, path):
        """dict(image, media, center, error) for a one-page PDF.

        ``media`` is the MediaBox and ``center`` the centre of the TrimBox
        (MediaBox when absent), both in pt. ``error`` is a Korean message when
        the file cannot be used; ``image`` is then None.
        """
        path = Path(path)
        try:
            stat = path.stat()
        except OSError:
            return dict(image=None, media=None, center=None, error="파일 없음")
        key = (str(path), stat.st_mtime_ns, stat.st_size, self.dpi)
        if key not in self.cache:
            self.cache[key] = self._load(path)
        return self.cache[key]

    def _load(self, path):
        failed = dict(image=None, media=None, center=None)
        try:
            data = path.read_bytes()
            with p.open(path) as doc:
                if len(doc.pages) != 1:
                    return dict(failed, error="1페이지 PDF가 아닙니다")
                page = doc.pages[0]
                if page.obj.get("/Rotate", 0) != 0 or page.obj.get("/UserUnit", 1) != 1:
                    return dict(failed, error="회전(Rotate)이 설정된 PDF는 쓸 수 없습니다")
                media = [float(v) for v in page.MediaBox]
                trim = [float(v) for v in page.obj.get("/TrimBox", page.MediaBox)]
        except (p.PdfError, OSError, ValueError) as exc:
            return dict(failed, error=f"PDF를 열 수 없습니다 ({exc})")
        try:
            image = QImage.fromData(render_bytes(data, self.dpi))
        except RuntimeError as exc:
            return dict(failed, error=f"미리보기를 만들 수 없습니다 ({exc})")
        if image.isNull():
            return dict(failed, error="미리보기를 만들 수 없습니다")
        center = ((trim[0] + trim[2]) / 2, (trim[1] + trim[3]) / 2)
        return dict(image=image, media=media, center=center, error=None)


class FontBook:
    """Qt fonts for previewing template text with the engine's font files."""

    def __init__(self):
        self.loaded = {}

    def font(self, name):
        """A QFont for the engine font ``name``, or None if not installed."""
        if name in self.loaded:
            return self.loaded[name]
        result = None
        try:
            path, _ = fonts.resolve(name)
            font_id = QFontDatabase.addApplicationFont(path)
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                match = [f for f in families if f.casefold() == name.casefold()]
                result = QFont(match[0] if match else families[0])
        except fonts.FontError:
            pass
        self.loaded[name] = result
        return result


class SheetItem(QGraphicsItem):
    """Paints the base, placed B pages, cell outlines and text fields in mm."""

    def __init__(self, thumbs, font_book):
        super().__init__()
        self.thumbs = thumbs
        self.font_book = font_book
        self.size = (305.0, 506.0)
        self.base = None
        self.definition = None
        self.positions = {}
        self.placements = {}
        self.texts = {}
        self.selected = 0
        self.show_orientation = False
        self.show_field_names = False

    def boundingRect(self):
        rect = QRectF(0, 0, *self.size)
        if self.definition:
            w, h = self.definition["cell"]["size_mm"]
            for x, y in self.positions.values():
                rect = rect.united(QRectF(x, y, w, h))
            for field in self.definition["text_fields"]:
                rect = rect.united(QRectF(field["x_mm"] - 5, field["y_mm"] - 10, 120, 15))
        return rect.adjusted(-6, -6, 6, 6)

    def cell_rect(self, cell):
        x, y = self.positions[cell]
        w, h = self.definition["cell"]["size_mm"]
        return QRectF(x, y, w, h)

    def cell_at(self, point):
        best, distance = 0, None
        for cell in self.positions:
            rect = self.cell_rect(cell)
            if rect.contains(point):
                d = (rect.center() - point).manhattanLength()
                if distance is None or d < distance:
                    best, distance = cell, d
        return best

    def paint(self, painter, option, widget=None):
        sheet = QRectF(0, 0, *self.size)
        painter.fillRect(sheet, Qt.white)
        if self.base is not None:
            painter.drawImage(sheet, self.base)
        if not self.definition:
            return
        rotation = self.definition["cell"]["rotation_deg"]
        for cell, item in sorted(self.placements.items(), key=lambda e: e[1]["order"]):
            if cell in self.positions:
                self._paint_card(painter, self.cell_rect(cell), item["path"], rotation, sheet)
        for cell in self.positions:
            self._paint_outline(painter, cell, sheet, rotation)
        if self.selected in self.positions:
            pen = QPen(SELECT, 3)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.cell_rect(self.selected))
        for field in self.definition["text_fields"]:
            self._paint_text(painter, field)
        pen = QPen(QColor("#30343a"), 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(sheet)

    def _paint_card(self, painter, rect, path, rotation, sheet):
        thumb = self.thumbs.get(path)
        visible = rect.intersected(sheet)
        if visible.isEmpty():
            return
        painter.save()
        painter.setClipRect(visible)
        if thumb["image"] is None:
            painter.fillRect(rect, QBrush(MISSING, Qt.BDiagPattern))
            painter.restore()
            self._label(painter, rect.center(), thumb["error"], 3.2, QColor("#5b6470"), center=True)
            return
        media, (cx, cy) = thumb["media"], thumb["center"]
        painter.translate(rect.center())
        # PDF angles are counter-clockwise; Qt's y axis points down.
        painter.rotate(-rotation)
        target = QRectF(
            (media[0] - cx) / MM,
            -(media[3] - cy) / MM,
            (media[2] - media[0]) / MM,
            (media[3] - media[1]) / MM,
        )
        painter.drawImage(target, thumb["image"])
        painter.restore()

    def _paint_outline(self, painter, cell, sheet, rotation):
        rect = self.cell_rect(cell)
        filled = cell in self.placements
        pen = QPen(FILLED if filled else SKY, 1)
        pen.setCosmetic(True)
        if not sheet.contains(rect):
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)
        height = max(2.2, min(4.0, rect.height() * 0.12, rect.width() * 0.12))
        self._label(
            painter,
            rect.topLeft() + QPointF(0.8, 0.8),
            str(cell),
            height,
            QColor("#0b5c8e") if not filled else QColor("#20252b"),
            background=True,
        )
        if self.show_orientation and not filled:
            self._paint_arrow(painter, rect, rotation)

    def _paint_arrow(self, painter, rect, rotation):
        """A small triangle on the side the top of B will face."""
        size = min(rect.width(), rect.height()) * 0.18
        painter.save()
        painter.translate(rect.center())
        painter.rotate(-rotation)
        reach = (rect.height() if rotation in (0, 180) else rect.width()) / 2
        tip = -reach + size * 0.35
        triangle = QPolygonF(
            [QPointF(0, tip), QPointF(-size / 2, tip + size), QPointF(size / 2, tip + size)]
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(30, 155, 224, 110))
        painter.drawPolygon(triangle)
        painter.restore()

    def _label(self, painter, point, text, height_mm, color, background=False, center=False):
        font = QFont(QApplication.font())
        font.setPixelSize(100)
        metrics = QFontMetricsF(font)
        scale = height_mm / 100
        width = metrics.horizontalAdvance(text)
        painter.save()
        painter.translate(point)
        painter.scale(scale, scale)
        if center:
            painter.translate(-width / 2, -metrics.height() / 2)
        if background:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 215))
            painter.drawRoundedRect(QRectF(-18, 0, width + 36, metrics.height()), 18, 18)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(QPointF(0, metrics.ascent()), text)
        painter.restore()

    def _paint_text(self, painter, field):
        value = self.texts.get(field["id"], "")
        placeholder = not value
        if placeholder and not self.show_field_names:
            return
        font = self.font_book.font(field["font"])
        font = QFont(font) if font is not None else QFont(QApplication.font())
        font.setPixelSize(100)
        scale = field["size_pt"] / MM / 100
        painter.save()
        painter.translate(field["x_mm"], field["y_mm"])
        if placeholder:
            pen = QPen(SKY, 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLine(QPointF(-1.5, 0), QPointF(1.5, 0))
            painter.drawLine(QPointF(0, -1.5), QPointF(0, 1.5))
        painter.scale(scale, scale)
        painter.setFont(font)
        painter.setPen(SKY if placeholder else Qt.black)
        painter.drawText(QPointF(0, 0), field["id"] if placeholder else value)
        painter.restore()


class SheetView(QGraphicsView):
    """Zoomable sheet preview. Cells can be clicked and receive dropped files."""

    cellSelected = Signal(int)
    cellActivated = Signal(int)
    filesDropped = Signal(int, list)

    def __init__(self, thumbs=None, parent=None, base_dpi=110):
        super().__init__(parent)
        self.thumbs = thumbs or Thumbs()
        self.base_dpi = base_dpi
        self.item = SheetItem(self.thumbs, FontBook())
        scene = QGraphicsScene(self)
        scene.addItem(self.item)
        self.setScene(scene)
        self.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing
        )
        self.setBackgroundBrush(QColor("#7d838c"))
        self.setAcceptDrops(True)
        self.setMinimumSize(320, 360)
        self.fitted = True
        self._base_key = None

    # -- content ----------------------------------------------------------

    def set_sheet(self, base_pdf, definition, size_mm=None):
        """Show a base PDF (or a blank sheet of ``size_mm``) with a template."""
        item = self.item
        item.prepareGeometryChange()
        if base_pdf is not None:
            path = Path(base_pdf)
            try:
                stat = path.stat()
                key = (str(path), stat.st_mtime_ns, stat.st_size)
            except OSError:
                key = None
            if key != self._base_key or key is None:
                self._base_key = key
                item.base, item.size = self._render_base(path, size_mm)
        else:
            self._base_key = None
            item.base = None
            item.size = tuple(size_mm or (305.0, 506.0))
        item.definition = definition
        item.positions = cells(definition) if definition else {}
        if item.selected not in item.positions:
            item.selected = 0
        self.scene().setSceneRect(item.boundingRect())
        item.update()
        if self.fitted:
            self.fit()

    def _render_base(self, path, fallback):
        try:
            with p.open(path) as doc:
                box = [float(v) for v in doc.pages[0].MediaBox]
            size = ((box[2] - box[0]) / MM, (box[3] - box[1]) / MM)
            image = QImage.fromData(render_bytes(path.read_bytes(), self.base_dpi))
            return (None if image.isNull() else image), size
        except (p.PdfError, OSError, RuntimeError, IndexError):
            return None, tuple(fallback or (305.0, 506.0))

    def set_placements(self, placements):
        self.item.placements = {
            cell: dict(path=entry["path"], order=entry["order"])
            for cell, entry in placements.items()
        }
        self.item.update()

    def set_texts(self, texts):
        self.item.texts = dict(texts)
        self.item.update()

    def select(self, cell):
        cell = cell if cell in self.item.positions else 0
        if cell != self.item.selected:
            self.item.selected = cell
            self.item.update()
            self.cellSelected.emit(cell)

    @property
    def selected(self):
        return self.item.selected

    # -- view -------------------------------------------------------------

    def fit(self):
        self.fitted = True
        self.fitInView(self.item.boundingRect(), Qt.KeepAspectRatio)

    def zoom(self, factor):
        self.fitted = False
        self.scale(factor, factor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fitted:
            self.fit()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
            self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
            event.accept()
        else:
            super().wheelEvent(event)

    def _cell_at(self, position):
        if not self.item.definition:
            return 0
        return self.item.cell_at(self.mapToScene(position))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.select(self._cell_at(event.position().toPoint()))
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            cell = self._cell_at(event.position().toPoint())
            if cell:
                self.select(cell)
                self.cellActivated.emit(cell)
        super().mouseDoubleClickEvent(event)

    # -- drag and drop ----------------------------------------------------

    @staticmethod
    def _pdf_paths(mime):
        return [
            url.toLocalFile()
            for url in mime.urls()
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf")
        ]

    def dragEnterEvent(self, event):
        if self._pdf_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        cell = self._cell_at(event.position().toPoint())
        if cell and self._pdf_paths(event.mimeData()):
            if cell != self.item.selected:
                self.select(cell)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        cell = self._cell_at(event.position().toPoint())
        paths = self._pdf_paths(event.mimeData())
        if cell and paths:
            event.acceptProposedAction()
            self.filesDropped.emit(cell, paths)
        else:
            event.ignore()
