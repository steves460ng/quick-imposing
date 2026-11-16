"""LICENSE and the third-party license collection used by build.ps1."""

import importlib.util
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def load_collector():
    spec = importlib.util.spec_from_file_location(
        "collect_licenses", ROOT / "packaging/collect_licenses.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_project_license_is_mit():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert "Copyright (c) 2026 steves460ng" in text
    assert 'license = "MIT"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_collects_every_component(tmp_path):
    collector = load_collector()
    tools = tmp_path / "tools"
    (tools / "qpdf-12.0.0-msvc64").mkdir(parents=True)
    (tools / "qpdf-12.0.0-msvc64" / "LICENSE.txt").write_text("qpdf license")
    nested = tools / "Release-25.0.0-0" / "poppler-25.0.0" / "share" / "licenses" / "cairo"
    nested.mkdir(parents=True)
    (nested / "COPYING").write_text("cairo license")
    (tools / "unrelated").mkdir()
    (tools / "unrelated" / "LICENSE").write_text("not ours")
    qpdf = shutil.which("qpdf") or str(tmp_path / "qpdf.exe")
    poppler = shutil.which("pdftoppm") or str(tmp_path / "pdftoppm.exe")
    out = tmp_path / "out"
    code = collector.main(
        ["--out", str(out), "--tool", f"qpdf={qpdf}", "--tool", f"poppler={poppler}",
         "--search", str(tools)]
    )
    assert code == 0
    readme = (out / "README.md").read_text(encoding="utf-8")
    for name in ("pikepdf", "pillow", "fonttools", "PySide6_Essentials", "Python", "qpdf", "Poppler"):
        assert f"| {name}" in readme, name
    assert "| quick-imposing" not in readme  # our own license is LICENSE.txt
    # Bundled libraries inside pikepdf (qpdf, zlib, ...) come along.
    assert (out / "python/pikepdf-10.18.0/third-party-licenses/qpdf.txt").is_file()
    # Qt is used under the LGPL: its text (and the GPL it builds on) is always
    # there, and the commercial license text that Windows wheels ship is not.
    qt = out / "python/PySide6_Essentials-6.10.1"
    names = sorted(p.name for p in qt.rglob("*") if p.is_file())
    assert "LGPL-3.0.txt" in names and "GPL-3.0.txt" in names
    assert not [n for n in names if "Commercial" in n]
    assert (out / "python-runtime/LICENSE.txt").is_file()
    # Tool licenses from the downloaded release folders, plus the standard text.
    assert (out / "qpdf/package/qpdf-12.0.0-msvc64/LICENSE.txt").read_text() == "qpdf license"
    assert (out / "qpdf/Apache-2.0.txt").is_file()
    assert (
        out / "poppler/package/Release-25.0.0-0/poppler-25.0.0/share/licenses/cairo/COPYING"
    ).is_file()
    assert (out / "poppler/GPL-2.0.txt").is_file() and (out / "poppler/GPL-3.0.txt").is_file()
    assert not list(out.rglob("unrelated"))
    assert "poppler.freedesktop.org" in readme


def test_standard_texts_are_complete():
    folder = ROOT / "packaging/licenses"
    heads = {
        "Apache-2.0.txt": "Apache License",
        "GPL-2.0.txt": "GNU GENERAL PUBLIC LICENSE",
        "GPL-3.0.txt": "GNU GENERAL PUBLIC LICENSE",
        "LGPL-3.0.txt": "GNU LESSER GENERAL PUBLIC LICENSE",
    }
    for name, head in heads.items():
        text = (folder / name).read_text(encoding="utf-8")
        assert head in text[:400] and len(text) > 7000, name


def test_missing_license_text_warns_unless_strict(tmp_path, monkeypatch, capsys):
    collector = load_collector()
    # A package that ships no license file and has no standard text to use.
    monkeypatch.setattr(collector, "metadata_license_files", lambda dist: [])
    monkeypatch.setattr(collector, "fallback_for", lambda expression: [])
    out = tmp_path / "out"
    assert collector.main(["--out", str(out)]) == 0
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "라이선스 문서 없음" in readme
    assert "https://pypi.org/project/fonttools/4.68.0/" in readme
    assert "WARNING: license text missing for:" in capsys.readouterr().out
    assert collector.main(["--out", str(out), "--strict"]) == 1


def test_lgpl_text_added_next_to_shipped_files(tmp_path, monkeypatch):
    collector = load_collector()
    shipped = tmp_path / "pkg.dist-info" / "licenses"
    shipped.mkdir(parents=True)
    (shipped / "LicenseRef-Qt-Commercial.txt").write_text("commercial")
    (shipped / "NOTICE").write_text("notice")

    class Entry(str):
        pass

    class Dist:
        version = "1.0"
        metadata = {"Name": "Qtish", "License-Expression": "LGPL-3.0-only OR GPL-3.0-only"}
        files = [Entry("pkg.dist-info/licenses/LicenseRef-Qt-Commercial.txt"),
                 Entry("pkg.dist-info/licenses/NOTICE")]

        def locate_file(self, entry):
            return tmp_path / entry

    monkeypatch.setattr(collector, "runtime_distributions", lambda **kwargs: [Dist()])
    rows = collector.collect_python(tmp_path / "out", extra_roots=())
    names = sorted(path.name for path in rows[0]["files"])
    assert names == ["GPL-3.0.txt", "LGPL-3.0.txt", "NOTICE"]
