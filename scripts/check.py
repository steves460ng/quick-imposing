"""Quiet check command: one line on success, only the failures otherwise.

    python scripts/check.py              full check (ruff, pytest, runners, GUI self-test)
    python scripts/check.py PATH [...]   ruff on PATHs and only the related tests

The full check runs test32_runner.py, which also runs the 3-1 regression
cases (test03_runner.py), so test03_runner.py is not run separately.
"""

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
RUFF_TARGETS = ["imposing", "tests", "packaging/collect_licenses.py", "scripts"]
MAX_LINES = 20


def run(args, cwd=ROOT, env=None):
    return subprocess.run(
        args, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )


def clip(lines):
    lines = [line for line in lines if line.strip()]
    if len(lines) > MAX_LINES:
        return lines[:MAX_LINES] + [f"... {len(lines) - MAX_LINES} more"]
    return lines


def base_env():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT), env.get("PYTHONPATH")]))
    return env


def ruff(targets):
    try:
        result = run([sys.executable, "-m", "ruff", "check", "-q", "--output-format", "concise", "--select", "F", *targets])
    except OSError as exc:
        return False, "ruff", [str(exc)]
    if result.returncode == 0:
        return True, "ruff", []
    lines = (result.stdout + result.stderr).splitlines()
    if "No module named ruff" in result.stderr:
        lines = ["ruff is not installed: pip install ruff==0.16.9"]
    return False, "ruff", clip(lines)


def pytest(tests=()):
    result = run(
        [sys.executable, "-m", "pytest", "-q", "--tb=line", "-p", "no:cacheprovider", *tests],
        env=base_env(),
    )
    output = (result.stdout + result.stderr).splitlines()
    tail = next(
        (line for line in reversed(output) if re.search(r"\d+ (passed|failed|errors?)\b", line)),
        "",
    )
    label = f"pytest ({tail.strip('= ').split(' in ')[0]})" if tail else "pytest"
    if result.returncode == 0:
        return True, label, []
    keep = [
        line for line in output
        if line.startswith(("FAILED", "ERROR", "E   "))
        or re.match(r"^\S+\.py:\d+: ", line)
    ]
    return False, label, clip(keep or output[-MAX_LINES:])


def runner(scratch):
    import json

    out = Path(scratch) / "test03-2"
    result = run([sys.executable, "test32_runner.py", "--out", str(out)], env=base_env())
    label = "runners (3-2 with 3-1 regression)"
    if result.returncode == 0:
        return True, label, []
    lines = []
    try:
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        regression = summary.get("D9_regression03_1", {})
        lines.append(f"3-2: {summary.get('passed')}/{summary.get('case_count')} passed, "
                     f"3-1 regression: {regression.get('status')}")
        for case in summary.get("cases", []):
            if case.get("status") != "PASS":
                ids = [f["id"] if isinstance(f, dict) and "id" in f else str(f)[:120]
                       for f in case.get("failures", [])]
                lines.append(f"{case.get('case')}: {', '.join(ids)}")
    except (OSError, ValueError):
        lines = (result.stdout + result.stderr).splitlines()[-MAX_LINES:]
    return False, label, clip(lines)


def selftest(scratch):
    failures = []
    for program in ("work", "editor"):
        folder = Path(scratch) / f"selftest-{program}"
        folder.mkdir()
        result = run(
            [sys.executable, "-m", f"imposing.gui.{program}", "--selftest"],
            cwd=folder, env=base_env(),
        )
        if result.returncode != 0:
            failures.append(f"{program}: exit {result.returncode}")
            for name in ("selftest-error.txt", "selftest-hang.txt"):
                file = folder / name
                if file.is_file():
                    failures += file.read_text(encoding="utf-8").splitlines()[-8:]
    return not failures, "GUI self-test", clip(failures)


def related_tests(paths):
    """Test files for ``paths``; None means "run the whole suite"."""
    tests = set()
    sources = {file: file.read_text(encoding="utf-8") for file in (ROOT / "tests").glob("test_*.py")}
    for raw in paths:
        path = (Path.cwd() / raw).resolve()
        try:
            relative = path.relative_to(ROOT)
        except ValueError:
            continue
        if relative.parts[:1] == ("tests",) and path.name.startswith("test_"):
            tests.add(path)
        elif relative.parts[:1] == ("imposing",) and path.suffix == ".py":
            parts = list(relative.with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            dotted = ".".join(parts)
            parent, name = ".".join(parts[:-1]), parts[-1]
            pattern = re.compile(
                rf"\b{re.escape(dotted)}\b|from {re.escape(parent)} import [^\n]*\b{name}\b"
            )
            found = {file for file, text in sources.items() if pattern.search(text)}
            if not found:
                return None
            tests |= found
    return sorted(str(test.relative_to(ROOT)) for test in tests)


def main(argv):
    started = time.monotonic()
    results = []
    if argv:
        python_paths = [p for p in argv if p.endswith(".py") and Path(p).exists()]
        if python_paths:
            results.append(ruff(python_paths))
        tests = related_tests(argv)
        if tests is None:
            results.append(pytest())
        elif tests:
            results.append(pytest(tests))
    else:
        results.append(ruff(RUFF_TARGETS))
        results.append(pytest())
        with tempfile.TemporaryDirectory() as scratch:
            results.append(runner(scratch))
            results.append(selftest(scratch))
    elapsed = time.monotonic() - started
    failed = [(label, lines) for ok, label, lines in results if not ok]
    if not failed:
        labels = ", ".join(label for _, label, _ in results) or "nothing to check"
        report = [f"check OK: {labels} [{elapsed:.0f}s]"]
    else:
        report = [f"check FAILED: {', '.join(label for label, _ in failed)} [{elapsed:.0f}s]"]
        for label, lines in failed:
            report.append(f"-- {label}")
            report += [f"   {line}" for line in lines]
    print("\n".join(report))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("```\n" + "\n".join(report) + "\n```\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
