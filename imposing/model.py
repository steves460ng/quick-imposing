"""Schema checks and deterministic cell geometry for template@2/project@1."""

import math
import ntpath
from pathlib import Path


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


def template_errors(t, folder=None):
    errors = []

    def require(ok, field):
        if not ok:
            errors.append(dict(code="SCHEMA_INVALID", field=field))

    if not isinstance(t, dict):
        return [dict(code="SCHEMA_INVALID", field="template")]
    require(t.get("schema") == "quick-imposing/template@2", "template.schema")
    require(
        name_valid(t.get("name")) and (folder is None or t.get("name") == folder),
        "template.name",
    )
    require(t.get("base") == "base.pdf", "template.base")
    c = t.get("cell", {})
    g = t.get("grid", {})
    if not isinstance(c, dict):
        c = {}
    if not isinstance(g, dict):
        g = {}
    require(pair(c.get("size_mm"), True), "cell.size_mm")
    require(
        type(c.get("rotation_deg")) == int and c["rotation_deg"] in (0, 90, -90, 180),
        "cell.rotation_deg",
    )
    require(pair(g.get("origin_mm")), "grid.origin_mm")
    require(
        pair(g.get("pitch_mm")) and all(v >= 0 for v in g["pitch_mm"]),
        "grid.pitch_mm",
    )
    require(
        isinstance(g.get("count"), list)
        and len(g["count"]) == 2
        and all(type(v) == int and v > 0 for v in g["count"]),
        "grid.count",
    )
    require(t.get("fill_direction") in ("forward", "reverse"), "fill_direction")
    fields = t.get("text_fields")
    require(isinstance(fields, list), "text_fields")
    ids = set()
    for f in fields if isinstance(fields, list) else []:
        if not isinstance(f, dict):
            require(False, "text_fields")
            continue
        id = f.get("id")
        valid = isinstance(id, str) and bool(id)
        require(valid and id not in ids, "text_fields.id")
        if valid:
            ids.add(id)
        require(number(f.get("x_mm")) and number(f.get("y_mm")), "text_fields.position")
        require(number(f.get("size_pt")) and f["size_pt"] > 0, "text_fields.size_pt")
        require(isinstance(f.get("font"), str) and bool(f["font"]), "text_fields.font")
    return errors


def project_errors(project):
    if not isinstance(project, dict):
        return [dict(code="SCHEMA_INVALID", field="project")]
    errors = []

    def require(ok, field):
        if not ok:
            errors.append(dict(code="SCHEMA_INVALID", field=field))

    require(project.get("schema") == "quick-imposing/project@1", "project.schema")
    require(name_valid(project.get("template")), "project.template")
    texts = project.get("texts")
    require(
        isinstance(texts, dict) and all(isinstance(v, str) for v in texts.values()),
        "project.texts",
    )
    placements = project.get("placements")
    require(isinstance(placements, list), "project.placements")
    cells = set()
    orders = set()
    for item in placements if isinstance(placements, list) else []:
        if not isinstance(item, dict):
            require(False, "placements")
            continue
        cell, order = item.get("cell"), item.get("order")
        require(type(cell) == int and cell > 0 and cell not in cells, "placements.cell")
        require(
            type(order) == int and order > 0 and order not in orders, "placements.order"
        )
        if type(cell) == int:
            cells.add(cell)
        if type(order) == int:
            orders.add(order)
        require(relative_path(item.get("file")), "placements.file")
    return errors


def cells(template):
    grid = template["grid"]
    nx, ny = grid["count"]
    x, y = grid["origin_mm"]
    px, py = grid["pitch_mm"]
    return {
        r * nx + c + 1: (x + c * px, y + r * py) for r in range(ny) for c in range(nx)
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
