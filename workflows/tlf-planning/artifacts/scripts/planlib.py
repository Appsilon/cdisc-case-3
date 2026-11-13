"""Paths and the deterministic plan gate shared by the tlf-planning steps.

Every step of a run mounts the same worktree at /workspace:

    /workspace/tlf-planning/
        inputs/usdm.json                 the study definition (required)
        inputs/{sap,protocol,shells}/    optional context documents
        inputs/sdtm-inventory.json       what the delivered SDTM holds, for feasibility
        inputs/sdtm-study-facts.json     DM / EX / TS / TA columns for the data check
        study-check.json                 SDTM vs USDM data check (check-study)
        plan/study-model.json            written by the planner agent
        plan/tlf-plan.json               written by the planner agent
        plan/tlf-index.md                written by the planner agent
        plan-check.json                  the last gate result (the critic reads it)
        audit/coverage-report.md         written by the critic agent
        feedback.json                    what the last gate rejected, for the planner
        review-feedback.jsonl            every reviewer request, one JSON line each
        attempts.json                    how many times the gate has run since the last review

The gate checks what a script can check for certain: both files parse, every
candidate follows the candidate schema, every trace resolves into the study
model, numbering is unique and matches the type, and every resolved endpoint is
traced by at least one candidate (planned, or blocked with a reason). Judgement (is the plan complete for
this kind of study?) stays with the critic and the reviewer.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

from gate import GateLoop

WORKSPACE_DIR = Path(os.environ.get("MEDIFORCE_WORKSPACE_DIR", "/workspace"))
WORK_DIR = WORKSPACE_DIR / "tlf-planning"
INPUTS_DIR = WORK_DIR / "inputs"
PLAN_DIR = WORK_DIR / "plan"
AUDIT_DIR = WORK_DIR / "audit"
PLAN_CHECK_PATH = WORK_DIR / "plan-check.json"
STUDY_CHECK_PATH = WORK_DIR / "study-check.json"
LOOP = GateLoop(WORK_DIR)

STUDY_MODEL = "study-model.json"
TLF_PLAN = "tlf-plan.json"
TLF_INDEX = "tlf-index.md"
PLAN_FILES = (STUDY_MODEL, TLF_PLAN, TLF_INDEX)

TYPES = {"Table": "T", "Listing": "L", "Figure": "F"}
STATUSES = ("planned", "blocked", "needs-clarification")
PRIORITIES = ("primary", "secondary", "supportive")
CATEGORIES = ("disposition", "demographics", "efficacy", "pk", "exposure", "safety-ae", "safety-lab",
              "safety-vs", "conmeds", "pro", "other")
PLACEHOLDER = re.compile(r"to be determined|^\s*$|\*\*\*", re.IGNORECASE)
FINAL_ID = re.compile(r"^(?P<prefix>[TLF])-14-[0-9A-Za-z.\-]+$")


def load_json(path: Path, problems: list[str]):
    if path.is_file() is False:
        problems.append(f"{path.name} is missing from {path.parent}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        problems.append(f"{path.name} is not valid JSON: {error}")
        return None


def candidate_problems(candidate: dict, label: str, objective_ids: set[str], endpoint_ids: set[str]) -> list[str]:
    problems = []
    if candidate.get("type") not in TYPES:
        problems.append(f"{label}: type must be one of {', '.join(TYPES)}, got {candidate.get('type')!r}")
    if candidate.get("category") not in CATEGORIES:
        problems.append(f"{label}: category {candidate.get('category')!r} is not in the candidate schema enum")
    if not str(candidate.get("title") or "").strip():
        problems.append(f"{label}: title is empty")
    status = candidate.get("status")
    if status not in STATUSES:
        problems.append(f"{label}: status must be one of {', '.join(STATUSES)}, got {status!r}")
    elif status != "planned" and not str(candidate.get("status_reason") or "").strip():
        problems.append(f"{label}: status {status} needs a status_reason")
    if candidate.get("priority") not in PRIORITIES:
        problems.append(f"{label}: priority must be one of {', '.join(PRIORITIES)}, got {candidate.get('priority')!r}")

    traces = candidate.get("traces_to")
    if isinstance(traces, dict) is False:
        return problems + [f"{label}: traces_to is missing"]
    objectives = traces.get("objective_ids") or []
    endpoints = traces.get("endpoint_ids") or []
    rule = str(traces.get("regulatory_rule") or "").strip()
    if not objectives and not endpoints and not rule:
        problems.append(f"{label}: traces_to names no objective, endpoint or regulatory_rule (orphan)")
    problems += [f"{label}: traces_to.objective_ids names {item}, which is not in study-model.json"
                 for item in objectives if item not in objective_ids]
    problems += [f"{label}: traces_to.endpoint_ids names {item}, which is not in study-model.json"
                 for item in endpoints if item not in endpoint_ids]

    final_id = candidate.get("final_id")
    if status == "planned":
        match = FINAL_ID.match(str(final_id or ""))
        if match is None:
            problems.append(f"{label}: a planned output needs a final_id like T-14-3.01 / L-14-5.01 / F-14-1, got {final_id!r}")
        elif TYPES.get(candidate.get("type")) not in (None, match.group("prefix")):
            problems.append(f"{label}: final_id {final_id} does not match type {candidate.get('type')}")
    elif final_id not in (None, ""):
        problems.append(f"{label}: {status} outputs stay unnumbered (final_id null), got {final_id!r}")
    return problems


def staged_primary_endpoints() -> dict[str, str]:
    from studycheck import primary_endpoint_ids
    usdm_path = INPUTS_DIR / "usdm.json"
    return primary_endpoint_ids(json.loads(usdm_path.read_text(encoding="utf-8"))) if usdm_path.is_file() else {}


def check_plan(plan_dir: Path = PLAN_DIR, primary: dict[str, str] | None = None) -> dict:
    """Run the gate over the plan files; primary = the USDM's primary endpoints {id: text}.

    Result: {problems, counts}; counts.blockedPrimary lists primary endpoints whose every output is blocked (needs-clarification goes to the
    statistician, not here) - the data
    cannot answer the study's primary question, which the planner cannot fix, so the run stops."""
    problems: list[str] = []
    model = load_json(plan_dir / STUDY_MODEL, problems)
    plan = load_json(plan_dir / TLF_PLAN, problems)
    index_path = plan_dir / TLF_INDEX
    if index_path.is_file() is False:
        problems.append(f"{TLF_INDEX} is missing from {plan_dir}")
    if model is None or plan is None:
        return {"problems": problems, "counts": {}}

    if isinstance(model, dict) is False or isinstance(model.get("objectives"), list) is False \
            or isinstance(model.get("endpoints"), list) is False:
        return {"problems": problems + [f"{STUDY_MODEL} needs objectives[] and endpoints[] (references/study-model-schema.md)"],
                "counts": {}}
    if isinstance(plan, list) is False or not plan:
        return {"problems": problems + [f"{TLF_PLAN} must be a non-empty array of candidates"], "counts": {}}

    objective_ids = {str(item.get("id")) for item in model["objectives"] if isinstance(item, dict)}
    endpoints = [item for item in model["endpoints"] if isinstance(item, dict)]
    endpoint_ids = {str(item.get("id")) for item in endpoints}

    candidate_ids = Counter(str(item.get("candidate_id") or "") for item in plan if isinstance(item, dict))
    problems += [f"candidate_id {key!r} is used {count} times" for key, count in candidate_ids.items() if key and count > 1]
    final_ids = Counter(str(item.get("final_id")) for item in plan
                        if isinstance(item, dict) and item.get("status") == "planned" and item.get("final_id"))
    problems += [f"final_id {key} is used {count} times" for key, count in final_ids.items() if count > 1]

    traced: set[str] = set()
    planned_endpoints: set[str] = set()
    for position, candidate in enumerate(plan, start=1):
        if isinstance(candidate, dict) is False:
            problems.append(f"{TLF_PLAN} item {position} is not an object")
            continue
        label = str(candidate.get("candidate_id") or f"item {position}")
        if not candidate.get("candidate_id"):
            problems.append(f"{label}: candidate_id is empty")
        problems += candidate_problems(candidate, label, objective_ids, endpoint_ids)
        endpoint_trace = (candidate.get("traces_to") or {}).get("endpoint_ids") if isinstance(candidate.get("traces_to"), dict) else []
        traced.update(endpoint_trace or [])
        if candidate.get("status") == "planned":
            planned_endpoints.update(endpoint_trace or [])

    for endpoint_id, text in (primary or {}).items():
        modelled = next((item for item in endpoints if str(item.get("id")) == endpoint_id), None)
        if modelled is None:
            problems.append(f"Primary endpoint {endpoint_id} of the USDM is missing from {STUDY_MODEL} (keep the USDM ids verbatim)")
        elif modelled.get("resolved") is not True and PLACEHOLDER.search(text) is None:
            problems.append(f"Primary endpoint {endpoint_id} is marked unresolved, but the USDM states it: {text[:120]!r}")

    resolved = [item for item in endpoints if item.get("resolved") is True]
    for endpoint in resolved:
        if endpoint.get("id") not in traced:
            problems.append(f"Endpoint {endpoint.get('id')} ({endpoint.get('name')}) is resolved but no candidate traces to it "
                            "(plan it, or keep it as blocked with a status_reason - never drop it)")

    index_text = index_path.read_text(encoding="utf-8") if index_path.is_file() else ""
    missing_from_index = sorted(key for key in final_ids if re.search(rf"(?<![\w.-]){re.escape(key)}(?![\w.-])", index_text) is None)
    if missing_from_index:
        problems.append(f"{TLF_INDEX} does not list planned output(s) {', '.join(missing_from_index[:10])}")

    planned = [item for item in plan if isinstance(item, dict) and item.get("status") == "planned"]
    counts = {
        "tables": sum(1 for item in planned if item.get("type") == "Table"),
        "listings": sum(1 for item in planned if item.get("type") == "Listing"),
        "figures": sum(1 for item in planned if item.get("type") == "Figure"),
        "flagged": len(plan) - len(planned),
        "objectives": len(objective_ids),
        "endpoints": len(endpoints),
        "unresolvedEndpoints": sum(1 for item in endpoints if item.get("resolved") is False),
        "blockedEndpoints": sorted(str(item.get("id")) for item in resolved
                                   if item.get("id") in traced and item.get("id") not in planned_endpoints),
    }
    only_blocked = {endpoint for endpoint in counts["blockedEndpoints"]
                    if all(item.get("status") == "blocked" for item in plan if isinstance(item, dict)
                           and endpoint in ((item.get("traces_to") or {}).get("endpoint_ids") or []))}
    counts["blockedPrimary"] = [key for key in counts["blockedEndpoints"] if key in (primary or {}) and key in only_blocked]
    return {"problems": problems, "counts": counts}
