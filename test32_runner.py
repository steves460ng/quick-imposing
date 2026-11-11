"""TASK-03-2 acceptance runner; only test code reads expected fixture values."""

import argparse
import json
from pathlib import Path
import tempfile

import pikepdf as p

from imposing.autofill import autofill
from imposing.engine import create_template, generate
from imposing.model import relative_path
from imposing.pdf import canonical, digest, invoke, render, streams
from test03_runner import close, independent_geometry, pixel_difference, specimen
from test03_runner import run_suite as run_31

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "samples/test03-2"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def placements(rows):
    return [
        dict(cell=row["cell"], file=Path(row["file"]).name, order=row["order"])
        for row in rows
    ]


def source_file(name):
    return (
        (FIXTURES / "data" / name)
        if name.startswith("c-")
        else (ROOT / "samples/input" / name)
    )


def inspect_pdf(output, expected, definition, base, check):
    with (
        p.open(output) as pdf,
        p.open(base) as original,
        tempfile.TemporaryDirectory() as temp,
    ):
        temp = Path(temp)
        page = pdf.pages[0]
        check("qpdf", bool(invoke("qpdf", "--check", output)))
        original_contents = streams(original.pages[0])
        contents = streams(page)
        check(
            "base_contents",
            [s.read_raw_bytes() for s in contents[: len(original_contents)]]
            == [s.read_raw_bytes() for s in original_contents],
        )
        draws = []
        matrix = None
        for operands, op in p.parse_content_stream(contents[len(original_contents)]):
            if str(op) == "cm":
                matrix = list(map(float, operands))
            if str(op) == "Do":
                draws.append((str(operands[0]), matrix))
        ordered = sorted(expected["placements"], key=lambda item: item["order"])
        values = {entry["cell"]: entry for entry in expected["pdf"]}
        check("D6.draw_count", len(draws) == len(ordered), len(draws))
        check("no_extra_content", len(contents) == len(original_contents) + 1)
        for index, ((key, matrix), item) in enumerate(zip(draws, ordered)):
            n = item["cell"]
            value = values[n]
            actual = page.Resources.XObject[key]
            check(
                f"D6/D7.matrix.{index}",
                close(matrix, value["cm"], expected["tolerance_pt"]),
                matrix,
            )
            check(
                f"D6.bbox.{n}",
                close(actual.BBox, value["bbox"], expected["tolerance_pt"]),
            )
            source_path = source_file(item["file"])
            with p.open(source_path) as source:
                sp = source.pages[0]
                check(
                    f"D8.bytes.{n}",
                    actual.read_bytes()
                    == b"".join(s.read_bytes() for s in streams(sp)),
                )
                check(
                    f"D8.resources.{n}",
                    canonical(actual.Resources) == canonical(sp.Resources),
                )
                cm, _, rect, _ = independent_geometry(
                    definition, n, sp.obj.get("/TrimBox", sp.MediaBox), page.MediaBox
                )
                specimen(sp.as_form_xobject(), cm, rect, temp / "reference.pdf")
                specimen(actual, matrix, rect, temp / "actual.pdf")
                reference = render(temp / "reference.pdf", temp / "ref", 300)
                image = render(temp / "actual.pdf", temp / "act", 300)
                different = pixel_difference(reference, image)
                check(f"D8.pixels.{n}", different == 0, different)
                alternative = ROOT / "samples/input/B-1.pdf"
                if digest(alternative) == digest(source_path):
                    alternative = ROOT / "samples/input/B-2.pdf"
                with p.open(alternative) as other:
                    specimen(
                        other.pages[0].as_form_xobject(), cm, rect, temp / "wrong.pdf"
                    )
                wrong = render(temp / "wrong.pdf", temp / "wrong", 300)
                different = pixel_difference(reference, wrong)
                check(f"D8.wrong_source.{n}", different > 0, different)
        # With no extra calls, checking every literal matrix/order above also
        # proves the empty cells (notably reverse case cell 6) receive no draw.
        check(
            "R11",
            "/Illustrator" not in pdf.Root.get("/PieceInfo", {})
            and all(
                "/Illustrator" not in pg.obj.get("/PieceInfo", {}) for pg in pdf.pages
            ),
        )


