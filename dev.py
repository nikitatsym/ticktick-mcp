#!/usr/bin/env python3
"""Single entry point for tests + linters. See specs/general/dev-script.md."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _run(cmd: list[str]) -> int:
    print(f":: {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


def lint() -> int:
    rc = _run(["uv", "run", "ruff", "check"])
    if rc:
        return rc
    return _run(["uv", "run", "mypy"])


def test() -> int:
    return _run(["uv", "run", "pytest"])


def install_hook() -> int:
    """Point git at the repo's tracked pre-commit hook. Idempotent."""
    if (ROOT / ".githooks" / "pre-commit").exists():
        return _run(["git", "config", "core.hooksPath", ".githooks"])
    print("no tracked hook: expected .githooks/pre-commit", file=sys.stderr)
    return 1


def _hook_ready() -> bool:
    if (ROOT / ".git" / "hooks" / "pre-commit").exists():
        return True
    configured = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return bool(configured) and (ROOT / configured / "pre-commit").exists()


def _hook_hint() -> None:
    # A fresh clone gates nothing until asked; CI has no use for a hook.
    if not os.environ.get("CI") and not _hook_ready():
        print("hint: `python dev.py hook` installs the pre-commit gate", file=sys.stderr)


def check() -> int:
    _hook_hint()
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
    if cmd == "hook":
        return install_hook()
    print("usage: dev.py {test|lint|check|hook}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
