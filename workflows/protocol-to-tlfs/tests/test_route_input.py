"""route_input.py: plan-tlfs from a USDM, digitize-protocol a protocol first, plan-tlfs from what it returned.

  python3 tests/test_route_input.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "artifacts" / "scripts"
SHARED = HERE.parent.parent / "shared"
SDTM = {"name": "dm.xpt", "kind": "sdtm", "downloadUrl": "/a", "sha256": "0"}
USDM = {"name": "usdm.json", "kind": "usdm", "downloadUrl": "/b", "sha256": "0"}
PROTOCOL = {"name": "protocol.pdf", "kind": "protocol", "downloadUrl": "/c", "sha256": "0"}


def route(work: Path, step_input: dict) -> tuple[int, dict]:
    scripts = work / "scripts"
    if scripts.is_dir() is False:
        shutil.copytree(SCRIPTS, scripts)
        for helper in SHARED.glob("*.py"):
            shutil.copyfile(helper, scripts / helper.name)
    output = work / "output"
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir()
    (output / "input.json").write_text(json.dumps(step_input))
    completed = subprocess.run([sys.executable, str(scripts / "route_input.py")], env={**os.environ, "MEDIFORCE_OUTPUT_DIR": str(output)},
                               capture_output=True, text=True)
    return completed.returncode, json.loads((output / "result.json").read_text())


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        with_usdm = {"files": [USDM, PROTOCOL, SDTM]}
        code, result = route(work, {"package": with_usdm, "steps": {}})
        assert code == 0 and result["target"] == "plan-tlfs" and result["package"] == with_usdm, result

        with_protocol = {"files": [PROTOCOL, SDTM]}
        code, result = route(work, {"package": with_protocol, "steps": {}})
        assert code == 0 and result["target"] == "digitize-protocol" and result["package"] == with_protocol, result

        code, result = route(work, {"package": {}, "steps": {}})
        assert code == 0 and result["target"] == "plan-tlfs" and result["package"] == {}, result

        digitized = {"files": [PROTOCOL, SDTM, USDM]}
        back = {"route-input": result, "digitize-protocol": {"status": "completed", "output": {"outcome": "digitized", "package": digitized}}}
        code, result = route(work, {"package": with_protocol, "steps": back})
        assert code == 0 and result["target"] == "plan-tlfs" and result["package"] == digitized, result

        empty = {"digitize-protocol": {"status": "completed", "output": {"outcome": "digitized", "package": with_protocol}}}
        code, result = route(work, {"package": with_protocol, "steps": empty})
        assert code != 0 and "returned no USDM" in result["error"], result
    print("ok  test_route_input")


if __name__ == "__main__":
    main()
