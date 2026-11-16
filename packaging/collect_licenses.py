"""Collect third-party license texts for the Windows distribution folder.

Run by packaging/build.ps1 with the build's Python, after bin\\ is ready:

    python packaging/collect_licenses.py --out dist/QuickImposing/THIRD-PARTY-LICENSES \\
        --tool qpdf=bin/qpdf/qpdf.exe --tool poppler=bin/poppler/pdftoppm.exe --search tools

What goes in:

- Python packages that the programs load (the runtime dependency tree of
  quick-imposing with the "gui" extra) and PyInstaller (its bootloader is
  part of each exe): the license files from each package's metadata.
- The Python runtime license.
- qpdf and Poppler: license files found next to the executables or in the
  downloaded release folders (--search), plus the standard license text.
- README.md: a table of every component, its version and license.

Standard texts that a package does not ship (Qt's LGPL, qpdf's Apache,
Poppler's GPL) come from packaging/licenses/. A component that still ends
up without any license text is a warning: the build goes on and README.md
marks it with a link to the original. With --strict it is an error
(exit code 1), for a check before distributing outside.
"""

import argparse
import importlib.metadata as md
from pathlib import Path
import re
import shutil
import subprocess
import sys

from packaging.markers import default_environment
from packaging.requirements import Requirement

HERE = Path(__file__).resolve().parent
STANDARD = HERE / "licenses"
LICENSE_FILE = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS|COPYRIGHT)", re.I)
TEXT_SUFFIXES = {"", ".txt", ".md", ".rst", ".apache", ".bsd", ".mit", ".lgpl", ".gpl"}

# Standard texts for licenses that some components do not ship themselves.
# The first key found in a license expression wins: PySide6 offers
# "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only" and is used under the LGPL.
FALLBACK = {
    "LGPL-3.0": ["LGPL-3.0.txt", "GPL-3.0.txt"],  # the LGPL builds on the GPL
    "GPL-3.0": ["GPL-3.0.txt"],
    "GPL-2.0": ["GPL-2.0.txt"],
    "Apache-2.0": ["Apache-2.0.txt"],
}

TOOLS = {
    "qpdf": dict(
        title="qpdf",
        license="Apache-2.0",
        standard=["Apache-2.0.txt"],
        home="https://github.com/qpdf/qpdf",
        version_args=["--version"],
    ),
    "poppler": dict(
        title="Poppler (pdftoppm 등)",
        license="GPL-2.0 / GPL-3.0 (GPL 계열)",
        standard=["GPL-2.0.txt", "GPL-3.0.txt"],
        home="https://poppler.freedesktop.org/",
        build="https://github.com/oschwartz10612/poppler-windows",
        version_args=["-v"],
    ),
}


