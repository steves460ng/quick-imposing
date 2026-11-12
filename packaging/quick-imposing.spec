# PyInstaller build: one folder with both programs.
#   pyinstaller packaging/quick-imposing.spec --noconfirm
# Result: dist/QuickImposing/QuickImposing.exe and QuickImposingEditor.exe.
# qpdf and Poppler go into dist/QuickImposing/bin/ afterwards (see
# .github/workflows/windows.yml).

from pathlib import Path

ROOT = Path(SPECPATH).parent
EXCLUDES = ["tkinter", "pytest", "numpy"]


def analysis(script):
    return Analysis(
        [str(ROOT / "packaging" / script)],
        pathex=[str(ROOT)],
        excludes=EXCLUDES,
    )


def prefer_qt_runtime(a):
    """Bundle the Visual C++ runtime that ships with PySide6.

    Several packages bring their own MSVCP140/VCRUNTIME140 copies and
    PyInstaller keeps one per file name. With an older copy Qt fails to load
    ("DLL load failed while importing QtCore: The specified procedure could
    not be found"), so the copies PySide6 was built and shipped with win.
    """
    import PySide6

    qt = Path(PySide6.__file__).parent
    prefixes = ("msvcp140", "vcruntime140", "concrt140")
    binaries = []
    for dest, source, kind in a.binaries:
        name = Path(dest).name
        if name.lower().startswith(prefixes):
            if Path(dest).parent != Path("."):
                continue  # keep a single copy at the top level
            if (qt / name).is_file():
                source = str(qt / name)
        binaries.append((dest, source, kind))
    a.binaries[:] = binaries
    return a


work = prefer_qt_runtime(analysis("run_work.py"))
editor = prefer_qt_runtime(analysis("run_editor.py"))


def program(a, name):
    return EXE(
        PYZ(a.pure),
        a.scripts,
        exclude_binaries=True,
        name=name,
        console=False,
    )


COLLECT(
    program(work, "QuickImposing"),
    work.binaries,
    work.datas,
    program(editor, "QuickImposingEditor"),
    editor.binaries,
    editor.datas,
    name="QuickImposing",
)
