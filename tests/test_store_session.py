import json
from pathlib import Path

import pytest

from imposing import store
from imposing.autofill import plan_fill
from imposing.pdf import digest
from imposing.session import Session, SessionError, free_output_path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "samples/input/base-front-blank.pdf"
DATA = ROOT / "samples/test03-2/data"


def definition(name="T31-front-3x8"):
    data = json.loads((ROOT / "samples/manual/T31-front-3x8.json").read_text("utf-8"))
    data["name"] = name
    return data


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "templates"
    store.save_template(definition(), root, BASE)
    return root


def small(root, direction="forward"):
    data = definition("small")
    data["grid"]["count"] = [3, 3]
    data["fill_direction"] = direction
    data["text_fields"] = []
    store.save_template(data, root, BASE)
    return Session.new(root, "small")


def cards(*numbers):
    return [DATA / f"c-{n}.pdf" for n in numbers]


def test_template_create_update_list_delete(root, tmp_path):
    folder = root / "T31-front-3x8"
    assert digest(folder / "base.pdf") == digest(BASE)
    changed = definition()
    changed["grid"]["count"] = [2, 2]
    store.save_template(changed, root)
    assert store.load_template(root, "T31-front-3x8")["grid"]["count"] == [2, 2]
    assert digest(folder / "base.pdf") == digest(BASE)
    assert [p.name for p in folder.iterdir() if p.name not in ("base.pdf", "template.json")] == []
    back = ROOT / "samples/input/base-back-blank.pdf"
    store.save_template(changed, root, back)
    assert digest(folder / "base.pdf") == digest(back)
    store.save_template(definition("한글 10"), root, BASE)
    store.save_template(definition("한글 2"), root, BASE)
    assert store.list_templates(root) == ["T31-front-3x8", "한글 2", "한글 10"]
    store.delete_template(root, "한글 2")
    assert "한글 2" not in store.list_templates(root)
    with pytest.raises(store.TemplateError):
        store.delete_template(root, "없는 템플릿")


def test_template_errors(root, tmp_path):
    with pytest.raises(store.TemplateError):
        store.save_template(definition("새 템플릿"), root)  # no base
    bad = definition("bad")
    bad["grid"]["pitch_mm"] = [-1, 51]
    with pytest.raises(store.TemplateError):
        store.save_template(bad, root, BASE)
    assert not (root / "bad").exists()
    with pytest.raises(store.TemplateError):
        store.load_template(root, "없음")
    (root / "broken").mkdir()
    (root / "broken/template.json").write_text("{", encoding="utf-8")
    with pytest.raises(store.TemplateError):
        store.load_template(root, "broken")
    with pytest.raises(store.TemplateError):
        store.page_size_mm(tmp_path / "missing.pdf")
    width, height = store.page_size_mm(BASE)
    assert round(width, 1) == 305.0 and round(height, 1) == 506.0


def test_usable_fonts_resolve():
    names = store.usable_fonts()
    assert "Noto Sans CJK KR" in names
    assert names == sorted(names, key=str.casefold)


# Expected cells are TASK-03-2 §3 / TEMPLATE-REQUIREMENTS §6.4 tables.
@pytest.mark.parametrize(
    "direction,start,occupied,wanted,expected",
    [
        ("forward", 1, set(), 9, ([1, 2, 3, 4, 5, 6, 7, 8, 9], None, None)),
        ("forward", 5, set(), 5, ([5, 6, 7, 8, 9], None, None)),
        ("reverse", 3, set(), 9, ([3, 2, 1, 6, 5, 4, 9, 8, 7], None, None)),
        ("reverse", 5, set(), 5, ([5, 4, 9, 8, 7], None, None)),
        ("reverse", 8, set(), 3, ([8, 7], "end_of_cells", None)),
        ("forward", 1, {3}, 5, ([1, 2], "occupied", 3)),
        ("forward", 3, {3}, 2, ([], "occupied", 3)),
        ("forward", 9, set(), 1, ([9], None, None)),
    ],
)
def test_plan_fill(direction, start, occupied, wanted, expected):
    assert plan_fill([3, 3], direction, occupied, start, wanted) == expected


