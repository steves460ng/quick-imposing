"""In-memory editing of one job (project@1) for the work program.

The session keeps B files as absolute paths while editing. Relative paths are
only computed when the project is written next to the output PDF.
"""

import json
import os
from pathlib import Path

from .autofill import natural_file_key, plan_fill
from .engine import generate
from .model import cells, overlap_pairs, project_errors
from . import store


class SessionError(ValueError):
    """A job cannot be opened or saved; ``str()`` is a Korean user message."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


OUTPUT_SUFFIXES = (".pdf", ".qiproj.json", ".png", ".report.json")


def output_files(pdf_path):
    """The four files a build writes for one output PDF path."""
    pdf_path = Path(pdf_path)
    return [pdf_path.with_suffix(suffix) for suffix in OUTPUT_SUFFIXES]


def free_output_path(pdf_path):
    """``pdf_path``, or the first ``name-2.pdf``, ``name-3.pdf``… that is free."""
    pdf_path = Path(pdf_path)
    candidate = pdf_path
    number = 2
    while any(path.exists() for path in output_files(candidate)):
        candidate = pdf_path.with_name(f"{pdf_path.stem}-{number}.pdf")
        number += 1
    return candidate


class Session:
    def __init__(self, root, definition):
        self.root = Path(root)
        self.template = definition
        self.texts = {field["id"]: "" for field in definition["text_fields"]}
        self.placements = {}  # cell -> dict(path=Path, order=int)
        self.project_path = None
        self.dirty = False

    # -- construction -----------------------------------------------------

    @classmethod
    def new(cls, root, template_name):
        return cls(root, store.load_template(root, template_name))

    @classmethod
    def open(cls, root, project_file):
        """Open a saved project against the template as it is stored now."""
        project_file = Path(os.path.abspath(project_file))
        try:
            data = json.loads(project_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SessionError(f"프로젝트 파일을 읽을 수 없습니다.\n{exc}") from None
        if project_errors(data):
            raise SessionError(
                "프로젝트 파일 형식이 올바르지 않습니다.", "SCHEMA_INVALID"
            )
        try:
            session = cls.new(root, data["template"])
        except store.TemplateError as exc:
            raise SessionError(str(exc), "TEMPLATE_NOT_FOUND") from None
        known = session.cell_positions()
        missing = sorted(
            item["cell"] for item in data["placements"] if item["cell"] not in known
        )
        if missing:
            raise SessionError(
                "현재 템플릿에 없는 셀을 쓰는 프로젝트입니다. "
                f"템플릿 '{data['template']}'의 셀 수가 줄었는지 확인하세요.\n"
                f"없는 셀: {', '.join(map(str, missing))}",
                "CELL_NOT_IN_TEMPLATE",
            )
        for id, value in data["texts"].items():
            # Values for fields the template no longer has are kept on save.
            session.texts[id] = value
        for item in data["placements"]:
            session.placements[item["cell"]] = dict(
                path=Path(os.path.abspath(project_file.parent / item["file"])),
                order=item["order"],
            )
        session.project_path = project_file
        return session

    # -- queries ----------------------------------------------------------

    @property
    def template_name(self):
        return self.template["name"]

    def cell_positions(self):
        return cells(self.template)

    def overlaps(self):
        return overlap_pairs(self.cell_positions(), self.template["cell"]["size_mm"])

    def field_ids(self):
        return [field["id"] for field in self.template["text_fields"]]

    def next_order(self):
        return max((item["order"] for item in self.placements.values()), default=0) + 1

    # -- editing ----------------------------------------------------------

    def set_text(self, id, value):
        if self.texts.get(id, "") != value:
            self.texts[id] = value
            self.dirty = True

    def assign(self, cell, path):
        """Put one B into a cell. An occupied cell keeps its drawing order."""
        if cell not in self.cell_positions():
            raise SessionError(f"템플릿에 없는 셀입니다: {cell}", "CELL_NOT_IN_TEMPLATE")
        path = Path(os.path.abspath(path))
        if cell in self.placements:
            self.placements[cell]["path"] = path
        else:
            self.placements[cell] = dict(path=path, order=self.next_order())
        self.dirty = True

    def remove(self, cell):
        if self.placements.pop(cell, None) is not None:
            self.dirty = True

    def clear(self):
        if self.placements:
            self.placements.clear()
            self.dirty = True

    def fill(self, start_cell, paths):
        """Auto-fill from ``start_cell`` in file-name order.

        Returns dict(added=[(cell, path)], reason, blocked_cell, unplaced=[path]).
        Filling stops in front of an occupied cell or after the last cell.
        """
        if start_cell not in self.cell_positions():
            raise SessionError(
                f"템플릿에 없는 셀입니다: {start_cell}", "CELL_NOT_IN_TEMPLATE"
            )
        ordered = sorted(
            (Path(os.path.abspath(path)) for path in paths), key=natural_file_key
        )
        assigned, reason, blocked_cell = plan_fill(
            self.template["grid"]["count"],
            self.template["fill_direction"],
            set(self.placements),
            start_cell,
            len(ordered),
        )
        added = list(zip(assigned, ordered))
        for cell, path in added:
            self.placements[cell] = dict(path=path, order=self.next_order())
        if added:
            self.dirty = True
        return dict(
            added=added,
            reason=reason,
            blocked_cell=blocked_cell,
            unplaced=ordered[len(assigned) :],
        )

    # -- saving -----------------------------------------------------------

    def to_project(self, folder):
        """project@1 data with B paths relative to ``folder``."""
        try:
            placements = [
                dict(
                    cell=cell,
                    file=Path(os.path.relpath(item["path"], folder)).as_posix(),
                    order=item["order"],
                )
                for cell, item in sorted(
                    self.placements.items(), key=lambda entry: entry[1]["order"]
                )
            ]
        except ValueError:
            raise SessionError(
                "B 데이터와 저장 위치는 같은 드라이브에 있어야 합니다.\n"
                "B 데이터가 있는 드라이브에 저장하세요.",
                "DIFFERENT_DRIVE",
            ) from None
        return dict(
            schema="quick-imposing/project@1",
            template=self.template_name,
            texts=dict(self.texts),
            placements=placements,
        )

    def save(self, pdf_path, font_dirs=()):
        """Build the PDF, project, preview and report next to ``pdf_path``.

        Existing output files are never overwritten. Returns the build report;
        ``report["status"]`` is "PASS" when the PDF was written.
        """
        pdf_path = Path(os.path.abspath(pdf_path))
        if pdf_path.suffix.lower() != ".pdf":
            pdf_path = pdf_path.with_name(pdf_path.name + ".pdf")
        existing = [path for path in output_files(pdf_path) if path.exists()]
        if existing:
            raise SessionError(
                "같은 이름의 파일이 이미 있습니다. 다른 이름으로 저장하세요.\n"
                + "\n".join(path.name for path in existing),
                "OUTPUT_EXISTS",
            )
        project = self.to_project(pdf_path.parent)
        staged = pdf_path.with_name(f"~{pdf_path.stem}.{os.getpid()}.input.json")
        try:
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            staged.write_text(
                json.dumps(project, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            report = generate(staged, self.root, pdf_path, font_dirs)
        except (OSError, ValueError, RuntimeError) as exc:
            raise SessionError(f"저장하지 못했습니다.\n{exc}") from None
        finally:
            staged.unlink(missing_ok=True)
        if report["status"] == "PASS":
            self.project_path = pdf_path.with_suffix(".qiproj.json")
            self.dirty = False
        else:
            # A failed build leaves only its report; remove it so the same
            # name can be used again once the cause is fixed.
            pdf_path.with_suffix(".report.json").unlink(missing_ok=True)
        return report
