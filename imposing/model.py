"""Schema checks and deterministic cell geometry for template@2/project@1."""

import math
import ntpath
import os
from pathlib import Path


class PathError(ValueError):
    """A path cannot be stored; ``code`` is the report error code."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def pair(value, positive=False):
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(number(x) and (not positive or x > 0) for x in value)
    )


def name_valid(value):
    return (
        isinstance(value, str)
        and bool(value)
        and value not in (".", "..")
        and not any(c in value for c in '\\/:*?"<>|')
        and not any(ord(c) < 32 for c in value)
        and not value.endswith((" ", "."))
    )


def relative_path(value):
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and not ntpath.isabs(value)
        and not ntpath.splitdrive(value)[0]
    )


def relative_file(path, folder):
    """``path`` relative to ``folder`` in POSIX form, as stored in project@1.

    Raises PathError("DIFFERENT_DRIVE") when no relative path exists, i.e. the
    two are on different Windows drives.
    """
    try:
        return Path(os.path.relpath(path, folder)).as_posix()
    except ValueError as exc:
        raise PathError(
            f"No relative path from {folder} to {path}: {exc}", "DIFFERENT_DRIVE"
        ) from None


def schema_error(field, reason):
    """One report error entry for an invalid field (SPEC §6.4)."""
    return dict(code="SCHEMA_INVALID", reason=f"{field}: {reason}", field=field)


def template_errors(t, folder=None):
    errors = []

    def require(ok, field, reason):
        if not ok:
            errors.append(schema_error(field, reason))

    if not isinstance(t, dict):
        return [schema_error("template", "must be an object")]
    require(
        t.get("schema") == "quick-imposing/template@2",
        "template.schema",
        "must be quick-imposing/template@2",
    )
    require(
        name_valid(t.get("name")) and (folder is None or t.get("name") == folder),
        "template.name",
        "must be a valid folder name matching the template folder",
    )
    require(t.get("base") == "base.pdf", "template.base", "must be base.pdf")
    c = t.get("cell", {})
    g = t.get("grid", {})
    if not isinstance(c, dict):
        c = {}
    if not isinstance(g, dict):
        g = {}
    require(
        pair(c.get("size_mm"), True),
        "cell.size_mm",
        "must be two positive numbers",
    )
    require(
        type(c.get("rotation_deg")) == int and c["rotation_deg"] in (0, 90, -90, 180),
        "cell.rotation_deg",
        "must be 0, 90, -90 or 180",
    )
    require(pair(g.get("origin_mm")), "grid.origin_mm", "must be two numbers")
    require(
        pair(g.get("pitch_mm")) and all(v >= 0 for v in g["pitch_mm"]),
        "grid.pitch_mm",
        "must be two numbers, not negative",
    )
    require(
        isinstance(g.get("count"), list)
        and len(g["count"]) == 2
        and all(type(v) == int and v > 0 for v in g["count"]),
        "grid.count",
        "must be two positive integers",
    )
    require(
        t.get("fill_direction") in ("forward", "reverse"),
        "fill_direction",
        "must be forward or reverse",
    )
    require(
        isinstance(t.get("memo", ""), str), "memo", "must be a string if present"
    )
    offsets = t.get("cell_offsets", {})
    count = g.get("count")
    total = (
        count[0] * count[1]
        if isinstance(count, list) and len(count) == 2 and all(type(v) == int for v in count)
        else None
    )
    require(
        isinstance(offsets, dict)
        and all(
            isinstance(key, str)
            and key.isdigit()
            and int(key) >= 1
            and (total is None or int(key) <= total)
            and pair(value)
            for key, value in offsets.items()
        ),
        "cell_offsets",
        "must map existing cell numbers to two numbers [dx, dy] in mm",
    )
    fields = t.get("text_fields")
    require(isinstance(fields, list), "text_fields", "must be a list")
    ids = set()
    for f in fields if isinstance(fields, list) else []:
        if not isinstance(f, dict):
            require(False, "text_fields", "each entry must be an object")
            continue
        id = f.get("id")
        valid = isinstance(id, str) and bool(id)
        require(
            valid and id not in ids,
            "text_fields.id",
            "must be a nonempty string, unique in the template",
        )
        if valid:
            ids.add(id)
        require(
            number(f.get("x_mm")) and number(f.get("y_mm")),
            "text_fields.position",
            "x_mm and y_mm must be numbers",
        )
        require(
            number(f.get("size_pt")) and f["size_pt"] > 0,
            "text_fields.size_pt",
            "must be a positive number",
        )
        require(
            isinstance(f.get("font"), str) and bool(f["font"]),
            "text_fields.font",
            "must be a nonempty font name",
        )
    return errors


def project_errors(project):
    if not isinstance(project, dict):
        return [schema_error("project", "must be an object")]
    errors = []

    def require(ok, field, reason):
        if not ok:
            errors.append(schema_error(field, reason))

    require(
        project.get("schema") == "quick-imposing/project@1",
        "project.schema",
        "must be quick-imposing/project@1",
    )
    require(
        name_valid(project.get("template")),
        "project.template",
        "must be a valid template name",
    )
    texts = project.get("texts")
    require(
        isinstance(texts, dict) and all(isinstance(v, str) for v in texts.values()),
        "project.texts",
        "must be an object of strings",
    )
    placements = project.get("placements")
    require(isinstance(placements, list), "project.placements", "must be a list")
    cells = set()
    orders = set()
    for item in placements if isinstance(placements, list) else []:
        if not isinstance(item, dict):
            require(False, "placements", "each entry must be an object")
            continue
        cell, order = item.get("cell"), item.get("order")
        require(
            type(cell) == int and cell > 0 and cell not in cells,
            "placements.cell",
            "must be a positive integer, one placement per cell",
        )
        require(
            type(order) == int and order > 0 and order not in orders,
            "placements.order",
            "must be a positive integer, unique in the project",
        )
        if type(cell) == int:
            cells.add(cell)
        if type(order) == int:
            orders.add(order)
        require(
            relative_path(item.get("file")),
            "placements.file",
            "must be a nonempty relative path",
        )
    return errors


def base_cells(template):
    """Cell top-left corners from the grid alone (mm, sheet top-left origin)."""
    grid = template["grid"]
    nx, ny = grid["count"]
    x, y = grid["origin_mm"]
    px, py = grid["pitch_mm"]
    return {
        r * nx + c + 1: (x + c * px, y + r * py) for r in range(ny) for c in range(nx)
    }


def cell_offsets(template):
    """Per-cell corrections {cell: (dx, dy)} in mm; cells without one are absent."""
    return {
        int(cell): (float(dx), float(dy))
        for cell, (dx, dy) in template.get("cell_offsets", {}).items()
    }


def cells(template):
    """Actual cell top-left corners: grid position plus the cell's correction."""
    offsets = cell_offsets(template)
    return {
        cell: (x + offsets.get(cell, (0, 0))[0], y + offsets.get(cell, (0, 0))[1])
        for cell, (x, y) in base_cells(template).items()
    }


def overlap_pairs(positions, size):
    w, h = size
    values = list(positions.items())
    result = []
    for i, (a, (x, y)) in enumerate(values):
        for b, (u, v) in values[i + 1 :]:
            if max(x, u) < min(x + w, u + w) and max(y, v) < min(y + h, v + h):
                result.append([a, b])
    return result
