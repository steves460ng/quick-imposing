import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pikepdf as p
import pytest

from imposing.engine import create_template, generate, geometry
from imposing.fonts import resolve
from imposing.model import cells, project_errors, template_errors
from imposing.pdf import canonical, digest, remove_illustrator, streams
from test03_runner import ROOT, FIXTURES, run_suite


def definition(name="front-3x8"):
    return json.loads((FIXTURES / "template-defs" / f"T31-{name}.json").read_text())[
        "template"
    ]


def project():
    return json.loads((FIXTURES / "projects/T31-01.qiproj.json").read_text())


@pytest.fixture
def prepared(tmp_path):
    t = definition()
    root = tmp_path / "templates"
    create_template(t, ROOT / "samples/input/base-front-blank.pdf", root)
    pr = project()
    for item in pr["placements"]:
        item["file"] = Path(
            os.path.relpath(ROOT / "samples/input" / Path(item["file"]).name, tmp_path)
        ).as_posix()
    path = tmp_path / "input.qiproj.json"
    path.write_text(json.dumps(pr))
    return root, path, pr


def test_full_suite(tmp_path):
    result = run_suite(tmp_path / "test03-1")
    assert result["case_count"] == 10
    assert result["status"] == "PASS", result


@pytest.mark.parametrize(
    "rotation,expected",
    [
        (0, [1, 0, 0, 1]),
        (90, [0, 1, -1, 0]),
        (-90, [0, -1, 1, 0]),
        (180, [-1, 0, 0, -1]),
    ],
)
def test_center_unit_rotation(rotation, expected):
    source = [10, 20, 40, 70]
    media = [0, 0, 864, 1434]
    cm, bbox = geometry(source, rotation, [24, 49.5], [85, 50], media)
    a, b, c, d, e, f = cm
    assert cm[:4] == expected
    assert a * 25 + c * 45 + e == pytest.approx((24 + 85 / 2) * 72 / 25.4)
    assert b * 25 + d * 45 + f == pytest.approx(1434 - (49.5 + 50 / 2) * 72 / 25.4)
    assert bbox[0] < bbox[2] and bbox[1] < bbox[3]


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "quick-imposing/template@1"),
        ("base", "../base.pdf"),
        ("name", "../escape"),
        ("name", "a:b"),
        ("fill_direction", "unknown"),
        ("text_fields", None),
        ("cell", None),
        ("grid", None),
    ],
)
def test_template_schema(field, value):
    t = definition()
    t[field] = value
    assert template_errors(t)


def test_duplicate_text_id():
    t = definition()
    t["text_fields"].append(copy.deepcopy(t["text_fields"][0]))
    assert template_errors(t)


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(schema="bad"),
        lambda p: p.update(texts=[]),
        lambda p: p["placements"].append(copy.deepcopy(p["placements"][0])),
        lambda p: p["placements"][0].update(order=0),
        lambda p: p["placements"][0].update(file="/absolute.pdf"),
        lambda p: p["placements"][0].update(file="C:\\data\\file.pdf"),
        lambda p: p["placements"][0].update(file="C:relative.pdf"),
    ],
)
def test_project_schema(change):
    pr = project()
    change(pr)
    assert project_errors(pr)


def test_order_gap_allowed():
    pr = project()
    pr["placements"][0]["order"] = 100
    assert not project_errors(pr)


def test_copy_no_overwrite(tmp_path):
    base = ROOT / "samples/input/base-front-blank.pdf"
    target = create_template(definition(), base, tmp_path)
    assert digest(target / "base.pdf") == digest(base)
    with pytest.raises(FileExistsError):
        create_template(definition(), base, tmp_path)


def test_template_missing(prepared, tmp_path):
    root, path, pr = prepared
    pr["template"] = "missing"
    path.write_text(json.dumps(pr))
    r = generate(path, root, tmp_path / "out/result.pdf")
    assert [e["code"] for e in r["errors"]] == ["TEMPLATE_NOT_FOUND"]
    assert not (tmp_path / "out/result.pdf").exists()


def test_current_template_smaller(prepared, tmp_path):
    root, path, pr = prepared
    tf = root / pr["template"] / "template.json"
    t = json.loads(tf.read_text())
    t["grid"]["count"] = [1, 1]
    tf.write_text(json.dumps(t))
    r = generate(path, root, tmp_path / "out/result.pdf")
    assert {e["code"] for e in r["errors"]} == {"CELL_NOT_IN_TEMPLATE"}
    assert len(r["errors"]) == 23
    assert not (tmp_path / "out/result.pdf").exists()


