"""Build a local catalog and match the saved inputs without a server."""
import argparse
from datetime import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description="Match colors to documented fired glaze combinations")
    parser.add_argument("command", nargs="?", choices=("match", "index"), default="match")
    parser.add_argument("--inputs", default=str(ROOT / "inputs.txt"))
    parser.add_argument("--catalog", default=str(ROOT / "outputs/catalog"))
    parser.add_argument("--output", help="Fresh report folder; default outputs/match-TIMESTAMP")
    args = parser.parse_args()
    try:
        from .config import read_inputs
        input_bytes = Path(args.inputs).read_bytes()
        inputs = read_inputs(args.inputs, require_target=args.command == "match", contents=input_bytes)
        output = Path(args.output) if args.output else ROOT / "outputs" / datetime.now().strftime("match-%Y%m%d-%H%M%S-%f")
        if args.command == "match" and output.exists() and any(output.iterdir()):
            raise ValueError("Result output folder is not empty; choose a fresh --output folder")
        from .catalog import build_catalog
        catalog = build_catalog(inputs["combination_zip_path"], args.catalog, lambda s: print(s, flush=True))
        if args.command == "index":
            print(f"Catalog ready: {Path(args.catalog).resolve() / 'catalog.json'}")
            return
        from .matcher import match
        from .report import write_report
        result = match(catalog, inputs)
        write_report(result, args.catalog, output, args.inputs, input_bytes)
        print(f"Found {len(result['matches'])} matches; report: {output.resolve() / 'report.html'}")
        print("Peak temperature, dry thickness and full schedules are recorded, not predicted from these charts.")
    except (ValueError, OSError, ImportError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
