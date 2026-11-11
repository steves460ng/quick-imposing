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


def invoke(name, *args):
    executable = shutil.which(name)
    if not executable:
        raise RuntimeError(f"Required executable not on PATH: {name}")
    result = subprocess.run(
        [executable, *map(str, args)], capture_output=True, text=True
    )
    if result.returncode:
        raise RuntimeError(f"{name}: {result.stdout}{result.stderr}")
    return result.stdout


def render(path, target, dpi=150):
    invoke("pdftoppm", "-singlefile", "-r", dpi, "-png", path, target)
    with Image.open(str(target) + ".png") as image:
        return image.convert("RGB")
