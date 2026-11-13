"""Paths and the deterministic USDM gate shared by the digitize-protocol steps.

Every step of a run mounts the same worktree at /workspace:

    /workspace/digitize-protocol/
        inputs/protocol/pages/page-001.txt   the protocol's text, one file per PDF page (1-based, physical)
        inputs/protocol/protocol.txt         the same text in one file, "=== Page N ===" before each page
        inputs/sap/...                       the SAP, same layout (optional)
        inputs/schema/USDM_API.json          the DDF-RA USDM 4.0 OpenAPI document (the gate's schema)
        usdm/usdm.json                       written by the extraction agent
        usdm/usdm-citations.json             written by the extraction agent: entity id -> {page, quote}
        usdm-check.json                      the last gate result
        feedback.json                        what the last gate rejected, for the agent
        review-feedback.jsonl                every reviewer / CORE change request, one JSON line each
        attempts.json                        how many times the gate has run since the last review

The gate checks what a script can decide for certain: the document validates
against the USDM 4.0 schema, ids are unique and every *Id / *Ids reference
resolves, the v1 entities are present and wired (objectives with endpoints,
arms x epochs cells, inclusion and exclusion criteria, encounters and activities
on one main timeline), and every extracted entity carries a citation whose quote
is found on the cited page. Whether the extraction is *right* stays with the
reviewer.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from gate import GateLoop
from mfpkg import replace_files, step_output

WORKFLOW = "digitize-protocol"
WORKSPACE_DIR = Path(os.environ.get("MEDIFORCE_WORKSPACE_DIR", "/workspace"))
WORK_DIR = WORKSPACE_DIR / "digitize-protocol"
INPUTS_DIR = WORK_DIR / "inputs"
SCHEMA_PATH = INPUTS_DIR / "schema" / "USDM_API.json"
USDM_DIR = WORK_DIR / "usdm"
CHECK_PATH = WORK_DIR / "usdm-check.json"
LOOP = GateLoop(WORK_DIR)

USDM = "usdm.json"
CITATIONS = "usdm-citations.json"
USDM_FILES = (USDM, CITATIONS)
DOCUMENTS = ("protocol", "sap")
USDM_VERSION = "4.0.0"

CITED_TYPES = ("Objective", "Endpoint", "Estimand", "StudyArm", "StudyEpoch", "StudyElement", "EligibilityCriterion",
               "StudyDesignPopulation", "Encounter", "Activity", "ScheduledActivityInstance")
PRIMARY_OBJECTIVE = "C85826"
INCLUSION = "C25532"
EXCLUSION = "C25370"
MIN_QUOTE_CHARACTERS = 20
MAX_SCHEMA_PROBLEMS = 40

PUNCTUATION = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-",
                             "\u2010": "-", "\u2011": "-", "\u2212": "-", "\u00ad": None})


def squash(text: str) -> str:
    """Text as the citation check compares it: NFKC, plain quotes and dashes, no soft hyphens or whitespace, case-folded.

    PDF text breaks lines and spaces words unpredictably, so whitespace carries no
    meaning here; a 20+ character quote stays specific without it."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).translate(PUNCTUATION)).casefold()


def page_path(document: str, page: int) -> Path:
    return INPUTS_DIR / document / "pages" / f"page-{page:03d}.txt"


def staged_documents() -> dict[str, int]:
    """Document -> page count, for the documents stage-inputs extracted."""
    counts = {}
    for document in DOCUMENTS:
        pages = INPUTS_DIR / document / "pages"
        if pages.is_dir():
            counts[document] = len(list(pages.glob("page-*.txt")))
    return counts


def base_package(step_input: dict) -> dict:
    """The study package this run started from, plus the documents uploaded in this run."""
    resolved = step_output(step_input, "resolve-inputs")
    package = resolved.get("package") or {}
    if resolved.get("needsUpload") is True:
        run_id = os.environ.get("RUN_ID", "")
        uploaded = [{**item, "producedBy": {"workflow": WORKFLOW, "runId": run_id, "step": "upload-protocol"}}
                    for item in step_output(step_input, "stage-inputs").get("inputFiles") or []]
        package = replace_files(package, uploaded)
    return package


