"""PDF primitives shared by production generation and structural inspection."""

import hashlib
from pathlib import Path
import shutil
import subprocess

import pikepdf as p
from PIL import Image

MM = 72 / 25.4


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def streams(page):
    obj = page.obj if isinstance(page, p.Page) else page
    value = obj.get("/Contents", p.Array())
    return list(value) if isinstance(value, p.Array) else [value]


def canonical(obj):
    if isinstance(obj, p.Stream):
        return [
            canonical(obj.stream_dict),
            hashlib.sha256(obj.read_raw_bytes()).hexdigest(),
        ]
    if isinstance(obj, p.Dictionary):
        return {k: canonical(v) for k, v in obj.items() if k != "/Length"}
    if isinstance(obj, p.Array):
        return [canonical(v) for v in obj]
    return str(obj)


def remove_illustrator(pdf):
    removed = []
    for label, obj in [
        ("catalog", pdf.Root),
        *[(f"page-{i + 1}", pg.obj) for i, pg in enumerate(pdf.pages)],
    ]:
        info = obj.get("/PieceInfo")
        if isinstance(info, p.Dictionary) and "/Illustrator" in info:
            del info["/Illustrator"]
            removed.append(label)
            if not len(info):
                del obj["/PieceInfo"]
    return removed


def save(pdf, path):
    pdf.save(
        path, compress_streams=False, object_stream_mode=p.ObjectStreamMode.preserve
    )


def invoke(name, *args, cwd=None, input=None, binary=False, accept=(0,)):
    executable = shutil.which(name)
    if not executable:
        raise RuntimeError(f"Required executable not on PATH: {name}")
    result = subprocess.run(
        [executable, *map(str, args)],
        capture_output=True,
        text=not binary,
        cwd=cwd,
        input=input,
        # A windowed Windows program must not flash a console per tool call.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode not in accept:
        raise RuntimeError(f"{name}: {result.stdout}{result.stderr}")
    if len(accept) > 1:
        return result
    return result.stdout


def check(path):
    """Run ``qpdf --check``; return its warning lines, raise on errors.

    qpdf exits with 0 (clean), 3 (warnings only) or 2 (errors). Warnings do
    not fail a build: qpdf 12 warns about deflate streams of Illustrator/Quark
    base files, which are kept byte for byte (SPEC R3) and so reappear in the
    result. The command runs in the file's folder so only its name is passed.
    """
    path = Path(path)
    result = invoke("qpdf", "--check", path.name, cwd=path.parent, accept=(0, 3))
    if result.returncode == 0:
        return []
    lines = f"{result.stdout}\n{result.stderr}".splitlines()
    return [line.strip() for line in lines if line.startswith("WARNING")]


def render(path, target, dpi=150):
    path, target = Path(path), Path(target)
    if path.parent == target.parent:
        # Staged files have ASCII names; running inside their folder keeps
        # non-ASCII output folders out of the tool's command line.
        invoke(
            "pdftoppm", "-singlefile", "-r", dpi, "-png", path.name, target.name,
            cwd=path.parent,
        )
    else:
        invoke("pdftoppm", "-singlefile", "-r", dpi, "-png", path, target)
    with Image.open(str(target) + ".png") as image:
        return image.convert("RGB")


def render_bytes(data, dpi):
    """Render page 1 of in-memory PDF bytes to PNG bytes (no file paths)."""
    return invoke(
        "pdftoppm", "-singlefile", "-r", dpi, "-png", "-", input=data, binary=True
    )
