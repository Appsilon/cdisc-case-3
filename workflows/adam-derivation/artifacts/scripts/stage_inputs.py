"""Verify and stage the derivation inputs where the agent and the executor read them.

Files arrive as top-level `files` (from the study package or the upload),
already downloaded with `localPath`. Each is sha256-verified, classified by its
package `kind` (uploads have none, so by name and content), and copied into
/workspace/adam-derivation/inputs. On a fix loop the previous programs go back
to /workspace/programs and the CORE findings the reviewer marked 'fix' are cut
down to /workspace/adam-derivation/inputs/core-findings.json.

Result: { inputFiles: [{name, downloadUrl, sha256, kind}], sdtm: [domains], fixMode, findings, summary }
"""

from __future__ import annotations

import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adamlib import ATTEMPTS_PATH, FEEDBACK_PATH, INPUTS_DIR, PROGRAMS_DIR, SDTM_DIR, WORK_DIR  # noqa: E402
from mfpkg import StepFailure, read_input, run_main, sha256_of, verify_files, write_result  # noqa: E402

DATASET_SUFFIXES = (".xpt", ".sas7bdat")
EXAMPLES_PER_FINDING = 20


def sniff_json(path: Path) -> str:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "ignored"
    if isinstance(document, dict) is False:
        return "ignored"
    if "Issue_Details" in document:
        return "core-report-adamig"
    if "dispositions" in document:
        return "core-dispositions-adamig"
    variables = document.get("variables")
    if isinstance(variables, list) and variables and isinstance(variables[0], dict) and "program" in variables[0]:
        return "lineage"
    datasets = document.get("datasets")
    if isinstance(datasets, list) and datasets and isinstance(datasets[0], dict) and "variables" in datasets[0]:
        return "adam-spec"
    if "analyses" in document or "analysis_specs" in document:
        return "analysis-spec"
    return "ignored"


def classify(entry: dict) -> str:
    kind = entry.get("kind")
    if kind:
        return str(kind)
    name = str(entry.get("name", "")).lower()
    if name.endswith(DATASET_SUFFIXES):
        return "sdtm"
    if name.endswith(".xml"):
        return "sdtm-define"
    if name.endswith(".r"):
        return "adam-program"
    if name.endswith(".json"):
        return sniff_json(Path(entry["localPath"]))
    return "ignored"


def fix_findings(dispositions_path: Path | None, report_path: Path | None) -> list[dict]:
    """The rule x dataset findings marked 'fix', each with example records from the CORE report."""
    if dispositions_path is None:
        return []
    dispositions = json.loads(dispositions_path.read_text(encoding="utf-8")).get("dispositions") or {}
    to_fix = {key: value for key, value in dispositions.items() if value.get("disposition") == "fix"}
    if not to_fix:
        return []
    issues = defaultdict(list)
    messages = {}
    if report_path is not None:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for issue in report.get("Issue_Details") or []:
            key = (str(issue.get("core_id")), str(issue.get("dataset", "")).upper())
            messages.setdefault(key, issue.get("message"))
            if len(issues[key]) < EXAMPLES_PER_FINDING:
                issues[key].append({field: issue.get(field) for field in ("USUBJID", "row", "variables", "values")})
    findings = []
    for value in to_fix.values():
        key = (str(value.get("rule")), str(value.get("dataset", "")).upper())
        # Dispositions accumulate across rounds; one fixed since it was marked is no longer in the report.
        if report_path is not None and key not in messages:
            continue
        findings.append({
            "rule": value.get("rule"),
            "dataset": value.get("dataset"),
            "issues": value.get("issues"),
            "message": messages.get(key, ""),
            "reviewerNote": value.get("justification", ""),
            "examples": issues.get(key, []),
        })
    return findings


def main() -> None:
    step_input = read_input()
    files = step_input.get("files") or []
    if not files:
        raise StepFailure("No files reached this step: the upload or the study package was empty.")
    verify_files(files)

    shutil.rmtree(INPUTS_DIR, ignore_errors=True)
    SDTM_DIR.mkdir(parents=True)
    for stale in (FEEDBACK_PATH, ATTEMPTS_PATH):
        stale.unlink(missing_ok=True)

    kinds = {entry["name"]: classify(entry) for entry in files}
    singles = defaultdict(list)
    programs = []
    for entry in files:
        kind = kinds[entry["name"]]
        source = Path(entry["localPath"])
        if kind == "sdtm":
            if source.suffix.lower() not in DATASET_SUFFIXES:
                raise StepFailure(f"{source.name}: SDTM must be SAS V5 .xpt or .sas7bdat")
            shutil.copyfile(source, SDTM_DIR / source.name.lower())
        elif kind == "adam-program":
            programs.append(source)
        elif kind != "ignored":
            singles[kind].append(source)

    for kind, paths in singles.items():
        if len(paths) > 1:
            raise StepFailure(f"Expected one {kind} file, got {len(paths)}: {', '.join(path.name for path in paths)}")
    if not list(SDTM_DIR.iterdir()):
        raise StepFailure("No SDTM datasets (.xpt / .sas7bdat) among the inputs.")
    if "adam-spec" not in singles:
        raise StepFailure("No adam-spec.json among the inputs: the spec drives which datasets and variables to derive.")

    targets = {
        "adam-spec": INPUTS_DIR / "adam-spec.json",
        "sdtm-define": INPUTS_DIR / "define.xml",
        "analysis-spec": INPUTS_DIR / "analysis-spec.json",
        "lineage": INPUTS_DIR / "previous-lineage.json",
    }
    for kind, target in targets.items():
        if kind in singles:
            shutil.copyfile(singles[kind][0], target)

    findings = fix_findings(
        (singles.get("core-dispositions-adamig") or [None])[0],
        (singles.get("core-report-adamig") or [None])[0],
    )
    fix_mode = len(programs) > 0 and len(findings) > 0
    if programs:
        shutil.rmtree(PROGRAMS_DIR, ignore_errors=True)
        PROGRAMS_DIR.mkdir(parents=True)
        for program in programs:
            shutil.copyfile(program, PROGRAMS_DIR / program.name)
    (INPUTS_DIR / "core-findings.json").write_text(json.dumps({"findings": findings if fix_mode else []}, indent=2), encoding="utf-8")
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    input_files = [
        {"name": entry["name"], "downloadUrl": entry["downloadUrl"], "sha256": sha256_of(Path(entry["localPath"])), "kind": kinds[entry["name"]]}
        for entry in files
        if kinds[entry["name"]] in ("sdtm", "sdtm-define", "adam-spec", "analysis-spec")
    ]
    domains = sorted(path.stem.upper() for path in SDTM_DIR.iterdir())
    ignored = sorted(name for name, kind in kinds.items() if kind == "ignored")
    write_result({
        "inputFiles": input_files,
        "sdtm": domains,
        "fixMode": fix_mode,
        "findings": len(findings),
        "ignored": ignored,
        "summary": (
            f"Staged {len(domains)} SDTM dataset(s) and the ADaM spec"
            + (f"; fix loop: {len(programs)} previous program(s), {len(findings)} finding(s) to fix" if fix_mode else "")
            + (f". Ignored: {', '.join(ignored)}" if ignored else "")
            + "."
        ),
    })


if __name__ == "__main__":
    run_main(main)
