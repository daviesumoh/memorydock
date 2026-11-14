"""Reject commit messages and PR bodies that carry tool attribution.

Usage: check_attribution.py <file>   (or "-" for stdin)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ATTRIBUTION = re.compile(
    r"(?i)co-authored-by|generated with|\U0001F916|noreply@anthropic|ai-generated"
    r"|written by (an )?ai"
)


def offending_lines(text: str) -> list[int]:
    lines = text.splitlines()
    # git strips "#" lines from commit messages after the hook runs, so they never land.
    return [
        n
        for n, line in enumerate(lines, start=1)
        if not line.startswith("#") and ATTRIBUTION.search(line)
    ]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_attribution.py <file|->", file=sys.stderr)
        return 2
    text = sys.stdin.read() if argv[1] == "-" else Path(argv[1]).read_text(encoding="utf-8")
    bad = offending_lines(text)
    for n in bad:
        print(f"line {n}: attribution marker", file=sys.stderr)
    if bad:
        print("Remove tool attribution from the message.", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
