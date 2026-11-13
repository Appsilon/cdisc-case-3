"""ADaM conservation: the executed ADaM against the SDTM it was derived from.

Deterministic and independent of the agent's programs: it re-reads DM, EX and
the exported ADaM (.xpt, with R haven - the image's reader) and checks the
subject-level invariants every analysis denominator rests on:

  * ADSL holds every DM subject, or exactly the randomised ones (shared/arms.py
    is_randomised: DM minus screen failures / not assigned / not randomised by
    ARMCD or ARM, or both blank); one record per subject;
  * SAFFL='Y' == the subjects with an EX record whose EXSTDTC is present (placebo
    EXDOSE = 0 counts as exposed);
  * RANDFL / ITTFL = 'Y' (whichever exist) == the randomised subjects;
  * over the randomised subjects, TRT01P maps one-to-one onto DM.ARM, and over the
    treated ones (ACTARMCD / ACTARM also not Not Treated / Unplanned Treatment)
    TRT01A onto DM.ACTARM (noting the subjects whose ACTARM != ARM), or, as in the
    CDISC pilot ADSL, onto DM.ARM - accepted with a note;
  * every USUBJID of every other ADaM dataset is in ADSL.

DM / EX are inputs: if R cannot read them (or R itself fails) the step fails
(StepFailure). An ADaM .xpt that haven cannot read is the agent's program's
output, so that goes back to the agent as a problem.

It also counts each population flag by arm (population-counts.json), which
ard-tfl-generation stages and compares with the ADSL it reports on:

    {"datasets": {"ADSL": {"records": 254}, ...}, "armVariable": "TRT01A",
     "populations": {"SAFFL": {"total": 254, "byArm": {"Placebo": 86, ...}}, ...}}
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from arms import is_randomised, normalise_arm
from mfpkg import StepFailure

EXAMPLES = 5
MISSING_ARM = "(missing)"
NOT_TREATED = {"nottrt", "nottreated", "unplan", "unplannedtreatment"}
RANDOMISED_FLAGS = ("RANDFL", "ITTFL")
# Reads only the columns the checks need; latin1 strings (some pilot domains) are re-encoded to UTF-8.
READ_R = r'''
arguments <- commandArgs(TRUE)
output <- arguments[1]; sdtm_dir <- arguments[2]; adam_dir <- arguments[3]
clean <- function(column) {
  column <- as.character(column)
  invalid <- !is.na(column) & !validUTF8(column)
  column[invalid] <- iconv(column[invalid], "latin1", "UTF-8")
  column[is.na(column)] <- ""
  I(trimws(column))
}
read <- function(path, wanted) {
  data <- if (grepl("[.]xpt$", path, ignore.case = TRUE)) haven::read_xpt(path) else haven::read_sas(path)
  data[, intersect(wanted(names(data)), names(data)), drop = FALSE]
}
domain_file <- function(name) {
  found <- list.files(sdtm_dir, pattern = paste0("^", name, "[.](xpt|sas7bdat)$"), ignore.case = TRUE, full.names = TRUE)
  if (length(found) == 0) NULL else found[1]
}
columns_of <- function(data) lapply(as.list(data), clean)
sdtm <- list()
dm_path <- domain_file("dm")
if (!is.null(dm_path)) sdtm$DM <- columns_of(read(dm_path, function(names) c("USUBJID", "ARMCD", "ARM", "ACTARMCD", "ACTARM")))
ex_path <- domain_file("ex")
if (!is.null(ex_path)) sdtm$EX <- columns_of(read(ex_path, function(names) c("USUBJID", "EXSTDTC")))
adam <- list()
for (path in list.files(adam_dir, pattern = "[.]xpt$", ignore.case = TRUE, full.names = TRUE)) {
  name <- toupper(tools::file_path_sans_ext(basename(path)))
  adam[[name]] <- tryCatch(
    if (name == "ADSL") {
      data <- read(path, function(names) c("USUBJID", "TRT01P", "TRT01A", grep("FL$", names, value = TRUE)))
      list(records = nrow(data), columns = columns_of(data))
    } else {
      data <- read(path, function(names) "USUBJID")
      subjects <- if ("USUBJID" %in% names(data)) sort(unique(as.character(clean(data$USUBJID)))) else character()
      list(records = nrow(data), hasUsubjid = "USUBJID" %in% names(data), subjects = I(subjects))
    },
    error = function(problem) list(error = conditionMessage(problem)))
}
jsonlite::write_json(list(sdtm = sdtm, adam = adam), output, auto_unbox = TRUE)
'''


def read_datasets(sdtm_dir: Path, adam_dir: Path) -> dict:
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "datasets.json"
        program = Path(temporary) / "read.R"
        program.write_text(READ_R, encoding="utf-8")
        completed = subprocess.run(["Rscript", "--vanilla", str(program), str(target), str(sdtm_dir), str(adam_dir)],
                                   capture_output=True, text=True)
        if completed.returncode != 0 or target.is_file() is False:
            raise StepFailure("Could not read the staged DM / EX for the population checks (R / haven): " + completed.stderr.strip()[-800:])
        return json.loads(target.read_text(encoding="utf-8"))


def gate_populations(sdtm_dir: Path, adam_dir: Path) -> tuple[list[str], list[str], dict]:
    """check() on the datasets. An unreadable DM / EX or a broken R fails the step; an unreadable ADaM .xpt is the agent's."""
    return check(read_datasets(sdtm_dir, adam_dir))


