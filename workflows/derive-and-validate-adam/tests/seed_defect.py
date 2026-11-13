"""Build a seeded-defect ADaM delivery for the derive-and-validate-adam acceptance run.

Takes the programs of a green derive-adam run, plants one derivation bug
that the program's own checks miss but CORE (MF-ADAM-008) catches - ADQSPHQ
ANL01FL "N" instead of null on the non-endpoint records, an in-place edit that
keeps every line number and record count - and runs the seeded programs through
the real derive-adam scripts (execute -> lineage -> define), so the delivery
is exactly what the platform would have produced from that code.

The strings match the programs of staging run 8785039f (derive-adam v1);
programs from another run need their own CORRECT line.

  SDTM_DIR=... python3 tests/seed_defect.py <programs-dir> <adam-spec.json> <out-dir>

Writes <out-dir>/{adam/*.xpt, programs/*.R, lineage.json, define.xml}.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "derive-adam" / "tests"))

from test_pipeline import FIXTURES, Run, entry, package_for, r_libraries, without_local  # noqa: E402,F401

PROGRAM = "adqsphq.R"
CORRECT = 'ANL01FL = if_else(ANL02FL == "Y" & AVISITN == endpoint_avisitn, "Y", NA_character_))'
SEEDED = 'ANL01FL = if_else(ANL02FL == "Y" & AVISITN == endpoint_avisitn, "Y", "N"))'


def main() -> None:
    programs, spec, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    os.environ["R_LIBS"] = r_libraries()
    seeded = Path(tempfile.mkdtemp()) / "programs"
    shutil.copytree(programs, seeded)
    program = seeded / PROGRAM
    text = program.read_text(encoding="utf-8")
    if text.count(CORRECT) != 1:
        raise SystemExit(f"Expected the line to seed exactly once in {program}")
    program.write_text(text.replace(CORRECT, SEEDED), encoding="utf-8")

    with tempfile.TemporaryDirectory() as temporary:
        run = Run(Path(temporary) / "seed")
        local_package = package_for(Path(os.environ["SDTM_DIR"]), spec)
        resolved = run.step("resolve-inputs", "resolve_inputs.py", {"package": without_local(local_package)})
        local = {item["name"]: item["localPath"] for item in local_package["files"]}
        run.step("stage-inputs", "stage_inputs.py", files=[{**item, "localPath": local[item["name"]]} for item in resolved["files"]])
        run.agent(seeded)
        executed = run.step("execute-programs", "execute_programs.py")
        assert executed["needsFix"] is False, executed["problems"]
        lineage_gate = run.step("check-lineage", "check_lineage.py")
        assert lineage_gate["needsFix"] is False, lineage_gate["problems"]
        run.step("generate-define", "generate_define.py")

        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        shutil.copytree(run.steps_dir / "execute-programs" / "adam", out / "adam")
        shutil.copytree(run.steps_dir / "execute-programs" / "programs", out / "programs")
        shutil.copyfile(run.steps_dir / "check-lineage" / "lineage.json", out / "lineage.json")
        shutil.copyfile(run.steps_dir / "generate-define" / "define.xml", out / "define.xml")
    print(f"seeded delivery in {out}: {executed['summary']}")


if __name__ == "__main__":
    main()
