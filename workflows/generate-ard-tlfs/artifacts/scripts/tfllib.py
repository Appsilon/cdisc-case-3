"""Paths, the program contract and the ARD <-> display reconciliation for generate-ard-tlfs.

Every step of a run mounts the same worktree at /workspace:

    /workspace/generate-ard-tlfs/
        inputs/adam/<dataset>.xpt          staged ADaM (lower-case names)
        inputs/analysis-spec.json          one entry per planned output (table_id)
        inputs/reporting-event.json        the CDISC ARS ReportingEvent
        inputs/tlf-plan.json               titles and output types
        inputs/lineage.json                ADaM variable -> program lines, when supplied
        inputs/population-counts.json      population flag counts by arm from derive-adam, when supplied
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
    rounding half away from zero at display time - reconcile checks every displayed number;
  * every table body cell that shows numbers names their ARD rows: <td data-ard="12,13">73.6 (9.94)</td>
    = 0-based indices into the ARD array, one per number in the cell, in order. The number must be
    that row's stat rounded half away from zero at the shown decimals (a proportion may be shown
    x100 - always when followed by %); "<0.001" / ">0.999" must bound it. The first cell of a row
    (its label) and <th>-only header rows carry none. Listings show ADaM records, not statistics:
    their cells need no data-ard (any that carry one are checked).
  * big N: one ARD row per displayed column of a table or figure with variable "BIGN", stat_name "N",
    group1 = the treatment variable and group1_level = the arm ("Total", or no group1, for an overall
    column), counted from ADSL with the ARS analysis set. A header cell that shows "N=" names that row:
    <th data-ard="0">Placebo (N=86)</th> (in header rows only the numbers after "N=" are checked);
  * every other ARD row says what it summarises so it can be recomputed from ADaM (accuracy.py): variable
    = the ADaM column, variable_level = the category counted, group1..k / group1_level..k = the ADaM
    grouping columns and values, stat_name N / n / p / mean / sd / median / min / max for those
    statistics; when the statistic covers a narrower slice than the ARS data subset (one parameter, one
    visit), the row's "filter" says which, as a where-clause: "PARAMCD = 'ALT' AND AVISITN = 24".
"""

from __future__ import annotations

import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path

from gate import GateLoop

WORKSPACE_DIR = Path(os.environ.get("MEDIFORCE_WORKSPACE_DIR", "/workspace"))
WORK_DIR = WORKSPACE_DIR / "generate-ard-tlfs"
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
NUMBER = re.compile(r"(?:(?P<bound>[<>≤≥])\s?|(?<![\w.]))(?P<value>[-−]?\d+(?:\.\d+)?)(?![\w.])(?P<percent>\s?%)?")
ARD_INDEX = re.compile(r"[0-9]+")
ADAM_VARIABLE = re.compile(r"^(AD[A-Z0-9]{1,6})\.([A-Z][A-Z0-9_]{0,7})$")
HEADER_N = re.compile(r"\bN\s*=\s*(?P<value>\d+)(?![\w.])")


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
    """Cells of every <table>, per row: (tag, text, data-ard attribute or None)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[tuple[str, str, str | None]]] = []
        self.current: list[tuple[str, str, str | None]] | None = None
        self.cell: list[str] | None = None
        self.cell_tag = ""
        self.cell_refs: str | None = None
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "tr":
            self.current = []
        elif tag in ("td", "th") and self.current is not None:
            self.cell, self.cell_tag, self.cell_refs = [], tag, dict(attrs).get("data-ard")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in ("td", "th") and self.cell is not None and self.current is not None:
            self.current.append((self.cell_tag, " ".join("".join(self.cell).split()), self.cell_refs))
            self.cell = None
        elif tag == "tr" and self.current is not None:
            self.rows.append(self.current)
            self.current = None

    def handle_data(self, data):
        if self.cell is not None and self.skip == 0:
            self.cell.append(data)


def displayed_cells(html_text: str) -> list[dict]:
    """Every table body cell that shows numbers, and every header cell that shows a big N ("N=86"):
    {where, text, numbers: [(bound, token, percent)], refs}. Row labels (first cell) are excluded; in pure
    header rows only the numbers after "N=" count."""
    parser = TableCells()
    parser.feed(html_text)
    found = []
    for row in parser.rows:
        if not row:
            continue
        if all(tag == "th" for tag, _, _ in row):
            for position, (_, text, refs) in enumerate(row, start=1):
                numbers = [("", match.group("value"), False) for match in HEADER_N.finditer(text)]
                if numbers:
                    found.append({"where": f"header '{text[:40]}', column {position}", "text": text, "numbers": numbers, "refs": refs})
            continue
        label = row[0][1]
        for position, (_, text, refs) in enumerate(row[1:], start=2):
            numbers = [(match.group("bound") or "", match.group("value").replace("−", "-"), match.group("percent") is not None)
                       for match in NUMBER.finditer(text)]
            if numbers:
                found.append({"where": f"row '{label[:40]}', column {position}", "text": text, "numbers": numbers, "refs": refs})
    return found


def sas_round(value: float, digits: int) -> float:
    scaled = abs(value) * 10 ** digits
    rounded = int(scaled + 0.5 + 1e-9) / 10 ** digits
    return rounded if value >= 0 else -rounded


def ard_stat(row) -> float | None:
    """The row's stat as one number, or None (missing, text, boolean, several values)."""
    stat = row.get("stat") if isinstance(row, dict) else None
    if isinstance(stat, list) and len(stat) == 1:
        stat = stat[0]
    if stat is None or isinstance(stat, (bool, list, dict)):
        return None
    try:
        return float(stat)
    except (TypeError, ValueError):
        return None


