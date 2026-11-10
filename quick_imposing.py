"""Vector-preserving PDF imposition. See docs/SPEC.md."""

import argparse
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from template_layout import (
    placement_matrix,
    preset_positions,
    validate_template,
    ROOT,
    vector,
)
import pikepdf as p
from PIL import Image, ImageChops, ImageDraw

MM = 72 / 25.4
DEFAULT = dict(
    card_size_mm=[85, 50],
    rotation_deg=-90,
    crop_anchor="center",
    grid=[3, 8],
    gap_mm=[1, 1],
    align="sheet-center",
    safe_area_mm=[15, 33, 290, 458],
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def streams(page):
    c = page.obj.get("/Contents", p.Array())
    return list(c) if isinstance(c, p.Array) else [c]


def canonical(obj):
    if isinstance(obj, p.Stream):
        return (
            canonical(obj.stream_dict),
            hashlib.sha256(obj.read_raw_bytes()).hexdigest(),
        )
    if isinstance(obj, p.Dictionary):
        return {k: canonical(v) for k, v in obj.items() if k not in ("/Length",)}
    if isinstance(obj, p.Array):
        return [canonical(v) for v in obj]
    return str(obj)


def form(pdf, page):
    f = pdf.make_stream(b"".join(s.read_bytes() for s in streams(page)))
    f.Type = p.Name.XObject
    f.Subtype = p.Name.Form
    f.Resources = page.Resources
    if "/Group" in page.obj:
        f.Group = page.obj.Group
    return f


def save(pdf, path):
    pdf.save(
        path, compress_streams=False, object_stream_mode=p.ObjectStreamMode.preserve
    )


def remove_stale_illustrator_data(pdf):
    """Invalidate native round-trip artwork after modifying PDF page content.

    Illustrator can reopen its private artwork instead of the PDF Contents.
    Preserve other applications' PieceInfo and all rendering resources.
    """
    removed = []
    for label, obj in [
        ("catalog", pdf.Root),
        *((f"page-{i + 1}", page.obj) for i, page in enumerate(pdf.pages)),
    ]:
        info = obj.get("/PieceInfo")
        if isinstance(info, p.Dictionary) and "/Illustrator" in info:
            del info["/Illustrator"]
            removed.append(label)
            if not len(info):
                del obj["/PieceInfo"]
    return removed


def tool(name):
    found = shutil.which(name)
    if not found and name == "qpdf":
        candidate = Path("/workspace/.setup/qpdf/usr/bin/qpdf")
        if candidate.exists():
            found = str(candidate)
    if not found:
        raise ValueError(f"Missing tool: {name}")
    return found


def run(name, *args):
    r = subprocess.run([tool(name), *map(str, args)], capture_output=True, text=True)
    if r.returncode:
        raise ValueError(f"{name}: {r.stdout}{r.stderr}")
    return r.stdout


def render(path, target, dpi):
    run("pdftoppm", "-singlefile", "-r", dpi, "-png", path, target)
    with Image.open(str(target) + ".png") as im:
        return im.convert("RGB")


def standalone(f, bbox, target, size=(85, 50), rotation=-90):
    with p.new() as doc:
        page = doc.add_blank_page(page_size=(size[0] * MM, size[1] * MM))
        imported = doc.copy_foreign(f)
        page.Resources = p.Dictionary(XObject=p.Dictionary(F=imported))
        cm = placement_matrix(bbox, rotation, 0, 0, size[1] * MM, size)
        page.Contents = doc.make_stream(
            ("q " + " ".join(f"{v:.9f}" for v in cm) + " cm /F Do Q").encode()
        )
        save(doc, target)


def impose(base, config, cards, out):
    base = Path(base).resolve()
    cards = Path(cards).resolve()
    out = Path(out).resolve()
    cfg = DEFAULT | config
    if (
        not vector(cfg["card_size_mm"], 2, True)
        or type(cfg["rotation_deg"]) != int
        or cfg["rotation_deg"] not in (0, 90, -90, 180)
        or cfg["crop_anchor"] != "center"
    ):
        raise ValueError("Invalid card geometry")
    cw, ch = cfg["card_size_mm"]
    rotation = cfg["rotation_deg"]
    sw, sh = (cw, ch) if rotation in (0, 180) else (ch, cw)
    assign = cfg.get(
        "assign",
        {str(i + 1): f.name for i, f in enumerate(sorted(cards.glob("B-*.pdf")))},
    )
    paths = {name: (cards / name).resolve() for name in set(assign.values())}
    for target in (out / "result.pdf", out / "report.json", out / "preview.png"):
        if target in [base, *paths.values()]:
            raise ValueError("Output must not overwrite input")
        if target.exists():
            raise ValueError(f"Output exists: {target}; choose a new output directory")
    hashes = {str(f): digest(f) for f in [base, *paths.values()]}
    report = dict(
        timestamp=datetime.now(timezone.utc).isoformat(),
        inputs=hashes,
        layout=cfg,
        slots=[],
        checks=[],
    )

    def check(id, ok, measured=None):
        report["checks"].append(
            dict(
                id=id,
                passed=bool(ok),
                measured=measured,
                reason=None if ok else "Validation mismatch",
            )
        )

    with ExitStack() as stack:
        original = stack.enter_context(p.open(base))
        dest = stack.enter_context(p.open(base))
        if len(dest.pages) != 1:
            raise ValueError("Base must have exactly one page")
        page = dest.pages[0]
        mb = list(map(float, page.MediaBox))
        if (
            mb[:2] != [0, 0]
            or page.obj.get("/Rotate", 0) != 0
            or page.obj.get("/UserUnit", 1) != 1
        ):
            raise ValueError("Unsupported base coordinate system")
        width, height = mb[2] / MM, mb[3] / MM
        safe = cfg["safe_area_mm"]
        if not vector(safe, 4) or not (safe[0] < safe[2] and safe[1] < safe[3]):
            raise ValueError("Invalid safe area")
        positions = cfg.get("_positions")
        if positions is None:
            positions = preset_positions(cfg, width, height)
        for n, (x, y) in positions.items():
            if x < safe[0] or y < safe[1] or x + cw > safe[2] or y + ch > safe[3]:
                raise ValueError("Grid exceeds safe area")
            for other, (ox, oy) in positions.items():
                if (
                    other > n
                    and max(x, ox) < min(x + cw, ox + cw)
                    and max(y, oy) < min(y + ch, oy + ch)
                ):
                    raise ValueError("Slot overlap")
        report["empty_slots"] = sorted(set(positions) - {int(n) for n in assign})
        report["warnings"] = []
        if (
            "slots_mm" in config
            and "grid" in config
            and len(positions) != math.prod(config["grid"])
        ):
            report["warnings"].append({"code": "SLOTS_OVERRIDE_GRID"})
        sources = {}
        forms = {}
        boxes = {}
        ocgs = list(dest.Root.get("/OCProperties", p.Dictionary()).get("/OCGs", []))
        expected_names = [str(o.Name) for o in ocgs]
        if "/XObject" not in page.Resources:
            page.Resources.XObject = p.Dictionary()
        names = {}
        for index, (name, path) in enumerate(sorted(paths.items())):
            src = stack.enter_context(p.open(path))
            sources[name] = src
            if len(src.pages) != 1:
                raise ValueError(f"{name}: expected one page")
            sp = src.pages[0]
            if sp.obj.get("/Rotate", 0) != 0 or sp.obj.get("/UserUnit", 1) != 1:
                raise ValueError("Unsupported card coordinate system")
            x0, y0, x1, y1 = map(float, sp.obj.get("/TrimBox", sp.MediaBox))
            if x1 - x0 < sw * MM or y1 - y0 < sh * MM:
                raise ValueError(f"{name}: card too small")
            a = (x0 + x1 - sw * MM) / 2
            b = (y0 + y1 - sh * MM) / 2
            bbox = [a, b, a + sw * MM, b + sh * MM]
            boxes[name] = bbox
            f = form(src, sp)
            f.BBox = p.Array(bbox)
            forms[name] = f
            key = f"/Card{index}"
            while key in page.Resources.XObject:
                key += "x"
            names[name] = key
            page.Resources.XObject[key] = dest.copy_foreign(f)
            for ocg in src.Root.get("/OCProperties", p.Dictionary()).get("/OCGs", []):
                ocgs.append(dest.copy_foreign(ocg))
                expected_names.append(str(ocg.Name))
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
        for slot, name in sorted(assign.items(), key=lambda kv: int(kv[0])):
            n = int(slot)
            if str(n) != str(slot) or n not in positions:
                raise ValueError("Invalid slot")
            x, y = positions[n]
            a, b, _, _ = boxes[name]
            cm = placement_matrix(boxes[name], rotation, x, y, mb[3], (cw, ch))
            commands.append(
                "q " + " ".join(f"{v:.9f}" for v in cm) + f" cm {names[name]} Do Q\n"
            )
            report["slots"].append(
                dict(
                    slot=n,
                    file=name,
                    xy_mm=[x, y],
                    cm=cm,
                    BBox=boxes[name],
                    xobject=names[name],
                    placed_rect_mm=[x, y, x + cw, y + ch],
                )
            )
        page.Contents = p.Array(
            streams(page) + [dest.make_stream("".join(commands).encode())]
        )
        report["illustrator_private_data_removed"] = remove_stale_illustrator_data(dest)
        out.mkdir(parents=True, exist_ok=True)
        result = out / "result.pdf"
        save(dest, result)
        check("V1", True, run("qpdf", "--check", result))
        with p.open(result) as actual:
            ap = actual.pages[0]
            check(
                "V2",
                len(actual.pages) == 1
                and list(ap.MediaBox) == list(original.pages[0].MediaBox),
            )
            fonts = run("pdffonts", result)
            images = run("pdfimages", "-list", result)
            base_fonts = run("pdffonts", base)
            font_rows = lambda text: Counter(
                tuple(line.split()[:-2]) for line in text.splitlines()[2:]
            )
            check(
                "V3",
                font_rows(fonts) == font_rows(base_fonts)
                and all(line.split()[-5] == "yes" for line in fonts.splitlines()[2:]),
                fonts,
            )
            expected_images = []
            for source in [base, *[paths[name] for name in assign.values()]]:
                expected_images.extend(
                    " ".join(line.split()[2:10])
                    for line in run("pdfimages", "-list", source).splitlines()[2:]
                )
            actual_images = [
                " ".join(line.split()[2:10]) for line in images.splitlines()[2:]
            ]
            # Repeated placements may be listed repeatedly by Poppler; compare unique resource properties below as well.
            check("V4", Counter(actual_images) == Counter(expected_images), images)
            check(
                "V5",
                all(
                    canonical(ap.Resources.XObject[names[n]].Resources)
                    == canonical(s.pages[0].Resources)
                    for n, s in sources.items()
                ),
            )
            check(
                "V6",
                all(
                    ap.Resources.XObject[names[n]].read_bytes()
                    == b"".join(t.read_bytes() for t in streams(s.pages[0]))
                    for n, s in sources.items()
                ),
            )
            check(
                "V7",
                [s.read_raw_bytes() for s in streams(ap)[:-1]]
                == [s.read_raw_bytes() for s in streams(original.pages[0])],
            )
            check("V8", streams(ap)[-1].read_bytes() == "".join(commands).encode())
            check(
                "V9",
                all(
                    all(
                        abs(float(v) - w) < 1e-6
                        for v, w in zip(ap.Resources.XObject[names[n]].BBox, boxes[n])
                    )
                    for n in sources
                ),
            )
            check(
                "V10",
                all(
                    canonical(ap.Resources.XObject[names[n]].get("/Group"))
                    == canonical(s.pages[0].obj.get("/Group"))
                    for n, s in sources.items()
                ),
            )
            props = actual.Root.OCProperties
            check(
                "V11",
                Counter(str(o.Name) for o in props.OCGs) == Counter(expected_names)
                and set(o.objgen for o in props.D.ON)
                == set(o.objgen for o in props.OCGs)
                and not list(props.D.OFF),
            )
            check(
                "V12",
                all(
                    canonical(ap.Resources.XObject[k]) == canonical(v)
                    for k, v in original.pages[0]
                    .Resources.get("/XObject", p.Dictionary())
                    .items()
                )
                and all(
                    canonical(ap.Resources[k]) == canonical(v)
                    for k, v in original.pages[0].Resources.items()
                    if k != "/XObject"
                ),
            )
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                differences = []
                for n in sources:
                    standalone(
                        forms[n], boxes[n], tmp / "original.pdf", (cw, ch), rotation
                    )
                    standalone(
                        ap.Resources.XObject[names[n]],
                        boxes[n],
                        tmp / "actual.pdf",
                        (cw, ch),
                        rotation,
                    )
                    a = render(tmp / "original.pdf", tmp / "a", 300)
                    b = render(tmp / "actual.pdf", tmp / "b", 300)
                    differences.append(ImageChops.difference(a, b).getbbox() is None)
                check("V13", all(differences), differences)
                before = render(base, tmp / "base", 150)
                after = render(result, out / "preview", 150)
                diff = ImageChops.difference(before, after)
                draw = ImageDraw.Draw(diff)
                for s in report["slots"]:
                    x, y = s["xy_mm"]
                    scale = 150 / 25.4
                    draw.rectangle(
                        (
                            math.floor(x * scale) - 1,
                            math.floor(y * scale) - 1,
                            math.ceil((x + cw) * scale) + 1,
                            math.ceil((y + ch) * scale) + 1,
                        ),
                        fill=0,
                    )
                same = diff.getbbox() is None
                check("V14", same)
                check("V16", same)
        report["checks"].append(
            dict(
                id="V15",
                passed=None,
                reason="Human review required: Hello world must face right in preview.png",
            )
        )
        check("TC6", all(digest(f) == h for f, h in hashes.items()))
        report["final"] = (
            "PASS"
            if all(c["passed"] is not False for c in report["checks"])
            else "FAIL"
        )
        report["human_review_required"] = True
        (out / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
        return report


def run_template(path, out=None, root=ROOT):
    template = json.loads(Path(path).read_text())
    errors, warnings = validate_template(template, root)
    name = template.get("name") if isinstance(template, dict) else None
    if (
        not isinstance(name, str)
        or not name
        or name in (".", "..")
        or "/" in name
        or "\\" in name
    ):
        name = Path(path).stem
    out = Path(out) if out is not None else Path(root) / "out/test02" / name
    if any((out / f).exists() for f in ("report.json", "result.pdf", "preview.png")):
        raise ValueError(f"Output exists: {out}; choose a new output directory")
    if errors:
        out.mkdir(parents=True, exist_ok=True)
        report = dict(
            template=name,
            final="FAIL",
            errors=errors,
            warnings=warnings,
            checks=[],
            empty_slots=[],
        )
    else:
        card = template["card"]
        cfg = dict(
            card_size_mm=card["size_mm"],
            rotation_deg=card["rotation_deg"],
            crop_anchor=card["crop_anchor"],
            safe_area_mm=template["base"]["safe_area_mm"],
            _positions={s["id"]: (s["x"], s["y"]) for s in template["slots"]},
            assign={str(d["slot"]): d["file"] for d in template["data"]},
        )
        report = impose(Path(root) / template["base"]["file"], cfg, root, out)
        report.update(template=name, errors=[], warnings=warnings, layout=template)
    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    return report


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("template", nargs="?")
    cli.add_argument("--base")
    cli.add_argument("--layout")
    cli.add_argument("--preset", default="default-3x8")
    cli.add_argument("--files", nargs="+")
    cli.add_argument("--cards")
    cli.add_argument("--out")
    args = cli.parse_args()
    try:
        if args.template:
            report = run_template(args.template, args.out)
        else:
            if not args.base:
                cli.error("--base is required without a template")
            cfg_path = Path(args.layout or args.preset)
            if not cfg_path.is_file():
                cfg_path = ROOT / "presets" / f"{args.preset}.json"
            cfg = json.loads(cfg_path.read_text())
            cards = args.cards or "."
            if args.files:
                cfg["assign"] = {
                    str(i + 1): str(Path(f).resolve()) for i, f in enumerate(args.files)
                }
            report = impose(args.base, cfg, cards, args.out or "out")
        print(
            report["final"] + " (V15 human review pending)"
            if not report.get("errors")
            else json.dumps(report["errors"])
        )
        return 0 if report["final"] == "PASS" else 1
    except (ValueError, OSError, p.PdfError, KeyError, TypeError) as error:
        cli.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
