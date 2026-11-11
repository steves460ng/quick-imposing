"""Independent TASK-03-1 fixture runner. Expected files are test inputs only."""

import argparse
from collections import Counter
from contextlib import ExitStack
import json
import math
from pathlib import Path
import tempfile

import pikepdf as p
from PIL import Image, ImageChops, ImageDraw

from imposing.engine import create_template, generate
from imposing.pdf import canonical, digest, invoke, render, save, streams

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "samples/test03-1"
PT = 72 / 25.4


def independent_geometry(t, n, source, media):
    """Independent center formulas from TASK section 3.1 (not engine helpers)."""
    nx, ny = t["grid"]["count"]
    col = (n - 1) % nx
    row = (n - 1) // nx
    x = t["grid"]["origin_mm"][0] + col * t["grid"]["pitch_mm"][0]
    y = t["grid"]["origin_mm"][1] + row * t["grid"]["pitch_mm"][1]
    w, h = t["cell"]["size_mm"]
    rotation = t["cell"]["rotation_deg"]
    x0, y0, x1, y1 = map(float, source)
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    mx, my, mx1, my1 = map(float, media)
    CX = mx + (x + w / 2) * PT
    CY = my1 - (y + h / 2) * PT
    if rotation == 0:
        cm = [1, 0, 0, 1, CX - cx, CY - cy]
    elif rotation == 90:
        cm = [0, 1, -1, 0, CX + cy, CY - cx]
    elif rotation == -90:
        cm = [0, -1, 1, 0, CX - cy, CY + cx]
    else:
        cm = [-1, 0, 0, -1, CX + cx, CY + cy]
    a, b, c, d, e, f = cm
    det = a * d - b * c
    rect = [
        max(mx, mx + x * PT),
        max(my, my1 - (y + h) * PT),
        min(mx1, mx + (x + w) * PT),
        min(my1, my1 - y * PT),
    ]
    points = [
        ((d * (u - e) - c * (v - f)) / det, (-b * (u - e) + a * (v - f)) / det)
        for u in (rect[0], rect[2])
        for v in (rect[1], rect[3])
    ]
    box = [
        min(u for u, v in points),
        min(v for u, v in points),
        max(u for u, v in points),
        max(v for u, v in points),
    ]
    return cm, box, rect, [x, y, x + w, y + h]


def close(a, b, tolerance=0.01):
    return len(a) == len(b) and all(
        abs(float(x) - float(y)) <= tolerance for x, y in zip(a, b)
    )


def pixel_difference(a, b):
    if a.size != b.size:
        return -1
    diff = ImageChops.difference(a, b)
    return sum(1 for rgb in diff.get_flattened_data() if rgb != (0, 0, 0))


def rectangle_mask(rect, dpi, margin=0):
    x0, y0, x1, y1 = rect
    scale = dpi / 25.4
    return (
        math.floor((x0 - margin) * scale),
        math.floor((y0 - margin) * scale),
        math.ceil((x1 + margin) * scale),
        math.ceil((y1 + margin) * scale),
    )


def specimen(form, cm, rect, target):
    """Render original or extracted artwork through an independent page clip.

    The source reference uses Page.as_form_xobject(), not engine Form creation.
    A rectangle page restricts the visible portion without editing source bytes.
    """
    x0, y0, x1, y1 = rect
    width = x1 - x0
    height = y1 - y0
    with p.new() as doc:
        page = doc.add_blank_page(page_size=(width, height))
        obj = doc.copy_foreign(form)
        page.Resources = p.Dictionary(XObject=p.Dictionary(Artwork=obj))
        a, b, c, d, e, f = cm
        page.Contents = doc.make_stream(
            (
                f"q 0 0 {width:.9f} {height:.9f} re W n "
                + " ".join(f"{v:.9f}" for v in [a, b, c, d, e - x0, f - y0])
                + " cm /Artwork Do Q\n"
            ).encode()
        )
        save(doc, target)


