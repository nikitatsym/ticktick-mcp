#!/usr/bin/env python3
"""Single entry point for tests + linters. See specs/general/dev-script.md."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _run(cmd: list[str]) -> int:
    print(f":: {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=ROOT).returncode


def lint() -> int:
    rc = _run(["uv", "run", "ruff", "check"])
    if rc:
        return rc
    return _run(["uv", "run", "mypy"])


def test() -> int:
    return _run(["uv", "run", "pytest"])


def check() -> int:
    rc = lint()
    if rc:
        return rc
    return test()


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "lint":
        return lint()
    if cmd == "test":
        return test()
    if cmd == "check":
        return check()
    print("usage: dev.py {test|lint|check}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
