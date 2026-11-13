"""Turn the CORE findings the standards reviewer marked `fix` into a change request for the extraction agent.

Reads the files route-core lifted (core-report.json, core-dispositions-usdm.json,
downloaded with localPath). Only this round's `fix` dispositions count. Writes
core-feedback.json - per rule the message, the reviewer's note and the flagged
instances (id, JSON path, values) - and appends a request to review-feedback.jsonl
that points at it, with fresh gate attempts.

Result: { iteration, rules, comment, summary }
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, read_input, run_main, verify_files, write_result  # noqa: E402
from usdmlib import LOOP, WORK_DIR  # noqa: E402

CORE_FEEDBACK = WORK_DIR / "core-feedback.json"
INSTANCES_PER_RULE = 25


def local_json(files: list[dict], prefix: str) -> tuple[dict, dict]:
    matches = [entry for entry in files if str(entry.get("name", "")).startswith(prefix)]
    if not matches:
        raise StepFailure(f"route-core handed on no {prefix}* file.")
    return matches[0], json.loads(Path(matches[0]["localPath"]).read_text(encoding="utf-8"))


def main() -> None:
    files = verify_files(read_input().get("files") or [])
    dispositions_entry, dispositions = local_json(files, "core-dispositions-usdm")
    report = local_json(files, "core-report")[1]
    child_run = (dispositions_entry.get("producedBy") or {}).get("runId")
    to_fix = {key: item for key, item in (dispositions.get("dispositions") or {}).items()
              if item.get("disposition") == "fix" and item.get("runId") == child_run}
    if not to_fix:
        raise StepFailure("CORE rejected the USDM but this round has no finding marked fix.")

    issues = defaultdict(list)
    for issue in report.get("Issue_Details") or []:
        issues[issue.get("core_id")].append(issue)
    rules = []
    for item in sorted(to_fix.values(), key=lambda value: str(value.get("rule"))):
        found = issues.get(item.get("rule")) or []
        rules.append({
            "rule": item.get("rule"), "ddfRule": found[0].get("cdisc_rule_id") if found else None,
            "message": found[0].get("message") if found else None, "reviewer": item.get("justification") or "",
            "issues": len(found),
            "instances": [{"entity": issue.get("entity"), "id": issue.get("instance_id"), "path": issue.get("path"),
                           "values": dict(zip(issue.get("attributes") or [], issue.get("values") or []))}
                          for issue in found[:INSTANCES_PER_RULE]],
        })
    CORE_FEEDBACK.write_text(json.dumps({"coreRun": child_run, "rules": rules}, indent=2), encoding="utf-8")

    lines = [f"CORE USDM 4.0 validation: the standards reviewer marked {len(rules)} rule(s) to fix. Fix every flagged instance; "
             f"the instance ids, JSON paths and values are in {CORE_FEEDBACK}."]
    for rule in rules:
        example = rule["instances"][0] if rule["instances"] else {}
        lines.append(f"- {rule['rule']} ({rule['ddfRule']}, {rule['issues']} issue(s)): {rule['message']}"
                     + (f" Reviewer: {rule['reviewer']}" if rule["reviewer"] else "")
                     + (f" e.g. {example.get('id')} at {example.get('path')}" if example else ""))
    recorded = LOOP.append_request("\n".join(lines), "protocol-to-usdm", source="core")
    write_result({**recorded, "rules": [rule["rule"] for rule in rules],
                  "summary": f"{len(rules)} CORE rule(s) to fix sent back to the agent: {', '.join(rule['rule'] for rule in rules)}"})


if __name__ == "__main__":
    run_main(main)
