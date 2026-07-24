"""Run the local quality checks required before committing."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run(command: list[str]) -> None:
    print(f"$ {' '.join(command)}")
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def main() -> int:
    uv = ["uv"]
    run([*uv, "lock", "--check"])
    run(["npm", "exec", "--no", "--", "prettier", "--check", "."])
    run(["npm", "exec", "--no", "--", "taplo", "format", "--check"])
    run([*uv, "run", "pyright"])
    run([sys.executable, "-m", "ruff", "format", "--check", "."])
    run([sys.executable, "-m", "ruff", "check", "."])
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=tact_downloader",
            "--cov=main",
            "--cov-branch",
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
