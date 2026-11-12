"""Start a GUI program; with --selftest, leave start-up failures in a file."""

import os
import sys
import traceback


def describe_bundle(stream):
    """Which bundled DLL fails to load, and what lies at the top level."""
    import ctypes

    home = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    stream.write(f"bundle: {home}\n")
    for name in (
        "vcruntime140.dll",
        "msvcp140.dll",
        "python3.dll",
        "shiboken6/shiboken6.abi3.dll",
        "PySide6/Qt6Core.dll",
        "PySide6/pyside6.abi3.dll",
        "PySide6/QtCore.pyd",
    ):
        path = os.path.join(home, *name.split("/"))
        if not os.path.exists(path):
            stream.write(f"  missing  {name}\n")
            continue
        try:
            ctypes.WinDLL(path)
            stream.write(f"  ok       {name}\n")
        except OSError as exc:
            stream.write(f"  FAILED   {name}: {exc}\n")
    for folder in ("", "PySide6", "shiboken6"):
        try:
            names = sorted(
                n for n in os.listdir(os.path.join(home, folder))
                if n.lower().endswith((".dll", ".pyd"))
            )
        except OSError:
            names = []
        stream.write(f"  {folder or '.'}: {' '.join(names)}\n")


def run(module):
    try:
        code = __import__(module, fromlist=["main"]).main()
    except Exception:
        if "--selftest" not in sys.argv:
            raise
        # A windowed program has no console.
        with open("selftest-error.txt", "a", encoding="utf-8") as stream:
            traceback.print_exc(file=stream)
            if sys.platform == "win32":
                describe_bundle(stream)
        code = 3
    raise SystemExit(code)
