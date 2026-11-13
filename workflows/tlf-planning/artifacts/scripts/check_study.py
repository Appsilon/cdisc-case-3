"""Deterministic gate: is the delivered SDTM the study the USDM describes?

Compares the staged SDTM facts (DM / EX / TS / TA, sdtm-study-facts.json) with
the USDM (studycheck.check_study). A 'fail' stops the run before any planning:
no agent can fix data that belongs to another study, and CORE will not notice.
'warn' lines are shown on the plan review page. A planning run with no SDTM at
all (planning before data exists) passes with a warning. Writes study-check.json (the
planner and the plan page read it) and study-check.html to /output.

Result: { failed, checks, counts, summary }
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import OUTPUT_DIR, run_main, write_result  # noqa: E402
from planlib import INPUTS_DIR, STUDY_CHECK_PATH  # noqa: E402
from studycheck import check_study  # noqa: E402

STYLE = """
:root { color-scheme: light dark; --fg:#1d2433; --muted:#5b6475; --line:#d9dee7; --bg:#fff; --pass:#1a7f37; --warn:#9a5b00; --fail:#c62828; }
html.dark { --fg:#e6e9ef; --muted:#9aa3b2; --line:#333a47; --bg:#14171d; --pass:#4ac26b; --warn:#e0a24a; --fail:#ff6b6b; }
body { font: 14px/1.45 system-ui, sans-serif; color: var(--fg); background: var(--bg); margin: 16px; }
h1 { font-size: 18px; margin: 0 0 8px; } table { border-collapse: collapse; width: 100%; }
th, td { border-bottom: 1px solid var(--line); padding: 5px 8px; text-align: left; vertical-align: top; } th { color: var(--muted); }
.pass { color: var(--pass); font-weight: 600; } .warn { color: var(--warn); font-weight: 600; } .fail { color: var(--fail); font-weight: 600; }
"""


def render_rows(checks: list[dict]) -> str:
    return "".join(
        f"<tr><td>{html.escape(item['check'])}</td><td class='{item['status']}'>{item['status'].upper()}</td>"
        f"<td>{html.escape(item['detail'])}</td></tr>" for item in checks)


def render(result: dict) -> str:
    verdict = "FAIL - the SDTM does not match the protocol" if result["failed"] else "PASS"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Data checks</title><style>{STYLE}</style></head><body>
<h1>Data checks: SDTM vs protocol (USDM) - <span class="{'fail' if result['failed'] else 'pass'}">{verdict}</span></h1>
<table><tr><th>Check</th><th>Result</th><th>Detail</th></tr>{render_rows(result['checks'])}</table>
</body></html>"""


def main() -> None:
    usdm = json.loads((INPUTS_DIR / "usdm.json").read_text(encoding="utf-8"))
    facts_path = INPUTS_DIR / "sdtm-study-facts.json"
    staged = json.loads(facts_path.read_text(encoding="utf-8")) if facts_path.is_file() else {}
    result = check_study(usdm, staged.get("facts") or {}, sdtm_delivered=int(staged.get("sdtmFiles") or 0) > 0)
    STUDY_CHECK_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "study-check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "study-check.html").write_text(render(result), encoding="utf-8")
    failures = [f"{item['check']}: {item['detail']}" for item in result["checks"] if item["status"] == "fail"]
    warnings = [item for item in result["checks"] if item["status"] == "warn"]
    summary = (f"Data check FAILED - the SDTM is not the study the USDM describes: {' | '.join(failures)}" if failures
               else f"Data check passed ({len(result['checks'])} checks, {len(warnings)} warning(s)): "
                    + "; ".join(item["detail"] for item in result["checks"] if item["check"] in ("arms", "enrollment")))
    write_result({**result, "summary": summary})


if __name__ == "__main__":
    run_main(main)
