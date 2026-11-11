"""Assemble the deliverables of a protocol-to-TFL run into one manifest.

Reads the study package the last sub-workflow returned and lists, by
deliverable, every file with the sub-workflow run that produced it, plus the
package history (which run of which sub-workflow ended how). Nothing is copied:
every entry is a download URL into the run that made it.

Result: { outcome: complete, summary, deliverables, history, package }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import OUTPUT_DIR, StepFailure, read_input, run_main, step_output, with_history, write_result  # noqa: E402

WORKFLOW = "protocol-to-tfl-modular"
DELIVERABLES = (
    ("TLF viewer (displays + ARD + programs + trace)", ("tfl",), ("tlf-viewer.html", "reconciliation.json")),
    ("Rendered tables and figures", ("tfl",), None),
    ("Analysis Results Data", ("ard",), None),
    ("TLF programs and logs", ("tfl-program", "tfl-log"), None),
    ("ADaM datasets, define.xml and lineage", ("adam", "adam-define", "lineage"), None),
    ("ADaM programs and logs", ("adam-program", "adam-log"), None),
    ("CORE reports and dispositions", ("core-report-sdtmig", "core-report-adamig", "core-issue-index-sdtmig", "core-issue-index-adamig",
                                       "core-dispositions-sdtmig", "core-dispositions-adamig"), None),
    ("Analysis specs, ADaM spec and ARS ReportingEvent", ("analysis-spec", "analysis-spec-view", "adam-spec", "ars"), None),
    ("TLF plan, study model and coverage audit", ("tlf-plan", "tlf-plan-view", "study-model", "coverage-report"), None),
    ("Study inputs", ("usdm", "sdtm", "sdtm-define", "sap", "protocol", "shells"), None),
)


def deliverables(package: dict) -> list[dict]:
    files = package.get("files") or []
    listed, groups = set(), []
    for title, kinds, names in DELIVERABLES:
        chosen = [entry for entry in files if entry.get("kind") in kinds and (names is None or entry.get("name") in names)
                  and entry.get("downloadUrl") not in listed]
        listed.update(entry.get("downloadUrl") for entry in chosen)
        if chosen:
            groups.append({"title": title, "files": [{"name": entry.get("name"), "kind": entry.get("kind"), "downloadUrl": entry.get("downloadUrl"),
                                                      "producedBy": entry.get("producedBy")} for entry in chosen]})
    return groups


def main() -> None:
    generated = step_output(read_input(), "generate").get("output") or {}
    package = generated.get("package")
    if isinstance(package, dict) is False or not package.get("files"):
        raise StepFailure("ard-tfl-generation returned no study package.")
    groups = deliverables(package)
    history = package.get("history") or []
    manifest = {"study": package.get("study"), "deliverables": groups, "history": history}
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    counts = ", ".join(f"{len(group['files'])} {group['title'].split(' (')[0].lower()}" for group in groups[:3])
    write_result({
        "outcome": "complete", "deliverables": groups, "history": history,
        "summary": f"COMPLETE: {counts}; {len(history)} sub-workflow run(s) in the history. Open manifest.json; start with the TLF viewer.",
        "package": with_history(package, WORKFLOW, "complete"),
    })


if __name__ == "__main__":
    run_main(main)