def normalized(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def license_of(dist):
    meta = dist.metadata
    value = meta.get("License-Expression")
    if value:
        return value
    value = (meta.get("License") or "").strip()
    if value and "\n" not in value and len(value) <= 80:
        return value
    classifiers = [
        c.split("::")[-1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    return " / ".join(classifiers) or "(메타데이터에 없음)"


def runtime_distributions(root="quick-imposing", extras=("gui",), extra_roots=()):
    """Distributions reachable from ``root`` (with ``extras``) and ``extra_roots``."""
    environment = default_environment()
    found = {}

    def visit(name, wanted_extras):
        key = normalized(name)
        try:
            dist = md.distribution(name)
        except md.PackageNotFoundError:
            return
        if key in found:
            return
        found[key] = dist
        for text in dist.requires or []:
            requirement = Requirement(text)
            if requirement.marker is not None and not any(
                requirement.marker.evaluate({**environment, "extra": extra})
                for extra in ("", *wanted_extras)
            ):
                continue
            visit(requirement.name, tuple(requirement.extras))

    visit(root, tuple(extras))
    for name in extra_roots:
        visit(name, ())
    found.pop(normalized(root), None)
    return [found[key] for key in sorted(found)]


def metadata_license_files(dist):
    """License files in the package metadata.

    Everything under ``*.dist-info/licenses/`` is a license file (PEP 639),
    including bundled libraries' texts such as pikepdf's
    ``third-party-licenses/qpdf.txt``; elsewhere in the metadata folder only
    files named like LICENSE/COPYING/NOTICE count.
    """
    files = []
    for entry in dist.files or []:
        text = str(entry).replace("\\", "/")
        if ".dist-info/" not in text:
            continue
        inside = text.split(".dist-info/", 1)[1]
        path = Path(text)
        if inside.startswith("licenses/") or (
            LICENSE_FILE.search(path.name) and path.suffix.lower() in TEXT_SUFFIXES
        ):
            files.append(entry)
    return files


def copy_standard(names, target):
    copied = []
    target.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copyfile(STANDARD / name, target / name)
        copied.append(target / name)
    return copied


def fallback_for(expression):
    for key, files in FALLBACK.items():
        if key in expression:
            return files
    return []


def collect_python(out, extra_roots):
    rows = []
    for dist in runtime_distributions(extra_roots=extra_roots):
        name, version = dist.metadata["Name"], dist.version
        expression = license_of(dist)
        target = out / "python" / f"{name}-{version}"
        copied = []
        for entry in metadata_license_files(dist):
            inside = str(entry).replace("\\", "/").split(".dist-info/", 1)[1]
            inside = inside.removeprefix("licenses/")
            destination = target / inside
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(dist.locate_file(entry), destination)
            copied.append(destination)
        note = ""
        if not copied:
            names = fallback_for(expression)
            copied = copy_standard(names, target)
            if copied:
                note = "패키지에 라이선스 파일이 없어 표준 문서를 넣음"
            else:
                note = (
                    "**라이선스 문서 없음.** 패키지가 문서를 넣지 않았습니다. "
                    f"원문: https://pypi.org/project/{name}/{version}/"
                )
        rows.append(dict(name=name, version=version, license=expression, files=copied, note=note))
    return rows


def collect_runtime(out):
    base = Path(sys.base_prefix)
    candidates = [
        base / "LICENSE.txt",
        base / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "LICENSE.txt",
    ]
    target = out / "python-runtime"
    for candidate in candidates:
        if candidate.is_file():
            target.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, target / "LICENSE.txt")
            return dict(
                name="Python",
                version=sys.version.split()[0],
                license="PSF-2.0",
                files=[target / "LICENSE.txt"],
                note="",
            )
    return dict(
        name="Python",
        version=sys.version.split()[0],
        license="PSF-2.0",
        files=[],
        note="**라이선스 문서 없음.** 원문: https://docs.python.org/3/license.html",
    )


def tool_version(executable, args):
    try:
        result = subprocess.run(
            [str(executable), *args], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return "(확인 못 함)"
    lines = (result.stdout + result.stderr).strip().splitlines()
    return lines[0].strip() if lines else "(확인 못 함)"


def collect_tool(out, name, executable, search):
    info = TOOLS[name]
    executable = Path(executable)
    target = out / name
    roots = [executable.parent]
    for base in map(Path, search):
        if not base.is_dir():
            continue
        for folder in sorted(base.iterdir()):
            label = folder.name.lower()
            # Release folders: "qpdf-12.x-msvc64", poppler-windows "Release-24.x".
            if folder.is_dir() and (
                name in label or (name == "poppler" and label.startswith("release-"))
            ):
                roots.append(folder)
    copied, sources = [], []
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or not LICENSE_FILE.search(path.name):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            relative = path.relative_to(root)
            destination = target / "package" / root.name / relative
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            copied.append(destination)
        if root != executable.parent:
            sources.append(root.name)
    copied += copy_standard(info["standard"], target)
    version = tool_version(executable, info["version_args"]) if executable.is_file() else "(없음)"
    return dict(
        name=info["title"],
        version=version,
        license=info["license"],
        files=copied,
        note=("받은 파일: " + ", ".join(sources)) if sources else "",
        home=info["home"],
        build=info.get("build"),
    )


def write_readme(out, rows):
    lines = [
        "# 서드파티 라이선스",
        "",
        "퀵 임포징 배포본에 함께 들어 있는 다른 프로젝트의 구성 요소와 라이선스입니다.",
        "퀵 임포징 자체의 라이선스는 상위 폴더의 `LICENSE.txt`(MIT)입니다.",
        "",
        "| 구성 요소 | 버전 | 라이선스 | 라이선스 문서 | 비고 |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        files = "<br>".join(f"`{f.relative_to(out).as_posix()}`" for f in row["files"])
        lines.append(
            f"| {row['name']} | {row['version']} | {row['license']} | {files} | {row['note']} |"
        )
    lines += [
        "",
        "## Poppler 소스 코드",
        "",
        "`bin\\poppler`의 Poppler 실행 파일과 함께 들어 있는 라이브러리는 GPL 등 각자의 라이선스를 따릅니다.",
        "이 배포본은 Poppler를 고치지 않고, 아래 Windows 빌드의 배포 파일을 그대로 넣었습니다.",
        "",
        "- Poppler 소스: https://poppler.freedesktop.org/",
        "- Windows 빌드(사용한 버전은 위 표의 \"받은 파일\", 빌드 방법과 포함 라이브러리 목록): "
        "https://github.com/oschwartz10612/poppler-windows",
        "- 이 배포본에 든 버전의 소스가 필요하면 https://github.com/steves460ng/quick-imposing/issues 로 요청하세요.",
        "",
        "## Qt (PySide6)",
        "",
        "Qt와 PySide6는 LGPL-3.0으로 사용합니다. Qt 라이브러리는 배포 폴더의 `_internal` 안에 별도 파일로 들어 있어,",
        "같은 버전과 호환되는 다른 빌드로 바꿔 쓸 수 있습니다. 소스: https://code.qt.io/ , https://download.qt.io/",
        "Qt 안에 포함된 다른 라이브러리의 라이선스: https://doc.qt.io/qt-6/licenses-used-in-qt.html",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tool", action="append", default=[], help="NAME=EXECUTABLE")
    parser.add_argument("--search", action="append", default=[], type=Path)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit with code 1 when a component has no license text",
    )
    args = parser.parse_args(argv)
    # Korean names must not stop a build whose console is not UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    out = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    rows = collect_python(out, extra_roots=("pyinstaller",))
    rows.append(collect_runtime(out))
    for item in args.tool:
        name, _, executable = item.partition("=")
        if name not in TOOLS:
            parser.error(f"unknown tool: {name}")
        rows.append(collect_tool(out, name, executable, args.search))
    write_readme(out, rows)
    missing = [row["name"] for row in rows if not row["files"]]
    for row in rows:
        print(f"  {row['name']} {row['version']}: {row['license']} ({len(row['files'])} files)")
    if missing:
        print(
            "WARNING: license text missing for: " + ", ".join(missing)
            + " (marked in THIRD-PARTY-LICENSES/README.md)"
        )  # stdout: Windows PowerShell may treat a native command's stderr as an error
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
