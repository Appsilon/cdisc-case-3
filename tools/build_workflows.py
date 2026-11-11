"""Assemble each workflows/<name>/ folder into a registrable dist/<name>.wd.json.

A workflow folder holds `workflow.json` (the definition without files) and
`artifacts/` (Dockerfile, scripts, rules, templates). The platform mounts carried
artifacts read-only at /artifacts and builds the carried Dockerfile, so scripts
version with the definition and no image or commit has to be pinned. Shared
helpers in workflows/shared/ are copied into every workflow's scripts/.

Usage: python3 tools/build_workflows.py [name ...]
Then:  pnpm exec mediforce workflow register --file=dist/<name>.wd.json --namespace=<ns>
"""

from __future__ import annotations

import json
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


def build(folder: Path) -> Path:
    definition = json.loads((folder / "workflow.json").read_text(encoding="utf-8"))
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
    DIST.mkdir(exist_ok=True)
    target = DIST / f"{definition['name']}.wd.json"
    target.write_text(json.dumps(definition, indent=2), encoding="utf-8")
    print(f"{target.relative_to(ROOT)}: {len(definition['steps'])} steps, {len(files)} artifacts, {total / 1024:.1f} KiB")
    return target


def main() -> None:
    names = sys.argv[1:] or [path.name for path in sorted(WORKFLOWS.iterdir()) if (path / "workflow.json").is_file()]
    for name in names:
        build(WORKFLOWS / name)


if __name__ == "__main__":
    main()
