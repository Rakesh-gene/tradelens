"""Run the backend test suite without requiring the external pytest package."""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("paths", nargs="*")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    target = Path(args.paths[0]).resolve() if args.paths else Path.cwd()
    loader = unittest.defaultTestLoader
    if target.is_file():
        suite = loader.discover(
            start_dir=str(target.parent),
            pattern=target.name,
        )
    else:
        suite = loader.discover(start_dir=str(target))

    verbosity = 0 if args.quiet else 2 if args.verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
