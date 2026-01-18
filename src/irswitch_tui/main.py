"""Entry point for the TUI client."""
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="iRacing OBS switcher TUI")
    parser.add_argument("--url", required=True, help="Core service base URL")
    return parser


def main() -> int:
    parser = build_parser()
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