def examples(subjects: set[str]) -> str:
    shown = sorted(subjects)[:EXAMPLES]
    return ", ".join(shown) + (f" ... ({len(subjects)} in all)" if len(subjects) > EXAMPLES else "")


def rows(columns: dict[str, list[str]]) -> list[dict[str, str]]:
    names = list(columns)
    return [dict(zip(names, values)) for values in zip(*(columns[name] for name in names))] if names else []


def mapping_problems(pairs: list[tuple[str, str, str]], source: str, target: str) -> list[str]:
    """(subject, DM value, ADSL value) -> problems unless the values map one-to-one."""
    forward: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    backward: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for subject, dm_value, adam_value in pairs:
        forward[dm_value][adam_value].add(subject)
        backward[adam_value][dm_value].add(subject)
    problems = []
    for start, end, table in ((source, target, forward), (target, source, backward)):
        for value, mapped in sorted(table.items()):
            if len(mapped) > 1:
                parts = "; ".join(f"'{other}' for {len(subjects)} ({examples(subjects)})"
                                  for other, subjects in sorted(mapped.items(), key=lambda item: -len(item[1])))
                problems.append(f"{start} '{value}' maps to more than one {end}: {parts}. "
                                f"{target} must follow {source} through one consistent one-to-one mapping.")
    return problems


def flag_problem(flag: str, flagged: set[str], expected: set[str], label: str, definition: str) -> list[str]:
    if flagged == expected:
        return []
    parts = []
    extra, missing = flagged - expected, expected - flagged
    if extra:
        parts.append(f"flagged but not {label}: {examples(extra)}")
    if missing:
        parts.append(f"{label} but not flagged or not in ADSL: {examples(missing)}")
    detail = "; ".join(parts)
    return [f"ADSL.{flag}='Y' for {len(flagged)} subject(s), but {len(expected)} are {label} ({definition}). {detail[0].upper()}{detail[1:]}."]


def population_counts(adsl: list[dict[str, str]], adam: dict) -> dict:
    columns = list(adsl[0]) if adsl else []
    arm_variable = "TRT01A" if "TRT01A" in columns else ("TRT01P" if "TRT01P" in columns else None)
    populations = {}
    for flag in sorted(column for column in columns if column.endswith("FL")):
        flagged = [row for row in adsl if row[flag] == "Y"]
        if not flagged:
            continue
        by_arm: dict[str, int] = defaultdict(int)
        if arm_variable is not None:
            for row in flagged:
                by_arm[row[arm_variable] or MISSING_ARM] += 1
        populations[flag] = {"total": len(flagged), "byArm": dict(sorted(by_arm.items()))}
    return {"datasets": {name: {"records": item["records"]} for name, item in sorted(adam.items())},
            "populations": populations, "armVariable": arm_variable}


