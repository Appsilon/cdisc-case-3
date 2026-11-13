"""Fetch a study package locally for offline work (e.g. handover/e2e-a48c3201).

  python3 tools/fetch_package.py <folder containing package.json>

Run files come through `mediforce run download` (prod, phuse-key); uploaded inputs
(/api/attachments/..., 403 for the API key) are copied from the local pilot SDTM and
handover/ copies when their sha256 matches. Files land in <folder>/<kind>/<name>.
"""
import hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path
target = Path(sys.argv[1])
package = json.loads((target / "package.json").read_text())
local_inputs = [Path.home() / "Repo/protocol-to-tfl/test-docs/cdiscpilot01/sdtm", Path.home() / "Repo/cdisc-case-3/handover"]
environment = {**os.environ, "MEDIFORCE_API_KEY": (Path.home() / ".config/mediforce/phuse-key").read_text().strip()}
missing = []
for entry in package["files"]:
    folder = target / entry["kind"]
    folder.mkdir(exist_ok=True)
    destination = folder / entry["name"]
    match = re.search(r"/api/runs/([^/]+)/files/(.+)$", entry["downloadUrl"])
    if match:
        scratch = target / ".tmp"
        subprocess.run(["pnpm", "-s", "exec", "mediforce", "run", "download", match.group(1), match.group(2), "-o", str(scratch),
                        "--base-url=https://prod.mediforce.ai"], cwd=Path.home() / "Repo/mediforce", env=environment, capture_output=True)
        downloaded = scratch / Path(match.group(2)).name
        if downloaded.exists():
            shutil.move(str(downloaded), destination)
    else:
        for folder_candidate in local_inputs:
            candidate = folder_candidate / entry["name"]
            if candidate.exists() and hashlib.sha256(candidate.read_bytes()).hexdigest() == entry.get("sha256"):
                shutil.copyfile(candidate, destination)
                break
    if destination.exists() is False:
        missing.append(entry["name"])
shutil.rmtree(target / ".tmp", ignore_errors=True)
print("files", len(package["files"]), "missing", missing)