def test_missing_font_is_error_even_empty(prepared, tmp_path):
    root, path, pr = prepared
    tf = root / pr["template"] / "template.json"
    t = json.loads(tf.read_text())
    t["text_fields"][0]["font"] = "No Such Font 987654"
    tf.write_text(json.dumps(t))
    pr["texts"] = {}
    path.write_text(json.dumps(pr))
    r = generate(path, root, tmp_path / "out/result.pdf")
    assert [e["code"] for e in r["errors"]] == ["FONT_NOT_FOUND"]
    assert not (tmp_path / "out/result.pdf").exists()


def test_small_card_and_missing_are_not_errors(prepared, tmp_path):
    root, path, pr = prepared
    with p.new() as doc:
        page = doc.add_blank_page(page_size=(20, 30))
        page.Contents = doc.make_stream(b"0 1 0 0 k 0 0 20 30 re f")
        doc.save(tmp_path / "tiny.pdf")
    pr["placements"] = [
        dict(cell=1, file="tiny.pdf", order=1),
        dict(cell=2, file="missing.pdf", order=2),
    ]
    pr["texts"] = {}
    path.write_text(json.dumps(pr))
    r = generate(path, root, tmp_path / "out/result.pdf")
    assert r["status"] == "PASS" and not r["warnings"]
    assert [e["code"] for e in r["info"]] == ["B_FILE_MISSING"]
    assert r["empty_cells"] == list(range(2, 25))


def test_fill_direction_ignored_and_input_array_not_order(prepared, tmp_path):
    root, path, pr = prepared
    tf = root / pr["template"] / "template.json"
    t = json.loads(tf.read_text())
    t["fill_direction"] = "reverse"
    tf.write_text(json.dumps(t))
    pr["placements"] = pr["placements"][:2][::-1]
    pr["texts"] = {}
    path.write_text(json.dumps(pr))
    r = generate(path, root, tmp_path / "out/result.pdf")
    assert r["status"] == "PASS"
    assert [e["cell"] for e in r["placements"]] == [1, 2]
    assert cells(t)[1] == (24, 49.5)


def test_r11_preserves_rendering_and_other_app(tmp_path):
    base = ROOT / "samples/input/base-front-blank.pdf"
    with p.open(base) as doc:
        pg = doc.pages[0]
        original = [s.read_raw_bytes() for s in streams(pg)]
        resources = canonical(pg.Resources)
        pg.obj.PieceInfo.Other = p.Dictionary(Private="keep")
        doc.Root.PieceInfo = p.Dictionary(Illustrator=p.Dictionary(Private="stale"))
        assert remove_illustrator(doc) == ["catalog", "page-1"]
        assert str(pg.obj.PieceInfo.Other.Private) == "keep"
        assert resources == canonical(pg.Resources)
        assert original == [s.read_raw_bytes() for s in streams(pg)]
        assert remove_illustrator(doc) == []


