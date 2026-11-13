"""Turn CORE's report into a reviewable HTML page and one review row per finding.

Reads run-core's Output Files (core-report.json, the staged datasets and the
trace inputs it copied) and writes:

- core-report.html   self-contained page: findings grouped by rule x dataset,
                      example records, trace to code, what CORE could not check,
                      and the change since the previous validation;
- core-issue-index.json  one key per issue, so the next validation can tell
                      new issues from fixed and persisting ones.

Trace, when a `lineage.json` is supplied (written by derive-adam):
  ADaM issue  -> variable -> program file:lines + spec entry + SDTM sources,
                 and for BDS/OCCDS rows the SRCDOM/SRCSEQ source record;
  SDTM issue  -> the ADaM variables derived from it and the TLFs that use them.

Result: { options: [review rows], counts, groups, notChecked, needsReview, summary }
`options` feeds the table-editor review step that follows.
"""

from __future__ import annotations

import html
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import OUTPUT_DIR, STEP_OUTPUTS_DIR, StepFailure, read_input, run_main, step_output, write_result  # noqa: E402

RUN_CORE_DIR = STEP_OUTPUTS_DIR / "run-core"
TEMPLATE = Path(__file__).resolve().parent / "report_template.html"
EXAMPLES_PER_GROUP = 25
SNIPPET_CONTEXT = 2
SNIPPET_MAX_LINES = 40
SOURCE_VARIABLES = ("SRCDOM", "SRCVAR", "SRCSEQ")
SEVERITIES = ("error", "warning", "ignore")


def issue_key(issue: dict) -> str:
    record = issue.get("SEQ") if issue.get("SEQ") not in (None, "") else issue.get("row")
    return "|".join(str(part) for part in (issue.get("core_id"), issue.get("dataset"), issue.get("USUBJID") or "", record if record is not None else ""))


def group_id(core_id: str, dataset: str) -> str:
    return f"{core_id}|{dataset}"


def load_json(folder: Path, prefix: str) -> dict:
    matches = sorted(folder.glob(f"{prefix}*.json")) if folder.is_dir() else []
    return json.loads(matches[0].read_text(encoding="utf-8")) if matches else {}


class Lineage:
    """Variable-level lineage: who derives each ADaM variable, and what reads each SDTM variable."""

    def __init__(self, document: dict, programs_dir: Path):
        self.by_variable: dict[str, dict] = {}
        self.readers: dict[str, list[dict]] = defaultdict(list)
        self.consumers: dict[str, list[str]] = document.get("consumers") or {}
        self.programs_dir = programs_dir
        for entry in document.get("variables") or []:
            key = f"{str(entry.get('dataset', '')).upper()}.{str(entry.get('variable', '')).upper()}"
            self.by_variable[key] = entry
            for source in entry.get("sources") or []:
                self.readers[str(source).upper()].append(entry)

    @property
    def present(self) -> bool:
        return bool(self.by_variable)

    def snippet(self, program: str, lines: list) -> dict | None:
        path = self.programs_dir / Path(program).name
        if path.is_file() is False or len(lines) != 2:
            return None
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
        first = max(1, int(lines[0]) - SNIPPET_CONTEXT)
        last = min(len(text), int(lines[1]) + SNIPPET_CONTEXT, first + SNIPPET_MAX_LINES - 1)
        return {"first": first, "highlight": [int(lines[0]), int(lines[1])], "code": text[first - 1:last]}

    def trace(self, dataset: str, variables: list[str]) -> dict:
        derivations, impacts = [], []
        for variable in variables:
            key = f"{dataset}.{variable}".upper()
            entry = self.by_variable.get(key)
            if entry is not None:
                derivations.append({
                    "variable": key,
                    "origin": entry.get("origin"),
                    "program": entry.get("program"),
                    "lines": entry.get("lines"),
                    "spec": entry.get("spec"),
                    "sources": entry.get("sources") or [],
                    "method": entry.get("method"),
                    "snippet": self.snippet(str(entry.get("program") or ""), entry.get("lines") or []),
                    "usedBy": self.consumers.get(key, []),
                })
            for reader in self.readers.get(key, []):
                derived = f"{reader.get('dataset')}.{reader.get('variable')}".upper()
                impacts.append({"source": key, "derived": derived, "program": reader.get("program"),
                                "lines": reader.get("lines"), "usedBy": self.consumers.get(derived, [])})
        return {"derivations": derivations, "impacts": impacts}


