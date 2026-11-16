"""Font problems are reported with their own codes (REFACTORING R1, SPEC §6.4)."""

import json
import os
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
import pikepdf as p
import pytest

from imposing import fonts
from imposing.engine import create_template, generate
from imposing.gui.work import describe_error

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "samples/test03-1"


def triangle(pen):
    pen.moveTo((50, 0))
    pen.lineTo((550, 0))
    pen.lineTo((300, 700))
    pen.closePath()


def make_font(path, family, fs_type=0, cff=False):
    """A font with only the glyph "A"; CFF fonts are name-keyed (no ROS)."""
    builder = FontBuilder(1000, isTTF=not cff)
    builder.setupGlyphOrder([".notdef", "A"])
    builder.setupCharacterMap({65: "A"})
    if cff:
        empty = T2CharStringPen(600, None)
        glyph = T2CharStringPen(600, None)
        triangle(glyph)
        builder.setupCFF(
            family.replace(" ", ""),
            {"FullName": family},
            {".notdef": empty.getCharString(), "A": glyph.getCharString()},
            {},
        )
    else:
        glyph = TTGlyphPen(None)
        triangle(glyph)
        builder.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "A": glyph.glyph()})
    builder.setupHorizontalMetrics({".notdef": (600, 0), "A": (600, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(
        {1: family, 2: "Regular", 4: family, 6: family.replace(" ", "") + "-Regular"}
    )
    builder.setupOS2(
        sTypoAscender=800,
        sTypoDescender=-200,
        usWinAscent=800,
        usWinDescent=200,
        fsType=fs_type,
    )
    builder.setupPost()
    if not cff:
        builder.setupMaxp()
    builder.save(path)
    return path


CASES = {
    # family, font options, text, expected code
    "glyph": ("Review Glyph", {}, "AB", "FONT_GLYPH_MISSING"),
    "embed": ("Review Locked", {"fs_type": 2}, "A", "FONT_EMBED_FORBIDDEN"),
    "cff": ("Review NameKeyed", {"cff": True}, "A", "FONT_UNSUPPORTED"),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_embed_raises_coded_error(tmp_path, case):
    family, options, text, code = CASES[case]
    suffix = ".otf" if options.get("cff") else ".ttf"
    path = make_font(tmp_path / f"face{suffix}", family, **options)
    with pytest.raises(fonts.FontError) as error:
        fonts.embed(p.new(), (str(path), 0), text)
    assert error.value.code == code
    if code == "FONT_GLYPH_MISSING":
        assert error.value.context == {"missing": ["B"]}


def test_missing_font_has_code():
    with pytest.raises(fonts.FontError) as error:
        fonts.resolve("No Such Font 246813")
    assert error.value.code == "FONT_NOT_FOUND"


@pytest.mark.parametrize("case", sorted(CASES))
def test_build_reports_font_code(tmp_path, case):
    family, options, text, code = CASES[case]
    font_dir = tmp_path / "fonts"
    font_dir.mkdir()
    suffix = ".otf" if options.get("cff") else ".ttf"
    make_font(font_dir / f"face{suffix}", family, **options)
    definition = json.loads(
        (FIXTURES / "template-defs/T31-front-3x8.json").read_text()
    )["template"]
    for field in definition["text_fields"]:
        field["font"] = family
    root = tmp_path / "templates"
    create_template(definition, ROOT / "samples/input/base-front-blank.pdf", root)
    project = json.loads((FIXTURES / "projects/T31-01.qiproj.json").read_text())
    for item in project["placements"]:
        item["file"] = Path(
            os.path.relpath(ROOT / "samples/input" / Path(item["file"]).name, tmp_path)
        ).as_posix()
    project["texts"] = {definition["text_fields"][0]["id"]: text}
    path = tmp_path / "input.qiproj.json"
    path.write_text(json.dumps(project))
    output = tmp_path / "out/result.pdf"
    report = generate(path, root, output, [font_dir])
    assert report["status"] == "FAIL"
    assert [e["code"] for e in report["errors"]] == [code]
    entry = report["errors"][0]
    assert entry["font"] == family and entry["reason"]
    assert not output.exists()
    # The work program picks its sentence by code alone.
    message = describe_error(entry)
    assert "글꼴" in message and "입력을 처리할 수 없습니다" not in message


def test_error_text_ignores_english_reason():
    # Changing the engine's English wording must not change the Korean text.
    entry = dict(code="FONT_GLYPH_MISSING", reason="anything", font="F")
    assert "없는 글자" in describe_error(entry)
    assert "입력을 처리할 수 없습니다" in describe_error(
        dict(code="SCHEMA_INVALID", reason="Font lacks characters: [1]")
    )
