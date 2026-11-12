import json
from pathlib import Path
import subprocess
import sys

import pytest

from imposing.autofill import autofill, natural_file_key
from test32_runner import run_cases

ROOT = Path(__file__).resolve().parents[1]


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def setup(tmp_path):
    definition = json.loads(
        (ROOT / "samples/test03-2/template-defs/T32-fwd-3x3.json").read_text()
    )["template"]
    template = tmp_path / "templates" / definition["name"] / "template.json"
    write(template, definition)
    source = tmp_path / "inputs" / "input.json"
    write(
        source,
        {
            "schema": "quick-imposing/project@1",
            "template": definition["name"],
            "texts": {},
            "placements": [],
        },
    )
    files = [ROOT / f"samples/test03-2/data/c-{i}.pdf" for i in [10, 3, 11, 1, 2]]
    args = dict(
        templates_root=tmp_path / "templates",
        project=source,
        start_cell=1,
        files=files,
        output=tmp_path / "new" / "filled.json",
    )
    return args, template


def test_acceptance_cases(tmp_path):
    summary = run_cases(tmp_path / "suite")
    assert summary["status"] == "PASS", summary
    assert summary["passed"] == 11


def test_natural_sort(tmp_path):
    paths = [
        tmp_path / name
        for name in [
            "z/c-2.pdf",
            "a/c-10.pdf",
            "b/c-02.pdf",
            "a/C-2.pdf",
            "a/c-2.PDF",
            "a/c-2.ai",
            "a/2.pdf",
        ]
    ]
    assert [
        p.relative_to(tmp_path).as_posix() for p in sorted(paths, key=natural_file_key)
    ] == [
        "a/2.pdf",
        "a/c-2.ai",
        "a/C-2.pdf",
        "a/c-2.PDF",
        "b/c-02.pdf",
        "z/c-2.pdf",
        "a/c-10.pdf",
    ]


def test_symlink_selected_name(setup, tmp_path):
    args, _ = setup
    alias = tmp_path / "c-0.pdf"
    alias.symlink_to(args["files"][0])
    args["files"] = [args["files"][3], alias]
    result = autofill(**args)
    assert [Path(p).name for p in result["sorted_files"]] == ["c-0.pdf", "c-1.pdf"]


def test_preserve_order_metadata_and_missing_target(setup):
    args, _ = setup
    source = args["project"]
    original = json.loads(source.read_text())
    original.update(texts={"label": "Keep"}, extra={"keep": True})
    original["placements"] = [
        {"cell": 9, "file": "missing.pdf", "order": 12},
        {"cell": 8, "file": "another.pdf", "order": 4},
    ]
    write(source, original)
    before = source.read_bytes()
    result = autofill(**args)
    saved = json.loads(args["output"].read_text())
    assert result["status"] == "PASS"
    assert [p["order"] for p in saved["placements"]] == [12, 4, 13, 14, 15, 16, 17]
    assert saved["texts"] == original["texts"] and saved["extra"] == original["extra"]
    for old, new in zip(original["placements"], saved["placements"]):
        assert (source.parent / old["file"]).resolve() == (
            args["output"].parent / new["file"]
        ).resolve()
    assert source.read_bytes() == before


def test_missing_existing_file_still_blocks(setup):
    args, _ = setup
    data = json.loads(args["project"].read_text())
    data["placements"] = [{"cell": 1, "file": "missing.pdf", "order": 7}]
    write(args["project"], data)
    result = autofill(**args)
    assert result["status"] == "PASS" and result["added"] == []
    assert result["warnings"][0]["reason"] == "occupied"
    assert result["warnings"][0]["blocked_cell"] == 1
    assert len(json.loads(args["output"].read_text())["placements"]) == 1


@pytest.mark.parametrize(
    "fault,code",
    [
        ("empty", "SCHEMA_INVALID"),
        ("missing", "SCHEMA_INVALID"),
        ("start", "CELL_NOT_IN_TEMPLATE"),
        ("template", "TEMPLATE_NOT_FOUND"),
        ("direction", "SCHEMA_INVALID"),
    ],
)
def test_errors_do_not_save(setup, fault, code):
    args, template = setup
    if fault == "empty":
        args["files"] = []
    elif fault == "missing":
        args["start_cell"] = 9
        args["files"].append(args["output"].parent / "z-missing.pdf")
    elif fault == "start":
        args["start_cell"] = 10
    elif fault == "template":
        template.unlink()
    else:
        data = json.loads(template.read_text())
        data["fill_direction"] = "sideways"
        write(template, data)
    result = autofill(**args)
    assert result["status"] == "FAIL"
    assert result["errors"][0]["code"] == code
    assert all(e["reason"] for e in result["errors"])
    assert not args["output"].exists()
    assert (
        json.loads(args["output"].with_suffix(".autofill.json").read_text()) == result
    )


def test_offpage_and_duplicate_inputs(setup):
    args, template = setup
    data = json.loads(template.read_text())
    data["grid"]["origin_mm"] = [10000, 10000]
    write(template, data)
    args["files"] = [args["files"][0]] * 2
    result = autofill(**args)
    assert result["status"] == "PASS" and not result["warnings"]
    assert [p["cell"] for p in result["added"]] == [1, 2]


@pytest.mark.parametrize("existing", ["output", "report"])
def test_no_overwrite(setup, existing):
    args, _ = setup
    path = (
        args["output"]
        if existing == "output"
        else args["output"].with_suffix(".autofill.json")
    )
    path.parent.mkdir(parents=True)
    path.write_bytes(b"keep")
    if existing == "report":
        with pytest.raises(FileExistsError):
            autofill(**args)
        assert not args["output"].exists()
    else:
        assert autofill(**args)["status"] == "FAIL"
    assert path.read_bytes() == b"keep"


def test_report_project_alias_rejected(setup, tmp_path):
    args, _ = setup
    args["output"].parent.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(args["output"].parent, target_is_directory=True)
    args["report_path"] = alias / args["output"].name
    with pytest.raises(ValueError):
        autofill(**args)
    assert not args["output"].exists()


@pytest.mark.parametrize("empty", [False, True])
def test_cli_other_working_directory(setup, tmp_path, empty):
    args, template = setup
    work = tmp_path / "cli"
    work.mkdir()
    (work / "selected.pdf").write_bytes(args["files"][0].read_bytes())
    cmd = [
        sys.executable,
        "-m",
        "imposing",
        "autofill",
        "--template",
        template.parent.name,
        "--templates-root",
        str(args["templates_root"]),
        "--start-cell",
        "9",
        "--output",
        "saved/filled.json",
        "--files",
    ]
    if not empty:
        cmd.extend(["selected.pdf", "selected.pdf"])
    result = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    report = json.loads(result.stdout)
    assert result.returncode == (1 if empty else 0), result.stderr
    if empty:
        assert not (work / "saved/filled.json").exists()
    else:
        saved = json.loads((work / "saved/filled.json").read_text())
        assert saved["placements"][0]["file"] == "../selected.pdf"
        assert report["warnings"][0]["reason"] == "end_of_cells"