def check(data: dict) -> tuple[list[str], list[str], dict]:
    """(problems, notes, population counts) for the datasets read by read_datasets."""
    adam = data.get("adam") or {}
    sdtm = data.get("sdtm") or {}
    unreadable = {name: item["error"] for name, item in sorted(adam.items()) if "error" in item}
    if unreadable:
        return [f"{name.lower()}.xpt cannot be read with haven::read_xpt: {error}. Re-export it with xportr / haven::write_xpt (version 5)."
                for name, error in unreadable.items()], [], population_counts([], {})
    if "ADSL" not in adam:
        return ["No ADSL was exported: every population check and analysis denominator starts from ADSL."], [], population_counts([], adam)
    adsl = rows(adam["ADSL"]["columns"])
    counts = population_counts(adsl, adam)
    if adsl and "USUBJID" not in adsl[0]:
        return ["ADSL has no USUBJID."], [], counts
    dm = rows(sdtm.get("DM") or {})
    if not dm or "USUBJID" not in dm[0]:
        return ["The staged SDTM has no DM with USUBJID: ADSL cannot be checked against the subjects it was derived from."], [], counts

    problems: list[str] = []
    notes: list[str] = []
    adsl_by_subject = {row["USUBJID"]: row for row in adsl}
    dm_by_subject = {row["USUBJID"]: row for row in dm}
    adsl_subjects, dm_subjects = set(adsl_by_subject), set(dm_by_subject)
    duplicates = {subject for subject, records in Counter(row["USUBJID"] for row in adsl).items() if records > 1}
    if duplicates:
        problems.append(f"ADSL must have one record per subject; {len(duplicates)} subject(s) repeat: {examples(duplicates)}.")

    not_randomised = {subject for subject, row in dm_by_subject.items() if is_randomised(row.get("ARMCD"), row.get("ARM")) is False}
    randomised = dm_subjects - not_randomised
    if adsl_subjects not in (dm_subjects, randomised):
        parts = []
        if adsl_subjects - dm_subjects:
            parts.append(f"Not in DM: {examples(adsl_subjects - dm_subjects)}")
        if randomised - adsl_subjects:
            parts.append(f"Randomised in DM but missing from ADSL: {examples(randomised - adsl_subjects)}")
        partial = adsl_subjects & not_randomised
        if partial and partial != not_randomised:
            parts.append(f"Holds {len(partial)} of the {len(not_randomised)} screen-failure / not-assigned subjects (all or none): {examples(partial)}")
        problems.append(f"ADSL holds {len(adsl_subjects)} subject(s); DM has {len(dm_subjects)}, {len(randomised)} randomised "
                        f"({len(not_randomised)} screen failure / not assigned). ADSL must hold every DM subject or exactly the randomised ones. "
                        + "; ".join(parts) + ".")

    columns = set(adsl[0]) if adsl else set()
    if "SAFFL" in columns:
        if "EX" in sdtm and "USUBJID" in (sdtm["EX"] or {}) and "EXSTDTC" in sdtm["EX"]:
            exposed = {record["USUBJID"] for record in rows(sdtm["EX"]) if record["EXSTDTC"] != ""}
            flagged = {row["USUBJID"] for row in adsl if row["SAFFL"] == "Y"}
            problems.extend(flag_problem("SAFFL", flagged, exposed, "exposed", "an EX record with EXSTDTC, any EXDOSE"))
        else:
            notes.append("SAFFL not checked: the staged SDTM has no EX with USUBJID and EXSTDTC.")
    for flag in RANDOMISED_FLAGS:
        if flag in columns:
            flagged = {row["USUBJID"] for row in adsl if row[flag] == "Y"}
            problems.extend(flag_problem(flag, flagged, randomised, "randomised", "DM ARMCD/ARM not screen failure, not assigned or blank"))

    in_both = sorted((adsl_subjects & dm_subjects) - not_randomised)
    if "TRT01P" in columns and "ARM" in dm[0]:
        problems.extend(mapping_problems([(subject, dm_by_subject[subject]["ARM"], adsl_by_subject[subject]["TRT01P"]) for subject in in_both],
                                         "DM.ARM", "ADSL.TRT01P"))
    if "TRT01A" in columns and "ACTARM" in dm[0]:
        treated = [subject for subject in in_both if treated_subject(dm_by_subject[subject])]
        actual = mapping_problems([(subject, dm_by_subject[subject]["ACTARM"], adsl_by_subject[subject]["TRT01A"]) for subject in treated],
                                  "DM.ACTARM", "ADSL.TRT01A")
        planned = mapping_problems([(subject, dm_by_subject[subject]["ARM"], adsl_by_subject[subject]["TRT01A"]) for subject in in_both],
                                   "DM.ARM", "ADSL.TRT01A") if "ARM" in dm[0] else actual
        if actual and not planned:
            differing = {subject for subject in in_both if dm_by_subject[subject]["ACTARM"] != dm_by_subject[subject]["ARM"]}
            notes.append(f"ADSL.TRT01A follows DM.ARM (planned), not DM.ACTARM: {len(differing)} subject(s) have ACTARM != ARM "
                         f"({examples(differing)}). Accepted (the CDISC pilot ADSL convention), but TRT01A then states the planned arm.")
        else:
            problems.extend(actual)
            switched = {subject for subject in treated if "ARM" in dm[0] and dm_by_subject[subject]["ACTARM"] != dm_by_subject[subject]["ARM"]}
            if len(actual) == 0 and len(switched) > 0:
                notes.append(f"ADSL.TRT01A follows DM.ACTARM: {len(switched)} treated subject(s) have ACTARM != ARM ({examples(switched)}), "
                             "so their TRT01A differs from TRT01P.")

    for name, item in sorted(adam.items()):
        if name == "ADSL" or item.get("hasUsubjid") is False:
            continue
        orphans = set(item.get("subjects") or []) - adsl_subjects
        if orphans:
            problems.append(f"{name} has {len(orphans)} USUBJID(s) that are not in ADSL: {examples(orphans)}.")
    return problems, notes, counts


def treated_subject(row: dict[str, str]) -> bool:
    actual = (row.get("ACTARMCD"), row.get("ACTARM"))
    return is_randomised(*actual) is True and {normalise_arm(value) for value in actual}.isdisjoint(NOT_TREATED) is True


def summary_line(counts: dict) -> str:
    adsl = (counts["datasets"].get("ADSL") or {}).get("records")
    parts = [f"ADSL {adsl} subject(s)"] if adsl is not None else []
    for flag in ("SAFFL", "ITTFL", "RANDFL", "EFFFL"):
        population = counts["populations"].get(flag)
        if population is not None:
            arms = ", ".join(f"{arm} {count}" for arm, count in population["byArm"].items())
            parts.append(f"{flag} {population['total']}" + (f" ({arms})" if arms else ""))
    return "; ".join(parts)