def test_session_fill_assign_replace(root):
    session = small(root, "reverse")
    result = session.fill(5, cards(10, 3, 11, 1, 2))
    assert [(cell, path.name) for cell, path in result["added"]] == [
        (5, "c-1.pdf"), (4, "c-2.pdf"), (9, "c-3.pdf"), (8, "c-10.pdf"), (7, "c-11.pdf"),
    ]
    assert result["reason"] is None and result["unplaced"] == []
    assert [session.placements[c]["order"] for c in (5, 4, 9, 8, 7)] == [1, 2, 3, 4, 5]
    # Replacing keeps the drawing order; a new cell goes on top.
    session.assign(4, cards(11)[0])
    assert session.placements[4] == dict(path=cards(11)[0], order=2)
    session.assign(1, cards(1)[0])
    assert session.placements[1]["order"] == 6
    blocked = session.fill(3, cards(1, 2, 3))
    assert [cell for cell, _ in blocked["added"]] == [3, 2]
    assert blocked["reason"] == "occupied" and blocked["blocked_cell"] == 1
    assert [p.name for p in blocked["unplaced"]] == ["c-3.pdf"]
    session.remove(2)
    assert 2 not in session.placements
    with pytest.raises(SessionError):
        session.assign(10, cards(1)[0])
    with pytest.raises(SessionError):
        session.fill(0, cards(1))


def test_session_save_open_roundtrip(root, tmp_path):
    session = Session.new(root, "T31-front-3x8")
    session.set_text("product", "한글 제품")
    session.fill(1, cards(2, 1))
    target = tmp_path / "작업 폴더" / "결과.pdf"
    report = session.save(target)
    assert report["status"] == "PASS" and not session.dirty
    assert sorted(p.name for p in target.parent.iterdir()) == [
        "결과.pdf", "결과.png", "결과.qiproj.json", "결과.report.json",
    ]
    saved = json.loads(session.project_path.read_text("utf-8"))
    assert [(i["cell"], i["order"]) for i in saved["placements"]] == [(1, 1), (2, 2)]
    assert all(not Path(i["file"]).is_absolute() for i in saved["placements"])
    assert [p["cm"] for p in report["placements"]][0][:4] == [0, -1, 1, 0]
    before = {p: digest(p) for p in target.parent.iterdir()}
    with pytest.raises(SessionError) as error:
        session.save(target)
    assert error.value.code == "OUTPUT_EXISTS"
    assert before == {p: digest(p) for p in target.parent.iterdir()}
    assert free_output_path(target).name == "결과-2.pdf"

    reopened = Session.open(root, session.project_path)
    assert reopened.texts["product"] == "한글 제품"
    assert {c: i["path"] for c, i in reopened.placements.items()} == {
        1: cards(1)[0], 2: cards(2)[0],
    }
    # Saving elsewhere recomputes B paths from the new project location.
    other = tmp_path / "다른 곳" / "깊은 폴더" / "again.pdf"
    assert reopened.save(other)["status"] == "PASS"
    again = json.loads(other.with_suffix(".qiproj.json").read_text("utf-8"))
    for item in again["placements"]:
        assert (other.parent / item["file"]).resolve().is_file()


def test_session_open_errors_and_missing_file(root, tmp_path):
    session = Session.new(root, "T31-front-3x8")
    session.fill(23, cards(1, 2))
    copy = tmp_path / "data" / "c-1.pdf"
    copy.parent.mkdir()
    copy.write_bytes(cards(1)[0].read_bytes())
    session.assign(1, copy)
    report = session.save(tmp_path / "job" / "a.pdf")
    assert report["status"] == "PASS"
    copy.unlink()
    # A missing B is not an error: the cell stays assigned and is drawn blank.
    reopened = Session.open(root, session.project_path)
    assert 1 in reopened.placements
    report = reopened.save(tmp_path / "job" / "b.pdf")
    assert report["status"] == "PASS"
    assert [i["code"] for i in report["info"]] == ["B_FILE_MISSING"]
    shrunk = definition()
    shrunk["grid"]["count"] = [3, 7]
    store.save_template(shrunk, root)
    with pytest.raises(SessionError) as error:
        Session.open(root, session.project_path)
    assert error.value.code == "CELL_NOT_IN_TEMPLATE"
    store.delete_template(root, "T31-front-3x8")
    with pytest.raises(SessionError) as error:
        Session.open(root, session.project_path)
    assert error.value.code == "TEMPLATE_NOT_FOUND"
    broken = tmp_path / "x.qiproj.json"
    broken.write_text("{}", encoding="utf-8")
    with pytest.raises(SessionError):
        Session.open(root, broken)


def test_failed_save_leaves_nothing(root, tmp_path):
    data = definition("nofont")
    data["text_fields"][0]["font"] = "No Such Font 123"
    store.save_template(data, root, BASE)
    session = Session.new(root, "nofont")
    report = session.save(tmp_path / "out" / "x.pdf")
    assert report["status"] == "FAIL"
    assert report["errors"][0]["code"] == "FONT_NOT_FOUND"
    assert list((tmp_path / "out").iterdir()) == []
    assert session.dirty is False or session.project_path is None
