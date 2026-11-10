"""Run TEST-02 fixtures; expected files are read only by this test runner."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import tempfile

import pikepdf as p
from PIL import Image, ImageChops

from quick_imposing import ROOT, canonical, render, run, run_template, streams


def close(actual, expected, tolerance):
    return len(actual) == len(expected) and all(
        abs(float(a) - b) <= tolerance for a, b in zip(actual, expected)
    )


def compare_case(template_path, expected_path, out):
    t = json.loads(template_path.read_text())
    e = json.loads(expected_path.read_text())
    report = run_template(template_path, out)
    checks = []

    def check(id, ok, detail=None):
        checks.append(dict(id=id, passed=bool(ok), detail=detail))

    if e["expect"] == "error":
        check(
            "error_code",
            e["error_code"] in [x["code"] for x in report["errors"]],
            report["errors"],
        )
        check("no_pdf", not (out / "result.pdf").exists())
    else:
        check(
            "C1",
            report["final"] == "PASS"
            and all(c["passed"] is True for c in report["checks"] if c["id"] != "V15"),
        )
        check("empty_slots", report["empty_slots"] == e["empty_slots"])
        placements = {s["slot"]: s for s in report["slots"]}
        check("placement_count", len(placements) == len(e["placements"]))
        with p.open(out / "result.pdf") as pdf:
            page = pdf.pages[0]
            # Extract actual operations, not merely the generator's report.
            operations = list(p.parse_content_stream(streams(page)[-1]))
            draws = []
            matrix = None
            for operands, op in operations:
                if str(op) == "cm":
                    matrix = list(map(float, operands))
                if str(op) == "Do":
                    draws.append((matrix, page.Resources.XObject[str(operands[0])]))
            check("draw_count", len(draws) == len(e["placements"]))
            for i, expect in enumerate(
                sorted(e["placements"], key=lambda x: x["slot"])
            ):
                slot = expect["slot"]
                actual = placements[slot]
                matrix, f = draws[i]
                check(
                    f"V8-slot-{slot}",
                    close(matrix, expect["cm"], e["tolerance_pt"])
                    and all(v in (-1, 0, 1) for v in matrix[:4]),
                )
                check(
                    f"V9-slot-{slot}", close(f.BBox, expect["bbox"], e["tolerance_pt"])
                )
                check(
                    f"rect-slot-{slot}",
                    close(actual["placed_rect_mm"], expect["placed_rect_mm"], 0.0001),
                )
                with p.open(ROOT / expect["file"]) as src:
                    expected_content = b"".join(
                        s.read_bytes() for s in streams(src.pages[0])
                    )
                check(
                    f"C2-slot-{slot}",
                    f.read_bytes() == expected_content
                    and actual["file"] == expect["file"],
                )
                check(
                    f"C5-slot-{slot}",
                    not any(
                        str(op) in ("BT", "Tj", "TJ")
                        for _, op in p.parse_content_stream(f)
                    ),
                )
                # Transform actual BBox corners and check its clipping boundary.
                a, b, c, d, tx, ty = matrix
                x0, y0, x1, y1 = map(float, f.BBox)
                pts = [
                    (a * x + c * y + tx, b * x + d * y + ty)
                    for x in (x0, x1)
                    for y in (y0, y1)
                ]
                h = float(page.MediaBox[3])
                mm = 72 / 25.4
                rect = [
                    min(x for x, y in pts) / mm,
                    (h - max(y for x, y in pts)) / mm,
                    max(x for x, y in pts) / mm,
                    (h - min(y for x, y in pts)) / mm,
                ]
                check(f"C6-slot-{slot}", close(rect, expect["placed_rect_mm"], 0.0001))
            fonts = run("pdffonts", out / "result.pdf").splitlines()[2:]
            check("C4", len(fonts) == 2, fonts)
            with tempfile.TemporaryDirectory() as temp:
                temp = Path(temp)
                base = render(ROOT / t["base"]["file"], temp / "base", 150)
                with Image.open(out / "preview.png") as image:
                    actual = image.convert("RGB")
                for slot in t["slots"]:
                    if slot["id"] not in e["empty_slots"]:
                        continue
                    x, y = slot["x"], slot["y"]
                    w, h = t["card"]["size_mm"]
                    scale = 150 / 25.4
                    rect = (
                        math.floor(x * scale),
                        math.floor(y * scale),
                        math.ceil((x + w) * scale),
                        math.ceil((y + h) * scale),
                    )
                    check(
                        f"C3-slot-{slot['id']}",
                        ImageChops.difference(
                            base.crop(rect), actual.crop(rect)
                        ).getbbox()
                        is None,
                    )
                run_template(template_path, temp / "repeat")
                with p.open(temp / "repeat/result.pdf") as repeated:
                    check(
                        "C7",
                        canonical(page.Resources)
                        == canonical(repeated.pages[0].Resources)
                        and [s.read_raw_bytes() for s in streams(page)]
                        == [s.read_raw_bytes() for s in streams(repeated.pages[0])],
                    )
        report["test02_checks"] = checks
        (out / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
    return dict(
        template=t["name"],
        status="PASS" if all(c["passed"] for c in checks) else "FAIL",
        failures=[c for c in checks if not c["passed"]],
        manual_checks=[
            "V15: human direction review pending",
            "Illustrator open verification pending",
        ]
        if e["expect"] == "pass"
        else [],
    )


def run_suite(out):
    out = Path(out)
    if out.exists():
        raise ValueError(f"Use a new output directory: {out}")
    out.mkdir(parents=True)
    protected = list((ROOT / "samples").rglob("*"))
    hashes = {
        str(f): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in protected
        if f.is_file()
    }
    cases = []
    for template in sorted((ROOT / "samples/templates").glob("*.json")):
        expected = ROOT / "samples/expected" / f"{template.stem}.expected.json"
        try:
            cases.append(compare_case(template, expected, out / template.stem))
        except Exception as exc:
            cases.append(
                dict(template=template.stem, status="FAIL", failures=[str(exc)])
            )
    unchanged = all(
        hashlib.sha256(Path(f).read_bytes()).hexdigest() == h for f, h in hashes.items()
    )
    summary = dict(
        status="PASS"
        if len(cases) == 7 and unchanged and all(c["status"] == "PASS" for c in cases)
        else "FAIL",
        scope="Automated checks; manual V15 and Illustrator checks are not claimed",
        input_and_fixture_hashes_unchanged=unchanged,
        cases=cases,
    )
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(ROOT / "out/test02"))
    args = parser.parse_args()
    summary = run_suite(args.out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    raise SystemExit(0 if summary["status"] == "PASS" else 1)
