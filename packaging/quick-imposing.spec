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
    """Bundle one matching Visual C++ runtime: the set shipped with PySide6.

    The runtime DLLs must come from the same release. A bundle that mixes
    them (VCRUNTIME140 from one place, MSVCP140 from another or from the
    system) fails with "DLL load failed while importing QtCore: The specified
    procedure could not be found". Every runtime DLL PySide6 ships is placed
    at the top level, replacing copies collected from elsewhere.
    """
    import PySide6

    qt = Path(PySide6.__file__).parent
    prefixes = ("msvcp140", "vcruntime140", "concrt140")
    shipped = {
        f.name.lower(): f
        for f in qt.glob("*.dll")
        if f.name.lower().startswith(prefixes)
    }
    if not shipped:
        return a  # not a Windows wheel
    binaries = [
        entry
        for entry in a.binaries
        if not (
            Path(entry[0]).parent == Path(".")
            and Path(entry[0]).name.lower().startswith(prefixes)
        )
    ]
    binaries += [(f.name, str(f), "BINARY") for f in shipped.values()]
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
