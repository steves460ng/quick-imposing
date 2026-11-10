"""Template validation and preset expansion; never reads expected test results."""

import math
from pathlib import Path
import pikepdf as p

MM = 72 / 25.4
ROOT = Path(__file__).resolve().parent


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def vector(value, length, positive=False):
    return (
        isinstance(value, list)
        and len(value) == length
        and all(number(x) and (not positive or x > 0) for x in value)
    )


def placement_matrix(box, rotation, x, y, sheet_height, size):
    """Rotate crop corners, then translate their minimum to the slot origin."""
    a, b, c, d = {
        0: (1, 0, 0, 1),
        90: (0, 1, -1, 0),
        -90: (0, -1, 1, 0),
        180: (-1, 0, 0, -1),
    }[rotation]
    x0, y0, x1, y1 = box
    corners = [(a * u + c * v, b * u + d * v) for u in (x0, x1) for v in (y0, y1)]
    return [
        a,
        b,
        c,
        d,
        x * MM - min(u for u, v in corners),
        sheet_height - (y + size[1]) * MM - min(v for u, v in corners),
    ]


def preset_positions(cfg, width, height):
    if "slots_mm" in cfg:
        slots = cfg["slots_mm"]
        if not isinstance(slots, list) or not all(vector(s, 2) for s in slots):
            raise ValueError("Invalid slots_mm")
        return {i + 1: tuple(s) for i, s in enumerate(slots)}
    cols, rows = cfg["grid"]
    gx, gy = cfg["gap_mm"]
    if any(type(v) != int or v <= 0 for v in (cols, rows)) or cols * rows > 10000:
        raise ValueError("Invalid grid")
    if not all(number(v) and v >= 0 for v in (gx, gy)):
        raise ValueError("Invalid gap / overlapping slots")
    cw, ch = cfg["card_size_mm"]
    gw, gh = cols * cw + (cols - 1) * gx, rows * ch + (rows - 1) * gy
    if cfg["align"] == "sheet-center":
        left, top = (width - gw) / 2, (height - gh) / 2
    elif cfg["align"] == "safe-area-center":
        x0, y0, x1, y1 = cfg["safe_area_mm"]
        left, top = (x0 + x1 - gw) / 2, (y0 + y1 - gh) / 2
    elif cfg["align"] == "margin" and vector(cfg.get("margin_mm"), 2):
        left, top = cfg["margin_mm"]
    else:
        raise ValueError("Invalid alignment")
    if cfg.get("slot_order", "row-major") != "row-major":
        raise ValueError("Invalid slot order")
    return {
        i + 1: (left + (i % cols) * (cw + gx), top + (i // cols) * (ch + gy))
        for i in range(cols * rows)
    }


def validate_template(t, root=ROOT):
    errors, warnings = [], []

    def error(code, **context):
        errors.append(dict(code=code, **context))

    def required(obj, key, valid):
        value = obj.get(key)
        if not valid(value):
            error("SCHEMA_INVALID", field=key)
        return value

    if not isinstance(t, dict):
        return [dict(code="SCHEMA_INVALID", field="template")], warnings
    required(t, "schema", lambda x: x == "quick-imposing/template@1")
    required(
        t,
        "name",
        lambda x: (
            isinstance(x, str)
            and bool(x)
            and x not in (".", "..")
            and "/" not in x
            and "\\" not in x
        ),
    )
    required(t, "units", lambda x: x == "mm")
    required(t, "origin", lambda x: x == "top-left")
    base = required(t, "base", lambda x: isinstance(x, dict))
    card = required(t, "card", lambda x: isinstance(x, dict))
    slots = required(t, "slots", lambda x: isinstance(x, list))
    data = required(t, "data", lambda x: isinstance(x, list))
    base = base if isinstance(base, dict) else {}
    card = card if isinstance(card, dict) else {}
    slots = slots if isinstance(slots, list) else []
    data = data if isinstance(data, list) else []
    path = required(base, "file", lambda x: isinstance(x, str) and bool(x))
    size = required(base, "size_mm", lambda x: vector(x, 2, True))
    safe = required(
        base, "safe_area_mm", lambda x: vector(x, 4) and x[0] < x[2] and x[1] < x[3]
    )
    cs = required(card, "size_mm", lambda x: vector(x, 2, True))
    rot = required(
        card, "rotation_deg", lambda x: type(x) == int and x in (0, 90, -90, 180)
    )
    required(card, "crop_anchor", lambda x: x == "center")
    required(card, "source_box", lambda x: x == "TrimBox")
    ids = set()
    valid_slots = []
    for s in slots:
        if (
            not isinstance(s, dict)
            or type(s.get("id")) != int
            or not number(s.get("x"))
            or not number(s.get("y"))
        ):
            error("SCHEMA_INVALID", field="slots")
            continue
        if s["id"] in ids:
            error("DUPLICATE_SLOT_ID", slot=s["id"])
        ids.add(s["id"])
        valid_slots.append(s)
        if vector(cs, 2, True) and vector(safe, 4):
            x, y = s["x"], s["y"]
            w, h = cs
            if x < safe[0] or y < safe[1] or x + w > safe[2] or y + h > safe[3]:
                error("SLOT_OUT_OF_SAFE_AREA", slot=s["id"])
    if vector(cs, 2, True):
        w, h = cs
        for i, a in enumerate(valid_slots):
            for b in valid_slots[i + 1 :]:
                if max(a["x"], b["x"]) < min(a["x"] + w, b["x"] + w) and max(
                    a["y"], b["y"]
                ) < min(a["y"] + h, b["y"] + h):
                    error("SLOT_OVERLAP", slots=[a["id"], b["id"]])

    def read_pdf(filename, is_base=False):
        file = (Path(root) / filename).resolve()
        if not file.is_file():
            error("FILE_NOT_FOUND", file=filename)
            return
        try:
            with p.open(file) as doc:
                if len(doc.pages) != 1:
                    raise ValueError("Expected exactly one page")
                page = doc.pages[0]
                if page.obj.get("/Rotate", 0) != 0 or page.obj.get("/UserUnit", 1) != 1:
                    raise ValueError("Unsupported page Rotate/UserUnit")
                if is_base:
                    box = list(map(float, page.MediaBox))
                    if box[:2] != [0, 0]:
                        raise ValueError("Nonzero base origin")
                    actual = [(box[2] - box[0]) / MM, (box[3] - box[1]) / MM]
                    if vector(size, 2, True) and any(
                        abs(a - b) > 0.1 for a, b in zip(actual, size)
                    ):
                        error("BASE_SIZE_MISMATCH", file=filename, actual_mm=actual)
                elif (
                    vector(cs, 2, True)
                    and type(rot) == int
                    and rot in (0, 90, -90, 180)
                ):
                    box = list(map(float, page.obj.get("/TrimBox", page.MediaBox)))
                    if "/TrimBox" not in page.obj:
                        warnings.append(dict(code="TRIMBOX_FALLBACK", file=filename))
                    w, h = cs if rot in (0, 180) else cs[::-1]
                    if box[2] - box[0] < w * MM or box[3] - box[1] < h * MM:
                        error("CARD_TOO_SMALL", file=filename)
        except (p.PdfError, ValueError, OSError) as exc:
            error(
                "SCHEMA_INVALID" if is_base else "INVALID_CARD_PDF",
                file=filename,
                reason=str(exc),
            )

    if isinstance(path, str) and path:
        read_pdf(path, True)
    assigned = set()
    files = set()
    for d in data:
        if (
            not isinstance(d, dict)
            or type(d.get("slot")) != int
            or not isinstance(d.get("file"), str)
            or not d["file"]
        ):
            error("SCHEMA_INVALID", field="data")
            continue
        slot = d["slot"]
        if slot not in ids:
            error("UNKNOWN_SLOT", slot=slot)
        if slot in assigned:
            error("DUPLICATE_SLOT_ASSIGNMENT", slot=slot)
        assigned.add(slot)
        files.add(d["file"])
    for file in sorted(files):
        read_pdf(file)
    return errors, warnings