def source_records(dataset: str, rows: list[int]) -> dict[int, dict]:
    """SRCDOM/SRCVAR/SRCSEQ of the given 1-based rows, when the dataset carries them."""
    path = RUN_CORE_DIR / "datasets" / f"{dataset.lower()}.xpt"
    if path.is_file() is False or not rows:
        return {}
    import pyreadstat

    _, meta = pyreadstat.read_xport(str(path), metadataonly=True)
    present = [name for name in SOURCE_VARIABLES if name in meta.column_names]
    if "SRCDOM" not in present:
        return {}
    frame, _ = pyreadstat.read_xport(str(path), usecols=present)
    found = {}
    for row in rows:
        if 1 <= row <= len(frame):
            record = frame.iloc[row - 1]
            found[row] = {name: (None if record[name] != record[name] else str(record[name])) for name in present}
    return found


def build_groups(report: dict, policy: dict, previous_index: set[str], previous_dispositions: dict, lineage: Lineage) -> tuple[list[dict], set[str]]:
    rules = {rule.get("core_id"): rule for rule in report.get("Rules_Report") or []}
    totals: dict[str, int] = defaultdict(int)
    for item in report.get("Issue_Summary") or []:
        totals[group_id(item.get("core_id"), item.get("dataset"))] += int(item.get("issues") or 0)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for issue in report.get("Issue_Details") or []:
        grouped[group_id(issue.get("core_id"), issue.get("dataset"))].append(issue)

    current_keys: set[str] = set()
    groups = []
    for identifier, issues in grouped.items():
        core_id, dataset = identifier.split("|", 1)
        keys = {issue_key(issue) for issue in issues}
        total = max(totals.get(identifier, 0), len(issues))
        truncated = total > len(issues)
        current_keys |= keys
        previous_in_group = {key for key in previous_index if key.startswith(identifier + "|")}
        severity = str((policy.get("rules") or {}).get(core_id, {}).get("severity") or "error")
        severity = severity if severity in SEVERITIES else "error"
        variables = sorted({variable for issue in issues for variable in issue.get("variables") or []})
        examples = issues[:EXAMPLES_PER_GROUP]
        records = source_records(dataset, [int(issue["row"]) for issue in examples if str(issue.get("row", "")).isdigit()])
        rule = rules.get(core_id) or {}
        groups.append({
            "id": identifier,
            "coreId": core_id,
            "dataset": dataset,
            "message": issues[0].get("message") or rule.get("message") or "",
            "executability": issues[0].get("executability") or "",
            "cdiscRuleId": rule.get("cdisc_rule_id") or "",
            "fdaRuleId": rule.get("fda_rule_id") or "",
            "ruleSource": rule.get("source") or "published",
            "severity": severity,
            "issues": total,
            "detailedIssues": len(issues),
            "subjects": len({issue.get("USUBJID") for issue in issues if issue.get("USUBJID")}),
            "subjectsAtLeast": truncated,
            "variables": variables,
            "new": len(keys - previous_index) if previous_index and truncated is False else None,
            "fixed": len(previous_in_group - keys) if previous_index and truncated is False else None,
            "previous": previous_dispositions.get(identifier),
            "examples": [
                {"USUBJID": issue.get("USUBJID"), "row": issue.get("row"), "SEQ": issue.get("SEQ"),
                 "variables": issue.get("variables") or [], "values": issue.get("values") or [],
                 "source": records.get(int(issue["row"])) if str(issue.get("row", "")).isdigit() else None}
                for issue in examples
            ],
            "trace": lineage.trace(dataset, variables) if lineage.present else None,
        })
    order = {severity: index for index, severity in enumerate(SEVERITIES)}
    groups.sort(key=lambda group: (order[group["severity"]], -group["issues"]))
    return groups, current_keys


def not_checked(report: dict) -> list[dict]:
    rows = []
    for rule in report.get("Rules_Report") or []:
        status = rule.get("status")
        reason = str(rule.get("skip_reason") or "")
        if status == "EXECUTION ERROR" or (status == "SKIPPED" and "requires" in reason.lower()):
            rows.append({"coreId": rule.get("core_id"), "status": status, "reason": reason or rule.get("message") or "",
                         "message": rule.get("message") or "", "source": rule.get("source") or "published"})
    return rows