def load_json(path: Path, problems: list[str]):
    if path.is_file() is False:
        problems.append(f"{path.name} is missing from {path.parent}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        problems.append(f"{path.name} is not valid JSON: {error}")
        return None


def schema_validator(schema_path: Path = SCHEMA_PATH):
    """A Draft 2020-12 validator rooted at Wrapper-Input, from the DDF-RA OpenAPI components."""
    from jsonschema import Draft202012Validator

    api = json.loads(schema_path.read_text(encoding="utf-8"))
    text = json.dumps(api["components"]["schemas"]).replace('"#/components/schemas/', '"#/$defs/')
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": "#/$defs/Wrapper-Input", "$defs": json.loads(text)}
    return Draft202012Validator(schema)


def leaf_errors(error) -> list:
    """An anyOf/oneOf error says only that no branch matched; report the errors of the branch the object meant
    (the one whose instanceType it carries, else the closest) so the message names the field to fix."""
    if error.validator not in ("anyOf", "oneOf") or not error.context:
        return [error]
    branches: dict[int, list] = defaultdict(list)
    for sub_error in error.context:
        branches[sub_error.relative_schema_path[0]].append(sub_error)
    candidates = list(branches.values())
    if isinstance(error.instance, dict):
        # a nullable object is anyOf [X, null]: "is not of type 'null'" never names the field to fix
        candidates = [errors for errors in candidates
                      if not (len(errors) == 1 and errors[0].validator == "type" and len(errors[0].relative_path) == 0)] or candidates
    intended = [errors for errors in candidates if all(list(sub.relative_path) != ["instanceType"] for sub in errors)]
    chosen = min(intended or candidates, key=len)
    return [leaf for sub_error in chosen for leaf in leaf_errors(sub_error)]


def schema_problems(document: dict, schema_path: Path = SCHEMA_PATH) -> list[str]:
    """Schema errors, collapsed per (path pattern, error kind) so one repeated mistake reads as one line."""
    groups: dict[tuple[str, str], list] = defaultdict(list)
    leaves = [leaf for error in schema_validator(schema_path).iter_errors(document) for leaf in leaf_errors(error)]
    for error in leaves:
        pattern = re.sub(r"/\d+", "/*", "/" + "/".join(str(part) for part in error.absolute_path))
        groups[(pattern, str(error.validator))].append(error)
    problems = []
    for (pattern, _kind), errors in sorted(groups.items()):
        first = errors[0]
        where = "/" + "/".join(str(part) for part in first.absolute_path)
        message = first.message if len(first.message) <= 200 else first.message[:197] + "..."
        problems.append(f"schema: {where}: {message}" + (f" (and {len(errors) - 1} more at {pattern})" if len(errors) > 1 else ""))
    if len(problems) > MAX_SCHEMA_PROBLEMS:
        problems = problems[:MAX_SCHEMA_PROBLEMS] + [f"schema: ... and {len(problems) - MAX_SCHEMA_PROBLEMS} more error group(s)"]
    return problems


def walk(node, path: str = ""):
    """Every dict in the document with its JSON path."""
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from walk(value, f"{path}/{key}")
    elif isinstance(node, list):
        for position, value in enumerate(node):
            yield from walk(value, f"{path}/{position}")


def reference_problems(document: dict) -> tuple[list[str], dict[str, dict]]:
    """Unique ids, and every non-empty *Id / *Ids value names an id in the document."""
    entities: dict[str, dict] = {}
    duplicates = Counter()
    for _path, node in walk(document):
        identifier = node.get("id")
        if isinstance(identifier, str) and identifier:
            duplicates[identifier] += 1
            entities[identifier] = node
    problems = [f"id {identifier} is used {count} times" for identifier, count in sorted(duplicates.items()) if count > 1]
    dangling: dict[str, list[str]] = defaultdict(list)
    for path, node in walk(document):
        for key, value in node.items():
            if key == "id" or (key.endswith("Id") or key.endswith("Ids")) is False:
                continue
            for target in value if isinstance(value, list) else [value]:
                if isinstance(target, str) and target and target not in entities:
                    dangling[re.sub(r"/\d+", "/*", f"{path}/{key}")].append(f"{path}/{key} -> {target}")
    for pattern, examples in sorted(dangling.items()):
        problems.append(f"dangling reference: {examples[0]} names no id in usdm.json"
                        + (f" (and {len(examples) - 1} more at {pattern})" if len(examples) > 1 else ""))
    return problems, entities


def code_of(value, field: str = "code") -> str:
    """A field (the C-code by default, or "decode") of a Code, or of an AliasCode's standardCode."""
    if isinstance(value, dict) is False:
        return ""
    standard = value.get("standardCode")
    return str((standard if isinstance(standard, dict) else value).get(field) or "")


def design_problems(document: dict) -> tuple[list[str], dict]:
    """The v1 extraction scope is present and wired together."""
    problems: list[str] = []
    if document.get("usdmVersion") != USDM_VERSION:
        problems.append(f"usdmVersion must be {USDM_VERSION!r}, got {document.get('usdmVersion')!r}")
    versions = (document.get("study") or {}).get("versions") or []
    if not versions:
        return problems + ["study.versions is empty: write one StudyVersion"], {}
    version = versions[0]
    designs = version.get("studyDesigns") or []
    if not designs:
        return problems + ["study.versions[0].studyDesigns is empty: write one InterventionalStudyDesign"], {}
    design = designs[0]

    objectives = design.get("objectives") or []
    endpoints = [endpoint for objective in objectives for endpoint in objective.get("endpoints") or []]
    if not objectives:
        problems.append("studyDesigns[0].objectives is empty")
    if objectives and all(code_of(objective.get("level")) != PRIMARY_OBJECTIVE for objective in objectives):
        problems.append(f"no objective has level {PRIMARY_OBJECTIVE} (Primary Objective)")
    problems += [f"objective {objective.get('id')} has no endpoints" for objective in objectives if not objective.get("endpoints")]
    problems += [f"{item.get('instanceType')} {item.get('id')} has empty text"
                 for item in objectives + endpoints if not str(item.get("text") or "").strip()]

    arms = design.get("arms") or []
    epochs = design.get("epochs") or []
    cells = {(cell.get("armId"), cell.get("epochId")) for cell in design.get("studyCells") or []}
    for kind, items in (("arms", arms), ("epochs", epochs), ("elements", design.get("elements") or [])):
        if not items:
            problems.append(f"studyDesigns[0].{kind} is empty")
    missing_cells = [f"{arm.get('id')} x {epoch.get('id')}" for arm in arms for epoch in epochs if (arm.get("id"), epoch.get("id")) not in cells]
    if missing_cells:
        problems.append(f"{len(missing_cells)} arm x epoch pair(s) have no studyCell, e.g. {missing_cells[0]} (one cell per arm per epoch)")

    criteria = design.get("eligibilityCriteria") or []
    categories = Counter(code_of(criterion.get("category")) for criterion in criteria)
    if categories[INCLUSION] == 0:
        problems.append(f"no eligibility criterion has category {INCLUSION} (Inclusion Criteria)")
    if categories[EXCLUSION] == 0:
        problems.append(f"no eligibility criterion has category {EXCLUSION} (Exclusion Criteria)")
    items = {item.get("id"): item for item in version.get("eligibilityCriterionItems") or []}
    problems += [f"eligibility criterion {criterion.get('id')}: its item {criterion.get('criterionItemId')} has empty text"
                 for criterion in criteria
                 if criterion.get("criterionItemId") in items and not str(items[criterion["criterionItemId"]].get("text") or "").strip()]

    encounters = design.get("encounters") or []
    activities = design.get("activities") or []
    timelines = design.get("scheduleTimelines") or []
    main = [timeline for timeline in timelines if timeline.get("mainTimeline") is True]
    if not encounters:
        problems.append("studyDesigns[0].encounters is empty")
    if not activities:
        problems.append("studyDesigns[0].activities is empty")
    if len(main) != 1:
        problems.append(f"exactly one scheduleTimeline needs mainTimeline true, found {len(main)}")
    instances = [instance for timeline in timelines for instance in timeline.get("instances") or []]
    main_instances = [instance for timeline in main for instance in timeline.get("instances") or []]
    on_main = {instance.get("encounterId") for instance in main_instances}
    unscheduled_encounters = [encounter.get("id") for encounter in encounters if encounter.get("id") not in on_main]
    if unscheduled_encounters:
        problems.append(f"encounter(s) with no ScheduledActivityInstance on the main timeline: {', '.join(map(str, unscheduled_encounters))}")
    scheduled = {activity for instance in instances for activity in instance.get("activityIds") or []}
    unscheduled = [activity.get("id") for activity in activities if activity.get("id") not in scheduled]
    if unscheduled:
        problems.append(f"activity(ies) scheduled in no ScheduledActivityInstance: {', '.join(map(str, unscheduled))}")

    counts = {
        "objectives": len(objectives), "endpoints": len(endpoints), "estimands": len(design.get("estimands") or []),
        "arms": len(arms), "epochs": len(epochs), "elements": len(design.get("elements") or []), "cells": len(cells),
        "inclusion": categories[INCLUSION], "exclusion": categories[EXCLUSION],
        "encounters": len(encounters), "activities": len(activities), "timelines": len(timelines),
        "scheduledActivities": sum(len(instance.get("activityIds") or []) for instance in main_instances),
    }
    return problems, counts


def citation_problems(citations, entities: dict[str, dict], documents: dict[str, int]) -> tuple[list[str], dict]:
    """Every extracted entity is cited, and every citation's quote is on the page it names."""
    if isinstance(citations, dict) is False:
        return [f"{CITATIONS} must be an object: entity id -> {{page, quote}}"], {}
    problems: list[str] = []
    page_text: dict[tuple[str, int], str] = {}
    cited_pages: set[tuple[str, int]] = set()
    for identifier, citation in sorted(citations.items()):
        if identifier not in entities:
            problems.append(f"citation for {identifier}: no entity with that id in usdm.json")
            continue
        if isinstance(citation, dict) is False:
            problems.append(f"citation for {identifier}: must be {{page, quote}}")
            continue
        document = citation.get("document") or "protocol"
        page = citation.get("page")
        quote = str(citation.get("quote") or "")
        if document not in documents:
            problems.append(f"citation for {identifier}: document {document!r} was not staged ({', '.join(documents) or 'none'})")
            continue
        if type(page) is not int or page < 1 or page > documents[document]:
            problems.append(f"citation for {identifier}: page must be a {document} page number 1..{documents[document]}, got {page!r}")
            continue
        if len(squash(quote)) < MIN_QUOTE_CHARACTERS:
            problems.append(f"citation for {identifier}: quote must be at least {MIN_QUOTE_CHARACTERS} characters copied from the page")
            continue
        key = (document, page)
        if key not in page_text:
            page_text[key] = squash(page_path(document, page).read_text(encoding="utf-8"))
        if squash(quote) not in page_text[key]:
            problems.append(f"citation for {identifier}: quote not found on {document} page {page}: {quote[:120]!r}")
            continue
        cited_pages.add(key)
    uncited = defaultdict(list)
    for identifier, entity in entities.items():
        if entity.get("instanceType") in CITED_TYPES and identifier not in citations:
            uncited[entity["instanceType"]].append(identifier)
    for kind, identifiers in sorted(uncited.items()):
        problems.append(f"{len(identifiers)} {kind}(s) without a citation: {', '.join(identifiers[:8])}" + (" ..." if len(identifiers) > 8 else ""))
    return problems, {"citations": len(citations), "citedPages": len(cited_pages)}


def check_usdm(usdm_dir: Path = USDM_DIR, schema_path: Path = SCHEMA_PATH) -> dict:
    """Run the gate over usdm.json + usdm-citations.json. Result: {problems, counts}."""
    problems: list[str] = []
    document = load_json(usdm_dir / USDM, problems)
    citations = load_json(usdm_dir / CITATIONS, problems)
    if isinstance(document, dict) is False:
        return {"problems": problems or [f"{USDM} must be a JSON object (the USDM Wrapper: study, usdmVersion, ...)"], "counts": {}}
    structure = schema_problems(document, schema_path)
    reference_issues, entities = reference_problems(document)
    problems += structure + reference_issues
    counts: dict = {}
    if not structure:  # the design checks read the document's shape; on a schema failure fix the shape first
        design_issues, counts = design_problems(document)
        problems += design_issues
    if citations is not None:
        citation_issues, citation_counts = citation_problems(citations, entities, staged_documents())
        problems += citation_issues
        counts.update(citation_counts)
    return {"problems": problems, "counts": counts}