def describe_ard_row(row: dict) -> str:
    keys = ("group1_level", "variable", "variable_level", "context", "stat_name")
    return ", ".join(f"{key}={row[key]}" for key in keys if row.get(key) not in (None, "", []))


def shows_stat(bound: str, token: str, stat: float, percent: bool = False) -> bool:
    """Does the displayed token (with an optional < > ≤ ≥ bound) show this stat? A proportion may be shown x100:
    always when the number is followed by %, otherwise only for an exact (unbounded) proportion that is a fraction or is
    shown with decimals (1 as 100.0, never a count of 1 as 100)."""
    digits = len(token.split(".")[1]) if "." in token else 0
    target = float(token)
    fraction = bound == "" and abs(stat) <= 1.0 and (stat != int(stat) or digits > 0)
    candidates = [stat, stat * 100] if percent is True or fraction is True else [stat]
    comparisons = {"<": lambda value: value < target, "≤": lambda value: value <= target,
                   ">": lambda value: value > target, "≥": lambda value: value >= target,
                   "": lambda value: abs(sas_round(value, digits) - target) < 1e-9}
    return any(comparisons[bound](candidate) for candidate in candidates)


def cell_problems(cell: dict, rows: list) -> list[str]:
    """Why this cell's numbers are not exactly the ARD rows its data-ard names (empty when they are)."""
    numbers, refs = cell["numbers"], cell["refs"]
    if refs is None:
        return [f"shows '{cell['text'][:40]}' without data-ard (the 0-based ARD row of each number)"]
    references = [reference.strip() for reference in refs.split(",") if reference.strip()]
    if all(ARD_INDEX.fullmatch(reference) is not None for reference in references) is False:
        return [f"data-ard='{refs}' is not a comma-separated list of 0-based ARD row indices"]
    if len(references) != len(numbers):
        return [f"shows '{cell['text'][:40]}': {len(numbers)} number(s) but data-ard='{refs}' names {len(references)} ARD row(s)"]
    problems = []
    for (bound, token, percent), reference in zip(numbers, references):
        index = int(reference)
        if index >= len(rows):
            problems.append(f"data-ard index {index} is outside the ARD (rows 0-{len(rows) - 1})")
            continue
        stat = ard_stat(rows[index])
        if stat is None:
            problems.append(f"shows {bound}{token}, but ARD row {index} ({describe_ard_row(rows[index])}) has no single numeric stat")
        elif shows_stat(bound, token, stat, percent) is False:
            problems.append(f"shows {bound}{token}, but ARD row {index} ({describe_ard_row(rows[index])}) is {stat:g}")
    return problems


def reconcile_output(final_id: str, html_path: Path, ard_path: Path, listing: bool = False) -> dict:
    """Every number a table shows must be the ARD row its cell names, rounded half away from zero.
    A listing shows ADaM records, not statistics: only its cells that carry data-ard are checked."""
    if html_path.is_file() is False:
        return {"output": final_id, "checked": 0, "unmatched": [], "skipped": "no HTML display (figure)"}
    rows = read_json(ard_path)
    cells = [cell for cell in displayed_cells(html_path.read_text(encoding="utf-8", errors="replace"))
             if listing is False or cell["refs"] is not None]
    unmatched = [{"where": cell["where"], "value": cell["text"], "problem": problem} for cell in cells for problem in cell_problems(cell, rows)]
    return {"output": final_id, "checked": sum(len(cell["numbers"]) for cell in cells), "unmatched": unmatched, "skipped": None}
