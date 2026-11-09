import argparse
import json
from .config import read_settings


def main():
    parser = argparse.ArgumentParser(description="Local vase stress analysis; VTU first, then colored GLB")
    commands = parser.add_subparsers(dest="command", required=True)
    analysis = commands.add_parser("run")
    analysis.add_argument("--model", required=True)
    analysis.add_argument("--settings", default="examples/settings.txt",
                          help="Editable settings file (default: examples/settings.txt)")
    analysis.add_argument("--output", required=True)
    conversion = commands.add_parser("convert")
    conversion.add_argument("--settings", default="examples/settings.txt")
    conversion.add_argument("--vtu", required=True)
    conversion.add_argument("--glb", required=True)
    args = parser.parse_args()
    try:
        if args.command == "run":
            settings = read_settings(args.settings)
            from .pipeline import run
            print(json.dumps(run(args.model, settings, args.output), indent=2))
        else:
            from .pipeline import convert
            from pathlib import Path
            if Path(args.glb).exists():
                raise ValueError("GLB output already exists")
            print(f"Maximum stress: {convert(args.vtu, args.glb, read_settings(args.settings).log_range_decades):.6g} Pa")
    except (ValueError, OSError, ImportError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
