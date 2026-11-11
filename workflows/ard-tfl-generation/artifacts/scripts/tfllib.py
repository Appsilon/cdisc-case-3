"""Paths, the program contract and the ARD <-> display reconciliation for ard-tfl-generation.

Every step of a run mounts the same worktree at /workspace:

    /workspace/ard-tfl-generation/
        inputs/adam/<dataset>.xpt          staged ADaM (lower-case names)
        inputs/analysis-spec.json          one entry per planned output (table_id)
        inputs/reporting-event.json        the CDISC ARS ReportingEvent
        inputs/tlf-plan.json               titles and output types
        inputs/lineage.json                ADaM variable -> program lines, when supplied
        inputs/adam-columns.json           what each ADaM dataset holds (written by stage-inputs)
        feedback.json                      what the last gate rejected, for the agent
        review-feedback.jsonl              every reviewer request, one JSON line each
        attempts.json                      how many times the programs have been executed
        run/{ard,tfl,logs}/                one execution's results
    /workspace/tlf-programs/<final_id>.R   written by the agent (the only AI output)

Program contract (enforced by execute-programs and reconcile):
  * one program per planned output, named after its final_id: T-14-1.01.R, F-14-1.R
    (setup.R, if present, is a helper sourced by the others and produces nothing);
  * the first line is its tag:
        # @tlf T-14-3.01 analysis=AN.T-14-3.01 uses=ADSL.EFFFL,ADQSPHQ.CHG,ADQSPHQ.BASE
    `uses` names every ADaM variable the program reads (the trace to ADaM lineage);
  * reads ADaM only from Sys.getenv("ADAM_DIR") (<dataset>.xpt, haven::read_xpt);
  * writes the ARD to file.path(Sys.getenv("ARD_DIR"), "<final_id>.json"): a JSON array, one
    object per statistic with at least variable, stat_name and stat (number, string or null),
    plus group1 / group1_level / variable_level / context where they apply;
  * writes the display to file.path(Sys.getenv("TFL_DIR"), "<final_id>.html") (tables and
    listings: an HTML <table>), figures to "<final_id>.png" (an .html is optional);
  * computes every number into the ARD first and renders the display from the ARD only,
    rounding half away from zero at display time - reconcile checks every displayed number.
"""

from __future__ import annotations

import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path

from gate import GateLoop

WORKSPACE_DIR = Path(os.environ.get("MEDIFORCE_WORKSPACE_DIR", "/workspace"))
WORK_DIR = WORKSPACE_DIR / "ard-tfl-generation"
INPUTS_DIR = WORK_DIR / "inputs"
ADAM_DIR = INPUTS_DIR / "adam"
PROGRAMS_DIR = WORKSPACE_DIR / "tlf-programs"
ADAM_COLUMNS_PATH = INPUTS_DIR / "adam-columns.json"
RUN_DIR = Path(os.environ.get("TFL_RUN_DIR", str(WORK_DIR / "run")))
SELF_CHECK = os.environ.get("TFL_SELF_CHECK") == "1"
LOOP = GateLoop(WORK_DIR, self_check=SELF_CHECK)
HELPER_PROGRAMS = ("setup.R",)
MAX_PROBLEMS_PER_OUTPUT = 8

TAG = re.compile(r"^\s*#\s*@tlf\s+(?P<id>[TLF]-[0-9A-Za-z.\-]+)(?P<rest>.*)$")
FIELD = re.compile(r"(?P<key>analysis|uses)=(?P<value>\S+)")
NUMBER = re.compile(r"(?<![\w.<>≤≥])-?\d+(?:\.\d+)?(?![\w.])")
ADAM_VARIABLE = re.compile(r"^(AD[A-Z0-9]{1,6})\.([A-Z][A-Z0-9_]{0,7})$")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def planned_outputs(inputs_dir: Path = INPUTS_DIR) -> dict[str, dict]:
    """final_id -> {type, title} for every planned output that has an analysis-spec entry (table_id = final_id)."""
    plan = read_json(inputs_dir / "tlf-plan.json")
    specified = {str(entry.get("table_id")) for entry in read_json(inputs_dir / "analysis-spec.json") if isinstance(entry, dict)}
    return {str(item["final_id"]): {"type": item.get("type"), "title": item.get("title")} for item in plan
            if isinstance(item, dict) and item.get("status") == "planned" and str(item.get("final_id")) in specified}


def parse_tag(program: Path) -> tuple[dict | None, str | None]:
    """The @tlf tag on the first line: ({id, analysis, uses}, None) or (None, problem)."""
    first = program.read_text(encoding="utf-8").splitlines()[:1]
    match = TAG.match(first[0]) if first else None
    if match is None:
        return None, f"{program.name}: the first line must be '# @tlf <final_id> analysis=<ARS analysis id> uses=<DS.VAR,...>'"
    fields = {item.group("key"): item.group("value") for item in FIELD.finditer(match.group("rest"))}
    uses = [value for value in fields.get("uses", "").split(",") if value]
    return {"id": match.group("id"), "analysis": fields.get("analysis"), "uses": uses}, None


def ars_analysis_ids(inputs_dir: Path = INPUTS_DIR) -> set[str]:
    event = read_json(inputs_dir / "reporting-event.json")
    return {str(item.get("id")) for item in event.get("analyses") or [] if isinstance(item, dict)}


