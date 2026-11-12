"""Template folder management shared by the GUI programs.

A template is one folder ``<root>/<name>/`` holding ``template.json`` and a
byte-identical copy of the base PDF (``base.pdf``).
"""

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import pikepdf as p
from fontTools.ttLib import TTFont, TTLibError

from . import fonts
from .autofill import natural_file_key
from .engine import create_template
from .model import template_errors
from .pdf import MM, digest

APP_FOLDER = "QuickImposing"


class TemplateError(ValueError):
    """A template cannot be read or saved; ``str()`` is a Korean user message."""


def default_templates_root():
    """Per-user template folder; ``QUICK_IMPOSING_TEMPLATES`` overrides it."""
    override = os.environ.get("QUICK_IMPOSING_TEMPLATES")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData/Local")
        return Path(base) / APP_FOLDER / "templates"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    return Path(base) / "quick-imposing" / "templates"


def list_templates(root):
    """Names of the template folders in ``root`` in Explorer-like order."""
    root = Path(root)
    if not root.is_dir():
        return []
    names = [
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and (entry / "template.json").is_file()
    ]
    return sorted(names, key=lambda name: natural_file_key(root / name)[0])


def load_template(root, name):
    folder = Path(root) / name
    try:
        definition = json.loads((folder / "template.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise TemplateError(f"템플릿을 찾을 수 없습니다: {name}") from None
    except (OSError, ValueError) as exc:
        raise TemplateError(f"템플릿 파일을 읽을 수 없습니다: {name}\n{exc}") from None
    errors = template_errors(definition, folder.name)
    if errors:
        fields = ", ".join(sorted({entry["field"] for entry in errors}))
        raise TemplateError(f"템플릿 형식이 올바르지 않습니다: {name}\n({fields})")
    if not (folder / "base.pdf").is_file():
        raise TemplateError(f"템플릿에 베이스 PDF가 없습니다: {name}")
    return definition


def base_path(root, name):
    return Path(root) / name / "base.pdf"


def page_size_mm(pdf_path):
    """(width, height) of a one-page PDF's MediaBox in mm."""
    try:
        with p.open(pdf_path) as doc:
            if len(doc.pages) != 1:
                raise TemplateError("베이스 PDF는 1페이지여야 합니다.")
            box = [float(v) for v in doc.pages[0].MediaBox]
    except (p.PdfError, OSError) as exc:
        raise TemplateError(f"PDF를 열 수 없습니다: {exc}") from None
    return (box[2] - box[0]) / MM, (box[3] - box[1]) / MM


def save_template(definition, root, base=None):
    """Create a template folder, or update the definition of an existing one.

    A new template needs ``base``. For an existing template the definition is
    replaced atomically; ``base`` (optional) replaces the stored base copy.
    """
    errors = template_errors(definition)
    if errors:
        fields = ", ".join(sorted({entry["field"] for entry in errors}))
        raise TemplateError(f"입력값이 올바르지 않습니다: {fields}")
    root = Path(root)
    folder = root / definition["name"]
    if not folder.exists():
        if base is None:
            raise TemplateError("새 템플릿에는 베이스 PDF가 필요합니다.")
        page_size_mm(base)
        try:
            return create_template(definition, base, root)
        except (OSError, ValueError, p.PdfError) as exc:
            raise TemplateError(f"템플릿을 저장할 수 없습니다: {exc}") from None
    if not (folder / "template.json").is_file():
        raise TemplateError(
            f"같은 이름의 폴더가 있지만 템플릿이 아닙니다: {definition['name']}"
        )
    try:
        with tempfile.TemporaryDirectory(dir=folder) as tmp:
            tmp = Path(tmp)
            if base is not None and Path(base).resolve() != (folder / "base.pdf").resolve():
                page_size_mm(base)
                shutil.copyfile(base, tmp / "base.pdf")
                if digest(base) != digest(tmp / "base.pdf"):
                    raise OSError("Base copy hash mismatch")
                os.replace(tmp / "base.pdf", folder / "base.pdf")
            (tmp / "template.json").write_text(
                json.dumps(definition, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp / "template.json", folder / "template.json")
    except OSError as exc:
        raise TemplateError(f"템플릿을 저장할 수 없습니다: {exc}") from None
    return folder


def delete_template(root, name):
    """Remove one template folder. Only a folder holding template.json goes."""
    folder = Path(root) / name
    if not (folder / "template.json").is_file():
        raise TemplateError(f"템플릿을 찾을 수 없습니다: {name}")
    try:
        shutil.rmtree(folder)
    except OSError as exc:
        raise TemplateError(f"템플릿을 삭제할 수 없습니다: {exc}") from None


def usable_fonts(extra=()):
    """Display names of installed fonts that the engine can embed.

    Names come from the family name records (nameID 1) of every face. A name
    is kept only when the face the engine would pick for it is embeddable:
    TrueType or CID-keyed CFF, and not licence-restricted.
    """
    display = {}
    for directory in [*map(Path, extra), *fonts.system_dirs()]:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.suffix.lower() not in (".ttf", ".otf", ".ttc", ".otc"):
                continue
            index = 0
            while True:
                try:
                    font = TTFont(path, fontNumber=index, lazy=True)
                except (TTLibError, OSError, UnicodeError, IndexError):
                    break
                try:
                    for record in font["name"].names:
                        if record.nameID == 1:
                            name = record.toUnicode().strip()
                            if name:
                                display.setdefault(name.casefold(), name)
                except (TTLibError, UnicodeError, KeyError):
                    pass
                finally:
                    font.close()
                if path.suffix.lower() not in (".ttc", ".otc"):
                    break
                index += 1
    usable = []
    extra = tuple(str(d) for d in extra)
    for name in display.values():
        try:
            location = fonts.resolve(name, extra)
        except fonts.FontError:
            continue
        if _embeddable(*location):
            usable.append(name)
    return sorted(usable, key=str.casefold)


def _embeddable(path, index):
    try:
        font = TTFont(path, fontNumber=index, lazy=True)
    except (TTLibError, OSError):
        return False
    try:
        if font["OS/2"].fsType & 2:
            return False
        if "CFF " in font:
            return hasattr(font["CFF "].cff.topDictIndex[0], "ROS")
        return "glyf" in font
    except (TTLibError, KeyError, AttributeError):
        return False
    finally:
        font.close()