def test_cli_from_different_directory(prepared, tmp_path):
    root, path, pr = prepared
    pr["placements"] = pr["placements"][:1]
    pr["texts"] = {}
    path.write_text(json.dumps(pr))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "imposing",
            "build",
            str(path),
            "--templates-root",
            str(root),
            "--output",
            str(tmp_path / "output/result.pdf"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


def test_empty_and_unknown_texts(prepared, tmp_path):
    root, path, pr = prepared
    pr["texts"] = {"product": "", "extra": "ignored"}
    pr["placements"] = []
    path.write_text(json.dumps(pr))
    r = generate(path, root, tmp_path / "out/result.pdf")
    assert r["status"] == "PASS" and r["texts"] == []
    assert [e["code"] for e in r["info"]] == ["TEXT_FIELD_UNKNOWN"]
    with (
        p.open(tmp_path / "out/result.pdf") as doc,
        p.open(root / pr["template"] / "base.pdf") as base,
    ):
        assert canonical(doc.pages[0].Resources.Font) == canonical(
            base.pages[0].Resources.Font
        )


def test_no_overwrite(prepared, tmp_path):
    root, path, pr = prepared
    target = tmp_path / "result.pdf"
    target.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        generate(path, root, target)
    assert target.read_bytes() == b"keep"


def test_extra_font_directory(tmp_path):
    from fontTools.ttLib import TTFont
    from imposing.fonts import embed

    # Any installed TrueType font serves as the source (Linux, then Windows).
    for candidate in ("DejaVu Sans", "Arial"):
        try:
            path, index = resolve(candidate)
            break
        except ValueError:
            continue
    else:
        pytest.skip("no TrueType source font installed")
    f = TTFont(path, fontNumber=index)
    for name in f["name"].names:
        if name.nameID in (1, 4, 6, 16):
            name.string = "TestExtraFont".encode(name.getEncoding())
    f.save(tmp_path / "test-extra.ttf")
    f.close()
    found = resolve("TestExtraFont", [tmp_path])
    assert Path(found[0]).parent == tmp_path
    with p.new() as doc:
        font, mapping, metrics = embed(doc, found, "Hello")
        assert font.DescendantFonts[0].FontDescriptor.FontFile2.read_bytes()
        assert "H" in mapping and metrics["widths"]["H"] > 0


def test_same_pdf_path_alias_does_not_duplicate_resources(prepared, tmp_path):
    root, path, pr = prepared
    name = pr["placements"][0]["file"]
    alias = str(Path(name).parent) + "/./" + Path(name).name
    pr["placements"] = [
        dict(cell=1, file=name, order=1),
        dict(cell=2, file=alias, order=2),
    ]
    pr["texts"] = {}
    path.write_text(json.dumps(pr))
    result = tmp_path / "out/result.pdf"
    r = generate(path, root, result)
    assert r["status"] == "PASS"
    with p.open(result) as doc:
        first, second = [
            doc.pages[0].Resources.XObject[e["xobject"]] for e in r["placements"]
        ]
        assert first.Resources.objgen == second.Resources.objgen
        assert len(doc.Root.OCProperties.OCGs) == 5  # four base OCGs plus one B


@pytest.mark.parametrize("pitch", [[-1, 51], [86, -1]])
def test_negative_pitch_rejected(prepared, tmp_path, pitch):
    root, path, pr = prepared
    tf = root / pr["template"] / "template.json"
    t = json.loads(tf.read_text())
    t["grid"]["pitch_mm"] = pitch
    tf.write_text(json.dumps(t))
    r = generate(path, root, tmp_path / "out/result.pdf")
    assert r["status"] == "FAIL"
    assert r["errors"] == [
        dict(
            code="SCHEMA_INVALID",
            reason="grid.pitch_mm: must be two numbers, not negative",
            field="grid.pitch_mm",
        )
    ]
    assert not (tmp_path / "out/result.pdf").exists()


def test_zero_pitch_warns_and_draws(prepared, tmp_path):
    root, path, pr = prepared
    tf = root / pr["template"] / "template.json"
    t = json.loads(tf.read_text())
    t["grid"].update(count=[2, 1], pitch_mm=[0, 0])
    tf.write_text(json.dumps(t))
    pr["placements"] = pr["placements"][:2]
    pr["texts"] = {}
    path.write_text(json.dumps(pr))
    r = generate(path, root, tmp_path / "out/result.pdf")
    assert r["status"] == "PASS" and not r["errors"]
    assert r["warnings"] == [dict(code="CELL_OVERLAP", cells=[[1, 2]])]
    assert all(item["drawn"] for item in r["placements"])
    assert r["placements"][0]["cm"] == r["placements"][1]["cm"]


def test_fully_offpage_retains_assignment_and_reopens(prepared, tmp_path):
    root, path, pr = prepared
    tf = root / pr["template"] / "template.json"
    t = json.loads(tf.read_text())
    t["grid"].update(count=[1, 1], origin_mm=[400, 600])
    tf.write_text(json.dumps(t))
    pr["placements"] = pr["placements"][:1]
    pr["texts"] = {}
    path.write_text(json.dumps(pr))
    first = tmp_path / "offpage/result.pdf"
    r = generate(path, root, first)
    assert r["status"] == "PASS" and not r["warnings"]
    assert r["placements"][0]["drawn"] is False and r["placements"][0]["bbox"] is None
    assert r["empty_cells"] == []
    saved = first.with_suffix(".qiproj.json")
    kept = json.loads(saved.read_text())
    assert len(kept["placements"]) == 1 and kept["placements"][0]["cell"] == 1
    assert kept["placements"][0]["order"] == pr["placements"][0]["order"]
    assert (saved.parent / kept["placements"][0]["file"]).resolve() == (
        path.parent / pr["placements"][0]["file"]
    ).resolve()
    with p.open(first) as pdf:
        assert not any(
            str(op) == "Do"
            for args, op in p.parse_content_stream(streams(pdf.pages[0])[-1])
        )
    t["grid"]["origin_mm"] = [24, 49.5]
    tf.write_text(json.dumps(t))
    r = generate(saved, root, tmp_path / "reopened/result.pdf")
    assert r["status"] == "PASS" and not r["warnings"]
    assert (
        r["placements"][0]["drawn"] is True and r["placements"][0]["bbox"] is not None
    )


def test_template_saved_without_fixture_envelope(tmp_path):
    envelope = json.loads((FIXTURES / "template-defs/T31-front-3x8.json").read_text())
    target = create_template(
        envelope["template"], ROOT / "samples/input/base-front-blank.pdf", tmp_path
    )
    saved = json.loads((target / "template.json").read_text())
    assert saved == envelope["template"]
    assert "source_base" not in saved and "template" not in saved


def test_two_named_outputs_and_repeat_preserves_bytes(prepared, tmp_path):
    root, path, _ = prepared
    folder = tmp_path / "outputs"
    for name in ("a", "b"):
        output = folder / f"{name}.pdf"
        report = generate(path, root, output)
        assert report["status"] == "PASS"
        assert json.loads(output.with_suffix(".report.json").read_text()) == report
    expected = {
        f"{name}{suffix}"
        for name in ("a", "b")
        for suffix in (".pdf", ".qiproj.json", ".png", ".report.json")
    }
    assert {p.name for p in folder.iterdir()} == expected
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    with pytest.raises(FileExistsError):
        generate(path, root, folder / "a.pdf")
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before


@pytest.mark.parametrize("suffix", [".pdf", ".qiproj.json", ".png", ".report.json"])
def test_each_named_artifact_blocks_generation(prepared, tmp_path, suffix):
    root, path, _ = prepared
    folder = tmp_path / "outputs"
    folder.mkdir()
    existing = folder / f"front-01{suffix}"
    existing.write_bytes(b"existing artifact")
    with pytest.raises(FileExistsError):
        generate(path, root, folder / "front-01.pdf")
    assert list(folder.iterdir()) == [existing]
    assert existing.read_bytes() == b"existing artifact"


def test_error_reports_use_output_stem_and_refuse_overwrite(tmp_path):
    folder = tmp_path / "outputs"
    for name in ("front-01", "back.v2"):
        output = folder / f"{name}.pdf"
        report = generate(tmp_path / "missing.json", tmp_path / "templates", output)
        assert report["status"] == "FAIL"
        assert report["errors"][0]["code"] == "SCHEMA_INVALID"
        assert json.loads(output.with_suffix(".report.json").read_text()) == report
        assert not output.exists()
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    assert set(before) == {"front-01.report.json", "back.v2.report.json"}
    with pytest.raises(FileExistsError):
        generate(
            tmp_path / "missing.json", tmp_path / "templates", folder / "front-01.pdf"
        )
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before


def test_every_schema_error_has_reason_and_field():
    # REFACTORING R5: one entry form {code, reason, field?} for every error.
    broken_template = dict(
        schema="x",
        name="a/b",
        base="x.pdf",
        cell=dict(size_mm=[0, 1], rotation_deg=45),
        grid=dict(origin_mm=None, pitch_mm=[-1, 0], count=[0, 1]),
        fill_direction="up",
        text_fields=[1, dict(id="")],
    )
    broken_project = dict(
        schema="x", template="", texts=[], placements=[1, dict(cell=0, order=0)]
    )
    errors = (
        template_errors(broken_template)
        + project_errors(broken_project)
        + template_errors(None)
        + project_errors(None)
    )
    assert len(errors) > 15
    for entry in errors:
        assert entry["code"] == "SCHEMA_INVALID"
        assert entry["field"] and entry["reason"].startswith(entry["field"] + ": ")


def test_build_errors_all_have_reason(prepared, tmp_path):
    root, path, pr = prepared
    pr["placements"][0]["cell"] = 99
    pr["template"] = "missing-template"
    path.write_text(json.dumps(pr))
    r = generate(path, root, tmp_path / "out/a.pdf")
    assert [e["code"] for e in r["errors"]] == ["TEMPLATE_NOT_FOUND"]
    pr["template"] = definition()["name"]
    path.write_text(json.dumps(pr))
    r2 = generate(path, root, tmp_path / "out/b.pdf")
    assert [e["code"] for e in r2["errors"]] == ["CELL_NOT_IN_TEMPLATE"]
    for entry in r["errors"] + r2["errors"]:
        assert entry["reason"]
