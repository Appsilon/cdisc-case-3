"""Assemble each workflows/<name>/ folder into a registrable dist/<name>.wd.json.

A workflow folder holds `workflow.json` (the definition without files) and
`artifacts/` (Dockerfile, scripts, rules, templates). The platform mounts carried
artifacts read-only at /artifacts and builds the carried Dockerfile, so scripts
version with the definition and no image or commit has to be pinned. Shared
helpers in workflows/shared/ are copied into every workflow's scripts/.

Child versions are per namespace. Pins live in `pins/<instance>-<namespace>.json`
(prod `clinical-workflows` from 2026-11-13; the versions inside workflow.json are
historical); `--pins pins/<instance>-<namespace>.json` (child name -> version) rewrites every
run-workflow step's `definitionVersion` and writes to dist/<instance>-<namespace>/.

Usage: python3 tools/build_workflows.py [--pins pins/prod-clinical-workflows.json] [name ...]
Then:  pnpm exec mediforce workflow register --file=dist/[<pins>/]<name>.wd.json --namespace=<ns>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / "workflows"
SHARED = WORKFLOWS / "shared"
DIST = ROOT / "dist"
FILE_CAP = 64 * 1024
SET_CAP = 256 * 1024
SKIPPED_PARTS = {"__pycache__", ".pytest_cache"}


def artifact_files(folder: Path) -> list[dict]:
    files = []
    artifacts = folder / "artifacts"
    for path in sorted(artifacts.rglob("*")):
        if path.is_file() and SKIPPED_PARTS.isdisjoint(path.parts):
            files.append({"path": path.relative_to(artifacts).as_posix(), "contents": path.read_text(encoding="utf-8")})
    for path in sorted(SHARED.glob("*.py")):
        files.append({"path": f"scripts/{path.name}", "contents": path.read_text(encoding="utf-8")})
    return files


STEP_REFERENCE = re.compile(r"\$\{steps\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)")


def reference_problems(definition: dict) -> list[str]:
    """`${steps.<id>.output.x}` only for run-workflow steps (their child's result sits under `output`);
    a script or agent step's own result fields are read directly: `${steps.<id>.x}`."""
    kinds = {step["id"]: (step.get("action") or {}).get("kind") or step.get("executor") for step in definition["steps"]}
    problems = []
    for step_id, field in STEP_REFERENCE.findall(json.dumps(definition)):
        if step_id not in kinds:
            problems.append(f"${{steps.{step_id}...}} names no step")
        elif (field == "output") is not (kinds[step_id] == "run-workflow"):
            problems.append(f"${{steps.{step_id}.{field}...}}: {step_id} is a {kinds[step_id]} step")
    return sorted(set(problems))


def apply_pins(definition: dict, pins: dict[str, int]) -> None:
    for step in definition["steps"]:
        config = (step.get("action") or {}).get("config") or {}
        if "definitionName" not in config:
            continue
        if config["definitionName"] not in pins:
            raise SystemExit(f"{definition['name']}: step {step['id']} runs {config['definitionName']}, which the pins file does not pin")
        config["definitionVersion"] = pins[config["definitionName"]]


def build(folder: Path, pins: dict[str, int] | None, target_folder: Path) -> Path:
    definition = json.loads((folder / "workflow.json").read_text(encoding="utf-8"))
    if pins is not None:
        apply_pins(definition, pins)
    problems = reference_problems(definition)
    if problems:
        raise SystemExit(f"{folder.name}: bad step references: {problems}")
    files = artifact_files(folder)
    paths = [entry["path"] for entry in files]
    duplicates = {path for path in paths if paths.count(path) > 1}
    if duplicates:
        raise SystemExit(f"{folder.name}: duplicate artifact paths {sorted(duplicates)}")
    oversized = [entry["path"] for entry in files if len(entry["contents"].encode()) > FILE_CAP]
    total = sum(len(entry["contents"].encode()) for entry in files)
    if oversized or total > SET_CAP:
        raise SystemExit(f"{folder.name}: artifacts over the cap (64 KiB/file, 256 KiB/set): {oversized}, total {total}")
    definition["artifacts"] = files
    target_folder.mkdir(parents=True, exist_ok=True)
    target = target_folder / f"{definition['name']}.wd.json"
    target.write_text(json.dumps(definition, indent=2), encoding="utf-8")
    print(f"{target.relative_to(ROOT)}: {len(definition['steps'])} steps, {len(files)} artifacts, {total / 1024:.1f} KiB")
    return target


def main() -> None:
    arguments = sys.argv[1:]
    pins, target_folder = None, DIST
    if len(arguments) >= 2 and arguments[0] == "--pins":
        pins_file = Path(arguments[1])
        pins = json.loads(pins_file.read_text(encoding="utf-8"))
        target_folder = DIST / pins_file.stem
        arguments = arguments[2:]
    names = arguments or [path.name for path in sorted(WORKFLOWS.iterdir()) if (path / "workflow.json").is_file()]
    for name in names:
        build(WORKFLOWS / name, pins, target_folder)


if __name__ == "__main__":
    main()
