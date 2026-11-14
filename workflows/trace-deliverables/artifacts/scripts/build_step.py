"""Build the traceability explorer of the study package and add it to the package.

The files resolve-inputs chose arrive downloaded (`localPath`); each is
sha256-verified and staged as <kind>/<name>, the layout build_explorer.py reads.
traceability-explorer.html and traceability.json are written to /output (so the
run shows the page) and published into the package as kind `traceability`.
Gaps are reported, never fatal: the explorer is a view of what the run produced.

Result: { outcome: traced, gaps, summary, files, package }
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_explorer import build, summary  # noqa: E402
from mfpkg import OUTPUT_DIR, StepFailure, published_file, read_input, replace_files, run_main, verify_files, with_history, write_result  # noqa: E402

WORKFLOW = "trace-deliverables"
KIND = "traceability"


def stage(files: list[dict], package: dict, folder: Path) -> None:
    for entry in verify_files(files):
        target = folder / str(entry["kind"]) / Path(str(entry["name"])).name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(entry["localPath"], target)
    (folder / "package.json").write_text(json.dumps(package), encoding="utf-8")


def main() -> None:
    step_input = read_input()
    package = step_input.get("package")
    if isinstance(package, dict) is False or len(package.get("files") or []) == 0:
        raise StepFailure("resolve-inputs handed on no study package.")
    with tempfile.TemporaryDirectory() as scratch:
        staged = Path(scratch) / "package"
        stage(step_input.get("files") or [], package, staged)
        model = build(staged, OUTPUT_DIR)
    files = [published_file(OUTPUT_DIR / name, KIND, WORKFLOW) for name in ("traceability-explorer.html", "traceability.json")]
    write_result({"outcome": "traced", "gaps": len(model["gaps"]), "summary": summary(model) + " Open traceability-explorer.html.",
                  "files": files, "package": with_history(replace_files(package, files), WORKFLOW, "traced")})


if __name__ == "__main__":
    run_main(main)