def reference_sheet(base, t, project, project_dir, target, selected=None):
    """Draw original pages using independent geometry and page-space clips."""
    with ExitStack() as stack:
        doc = stack.enter_context(p.open(base))
        pg = doc.pages[0]
        if "/XObject" not in pg.Resources:
            pg.Resources.XObject = p.Dictionary()
        commands = []
        for index, item in enumerate(
            sorted(project["placements"], key=lambda x: x["order"])
        ):
            if selected is not None and item["cell"] not in selected:
                continue
            file = project_dir / item["file"]
            if not file.is_file():
                continue
            source = stack.enter_context(p.open(file))
            sp = source.pages[0]
            cm, box, rect, mm = independent_geometry(
                t, item["cell"], sp.obj.get("/TrimBox", sp.MediaBox), pg.MediaBox
            )
            key = f"/Reference{index}"
            pg.Resources.XObject[key] = doc.copy_foreign(sp.as_form_xobject())
            x0, y0, x1, y1 = rect
            commands.append(
                f"q {x0:.9f} {y0:.9f} {x1 - x0:.9f} {y1 - y0:.9f} re W n "
                + " ".join(f"{v:.9f}" for v in cm)
                + f" cm {key} Do Q\n"
            )
        pg.Contents = p.Array(
            streams(pg) + [doc.make_stream("".join(commands).encode())]
        )
        save(doc, target)


def font_rows(path):
    return [
        tuple(line.split()[:-2]) for line in invoke("pdffonts", path).splitlines()[2:]
    ]


def image_inventory(doc):
    # Unique reachable image objects, including SMask, preserve multiplicity.
    return Counter(
        json.dumps(canonical(obj), sort_keys=True)
        for obj in doc.objects
        if isinstance(obj, p.Stream) and obj.get("/Subtype") == p.Name.Image
    )


