"""The planner agent's own gate run: the same checks as check-plan, no attempt used.

  python3 /artifacts/scripts/self_check.py    -> PASS, or the problems to fix
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from planlib import check_plan, staged_primary_endpoints  # noqa: E402


def main() -> None:
    result = check_plan(primary=staged_primary_endpoints())
    blocked_primary = result["counts"].get("blockedPrimary") or []
    if blocked_primary:
        print(f"WARNING: primary endpoint(s) {', '.join(blocked_primary)} have no planned output. The run STOPS on this "
              "(the data cannot answer the primary question). Re-check sdtm-inventory.json - keep them blocked only when the "
              "instrument truly is not in the delivered SDTM.")
    if result["problems"]:
        print(f"FAIL: {len(result['problems'])} problem(s)")
        for problem in result["problems"]:
            print(f"  - {problem}")
        sys.exit(1)
    print(f"PASS {result['counts']}")


if __name__ == "__main__":
    main()
