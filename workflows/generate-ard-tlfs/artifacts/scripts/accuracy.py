"""Accuracy gates on the ARD itself, independent of the agent's programs, driven by the ADaM and the ARS spec.

reconcile proves each displayed number is the ARD row its cell names; these gates check the ARD against the data.
Both read the staged ADaM through one fixed R program (recompute.R, haven) and the ARS ReportingEvent: the
output's analysis (its @tlf tag) -> analysisSet (population on ADSL), dataSubset (record filter on the analysis
dataset: a structured condition / compoundExpression, or a where-clause label like "PARAMCD = 'ALT' AND
ANL01FL = 'Y'"), the treatment grouping (the first orderedGrouping whose variable is TRT01P / TRT01A / TRTP / TRTA /
ARM / ACTARM, in any order; TRTP / TRTA resolve to ADSL TRT01P / TRT01A).

Gate 3 - denominators (tables and figures; listings are exempt):
  * the ARD has one big-N row per displayed column: variable "BIGN", stat_name "N", group1 / group1_level the
    arm ("Total" or no group1 for an overall column);
  * each equals the subjects in ADSL meeting the analysis set, by the ARS grouping variable; every arm with
    subjects has one;
  * the display names every big-N row in a data-ard (the column header), so the shown N is that row;
  * an analysis grouped only by non-treatment variables has its big N not checked;
  * outputs whose analysis set cannot be evaluated must agree with the other outputs on the same ARS analysis set;
  * population-counts.json (from derive-adam), when staged: its total and per-arm counts for the flag are
    compared with ADSL's. A difference is a warning (the approved ADaM disagrees with itself upstream), not a
    problem for the TLF agent.

Gate 4 - independent recompute, for analyses whose ARS method is a simple summary (descriptive, frequency,
incidence, counts). Each numeric ARD row is recomputed over: analysis set, data subset, group1..k (= level), the
row's optional `filter` (a where-clause like the subset label) and variable / variable_level:
    N        subjects (or records) with a non-missing variable, or the arm's big N (cards' denominator N)
    n        subjects (or records) with variable == variable_level (no level: non-missing; level "" or "Missing":
             variable null / blank)
    p        n / the arm's big N or / N (subjects or records), as a fraction or x100 (also pct, percent)
    mean sd median min max   of the variable's non-missing values
A value matches within 1e-6 relative, within 5e-5 absolute, or when the recomputed value rounded to the ARD value's
own decimals is the ARD value (an ARD written at reduced precision; an integer ARD value must be exact). A mismatch
blocks. Anything else - model-based methods, other statistics, a variable or
group that is not an ADaM column, a subset that is not a simple AND of comparisons - is counted as not
independently checked, never failed. Only a row `filter` the program declared that is not such a where-clause
blocks: it is the program's own contract. Coverage = recomputed / numeric ARD statistics.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
import subprocess
import tempfile
from pathlib import Path

from mfpkg import StepFailure
from tfllib import ADAM_DIR, ARD_INDEX, INPUTS_DIR, MAX_PROBLEMS_PER_OUTPUT, TableCells, ard_stat, describe_ard_row, read_json

RECOMPUTE_R = Path(__file__).resolve().parent / "recompute.R"
POPULATION_COUNTS = "population-counts.json"
BIG_N = "BIGN"
MISSING_ARM = "(missing)"
TOTAL_LEVELS = {"total", "overall", "all", "all subjects"}
TREATMENT_ALIASES = {"TRTP": "TRT01P", "TRTA": "TRT01A", "TRTPN": "TRT01PN", "TRTAN": "TRT01AN"}
TREATMENT_VARIABLES = {"TRT01P", "TRT01A", "TRTP", "TRTA", "ARM", "ACTARM"}
MISSING_LEVELS = {"", "missing"}
SIMPLE_METHOD = re.compile(r"descriptive|summary stat|frequenc|incidence|count", re.IGNORECASE)
MODEL_METHOD = re.compile(r"ancova|anova|mmrm|mixed|model|regression|kaplan|surviv|time.to.event|log.?rank|cox|shift|cmh|mantel|test|listing",
                          re.IGNORECASE)
STATISTICS = {"N": "N", "n": "n", "count": "n", "p": "p", "pct": "p", "percent": "p", "mean": "mean", "sd": "sd", "std": "sd",
              "median": "median", "min": "min", "minimum": "min", "max": "max", "maximum": "max"}
TOLERANCE = 1e-6
ROUNDING_SLACK = 5e-5
OPERATORS = {"=": "EQ", "==": "EQ", "EQ": "EQ", "!=": "NE", "<>": "NE", "^=": "NE", "NE": "NE", ">": "GT", "GT": "GT", ">=": "GE",
             "GE": "GE", "<": "LT", "LT": "LT", "<=": "LE", "LE": "LE"}
ARS_COMPARATORS = {"EQ", "NE", "GT", "GE", "LT", "LE", "IN", "NOTIN"}
LITERAL = r"'[^']*'|\"[^\"]*\"|-?\d+(?:\.\d+)?"
CLAUSE = re.compile(rf"""^\(?\s*(?P<variable>[A-Za-z][A-Za-z0-9_]*)\s*(?:
      IS\s+(?P<negated>NOT\s+)?NULL
    | (?P<excluded>NOT\s+)?IN\s*\((?P<members>[^()]*)\)
    | (?P<operator>==|!=|<>|\^=|>=|<=|=|>|<|EQ|NE|GT|GE|LT|LE)\s*(?P<value>{LITERAL})
    )\s*\)?$""", re.IGNORECASE | re.VERBOSE)
MEMBER = re.compile(LITERAL)
CONNECTIVE = re.compile(r"'[^']*'|\"[^\"]*\"|(?P<conjunction>\s+AND\s+|\s*&&?\s*)|(?P<disjunction>\bOR\b|\|)", re.IGNORECASE)


def literal(token: str):
    if token[:1] in ("'", '"'):
        return token[1:-1]
    number = float(token)
    return int(number) if number.is_integer() else number


def parse_where(text) -> list[dict] | None:
    """A where-clause (AND of comparisons, IN lists, IS [NOT] NULL) as conditions; [] for none / '(all ...)'; None when unsupported."""
    text = str(text or "").strip()
    if not text or (text.startswith("(") and text.endswith(")") and re.search(r"\ball\b", text, re.IGNORECASE)):
        return []
    clauses, start = [], 0
    for match in CONNECTIVE.finditer(text):
        if match.group("disjunction"):
            return None
        if match.group("conjunction"):
            clauses.append(text[start:match.start()])
            start = match.end()
    conditions = []
    for clause in clauses + [text[start:]]:
        match = CLAUSE.match(clause.strip())
        if match is None:
            return None
        variable = match.group("variable").upper()
        if match.group("operator"):
            conditions.append({"variable": variable, "comparator": OPERATORS[match.group("operator").upper()],
                               "values": [literal(match.group("value"))]})
        elif match.group("members") is not None:
            members = [literal(member) for member in MEMBER.findall(match.group("members"))]
            conditions.append({"variable": variable, "comparator": "NOTIN" if match.group("excluded") else "IN", "values": members})
        else:
            conditions.append({"variable": variable, "comparator": "NOTNULL" if match.group("negated") else "ISNULL", "values": []})
    return conditions


def ars_conditions(entity: dict | None) -> list[dict] | None:
    """An ARS analysisSet / dataSubset / whereClause as conditions (AND only); falls back to its label as a where-clause."""
    if not isinstance(entity, dict):
        return None
    condition = entity.get("condition")
    if isinstance(condition, dict) and condition.get("variable"):
        comparator = str(condition.get("comparator") or "").upper()
        if comparator not in ARS_COMPARATORS:
            return None
        values = condition.get("value")
        return [{"variable": str(condition["variable"]).upper(), "comparator": comparator,
                 "values": values if isinstance(values, list) else [values]}]
    compound = entity.get("compoundExpression")
    if isinstance(compound, dict):
        if str(compound.get("logicalOperator") or "").upper() != "AND":
            return None
        parts = [ars_conditions(clause) for clause in compound.get("whereClauses") or []]
        return None if any(part is None for part in parts) or not parts else [item for part in parts for item in part]
    if entity.get("label"):
        return parse_where(entity["label"])
    return None


def describe_conditions(conditions: list[dict] | None) -> str:
    if conditions is None:
        return "(not evaluable)"
    return " AND ".join(f"{item['variable']} {item['comparator']} {','.join(map(str, item['values']))}".strip() for item in conditions) or "all"


def level_text(value) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def is_total(group, level) -> bool:
    return group in (None, "") or level in (None, "") or level_text(level).lower() in TOTAL_LEVELS


def close(first: float, second: float) -> bool:
    return abs(first - second) <= TOLERANCE * max(1.0, abs(second))


def decimals(value: float) -> int:
    return max(0, -Decimal(repr(float(value))).normalize().as_tuple().exponent)


def matches(ard_value: float, recomputed: float) -> bool:
    """The ARD value is the recomputed one, allowing for the ARD having been written at reduced precision."""
    if close(ard_value, recomputed) is True or abs(ard_value - recomputed) <= ROUNDING_SLACK:
        return True
    places = decimals(ard_value)
    return places > 0 and close(ard_value, round(recomputed, places)) is True


class Context:
    """What the ARS says one analysis is computed over, resolved against the delivered ADaM columns."""

    def __init__(self, event: dict, analysis_id: str | None, columns: dict[str, list[str]]):
        def by_id(collection: str) -> dict:
            return {item.get("id"): item for item in event.get(collection) or [] if isinstance(item, dict)}

        self.columns = columns
        analysis = by_id("analyses").get(analysis_id) or {}
        self.found = bool(analysis)
        self.dataset = str(analysis.get("dataset") or "ADSL").upper()
        analysis_set = by_id("analysisSets").get(analysis.get("analysisSetId"))
        self.set_id = analysis.get("analysisSetId")
        self.population = ars_conditions(analysis_set) if analysis_set else None
        subset_id = analysis.get("dataSubsetId")
        self.subset = ars_conditions(by_id("dataSubsets").get(subset_id)) if subset_id else []
        ordered = sorted(analysis.get("orderedGroupings") or [], key=lambda item: item.get("order") or 0)
        groupings = [by_id("analysisGroupings").get(item.get("groupingId")) for item in ordered]
        self.grouped = len(groupings) > 0
        grouping = next((item for item in groupings if isinstance(item, dict) and self.treatment(item.get("groupingVariable"))), None)
        self.grouping_id = (grouping or {}).get("id")
        self.grouping_raw = str((grouping or {}).get("groupingVariable") or "").upper().split(".")[-1] or None
        self.grouping = self.resolve(self.grouping_raw, "ADSL") if self.grouping_raw else None
        method = by_id("methods").get(analysis.get("methodId")) or {}
        self.method = str(method.get("name") or analysis.get("methodId") or "")
        method_text = f"{method.get('id') or ''} {method.get('name') or ''}"
        self.simple = SIMPLE_METHOD.search(method_text) is not None and MODEL_METHOD.search(method_text) is None

    @staticmethod
    def treatment(variable) -> bool:
        return str(variable or "").upper().split(".")[-1] in TREATMENT_VARIABLES

    def resolve(self, variable, dataset: str | None = None) -> str | None:
        """The ADaM column a variable name means: in the analysis dataset or ADSL, TRTP / TRTA as ADSL TRT01P / TRT01A."""
        name = str(variable or "").upper()
        for candidate in (name, TREATMENT_ALIASES.get(name)):
            if candidate and (candidate in self.columns.get(dataset or self.dataset, []) or candidate in self.columns.get("ADSL", [])):
                return candidate
        return None

    def group_variable(self, group) -> str | None:
        name = str(group or "").upper()
        if self.grouping is not None and name in (self.grouping_raw, self.grouping, TREATMENT_ALIASES.get(name)):
            return self.grouping
        return self.resolve(name)


class Requests:
    """Aggregates to compute in one R run, de-duplicated by content."""

    def __init__(self):
        self.items: dict[str, dict] = {}
        self.results: dict[str, dict] = {}

    def add(self, **request) -> str:
        key = json.dumps(request, sort_keys=True)
        self.items.setdefault(key, {"key": key, **request})
        return key

    def run(self, adam_dir: Path) -> None:
        if len(self.items) == 0:
            return
        with tempfile.TemporaryDirectory() as scratch:
            plan, target = Path(scratch) / "plan.json", Path(scratch) / "result.json"
            plan.write_text(json.dumps({"adamDir": str(adam_dir), "requests": list(self.items.values())}), encoding="utf-8")
            completed = subprocess.run(["Rscript", "--vanilla", str(RECOMPUTE_R), str(plan), str(target)], capture_output=True, text=True)
            if completed.returncode != 0 or target.is_file() is False:
                raise StepFailure("The accuracy recompute (recompute.R) failed: " + completed.stderr.strip()[-800:])
            loaded = json.loads(target.read_text(encoding="utf-8"))
            self.results = loaded if isinstance(loaded, dict) else {}

    def __getitem__(self, key: str) -> dict:
        return self.results.get(key) or {"error": "no result"}


def referenced_rows(html_text: str) -> set[int]:
    parser = TableCells()
    parser.feed(html_text)
    return {int(reference) for row in parser.rows for _, _, refs in row if refs
            for reference in (part.strip() for part in refs.split(",")) if ARD_INDEX.fullmatch(reference) is not None}


def population_request(requests: Requests, context: Context) -> str:
    return requests.add(dataset="ADSL", population=context.population, where=[], variable=None, level=None, tabulate=context.grouping)


def big_n_expected(result: dict, context: Context, row: dict) -> int | None:
    if is_total(row.get("group1"), row.get("group1_level")) or context.grouping is None:
        return result.get("subjects")
    counts = result.get("counts") if isinstance(result.get("counts"), dict) else {}
    return int(counts.get(level_text(row.get("group1_level")), 0))


def denominator_check(final_id: str, output_type: str, context: Context, rows: list, html_path: Path, requests: Requests) -> dict:
    big_n = [(index, row) for index, row in enumerate(rows) if isinstance(row, dict) and row.get("variable") == BIG_N]
    report = {"status": "not checked", "analysisSet": context.set_id, "population": describe_conditions(context.population),
              "grouping": context.grouping, "expected": {}, "ard": {level_text(row.get("group1_level") or "Total"): ard_stat(row) for _, row in big_n},
              "problems": []}
    if output_type.lower().startswith("listing"):
        report["reason"] = "listing"
        return report
    if len(big_n) == 0:
        report["status"] = "fail"
        report["problems"].append(f"{final_id}: the ARD has no big-N rows - add one row per displayed column with variable='BIGN', "
                                  "stat_name='N', group1=<treatment variable>, group1_level=<arm> (or 'Total') and name it in the "
                                  "column header's data-ard")
        return report
    if context.found is False or context.population is None:
        report["reason"] = "the ARS analysis or its analysis-set condition cannot be evaluated"
        return report
    if context.grouped is True and context.grouping_id is None:
        report["reason"] = "none of the ARS analysis groupings is a treatment variable (" + "/".join(sorted(TREATMENT_VARIABLES)) + ")"
        return report
    if context.grouping is None and any(is_total(row.get("group1"), row.get("group1_level")) is False for _, row in big_n):
        report["reason"] = "big N by arm, but the ARS analysis has no ADSL grouping variable"
        return report
    result = requests[population_request(requests, context)]
    if "error" in result:
        report["reason"] = f"recompute failed: {result['error']}"
        return report
    counts = result.get("counts") if isinstance(result.get("counts"), dict) else {}
    report["expected"] = {**({level: int(count) for level, count in counts.items()} if context.grouping else {}), "Total": result.get("subjects")}
    where = f"ADSL subjects with {describe_conditions(context.population)}"
    for index, row in big_n:
        expected, stat = big_n_expected(result, context, row), ard_stat(row)
        column = level_text(row.get("group1_level") or "Total")
        if stat is None or expected is None or close(stat, expected) is False:
            report["problems"].append(f"{final_id}: big N for {column} is {level_text(stat)} in ARD row {index}, but {where}"
                                      + (f" and {context.grouping} = {column}" if is_total(row.get("group1"), row.get("group1_level")) is False else "")
                                      + f" number {expected} (ARS {context.set_id})")
    if context.grouping is not None:
        shown = {level_text(row.get("group1_level")) for _, row in big_n}
        absent = sorted(level for level, count in counts.items() if int(count) > 0 and level not in shown)
        if absent:
            report["problems"].append(f"{final_id}: no big-N row for {', '.join(absent)} ({context.grouping}), which has subjects in {where}")
    if html_path.is_file():
        referenced = referenced_rows(html_path.read_text(encoding="utf-8", errors="replace"))
        hidden = [index for index, _ in big_n if index not in referenced]
        if hidden:
            report["problems"].append(f"{final_id}: big-N ARD row(s) {hidden} are not shown - name each in its column header's data-ard "
                                      "(e.g. <th data-ard='0'>Placebo (N=86)</th>)")
    report["status"] = "fail" if report["problems"] else "pass"
    return report


def consistency_problems(reports: dict[str, dict], contexts: dict[str, Context]) -> list[str]:
    """Outputs whose own analysis set could not be evaluated must show the N of the others on the same ARS analysis set."""
    problems, reference = [], {}
    for final_id in sorted(reports, key=lambda item: reports[item]["status"] == "not checked"):
        report, context = reports[final_id], contexts[final_id]
        if not report["ard"] or report.get("reason") == "listing" or context.set_id is None:
            continue
        key = (context.set_id, context.grouping_id)
        if key not in reference:
            reference[key] = (final_id, report["ard"])
            continue
        other_id, other = reference[key]
        if report["status"] == "not checked" and any(level in other and other[level] != value for level, value in report["ard"].items()):
            problems.append(f"{final_id}: big N {report['ard']} differs from {other_id} {other} on the same analysis set {context.set_id}")
    return problems


def population_count_warnings(path: Path, reports: dict[str, dict], contexts: dict[str, Context]) -> tuple[list[str], dict]:
    """population-counts.json against ADSL. Both come from the approved ADaM, so a difference is upstream's, not the TLF agent's."""
    if path.is_file() is False:
        return [], {"status": "absent"}
    counts = read_json(path)
    populations = counts.get("populations") or {}
    arm_variable = str(counts.get("armVariable") or "").upper()
    warnings, compared = [], []
    for final_id, report in sorted(reports.items()):
        context = contexts[final_id]
        flags = context.population or []
        if report["status"] == "not checked" or len(flags) != 1 or flags[0]["comparator"] != "EQ" or flags[0]["values"] != ["Y"]:
            continue
        flag = flags[0]["variable"]
        declared = populations.get(flag)
        if not isinstance(declared, dict) or (flag, context.grouping) in compared:
            continue
        compared.append((flag, context.grouping))
        expected = report["expected"]
        if declared.get("total") != expected.get("Total"):
            warnings.append(f"{POPULATION_COUNTS}: {flag} total is {declared.get('total')}, but ADSL has {expected.get('Total')} ({final_id})")
        if context.grouping is not None and context.grouping == arm_variable:
            by_arm = {level_text(level): count for level, count in (declared.get("byArm") or {}).items()}
            observed = {level or MISSING_ARM: count for level, count in expected.items() if level != "Total"}
            if {level: count for level, count in by_arm.items() if count} != {level: count for level, count in observed.items() if count}:
                warnings.append(f"{POPULATION_COUNTS}: {flag} by {arm_variable} is {by_arm}, but ADSL has {observed} ({final_id})")
    return warnings, {"status": "compared" if compared else "not applicable", "populations": [flag for flag, _ in compared]}


def recompute_plan(row: dict, context: Context, requests: Requests) -> tuple[dict | None, str | None]:
    """The requests that recompute one ARD row, or (None, why it is not independently checked)."""
    name = str(row.get("stat_name"))
    statistic = STATISTICS.get(name) or STATISTICS.get(name.lower())
    if statistic is None:
        return None, f"statistic {name}"
    variable = context.resolve(row.get("variable"))
    if variable is None:
        return None, f"variable {row.get('variable')} is not an ADaM column"
    where = list(context.subset)
    for number in sorted(int(key[5:]) for key in row if re.fullmatch(r"group[0-9]+", key)):
        group, level = row.get(f"group{number}"), row.get(f"group{number}_level")
        if is_total(group, level):
            continue
        group_variable = context.group_variable(group)
        if group_variable is None:
            return None, f"group {group} is not an ADaM column"
        where.append({"variable": group_variable, "comparator": "EQ", "values": [level]})
    if row.get("filter") not in (None, ""):
        declared = parse_where(row["filter"])
        if declared is None:
            return {"problem": f"filter '{row['filter']}' is not a where-clause of AND-ed comparisons (e.g. PARAMCD = 'ALT' AND AVISITN = 24)"}, None
        where += declared
    level = row.get("variable_level")
    if statistic in ("n", "p") and level is not None and level_text(level).lower() in MISSING_LEVELS:
        kind, level = "missing", None
    elif level in (None, "", "NA"):
        kind, level = "none", None
    else:
        kind = "value"
    counted = where + [{"variable": variable, "comparator": "ISNULL", "values": []}] if kind == "missing" else where
    plan = {"statistic": statistic, "variable": variable, "level": kind, "where": counted,
            "key": requests.add(dataset=context.dataset, population=context.population, where=counted,
                                variable=None if kind == "missing" else variable, level=level, tabulate=None)}
    if statistic in ("N", "p"):
        plan["bign"] = population_request(requests, context)
    if statistic == "p":
        plan["denominator"] = requests.add(dataset=context.dataset, population=context.population, where=where, variable=variable, level=None,
                                           tabulate=None)
    return plan, None


def candidates(plan: dict, row: dict, requests: Requests, context: Context) -> list[tuple[float, str]] | str:
    """Each reading of the ARD row the ADaM supports, as (value, how it was counted)."""
    result = requests[plan["key"]]
    if "error" in result:
        return f"recompute failed: {result['error']}"
    statistic, variable = plan["statistic"], plan["variable"]
    nonmissing = [(result.get("nonmissingSubjects"), f"subjects with {variable} non-missing"),
                  (result.get("nonmissingRecords"), f"records with {variable} non-missing")]
    if plan["level"] == "missing":
        counts = [(result.get("subjects"), f"subjects with {variable} missing"), (result.get("records"), f"records with {variable} missing")]
    elif plan["level"] == "value":
        shown = level_text(row.get("variable_level"))
        counts = [(result.get("levelSubjects"), f"subjects with {variable} = {shown}"), (result.get("levelRecords"), f"records with {variable} = {shown}")]
    else:
        counts = nonmissing
    population = requests[plan["bign"]] if "bign" in plan else {"error": "not needed"}
    arm = None if "error" in population else big_n_expected(population, context, row)
    if statistic == "N":
        readings = nonmissing + [(arm, "the arm's big N")]
    elif statistic == "n":
        readings = counts
    elif statistic == "p":
        whole = requests[plan["denominator"]]
        denominators = [(arm, "the arm's big N"), (whole.get("nonmissingSubjects"), f"subjects with {variable} non-missing"),
                        (whole.get("nonmissingRecords"), f"records with {variable} non-missing")]
        if plan["level"] == "missing":
            denominators += [(whole.get("subjects"), "all subjects"), (whole.get("records"), "all records")]
        readings = [(numerator / denominator * scale, f"{numerator_label} ({numerator:g}) / {denominator_label} ({denominator:g})"
                     + (" x 100" if scale == 100 else ""))
                    for numerator, numerator_label in counts for denominator, denominator_label in denominators for scale in (1, 100)
                    if numerator is not None and denominator not in (None, 0)]
    else:
        readings = [(result.get(statistic), f"{statistic} of {variable} over its non-missing values")]
    return [(float(value), label) for value, label in readings if value is not None] or "not computable from the ADaM"


def recompute_check(final_id: str, context: Context, rows: list, requests: Requests, plans: list) -> dict:
    report = {"method": context.method, "statistics": 0, "recomputed": 0, "mismatches": [], "notChecked": {}, "problems": []}
    numeric = [(index, row) for index, row in enumerate(rows) if isinstance(row, dict) and row.get("variable") != BIG_N and ard_stat(row) is not None]
    report["statistics"] = len(numeric)
    if context.found is False or context.simple is False:
        reason = f"method {context.method or 'unknown'} is not a simple summary" if context.found else "no ARS analysis"
        report["notChecked"] = {reason: len(numeric)} if numeric else {}
        return report
    if context.population is None or context.subset is None:
        report["notChecked"] = {"analysis set or data subset is not an AND of comparisons": len(numeric)} if numeric else {}
        return report
    for index, row in numeric:
        plan, reason = recompute_plan(row, context, requests)
        if plan is not None and "problem" in plan:
            report["problems"].append(f"{final_id}: ARD row {index}: {plan['problem']}")
        elif plan is None:
            report["notChecked"][reason] = report["notChecked"].get(reason, 0) + 1
        else:
            plans.append((index, row, plan))
    return report


def evaluate_recompute(final_id: str, report: dict, plans: list, requests: Requests, context: Context) -> None:
    for index, row, plan in plans:
        readings = candidates(plan, row, requests, context)
        if isinstance(readings, str):
            report["notChecked"][readings] = report["notChecked"].get(readings, 0) + 1
            continue
        report["recomputed"] += 1
        stat = ard_stat(row)
        if any(matches(stat, value) is True for value, _ in readings):
            continue
        scope = f"{context.dataset} records of ADSL subjects with {describe_conditions(context.population)}, where {describe_conditions(plan['where'])}"
        report["mismatches"].append({"row": index, "ard": stat, "recomputed": readings[0][0], "reading": readings[0][1], "scope": scope})
        shown = "; ".join(f"{value:g} = {label}" for value, label in readings[:4])
        report["problems"].append(f"{final_id}: ARD row {index} ({describe_ard_row(row)}) is {stat:g}, but recomputing {plan['statistic']} "
                                  f"independently from {scope} gives {shown} - fix the computation, or declare a narrower slice in the "
                                  "row's filter")


def accuracy_gate(outputs: dict[str, dict], tags: dict[str, dict], folder: Path, inputs_dir: Path = INPUTS_DIR,
                  adam_dir: Path = ADAM_DIR) -> tuple[list[str], dict]:
    """Gates 3 and 4 over every executed output. Returns (problems for the agent, the accuracy.json report with its warnings)."""
    event = read_json(inputs_dir / "reporting-event.json")
    columns = read_json(inputs_dir / "adam-columns.json")
    requests = Requests()
    contexts, ards, plans = {}, {}, {}
    for final_id in sorted(tags):
        contexts[final_id] = Context(event, tags[final_id].get("analysis"), columns)
        ards[final_id] = read_json(folder / "ard" / f"{final_id}.json")
        if contexts[final_id].population is not None and contexts[final_id].found:
            population_request(requests, contexts[final_id])
    recomputes = {}
    for final_id in sorted(tags):
        plans[final_id] = []
        recomputes[final_id] = recompute_check(final_id, contexts[final_id], ards[final_id], requests, plans[final_id])
    requests.run(adam_dir)

    denominators = {final_id: denominator_check(final_id, str(outputs.get(final_id, {}).get("type") or ""), contexts[final_id], ards[final_id],
                                                folder / "tfl" / f"{final_id}.html", requests) for final_id in sorted(tags)}
    for final_id in sorted(tags):
        evaluate_recompute(final_id, recomputes[final_id], plans[final_id], requests, contexts[final_id])
    global_problems = consistency_problems(denominators, contexts)
    count_warnings, population_counts = population_count_warnings(inputs_dir / POPULATION_COUNTS, denominators, contexts)
    problems = []
    for final_id in sorted(tags):
        found = denominators[final_id]["problems"] + recomputes[final_id]["problems"]
        problems += found[:MAX_PROBLEMS_PER_OUTPUT]
        if len(found) > MAX_PROBLEMS_PER_OUTPUT:
            problems.append(f"{final_id}: {len(found) - MAX_PROBLEMS_PER_OUTPUT} more accuracy problem(s)")
    problems += global_problems
    statistics = sum(item["statistics"] for item in recomputes.values())
    recomputed = sum(item["recomputed"] for item in recomputes.values())
    report = {
        "denominators": denominators,
        "recompute": recomputes,
        "populationCounts": {**population_counts, "warnings": count_warnings},
        "warnings": count_warnings,
        "consistency": global_problems,
        "coverage": {"statistics": statistics, "recomputed": recomputed,
                     "mismatches": sum(len(item["mismatches"]) for item in recomputes.values())},
        "summary": {"denominatorsPassed": sum(1 for item in denominators.values() if item["status"] == "pass"),
                    "denominatorsFailed": sum(1 for item in denominators.values() if item["status"] == "fail"),
                    "denominatorsNotChecked": sum(1 for item in denominators.values() if item["status"] == "not checked")},
    }
    return problems, report