def review_rows(groups: list[dict], unchecked: list[dict], intake: list[dict]) -> list[dict]:
    rows = []
    for group in groups:
        if group["severity"] == "ignore":
            continue
        previous = group["previous"] or {}
        change = "" if group["new"] is None else f"+{group['new']} new / -{group['fixed']} fixed"
        rows.append({
            "id": group["id"],
            "rule": group["coreId"],
            "dataset": group["dataset"],
            "severity": group["severity"],
            "issues": str(group["issues"]),
            "subjects": "" if group["subjects"] == 0 else f"≥{group['subjects']}" if group["subjectsAtLeast"] is True else str(group["subjects"]),
            "change": change,
            "previously": f"{previous.get('disposition')}: {previous.get('justification') or ''}".strip(": ") if previous else "",
            "message": group["message"][:160],
        })
    errors = [row for row in unchecked if row["status"] == "EXECUTION ERROR"]
    if errors:
        rows.append({"id": "not-checked", "rule": "EXECUTION ERROR", "dataset": "-", "severity": "warning",
                     "issues": str(len(errors)), "subjects": "", "change": "", "previously": "",
                     "message": f"{len(errors)} rule(s) could not execute — those checks did not run. See 'Not checked' in the report."})
    fatal = [item for item in intake if item.get("fatal")]
    if fatal:
        rows.append({"id": "intake", "rule": "INTAKE", "dataset": ", ".join(item["dataset"] for item in fatal)[:60],
                     "severity": "error", "issues": str(len(fatal)), "subjects": "", "change": "", "previously": "",
                     "message": "Datasets that could not be validated at all: " + "; ".join(item["problem"] for item in fatal)[:300]})
    return rows


def render(data: dict) -> str:
    payload = json.dumps(data, default=str).replace("</", "<\\/")
    title = html.escape(f"CORE {data['config']['standard'].upper()} {data['config']['version']} report")
    return TEMPLATE.read_text(encoding="utf-8").replace("__TITLE__", title).replace("__DATA__", payload)


def main() -> None:
    step_input = read_input()
    run = step_output(step_input, "run-core")
    report_path = RUN_CORE_DIR / "core-report.json"
    if report_path.is_file() is False:
        raise StepFailure(f"run-core left no core-report.json at {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    inputs = RUN_CORE_DIR / "inputs"
    standard = (run.get("config") or {}).get("standard", "")

    previous_index_doc = load_json(inputs, f"core-issue-index-{standard}")
    previous_index = set(previous_index_doc.get("keys") or [])
    previous_dispositions = (load_json(inputs, f"core-dispositions-{standard}") or {}).get("dispositions") or {}
    policy = load_json(inputs, "core-policy")
    lineage = Lineage(load_json(inputs, "lineage"), inputs / "programs")

    groups, current_keys = build_groups(report, policy, previous_index, previous_dispositions, lineage)
    unchecked = not_checked(report)
    intake = run.get("intakeFindings") or []
    rows = review_rows(groups, unchecked, intake)

    counts = {
        "issues": sum(group["issues"] for group in groups),
        "groups": len(groups),
        "errorGroups": sum(1 for group in groups if group["severity"] == "error"),
        "new": len(current_keys - previous_index) if previous_index else None,
        "fixed": len(previous_index - current_keys) if previous_index else None,
        "notChecked": len(unchecked),
        "executionErrors": sum(1 for row in unchecked if row["status"] == "EXECUTION ERROR"),
        "datasets": len(run.get("datasets") or []),
    }
    data = {
        "config": run.get("config") or {},
        "coreVersion": run.get("coreVersion"),
        "conformance": report.get("Conformance_Details") or {},
        "datasets": run.get("datasets") or [],
        "statusCounts": run.get("ruleStatusCounts") or {},
        "counts": counts,
        "groups": groups,
        "notChecked": unchecked,
        "intake": intake,
        "notes": run.get("notes") or [],
        "lineage": lineage.present,
        "comparedWith": previous_index_doc.get("runId"),
    }
    (OUTPUT_DIR / "core-report.html").write_text(render(data), encoding="utf-8")
    (OUTPUT_DIR / f"core-issue-index-{standard}.json").write_text(
        json.dumps({"standard": standard, "runId": os.environ.get("RUN_ID", ""), "keys": sorted(current_keys)}), encoding="utf-8"
    )
    change = "" if counts["new"] is None else f" Since the last validation: {counts['new']} new, {counts['fixed']} fixed."
    write_result({
        "options": rows,
        "needsReview": len(rows) > 0,
        "counts": counts,
        "lineage": lineage.present,
        "summary": (
            f"{counts['issues']} issue(s) in {counts['groups']} rule x dataset group(s), {counts['errorGroups']} at error level;"
            f" {counts['executionErrors']} rule(s) could not execute.{change} Open core-report.html."
        ),
    })


if __name__ == "__main__":
    run_main(main)
