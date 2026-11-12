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


work = analysis("run_work.py")
editor = analysis("run_editor.py")


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
