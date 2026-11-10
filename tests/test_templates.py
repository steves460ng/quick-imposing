import copy
import json

import pikepdf as p
import pytest

from quick_imposing import impose, run_template
from template_layout import (
    ROOT,
    MM,
    placement_matrix,
    preset_positions,
    validate_template,
)
from test02_runner import run_suite


def template():
    return json.loads((ROOT / "samples/templates/t2-02-irregular.json").read_text())


def codes(t, root=ROOT):
    return {e["code"] for e in validate_template(t, root)[0]}


def test_fixture_suite(tmp_path):
    summary = run_suite(tmp_path / "suite")
    assert len(summary["cases"]) == 7
    assert summary["status"] == "PASS", summary


@pytest.mark.parametrize(
    "rotation,expected",
    [
        (0, [1, 0, 0, 1]),
        (90, [0, 1, -1, 0]),
        (-90, [0, -1, 1, 0]),
        (180, [-1, 0, 0, -1]),
    ],
)
def test_rotation_geometry(rotation, expected):
    w, h = (85 * MM, 50 * MM) if rotation in (0, 180) else (50 * MM, 85 * MM)
    box = [10, 20, 10 + w, 20 + h]
    a, b, c, d, e, f = placement_matrix(box, rotation, 25, 40, 506 * MM, [85, 50])
    assert [a, b, c, d] == expected
    points = [
        (a * x + c * y + e, b * x + d * y + f)
        for x in (box[0], box[2])
        for y in (box[1], box[3])
    ]
    assert min(x for x, y in points) == pytest.approx(25 * MM)
    assert max(x for x, y in points) == pytest.approx(110 * MM)
    assert min(y for x, y in points) == pytest.approx((506 - 90) * MM)
    assert max(y for x, y in points) == pytest.approx((506 - 40) * MM)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "wrong"),
        ("units", "pt"),
        ("origin", "bottom-left"),
        ("name", "../escape"),
        ("slots", None),
        ("base", None),
    ],
)
def test_schema(field, value):
    t = template()
    t[field] = value
    assert "SCHEMA_INVALID" in codes(t)


def test_multiple_errors(tmp_path):
    t = template()
    t["slots"].append(copy.deepcopy(t["slots"][0]))
    t["data"] += [{"slot": 99, "file": "missing.pdf"}, copy.deepcopy(t["data"][0])]
    t["base"]["size_mm"] = [300, 500]
    errors = codes(t)
    assert {
        "DUPLICATE_SLOT_ID",
        "SLOT_OVERLAP",
        "UNKNOWN_SLOT",
        "FILE_NOT_FOUND",
        "DUPLICATE_SLOT_ASSIGNMENT",
        "BASE_SIZE_MISMATCH",
    } <= errors
    path = tmp_path / "template.json"
    path.write_text(json.dumps(t))
    report = run_template(path, tmp_path / "out")
    assert {e["code"] for e in report["errors"]} == errors
    assert not (tmp_path / "out/result.pdf").exists()


def test_card_failures_and_fallback(tmp_path):
    t = template()
    t["base"]["file"] = str(ROOT / t["base"]["file"])
    for name, size, pages in [
        ("small", (30, 30), 1),
        ("multiple", (200, 300), 2),
        ("no-trim", (200, 300), 1),
    ]:
        with p.new() as doc:
            for _ in range(pages):
                doc.add_blank_page(page_size=size)
            doc.save(tmp_path / f"{name}.pdf")
    (tmp_path / "bad.pdf").write_bytes(b"not PDF")
    t["data"] = [
        {"slot": i + 1, "file": f"{name}.pdf"}
        for i, name in enumerate(["small", "multiple", "bad", "no-trim"])
    ]
    errors, warnings = validate_template(t, tmp_path)
    assert {e["code"] for e in errors} == {"CARD_TOO_SMALL", "INVALID_CARD_PDF"}
    assert any(w["file"] == "no-trim.pdf" for w in warnings)


@pytest.mark.parametrize("rotation", [0, 90, -90, 180])
def test_rotated_output(tmp_path, rotation):
    cfg = json.loads((ROOT / "presets/default-3x8.json").read_text())
    cfg.update(rotation_deg=rotation, slots_mm=[[25, 40]], assign={"1": "B-1.pdf"})
    if rotation in (0, 180):
        cfg["card_size_mm"] = [50, 85]
    report = impose(
        ROOT / "samples/input/base.pdf", cfg, ROOT / "samples/input", tmp_path
    )
    assert report["final"] == "PASS"


@pytest.mark.parametrize(
    "updates,xy",
    [
        ({}, [24, 49.5]),
        ({"gap_mm": [0.5, 0.5]}, [24.5, 51.25]),
        ({"gap_mm": [0, 0]}, [25, 53]),
        ({"align": "safe-area-center"}, [24, 42]),
        ({"align": "margin", "margin_mm": [20, 40]}, [20, 40]),
        ({"grid": [3, 7]}, [24, 75]),
        ({"slots_mm": [[20, 40], [120, 40]]}, [20, 40]),
    ],
)
def test_presets(updates, xy):
    cfg = json.loads((ROOT / "presets/default-3x8.json").read_text()) | updates
    assert preset_positions(cfg, 305, 506)[1] == pytest.approx(xy)


def test_presets_invalid(tmp_path):
    cfg = json.loads((ROOT / "presets/default-3x8.json").read_text())
    cfg.update(gap_mm=[1, 1.5], assign={"1": "B-1.pdf"})
    with pytest.raises(ValueError, match="safe area"):
        impose(ROOT / "samples/input/base.pdf", cfg, ROOT / "samples/input", tmp_path)
    assert not (tmp_path / "result.pdf").exists()


def test_shuffled_data(tmp_path):
    t = template()
    t["data"].reverse()
    path = tmp_path / "t.json"
    path.write_text(json.dumps(t))
    r = run_template(path, tmp_path / "out")
    assert [(s["slot"], s["file"]) for s in r["slots"]] == sorted(
        (d["slot"], d["file"]) for d in t["data"]
    )
    assert r["empty_slots"] == [8]
