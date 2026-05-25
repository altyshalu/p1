from __future__ import annotations

import argparse
import webbrowser


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open the L2 <-> L3 web cockpit.")
    parser.add_argument("--api-url", default="http://localhost:8080")
    parser.add_argument("--no-open", action="store_true", help="Print the cockpit URL without opening a browser.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    url = f"{args.api_url.rstrip('/')}/cockpit"
    print(url)
    if not args.no_open:
        webbrowser.open(url)