def program_problems(outputs: dict[str, dict], adam_columns: dict[str, list[str]], analyses: set[str]) -> tuple[list[str], dict[str, dict]]:
    """One tagged program per planned output, tags that resolve. Returns (problems, final_id -> tag)."""
    problems, tags = [], {}
    programs = sorted(path for path in PROGRAMS_DIR.glob("*.R") if path.name not in HELPER_PROGRAMS) if PROGRAMS_DIR.is_dir() else []
    for program in programs:
        tag, problem = parse_tag(program)
        if problem:
            problems.append(problem)
            continue
        if program.stem != tag["id"]:
            problems.append(f"{program.name}: tagged {tag['id']}; a program is named after the output it produces")
            continue
        if tag["id"] not in outputs:
            problems.append(f"{program.name}: {tag['id']} is not a planned, specified output")
            continue
        if not tag["analysis"] or tag["analysis"] not in analyses:
            problems.append(f"{program.name}: analysis={tag['analysis']} is not an analysis in reporting-event.json")
        if not tag["uses"]:
            problems.append(f"{program.name}: uses= must name the ADaM variables the program reads (DS.VAR,...)")
        for variable in tag["uses"]:
            match = ADAM_VARIABLE.match(variable)
            if match is None:
                problems.append(f"{program.name}: uses entry {variable!r} is not DATASET.VARIABLE")
            elif match.group(2) not in adam_columns.get(match.group(1), []):
                problems.append(f"{program.name}: uses {variable}, which the delivered ADaM does not contain")
        tags[tag["id"]] = tag
    missing = sorted(set(outputs) - set(tags) - {program.stem for program in programs})
    if missing:
        problems.append(f"No program for planned output(s) {', '.join(missing)} (expected /workspace/tlf-programs/<final_id>.R)")
    return problems, tags


def ard_problems(final_id: str, ard_path: Path) -> list[str]:
    if ard_path.is_file() is False:
        return [f"{final_id}: wrote no ARD at $ARD_DIR/{final_id}.json"]
    try:
        rows = read_json(ard_path)
    except json.JSONDecodeError as error:
        return [f"{final_id}: ARD is not valid JSON: {error}"]
    if isinstance(rows, list) is False or not rows:
        return [f"{final_id}: ARD must be a non-empty JSON array, one object per statistic"]
    incomplete = [position for position, row in enumerate(rows, start=1)
                  if isinstance(row, dict) is False or not row.get("stat_name") or "stat" not in row or "variable" not in row]
    if incomplete:
        return [f"{final_id}: ARD rows {incomplete[:5]} lack variable / stat_name / stat"]
    return []


class TableCells(HTMLParser):
    """Body cells of every <table>: (row label, column position, text). Header rows (<th> only) are kept as label rows."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[tuple[str, str]]] = []
        self.current: list[tuple[str, str]] | None = None
        self.cell: list[str] | None = None
        self.cell_tag = ""
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "tr":
            self.current = []
        elif tag in ("td", "th") and self.current is not None:
            self.cell, self.cell_tag = [], tag

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in ("td", "th") and self.cell is not None and self.current is not None:
            self.current.append((self.cell_tag, " ".join("".join(self.cell).split())))
            self.cell = None
        elif tag == "tr" and self.current is not None:
            self.rows.append(self.current)
            self.current = None

    def handle_data(self, data):
        if self.cell is not None and self.skip == 0:
            self.cell.append(data)


def displayed_numbers(html_text: str) -> list[tuple[str, str]]:
    """(where, token) for every number in a table body cell; row labels (first cell) and pure header rows excluded."""
    parser = TableCells()
    parser.feed(html_text)
    found = []
    for row in parser.rows:
        if not row or all(tag == "th" for tag, _ in row):
            continue
        label = row[0][1]
        for position, (_, text) in enumerate(row[1:], start=2):
            for match in NUMBER.finditer(text):
                found.append((f"row '{label[:40]}', column {position}", match.group(0)))
    return found


def sas_round(value: float, digits: int) -> float:
    scaled = abs(value) * 10 ** digits
    rounded = int(scaled + 0.5 + 1e-9) / 10 ** digits
    return rounded if value >= 0 else -rounded


def ard_numbers(rows: list[dict]) -> list[float]:
    values = []
    for row in rows:
        stat = row.get("stat")
        candidates = stat if isinstance(stat, list) else [stat]
        for candidate in candidates:
            if isinstance(candidate, bool):
                continue
            try:
                number = float(candidate)
            except (TypeError, ValueError):
                continue
            values.append(number)
            if -1.0 <= number <= 1.0:
                values.append(number * 100)
    return values


def matches_ard(token: str, values: list[float]) -> bool:
    digits = len(token.split(".")[1]) if "." in token else 0
    target = float(token)
    return any(abs(sas_round(value, digits) - target) < 1e-9 for value in values)


def reconcile_output(final_id: str, html_path: Path, ard_path: Path) -> dict:
    """Every number a table shows must be an ARD statistic rounded half away from zero."""
    if html_path.is_file() is False:
        return {"output": final_id, "checked": 0, "unmatched": [], "skipped": "no HTML display (figure)"}
    values = ard_numbers(read_json(ard_path))
    shown = displayed_numbers(html_path.read_text(encoding="utf-8", errors="replace"))
    unmatched = [{"where": where, "value": token} for where, token in shown if matches_ard(token, values) is False]
    return {"output": final_id, "checked": len(shown), "unmatched": unmatched, "skipped": None}
