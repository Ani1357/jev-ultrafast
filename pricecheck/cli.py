"""uv run pricecheck "Nutrilon 3" [--shops ah,jumbo] — calls TypeSafe and the text model for every shop."""

import argparse
import json
import re
from pathlib import Path

from jev_ultrafast.demo import load_environment

from .compare import compare, table
from .shops import BY_KEY, SHOPS


def main():
    parser = argparse.ArgumentParser(description="Compare a product's price across Dutch shops.")
    parser.add_argument("product")
    parser.add_argument("--shops", help="Comma-separated keys: " + ",".join(s["key"] for s in SHOPS))
    parser.add_argument("--parallel", type=int, default=3)
    parser.add_argument("--max-actions", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=90, help="Seconds per shop before extraction")
    parser.add_argument("--output", help="Folder for report.json (default artifacts/pricecheck/<product>)")
    args = parser.parse_args()
    product = args.product.strip()
    if not product or len(product) > 120:
        parser.error("Enter a product name of 1–120 characters")
    try:
        shops = [BY_KEY[k.strip()] for k in args.shops.split(",")] if args.shops else SHOPS
    except KeyError as error:
        parser.error(f"Unknown shop {error}")
    load_environment()

    def progress(update):
        print(f"  {update['name']:<13} {update['agent_status']:<10} {update['actions']} actions", flush=True)

    report = compare(product, shops, parallel=args.parallel, max_actions=args.max_actions, timeout=args.timeout,
                     on_update=progress)
    folder = Path(args.output or Path("artifacts/pricecheck") / (re.sub(r"[^a-z0-9]+", "-", product.lower()) or "x"))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print()
    print(table(report))
    for r in report["results"]:
        if r.get("note"):
            print(f"  {r['name']}: {r['note']}")
    print(f"\nReport: {folder / 'report.json'}")


if __name__ == "__main__":
    main()
