"""Is the delivered SDTM the study the USDM describes?

CORE checks SDTM conformance, not whether the data is this protocol's: 18
conformant subjects of another study pass it. These checks compare the SDTM
with the USDM (the protocol) and need nothing else:

    arm-count   DM has as many arms (randomised subjects) as the USDM            fail
    arms        DM arm names / codes == USDM arm names / labels                  warn
    enrollment  randomised subjects within 50-150 % of plannedEnrollmentNumber  fail
    exposure    at least one randomised subject has an EX record                 fail
    trial-arms  TA arms == USDM arms                                             warn
    plansub     TS PLANSUB == plannedEnrollmentNumber                            warn
    title       TS TITLE shares most words with a USDM title                     warn
    phase       TS TPHASE == the USDM study phase                                warn

study_facts() reads DM / EX / TS / TA with R haven (every image carries R; an
unreadable dataset counts as not delivered);
check_study() returns {failed, checks: [{check, status: pass|warn|fail, detail}], counts}.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from arms import is_randomised, normalise_arm
from mfpkg import StepFailure

ENROLLMENT_BAND = (0.5, 1.5)
DOMAINS = {"DM": ["STUDYID", "USUBJID", "ARMCD", "ARM"], "EX": ["USUBJID"], "TS": ["TSPARMCD", "TSVAL"], "TA": ["ARMCD", "ARM"]}
FACTS_R = r'''
arguments <- commandArgs(TRUE)
output <- arguments[1]
wanted <- jsonlite::fromJSON(arguments[2])
paths <- arguments[-(1:2)]
as_utf8 <- function(values) {
  values <- as.character(values)
  broken <- !is.na(values) & !validUTF8(values)
  values[broken] <- iconv(values[broken], "latin1", "UTF-8")
  values
}
facts <- list()
for (path in paths) {
  domain <- toupper(tools::file_path_sans_ext(basename(path)))
  if (!(domain %in% names(wanted))) next
  data <- tryCatch(if (grepl("\\.xpt$", path, ignore.case = TRUE)) haven::read_xpt(path) else haven::read_sas(path),
                   error = function(problem) NULL)
  if (is.null(data)) next
  columns <- intersect(wanted[[domain]], names(data))
  facts[[domain]] <- lapply(setNames(columns, columns), function(column) I(as_utf8(data[[column]])))
}
jsonlite::write_json(facts, output, auto_unbox = TRUE, na = "null")
'''


def study_facts(paths: list[Path]) -> dict:
    """{DOMAIN: {COLUMN: [values per record]}} for the columns the checks need."""
    chosen = [path for path in paths if path.stem.upper() in DOMAINS]
    if len(chosen) == 0:
        return {}
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "facts.json"
        program = Path(temporary) / "facts.R"
        program.write_text(FACTS_R, encoding="utf-8")
        completed = subprocess.run(["Rscript", "--vanilla", str(program), str(target), json.dumps(DOMAINS), *map(str, chosen)],
                                   capture_output=True, text=True)
        if completed.returncode != 0 or target.is_file() is False:
            raise StepFailure("Could not read DM / EX / TS / TA for the study check: " + completed.stderr.strip()[-800:])
        return json.loads(target.read_text(encoding="utf-8"))


def words(text: object) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", str(text or "").lower().replace("'", "")) if len(word) > 2}


def design_of(usdm: dict) -> tuple[dict, dict]:
    version = ((usdm.get("study") or {}).get("versions") or [{}])[0]
    designs = version.get("studyDesigns") or [{}]
    return version, designs[0]


def planned_enrollment(design: dict) -> tuple[float, float] | None:
    population = design.get("population") or {}
    quantity = population.get("plannedEnrollmentNumber")
    if isinstance(quantity, dict) is False:
        return None
    if quantity.get("value") is not None:
        return float(quantity["value"]), float(quantity["value"])
    if quantity.get("minValue") is not None and quantity.get("maxValue") is not None:
        bounds = [quantity["minValue"], quantity["maxValue"]]
        values = [float(bound.get("value") if isinstance(bound, dict) else bound) for bound in bounds]
        return min(values), max(values)
    return None


def records(facts: dict, domain: str) -> list[dict]:
    columns = facts.get(domain) or {}
    if len(columns) == 0:
        return []
    length = len(next(iter(columns.values())))
    return [{column: values[position] for column, values in columns.items()} for position in range(length)]


def usdm_arm_names(design: dict) -> dict[str, str]:
    names: dict[str, str] = {}
    for arm in design.get("arms") or []:
        for field in ("name", "label", "description"):
            if arm.get(field):
                names[normalise_arm(arm[field])] = str(arm.get("name"))
    return names


def compare_arms(label: str, data_arms: dict[str, str], usdm_arms: dict[str, str]) -> tuple[bool, str]:
    """data_arms {normalised: as shown}. Each data arm must be a USDM arm and every USDM arm must be in the data."""
    unknown = sorted(shown for key, shown in data_arms.items() if key not in usdm_arms)
    covered = {usdm_arms[key] for key in data_arms if key in usdm_arms}
    missing = sorted(set(usdm_arms.values()) - covered)
    if len(unknown) == 0 and len(missing) == 0:
        return True, f"{label} arms {sorted(data_arms.values())} match the USDM arms."
    parts = []
    if unknown:
        parts.append(f"{label} has arm(s) not in the USDM: {unknown}")
    if missing:
        parts.append(f"USDM arm(s) absent from {label}: {missing}")
    return False, "; ".join(parts) + f" (USDM arms: {sorted(set(usdm_arms.values()))})."


def ts_values(facts: dict, code: str) -> list[str]:
    return [str(row.get("TSVAL")) for row in records(facts, "TS") if row.get("TSPARMCD") == code and row.get("TSVAL")]


def check_study(usdm: dict, facts: dict, sdtm_delivered: bool = True) -> dict:
    version, design = design_of(usdm)
    checks: list[dict] = []

    def add(check: str, status: str, detail: str) -> None:
        checks.append({"check": check, "status": status, "detail": detail})

    demographics = records(facts, "DM")
    if len(demographics) == 0 and sdtm_delivered is False:
        add("sdtm", "warn", "No SDTM was delivered: the plan's feasibility and the study's data are not checked.")
        return {"failed": False, "checks": checks, "counts": {}}
    if len(demographics) == 0:
        add("arm-count", "fail", "SDTM was delivered without a readable DM dataset: the subjects and their arms cannot be checked against the protocol.")
        return {"failed": True, "checks": checks, "counts": {}}

    randomised = [row for row in demographics if is_randomised(row.get("ARMCD"), row.get("ARM")) is True]
    randomised_ids = {row.get("USUBJID") for row in randomised}
    usdm_arms = usdm_arm_names(design)
    data_arms = {normalise_arm(row.get("ARM")): str(row.get("ARM")) for row in randomised}
    usdm_arm_count = len(set(usdm_arms.values()))
    add("arm-count", "pass" if len(data_arms) == usdm_arm_count else "fail",
        f"DM has {len(data_arms)} arm(s) with randomised subjects; the USDM has {usdm_arm_count}.")
    codes = {normalise_arm(row.get("ARMCD")): str(row.get("ARM")) for row in randomised}
    passed, detail = compare_arms("DM", data_arms, usdm_arms)
    if passed is False and set(codes) <= set(usdm_arms):
        passed, detail = True, f"DM arm codes {sorted(codes)} match the USDM arms."
    add("arms", "pass" if passed is True else "warn", detail)

    planned = planned_enrollment(design)
    if planned is None:
        add("enrollment", "warn", f"{len(randomised_ids)} randomised subjects; the USDM has no plannedEnrollmentNumber to compare with.")
    else:
        low, high = planned[0] * ENROLLMENT_BAND[0], planned[1] * ENROLLMENT_BAND[1]
        shown = f"{planned[0]:g}" if planned[0] == planned[1] else f"{planned[0]:g}-{planned[1]:g}"
        inside = low <= len(randomised_ids) <= high
        add("enrollment", "pass" if inside else "fail",
            f"{len(randomised_ids)} randomised subjects vs {shown} planned (accepted {low:g}-{high:g}).")

    exposed = {row.get("USUBJID") for row in records(facts, "EX")} & randomised_ids
    add("exposure", "pass" if len(exposed) > 0 else "fail",
        f"{len(exposed)} of {len(randomised_ids)} randomised subjects have an EX record."
        if facts.get("EX") else "No EX dataset was delivered: no subject can be shown to have been treated.")

    trial_arms = {normalise_arm(row.get("ARM")): str(row.get("ARM")) for row in records(facts, "TA")}
    if trial_arms:
        passed, detail = compare_arms("TA", trial_arms, usdm_arms)
        add("trial-arms", "pass" if passed is True else "warn", detail)

    plansub = ts_values(facts, "PLANSUB")
    if plansub and planned is not None:
        matches = any(planned[0] <= float(value) <= planned[1] for value in plansub if re.fullmatch(r"\d+(\.\d+)?", value))
        add("plansub", "pass" if matches is True else "warn", f"TS PLANSUB {plansub} vs USDM planned enrollment {planned[0]:g}.")

    titles = [str(title.get("text")) for title in version.get("titles") or [] if title.get("text")]
    for value in ts_values(facts, "TITLE")[:1]:
        overlap = max((len(words(value) & words(title)) / max(len(words(value)), 1) for title in titles), default=0.0)
        add("title", "pass" if overlap >= 0.6 else "warn", f"TS TITLE shares {overlap:.0%} of its words with the closest USDM title.")

    phase = ((design.get("studyPhase") or {}).get("standardCode") or {}).get("decode") or ""
    for value in ts_values(facts, "TPHASE")[:1] if phase else []:
        same = normalise_arm(value).replace("trial", "") == normalise_arm(phase).replace("trial", "")
        add("phase", "pass" if same is True else "warn", f"TS TPHASE {value!r} vs USDM study phase {phase!r}.")

    counts = {"subjects": len({row.get("USUBJID") for row in demographics}), "randomised": len(randomised_ids), "exposed": len(exposed),
              "planned": planned[0] if planned else None,
              "byArm": {shown: sum(1 for row in randomised if str(row.get("ARM")) == shown) for shown in sorted(data_arms.values())}}
    return {"failed": any(item["status"] == "fail" for item in checks), "checks": checks, "counts": counts}


def primary_endpoint_ids(usdm: dict) -> dict[str, str]:
    """USDM endpoint id -> text, for endpoints whose level is Primary (C94496)."""
    _, design = design_of(usdm)
    primary: dict[str, str] = {}
    for objective in design.get("objectives") or []:
        for endpoint in objective.get("endpoints") or []:
            level = endpoint.get("level") or {}
            if level.get("code") == "C94496" or "primary" in str(level.get("decode", "")).lower():
                primary[str(endpoint.get("id"))] = str(endpoint.get("text") or endpoint.get("name") or "")
    return primary