def run_case(case, expected, out, templates):
    checks = []

    def check(id, ok, measured=None):
        checks.append(dict(id=id, passed=bool(ok), measured=measured))

    current = FIXTURES / case["project"] if "project" in case else None
    output = None
    for index, (step, want) in enumerate(zip(case["steps"], expected["steps"]), 1):
        source = load(current) if current else None
        before = digest(current) if current else None
        directory = out / f"step-{index}"
        directory.mkdir(parents=True)
        output = directory / "filled.qiproj.json"
        report_path = directory / "autofill-report.json"
        report = autofill(
            templates_root=templates,
            start_cell=step["start_cell"],
            files=[FIXTURES / file for file in step["files"]],
            output=output,
            project=current,
            template=case.get("template") if current is None else None,
            report_path=report_path,
        )
        check(f"report_saved.{index}", load(report_path) == report)
        check(
            f"D2.sorted.{index}",
            [Path(f).name for f in report["sorted_files"]] == want["sorted_files"],
            report["sorted_files"],
        )
        check(f"D1.added.{index}", placements(report["added"]) == want["added"])
        check(
            f"D3.unplaced.{index}",
            [Path(f).name for f in report["unplaced_files"]] == want["unplaced_files"],
        )
        warnings = [
            {**w, "unplaced_files": [Path(f).name for f in w["unplaced_files"]]}
            for w in report["warnings"]
        ]
        check(f"D3.warning.{index}", warnings == want["warnings"], warnings)
        check(
            f"D4.error.{index}",
            [e["code"] for e in report["errors"]] == expected["error_codes"],
            report["errors"],
        )
        check(f"error_reason.{index}", all(e.get("reason") for e in report["errors"]))
        if current:
            check(f"D10.project_unchanged.{index}", digest(current) == before)
        if expected["expect"] == "error":
            check("D4.no_project", not output.exists())
            check("D4.status", report["status"] == "FAIL")
            return checks
        check(f"status.{index}", report["status"] == "PASS")
        if not output.exists():
            check("output_missing", False)
            return checks
        result = load(output)
        if source:
            check(
                f"D1.preserve_metadata.{index}",
                {k: v for k, v in source.items() if k != "placements"}
                == {k: v for k, v in result.items() if k != "placements"},
            )
            old = result["placements"][: len(source["placements"])]
            check(
                f"D1.preserve_old.{index}",
                len(old) == len(source["placements"])
                and all(
                    left["cell"] == right["cell"]
                    and left["order"] == right["order"]
                    and (current.parent / left["file"]).resolve()
                    == (output.parent / right["file"]).resolve()
                    for left, right in zip(source["placements"], old)
                ),
            )
        for placement in result["placements"]:
            target = (output.parent / placement["file"]).resolve()
            check(
                f"D5.relative.{index}.{placement['cell']}",
                relative_path(placement["file"])
                and target == source_file(Path(placement["file"]).name).resolve(),
            )
        current = output
    result = load(output)
    check(
        "D1.final",
        placements(result["placements"]) == expected["placements"],
        placements(result["placements"]),
    )
    pdf = out / "pdf/result.pdf"
    generated = generate(output, templates, pdf)
    check("D5.build", generated["status"] == "PASS", generated["errors"])
    if pdf.exists():
        definition = load(templates / result["template"] / "template.json")
        inspect_pdf(
            pdf,
            expected,
            definition,
            templates / result["template"] / "base.pdf",
            check,
        )
    return checks


def run_cases(out):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(f"Use a new output directory: {out}")
    out.mkdir(parents=True)
    protected = list((ROOT / "samples/input").glob("*.pdf")) + list(
        (FIXTURES / "data").glob("*.pdf")
    )
    protected += list(FIXTURES.rglob("*.json"))
    hashes = {str(path): digest(path) for path in protected}
    templates = out / "templates"
    for path in sorted((FIXTURES / "template-defs").glob("*.json")):
        wrapper = load(path)
        create_template(
            wrapper["template"], path.parent / wrapper["source_base"], templates
        )
    cases = []
    for case in load(FIXTURES / "cases.json"):
        name = case["case"]
        directory = out / name
        directory.mkdir()
        try:
            expected = load(FIXTURES / "expected" / f"{name}.json")
            checks = run_case(case, expected, directory, templates)
            failures = [check for check in checks if not check["passed"]]
            result = dict(
                case=name,
                status="FAIL" if failures else "PASS",
                checks=checks,
                failures=failures,
            )
        except Exception as exc:
            result = dict(case=name, status="FAIL", checks=[], failures=[str(exc)])
        write(directory / "checks.json", result)
        cases.append({k: v for k, v in result.items() if k != "checks"})
    unchanged = all(digest(path) == sha for path, sha in hashes.items())
    data_hashes = load(FIXTURES / "expected/data-sha256.json")
    spec_hashes = all(
        digest(FIXTURES / "data" / name) == sha for name, sha in data_hashes.items()
    )
    summary = dict(
        status="PASS"
        if len(cases) == 11
        and all(c["status"] == "PASS" for c in cases)
        and unchanged
        and spec_hashes
        else "FAIL",
        scope="T32-01 through T32-11",
        case_count=len(cases),
        passed=sum(c["status"] == "PASS" for c in cases),
        cases=cases,
        D10_inputs_unchanged=unchanged,
        D10_data_hashes_match_task=spec_hashes,
    )
    write(out / "summary.json", summary)
    return summary


def run_suite(out):
    out = Path(out).resolve()
    summary = run_cases(out)
    regression = run_31(out / "regression03-1")
    summary["D9_regression03_1"] = dict(
        status=regression["status"],
        passed=regression["passed"],
        case_count=regression["case_count"],
    )
    summary["pytest"] = "Run separately: python -m pytest -q"
    summary["scope"] = (
        "T32 acceptance cases and T31 regression; pytest is a separate command"
    )
    if regression["status"] != "PASS":
        summary["status"] = "FAIL"
    write(out / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "out/test03-2")
    args = parser.parse_args()
    result = run_suite(args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
