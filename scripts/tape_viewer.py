#!/usr/bin/env python3
"""
Simple viewer for SDK JSONL tape files.

Usage:
  python scripts/tape_viewer.py tapes/sdk_*.tape --tail 5
  python scripts/tape_viewer.py tapes/sdk_*.tape --contains error
"""

import argparse
import json
from pathlib import Path


def load_lines(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="View SDK tape JSONL files")
    parser.add_argument("tape", type=str, help="Path to .tape JSONL file")
    parser.add_argument("--tail", type=int, default=10, help="Show last N records")
    parser.add_argument("--contains", type=str, default=None, help="Filter by substring")
    args = parser.parse_args()

    path = Path(args.tape)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    records = load_lines(path)
    if args.contains:
        needle = args.contains.lower()
        records = [r for r in records if needle in json.dumps(r).lower()]

    if args.tail > 0:
        records = records[-args.tail :]

    for rec in records:
        print(json.dumps(rec, indent=2, ensure_ascii=False))
        print("-" * 60)


if __name__ == "__main__":
    main()
