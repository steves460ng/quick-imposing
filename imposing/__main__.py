import argparse
import json
from pathlib import Path
from .engine import create_template, generate
from .autofill import autofill


def main():
    parser = argparse.ArgumentParser(
        description="Template@2 / project@1 PDF imposition"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-template")
    create.add_argument("definition", type=Path)
    create.add_argument("--base", type=Path, required=True)
    create.add_argument("--templates-root", type=Path, required=True)
    build = commands.add_parser("build")
    build.add_argument("project", type=Path)
    build.add_argument("--templates-root", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--font-dir", action="append", default=[])
    build.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing output files, only if the build passes",
    )
    fill = commands.add_parser("autofill", help="Append files to a new project copy")
    source = fill.add_mutually_exclusive_group(required=True)
    source.add_argument("--project", type=Path)
    source.add_argument("--template")
    fill.add_argument("--templates-root", type=Path, required=True)
    fill.add_argument("--start-cell", type=int, required=True)
    fill.add_argument("--files", nargs="*", type=Path, default=[])
    fill.add_argument("--output", type=Path, required=True)
    fill.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "create-template":
            definition = json.loads(args.definition.read_text(encoding="utf-8"))
            print(
                create_template(
                    definition,
                    args.base,
                    args.templates_root,
                )
            )
            return 0
        if args.command == "autofill":
            report = autofill(
                templates_root=args.templates_root,
                start_cell=args.start_cell,
                files=args.files,
                output=args.output,
                project=args.project,
                template=args.template,
                report_path=args.report,
            )
        else:
            report = generate(
                args.project,
                args.templates_root,
                args.output,
                args.font_dir,
                overwrite=args.overwrite,
            )
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "errors": report["errors"],
                    "warnings": report["warnings"],
                },
                ensure_ascii=False,
            )
        )
        return 0 if report["status"] == "PASS" else 1
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
