"""Paths on another Windows drive are one error everywhere (REFACTORING R3).

Linux has no drives, so ``os.path.relpath`` is replaced by one that fails the
way Windows does when either path lies under a folder named ``otherdrive``.
"""

import json
import os
from pathlib import Path
import shutil

import pytest

from imposing import store
from imposing.autofill import autofill
from imposing.engine import generate
from imposing.model import PathError, relative_file
from imposing.session import Session, SessionError

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "samples/input/base-front-blank.pdf"
DATA = ROOT / "samples/test03-2/data"


@pytest.fixture
def drives(monkeypatch):
    original = os.path.relpath

    def relpath(path, start=os.curdir):
        if "otherdrive" in Path(path).parts or "otherdrive" in Path(start).parts:
            raise ValueError("path is on mount 'D:', start on mount 'C:'")
        return original(path, start)

    monkeypatch.setattr(os.path, "relpath", relpath)


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "templates"
    data = json.loads((ROOT / "samples/manual/T31-front-3x8.json").read_text("utf-8"))
    data["name"] = "small"
    data["grid"]["count"] = [3, 3]
    data["text_fields"] = []
    store.save_template(data, root, BASE)
    other = tmp_path / "otherdrive"
    other.mkdir()
    cards = [Path(shutil.copy(DATA / f"c-{n}.pdf", other)) for n in (1, 2)]
    return root, cards


def test_relative_file(tmp_path, drives):
    assert relative_file(tmp_path / "a" / "b.pdf", tmp_path) == "a/b.pdf"
    with pytest.raises(PathError) as error:
        relative_file(tmp_path / "otherdrive" / "b.pdf", tmp_path)
    assert error.value.code == "DIFFERENT_DRIVE"


def test_build(setup, tmp_path, drives):
    root, cards = setup
    project = dict(
        schema="quick-imposing/project@1",
        template="small",
        texts={},
        placements=[dict(cell=1, file="otherdrive/c-1.pdf", order=1)],
    )
    path = tmp_path / "input.qiproj.json"
    path.write_text(json.dumps(project))
    output = tmp_path / "out/result.pdf"
    report = generate(path, root, output)
    assert report["status"] == "FAIL"
    assert [e["code"] for e in report["errors"]] == ["DIFFERENT_DRIVE"]
    assert report["errors"][0]["reason"]
    assert sorted(p.name for p in output.parent.iterdir()) == ["result.report.json"]


def test_autofill(setup, tmp_path, drives):
    root, cards = setup
    output = tmp_path / "out/project.qiproj.json"
    result = autofill(
        templates_root=root,
        start_cell=1,
        files=[str(path) for path in cards],
        output=output,
        template="small",
    )
    assert result["status"] == "FAIL"
    assert [e["code"] for e in result["errors"]] == ["DIFFERENT_DRIVE"]
    assert result["errors"][0]["reason"]
    assert not output.exists()


def test_session(setup, tmp_path, drives):
    root, cards = setup
    session = Session.new(root, "small")
    session.assign(1, cards[0])
    with pytest.raises(SessionError) as error:
        session.to_project(tmp_path / "out")
    assert error.value.code == "DIFFERENT_DRIVE"
    assert "드라이브" in str(error.value)
    with pytest.raises(SessionError) as error:
        session.save(tmp_path / "out" / "x.pdf")
    assert error.value.code == "DIFFERENT_DRIVE"
    assert not (tmp_path / "out").exists()
