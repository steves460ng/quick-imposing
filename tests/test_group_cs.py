"""Card transparency groups are blended in CMYK (RGB group -> K gray turned yellow)."""

import json
from pathlib import Path
import shutil
import subprocess

import pikepdf as p
import pytest

from imposing import store
from imposing.engine import card_group, generate
from imposing.session import Session

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "samples/input/base-front-blank.pdf"
DATA = ROOT / "samples/test03-2/data"


def make_card(path, cs):
    """A Ghostscript-style card: 60% gray in DeviceGray and K-only black."""
    pdf = p.new()
    pdf.add_blank_page(page_size=(124.8, 221.04))
    page = pdf.pages[0].obj
    page.Contents = pdf.make_stream(
        b"q .4 g 10 20 50 150 re f Q q 0 0 0 1 k 65 20 50 150 re f Q"
    )
    if cs is not None:
        page.Group = pdf.make_indirect(
            p.Dictionary(Type=p.Name.Group, S=p.Name.Transparency, CS=cs, I=True)
        )
    pdf.save(path)
    return path


@pytest.fixture
def root(tmp_path):
    data = json.loads((ROOT / "samples/manual/T31-front-3x8.json").read_text("utf-8"))
    data["name"] = "small"
    data["grid"]["count"] = [3, 3]
    data["text_fields"] = []
    root = tmp_path / "templates"
    store.save_template(data, root, BASE)
    return root


def build(root, tmp_path, *cards):
    session = Session.new(root, "small")
    for cell, card in enumerate(cards, 1):
        session.assign(cell, card)
    project = tmp_path / "p.qiproj.json"
    project.write_text(json.dumps(session.to_project(tmp_path)), encoding="utf-8")
    output = tmp_path / "out" / "r.pdf"
    report = generate(project, root, output)
    assert report["status"] == "PASS", report["errors"]
    return output, report


def forms(output, report):
    pdf = p.open(output)
    xobjects = pdf.pages[0].obj.Resources.XObject
    return pdf, {
        item["cell"]: xobjects[item["xobject"]]
        for item in report["placements"]
        if item.get("drawn")
    }


def test_rgb_group_is_blended_in_cmyk(root, tmp_path):
    card = make_card(tmp_path / "rgb.pdf", p.Name.DeviceRGB)
    before = card.read_bytes()
    output, report = build(root, tmp_path, card)
    _, by_cell = forms(output, report)
    group = by_cell[1].Group
    assert group.CS == p.Name.DeviceCMYK
    assert group.S == p.Name.Transparency and group.I is True  # rest unchanged
    assert report["info"] == [
        dict(code="B_GROUP_CS_REPLACED", cell=1, file=report["placements"][0]["file"],
             original="/DeviceRGB")
    ]
    assert card.read_bytes() == before  # the input file is never touched


def test_cmyk_and_missing_groups_are_kept(root, tmp_path):
    plain = make_card(tmp_path / "plain.pdf", None)
    output, report = build(root, tmp_path, DATA / "c-1.pdf", plain)
    _, by_cell = forms(output, report)
    source_pdf = p.open(DATA / "c-1.pdf")
    source = source_pdf.pages[0].obj.Group
    assert by_cell[1].Group.CS == p.Name.DeviceCMYK
    assert dict(by_cell[1].Group.items()).keys() == dict(source.items()).keys()
    assert "/Group" not in by_cell[2]
    assert report["info"] == []


def test_card_group_rules():
    owner = p.new()
    cmyk_icc = p.Array([p.Name.ICCBased, owner.make_stream(b"", N=4)])
    rgb_icc = p.Array([p.Name.ICCBased, owner.make_stream(b"", N=3)])
    for cs, replaced in [
        (p.Name.DeviceCMYK, None),
        (cmyk_icc, None),
        (p.Name.DeviceRGB, "/DeviceRGB"),
        (p.Name.DeviceGray, "/DeviceGray"),
        (rgb_icc, "/ICCBased"),
    ]:
        group = p.Dictionary(S=p.Name.Transparency, CS=cs)
        new, what = card_group(group)
        assert what == replaced
        assert (new.CS == p.Name.DeviceCMYK) if replaced else (new is group)
        assert group.CS == cs  # the source dictionary is not modified
    assert card_group(None) == (None, None)
    no_cs = p.Dictionary(S=p.Name.Transparency)
    assert card_group(no_cs) == (no_cs, None)


@pytest.mark.skipif(not shutil.which("gs"), reason="Ghostscript is only a test oracle")
def test_gray_and_black_separate_to_k_only(root, tmp_path):
    """Rendered to CMYK, the card's gray and black use the K plate only."""
    from PIL import Image

    card = make_card(tmp_path / "rgb.pdf", p.Name.DeviceRGB)
    output, _ = build(root, tmp_path, card)
    tif = tmp_path / "sep.tif"
    subprocess.run(
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=tiff32nc", "-r36",
         f"-sOutputFile={tif}", str(output)],
        check=True,
    )
    image = Image.open(tif)
    pixels = [image.getpixel((x, y)) for y in range(image.height) for x in range(image.width)]
    k_values = {round(k / 2.55) for c, m, y, k in pixels if k and not (c or m or y)}
    # Registration marks (Separation /All) are equal on every plate; skip them.
    mixed = [
        px for px in pixels if px[3] and px[0] and px[1] and px[2] and len(set(px)) > 1
    ]
    assert {60, 100} <= k_values
    assert not mixed
