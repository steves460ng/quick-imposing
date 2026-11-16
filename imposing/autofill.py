"""Edit project@1 assignments without rendering or reading test expectations."""

import copy
import json
import os
from pathlib import Path
import re

from .model import PathError, project_errors, relative_file, template_errors


def absolute(path):
    """Keep the selected filename (including symlink names) for sorting."""
    return Path(os.path.abspath(path))


def natural_file_key(path):
    path = absolute(path)
    # Splitting preserves alternating text/number positions, including empty
    # leading text, so mixed names never require comparing an int with a str.
    chunks = re.split(r"(\d+)", path.name)
    key = tuple(
        int(part) if i % 2 else part.casefold() for i, part in enumerate(chunks)
    )
    return key, str(path)


def fill_sequence(count, direction):
    columns, rows = count
    for row in range(rows):
        cols = range(columns) if direction == "forward" else range(columns - 1, -1, -1)
        for col in cols:
            yield row * columns + col + 1


def plan_fill(count, direction, occupied, start_cell, wanted):
    """Return (cells, reason, blocked_cell) for filling up to ``wanted`` cells.

    Filling starts at ``start_cell`` and follows the template direction. It
    stops in front of an occupied cell ("occupied") or after the last cell
    ("end_of_cells"); ``reason`` is None when every file found a cell.
    """
    sequence = iter(fill_sequence(count, direction))
    for cell in sequence:
        if cell == start_cell:
            break
    else:
        raise ValueError(f"Start cell is not in the template: {start_cell}")
    assigned = []
    while len(assigned) < wanted:
        if cell is None:
            return assigned, "end_of_cells", None
        if cell in occupied:
            return assigned, "occupied", cell
        assigned.append(cell)
        cell = next(sequence, None)
    return assigned, None, None


def autofill(
    *,
    templates_root,
    start_cell,
    files,
    output,
    project=None,
    template=None,
    report_path=None,
):
    """Append assignments, rebase paths, and save a new project and report.

    New input paths are relative to the caller's working directory. Existing
    placements remain relative to the input project until the final rebase.
    A blockage is a successful partial edit; input errors write only a report.
    """
    output = absolute(output)
    report_path = (
        absolute(report_path)
        if report_path is not None
        else output.with_suffix(".autofill.json")
    )
    if report_path.resolve() == output.resolve():
        raise ValueError("Report and project must have different paths")
    # Exclusive writes protect existing files and symlinks, even on errors.
    if report_path.exists() or report_path.is_symlink():
        raise FileExistsError(f"Report already exists: {report_path}")
    result = dict(
        status="FAIL",
        template=template,
        fill_direction=None,
        start_cell=start_cell,
        sorted_files=[],
        added=[],
        unplaced_files=[],
        warnings=[],
        errors=[],
    )

    def error(code, reason, **context):
        result["errors"].append(dict(code=code, reason=reason, **context))

    def finish():
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        return result

    def schema_errors(errors):
        for entry in errors:
            error(
                entry["code"], f"Invalid field: {entry['field']}", field=entry["field"]
            )

    if output.exists() or output.is_symlink():
        error("SCHEMA_INVALID", f"Output project already exists: {output}")
        return finish()
    if (project is None) == (template is None):
        error("SCHEMA_INVALID", "Specify exactly one input project or template name")
        return finish()
    input_project = absolute(project) if project is not None else None
    if input_project is not None:
        try:
            data = json.loads(input_project.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            error("SCHEMA_INVALID", str(exc))
            return finish()
    else:
        data = dict(
            schema="quick-imposing/project@1",
            template=template,
            texts={},
            placements=[],
        )
    schema_errors(project_errors(data))
    if result["errors"]:
        return finish()
    result["template"] = data["template"]
    folder = absolute(templates_root) / data["template"]
    try:
        definition = json.loads((folder / "template.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        error("TEMPLATE_NOT_FOUND", f"Template not found: {data['template']}")
        return finish()
    except (OSError, ValueError) as exc:
        error("SCHEMA_INVALID", str(exc))
        return finish()
    schema_errors(template_errors(definition, folder.name))
    if result["errors"]:
        return finish()
    result["fill_direction"] = definition["fill_direction"]
    columns, rows = definition["grid"]["count"]
    if type(start_cell) != int or not 1 <= start_cell <= columns * rows:
        error(
            "CELL_NOT_IN_TEMPLATE",
            f"Start cell is not in the current template: {start_cell}",
            cell=start_cell,
        )
    for item in data["placements"]:
        if item["cell"] > columns * rows:
            error(
                "CELL_NOT_IN_TEMPLATE",
                f"Existing cell is not in the current template: {item['cell']}",
                cell=item["cell"],
            )
    if not isinstance(files, (list, tuple)) or not files:
        error("SCHEMA_INVALID", "Select at least one B file")
        selected = []
    else:
        selected = []
        for file in files:
            if not isinstance(file, (str, os.PathLike)) or not str(file):
                error("SCHEMA_INVALID", "Each B file must be a nonempty path")
                continue
            path = absolute(file)
            if not path.is_file():
                error(
                    "SCHEMA_INVALID",
                    f"B file does not exist or is not a file: {path}",
                    file=str(path),
                )
            selected.append(path)
    selected.sort(key=natural_file_key)
    result["sorted_files"] = [str(path) for path in selected]
    result["unplaced_files"] = list(result["sorted_files"])
    if result["errors"]:
        return finish()
    revised = copy.deepcopy(data)
    try:
        # Only path spellings change: each old cell/order still refers to the
        # same B target, including missing files that continue to occupy cells.
        for item in revised["placements"]:
            old_file = absolute(input_project.parent / item["file"])
            item["file"] = relative_file(old_file, output.parent)
        rebased = [relative_file(path, output.parent) for path in selected]
    except PathError as exc:
        error(exc.code, str(exc))
        return finish()
    occupied = {item["cell"] for item in data["placements"]}
    next_order = max((item["order"] for item in data["placements"]), default=0) + 1
    assigned, reason, blocked_cell = plan_fill(
        definition["grid"]["count"],
        definition["fill_direction"],
        occupied,
        start_cell,
        len(selected),
    )
    for cell, relative in zip(assigned, rebased):
        added = dict(cell=cell, file=relative, order=next_order)
        revised["placements"].append(added)
        result["added"].append(copy.deepcopy(added))
        next_order += 1
    if reason:
        result["warnings"].append(
            dict(
                code="AUTOFILL_BLOCKED",
                reason=reason,
                blocked_cell=blocked_cell,
                unplaced_files=[str(p) for p in selected[len(assigned) :]],
            )
        )
    result["unplaced_files"] = [str(path) for path in selected[len(result["added"]) :]]
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as stream:
            json.dump(revised, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except OSError as exc:
        error("SCHEMA_INVALID", str(exc))
        return finish()
    result["status"] = "PASS"
    return finish()
