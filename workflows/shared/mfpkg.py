"""Study package helpers shared by every protocol-to-TFL sub-workflow.

A run cannot see another run's steps or files, so workflows hand each other a
*study package*: small JSON that names files by `downloadUrl` instead of
carrying bytes.

    package = {
        "study":   {"id": "CDISCPILOT01", ...},
        "profile": {"sdtmig": "3-4", "ct": "sdtmct-2025-09-26", ...},
        "files":   [FileEntry, ...],
        "history": [{"workflow", "runId", "outcome", "at"}, ...],
    }
    FileEntry = {"name", "downloadUrl", "kind", "sha256", "producedBy": {"workflow", "runId", "step"}}

The runtime downloads a step's top-level `files` to `/data/<i>/<name>` and sets
`localPath` before the script starts. `verify_files` re-hashes every download,
so a missing or swapped file fails the step instead of being replaced by other
data.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

OUTPUT_DIR = Path(os.environ.get("MEDIFORCE_OUTPUT_DIR", "/output"))
STEP_OUTPUTS_DIR = Path(os.environ.get("MEDIFORCE_STEP_OUTPUTS_DIR", "/workspace/.mediforce/output"))

# Replacing a kind makes everything derived from it stale. The master and every
# sub-workflow go through `replace_files`, so stale downstream artifacts are
# dropped in one place instead of being trusted by the next phase.
DOWNSTREAM: dict[str, tuple[str, ...]] = {
    "usdm": ("study-model", "tlf-plan", "coverage-report", "analysis-spec", "ars", "adam-spec"),
    "tlf-plan": ("analysis-spec", "ars", "adam-spec"),
    "analysis-spec": ("ard", "tfl", "tfl-program"),
    "ars": ("ard", "tfl", "tfl-program"),
    "adam-spec": ("adam", "adam-define", "adam-program", "adam-log", "lineage"),
    "sdtm": ("adam", "adam-define", "adam-program", "adam-log", "lineage", "core-report-adamig"),
    "sdtm-define": ("core-report-sdtmig",),
    "adam": ("ard", "tfl", "tfl-program", "core-report-adamig"),
}


class StepFailure(Exception):
    """An expected failure whose message is what the reviewer should read."""


def read_input() -> dict:
    return json.loads((OUTPUT_DIR / "input.json").read_text(encoding="utf-8"))


def write_result(result: dict) -> None:
    (OUTPUT_DIR / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


def fail(message: str) -> None:
    """Surface `message` as the step error: result.json `error` plus stderr, exit 1."""
    write_result({"status": "failed", "error": message})
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def run_main(main) -> None:
    try:
        main()
    except StepFailure as failure:
        fail(str(failure))


def step_output(step_input: dict, step_id: str) -> dict:
    output = (step_input.get("steps") or {}).get(step_id)
    return output if isinstance(output, dict) else {}


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_files(files: list[dict]) -> list[dict]:
    """Every entry downloaded and, where a hash was recorded, byte-identical."""
    problems = []
    for entry in files:
        local_path = entry.get("localPath")
        if not local_path or Path(local_path).is_file() is False:
            problems.append(f"{entry.get('name')}: not downloaded")
            continue
        expected = entry.get("sha256")
        if expected and sha256_of(Path(local_path)) != expected:
            problems.append(f"{entry.get('name')}: sha256 mismatch")
    if problems:
        raise StepFailure("Input files failed verification — " + "; ".join(problems))
    return files


def file_entry(path: Path, step_id: str, relative: str, kind: str, workflow: str) -> dict:
    run_id = os.environ.get("RUN_ID", "")
    return {
        "name": path.name,
        "downloadUrl": f"/api/runs/{run_id}/files/.mediforce/output/{step_id}/{relative}",
        "kind": kind,
        "sha256": sha256_of(path),
        "producedBy": {"workflow": workflow, "runId": run_id, "step": step_id},
    }


def published_file(path: Path, kind: str, workflow: str, extra: dict | None = None) -> dict:
    """A FileEntry for a file this step wrote under /output."""
    entry = file_entry(path, os.environ.get("STEP_ID", ""), path.relative_to(OUTPUT_DIR).as_posix(), kind, workflow)
    entry.update(extra or {})
    return entry


def step_file(step_id: str, relative: str, kind: str, workflow: str) -> dict | None:
    """A FileEntry for a file an earlier step of this run wrote under its /output, or None if it did not."""
    path = STEP_OUTPUTS_DIR / step_id / relative
    if path.is_file() is False:
        return None
    return file_entry(path, step_id, relative, kind, workflow)


def strip_local(entry: dict) -> dict:
    """A FileEntry as it travels in a package: no host-specific localPath."""
    return {key: value for key, value in entry.items() if key != "localPath"}


def stale_kinds(kinds: set[str]) -> set[str]:
    stale: set[str] = set()
    pending = list(kinds)
    while pending:
        for downstream in DOWNSTREAM.get(pending.pop(), ()):
            if downstream not in stale:
                stale.add(downstream)
                pending.append(downstream)
    return stale - kinds


def replace_files(package: dict, new_files: list[dict]) -> dict:
    """Swap in `new_files`, dropping older files of the same kinds and of every kind derived from them."""
    replaced = {entry["kind"] for entry in new_files}
    dropped = replaced | stale_kinds(replaced)
    kept = [entry for entry in package.get("files") or [] if entry.get("kind") not in dropped]
    updated = dict(package)
    updated["files"] = kept + [strip_local(entry) for entry in new_files]
    return updated


def with_history(package: dict, workflow: str, outcome: str) -> dict:
    updated = dict(package)
    updated["history"] = list(package.get("history") or []) + [
        {"workflow": workflow, "runId": os.environ.get("RUN_ID", ""), "outcome": outcome, "at": now_iso()}
    ]
    return updated


def files_of_kind(package: dict, *kinds: str) -> list[dict]:
    return [entry for entry in package.get("files") or [] if entry.get("kind") in kinds]
