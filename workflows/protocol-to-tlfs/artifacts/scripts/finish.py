"""Assemble the deliverables of a protocol-to-TFL run into one manifest.

Follows collect-deliverables, which hands on the final study package and, as
downloaded `files`, the deliverables worth opening (traceability explorer, reconciliation,
review pages, CORE reports, ADaM define.xml). Each is sha256-verified and copied
into this step's /output under its `showAs` name, so the master run shows them.
manifest.json lists, by deliverable, every file in the package with the
sub-workflow run that produced it (a download URL into that run), plus the
package history (which run of which sub-workflow ended how).

Result: { outcome: complete, summary, shown, deliverables, history, package }
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import OUTPUT_DIR, StepFailure, read_input, run_main, verify_files, with_history, write_result  # noqa: E402

WORKFLOW = "protocol-to-tlfs"
DELIVERABLES = (
    ("Traceability explorer (outputs, ARD, ADaM lineage, protocol, CORE, checks)", ("traceability",), None),
    ("TLF viewer and reconciliation", ("tfl",), ("tlf-viewer.html", "reconciliation.json", "accuracy.json")),
    ("Rendered tables and figures", ("tfl",), None),
    ("Analysis Results Data", ("ard",), None),
    ("TLF programs and logs", ("tfl-program", "tfl-log"), None),
    ("ADaM datasets, define.xml and lineage", ("adam", "adam-define", "lineage"), None),
    ("ADaM programs and logs", ("adam-program", "adam-log"), None),
    ("CORE reports and dispositions", ("core-report-sdtmig", "core-report-adamig", "core-issue-index-sdtmig", "core-issue-index-adamig",
                                       "core-dispositions-sdtmig", "core-dispositions-adamig"), None),
    ("Analysis specs, ADaM spec and ARS ReportingEvent", ("analysis-spec", "analysis-spec-view", "adam-spec", "ars"), None),
    ("TLF plan, study model and coverage audit", ("tlf-plan", "tlf-plan-view", "study-model", "coverage-report"), None),
    ("Protocol digitization: USDM citations, review page and CORE USDM", ("usdm-citations", "usdm-view", "core-report-usdm",
                                                                          "core-issue-index-usdm", "core-dispositions-usdm"), None),
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


def show(files: list[dict]) -> list[str]:
    shown = []
    for entry in verify_files(files):
        show_as = Path(entry.get("showAs") or entry["name"]).name
        shutil.copyfile(entry["localPath"], OUTPUT_DIR / show_as)
        shown.append(show_as)
    return shown


def main() -> None:
    step_input = read_input()
    package = step_input.get("package")
    if isinstance(package, dict) is False or not package.get("files"):
        raise StepFailure("collect-deliverables handed on no study package.")
    shown = show(step_input.get("files") or [])
    groups = deliverables(package)
    history = package.get("history") or []
    manifest = {"study": package.get("study"), "deliverables": groups, "history": history}
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    counts = ", ".join(f"{len(group['files'])} {group['title'].split(' (')[0].lower()}" for group in groups[:3])
    write_result({
        "outcome": "complete", "shown": shown, "deliverables": groups, "history": history,
        "summary": f"COMPLETE: {counts}; {len(history)} sub-workflow run(s) in the history. Start with traceability-explorer.html; manifest.json lists every file.",
        "package": with_history(package, WORKFLOW, "complete"),
    })


if __name__ == "__main__":
    run_main(main)
