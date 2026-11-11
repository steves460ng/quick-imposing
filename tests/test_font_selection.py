"""Reproduce Windows/Noto family and typographic-style ambiguity without OS fonts."""

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection
import pikepdf as p
import pytest

from imposing import fonts


def make_font(names):
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "A"])
    builder.setupCharacterMap({65: "A"})
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0))
    pen.lineTo((550, 0))
    pen.lineTo((300, 700))
    pen.closePath()
    builder.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "A": pen.glyph()})
    builder.setupHorizontalMetrics({".notdef": (600, 0), "A": (600, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(names)
    builder.setupOS2(
        sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200
    )
    builder.setupPost()
    builder.setupMaxp()
    return builder.font


@pytest.fixture
def isolated_catalogue(monkeypatch):
    fonts.catalogue.cache_clear()
    monkeypatch.setattr(fonts, "system_dirs", lambda: [])
    yield
    fonts.catalogue.cache_clear()


def write_face(tmp_path, filename, names, collection=False):
    font = make_font(names)
    path = tmp_path / filename
    if collection:
        ttc = TTCollection()
        ttc.fonts = [
            make_font({1: "Other", 2: "Regular", 4: "Other", 6: "Other-Regular"}),
            font,
        ]
        ttc.save(path)
        ttc.close()
    else:
        font.save(path)
        font.close()
    return path


def test_black_legacy_regular_does_not_win_family(tmp_path, isolated_catalogue):
    # Mirrors Noto Black: legacy style Regular, typographic style Black, index 1.
    black = write_face(
        tmp_path,
        "00-Black.ttc",
        {
            1: "Review Family Black",
            2: "Regular",
            4: "Review Family Black",
            6: "ReviewFamily-Black",
            16: "Review Family",
            17: "Black",
        },
        collection=True,
    )
    regular = write_face(
        tmp_path,
        "99-Regular.ttc",
        {
            1: "Review Family",
            2: "Regular",
            4: "Review Family",
            6: "ReviewFamily-Regular",
            16: "Review Family",
            17: "Regular",
        },
        collection=True,
    )
    selected = fonts.resolve("Review Family", [tmp_path])
    assert selected == (str(regular), 1)
    assert fonts.resolve("ReviewFamily-Black", [tmp_path]) == (str(black), 1)
    # Check the saved PDF's actual BaseFont, not merely the resolver result.
    with p.new() as doc:
        page = doc.add_blank_page()
        font, mapping, _ = fonts.embed(doc, selected, "A")
        page.Resources = p.Dictionary(Font=p.Dictionary(F=font))
        page.Contents = doc.make_stream(
            f"BT /F 12 Tf <{mapping['A']:04X}> Tj ET".encode()
        )
        doc.save(tmp_path / "font.pdf")
    with p.open(tmp_path / "font.pdf") as doc:
        font = doc.pages[0].Resources.Font.F
        assert str(font.BaseFont).split("+", 1)[-1] == "ReviewFamily-Regular"
        assert font.DescendantFonts[0].FontDescriptor.FontFile2.read_bytes()


@pytest.mark.parametrize("typographic", [True, False])
def test_family_only_prefers_regular_with_style_fallback(
    tmp_path, isolated_catalogue, typographic
):
    black = {
        1: "Face Black",
        2: "Regular" if typographic else "Black",
        4: "Face Black",
        6: "Face-Black",
        16: "Shared Family",
    }
    regular = {
        1: "Face Plain",
        2: "Bold" if typographic else "Regular",
        4: "Face Plain",
        6: "Face-Regular",
        16: "Shared Family",
    }
    if typographic:
        black[17] = "Black"
        regular[17] = "Regular"
    write_face(tmp_path, "00-Black.ttf", black)
    target = write_face(tmp_path, "99-Regular.ttf", regular)
    assert fonts.resolve("Shared Family", [tmp_path]) == (str(target), 0)


@pytest.mark.parametrize("exact_id", [1, 4, 6])
def test_exact_name_precedes_typographic_family_alias(
    tmp_path, isolated_catalogue, exact_id
):
    write_face(
        tmp_path,
        "00-Alias.ttf",
        {
            1: "Alias Regular",
            2: "Regular",
            4: "Alias Regular",
            6: "Alias-Regular",
            16: "Requested",
            17: "Regular",
        },
    )
    names = {
        1: "Named Black",
        2: "Regular",
        4: "Named Black",
        6: "Named-Black",
        16: "Other Family",
        17: "Black",
    }
    names[exact_id] = "Requested"
    target = write_face(tmp_path, "99-Exact.ttf", names)
    assert fonts.resolve("Requested", [tmp_path]) == (str(target), 0)
