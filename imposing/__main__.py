import argparse
import json
from pathlib import Path
from .engine import create_template, generate


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
    args = parser.parse_args()
    try:
        if args.command == "create-template":
            definition = json.loads(args.definition.read_text(encoding="utf-8"))
            # Fixture envelopes hold source provenance outside the versioned definition.
            print(
                create_template(
                    definition.get("template", definition),
                    args.base,
                    args.templates_root,
                )
            )
            return 0
        report = generate(args.project, args.templates_root, args.output, args.font_dir)
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
