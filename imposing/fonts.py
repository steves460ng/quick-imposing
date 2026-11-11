"""Exact-name system font discovery and Unicode CID font subset embedding."""

from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path
import sys
import hashlib

from fontTools import subset
from fontTools.ttLib import TTFont, TTCollection, TTLibError
import pikepdf as p


class FontError(ValueError):
    pass


def system_dirs():
    paths = [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".local/share/fonts",
        Path.home() / ".fonts",
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
        Path.home() / "Library/Fonts",
    ]
    if sys.platform == "win32":
        paths += [
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
            Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
            / "Microsoft/Windows/Fonts",
        ]
    return paths


@lru_cache(maxsize=8)
def catalogue(extra):
    found = {}
    ranks = {}
    for directory in [*map(Path, extra), *system_dirs()]:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.suffix.lower() not in (".ttf", ".otf", ".ttc", ".otc"):
                continue
            collection = None
            try:
                if path.suffix.lower() in (".ttc", ".otc"):
                    collection = TTCollection(path, lazy=True)
                    fonts = collection.fonts
                else:
                    fonts = [TTFont(path, lazy=True)]
                for index, font in enumerate(fonts):
                    names = {
                        n.toUnicode().casefold()
                        for n in font["name"].names
                        if n.nameID in (1, 4, 6, 16)
                    }
                    regular = (font["name"].getDebugName(2) or "").casefold() in (
                        "regular",
                        "normal",
                        "book",
                    )
                    for name in names:
                        rank = 0 if regular else 1
                        if name not in found or rank < ranks[name]:
                            found[name] = (str(path), index)
                            ranks[name] = rank
                if collection is None:
                    fonts[0].close()
            except (TTLibError, OSError, UnicodeError):
                continue
            finally:
                if collection:
                    collection.close()
    return found


def resolve(name, extra=()):
    value = catalogue(tuple(str(Path(d).resolve()) for d in extra)).get(name.casefold())
    if value is None:
        raise FontError(f"Font not found: {name}")
    return value


def embed(pdf, location, text):
    """Return a Type0 font, character->CID mapping and point-unit metrics.

    TrueType uses subset glyph IDs; CID-keyed CFF retains the original CIDs.
    No source PDF fonts or streams are processed by this routine.
    """
    path, index = location
    font = TTFont(path, fontNumber=index, recalcTimestamp=False)
    try:
        cmap = font.getBestCmap()
        missing = sorted({ord(c) for c in text if ord(c) not in cmap})
        if missing:
            raise FontError(f"Font lacks characters: {missing}")
        if font["OS/2"].fsType & 2:
            raise FontError("Font license prohibits embedding")
        options = subset.Options()
        options.recalc_timestamp = False
        sub = subset.Subsetter(options=options)
        sub.populate(unicodes={ord(c) for c in text})
        sub.subset(font)
        cmap = font.getBestCmap()
        units = font["head"].unitsPerEm
        scale = 1000 / units
        cff = "CFF " in font
        if cff:
            top = font["CFF "].cff.topDictIndex[0]
            if not hasattr(top, "ROS"):
                raise FontError(
                    "Name-keyed CFF is unsupported; choose a TrueType or CID-keyed CFF font"
                )
            mapping = {c: int(cmap[ord(c)][3:]) for c in set(text)}
        else:
            mapping = {c: font.getGlyphID(cmap[ord(c)]) for c in set(text)}
        tag = "".join(
            chr(65 + (b % 26))
            for b in hashlib.sha256(
                (path + str(index) + "".join(sorted(set(text)))).encode()
            ).digest()[:6]
        )
        base = tag + "+" + font["name"].getDebugName(6).replace(" ", "")
        widths = {
            mapping[c]: round(font["hmtx"][cmap[ord(c)]][0] * scale, 6)
            for c in set(text)
        }
        head = font["head"]
        hhea = font["hhea"]
        descriptor = p.Dictionary(
            Type=p.Name.FontDescriptor,
            FontName=p.Name("/" + base),
            Flags=4,
            FontBBox=p.Array(
                [
                    head.xMin * scale,
                    head.yMin * scale,
                    head.xMax * scale,
                    head.yMax * scale,
                ]
            ),
            ItalicAngle=font["post"].italicAngle,
            Ascent=hhea.ascent * scale,
            Descent=hhea.descent * scale,
            CapHeight=getattr(font["OS/2"], "sCapHeight", hhea.ascent) * scale,
            StemV=80,
        )
        if cff:
            binary = font["CFF "].compile(font)
            program = pdf.make_stream(binary)
            program.Subtype = p.Name.CIDFontType0C
            descriptor.FontFile3 = program
        else:
            buffer = BytesIO()
            font.save(buffer)
            program = pdf.make_stream(buffer.getvalue())
            program.Length1 = len(buffer.getvalue())
            descriptor.FontFile2 = program
        descendant = p.Dictionary(
            Type=p.Name.Font,
            Subtype=p.Name.CIDFontType0 if cff else p.Name.CIDFontType2,
            BaseFont=p.Name("/" + base),
            CIDSystemInfo=p.Dictionary(
                Registry="Adobe", Ordering="Identity", Supplement=0
            ),
            FontDescriptor=pdf.make_indirect(descriptor),
            DW=1000,
            W=p.Array(
                [
                    v
                    for cid, width in sorted(widths.items())
                    for v in (cid, p.Array([width]))
                ]
            ),
        )
        if not cff:
            descendant.CIDToGIDMap = p.Name.Identity
        lines = [
            "/CIDInit /ProcSet findresource begin",
            "12 dict begin",
            "begincmap",
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
            "/CMapName /ImposingUnicode def",
            "/CMapType 2 def",
            "1 begincodespacerange",
            "<0000> <FFFF>",
            "endcodespacerange",
        ]
        pairs = sorted((cid, c.encode("utf-16-be").hex()) for c, cid in mapping.items())
        for start in range(0, len(pairs), 100):
            batch = pairs[start : start + 100]
            lines.append(f"{len(batch)} beginbfchar")
            lines += [f"<{cid:04X}> <{unicode}>" for cid, unicode in batch]
            lines.append("endbfchar")
        lines += [
            "endcmap",
            "CMapName currentdict /CMap defineresource pop",
            "end",
            "end",
        ]
        result = pdf.make_indirect(
            p.Dictionary(
                Type=p.Name.Font,
                Subtype=p.Name.Type0,
                BaseFont=p.Name("/" + base),
                Encoding=p.Name("/Identity-H"),
                DescendantFonts=p.Array([pdf.make_indirect(descendant)]),
                ToUnicode=pdf.make_stream(("\n".join(lines) + "\n").encode()),
            )
        )
        metrics = dict(
            widths={c: widths[cid] / 1000 for c, cid in mapping.items()},
            ascent=hhea.ascent / units,
            descent=hhea.descent / units,
        )
        return result, mapping, metrics
    finally:
        font.close()
