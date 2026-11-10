import json
from pathlib import Path
import pikepdf
import pytest
from quick_imposing import impose

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "samples/input/base.pdf"
CARDS = ROOT / "samples/input"


def config():
    return json.loads((ROOT / "layout.json").read_text())


@pytest.mark.parametrize("count,gap", [(3, 3), (20, 3), (3, 5)])
def test_success(tmp_path, count, gap):
    cfg = config()
    cfg["gap_mm"] = [gap, gap]
    cfg["assign"] = {str(i + 1): f"B-{i % 3 + 1}.pdf" for i in range(count)}
    report = impose(BASE, cfg, CARDS, tmp_path)
    assert report["final"] == "PASS", report["checks"]
    assert len(report["slots"]) == count
    assert report["illustrator_private_data_removed"] == ["page-1"]
    with pikepdf.open(tmp_path / "result.pdf") as result:
        assert "/Illustrator" not in result.pages[0].obj.get("/PieceInfo", {})
    assert all(c["passed"] for c in report["checks"] if c["id"] != "V15")
    if gap == 3:
        assert report["slots"][0]["cm"][4:] == pytest.approx(
            [59.475, 1241.554], abs=0.01
        )


def test_unsafe(tmp_path):
    cfg = config()
    cfg["gap_mm"] = [10, 10]
    with pytest.raises(ValueError, match="safe area"):
        impose(BASE, cfg, CARDS, tmp_path)
    assert not (tmp_path / "result.pdf").exists()


def test_small(tmp_path):
    with pikepdf.new() as doc:
        doc.add_blank_page(page_size=(100, 100))
        doc.save(tmp_path / "small.pdf")
    cfg = config()
    cfg["assign"] = {"1": "small.pdf"}
    with pytest.raises(ValueError, match="too small"):
        impose(BASE, cfg, tmp_path, tmp_path / "out")
    assert not (tmp_path / "out/result.pdf").exists()


def test_illustrator_private_data(tmp_path):
    from quick_imposing import remove_stale_illustrator_data, canonical, streams

    with pikepdf.open(BASE) as doc:
        page = doc.pages[0]
        assert "/Illustrator" in page.obj.PieceInfo
        resources = canonical(page.Resources)
        content = [s.read_raw_bytes() for s in streams(page)]
        page.obj.PieceInfo.OtherApp = pikepdf.Dictionary(Private=pikepdf.String("keep"))
        doc.Root.PieceInfo = pikepdf.Dictionary(
            Illustrator=pikepdf.Dictionary(Private=pikepdf.String("stale"))
        )
        assert remove_stale_illustrator_data(doc) == ["catalog", "page-1"]
        assert "/PieceInfo" not in doc.Root
        assert str(page.obj.PieceInfo.OtherApp.Private) == "keep"
        assert canonical(page.Resources) == resources
        assert [s.read_raw_bytes() for s in streams(page)] == content
        assert remove_stale_illustrator_data(doc) == []
        doc.save(tmp_path / "clean.pdf")
    with pikepdf.open(tmp_path / "clean.pdf") as doc:
        assert "/Illustrator" not in doc.pages[0].obj.PieceInfo
