"""The extraction agent's own gate run: the same checks as check-usdm, no attempt used.

  python3 /artifacts/scripts/self_check.py    -> PASS, or the problems to fix
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from usdmlib import check_usdm  # noqa: E402


def main() -> None:
    result = check_usdm()
    if result["problems"]:
        print(f"FAIL: {len(result['problems'])} problem(s)")
        for problem in result["problems"]:
            print(f"  - {problem}")
        sys.exit(1)
    print(f"PASS {result['counts']}")


if __name__ == "__main__":
    main()
