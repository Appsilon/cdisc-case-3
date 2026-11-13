"""Paths and the program contract shared by the derive-adam steps.

Every step of a run mounts the same worktree at /workspace, so the steps meet in
one folder:

    /workspace/derive-adam/
        inputs/sdtm/<domain>.xpt        staged SDTM (lower-case names)
        inputs/adam-spec.json           the ADaM spec that drives the derivation
        inputs/define.xml               SDTM define, when supplied
        inputs/core-findings.json       fix loop: the findings the reviewer marked 'fix'
        inputs/previous-lineage.json    fix loop: the lineage of the programs that ran
        feedback.json                   what the last gate rejected, for the agent
        attempts.json                   how many times the programs have been executed
    /workspace/programs/<dataset>.R     written by the agent (the only AI output)

Program contract (enforced by execute-programs and check-lineage):
  * one program per ADaM dataset, named after it: adsl.R, adae.R, adlbc.R
    (setup.R, if present, is a helper and produces no dataset);
  * reads SDTM from Sys.getenv("SDTM_DIR") and other ADaM from
    readRDS(file.path(Sys.getenv("ADAM_DIR"), "adsl.rds"));
  * ends with saveRDS(<data frame>, file.path(Sys.getenv("ADAM_DIR"), "<dataset>.rds"));
  * `# @depends ADSL ADAE` lists the ADaM datasets it reads (ADSL is implied for
    every program but adsl.R);
  * every output column carries exactly one tag naming the code that makes it:
        # @derive ADSL.TRTSDT origin=Derived src=EX.EXSTDTC method="First exposure date"
        # @derive ADSL.AGE,ADSL.SEX,ADSL.RACE origin=Predecessor src=DM.*
    Consecutive tag lines share the code block below them; the block ends at a
    blank line, the next tag, or a `# ----` section rule.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path

WORKSPACE_DIR = Path(os.environ.get("MEDIFORCE_WORKSPACE_DIR", "/workspace"))
WORK_DIR = WORKSPACE_DIR / "derive-adam"
INPUTS_DIR = WORK_DIR / "inputs"
SDTM_DIR = INPUTS_DIR / "sdtm"
PROGRAMS_DIR = WORKSPACE_DIR / "programs"
FEEDBACK_PATH = WORK_DIR / "feedback.json"
ATTEMPTS_PATH = WORK_DIR / "attempts.json"
# Scratch of one execution (rds, manifests, SDTM inventory); the self-check points it elsewhere.
RUN_DIR = Path(os.environ.get("ADAM_RUN_DIR", str(WORK_DIR / "run")))
SDTM_COLUMNS_PATH = RUN_DIR / "sdtm-columns.json"
MAX_ATTEMPTS = 3
# The agent runs the gates itself before finishing; that must not use up an attempt or leave feedback.
SELF_CHECK = os.environ.get("ADAM_SELF_CHECK") == "1"
HELPER_PROGRAMS = ("setup.R",)
# Define-XML 2.1 origin types.
ORIGINS = ("Collected", "Derived", "Assigned", "Protocol", "Predecessor")

TAG = re.compile(r"^\s*#\s*@derive\s+(?P<body>.+?)\s*$")
DEPENDS = re.compile(r"^\s*#\s*@depends\s+(?P<body>.+?)\s*$", re.IGNORECASE)
SECTION_RULE = re.compile(r"^\s*#\s*-{4,}")


def dataset_programs() -> dict[str, Path]:
    """ADaM dataset name -> its program, for every program in the programs folder."""
    if PROGRAMS_DIR.is_dir() is False:
        return {}
    return {
        path.stem.upper(): path
        for path in sorted(PROGRAMS_DIR.glob("*.R"))
        if path.name not in HELPER_PROGRAMS
    }


def depends_on(program: Path) -> list[str]:
    found = []
    for line in program.read_text(encoding="utf-8", errors="replace").splitlines():
        match = DEPENDS.match(line)
        if match is not None:
            found.extend(name.strip().upper() for name in re.split(r"[\s,]+", match.group("body")) if name.strip())
    if program.stem.upper() != "ADSL":
        found.append("ADSL")
    return sorted(set(found) - {program.stem.upper()})


def execution_order(programs: dict[str, Path]) -> list[str]:
    """Datasets in dependency order; raises ValueError on a cycle or an unknown dependency."""
    pending = {name: [dep for dep in depends_on(path) if dep != "ADSL" or "ADSL" in programs] for name, path in programs.items()}
    unknown = sorted({f"{name} -> {dep}" for name, deps in pending.items() for dep in deps if dep not in programs})
    if unknown:
        raise ValueError("@depends names datasets that have no program: " + ", ".join(unknown))
    order: list[str] = []
    while pending:
        ready = sorted(name for name, deps in pending.items() if all(dep in order for dep in deps))
        if not ready:
            raise ValueError("@depends forms a cycle between " + ", ".join(sorted(pending)))
        order.extend(ready)
        for name in ready:
            del pending[name]
    return order


def parse_tag(body: str) -> dict:
    """`ADSL.A,ADSL.B origin=Derived src=EX.X method="..."` -> {targets, origin, sources, method, spec}."""
    parts = shlex.split(body)
    if not parts:
        raise ValueError("empty @derive tag")
    targets = [target.strip().upper() for target in parts[0].split(",") if target.strip()]
    fields = {}
    for part in parts[1:]:
        if "=" not in part:
            raise ValueError(f"'{part}' is not key=value")
        key, value = part.split("=", 1)
        fields[key.strip().lower()] = value.strip()
    unknown = set(fields) - {"origin", "src", "spec", "method"}
    if unknown:
        raise ValueError(f"unknown field(s) {', '.join(sorted(unknown))}")
    return {
        "targets": targets,
        "origin": fields.get("origin", ""),
        "sources": [source.strip().upper() for source in fields.get("src", "").split(",") if source.strip()],
        "spec": fields.get("spec", ""),
        "method": fields.get("method", ""),
    }


def read_tags(program: Path) -> tuple[list[dict], list[str]]:
    """Every tagged block of a program: [{tag fields, lines: [first, last], code}], plus syntax problems."""
    lines = program.read_text(encoding="utf-8", errors="replace").splitlines()
    blocks: list[dict] = []
    problems: list[str] = []
    index = 0
    while index < len(lines):
        if TAG.match(lines[index]) is None:
            index += 1
            continue
        tags = []
        while index < len(lines) and TAG.match(lines[index]) is not None:
            body = TAG.match(lines[index]).group("body")
            try:
                tags.append((index + 1, parse_tag(body)))
            except ValueError as error:
                problems.append(f"{program.name}:{index + 1}: bad @derive tag ({error}): {lines[index].strip()}")
            index += 1
        first = index
        while index < len(lines) and lines[index].strip() != "" and TAG.match(lines[index]) is None and SECTION_RULE.match(lines[index]) is None:
            index += 1
        if index == first:
            problems.append(f"{program.name}:{tags[0][0] if tags else first}: @derive tag is not followed by code")
            continue
        code = "\n".join(lines[first:index])
        for line_number, tag in tags:
            blocks.append({**tag, "tagLine": line_number, "lines": [first + 1, index], "code": code})
    return blocks, problems


def resolve_sources(variable: str, sources: list[str]) -> list[str]:
    """`DM.*` -> `DM.<variable>`: a Predecessor copied under its own name."""
    return [f"{source[:-2]}.{variable}" if source.endswith(".*") else source for source in sources]


def attempts() -> int:
    if ATTEMPTS_PATH.is_file() is False:
        return 0
    return int(json.loads(ATTEMPTS_PATH.read_text(encoding="utf-8")).get("attempts", 0))


def count_attempt() -> int:
    if SELF_CHECK is True:
        return attempts()
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    attempt = attempts() + 1
    ATTEMPTS_PATH.write_text(json.dumps({"attempts": attempt}), encoding="utf-8")
    return attempt


def gate(step: str, problems: list[str]) -> dict:
    """The routing half of a gate result: send the programs back to the agent while attempts remain."""
    attempt = attempts()
    if SELF_CHECK is False and problems:
        FEEDBACK_PATH.write_text(json.dumps({"step": step, "attempt": attempt, "problems": problems}, indent=2), encoding="utf-8")
    elif SELF_CHECK is False:
        FEEDBACK_PATH.unlink(missing_ok=True)
    return {
        "needsFix": bool(problems),
        "retry": bool(problems) and attempt < MAX_ATTEMPTS,
        "attempt": attempt,
        "problems": problems,
    }