def validate_case(case, project_file, root, output, report, expected):
    checks = []

    def check(id, ok, measured=None):
        checks.append(dict(id=id, passed=bool(ok), measured=measured))

    check(
        "C10.errors",
        sorted(e["code"] for e in report["errors"]) == sorted(expected["error_codes"]),
        report["errors"],
    )
    check(
        "C10.warnings",
        sorted(e["code"] for e in report["warnings"])
        == sorted(expected["warning_codes"]),
        report["warnings"],
    )
    check(
        "C10.info",
        sorted(e["code"] for e in report["info"]) == sorted(expected["info_codes"]),
        report["info"],
    )
    if expected["expect"] == "error":
        check("no_pdf", not output.exists())
        return checks
    check("generated", report["status"] == "PASS", report["errors"])
    if not output.exists():
        return checks
    project = json.loads(project_file.read_text())
    t = report["template"]
    base = root / t["name"] / "base.pdf"
    actuals = {entry["cell"]: entry for entry in report["placements"]}
    expected_placed = [
        item
        for item in sorted(project["placements"], key=lambda x: x["order"])
        if (project_file.parent / item["file"]).is_file()
    ]
    with ExitStack() as stack:
        pdf = stack.enter_context(p.open(output))
        pg = pdf.pages[0]
        original = stack.enter_context(p.open(base))
        bp = original.pages[0]
        original_contents = streams(bp)
        contents = streams(pg)
        check("V1", bool(invoke("qpdf", "--check", output)))
        check("V2", len(pdf.pages) == 1 and list(pg.MediaBox) == list(bp.MediaBox))
        check(
            "V7",
            [s.read_raw_bytes() for s in contents[: len(original_contents)]]
            == [s.read_raw_bytes() for s in original_contents],
        )
        for kind, entries in bp.Resources.items():
            if kind in ("/Font", "/XObject"):
                check(
                    "V5/V12.base" + kind,
                    all(
                        canonical(pg.Resources[kind][key]) == canonical(value)
                        for key, value in entries.items()
                    ),
                )
            else:
                check(
                    "V12.base" + kind,
                    canonical(pg.Resources[kind]) == canonical(entries),
                )
        for label, obj, old in [
            ("catalog", pdf.Root, original.Root),
            ("page-1", pg.obj, bp.obj),
        ]:
            check("V17." + label, "/Illustrator" not in obj.get("/PieceInfo", {}))
            old_info = old.get("/PieceInfo", p.Dictionary())
            new_info = obj.get("/PieceInfo", p.Dictionary())
            check(
                "V17.other." + label,
                all(
                    canonical(new_info[key]) == canonical(value)
                    for key, value in old_info.items()
                    if key != "/Illustrator"
                ),
            )
        operations = list(p.parse_content_stream(contents[len(original_contents)]))
        draws = []
        current = None
        for operands, op in operations:
            if str(op) == "cm":
                current = list(map(float, operands))
            if str(op) == "Do":
                draws.append((str(operands[0]), current))
        check(
            "C3.order",
            [key for key, cm in draws]
            == [actuals[item["cell"]]["xobject"] for item in expected_placed],
        )
        check("C2.draw_count", len(draws) == len(expected_placed))
        constants = {item["cell"]: item for item in expected["constants"]}
        source_docs = {}
        geometry_by_cell = {}
        original_ocgs = list(
            original.Root.get("/OCProperties", p.Dictionary()).get("/OCGs", [])
        )
        input_ocg_names = [str(o.Name) for o in original_ocgs]
        expected_images = image_inventory(original)
        for item in expected_placed:
            file = (project_file.parent / item["file"]).resolve()
            if file not in source_docs:
                src = stack.enter_context(p.open(file))
                source_docs[file] = src
                input_ocg_names += [
                    str(o.Name)
                    for o in src.Root.get("/OCProperties", p.Dictionary()).get(
                        "/OCGs", []
                    )
                ]
                expected_images += image_inventory(src)
        check("V4", image_inventory(pdf) == expected_images)
        props = pdf.Root.OCProperties
        check(
            "V11",
            Counter(str(o.Name) for o in props.OCGs) == Counter(input_ocg_names)
            and {o.objgen for o in props.OCGs} == {o.objgen for o in props.D.ON}
            and not list(props.D.OFF),
        )
        registered = {o.objgen for o in props.OCGs}
        for obj in pdf.objects:
            if isinstance(obj, p.Dictionary) and obj.get("/Type") == p.Name.OCG:
                check("V11.registered." + str(obj.objgen), obj.objgen in registered)
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            seen = set()
            for (key, cm), item in zip(draws, expected_placed):
                n = item["cell"]
                source = source_docs[(project_file.parent / item["file"]).resolve()]
                sp = source.pages[0]
                f = pg.Resources.XObject[key]
                actual = actuals[n]
                ecm, ebb, rect, mm = independent_geometry(
                    t, n, sp.obj.get("/TrimBox", sp.MediaBox), pg.MediaBox
                )
                geometry_by_cell[n] = (ecm, ebb, rect, mm)
                check(
                    f"C2.cm.{n}",
                    close(cm, ecm) and all(v in (-1, 0, 1) for v in cm[:4]),
                )
                check(f"C2.bbox.{n}", close(f.BBox, ebb))
                if n in constants:
                    const = constants[n]
                    check(
                        f"C2.literal.{n}",
                        close(cm, const["cm"])
                        and close(f.BBox, const["bbox"])
                        and Path(item["file"]).name == const["file"],
                    )
                check(
                    f"V6.{n}",
                    f.read_bytes() == b"".join(s.read_bytes() for s in streams(sp)),
                )
                check(
                    f"V5.resources.{n}",
                    canonical(f.Resources) == canonical(sp.Resources),
                )
                check(
                    f"V10.{n}",
                    canonical(f.get("/Group")) == canonical(sp.obj.get("/Group")),
                )
                # Cache identical isolated source/crop comparisons across repeated cells.
                signature = (
                    str(source.filename),
                    tuple(round(v, 6) for v in ebb),
                    t["cell"]["rotation_deg"],
                )
                if signature in seen:
                    continue
                seen.add(signature)
                reference = sp.as_form_xobject()
                specimen(reference, ecm, rect, temp / "reference.pdf")
                specimen(f, cm, rect, temp / "actual.pdf")
                ref = render(temp / "reference.pdf", temp / "ref", 300)
                act = render(temp / "actual.pdf", temp / "act", 300)
                difference = pixel_difference(ref, act)
                check(f"C4.same.{n}", difference == 0, difference)
                other_path = (
                    ROOT
                    / "samples/input"
                    / ("B-2.pdf" if Path(item["file"]).name != "B-2.pdf" else "B-1.pdf")
                )
                other = stack.enter_context(p.open(other_path))
                other_form = other.pages[0].as_form_xobject()
                specimen(other_form, ecm, rect, temp / "other.pdf")
                wrong = render(temp / "other.pdf", temp / "wrong", 300)
                difference = pixel_difference(ref, wrong)
                check(f"C4.wrong_source.{n}", difference > 0, difference)
            # Full-sheet reference checks both painter order and actual placement.
            reference_sheet(base, t, project, project_file.parent, temp / "sheet.pdf")
            reference = render(temp / "sheet.pdf", temp / "sheet", 150)
            with Image.open(output.with_suffix(".png")) as im:
                actual = im.convert("RGB")
            diff = ImageChops.difference(reference, actual)
            mask = ImageDraw.Draw(diff)
            for text in report["texts"]:
                mask.rectangle(rectangle_mask(text["bounds_mm"], 150, 1), fill=0)
            check("C3/C4.sheet", diff.getbbox() is None)
            baseline = render(base, temp / "base", 150)
            diff = ImageChops.difference(baseline, actual)
            mask = ImageDraw.Draw(diff)
            for n, (cm, bbox, rect, mm) in geometry_by_cell.items():
                mask.rectangle(rectangle_mask(mm, 150, 1), fill=0)
            for text in report["texts"]:
                mask.rectangle(rectangle_mask(text["bounds_mm"], 150, 1), fill=0)
            check("C5.base_pixels", diff.getbbox() is None)
            if case == "T31-04":
                reference_sheet(
                    base,
                    t,
                    project,
                    project_file.parent,
                    temp / "top.pdf",
                    selected={1},
                )
                top = render(temp / "top.pdf", temp / "top", 150)
                # Interior of overlap avoids antialiasing the boundary itself.
                r = (
                    math.ceil(110 * 150 / 25.4) + 1,
                    math.ceil(60 * 150 / 25.4) + 1,
                    math.floor(115 * 150 / 25.4) - 1,
                    math.floor(110 * 150 / 25.4) - 1,
                )
                check(
                    "C3.overlap_top",
                    ImageChops.difference(top.crop(r), actual.crop(r)).getbbox()
                    is None,
                )
            if case == "T31-05":
                cm, bbox, rect, mm = geometry_by_cell[1]
                form = pg.Resources.XObject[actuals[1]["xobject"]]
                a, b, c, d, e, f = cm
                x0, y0, x1, y1 = map(float, form.BBox)
                corners = [
                    (a * x + c * y + e, b * x + d * y + f)
                    for x in (x0, x1)
                    for y in (y0, y1)
                ]
                media = list(map(float, pg.MediaBox))
                check(
                    "C6.within_sheet",
                    all(
                        media[0] - 0.00001 <= x <= media[2] + 0.00001
                        and media[1] - 0.00001 <= y <= media[3] + 0.00001
                        for x, y in corners
                    ),
                )
        # Text operator inspection does not rely on extracted text ordering.
        active = [f for f in t["text_fields"] if project["texts"].get(f["id"], "")]
        new_text_streams = contents[len(original_contents) + 1 :]
        check("C7.text_stream_count", len(new_text_streams) == (1 if active else 0))
        operations = [
            (operands, str(op))
            for stream in new_text_streams
            for operands, op in p.parse_content_stream(stream)
        ]
        check("C7.object_count", sum(op == "BT" for _, op in operations) == len(active))
        check(
            "C7.K100",
            all(
                list(map(float, args)) == [0, 0, 0, 1]
                for args, op in operations
                if op == "k"
            )
            and sum(op == "k" for _, op in operations) == len(active)
            and not any(
                op in ("g", "G", "rg", "RG", "K", "cs", "CS", "sc", "SC", "scn", "SCN")
                for _, op in operations
            ),
        )
        matrices = [list(map(float, args)) for args, op in operations if op == "Tm"]
        for field, matrix in zip(active, matrices):
            expected_xy = [
                float(pg.MediaBox[0]) + field["x_mm"] * PT,
                float(pg.MediaBox[3]) - field["y_mm"] * PT,
            ]
            check(
                "C7.baseline." + field["id"], close(matrix[4:], expected_xy, 0.1 * PT)
            )
        fonts = font_rows(output)
        before = font_rows(base)
        added = list((Counter(fonts) - Counter(before)).elements())
        text_fonts = {entry["font_resource"] for entry in report["texts"]}
        postscript_names = sorted(
            str(pg.Resources.Font[key].BaseFont).lstrip("/").split("+", 1)[-1]
            for key in text_fonts
        )
        check(
            "C7.font_postscript_name",
            postscript_names == sorted(expected["text_font_postscript_names"]),
            postscript_names,
        )
        check(
            "V3/C7.fonts",
            len(added) == len({f["font"] for f in active})
            and not (Counter(before) - Counter(fonts)),
        )
        check(
            "C7.embedded_subset_unicode",
            all(row[-3:] == ("yes", "yes", "yes") for row in added),
            added,
        )
        extracted = invoke("pdftotext", output, "-")
        check(
            "C7.unicode_text",
            all(project["texts"][field["id"]] in extracted for field in active),
            extracted,
        )
        if not active:
            check("C7.no_extra_font", fonts == before)
    expected_empty = sorted(
        set(range(1, math.prod(t["grid"]["count"]) + 1))
        - {item["cell"] for item in expected_placed}
    )
    check("empty_cells", report["empty_cells"] == expected_empty, report["empty_cells"])
    return checks


