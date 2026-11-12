import sys
import traceback

try:
    from imposing.gui.work import main

    code = main()
except Exception:
    if "--selftest" not in sys.argv:
        raise
    # A windowed program has no console; leave the reason in a file.
    with open("selftest-error.txt", "a", encoding="utf-8") as stream:
        traceback.print_exc(file=stream)
    code = 3
raise SystemExit(code)
