"""Verify every exact version declared in the generated requirements lock."""

from __future__ import annotations

import importlib.metadata
import re
import sys
from pathlib import Path


LOCK_ENTRY = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\;]+)(?:\s|\\|$)")


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_lock(path: Path) -> dict[str, tuple[str, str]]:
    expected: dict[str, tuple[str, str]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = LOCK_ENTRY.match(line)
        if not match:
            continue
        display_name, version = match.groups()
        key = canonical_name(display_name)
        if key in expected:
            raise ValueError(f"duplicate lock entry at line {line_number}: {display_name}")
        expected[key] = (display_name, version)
    if not expected:
        raise ValueError("dependency lock contains no exact package entries")
    return expected


def verify(path: Path) -> list[str]:
    failures: list[str] = []
    for _key, (name, expected_version) in sorted(parse_lock(path).items()):
        try:
            actual_version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            failures.append(f"{name}: missing (expected {expected_version})")
            continue
        if actual_version != expected_version:
            failures.append(f"{name}: installed {actual_version}, expected {expected_version}")
    return failures


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: verify_dependency_lock.py REQUIREMENTS_LOCK", file=sys.stderr)
        return 2
    lock_path = Path(args[0]).resolve()
    try:
        expected_count = len(parse_lock(lock_path))
        failures = verify(lock_path)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"dependency lock verification error: {error}", file=sys.stderr)
        return 2
    if failures:
        for failure in failures:
            print(f"LOCK_MISMATCH {failure}", file=sys.stderr)
        return 1
    print(f"Verified all {expected_count} locked dependency versions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