def run_suite(out, font_dirs=()):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(f"Use a new output folder: {out}")
    out.mkdir(parents=True)
    root = out / "templates"
    hashes = {
        str(path): digest(path) for path in (ROOT / "samples/input").glob("*.pdf")
    }
    fixture_hashes = {str(path): digest(path) for path in FIXTURES.rglob("*.json")}
    copies = []
    for path in sorted((FIXTURES / "template-defs").glob("*.json")):
        definition = json.loads(path.read_text())
        source = (path.parent / definition["source_base"]).resolve()
        created = create_template(definition["template"], source, root)
        copies.append(
            dict(
                template=created.name,
                passed=digest(source) == digest(created / "base.pdf"),
            )
        )
    cases = []
    for project in sorted((FIXTURES / "projects").glob("*.qiproj.json")):
        name = project.name.removesuffix(".qiproj.json")
        directory = out / name / ("sub" if name == "T31-08" else "")
        output = directory / "result.pdf"
        expected = json.loads((FIXTURES / "expected" / f"{name}.json").read_text())
        try:
            report = generate(project, root, output, font_dirs)
            checks = validate_case(name, project, root, output, report, expected)
            if name == "T31-09" and output.exists():
                with (
                    p.open(out / "T31-01/result.pdf") as first,
                    p.open(output) as extra,
                ):
                    checks.append(
                        dict(
                            id="unknown_text_has_no_effect",
                            passed=[s.read_bytes() for s in streams(first.pages[0])]
                            == [s.read_bytes() for s in streams(extra.pages[0])]
                            and canonical(first.pages[0].Resources)
                            == canonical(extra.pages[0].Resources),
                        )
                    )
            if name == "T31-08" and output.exists():
                saved = output.with_suffix(".qiproj.json")
                data = json.loads(saved.read_text())
                old = json.loads(project.read_text())
                reloc_ok = all(
                    not Path(item["file"]).is_absolute()
                    and (saved.parent / item["file"]).resolve()
                    == (project.parent / prior["file"]).resolve()
                    for item, prior in zip(data["placements"], old["placements"])
                )
                checks.append(dict(id="relocated_paths", passed=reloc_ok))
                reopened = out / name / "reopened/result.pdf"
                rr = generate(saved, root, reopened, font_dirs)
                with (
                    p.open(out / "T31-01/result.pdf") as first,
                    p.open(output) as moved,
                    p.open(reopened) as again,
                ):
                    contents = lambda doc: [
                        s.read_bytes() for s in streams(doc.pages[0])
                    ]
                    checks.append(
                        dict(
                            id="reopen_identical",
                            passed=rr["status"] == "PASS"
                            and contents(first) == contents(moved) == contents(again)
                            and canonical(first.pages[0].Resources)
                            == canonical(again.pages[0].Resources),
                        )
                    )
            report["test_checks"] = checks
            (directory / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n"
            )
            failed = [c for c in checks if not c["passed"]]
            cases.append(
                dict(
                    case=name,
                    status="PASS" if not failed else "FAIL",
                    failures=failed,
                    check_count=len(checks),
                )
            )
        except Exception as exc:
            cases.append(dict(case=name, status="FAIL", failures=[str(exc)]))
    unchanged = all(digest(path) == sha for path, sha in hashes.items())
    expected_hashes = json.loads((FIXTURES / "expected/input-sha256.json").read_text())
    hashes_match_spec = all(
        digest(ROOT / "samples/input" / name) == sha
        for name, sha in expected_hashes.items()
    )
    fixtures_unchanged = all(
        digest(path) == sha for path, sha in fixture_hashes.items()
    )
    summary = dict(
        status="PASS"
        if all(c["status"] == "PASS" for c in cases)
        and unchanged
        and hashes_match_spec
        and fixtures_unchanged
        and all(c["passed"] for c in copies)
        else "FAIL",
        case_count=len(cases),
        passed=sum(c["status"] == "PASS" for c in cases),
        cases=cases,
        C8_template_copies=copies,
        C9_input_hashes_unchanged=unchanged,
        C9_hashes_match_spec=hashes_match_spec,
        fixture_hashes_unchanged=fixtures_unchanged,
        manual_review=[
            "V15: direction",
            "C11/V18: open all successful outputs in Illustrator",
        ],
    )
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "out/test03-1")
    parser.add_argument("--font-dir", action="append", default=[])
    args = parser.parse_args()
    result = run_suite(args.out, args.font_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
