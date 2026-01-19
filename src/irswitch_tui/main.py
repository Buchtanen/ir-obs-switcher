"""Entry point for the TUI client."""
from __future__ import annotations

import argparse
import asyncio
import sys

from irswitch_tui.client import AsyncClient
from irswitch_tui.ui import SwitcherTUI


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(description="iRacing OBS switcher TUI")
    parser.add_argument("--url", required=True, help="Core service base URL")
    return parser


def main() -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Validate URL
    if not args.url.startswith(("http://", "https://")):
        print("Error: URL must start with http:// or https://", file=sys.stderr)
        return 1

    try:
        client = AsyncClient(args.url)
        app = SwitcherTUI(client)
        app.run()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
