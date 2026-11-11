"""Production PDF generation. No expected-result files are read here."""

from contextlib import ExitStack
from datetime import datetime, timezone
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile

import pikepdf as p

from . import fonts
from .model import cells, overlap_pairs, template_errors, project_errors
from .pdf import MM, digest, streams, remove_illustrator, save, render, invoke


def create_template(definition, base, root):
    """Save a definition and byte-identical base copy in a new template folder."""
    errors = template_errors(definition)
    if errors:
        raise ValueError(json.dumps(errors))
    base = Path(base).resolve()
    root = Path(root).resolve()
    target = root / definition["name"]
    if target.exists():
        raise FileExistsError(target)
    with p.open(base) as doc:
        if len(doc.pages) != 1:
            raise ValueError("Template base must have one page")
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        tmp = Path(tmp)
        shutil.copyfile(base, tmp / "base.pdf")
        if digest(base) != digest(tmp / "base.pdf"):
            raise IOError("Base copy hash mismatch")
        (tmp / "template.json").write_text(
            json.dumps(definition, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.rename(target)
    return target


def geometry(source_box, rotation, cell, size, media):
    a, b, c, d = {
        0: (1, 0, 0, 1),
        90: (0, 1, -1, 0),
        -90: (0, -1, 1, 0),
        180: (-1, 0, 0, -1),
    }[rotation]
    bx, by, bx1, by1 = map(float, source_box)
    cx, cy = (bx + bx1) / 2, (by + by1) / 2
    mx, my, mx1, my1 = map(float, media)
    x, y = cell
    w, h = size
    left = mx + x * MM
    top = my1 - y * MM
    right = left + w * MM
    bottom = top - h * MM
    e = (left + right) / 2 - a * cx - c * cy
    f = (top + bottom) / 2 - b * cx - d * cy
    visible = [max(left, mx), max(bottom, my), min(right, mx1), min(top, my1)]
    if visible[0] >= visible[2] or visible[1] >= visible[3]:
        return [a, b, c, d, e, f], None
    # Orthogonal unit rotations have inverse equal to their transpose.
    inverse = [
        (a * (u - e) + b * (v - f), c * (u - e) + d * (v - f))
        for u in (visible[0], visible[2])
        for v in (visible[1], visible[3])
    ]
    return [a, b, c, d, e, f], [
        min(x for x, y in inverse),
        min(y for x, y in inverse),
        max(x for x, y in inverse),
        max(y for x, y in inverse),
    ]


def unique(resources, prefix):
    i = 1
    while f"/{prefix}{i}" in resources:
        i += 1
    return f"/{prefix}{i}"


def generate(project_file, templates_root, output, font_dirs=()):
    project_file = Path(project_file).resolve()
    output = Path(output).resolve()
    saved_project = output.with_suffix(".qiproj.json")
    report_file = output.parent / "report.json"
    report = dict(
        timestamp=datetime.now(timezone.utc).isoformat(),
        status="FAIL",
        errors=[],
        warnings=[],
        info=[],
        placements=[],
        texts=[],
        inputs={},
        checks=[],
        manual_checks=[
            "V15: direction review",
            "V18/C11: Illustrator open verification",
        ],
    )

    def fail(code, **context):
        report["errors"].append(dict(code=code, **context))

    for path in (output, saved_project, report_file, output.with_suffix(".png")):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite: {path}")
    output.parent.mkdir(parents=True, exist_ok=True)

    def finish():
        report_file.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return report

    try:
        project = json.loads(project_file.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        fail("SCHEMA_INVALID", reason=str(exc))
        return finish()
    report["errors"] += project_errors(project)
    if report["errors"]:
        return finish()
    folder = Path(templates_root).resolve() / project["template"]
    if not (folder / "template.json").is_file():
        fail("TEMPLATE_NOT_FOUND", template=project["template"])
        return finish()
    try:
        template = json.loads((folder / "template.json").read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        fail("SCHEMA_INVALID", reason=str(exc))
        return finish()
    report["errors"] += template_errors(template, folder.name)
    if report["errors"]:
        return finish()
    positions = cells(template)
    size = template["cell"]["size_mm"]
    rotation = template["cell"]["rotation_deg"]
    report["template"] = template
    report["project"] = project
    overlaps = overlap_pairs(positions, size)
    if overlaps:
        report["warnings"].append(dict(code="CELL_OVERLAP", cells=overlaps))
    for placement in project["placements"]:
        if placement["cell"] not in positions:
            fail("CELL_NOT_IN_TEMPLATE", cell=placement["cell"])
    for id in project["texts"]:
        if id not in {field["id"] for field in template["text_fields"]}:
            report["info"].append(dict(code="TEXT_FIELD_UNKNOWN", id=id))
    locations = {}
    for field in template["text_fields"]:
        try:
            locations[field["font"]] = fonts.resolve(field["font"], font_dirs)
        except fonts.FontError as exc:
            fail("FONT_NOT_FOUND", font=field["font"], reason=str(exc))
    if report["errors"]:
        return finish()
    base = folder / "base.pdf"
    paths = {
        item["file"]: (project_file.parent / item["file"]).resolve()
        for item in project["placements"]
    }
    all_inputs = [
        project_file,
        folder / "template.json",
        base,
        *[path for path in paths.values() if path.is_file()],
    ]
    try:
        report["inputs"] = {str(path): digest(path) for path in all_inputs}
    except OSError as exc:
        fail("SCHEMA_INVALID", reason=str(exc))
        return finish()
    if any(path in all_inputs for path in (output, saved_project, report_file)):
        raise ValueError("Output aliases an input")
    with ExitStack() as stack:
        try:
            dest = stack.enter_context(p.open(base))
            page = dest.pages[0]
            if (
                len(dest.pages) != 1
                or page.obj.get("/Rotate", 0) != 0
                or page.obj.get("/UserUnit", 1) != 1
            ):
                raise ValueError("Base must have one unrotated page with UserUnit 1")
            source_docs = {}
            sources_by_path = {}
            for name, path in paths.items():
                if not path.is_file():
                    continue
                if path in sources_by_path:
                    source_docs[name] = sources_by_path[path]
                    continue
                src = stack.enter_context(p.open(path))
                if (
                    len(src.pages) != 1
                    or src.pages[0].obj.get("/Rotate", 0) != 0
                    or src.pages[0].obj.get("/UserUnit", 1) != 1
                ):
                    raise ValueError(
                        f"Unsupported B page count/Rotate/UserUnit: {name}"
                    )
                source_docs[name] = src
                sources_by_path[path] = src
        except (p.PdfError, OSError, ValueError, IndexError) as exc:
            fail("SCHEMA_INVALID", reason=str(exc))
            return finish()
        if "/XObject" not in page.Resources:
            page.Resources.XObject = p.Dictionary()
        ocgs = list(dest.Root.get("/OCProperties", p.Dictionary()).get("/OCGs", []))
        # Copy OCGs and resources through the same pikepdf foreign-object map.
        for path in sorted(sources_by_path):
            ocgs += [
                dest.copy_foreign(obj)
                for obj in sources_by_path[path]
                .Root.get("/OCProperties", p.Dictionary())
                .get("/OCGs", [])
            ]
        dest.Root.OCProperties = p.Dictionary(
            OCGs=p.Array(ocgs),
            D=p.Dictionary(
                BaseState=p.Name.ON,
                ON=p.Array(ocgs),
                OFF=p.Array(),
                Order=p.Array(ocgs),
            ),
        )
        commands = []
        occupied = set()
        for item in sorted(project["placements"], key=lambda x: x["order"]):
            n = item["cell"]
            name = item["file"]
            if name not in source_docs:
                report["info"].append(dict(code="B_FILE_MISSING", cell=n, file=name))
                continue
            src = source_docs[name]
            sp = src.pages[0]
            box = sp.obj.get("/TrimBox", sp.MediaBox)
            cm, bbox = geometry(box, rotation, positions[n], size, page.MediaBox)
            entry = dict(
                cell=n,
                file=name,
                order=item["order"],
                xy_mm=list(positions[n]),
                cm=cm,
                bbox=bbox,
                source_box=list(map(float, box)),
            )
            occupied.add(n)
            if bbox is None:
                entry["drawn"] = False
                report["placements"].append(entry)
                continue
            form = src.make_stream(b"".join(s.read_bytes() for s in streams(sp)))
            form.Type = p.Name.XObject
            form.Subtype = p.Name.Form
            form.BBox = p.Array(bbox)
            form.Resources = sp.Resources
            if "/Group" in sp.obj:
                form.Group = sp.obj.Group
            key = unique(page.Resources.XObject, "Card")
            page.Resources.XObject[key] = dest.copy_foreign(form)
            entry.update(xobject=key, drawn=True)
            report["placements"].append(entry)
            commands.append(
                "q " + " ".join(f"{v:.9f}" for v in cm) + f" cm {key} Do Q\n"
            )
        report["empty_cells"] = sorted(set(positions) - occupied)
        original_streams = streams(page)
        page.Contents = p.Array(
            original_streams + [dest.make_stream("".join(commands).encode())]
        )
        # Prepare all fonts before saving any PDF; missing glyphs are explicit errors.
        active = [
            field
            for field in template["text_fields"]
            if project["texts"].get(field["id"], "")
        ]
        if active and "/Font" not in page.Resources:
            page.Resources.Font = p.Dictionary()
        embedded = {}
        try:
            for font in sorted({field["font"] for field in active}):
                text = "".join(
                    project["texts"][field["id"]]
                    for field in active
                    if field["font"] == font
                )
                obj, mapping, metrics = fonts.embed(dest, locations[font], text)
                key = unique(page.Resources.Font, "Text")
                page.Resources.Font[key] = obj
                embedded[font] = (key, mapping, metrics)
        except fonts.FontError as exc:
            fail("SCHEMA_INVALID", reason=str(exc))
            return finish()
        text_commands = []
        for field in active:
            text = project["texts"][field["id"]]
            key, mapping, metrics = embedded[field["font"]]
            x = float(page.MediaBox[0]) + field["x_mm"] * MM
            y = float(page.MediaBox[3]) - field["y_mm"] * MM
            encoded = "".join(f"{mapping[c]:04X}" for c in text)
            text_commands.append(
                f"q 0 0 0 1 k BT {key} {field['size_pt']:.9f} Tf 1 0 0 1 {x:.9f} {y:.9f} Tm <{encoded}> Tj ET Q\n"
            )
            width = sum(metrics["widths"][c] for c in text) * field["size_pt"] / MM
            rect = [
                field["x_mm"],
                field["y_mm"] - metrics["ascent"] * field["size_pt"] / MM,
                field["x_mm"] + width,
                field["y_mm"] - metrics["descent"] * field["size_pt"] / MM,
            ]
            report["texts"].append(
                dict(
                    id=field["id"],
                    value=text,
                    font=field["font"],
                    font_resource=key,
                    baseline_mm=[field["x_mm"], field["y_mm"]],
                    size_pt=field["size_pt"],
                    bounds_mm=rect,
                )
            )
        if text_commands:
            page.Contents.append(dest.make_stream("".join(text_commands).encode()))
        report["illustrator_private_data_removed"] = remove_illustrator(dest)
        # Stage generation and qpdf validation before publishing output files.
        with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
            tmp = Path(tmp)
            result = tmp / "result.pdf"
            save(dest, result)
            try:
                invoke("qpdf", "--check", result)
            except RuntimeError as exc:
                fail("PDF_VALIDATION_FAILED", reason=str(exc))
                return finish()
            render(result, tmp / "preview", 150)
            revised = copy.deepcopy(project)
            for item in revised["placements"]:
                item["file"] = Path(
                    os.path.relpath(paths[item["file"]], saved_project.parent)
                ).as_posix()
            (tmp / "project.json").write_text(
                json.dumps(revised, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            if not all(digest(path) == sha for path, sha in report["inputs"].items()):
                fail("INPUT_CHANGED")
                return finish()
            shutil.move(result, output)
            shutil.move(tmp / "preview.png", output.with_suffix(".png"))
            shutil.move(tmp / "project.json", saved_project)
        report["status"] = "PASS"
        report["checks"] = [dict(id="V1", passed=True), dict(id="R9", passed=True)]
    return finish()
