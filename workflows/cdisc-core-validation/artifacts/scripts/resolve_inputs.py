"""Decide where this validation's inputs come from and with which settings.

Started by a parent workflow, the trigger carries a study `package`: its files
of the kinds this standard validates are handed to `run-core` as top-level
`files`, which the runtime downloads. Started by hand, there is no package and
the run goes to the upload step instead.

Result: { needsUpload, config: {standard, version, ct, onReject}, files, package, summary }
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, files_of_kind, read_input, run_main, write_result  # noqa: E402

# The rule sets the pinned CORE release carries (`core list-rule-sets`), newest
# first. adamig has no published rules: it runs on the carried local rules.
STANDARDS: dict[str, tuple[str, ...]] = {
    "sdtmig": ("3-4", "3-3", "3-2"),
    "adamig": ("1-3", "1-2", "1-1", "1-0"),
    "sendig": ("3-1-1", "3-1", "3-0"),
    "usdm": ("4-0", "3-0"),
}
# Package kinds validated under each standard, plus the trace inputs the report joins on.
DATA_KINDS: dict[str, tuple[str, ...]] = {
    "sdtmig": ("sdtm", "sdtm-define"),
    "sendig": ("send", "send-define"),
    "adamig": ("adam", "adam-define"),
    "usdm": ("usdm",),
}
TRACE_KINDS = ("lineage", "adam-program", "core-policy", "core-rules")
ON_REJECT = ("reupload", "return")


def text_param(step_input: dict, name: str) -> str:
    value = step_input.get(name)
    if isinstance(value, str) and value.strip() != "" and value.startswith("${") is False:
        return value.strip()
    return ""


def resolve_config(step_input: dict, package: dict | None) -> dict:
    profile = (package or {}).get("profile") or {}
    standard = (text_param(step_input, "standard") or "sdtmig").lower()
    if standard not in STANDARDS:
        raise StepFailure(f"Unsupported standard '{standard}'. Supported: {', '.join(STANDARDS)}")
    version = text_param(step_input, "version") or str(profile.get(standard) or "") or STANDARDS[standard][0]
    version = version.replace(".", "-")
    if version not in STANDARDS[standard]:
        raise StepFailure(
            f"{standard} {version} has no rule set in this CORE release. Supported: {', '.join(STANDARDS[standard])}"
        )
    on_reject = text_param(step_input, "onReject")
    if on_reject in ("", "auto"):
        on_reject = "return" if package else "reupload"
    if on_reject not in ON_REJECT:
        raise StepFailure(f"onReject must be one of {', '.join(ON_REJECT)}, got '{on_reject}'")
    return {
        "standard": standard,
        "version": version,
        "ct": text_param(step_input, "ct") or str(profile.get("ct") or ""),
        "onReject": on_reject,
    }


def main() -> None:
    step_input = read_input()
    package = step_input.get("package")
    package = package if isinstance(package, dict) and package.get("files") else None
    config = resolve_config(step_input, package)

    if package is None:
        write_result({
            "needsUpload": True,
            "config": config,
            "files": [],
            "package": {},
            "summary": f"No study package: waiting for an upload to validate against {config['standard']} {config['version']}.",
        })
        return

    data_files = files_of_kind(package, *DATA_KINDS[config["standard"]])
    if not [entry for entry in data_files if not entry["kind"].endswith("-define")]:
        raise StepFailure(
            f"The study package has no {' / '.join(DATA_KINDS[config['standard']])} files to validate "
            f"against {config['standard']}. Kinds present: "
            + ", ".join(sorted({str(entry.get('kind')) for entry in package.get('files') or []}) or ["none"])
        )
    trace_files = files_of_kind(package, *TRACE_KINDS)
    history_files = files_of_kind(
        package, f"core-dispositions-{config['standard']}", f"core-issue-index-{config['standard']}"
    )
    write_result({
        "needsUpload": False,
        "config": config,
        "files": data_files + trace_files + history_files,
        "package": package,
        "summary": (
            f"Validating {len(data_files)} package file(s) against {config['standard']} {config['version']}"
            f" with {len(trace_files)} trace input(s)."
        ),
    })


if __name__ == "__main__":
    run_main(main)
