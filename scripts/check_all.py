#!/usr/bin/env python3
"""Run every pre-deploy gate and report one combined result.

One command to remember instead of several. Each gate answers a different
question about the exported catalog:

  check_completeness.py  — is everything THERE?     (known titles, no duplicates)
  check_data_quality.py  — are the VALUES sane?     (readable text, live references)

Every gate runs even if an earlier one fails: seeing all the problems at once
beats fixing them one deploy at a time. Exits non-zero if any gate failed.

Usage:  python3 scripts/check_all.py
"""
import subprocess
import sys
from pathlib import Path

GATES = ["check_completeness.py", "check_data_quality.py"]


def main() -> int:
    here = Path(__file__).parent
    failed = []

    for gate in GATES:
        print(f"\n{'=' * 60}\n{gate}\n{'=' * 60}")
        result = subprocess.run([sys.executable, str(here / gate)])
        if result.returncode != 0:
            failed.append(gate)

    print(f"\n{'=' * 60}")
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print(f"ALL GATES PASSED ({len(GATES)}/{len(GATES)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
